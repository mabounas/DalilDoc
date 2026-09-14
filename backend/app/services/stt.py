"""Service Speech-to-Text (CDC §08, PROMPT 10).

Whisper (OpenAI) pour la transcription, puis détection fine de la langue
(darija vs arabe MSA) via :mod:`rag.langdetect`. L'audio n'est jamais écrit
sur disque : les octets sont libérés dès la transcription terminée (RGPD).
"""

from __future__ import annotations

import os

from rag.langdetect import detect_language

WHISPER_LANG = {"fr": "fr", "ar": "ar", "darija": "ar", "en": "en", "pt": "pt", "es": "es"}

# Amorce de vocabulaire : Whisper transcrit mieux la darija (et son orthographe usuelle)
# quand on lui montre le registre attendu. Aucun contenu de l'usager n'y figure.
PROMPTS = {
    "darija": "سؤال بالدارجة المغربية على لاكارط الوطنية: شنو خاصني باش ندير لاكارط؟ ضاعت ليا لاكارط، بغيت نجدد، الوراق، ولدي، الموعد.",
    "ar": "سؤال عن البطاقة الوطنية للتعريف الإلكترونية: الوثائق المطلوبة، التجديد، الضياع، شهادة السكنى، القاصر.",
    "fr": "Question sur la carte nationale d'identité électronique (CNIE) : documents, renouvellement, perte, timbre.",
}


class STTUnavailable(RuntimeError):
    """Aucun moteur STT configuré (clé OpenAI absente)."""


class STTService:
    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise STTUnavailable("OPENAI_API_KEY manquante : transcription vocale indisponible")
        import openai

        self.client = openai.OpenAI(timeout=15.0, max_retries=1)
        self.model = os.getenv("STT_MODEL", "whisper-1")

    def build_request(self, audio_bytes: bytes, hint: str | None, filename: str = "audio.webm") -> dict:
        """Paramètres de l'appel de transcription (langue forcée + amorce de vocabulaire)."""
        kwargs = {"model": self.model, "file": (filename, audio_bytes),
                  "response_format": "verbose_json" if self.model == "whisper-1" else "json"}
        if hint in WHISPER_LANG:
            kwargs["language"] = WHISPER_LANG[hint]
        if hint in PROMPTS:
            kwargs["prompt"] = PROMPTS[hint]
        return kwargs

    def transcribe(self, audio_bytes: bytes, hint: str | None = None, filename: str = "audio.webm") -> dict:
        """Transcrit un enregistrement et identifie la langue.

        Returns:
            ``{"text": str, "langue": str, "confidence": float}``
        """
        try:
            transcript = self.client.audio.transcriptions.create(**self.build_request(audio_bytes, hint, filename))
        finally:
            del audio_bytes  # anonymisation : aucune copie de l'audio conservée
        text = (transcript.text or "").strip()
        # L'amorce ne doit jamais revenir comme « transcription » d'un silence. Une vraie
        # question courte peut figurer dans l'amorce (« ضاعت ليا لاكارط ») : on ne rejette
        # que la recopie de l'amorce entière ou d'un long fragment.
        if text and any(text == p or (len(text) > 40 and text in p) for p in PROMPTS.values()):
            text = ""
        det = detect_language(text, hint=hint)
        return {"text": text, "langue": det["langue"], "confidence": det["confidence"]}
