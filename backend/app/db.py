"""Modèles SQLAlchemy (miroir de db/migrations/001_initial.sql).

Types portables : PostgreSQL en production, SQLite en développement/tests.
Les embeddings ne sont pas mappés ici (gérés par rag/embedder.py en SQL brut).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Demarche(Base):
    __tablename__ = "demarches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    categorie: Mapped[str] = mapped_column(String(50), nullable=False)
    titre_fr: Mapped[str] = mapped_column(Text, nullable=False)
    titre_ar: Mapped[str | None] = mapped_column(Text)
    titre_darija: Mapped[str | None] = mapped_column(Text)
    titre_en: Mapped[str | None] = mapped_column(Text)
    titre_pt: Mapped[str | None] = mapped_column(Text)
    titre_es: Mapped[str | None] = mapped_column(Text)
    administration: Mapped[str | None] = mapped_column(String(200))
    delai_jours: Mapped[int | None] = mapped_column(Integer)
    cout_mad: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    statut: Mapped[str] = mapped_column(String(20), default="brouillon")
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_url: Mapped[str | None] = mapped_column(Text)
    valide_par: Mapped[str | None] = mapped_column(String(100))
    contenu: Mapped[dict] = mapped_column(JSON, default=dict)
    cree_le: Mapped[datetime] = mapped_column(default=_now)
    mis_a_jour_le: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    documents: Mapped[list["DocumentRequis"]] = relationship(back_populates="demarche", cascade="all, delete-orphan",
                                                              order_by="DocumentRequis.ordre")
    versions: Mapped[list["DemarcheVersion"]] = relationship(back_populates="demarche", cascade="all, delete-orphan",
                                                              order_by="DemarcheVersion.version")


class DocumentRequis(Base):
    __tablename__ = "documents_requis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    demarche_id: Mapped[str] = mapped_column(ForeignKey("demarches.id", ondelete="CASCADE"))
    ordre: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    nom_fr: Mapped[str] = mapped_column(Text, nullable=False)
    nom_ar: Mapped[str | None] = mapped_column(Text)
    nom_darija: Mapped[str | None] = mapped_column(Text)
    nom_en: Mapped[str | None] = mapped_column(Text)
    nom_pt: Mapped[str | None] = mapped_column(Text)
    nom_es: Mapped[str | None] = mapped_column(Text)
    obligatoire: Mapped[bool] = mapped_column(Boolean, default=True)
    condition: Mapped[str | None] = mapped_column(Text)
    format: Mapped[list | None] = mapped_column(JSON)

    demarche: Mapped[Demarche] = relationship(back_populates="documents")


class DemarcheVersion(Base):
    __tablename__ = "demarches_versions"
    __table_args__ = (UniqueConstraint("demarche_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    demarche_id: Mapped[str] = mapped_column(ForeignKey("demarches.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    publiee: Mapped[bool] = mapped_column(Boolean, default=False)
    auteur: Mapped[str | None] = mapped_column(String(200))
    cree_le: Mapped[datetime] = mapped_column(default=_now)

    demarche: Mapped[Demarche] = relationship(back_populates="versions")


class HistoriqueInteraction(Base):
    __tablename__ = "historique_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    borne_id: Mapped[str | None] = mapped_column(String(50))
    requete_texte: Mapped[str | None] = mapped_column(Text)
    langue_detectee: Mapped[str | None] = mapped_column(String(10))
    demarche_id: Mapped[str | None] = mapped_column(String(100))
    chunks_utilises: Mapped[list | None] = mapped_column(JSON)
    score_confiance: Mapped[float | None] = mapped_column(Float)
    hors_perimetre: Mapped[bool] = mapped_column(Boolean, default=False)
    temps_ms: Mapped[int | None] = mapped_column(Integer)
    cree_le: Mapped[datetime] = mapped_column(default=_now)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="editor")
    totp_secret: Mapped[str | None] = mapped_column(Text)
    cree_le: Mapped[datetime] = mapped_column(default=_now)


class AdminAccessLog(Base):
    __tablename__ = "admin_access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    cible: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    cree_le: Mapped[datetime] = mapped_column(default=_now)


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1),
                       connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Dépendance FastAPI : session SQLAlchemy par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crée les tables manquantes (dev/SQLite ; en prod, appliquer db/migrations)."""
    if settings.database_url.startswith("sqlite"):
        from pathlib import Path

        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
