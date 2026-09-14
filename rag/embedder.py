"""Vectorisation et indexation des chunks (CDC §05, PROMPT 4.2).

Modèle : ``text-embedding-3-small`` (OpenAI, 1536 dimensions), par lots de 100.
Stockage : Qdrant (collection ``wathiqadoc``), avec repli pgvector.
"""

from __future__ import annotations

import logging
import os

from .chunker import Chunk

log = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
BATCH_SIZE = 100


class OpenAIEmbedder:
    """Client d'embeddings OpenAI."""

    def __init__(self, model: str | None = None):
        import openai

        self.client = openai.OpenAI()
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Vectorise une liste de textes par lots de 100."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        return vectors


def index_qdrant(chunks: list[Chunk], embedder: OpenAIEmbedder, url: str, collection: str = "wathiqadoc") -> int:
    """(Ré)indexe les chunks dans Qdrant. Retourne le nombre de points écrits."""
    from qdrant_client import QdrantClient, models

    client = QdrantClient(url=url)
    if not client.collection_exists(collection):
        client.create_collection(collection, vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE))
        client.create_payload_index(collection, "langue", models.PayloadSchemaType.KEYWORD)
    vectors = embedder.embed([c.contenu for c in chunks])
    points = [
        models.PointStruct(id=c.id, vector=v, payload={
            "demarche_slug": c.demarche_slug, "type_chunk": c.type_chunk, "langue": c.langue,
            "contenu": c.contenu, "tokens_count": c.tokens_count, "version": c.version, "source_url": c.source_url,
        })
        for c, v in zip(chunks, vectors)
    ]
    for i in range(0, len(points), BATCH_SIZE):
        client.upsert(collection, points=points[i:i + BATCH_SIZE])
    log.info("Qdrant : %d points indexés dans %s", len(points), collection)
    return len(points)


def index_pgvector(chunks: list[Chunk], embedder: OpenAIEmbedder, database_url: str) -> int:
    """Écrit les embeddings dans la table ``chunks`` (repli si Qdrant indisponible)."""
    import psycopg

    vectors = embedder.embed([c.contenu for c in chunks])
    with psycopg.connect(database_url) as conn:
        for c, v in zip(chunks, vectors):
            literal = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
            conn.execute(
                """INSERT INTO chunks (id, demarche_id, type_chunk, langue, contenu, embedding, tokens_count, version, source_url)
                   SELECT %s, d.id, %s, %s, %s, %s::vector, %s, %s, %s FROM demarches d WHERE d.slug = %s
                   ON CONFLICT (id) DO UPDATE SET contenu = EXCLUDED.contenu, embedding = EXCLUDED.embedding""",
                (c.id, c.type_chunk, c.langue, c.contenu, literal, c.tokens_count, c.version, c.source_url, c.demarche_slug),
            )
    log.info("pgvector : %d chunks indexés", len(chunks))
    return len(chunks)


def index_chunks(chunks: list[Chunk]) -> str:
    """Indexe dans Qdrant, sinon dans pgvector. Retourne le back-end utilisé."""
    embedder = OpenAIEmbedder()
    try:
        index_qdrant(chunks, embedder, os.getenv("QDRANT_URL", "http://localhost:6333"))
        return "qdrant"
    except Exception as exc:  # noqa: BLE001 — repli explicite exigé par le CDC
        log.warning("Qdrant indisponible (%s) — repli pgvector", exc)
        index_pgvector(chunks, embedder, os.environ["DATABASE_URL"])
        return "pgvector"
