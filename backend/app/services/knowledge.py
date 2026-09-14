"""Synchronisation base de données ↔ base de connaissances ↔ moteur RAG.

* La vérité éditoriale vit en base (table ``demarches``, champ ``contenu``).
* La borne ne sert que la **dernière version publiée** de chaque démarche
  active (table ``demarches_versions``, ``publiee = true``) : un brouillon en
  cours d'édition ne modifie jamais ce que voit le citoyen.
* Au premier démarrage, la base est amorcée depuis ``data/knowledge/*.json``
  (contenu issu du scraping de cnie.ma).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rag import WathiqaRAG
from rag.chunker import LANGS, chunk_demarche

from ..config import settings
from ..db import Demarche, DemarcheVersion, DocumentRequis, SessionLocal

log = logging.getLogger(__name__)

CONTENT_KEYS = ("titres", "mots_cles", "synonymes", "conditions", "documents", "exceptions", "tarifs", "faq", "code_portail")


def to_knowledge(d: Demarche, contenu: dict | None = None) -> dict:
    """Assemble le dictionnaire de connaissances d'une démarche (format data/knowledge)."""
    c = dict(contenu if contenu is not None else d.contenu or {})
    c.update({
        "slug": d.slug, "categorie": d.categorie, "administration": d.administration,
        "delai_jours": d.delai_jours, "cout_mad": float(d.cout_mad or 0), "source_url": d.source_url,
        "valide_par": d.valide_par, "version": d.version, "actif": d.actif, "statut": "production",
    })
    c.setdefault("titres", {"fr": d.titre_fr})
    return c


def apply_content(db: Session, d: Demarche, data: dict) -> None:
    """Écrit un contenu (dict multilingue) dans les colonnes, ``contenu`` et ``documents_requis``."""
    titres = data.get("titres") or {}
    d.slug = data.get("slug", d.slug)
    d.categorie = data.get("categorie", d.categorie)
    d.titre_fr = titres.get("fr") or d.titre_fr or d.slug
    for lg in ("ar", "darija", "en", "pt", "es"):
        setattr(d, f"titre_{lg}", titres.get(lg))
    for col in ("administration", "delai_jours", "cout_mad", "source_url"):
        if col in data:
            setattr(d, col, data[col])
    d.contenu = {k: data[k] for k in CONTENT_KEYS if k in data}
    d.documents.clear()
    db.flush()
    for doc in data.get("documents", []):
        nom = doc.get("nom") or {}
        cond = doc.get("condition") or {}
        d.documents.append(DocumentRequis(
            ordre=doc.get("ordre", 0), nom_fr=nom.get("fr") or "", obligatoire=doc.get("obligatoire", True),
            condition=cond.get("fr") if isinstance(cond, dict) else cond, format=doc.get("format") or [],
            **{f"nom_{lg}": nom.get(lg) for lg in ("ar", "darija", "en", "pt", "es")},
        ))


def snapshot(db: Session, d: Demarche, auteur: str | None, publiee: bool) -> DemarcheVersion:
    """Enregistre un instantané versionné du contenu courant."""
    v = DemarcheVersion(demarche_id=d.id, version=d.version, snapshot=to_knowledge(d), publiee=publiee, auteur=auteur)
    existing = db.scalar(select(DemarcheVersion).where(DemarcheVersion.demarche_id == d.id, DemarcheVersion.version == d.version))
    if existing is not None:
        existing.snapshot, existing.publiee, existing.auteur = v.snapshot, existing.publiee or publiee, auteur
        return existing
    db.add(v)
    return v


def seed_from_files(db: Session, knowledge_dir: Path | None = None) -> int:
    """Amorce la base depuis data/knowledge/*.json si elle est vide."""
    if db.scalar(select(func.count()).select_from(Demarche)):
        return 0
    count = 0
    for path in sorted((knowledge_dir or settings.knowledge_dir).glob("*.json")):
        kb = json.loads(path.read_text(encoding="utf-8"))
        for data in kb.get("demarches", []):
            d = Demarche(slug=data["slug"], categorie=data.get("categorie", "identite"), titre_fr=data["titres"]["fr"],
                         statut=data.get("statut", "production"), version=data.get("version", 1),
                         actif=data.get("actif", True), valide_par=data.get("valide_par") or "import cnie.ma")
            db.add(d)
            apply_content(db, d, data)
            db.flush()
            snapshot(db, d, "import cnie.ma", publiee=d.statut == "production")
            count += 1
    db.commit()
    log.info("Base amorcée : %d démarches", count)
    return count


def published_knowledge(db: Session) -> list[dict]:
    """Dernière version publiée de chaque démarche active."""
    out = []
    for d in db.scalars(select(Demarche).where(Demarche.actif.is_(True), Demarche.statut != "inactif")):
        v = db.scalar(select(DemarcheVersion).where(DemarcheVersion.demarche_id == d.id, DemarcheVersion.publiee.is_(True))
                      .order_by(DemarcheVersion.version.desc()).limit(1))
        if v is not None:
            out.append({**v.snapshot, "id": d.id})
    return out


class RAGHolder:
    """Instance RAG partagée, reconstruite à chaud après publication."""

    def __init__(self):
        self._rag: WathiqaRAG | None = None
        self._lock = threading.Lock()

    def get(self) -> WathiqaRAG:
        if self._rag is None:
            self.rebuild()
        return self._rag  # type: ignore[return-value]

    def rebuild(self, db: Session | None = None) -> WathiqaRAG:
        own = db is None
        db = db or SessionLocal()
        try:
            knowledge = published_knowledge(db)
        finally:
            if own:
                db.close()
        with self._lock:
            self._rag = WathiqaRAG(knowledge=knowledge, mode=settings.rag_mode) if knowledge else \
                WathiqaRAG(knowledge_dir=settings.knowledge_dir, mode=settings.rag_mode)
        log.info("RAG reconstruit : %d démarches, %d chunks, mode=%s", len(self._rag.demarches), len(self._rag.chunks), self._rag.mode)
        return self._rag


rag_holder = RAGHolder()


def reindex_vectors(knowledge: dict) -> str | None:
    """Réindexe les chunks d'une démarche publiée dans Qdrant/pgvector (mode API uniquement)."""
    if rag_holder.get().mode == "local":
        return None
    try:
        from rag.embedder import index_chunks

        return index_chunks(chunk_demarche(knowledge))
    except Exception as exc:  # noqa: BLE001 — la publication ne doit pas échouer pour l'index
        log.error("Réindexation vectorielle échouée pour %s : %s", knowledge.get("slug"), exc)
        return None


def localized_titles(d: Demarche | dict) -> dict[str, str | None]:
    if isinstance(d, dict):
        return {lg: (d.get("titres") or {}).get(lg) for lg in LANGS}
    return {lg: getattr(d, f"titre_{lg}") for lg in LANGS}
