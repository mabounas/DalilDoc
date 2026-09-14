"""Routes publiques de la borne citoyenne (CDC §06, PROMPT 6)."""

from __future__ import annotations

import base64
import binascii
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from rag.chunker import LANGS
from rag.generator import documents_for

from ..config import settings
from ..db import HistoriqueInteraction, get_db
from ..middleware.security import anonymize_text, anonymous_session_id, enforce_rate_limit, rate_limiter
from ..schemas import (DemarcheSummary, HealthResponse, QueryRequest, QueryResponse, SynthesizeRequest, SynthesizeResponse,
                       TranscribeRequest, TranscribeResponse)
from ..services import tts
from ..services.knowledge import localized_titles, rag_holder
from ..services.stt import STTService, STTUnavailable

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["borne"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # ~30 s d'audio compressé largement couverts


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    """Détecte la langue, interroge le RAG et journalise l'interaction anonymisée."""
    enforce_rate_limit("query", req.borne_id)
    result = rag_holder.get().query(req.text, langue_hint=req.langue)
    try:
        db.add(HistoriqueInteraction(
            session_id=anonymous_session_id(req.session_id), borne_id=req.borne_id,
            requete_texte=anonymize_text(req.text), langue_detectee=result.langue, demarche_id=result.demarche_id,
            chunks_utilises=result.chunks_utilises, score_confiance=result.score_confiance,
            hors_perimetre=result.hors_perimetre, temps_ms=result.temps_ms,
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — la journalisation ne bloque jamais la réponse
        db.rollback()
        log.error("Journalisation impossible : %s", exc)
    return QueryResponse(**{k: v for k, v in result.to_dict().items() if k in QueryResponse.model_fields})


@router.get("/voice/capabilities")
def voice_capabilities() -> dict:
    """Moteurs vocaux côté serveur disponibles (la borne choisit sinon ceux du navigateur)."""
    return {"stt": bool(os.getenv("OPENAI_API_KEY")), "tts": bool(os.getenv("ELEVENLABS_API_KEY"))}


@router.post("/voice/transcribe", response_model=TranscribeResponse)
def transcribe(req: TranscribeRequest) -> TranscribeResponse:
    """Whisper STT : audio base64 → texte + langue. L'audio n'est jamais stocké."""
    enforce_rate_limit("audio", req.borne_id)
    try:
        audio = base64.b64decode(req.audio.split(",", 1)[-1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audio base64 invalide") from exc
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio vide ou trop volumineux")
    try:
        result = STTService().transcribe(audio, hint=req.langue)
    except STTUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.error("Transcription échouée : %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Transcription indisponible, utilisez le clavier.") from exc
    finally:
        del audio
    return TranscribeResponse(**result)


@router.post("/voice/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest) -> SynthesizeResponse:
    """ElevenLabs TTS : texte → audio MP3 base64."""
    enforce_rate_limit("tts", req.borne_id)
    try:
        audio = tts.synthesize(req.text, req.langue)
    except tts.TTSUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return SynthesizeResponse(audio=base64.b64encode(audio).decode())


@router.get("/demarches", response_model=list[DemarcheSummary])
def list_demarches() -> list[DemarcheSummary]:
    """Démarches actives publiées."""
    return [
        DemarcheSummary(id=d.get("id", slug), slug=slug, categorie=d.get("categorie", ""), titres=localized_titles(d),
                        administration=d.get("administration"), cout_mad=float(d.get("cout_mad") or 0),
                        delai_jours=d.get("delai_jours"), source_url=d.get("source_url"), statut="production",
                        version=d.get("version", 1))
        for slug, d in rag_holder.get().demarches.items()
    ]


@router.get("/demarches/{slug}")
def get_demarche(slug: str, langue: str = "fr") -> dict:
    """Fiche d'une démarche localisée (documents, conditions, tarifs)."""
    d = rag_holder.get().demarches.get(slug)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Démarche inconnue")
    if langue not in LANGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Langue non supportée")

    def pick(v):
        return (v or {}).get(langue) or (v or {}).get("ar" if langue == "darija" else "fr")

    return {
        "slug": slug, "langue": langue, "titre": pick(d.get("titres")), "administration": d.get("administration"),
        "cout_mad": d.get("cout_mad"), "delai_jours": d.get("delai_jours"), "source_url": d.get("source_url"),
        "documents": documents_for(d, langue),
        **{k: [pick(x) for x in d.get(k, [])] for k in ("conditions", "exceptions", "tarifs")},
    }


@router.get("/offline-cache")
def offline_cache() -> dict:
    """Paquet de cache pour le mode hors ligne de la borne (démarches + chunks fr/ar)."""
    rag = rag_holder.get()
    return {
        "demarches": [get_demarche(slug, lg) for slug in rag.demarches for lg in ("fr", "ar")],
        "chunks": [c.to_dict() for c in rag.chunks if c.langue in ("fr", "ar")],
    }


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """État des services (DB, moteur RAG, Qdrant, Redis)."""
    services: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        services["database"] = "ok"
    except Exception:  # noqa: BLE001
        services["database"] = "down"
    rag = rag_holder.get()
    services["rag"] = f"ok ({len(rag.chunks)} chunks)"
    if rag.mode == "qdrant":
        try:
            rag.retriever.client.get_collections()  # type: ignore[attr-defined]
            services["qdrant"] = "ok"
        except Exception:  # noqa: BLE001
            services["qdrant"] = "down"
    services["redis"] = "ok" if rate_limiter._redis is not None else ("down" if settings.redis_url else "non configuré")
    degraded = any(v == "down" for v in services.values())
    return HealthResponse(status="degraded" if degraded else "ok", services=services, rag_mode=rag.mode)
