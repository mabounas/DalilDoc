"""API WathiqaDoc."""

import sys
from pathlib import Path

# Le moteur RAG (`rag/`) et la base de connaissances (`data/`) vivent à la racine du monorepo.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
