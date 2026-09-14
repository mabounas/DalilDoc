"""Génération de la réponse (CDC §05, PROMPT 4.4).

* :class:`ClaudeGenerator` — Claude (Anthropic SDK), réponse fondée
  uniquement sur les chunks récupérés, 250 tokens max ;
* :class:`ExtractiveGenerator` — sans LLM : recopie la liste numérotée des
  documents depuis la base structurée. Zéro hallucination par construction ;
  sert de mode dégradé (hors ligne, erreur API, réponse tronquée).
"""

from __future__ import annotations

import logging
import os

from .chunker import HEADERS, OPTIONAL
from .prompts import CONTEXT_TEMPLATE, FALLBACK_MESSAGES, SYSTEM_PROMPTS
from .retriever import ScoredChunk

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5"

LABELS = {
    "tarif": {"fr": "Coût", "ar": "التكلفة", "darija": "الثمن", "en": "Cost", "pt": "Custo", "es": "Coste"},
    "where": {"fr": "Où", "ar": "أين", "darija": "فين", "en": "Where", "pt": "Onde", "es": "Dónde"},
    "source": {"fr": "Source", "ar": "المصدر", "darija": "المصدر", "en": "Source", "pt": "Fonte", "es": "Fuente"},
}


def _t(value, lang: str, fallback: tuple[str, ...] = ("fr",)) -> str | None:
    if value is None or isinstance(value, str):
        return value
    for lg in (lang, *fallback):
        if value.get(lg):
            return value[lg]
    return None


def documents_for(demarche: dict, lang: str) -> list[dict]:
    """Liste des documents d'une démarche, localisée pour l'API/borne."""
    fb = ("ar", "fr") if lang == "darija" else ("fr",)
    out = []
    for doc in sorted(demarche.get("documents", []), key=lambda d: d.get("ordre", 0)):
        out.append({
            "ordre": doc.get("ordre"),
            "nom": _t(doc.get("nom"), lang, fb),
            "obligatoire": doc.get("obligatoire", True),
            "condition": _t(doc.get("condition"), lang, fb),
            "format": doc.get("format") or [],
        })
    return out


class ExtractiveGenerator:
    """Réponse construite uniquement à partir de la base structurée."""

    def generate(self, question: str, langue: str, hits: list[ScoredChunk], demarche: dict | None, hors_perimetre: bool) -> str:
        if hors_perimetre or demarche is None:
            return FALLBACK_MESSAGES.get(langue, FALLBACK_MESSAGES["fr"])
        fb = ("ar", "fr") if langue == "darija" else ("fr",)
        top_type = hits[0].chunk.type_chunk if hits else "documents"
        lines = [f"{_t(demarche['titres'], langue, fb)}"]
        if top_type in {"faq", "exceptions", "conditions"} and hits:
            # Question ciblée : on restitue le passage source tel quel.
            body = hits[0].chunk.contenu.split("\n", 1)[-1]
            body = "\n".join(ln for ln in body.split("\n") if not ln.startswith("["))
            lines.append(body)
        else:
            lines.append(f"{HEADERS['documents'][langue]} :")
            for doc in documents_for(demarche, langue):
                extra = [x for x in ([] if doc["obligatoire"] else [OPTIONAL[langue]]) + [doc["condition"]] if x]
                lines.append(f"{doc['ordre']}. {doc['nom']}" + (f" ({'; '.join(extra)})" if extra else ""))
        if demarche.get("cout_mad"):
            lines.append(f"{LABELS['tarif'][langue]} : {demarche['cout_mad']:g} MAD")
        return "\n".join(lines)


class ClaudeGenerator:
    """Génération contrôlée par Claude, avec repli extractif."""

    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=float(os.getenv("LLM_TIMEOUT_S", "8")), max_retries=1)
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens or int(os.getenv("MAX_OUTPUT_TOKENS", "250"))
        self.fallback = ExtractiveGenerator()

    def generate(self, question: str, langue: str, hits: list[ScoredChunk], demarche: dict | None, hors_perimetre: bool) -> str:
        if hors_perimetre or not hits:
            return FALLBACK_MESSAGES.get(langue, FALLBACK_MESSAGES["fr"])
        context = "\n\n---\n\n".join(h.chunk.contenu for h in hits)
        anthropic = self._anthropic
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                # Réponse courte et extractive : pas de raisonnement étendu (latence < 3 s).
                thinking={"type": "disabled"},
                system=[{"type": "text", "text": SYSTEM_PROMPTS.get(langue, SYSTEM_PROMPTS["fr"]),
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": CONTEXT_TEMPLATE.format(context=context, question=question)}],
            )
        except anthropic.RateLimitError:
            log.warning("Claude : limite de débit — réponse extractive")
            return self.fallback.generate(question, langue, hits, demarche, hors_perimetre)
        except anthropic.APIStatusError as exc:
            log.error("Claude : erreur API %s — réponse extractive", exc.status_code)
            return self.fallback.generate(question, langue, hits, demarche, hors_perimetre)
        except anthropic.APIConnectionError:
            log.warning("Claude injoignable — mode dégradé extractif")
            return self.fallback.generate(question, langue, hits, demarche, hors_perimetre)

        if response.stop_reason in {"refusal", "max_tokens"}:
            # Réponse refusée ou tronquée : on ne montre jamais une liste incomplète.
            log.info("Claude stop_reason=%s — réponse extractive", response.stop_reason)
            return self.fallback.generate(question, langue, hits, demarche, hors_perimetre)
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        return text or self.fallback.generate(question, langue, hits, demarche, hors_perimetre)
