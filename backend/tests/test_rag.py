"""Tests unitaires du moteur RAG (CDC §12)."""

import json
from pathlib import Path

import pytest

from rag import WathiqaRAG
from rag.chunker import MAX_TOKENS, chunk_knowledge, split_tokens, count_tokens
from rag.langdetect import detect_language
from rag.prompts import FALLBACK_MESSAGES

KB = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "cin.json"


@pytest.fixture(scope="module")
def rag():
    return WathiqaRAG(mode="local")


def test_chunking_taille():
    """Chunks ≤ 400 tokens ; les fenêtres d'un découpage font ≥ 150 tokens (sauf la dernière)."""
    chunks = chunk_knowledge(json.loads(KB.read_text(encoding="utf-8")))
    assert chunks
    assert max(c.tokens_count for c in chunks) <= MAX_TOKENS
    long_text = "\n".join(f"{i}. " + "mot " * 40 for i in range(30))
    windows = split_tokens(long_text)
    assert len(windows) > 1
    assert all(count_tokens(w) <= MAX_TOKENS for w in windows)
    assert all(count_tokens(w) >= 150 for w in windows[:-1])


def test_chunks_six_langues():
    chunks = chunk_knowledge(json.loads(KB.read_text(encoding="utf-8")))
    docs = {c.langue for c in chunks if c.type_chunk == "documents" and c.demarche_slug == "cin-premiere-demande"}
    assert docs == {"fr", "ar", "darija", "en", "pt", "es"}


def test_retrieval_score_minimum(rag):
    """Score sous le seuil → hors_perimetre = True."""
    res = rag.query("Quelle est la météo à Casablanca demain ?", "fr")
    assert res.score_confiance < rag.threshold
    assert res.hors_perimetre is True


def test_generation_hors_perimetre(rag):
    """Réponse hors contexte → message d'orientation guichet, aucun document."""
    res = rag.query("Recette du tajine aux pruneaux", "fr")
    assert res.reponse == FALLBACK_MESSAGES["fr"]
    assert res.documents == [] and res.sources == []


def test_langue_detection_darija():
    """'واش كاين وثيقة' → darija."""
    assert detect_language("واش كاين وثيقة")["langue"] == "darija"
    assert detect_language("ما هي الوثائق المطلوبة لتجديد البطاقة الوطنية")["langue"] == "ar"
    assert detect_language("Quels documents pour la carte d'identité ?")["langue"] == "fr"
    assert detect_language("Qué documentos necesito para el carné?")["langue"] == "es"


@pytest.mark.parametrize("question,hint,slug", [
    ("Documents pour CIN", "fr", "cin-premiere-demande"),
    ("J'ai perdu ma carte d'identité", "fr", "cin-perte-vol-deterioration"),
    ("وثائق تجديد البطاقة الوطنية", None, "cin-renouvellement"),
    ("What documents do I need to renew my ID card?", None, "cin-renouvellement"),
    ("واش كاين وثيقة باش ندير لاكارط لولدي", None, "cin-mineur"),
    ("ma mère est alitée à l'hôpital, comment faire sa carte ?", "fr", "cin-cas-particuliers"),
    ("comment modifier mon rendez-vous", "fr", "cin-pre-demande-en-ligne"),
    ("نسيت الكود PIN", None, "cin-perte-vol-deterioration"),
])
def test_routage_demarches(rag, question, hint, slug):
    res = rag.query(question, hint)
    assert not res.hors_perimetre, (question, res.score_confiance)
    assert res.demarche_id == slug


def test_reponse_fondee_sur_la_base(rag):
    """Zéro hallucination (mode extractif) : chaque document cité existe dans la base."""
    kb = {d["slug"]: d for d in json.loads(KB.read_text(encoding="utf-8"))["demarches"]}
    res = rag.query("Quels documents pour une première carte d'identité ?", "fr")
    noms = {doc["nom"]["fr"] for doc in kb[res.demarche_id]["documents"]}
    assert {d["nom"] for d in res.documents} <= noms
    assert "https://www.cnie.ma/static/procedure" in res.sources


def test_temps_reponse_local(rag):
    res = rag.query("Documents pour renouveler ma CIN", "fr")
    assert res.temps_ms < 3000
