"""Routes du back-office (JWT) — CDC §06 et §09.

Workflow : BROUILLON → REVIEW → (VALIDÉ) → PRODUCTION ; INACTIF sans suppression.
Chaque enregistrement crée une version ; rollback possible.
"""

from __future__ import annotations

import logging
import os
import smtplib
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rag.generator import documents_for

from ..db import AdminUser, Demarche, DemarcheVersion, HistoriqueInteraction, get_db
from ..middleware.security import (create_tokens, current_admin, decode_token, log_admin_access, require_role, verify_password,
                                   verify_totp)
from ..schemas import DemarcheCreate, DemarcheDetail, LoginRequest, RefreshRequest, TokenResponse, VersionOut
from ..services.knowledge import apply_content, localized_titles, rag_holder, reindex_vectors, snapshot, to_knowledge

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


def _detail(d: Demarche) -> DemarcheDetail:
    return DemarcheDetail(id=d.id, slug=d.slug, categorie=d.categorie, titres=localized_titles(d),
                          administration=d.administration, cout_mad=float(d.cout_mad or 0), delai_jours=d.delai_jours,
                          source_url=d.source_url, statut=d.statut, version=d.version, contenu=to_knowledge(d),
                          valide_par=d.valide_par)


def _get(db: Session, demarche_id: str) -> Demarche:
    d = db.get(Demarche, demarche_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Démarche introuvable")
    return d


def notify_reviewers(d: Demarche, auteur: str) -> None:
    """Notification e-mail « soumis en review » (SMTP optionnel, sinon journal)."""
    host, to = os.getenv("SMTP_HOST"), os.getenv("REVIEW_NOTIFY_EMAIL")
    if not host or not to:
        log.info("Review demandée pour %s par %s (SMTP non configuré)", d.slug, auteur)
        return
    msg = EmailMessage()
    msg["Subject"] = f"[WathiqaDoc] Démarche à valider : {d.titre_fr}"
    msg["From"] = os.getenv("SMTP_FROM", "noreply@wathiqadoc.ma")
    msg["To"] = to
    msg.set_content(f"{auteur} a soumis « {d.titre_fr} » (v{d.version}) pour validation.")
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=5) as s:
            s.starttls()
            if os.getenv("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        log.error("Notification e-mail échouée : %s", exc)


# ── Authentification ─────────────────────────────────────────────────────


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(AdminUser).where(AdminUser.email == req.email.lower().strip()))
    if user is None or not verify_password(req.password, user.password_hash):
        log_admin_access(db, request, req.email, "login_echec")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")
    if user.role == "super-admin" and user.totp_secret and not verify_totp(user.totp_secret, req.totp):
        log_admin_access(db, request, user.email, "login_2fa_echec")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Code 2FA requis ou invalide")
    log_admin_access(db, request, user.email, "login")
    return create_tokens(user)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    payload = decode_token(req.refresh_token, "refresh")
    user = db.get(AdminUser, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utilisateur inconnu")
    return create_tokens(user)


@router.get("/me")
def me(user: AdminUser = Depends(current_admin)) -> dict:
    return {"email": user.email, "role": user.role, "totp": bool(user.totp_secret)}


# ── Démarches ────────────────────────────────────────────────────────────


@router.get("/demarches", response_model=list[DemarcheDetail])
def list_demarches(q: str | None = None, statut: str | None = None, db: Session = Depends(get_db),
                   _: AdminUser = Depends(current_admin)) -> list[DemarcheDetail]:
    stmt = select(Demarche).order_by(Demarche.categorie, Demarche.slug)
    if statut:
        stmt = stmt.where(Demarche.statut == statut)
    items = [_detail(d) for d in db.scalars(stmt)]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i.slug or any(ql in (t or "").lower() for t in i.titres.values())]
    return items


@router.get("/demarches/{demarche_id}", response_model=DemarcheDetail)
def get_demarche(demarche_id: str, db: Session = Depends(get_db), _: AdminUser = Depends(current_admin)) -> DemarcheDetail:
    return _detail(_get(db, demarche_id))


@router.post("/demarches", response_model=DemarcheDetail, status_code=201)
def create_demarche(body: DemarcheCreate, request: Request, db: Session = Depends(get_db),
                    user: AdminUser = Depends(current_admin)) -> DemarcheDetail:
    if db.scalar(select(Demarche).where(Demarche.slug == body.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce slug existe déjà")
    data = body.model_dump()
    d = Demarche(slug=body.slug, categorie=body.categorie, titre_fr=body.titres.fr or body.slug, statut="brouillon", version=1)
    db.add(d)
    apply_content(db, d, data)
    db.flush()
    snapshot(db, d, user.email, publiee=False)
    db.commit()
    log_admin_access(db, request, user.email, "creer_demarche", d.slug)
    return _detail(d)


@router.put("/demarches/{demarche_id}", response_model=DemarcheDetail)
def update_demarche(demarche_id: str, body: DemarcheCreate, request: Request, db: Session = Depends(get_db),
                    user: AdminUser = Depends(current_admin)) -> DemarcheDetail:
    """Enregistre un brouillon : nouvelle version, la borne garde la version publiée."""
    d = _get(db, demarche_id)
    d.version += 1
    d.statut = "brouillon"
    apply_content(db, d, body.model_dump())
    db.flush()
    snapshot(db, d, user.email, publiee=False)
    db.commit()
    log_admin_access(db, request, user.email, "modifier_demarche", f"{d.slug} v{d.version}")
    return _detail(d)


@router.post("/demarches/{demarche_id}/submit", response_model=DemarcheDetail)
def submit_review(demarche_id: str, request: Request, db: Session = Depends(get_db),
                  user: AdminUser = Depends(current_admin)) -> DemarcheDetail:
    d = _get(db, demarche_id)
    d.statut = "review"
    db.commit()
    notify_reviewers(d, user.email)
    log_admin_access(db, request, user.email, "soumettre_review", d.slug)
    return _detail(d)


@router.post("/demarches/{demarche_id}/publish", response_model=DemarcheDetail)
def publish(demarche_id: str, request: Request, db: Session = Depends(get_db),
            user: AdminUser = Depends(require_role("reviewer"))) -> DemarcheDetail:
    """Valider & publier : version publiée, régénération des chunks, rechargement de la borne."""
    d = _get(db, demarche_id)
    if not (d.contenu or {}).get("titres", {}).get("fr") or not (d.contenu or {}).get("documents"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Titre FR et au moins un document requis pour publier")
    d.statut, d.actif, d.valide_par = "production", True, user.email
    snapshot(db, d, user.email, publiee=True)
    db.commit()
    rag_holder.rebuild(db)
    reindex_vectors(to_knowledge(d))
    log_admin_access(db, request, user.email, "publier_demarche", f"{d.slug} v{d.version}")
    return _detail(d)


@router.post("/demarches/{demarche_id}/deactivate", response_model=DemarcheDetail)
def deactivate(demarche_id: str, request: Request, db: Session = Depends(get_db),
               user: AdminUser = Depends(require_role("reviewer"))) -> DemarcheDetail:
    d = _get(db, demarche_id)
    d.statut, d.actif = "inactif", False
    db.commit()
    rag_holder.rebuild(db)
    log_admin_access(db, request, user.email, "desactiver_demarche", d.slug)
    return _detail(d)


@router.get("/demarches/{demarche_id}/versions", response_model=list[VersionOut])
def versions(demarche_id: str, db: Session = Depends(get_db), _: AdminUser = Depends(current_admin)) -> list[VersionOut]:
    d = _get(db, demarche_id)
    return [VersionOut(version=v.version, auteur=v.auteur, cree_le=v.cree_le.isoformat()) for v in reversed(d.versions)]


@router.post("/demarches/{demarche_id}/rollback/{version}", response_model=DemarcheDetail)
def rollback(demarche_id: str, version: int, request: Request, db: Session = Depends(get_db),
             user: AdminUser = Depends(require_role("reviewer"))) -> DemarcheDetail:
    """Restaure une version antérieure en brouillon (nouvelle version, à republier)."""
    d = _get(db, demarche_id)
    target = db.scalar(select(DemarcheVersion).where(DemarcheVersion.demarche_id == d.id, DemarcheVersion.version == version))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Version introuvable")
    d.version = max(v.version for v in d.versions) + 1
    d.statut = "brouillon"
    apply_content(db, d, target.snapshot)
    db.flush()
    snapshot(db, d, user.email, publiee=False)
    db.commit()
    log_admin_access(db, request, user.email, "rollback_demarche", f"{d.slug} v{version} -> v{d.version}")
    return _detail(d)


@router.get("/demarches/{demarche_id}/preview")
def preview(demarche_id: str, langue: str = "fr", db: Session = Depends(get_db), _: AdminUser = Depends(current_admin)) -> dict:
    """Rendu borne du brouillon courant (sans publication)."""
    d = _get(db, demarche_id)
    k = to_knowledge(d)
    return {"titre": (k.get("titres") or {}).get(langue), "documents": documents_for(k, langue), "cout_mad": k.get("cout_mad")}


# ── Analytics ────────────────────────────────────────────────────────────


@router.get("/analytics")
def analytics(days: int = 30, db: Session = Depends(get_db), _: AdminUser = Depends(current_admin)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(HistoriqueInteraction).where(HistoriqueInteraction.cree_le >= since)).all()
    total = len(rows)
    by_day = Counter(r.cree_le.date().isoformat() for r in rows)
    return {
        "periode_jours": days,
        "total": total,
        "hors_perimetre": sum(r.hors_perimetre for r in rows),
        "taux_hors_perimetre": round(sum(r.hors_perimetre for r in rows) / total, 3) if total else 0,
        "temps_moyen_ms": round(sum(r.temps_ms or 0 for r in rows) / total) if total else 0,
        "au_dela_3s": sum((r.temps_ms or 0) > 3000 for r in rows),
        "par_langue": dict(Counter(r.langue_detectee for r in rows)),
        "par_demarche": dict(Counter(r.demarche_id or "hors_perimetre" for r in rows)),
        "par_borne": dict(Counter(r.borne_id for r in rows)),
        "par_jour": dict(sorted(by_day.items())),
        "demarches_actives": db.scalar(select(func.count()).select_from(Demarche).where(Demarche.statut == "production")),
    }


@router.get("/interactions")
def interactions(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), _: AdminUser = Depends(current_admin)) -> dict:
    """Historique anonymisé (le texte est expurgé des données personnelles à l'écriture)."""
    limit = max(1, min(limit, 200))
    stmt = select(HistoriqueInteraction).order_by(HistoriqueInteraction.cree_le.desc()).offset(offset).limit(limit)
    return {
        "total": db.scalar(select(func.count()).select_from(HistoriqueInteraction)),
        "items": [{"id": r.id, "borne_id": r.borne_id, "requete": r.requete_texte, "langue": r.langue_detectee,
                   "demarche": r.demarche_id, "score": r.score_confiance, "hors_perimetre": r.hors_perimetre,
                   "temps_ms": r.temps_ms, "cree_le": r.cree_le.isoformat()} for r in db.scalars(stmt)],
    }
