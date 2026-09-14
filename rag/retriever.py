"""Recherche des chunks pertinents (CDC §05, PROMPT 4.3).

Trois back-ends, du plus précis au plus autonome :

* :class:`QdrantRetriever`  — embeddings OpenAI + Qdrant (production) ;
* :class:`PgVectorRetriever` — mêmes embeddings, repli sur PostgreSQL/pgvector ;
* :class:`LocalRetriever`   — TF-IDF sur n-grammes de caractères, 100 % local,
  sans clé API : borne hors ligne, développement et tests.

Tous renvoient des :class:`ScoredChunk` triés par score décroissant, filtrés
par langue avec repli (darija → ar, en/pt/es → fr) quand une langue n'a pas
de contenu. Le seuil de confiance décide du drapeau ``hors_perimetre``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .chunker import Chunk

LANG_FALLBACK = {"darija": ["darija", "ar", "fr"], "ar": ["ar", "darija", "fr"], "fr": ["fr"],
                 "en": ["en", "fr"], "pt": ["pt", "fr"], "es": ["es", "fr"]}

AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")

# Mots vides retirés avant la vectorisation locale (réduisent le bruit lexical).
STOP = set("""
le la les de des du d l un une et ou est pour au aux en à a je j me mon ma mes que qui quoi quels quelles quel quelle
comment faut il elle on ce cet cette ces sur par avec dans se sa son ses y ai as avez vous nous tu te ton
the a an of to for is are do does i my me what which how in on with and or need
el la los las de del para que qué es un una y o mi cómo como
o a os as de do da para que é um uma e ou meu minha como
في من على إلى عن ما ماذا هل أن او أو و يا مع هذا هذه التي الذي كيف
واش شنو اش آش ديال ف فـ ل لي اللي باش
""".split())


def normalize(text: str) -> str:
    """Normalise un texte multilingue (casse, accents latins, variantes arabes)."""
    text = text.lower()
    text = AR_DIACRITICS.sub("", text)
    text = re.sub("[إأآا]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def features(text: str) -> Counter:
    """Sac de mots + n-grammes de caractères (3-4), robuste à la morphologie arabe."""
    words = [w for w in re.findall(r"\w+", normalize(text)) if w not in STOP and len(w) > 1]
    feats: Counter = Counter()
    for w in words:
        feats[f"w:{w}"] += 2
        padded = f"#{w}#"
        for n in (3, 4):
            for i in range(len(padded) - n + 1):
                feats[f"c:{padded[i:i + n]}"] += 1
    return feats


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    raw_score: float = -1.0

    def __post_init__(self) -> None:
        if self.raw_score < 0:
            self.raw_score = self.score


class Retriever(Protocol):
    def search(self, query: str, langue: str, top_k: int = 5) -> list[ScoredChunk]: ...


class LocalRetriever:
    """Index TF-IDF en mémoire — aucune dépendance externe."""

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._vectors: list[dict[str, float]] = []
        df: Counter = Counter()
        raw = [features(c.contenu) for c in chunks]
        for f in raw:
            df.update(f.keys())
        n = max(len(chunks), 1)
        self._idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        for f in raw:
            self._vectors.append(self._weigh(f))
        self._langs = {c.langue.strip() for c in chunks}

    def _weigh(self, f: Counter) -> dict[str, float]:
        vec = {t: (1 + math.log(v)) * self._idf.get(t, 0.0) for t, v in f.items() if t in self._idf}
        norm = math.sqrt(sum(x * x for x in vec.values())) or 1.0
        return {t: x / norm for t, x in vec.items()}

    def search(self, query: str, langue: str, top_k: int = 5) -> list[ScoredChunk]:
        """Cosine TF-IDF entre la requête et les chunks de la langue (avec repli)."""
        q = self._weigh(features(query))
        if not q:
            return []
        langs = [lg for lg in LANG_FALLBACK.get(langue, [langue, "fr"]) if lg in self._langs]
        results: list[ScoredChunk] = []
        seen_keys: set[tuple[str, str]] = set()
        for lg in langs:
            for chunk, vec in zip(self.chunks, self._vectors):
                if chunk.langue.strip() != lg:
                    continue
                key = (chunk.demarche_slug, chunk.type_chunk)
                if key in seen_keys:
                    continue
                score = sum(w * vec.get(t, 0.0) for t, w in q.items())
                if score > 0:
                    results.append(ScoredChunk(chunk, score))
            # On ne descend dans la langue de repli que pour les (démarche, type) absents.
            seen_keys |= {(r.chunk.demarche_slug, r.chunk.type_chunk) for r in results}
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


class QdrantRetriever:
    """Recherche vectorielle Qdrant (collection ``wathiqadoc``)."""

    def __init__(self, url: str, embedder, collection: str = "wathiqadoc"):
        from qdrant_client import QdrantClient

        self.client = QdrantClient(url=url, timeout=2.0)
        self.embedder = embedder
        self.collection = collection

    def search(self, query: str, langue: str, top_k: int = 5) -> list[ScoredChunk]:
        from qdrant_client import models

        vector = self.embedder.embed([query])[0]
        langs = LANG_FALLBACK.get(langue, [langue, "fr"])
        hits = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            query_filter=models.Filter(must=[models.FieldCondition(key="langue", match=models.MatchAny(any=langs))]),
            with_payload=True,
        ).points
        out = []
        for h in hits:
            p = h.payload or {}
            chunk = Chunk(id=str(h.id), demarche_slug=p["demarche_slug"], type_chunk=p["type_chunk"],
                          langue=p["langue"], contenu=p["contenu"], tokens_count=p.get("tokens_count", 0),
                          version=p.get("version", 1), source_url=p.get("source_url"))
            # Priorité à la langue demandée à score quasi égal.
            bonus = 0.02 if p["langue"] == langue else 0.0
            out.append(ScoredChunk(chunk, float(h.score) + bonus))
        out.sort(key=lambda r: r.score, reverse=True)
        return out


class PgVectorRetriever:
    """Repli pgvector si Qdrant est indisponible."""

    def __init__(self, database_url: str, embedder):
        import psycopg

        self.conn = psycopg.connect(database_url, autocommit=True, connect_timeout=2)
        self.embedder = embedder

    def search(self, query: str, langue: str, top_k: int = 5) -> list[ScoredChunk]:
        vector = self.embedder.embed([query])[0]
        langs = LANG_FALLBACK.get(langue, [langue, "fr"])
        literal = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
        rows = self.conn.execute(
            """SELECT c.id, d.slug, c.type_chunk, trim(c.langue), c.contenu, c.tokens_count, c.version,
                      c.source_url, 1 - (c.embedding <=> %s::vector) AS score
               FROM chunks c JOIN demarches d ON d.id = c.demarche_id
               WHERE trim(c.langue) = ANY(%s) AND d.statut = 'production'
               ORDER BY c.embedding <=> %s::vector LIMIT %s""",
            (literal, langs, literal, top_k),
        ).fetchall()
        return [ScoredChunk(Chunk(str(r[0]), r[1], r[2], r[3], r[4], r[5] or 0, r[6], r[7]), float(r[8])) for r in rows]
