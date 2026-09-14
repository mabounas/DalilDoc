"""Pré-génère le cache audio des réponses de la borne : aucune attente à la première lecture.

Chaque réponse est lue phrase par phrase (titre, en-tête, documents) ; ce script
génère ces phrases pour toutes les démarches publiées, plus le message
« rapprochez-vous du guichet ». Seules les phrases absentes du cache consomment
des crédits ElevenLabs ; relancer le script ne coûte rien.

Usage (dans le conteneur api) :
    python -m scripts.prewarm_tts --dry-run                # estimation des crédits
    python -m scripts.prewarm_tts --langs darija,ar        # génération
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal, init_db  # noqa: E402
from app.services import tts  # noqa: E402
from app.services.knowledge import published_knowledge, seed_from_files  # noqa: E402
from rag.chunker import LANGS  # noqa: E402
from rag.prompts import FALLBACK_MESSAGES  # noqa: E402


def collect(knowledge: list[dict], langs: list[str]) -> list[tuple[str, str]]:
    """Phrases uniques (texte, langue) à lire sur la borne."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for langue in langs:
        texts = [FALLBACK_MESSAGES.get(langue, "")]
        for demarche in knowledge:
            texts += tts.spoken_segments(demarche, langue)
        for text in texts:
            key = (" ".join(text.split()), langue)
            if text.strip() and key not in seen:
                seen.add(key)
                out.append((text, langue))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--langs", default=",".join(LANGS), help="ex. darija,ar,fr")
    parser.add_argument("--dry-run", action="store_true", help="n'appelle pas ElevenLabs, estime les crédits")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    langs = [lg.strip() for lg in args.langs.split(",") if lg.strip() in LANGS]
    if not langs:
        print("Aucune langue valide.")
        return 2
    init_db()
    with SessionLocal() as db:
        seed_from_files(db)
        knowledge = published_knowledge(db)

    phrases = collect(knowledge, langs)
    missing = [(t, lg) for t, lg in phrases if not tts.is_cached(t, lg)]
    chars = sum(len(t) for t, _ in missing)
    print(f"{len(phrases)} phrases ({', '.join(langs)}) : {len(phrases) - len(missing)} déjà en cache, "
          f"{len(missing)} à générer ≈ {chars} caractères ElevenLabs.")
    if args.dry_run or not missing:
        return 0

    done = 0
    for text, langue in missing:
        try:
            tts.synthesize_cached(text, langue)
        except tts.TTSUnavailable as exc:
            print(f"Arrêt après {done}/{len(missing)} phrases : {exc}")
            return 1
        done += 1
        if done % 10 == 0 or done == len(missing):
            print(f"  {done}/{len(missing)} générées")
    print("Cache audio prêt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
