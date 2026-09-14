"""Pipeline RAG complet — classe :class:`WathiqaRAG` (CDC §05, PROMPT 4).

requête → détection langue → retrieval (top-5, filtre langue) → seuil de
confiance → génération contrôlée → réponse + documents + sources.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .chunker import Chunk, chunk_knowledge, load_knowledge
from .generator import ClaudeGenerator, ExtractiveGenerator, documents_for
from .langdetect import detect_language
from .retriever import LocalRetriever, PgVectorRetriever, QdrantRetriever, ScoredChunk, normalize

log = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE = Path(__file__).resolve().parents[1] / "data" / "knowledge"

# Seuils : cosine d'embeddings (CDC : 0.75) vs TF-IDF local (échelle différente).
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.75"))
LOCAL_MIN_CONFIDENCE = float(os.getenv("LOCAL_MIN_CONFIDENCE", "0.12"))
KEYWORD_BONUS = 0.2


@dataclass
class RAGResult:
    reponse: str
    langue: str
    demarche_id: str | None
    documents: list[dict]
    score_confiance: float
    hors_perimetre: bool
    sources: list[str]
    temps_ms: int
    chunks_utilises: list[str] = field(default_factory=list)
    mode: str = "local"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class WathiqaRAG:
    """Orchestrateur RAG multilingue « zéro hallucination »."""

    def __init__(self, knowledge_dir: str | Path | None = None, mode: str | None = None, knowledge: list[dict] | None = None):
        self.mode_requested = (mode or os.getenv("RAG_MODE", "auto")).lower()
        self.demarches: dict[str, dict] = {}
        if knowledge is not None:
            for d in knowledge:
                self.demarches[d["slug"]] = d
        else:
            for path in sorted(Path(knowledge_dir or DEFAULT_KNOWLEDGE).glob("*.json")):
                for d in load_knowledge(path).get("demarches", []):
                    if d.get("actif", True) and d.get("statut", "production") == "production":
                        self.demarches[d["slug"]] = d
        self.chunks: list[Chunk] = chunk_knowledge({"demarches": list(self.demarches.values())})
        self._keywords = self._specific_keywords()
        self._setup_backends()

    def _setup_backends(self) -> None:
        use_api = self.mode_requested == "api" or (
            self.mode_requested == "auto" and os.getenv("OPENAI_API_KEY") and os.getenv("ANTHROPIC_API_KEY")
        )
        self.local = LocalRetriever(self.chunks)
        self.retriever, self.threshold, self.mode = self.local, LOCAL_MIN_CONFIDENCE, "local"
        self.generator = ExtractiveGenerator()
        if not use_api:
            return
        try:
            from .embedder import OpenAIEmbedder

            embedder = OpenAIEmbedder()
            try:
                self.retriever = QdrantRetriever(os.getenv("QDRANT_URL", "http://localhost:6333"), embedder)
                self.mode = "qdrant"
            except Exception as exc:  # noqa: BLE001
                log.warning("Qdrant indisponible (%s) — repli pgvector", exc)
                self.retriever = PgVectorRetriever(os.environ["DATABASE_URL"], embedder)
                self.mode = "pgvector"
            self.threshold = MIN_CONFIDENCE
            self.generator = ClaudeGenerator()
        except Exception as exc:  # noqa: BLE001 — la borne doit toujours répondre
            log.error("Back-ends API indisponibles (%s) — moteur local", exc)
            self.retriever, self.threshold, self.mode = self.local, LOCAL_MIN_CONFIDENCE, "local"
            self.generator = ExtractiveGenerator()

    def _specific_keywords(self) -> dict[str, set[str]]:
        """Mots-clés propres à une seule démarche (les termes partagés ne discriminent pas).

        Les ``synonymes`` (CIN, carte d'identité…) sont volontairement exclus : ils
        désignent le domaine entier et ne doivent pas orienter vers une démarche.
        """
        owners: dict[str, set[str]] = {}
        for slug, d in self.demarches.items():
            for words in (d.get("mots_cles") or {}).values():
                for w in words:
                    owners.setdefault(normalize(w), set()).add(slug)
        out: dict[str, set[str]] = {}
        for kw, slugs in owners.items():
            if len(slugs) == 1 and len(kw) > 2:
                out.setdefault(next(iter(slugs)), set()).add(kw)
        return out

    def _rerank(self, text: str, hits: list[ScoredChunk]) -> list[ScoredChunk]:
        """Bonus lexical quand la question cite un mot-clé spécifique d'une démarche."""
        words = re.findall(r"\w+", normalize(text))
        joined = f" {' '.join(words)} "

        def hit(kw: str) -> bool:
            kw_words = re.findall(r"\w+", kw)
            if len(kw_words) > 1:
                return f" {' '.join(kw_words)} " in joined
            # Préfixe pour les mots longs : « alitée » ↔ « alité », « renewal » ↔ « renew ».
            return any(w == kw_words[0] or (len(kw_words[0]) >= 5 and w.startswith(kw_words[0])) for w in words) if kw_words else False

        matched = {slug for slug, kws in self._keywords.items() if any(hit(kw) for kw in kws)}
        if not matched:
            return hits
        bonus = KEYWORD_BONUS if self.retriever is self.local else KEYWORD_BONUS / 4
        for h in hits:
            if h.chunk.demarche_slug in matched:
                h.score = h.raw_score + bonus
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    def retrieve(self, text: str, langue: str, top_k: int | None = None) -> list[ScoredChunk]:
        """Top-k chunks ; bascule sur l'index local en cas d'erreur réseau."""
        k = top_k or int(os.getenv("TOP_K_RESULTS", "5"))
        try:
            # On élargit la fenêtre avant re-classement pour ne pas perdre la bonne démarche.
            return self._rerank(text, self.retriever.search(text, langue, k * 3))[:k]
        except Exception as exc:  # noqa: BLE001
            if self.retriever is self.local:
                raise
            log.warning("Retrieval %s en échec (%s) — index local", self.mode, exc)
            hits = self._rerank(text, self.local.search(text, langue, k * 3))[:k]
            # Score local ramené sur l'échelle du seuil API pour une décision cohérente.
            for h in hits:
                h.raw_score = min(1.0, h.raw_score * MIN_CONFIDENCE / LOCAL_MIN_CONFIDENCE)
            return hits

    def query(self, text: str, langue_hint: str | None = None) -> RAGResult:
        """Traite une question citoyenne de bout en bout."""
        start = time.perf_counter()
        det = detect_language(text, hint=langue_hint)
        langue = det["langue"]
        hits = self.retrieve(text, langue) if text.strip() else []
        # Le seuil s'applique au score sémantique brut : le bonus lexical sert
        # au classement, jamais à faire entrer une question hors périmètre.
        score = max((h.raw_score for h in hits), default=0.0)
        hors_perimetre = score < self.threshold
        demarche = None if hors_perimetre else self.demarches.get(self._pick_demarche(hits))
        reponse = self.generator.generate(text, langue, hits, demarche, hors_perimetre)
        used = [] if hors_perimetre else hits
        return RAGResult(
            reponse=reponse,
            langue=langue,
            demarche_id=demarche["slug"] if demarche else None,
            documents=documents_for(demarche, langue) if demarche else [],
            score_confiance=round(float(score), 4),
            hors_perimetre=hors_perimetre,
            sources=sorted({h.chunk.source_url for h in used if h.chunk.source_url}),
            temps_ms=int((time.perf_counter() - start) * 1000),
            chunks_utilises=[h.chunk.id for h in used],
            mode=self.mode,
        )

    @staticmethod
    def _pick_demarche(hits: list[ScoredChunk]) -> str | None:
        """Démarche du meilleur chunk après re-classement.

        Une somme sur plusieurs chunks favoriserait les démarches au contenu le
        plus volumineux plutôt que la plus pertinente.
        """
        return hits[0].chunk.demarche_slug if hits else None
