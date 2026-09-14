"""Service Text-to-Speech ElevenLabs (CDC §08, PROMPT 11).

Appel REST direct (``/v1/text-to-speech/{voice_id}``) avec ``httpx`` :
modèle ``eleven_multilingual_v2`` par défaut, débit légèrement ralenti.

Chaque langue peut utiliser sa propre voix via ``ELEVENLABS_VOICE_<LANGUE>``
(ex. ``ELEVENLABS_VOICE_DARIJA`` = une voix marocaine de la Voice Library),
sinon ``ELEVENLABS_VOICE_DEFAULT``, sinon les voix préconfigurées ci-dessous.
"""

from __future__ import annotations

import os

import httpx

VOICE_IDS = {
    "fr": "EXAVITQu4vr4xnSDxMaL",      # Sarah (FR)
    "ar": "pNInz6obpgDQGcFmaJgB",      # Adam (AR)
    "darija": "pNInz6obpgDQGcFmaJgB",  # même voix arabe
    "en": "21m00Tcm4TlvDq8ikWAM",      # Rachel (EN)
    "pt": "AZnzlk1XvdvUeBnXmlld",      # Elli (PT)
    "es": "pMsXgVXv3BLzUgSXRplE",      # Lucia (ES)
}

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class TTSUnavailable(RuntimeError):
    """Clé ElevenLabs absente ou service injoignable."""


def voice_for(langue: str) -> str:
    """Voix ElevenLabs d'une langue (surcharge par variable d'environnement)."""
    return (os.getenv(f"ELEVENLABS_VOICE_{langue.upper()}")
            or (os.getenv("ELEVENLABS_VOICE_AR") if langue == "darija" else None)
            or os.getenv("ELEVENLABS_VOICE_DEFAULT")
            or VOICE_IDS.get(langue, VOICE_IDS["fr"]))


def synthesize(text: str, langue: str) -> bytes:
    """Synthétise ``text`` et retourne l'audio MP3."""
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise TTSUnavailable("ELEVENLABS_API_KEY manquante : synthèse vocale indisponible")
    payload = {
        "text": text,
        "model_id": os.getenv("TTS_MODEL", "eleven_multilingual_v2"),
        "voice_settings": {"stability": 0.8, "similarity_boost": 0.75, "speed": 0.9},
    }
    try:
        resp = httpx.post(API_URL.format(voice_id=voice_for(langue)), json=payload, timeout=15.0,
                          headers={"xi-api-key": api_key, "Accept": "audio/mpeg"})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise TTSUnavailable(f"ElevenLabs indisponible : {exc}") from exc
    return resp.content
