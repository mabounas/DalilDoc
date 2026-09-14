"""Indexe toute la base de connaissances publiée dans Qdrant (ou pgvector).

Usage (depuis ``backend/``, clés OpenAI requises) : ``python -m scripts.index_vectors``
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, init_db  # noqa: E402
from app.services.knowledge import published_knowledge, seed_from_files  # noqa: E402
from rag.chunker import chunk_knowledge  # noqa: E402
from rag.embedder import index_chunks  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    init_db()
    with SessionLocal() as db:
        seed_from_files(db)
        knowledge = published_knowledge(db)
    chunks = chunk_knowledge({"demarches": knowledge})
    backend = index_chunks(chunks)
    print(f"{len(chunks)} chunks indexés ({len(knowledge)} démarches) → {backend}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
