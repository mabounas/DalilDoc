"""Schémas Pydantic de l'API (CDC §06, PROMPT 7)."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

Langue = Literal["fr", "ar", "darija", "en", "pt", "es"]
Statut = Literal["brouillon", "review", "valide", "production", "inactif"]


class QueryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    borne_id: str = Field(default="default", max_length=50)
    langue: Optional[Langue] = Field(default=None, description="Langue choisie sur la borne (indice)")


class DocumentOut(BaseModel):
    ordre: Optional[int] = None
    nom: Optional[str] = None
    obligatoire: bool = True
    condition: Optional[str] = None
    format: list[str] = []


class QueryResponse(BaseModel):
    reponse: str
    langue: str
    demarche_id: Optional[str]
    documents: list[DocumentOut]
    score_confiance: float
    hors_perimetre: bool
    sources: list[str]
    temps_ms: int


class TranscribeRequest(BaseModel):
    audio: str = Field(..., description="Audio encodé en base64 (webm/ogg/wav)")
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    borne_id: str = "default"
    langue: Optional[Langue] = None


class TranscribeResponse(BaseModel):
    text: str
    langue: str
    confidence: float


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    langue: Langue = "fr"
    borne_id: str = "default"


class SynthesizeResponse(BaseModel):
    audio: str
    mime_type: str = "audio/mpeg"


class DemarcheSummary(BaseModel):
    id: str
    slug: str
    categorie: str
    titres: dict[str, Optional[str]]
    administration: Optional[str]
    cout_mad: float
    delai_jours: Optional[int]
    source_url: Optional[str]
    statut: str
    version: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    services: dict[str, str]
    rag_mode: str


# ── Admin ────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str
    totp: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class Multilingue(BaseModel):
    fr: Optional[str] = None
    ar: Optional[str] = None
    darija: Optional[str] = None
    en: Optional[str] = None
    pt: Optional[str] = None
    es: Optional[str] = None


class DocumentRequisCreate(BaseModel):
    ordre: int
    nom: Multilingue
    obligatoire: bool = True
    condition: Optional[Multilingue] = None
    format: list[str] = []


class FAQItem(BaseModel):
    question: Multilingue
    reponse: Multilingue


class DemarcheCreate(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9-]{3,100}$")
    categorie: str
    titres: Multilingue
    mots_cles: dict[str, list[str]] = {}
    synonymes: dict[str, list[str]] = {}
    conditions: list[Multilingue] = []
    documents: list[DocumentRequisCreate] = []
    exceptions: list[Multilingue] = []
    tarifs: list[Multilingue] = []
    faq: list[FAQItem] = []
    administration: str
    delai_jours: Optional[int] = None
    cout_mad: float = 0
    source_url: Optional[str] = None


class DemarcheDetail(DemarcheSummary):
    contenu: dict
    valide_par: Optional[str]


class VersionOut(BaseModel):
    version: int
    auteur: Optional[str]
    cree_le: str
