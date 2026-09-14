"""Sécurité & conformité RGPD (CDC §10, PROMPT 14).

1. Anonymisation : l'audio n'est jamais persisté ; le texte journalisé est
   expurgé des données personnelles (n° CIN, téléphones, e-mails, dates).
2. Sessions anonymes : UUID généré côté borne, jamais lié à une identité.
3. Rate limiting : 30 requêtes/min et 5 transcriptions/min par borne_id.
4. Authentification admin : JWT 8 h, refresh 7 j, TOTP (2FA) pour super-admin,
   journal d'accès.
5. Chiffrement : HTTPS (reverse proxy), chiffrement at-rest côté PostgreSQL.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import settings
from ..db import AdminAccessLog, AdminUser, get_db

# ── 1. Anonymisation ─────────────────────────────────────────────────────

PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z]{1,2}\s?\d{5,7}\b"), "[CIN]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?:\+|00)?\d[\d\s.-]{7,}\d"), "[TEL]"),
    (re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"), "[DATE]"),
]


def anonymize_text(text: str) -> str:
    """Retire les données personnelles identifiables d'un texte avant journalisation."""
    for pattern, repl in PII_PATTERNS:
        text = pattern.sub(repl, text)
    return text[:500]


def anonymous_session_id(value: str | None) -> str:
    """Valide l'UUID de session de la borne ; en génère un nouveau sinon."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return str(uuid.uuid4())


def hash_ip(ip: str | None) -> str | None:
    """Empreinte salée de l'IP (journal admin sans IP en clair)."""
    if not ip:
        return None
    return hashlib.sha256(f"{settings.jwt_secret}:{ip}".encode()).hexdigest()


# ── 3. Rate limiting ─────────────────────────────────────────────────────


class RateLimiter:
    """Fenêtre glissante d'une minute ; Redis si disponible, mémoire sinon."""

    def __init__(self, redis_url: str | None = None):
        self._local: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._redis = None
        if redis_url:
            try:
                import redis

                client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
                client.ping()
                self._redis = client
            except Exception:  # noqa: BLE001 — borne autonome : repli mémoire
                self._redis = None

    def hit(self, key: str, limit: int, window_s: int = 60) -> bool:
        """Enregistre un appel ; retourne False si la limite est dépassée."""
        now = time.time()
        if self._redis is not None:
            try:
                rkey = f"rl:{key}"
                pipe = self._redis.pipeline()
                pipe.zremrangebyscore(rkey, 0, now - window_s)
                pipe.zadd(rkey, {f"{now}:{secrets.token_hex(4)}": now})
                pipe.zcard(rkey)
                pipe.expire(rkey, window_s)
                count = pipe.execute()[2]
                return count <= limit
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            q = self._local[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._local.clear()


rate_limiter = RateLimiter(settings.redis_url)


def enforce_rate_limit(kind: str, borne_id: str) -> None:
    """Lève HTTP 429 si la borne dépasse son quota pour ce type d'appel."""
    limits = {"audio": settings.rate_limit_audio_per_min, "tts": settings.rate_limit_tts_per_min}
    limit = limits.get(kind, settings.rate_limit_queries_per_min)
    if not rate_limiter.hit(f"{kind}:{borne_id}", limit):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Trop de requêtes, réessayez dans une minute.")


# ── 4. Authentification admin ────────────────────────────────────────────

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hachage PBKDF2-SHA256 salé (format : pbkdf2$iter$salt$hash)."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe en temps constant."""
    try:
        _, iterations, salt_b64, hash_b64 = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def totp_now(secret_b32: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    """Code TOTP RFC 6238 (compatible Google Authenticator)."""
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = int((at or time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str | None) -> bool:
    """Accepte le code courant et ±1 pas (dérive d'horloge)."""
    if not code:
        return False
    now = time.time()
    return any(hmac.compare_digest(totp_now(secret_b32, now + d * 30), code.strip()) for d in (-1, 0, 1))


def create_tokens(user: AdminUser) -> dict:
    """Émet un access token (8 h) et un refresh token (7 j)."""
    now = datetime.now(timezone.utc)
    base = {"sub": user.id, "email": user.email, "role": user.role}
    access = jwt.encode({**base, "type": "access", "iat": now, "exp": now + timedelta(hours=settings.jwt_expire_hours)},
                        settings.jwt_secret, algorithm="HS256")
    refresh = jwt.encode({**base, "type": "refresh", "iat": now, "exp": now + timedelta(days=settings.refresh_expire_days)},
                         settings.jwt_secret, algorithm="HS256")
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "role": user.role}


def decode_token(token: str, expected_type: str) -> dict:
    """Décode et valide un JWT ; lève HTTP 401 sinon."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide") from exc
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Type de jeton invalide")
    return payload


bearer = HTTPBearer(auto_error=False)


def current_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> AdminUser:
    """Dépendance : administrateur authentifié."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise")
    payload = decode_token(creds.credentials, "access")
    user = db.get(AdminUser, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utilisateur inconnu")
    return user


def require_role(*roles: str):
    """Dépendance : rôle parmi ``roles`` (super-admin toujours autorisé)."""

    def checker(user: AdminUser = Depends(current_admin)) -> AdminUser:
        if user.role != "super-admin" and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
        return user

    return checker


def log_admin_access(db: Session, request: Request | None, email: str | None, action: str, cible: str | None = None) -> None:
    """Journalise une action admin (CDC : logs d'accès admin complets)."""
    ip = request.client.host if request and request.client else None
    db.add(AdminAccessLog(email=email, action=action, cible=cible, ip_hash=hash_ip(ip)))
    db.commit()
