"""Service Speech-to-Text (CDC §08, PROMPT 10).

Whisper (OpenAI) pour la transcription, puis détection fine de la langue
(darija vs arabe MSA) via :mod:`rag.langdetect`. L'audio n'est jamais écrit
sur disque : les octets sont libérés dès la transcription terminée (RGPD).
"""

from __future__ import annotations

import os

from rag.langdetect import detect_language

WHISPER_LANG = {"fr": "fr", "ar": "ar", "darija": "ar", "en": "en", "pt": "pt", "es": "es"}


class STTUnavailable(RuntimeError):
    """Aucun moteur STT configuré (clé OpenAI absente)."""


class STTService:
    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise STTUnavailable("OPENAI_API_KEY manquante : transcription vocale indisponible")
        import openai

        self.client = openai.OpenAI(timeout=15.0, max_retries=1)
        self.model = os.getenv("STT_MODEL", "whisper-1")

    def transcribe(self, audio_bytes: bytes, hint: str | None = None, filename: str = "audio.webm") -> dict:
        """Transcrit un enregistrement et identifie la langue.

        Returns:
            ``{"text": str, "langue": str, "confidence": float}``
        """
        try:
            kwargs = {"model": self.model, "file": (filename, audio_bytes), "response_format": "verbose_json"}
            if hint in WHISPER_LANG:
                kwargs["language"] = WHISPER_LANG[hint]
            transcript = self.client.audio.transcriptions.create(**kwargs)
        finally:
            del audio_bytes  # anonymisation : aucune copie de l'audio conservée
        text = (transcript.text or "").strip()
        det = detect_language(text, hint=hint)
        return {"text": text, "langue": det["langue"], "confidence": det["confidence"]}
