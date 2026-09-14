import sys
from types import SimpleNamespace

import pytest

from app.services import stt, tts


class _FakeTranscriptions:
    def __init__(self, text):
        self.text = text
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(text=self.text)


def _service(monkeypatch, text):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Pas d'appel réseau ni de dépendance au SDK installé : client OpenAI factice.
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **_: None))
    service = stt.STTService()
    fake = _FakeTranscriptions(text)
    service.client = SimpleNamespace(audio=SimpleNamespace(transcriptions=fake))
    return service, fake


def test_stt_darija_langue_et_amorce(monkeypatch):
    """Darija : Whisper reçoit la langue arabe et l'amorce de vocabulaire marocain."""
    service, fake = _service(monkeypatch, "واش خاصني نجدد لاكارط")
    res = service.transcribe(b"audio", hint="darija")
    assert fake.kwargs["language"] == "ar"
    assert "لاكارط" in fake.kwargs["prompt"]
    assert res == {"text": "واش خاصني نجدد لاكارط", "langue": "darija", "confidence": res["confidence"]}


def test_stt_question_courte_presente_dans_amorce_conservee(monkeypatch):
    """Une vraie question courte contenue dans l'amorce n'est pas prise pour un écho."""
    service, _ = _service(monkeypatch, "ضاعت ليا لاكارط")
    assert service.transcribe(b"audio", hint="darija")["text"] == "ضاعت ليا لاكارط"


def test_stt_echo_amorce_rejete(monkeypatch):
    """Silence : Whisper recopie parfois l'amorce — elle ne doit pas devenir une question."""
    service, _ = _service(monkeypatch, stt.PROMPTS["darija"])
    assert service.transcribe(b"audio", hint="darija")["text"] == ""


def test_tts_voix_par_langue(monkeypatch):
    for key in ("ELEVENLABS_VOICE_DARIJA", "ELEVENLABS_VOICE_AR", "ELEVENLABS_VOICE_DEFAULT"):
        monkeypatch.delenv(key, raising=False)
    assert tts.voice_for("darija") == tts.VOICE_IDS["darija"]
    monkeypatch.setenv("ELEVENLABS_VOICE_AR", "voix-arabe")
    assert tts.voice_for("darija") == "voix-arabe"  # la darija hérite de la voix arabe
    monkeypatch.setenv("ELEVENLABS_VOICE_DARIJA", "voix-marocaine")
    assert tts.voice_for("darija") == "voix-marocaine"
    assert tts.voice_for("ar") == "voix-arabe"


def test_stt_sans_cle(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(stt.STTUnavailable):
        stt.STTService()


class _FakeResponse:
    content = b"ID3-fake-mp3"

    def raise_for_status(self):
        return None


def test_tts_cache_une_seule_generation(monkeypatch, tmp_path):
    """Même réponse, même langue : ElevenLabs n'est appelé qu'une fois, ensuite le cache sert."""
    calls = []
    monkeypatch.setattr(tts.httpx, "post", lambda url, **kw: calls.append((url, kw["json"]["text"])) or _FakeResponse())
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path))
    for key in ("ELEVENLABS_VOICE_DARIJA", "ELEVENLABS_VOICE_AR", "ELEVENLABS_VOICE_DEFAULT"):
        monkeypatch.delenv(key, raising=False)

    first = tts.synthesize_cached("لاكارط الوطنية — ضاعت", "darija")
    second = tts.synthesize_cached("لاكارط  الوطنية — ضاعت", "darija")  # espaces différents : même audio
    assert first == (b"ID3-fake-mp3", False)
    assert second == (b"ID3-fake-mp3", True)
    assert len(calls) == 1

    tts.synthesize_cached("لاكارط الوطنية — ضاعت", "ar")  # autre langue → autre audio
    monkeypatch.setenv("ELEVENLABS_VOICE_DARIJA", "voix-marocaine")
    tts.synthesize_cached("لاكارط الوطنية — ضاعت", "darija")  # nouvelle voix → régénéré
    assert len(calls) == 3

    # Le cache sert même si la clé est retirée ensuite (borne toujours parlante).
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert tts.synthesize_cached("لاكارط الوطنية — ضاعت", "ar")[1] is True


def test_tts_cache_plafond(monkeypatch, tmp_path):
    monkeypatch.setattr(tts.httpx, "post", lambda url, **kw: _FakeResponse())
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("TTS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TTS_CACHE_MAX_FILES", "3")
    for i in range(6):
        tts.synthesize_cached(f"réponse {i}", "fr")
    assert len(list(tmp_path.glob("*.mp3"))) == 3


def test_tts_sans_cache_ni_cle(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("TTS_CACHE_DIR", raising=False)
    with pytest.raises(tts.TTSUnavailable):
        tts.synthesize_cached("Bonjour", "fr")
