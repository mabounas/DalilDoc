"""Découpage de la base de connaissances en chunks (CDC §05, PROMPT 4.1).

Entrée : fichier de connaissances structuré (``data/knowledge/*.json``), où
chaque démarche porte des champs multilingues ``{fr, ar, darija, en, pt, es}``.

Sortie : une liste de :class:`Chunk` — un chunk par (démarche × type × langue),
redécoupé en fenêtres de 150-400 tokens avec 50 tokens de recouvrement.
Types : conditions, documents, exceptions, tarifs, faq.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

LANGS = ("fr", "ar", "darija", "en", "pt", "es")
CHUNK_TYPES = ("conditions", "documents", "exceptions", "tarifs", "faq")
MIN_TOKENS, MAX_TOKENS, OVERLAP = 150, 400, 50

HEADERS = {
    "conditions": {"fr": "Conditions", "ar": "الشروط", "darija": "الشروط", "en": "Conditions", "pt": "Condições", "es": "Condiciones"},
    "documents": {"fr": "Documents requis", "ar": "الوثائق المطلوبة", "darija": "الوراق اللي خاصك", "en": "Required documents", "pt": "Documentos exigidos", "es": "Documentos requeridos"},
    "exceptions": {"fr": "Cas particuliers", "ar": "حالات خاصة", "darija": "حالات خاصة", "en": "Special cases", "pt": "Casos especiais", "es": "Casos particulares"},
    "tarifs": {"fr": "Tarifs et délais", "ar": "الواجبات والآجال", "darija": "الثمن والوقت", "en": "Fees and timing", "pt": "Taxas e prazos", "es": "Tasas y plazos"},
    "faq": {"fr": "Questions fréquentes", "ar": "أسئلة شائعة", "darija": "أسئلة اللي كيتسولو بزاف", "en": "FAQ", "pt": "Perguntas frequentes", "es": "Preguntas frecuentes"},
}
OPTIONAL = {"fr": "facultatif", "ar": "اختياري", "darija": "ماشي ضروري", "en": "optional", "pt": "opcional", "es": "opcional"}

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def count_tokens(text: str) -> int:
    """Approximation du nombre de tokens (mots + ponctuation), sans dépendance."""
    return len(TOKEN_RE.findall(text))


@dataclass
class Chunk:
    """Unité indexée dans la base vectorielle."""

    id: str
    demarche_slug: str
    type_chunk: str
    langue: str
    contenu: str
    tokens_count: int
    version: int = 1
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _t(value: dict | str | None, lang: str) -> str | None:
    """Valeur multilingue dans la langue demandée (sans repli silencieux)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.get(lang)


def split_tokens(text: str, max_tokens: int = MAX_TOKENS, overlap: int = OVERLAP) -> list[str]:
    """Découpe un texte en fenêtres ≤ ``max_tokens`` recouvrantes, en coupant aux lignes."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if count_tokens(text) <= max_tokens:
        return [text]
    windows, current, current_tokens = [], [], 0
    for line in lines:
        n = count_tokens(line)
        if current and current_tokens + n > max_tokens:
            windows.append("\n".join(current))
            # Recouvrement : on reprend les dernières lignes jusqu'à ~overlap tokens.
            keep, kept = [], 0
            for prev in reversed(current):
                kept += count_tokens(prev)
                keep.insert(0, prev)
                if kept >= overlap:
                    break
            current, current_tokens = keep, kept
        current.append(line)
        current_tokens += n
    if current:
        windows.append("\n".join(current))
    return windows


def render_section(demarche: dict, type_chunk: str, lang: str) -> str | None:
    """Rend une section d'une démarche en texte, ou None si absente dans cette langue."""
    titre = _t(demarche.get("titres"), lang)
    if not titre:
        return None
    lines: list[str] = []
    if type_chunk == "documents":
        for doc in sorted(demarche.get("documents", []), key=lambda d: d.get("ordre", 0)):
            nom = _t(doc.get("nom"), lang)
            if not nom:
                continue
            extra = []
            if not doc.get("obligatoire", True):
                extra.append(OPTIONAL[lang])
            cond = _t(doc.get("condition"), lang)
            if cond:
                extra.append(cond)
            lines.append(f"{doc.get('ordre', len(lines) + 1)}. {nom}" + (f" ({'; '.join(extra)})" if extra else ""))
    elif type_chunk == "faq":
        for qa in demarche.get("faq", []):
            q, r = _t(qa.get("question"), lang), _t(qa.get("reponse"), lang)
            if q and r:
                lines.append(f"Q: {q}\nR: {r}")
    else:
        for item in demarche.get(type_chunk, []):
            txt = _t(item, lang)
            if txt:
                lines.append(f"- {txt}")
    if not lines:
        return None
    # Mots-clés spécifiques + synonymes génériques : indexés pour la recherche lexicale.
    mots = (demarche.get("mots_cles") or {}).get(lang, []) + (demarche.get("synonymes") or {}).get(lang, [])
    header = f"{titre} — {HEADERS[type_chunk][lang]}"
    if mots:
        header += f"\n[{', '.join(mots)}]"
    return header + "\n" + "\n".join(lines)


def _stable_id(*parts: str) -> str:
    return str(uuid.UUID(hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()))


def chunk_demarche(demarche: dict) -> list[Chunk]:
    """Produit tous les chunks (types × langues) d'une démarche."""
    chunks: list[Chunk] = []
    for type_chunk in CHUNK_TYPES:
        for lang in LANGS:
            text = render_section(demarche, type_chunk, lang)
            if not text:
                continue
            header = text.split("\n", 1)[0]
            for i, window in enumerate(split_tokens(text)):
                # Chaque fenêtre garde le titre de section pour rester autoportante.
                contenu = window if window.startswith(header) else f"{header}\n{window}"
                chunks.append(
                    Chunk(
                        id=_stable_id(demarche["slug"], type_chunk, lang, str(i), str(demarche.get("version", 1))),
                        demarche_slug=demarche["slug"],
                        type_chunk=type_chunk,
                        langue=lang,
                        contenu=contenu,
                        tokens_count=count_tokens(contenu),
                        version=demarche.get("version", 1),
                        source_url=demarche.get("source_url"),
                        metadata={"categorie": demarche.get("categorie"), "partie": i},
                    )
                )
    return chunks


def load_knowledge(path: str | Path) -> dict:
    """Charge un fichier de connaissances JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def chunk_knowledge(knowledge: dict) -> list[Chunk]:
    """Découpe toutes les démarches actives d'une base de connaissances."""
    out: list[Chunk] = []
    for d in knowledge.get("demarches", []):
        if d.get("actif", True):
            out.extend(chunk_demarche(d))
    return out
