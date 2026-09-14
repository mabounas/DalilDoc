"""Service Text-to-Speech ElevenLabs (CDC §08, PROMPT 11).

Appel REST direct (``/v1/text-to-speech/{voice_id}``) avec ``httpx`` :
modèle ``eleven_multilingual_v2`` par défaut, débit légèrement ralenti.

Chaque langue peut utiliser sa propre voix via ``ELEVENLABS_VOICE_<LANGUE>``
(ex. ``ELEVENLABS_VOICE_DARIJA`` = une voix marocaine de la Voice Library),
sinon ``ELEVENLABS_VOICE_DEFAULT``, sinon les voix préconfigurées ci-dessous.

Cache audio : les réponses de la borne sont déterministes (même démarche, même
langue → même texte). Chaque audio est donc généré une seule fois puis servi
depuis ``TTS_CACHE_DIR``. La clé de cache inclut texte, langue, voix et modèle :
modifier une démarche ou changer de voix produit automatiquement un nouvel audio.
Aucune donnée personnelle n'y figure (seules les réponses de la base sont lues).
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

VOICE_IDS = {
    "fr": "EXAVITQu4vr4xnSDxMaL",      # Sarah (FR)
    "ar": "pNInz6obpgDQGcFmaJgB",      # Adam (AR)
    "darija": "pNInz6obpgDQGcFmaJgB",  # même voix arabe
    "en": "21m00Tcm4TlvDq8ikWAM",      # Rachel (EN)
    "pt": "AZnzlk1XvdvUeBnXmlld",      # Elli (PT)
    "es": "pMsXgVXv3BLzUgSXRplE",      # Lucia (ES)
}

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
VOICE_SETTINGS = {"stability": 0.8, "similarity_boost": 0.75, "speed": 0.9}


class TTSUnavailable(RuntimeError):
    """Clé ElevenLabs absente ou service injoignable."""


def voice_for(langue: str) -> str:
    """Voix ElevenLabs d'une langue (surcharge par variable d'environnement)."""
    return (os.getenv(f"ELEVENLABS_VOICE_{langue.upper()}")
            or (os.getenv("ELEVENLABS_VOICE_AR") if langue == "darija" else None)
            or os.getenv("ELEVENLABS_VOICE_DEFAULT")
            or VOICE_IDS.get(langue, VOICE_IDS["fr"]))


def _model() -> str:
    return os.getenv("TTS_MODEL", "eleven_multilingual_v2")


# ── Cache disque ────────────────────────────────────────────────────────────

def _cache_dir() -> Path | None:
    raw = os.getenv("TTS_CACHE_DIR", "")
    if not raw:
        return None
    path = Path(raw)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Cache TTS désactivé (%s) : %s", path, exc)
        return None
    return path


def cache_key(text: str, langue: str, voice_id: str, model: str) -> str:
    """Empreinte stable d'un audio (texte normalisé + langue + voix + modèle + réglages)."""
    normalized = " ".join(text.split())
    raw = "|".join([normalized, langue, voice_id, model, repr(sorted(VOICE_SETTINGS.items()))])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _prune(directory: Path) -> None:
    """Garde au plus TTS_CACHE_MAX_FILES fichiers : supprime les moins récemment utilisés."""
    max_files = int(os.getenv("TTS_CACHE_MAX_FILES", "500"))
    files = sorted(directory.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    for old in files[: max(0, len(files) - max_files)]:
        old.unlink(missing_ok=True)


def _cache_read(directory: Path | None, key: str) -> bytes | None:
    if directory is None:
        return None
    path = directory / f"{key}.mp3"
    try:
        data = path.read_bytes()
        os.utime(path)  # marque l'utilisation (éviction des moins utilisés)
        return data
    except OSError:
        return None


def _cache_write(directory: Path | None, key: str, audio: bytes) -> None:
    if directory is None or not audio:
        return
    tmp = directory / f"{key}.tmp"
    try:
        tmp.write_bytes(audio)
        tmp.replace(directory / f"{key}.mp3")  # écriture atomique
        _prune(directory)
    except OSError as exc:
        log.warning("Écriture du cache TTS impossible : %s", exc)
        tmp.unlink(missing_ok=True)


# ── Synthèse ────────────────────────────────────────────────────────────────

def _call_elevenlabs(text: str, voice_id: str, model: str, api_key: str) -> bytes:
    payload = {"text": text, "model_id": model, "voice_settings": VOICE_SETTINGS}
    try:
        # Une réponse arabe complète (≈ 1 000 caractères) peut dépasser 15 s de génération.
        resp = httpx.post(API_URL.format(voice_id=voice_id), json=payload, timeout=45.0,
                          headers={"xi-api-key": api_key, "Accept": "audio/mpeg"})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise TTSUnavailable(f"ElevenLabs indisponible : {exc}") from exc
    return resp.content


def synthesize_cached(text: str, langue: str) -> tuple[bytes, bool]:
    """Synthétise ``text`` (MP3) ; retourne ``(audio, servi_depuis_le_cache)``."""
    voice_id, model = voice_for(langue), _model()
    directory = _cache_dir()
    key = cache_key(text, langue, voice_id, model)
    cached = _cache_read(directory, key)
    if cached is not None:
        return cached, True
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise TTSUnavailable("ELEVENLABS_API_KEY manquante : synthèse vocale indisponible")
    audio = _call_elevenlabs(text, voice_id, model, api_key)
    _cache_write(directory, key, audio)
    return audio, False


def synthesize(text: str, langue: str) -> bytes:
    """Synthétise ``text`` et retourne l'audio MP3 (avec cache)."""
    return synthesize_cached(text, langue)[0]


# ── Lecture découpée phrase par phrase ──────────────────────────────────────
# La borne lit une réponse en plusieurs courts audios (titre, en-tête, chaque document) :
# la première phrase part en ~1 s au lieu d'attendre toute la réponse, et les documents
# communs à plusieurs démarches (certificat de résidence, photos…) sont mis en cache une fois.

SPOKEN_HEADERS = {  # identiques à T[lang].requiredDocs de la borne (frontend/lib/i18n.ts)
    "fr": "Documents à fournir", "ar": "الوثائق المطلوبة", "darija": "الوراق اللي خاصك",
    "en": "Required documents", "pt": "Documentos exigidos", "es": "Documentos requeridos",
}


def _localized(value, langue: str) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value
    for lg in (langue, *(("ar", "fr") if langue == "darija" else ("fr",))):
        if value.get(lg):
            return value[lg]
    return None


def spoken_segments(demarche: dict, langue: str) -> list[str]:
    """Phrases lues pour une démarche : titre, en-tête « documents », puis chaque document numéroté."""
    from rag.generator import documents_for

    segments: list[str] = []
    titre = _localized(demarche.get("titres"), langue)
    if titre:
        segments.append(titre)
    docs = [d for d in documents_for(demarche, langue) if d.get("nom")]
    if docs:
        segments.append(SPOKEN_HEADERS.get(langue, SPOKEN_HEADERS["fr"]))
        segments += [f"{d.get('ordre') or i}. {d['nom']}" for i, d in enumerate(docs, 1)]
    return segments


def is_cached(text: str, langue: str) -> bool:
    """Vrai si l'audio de ce texte est déjà en cache (lecture gratuite et instantanée)."""
    directory = _cache_dir()
    if directory is None:
        return False
    return (directory / f"{cache_key(text, langue, voice_for(langue), _model())}.mp3").exists()
