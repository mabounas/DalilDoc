"""Configuration centralisée (variables d'environnement, cf. .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'wathiqadoc.sqlite'}")
    redis_url: str | None = os.getenv("REDIS_URL") or None
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    supported_languages: list[str] = field(default_factory=lambda: _list("SUPPORTED_LANGUAGES", "fr,ar,darija,en,pt,es"))
    knowledge_dir: Path = Path(os.getenv("KNOWLEDGE_DIR", str(ROOT / "data" / "knowledge")))
    rag_mode: str = os.getenv("RAG_MODE", "auto")
    max_response_time_ms: int = int(os.getenv("MAX_RESPONSE_TIME_MS", "3000"))

    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-secret-change-me-please-32bytes!")
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "8"))
    refresh_expire_days: int = int(os.getenv("REFRESH_EXPIRE_DAYS", "7"))
    admin_bootstrap_email: str | None = os.getenv("ADMIN_BOOTSTRAP_EMAIL") or None
    admin_bootstrap_password: str | None = os.getenv("ADMIN_BOOTSTRAP_PASSWORD") or None

    rate_limit_queries_per_min: int = int(os.getenv("RATE_LIMIT_QUERIES", "30"))
    rate_limit_audio_per_min: int = int(os.getenv("RATE_LIMIT_AUDIO", "5"))
    # Une réponse est lue en ~10 phrases : générations ElevenLabs par minute et par borne.
    rate_limit_tts_per_min: int = int(os.getenv("RATE_LIMIT_TTS", "120"))
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"))


settings = Settings()
