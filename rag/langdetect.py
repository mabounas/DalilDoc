"""Détection de langue : fr · ar · darija · en · pt · es (CDC §08).

fasttext (`lid.176.bin`) est utilisé s'il est installé ; sinon une heuristique
légère (script + mots-outils) prend le relais, ce qui suffit pour la borne
hors ligne. Dans les deux cas, l'arabe est ensuite départagé entre MSA et
darija à l'aide de marqueurs lexicaux propres au dialecte marocain.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

SUPPORTED = ("fr", "ar", "darija", "en", "pt", "es")

DARIJA_MARKERS = {
    "واش", "دابا", "كيدير", "ماشي", "بزاف", "زوين", "ديال", "ديالي", "ديالك", "شنو", "شنا", "علاش",
    "فين", "كيفاش", "بغيت", "خاصني", "خصني", "خاص", "كاين", "كاينة", "مزيان", "غادي", "نقدر", "بلا",
    "ضاعت", "ضاع", "تلفت", "شحال", "راه", "هادي", "هاد", "دير", "نديرها", "كنبغي", "ليا", "عندي",
    "لاكارط", "لاكارت", "نسيت", "بغيت", "كيفاش", "الكود", "ضاعتلي", "البطاقة ديال", "باش", "حتى", "واخا", "ولدي", "بنتي",
}
# Darija écrite en alphabet latin (arabizi).
DARIJA_LATIN_MARKERS = {
    "wach", "wash", "daba", "bghit", "bghina", "khasni", "khassni", "dyal", "dial", "fin", "kifach",
    "chno", "shno", "3lach", "kayn", "kayna", "bzaf", "mzyan", "lakart", "lacarte", "ghadi", "nqder",
    "diali", "mcha", "tlfat", "dal3at", "wlidi",
}

STOPWORDS = {
    "fr": {"le", "la", "les", "de", "des", "du", "pour", "une", "un", "et", "est", "je", "quels", "quelles",
           "carte", "documents", "pièces", "mon", "ma", "mes", "comment", "faut", "il", "que", "qui", "renouveler",
           "perdu", "perte", "identité", "nationale", "demande", "en", "au", "à", "sont", "obtenir", "papiers"},
    "en": {"the", "for", "what", "which", "documents", "do", "i", "need", "my", "card", "id", "how", "to",
           "is", "are", "renew", "lost", "national", "identity", "a", "of", "get", "required"},
    "es": {"el", "los", "las", "para", "qué", "que", "documentos", "necesito", "mi", "tarjeta", "cómo", "como",
           "renovar", "perdí", "identidad", "nacional", "del", "una", "es", "son", "necesarios", "y", "carné"},
    "pt": {"o", "os", "as", "para", "quais", "documentos", "preciso", "meu", "minha", "cartão", "como",
           "renovar", "perdi", "identidade", "nacional", "do", "da", "uma", "é", "são", "necessários", "e", "bilhete"},
}

ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9']+")


@lru_cache(maxsize=1)
def _fasttext_model():
    path = os.getenv("FASTTEXT_MODEL", "lid.176.bin")
    if not os.path.exists(path):
        return None
    try:
        import fasttext  # type: ignore

        return fasttext.load_model(path)
    except Exception:  # noqa: BLE001 — dépendance optionnelle
        return None


def is_darija(text: str) -> bool:
    """Vrai si le texte contient des marqueurs lexicaux de darija (arabe ou latin)."""
    lowered = text.lower()
    tokens = set(re.findall(r"[؀-ۿ]+|[a-z0-9]+", lowered))
    if tokens & DARIJA_MARKERS or tokens & DARIJA_LATIN_MARKERS:
        return True
    return any(" " in m and m in lowered for m in DARIJA_MARKERS)


def _heuristic(text: str) -> tuple[str, float]:
    arabic_chars = len(ARABIC_RE.findall(text))
    letters = sum(ch.isalpha() for ch in text) or 1
    if arabic_chars / letters > 0.4:
        return "ar", arabic_chars / letters
    words = [w.lower() for w in LATIN_WORD_RE.findall(text)]
    if not words:
        return "fr", 0.0
    scores = {lang: sum(w in sw for w in words) for lang, sw in STOPWORDS.items()}
    # Indices orthographiques discriminants.
    if re.search(r"[ãõç]|ção|ções", text.lower()):
        scores["pt"] += 2
    if re.search(r"[ñ¿¡]|ción", text.lower()):
        scores["es"] += 2
    if re.search(r"[èêàùœ]|\bqu'", text.lower()):
        scores["fr"] += 2
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] == 0:
        return "fr", 0.3
    return best, scores[best] / total


def detect_language(text: str, hint: str | None = None) -> dict:
    """Détecte la langue d'une requête.

    Args:
        text: texte transcrit ou saisi.
        hint: langue choisie sur la borne (utilisée en cas d'ambiguïté).

    Returns:
        ``{"langue": str, "confidence": float, "methode": str}``
    """
    text = (text or "").strip()
    if not text:
        return {"langue": hint if hint in SUPPORTED else "fr", "confidence": 0.0, "methode": "vide"}

    langue, conf, methode = None, 0.0, "heuristique"
    model = _fasttext_model()
    if model is not None:
        labels, probs = model.predict(text.replace("\n", " "))
        code = labels[0].replace("__label__", "")
        mapping = {"fr": "fr", "ar": "ar", "arz": "ar", "ary": "darija", "en": "en", "pt": "pt", "es": "es"}
        if code in mapping:
            langue, conf, methode = mapping[code], float(probs[0]), "fasttext"
    if langue is None:
        langue, conf = _heuristic(text)

    if langue == "ar" and is_darija(text):
        langue = "darija"
    elif langue in {"fr", "en"} and is_darija(text):
        langue, methode = "darija", methode + "+arabizi"

    # Sur une borne, la langue sélectionnée départage les cas peu sûrs.
    if hint in SUPPORTED and conf < 0.5:
        if not (hint == "ar" and langue == "darija"):
            langue = hint
    return {"langue": langue, "confidence": round(conf, 3), "methode": methode}
