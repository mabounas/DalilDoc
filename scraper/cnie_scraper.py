"""Scraper du portail officiel https://www.cnie.ma (DGSN).

Le portail est une application Angular : le contenu éditorial est injecté
côté client. On le rend donc avec Playwright (Chromium headless), en français
puis en arabe, et on complète avec les référentiels publics exposés par
l'API `/cnie-api` (lecture seule, GET uniquement).

Particularités du site gérées ici :
  * la langue par défaut est l'arabe ; le basculement se fait via le lien
    « Français » du menu (état conservé en mémoire par ngx-translate), on
    navigue donc ensuite *dans* le routeur Angular (pushState) sans recharger ;
  * la FAQ utilise des `mat-expansion-panel` repliés : on les déplie et on lit
    `textContent` (et non `innerText`) pour capter le texte masqué ;
  * le site ne devient jamais « networkidle » (analytics) : attentes fixes.

Sorties (dans ``data/raw/cnie/``) :
    pages/<lang>/<slug>.json   texte structuré (titres, paragraphes, listes)
    pages/<lang>/<slug>.md     rendu Markdown lisible
    api/<nom>.json             référentiels (types de demande, motifs…)
    i18n/<lang>.json           libellés officiels du portail
    manifest.json              date de collecte, URLs, empreintes SHA-256

Usage :
    python scraper/cnie_scraper.py [--out data/raw/cnie] [--langs fr,ar]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://www.cnie.ma"
API_URL = f"{BASE_URL}/cnie-api"
USER_AGENT = "WathiqaDoc-KB-Bot/1.0 (+https://github.com/mabounas/DalilDoc)"
POLITE_DELAY_S = 1.0

log = logging.getLogger("cnie_scraper")


@dataclass(frozen=True)
class Page:
    slug: str
    path: str
    categorie: str


PAGES: list[Page] = [
    Page("procedure", "/static/procedure", "procedures"),
    Page("cnie-pour-mineur", "/static/procedure/cnie-pour-mineur", "procedures"),
    Page("a-qui-s-adresser", "/static/procedure/a-qui-s-adresser", "procedures"),
    Page("frais-timbre", "/static/procedure/frais-timbre", "tarifs"),
    Page("normes-photographies", "/static/procedure/normes-photographies", "conditions"),
    Page("faq", "/static/faq", "faq"),
    Page("about", "/static/about", "information"),
    Page("reglementation", "/static/reglementation", "reglementation"),
    Page("informations-pratiques", "/pages/practical-informations", "information"),
    Page("cas-particuliers", "/request-particular-cases", "exceptions"),
    Page("types-demande", "/request-select-type", "procedures"),
]

# Référentiels publics (GET, aucune donnée personnelle).
API_ENDPOINTS: dict[str, str] = {
    "types_demande": "/configuration/requesttype/load",
    "motifs_duplicata": "/referentiel/motifduplicata/find",
    "types_profession": "/referentiel/typeprofession/find",
}

LANG_LINK_TEXT = {"fr": "Français", "ar": "العربية"}

SWITCH_LANG_JS = """
label => {
  const a = [...document.querySelectorAll('a')].find(x => x.textContent.trim() === label);
  if (a) a.click();
  return !!a;
}
"""

SPA_NAVIGATE_JS = """
path => { history.pushState({}, '', path); dispatchEvent(new PopStateEvent('popstate', {state: {}})); }
"""

EXPAND_PANELS_JS = """
() => {
  const headers = document.querySelectorAll('main mat-expansion-panel-header[aria-expanded="false"]');
  headers.forEach(h => h.click());
  return headers.length;
}
"""

# Extraction DOM : chaque nœud texte est rattaché à son bloc parent le plus
# proche (titre, paragraphe, élément de liste…) ; on conserve l'ordre et la
# profondeur de liste. `textContent` inclut le contenu des panneaux repliés.
EXTRACT_JS = r"""
() => {
  const root = document.querySelector('main') || document.body;
  const BLOCK = new Set(['H1','H2','H3','H4','H5','H6','P','LI','TD','TH','DT','DD','DIV','SECTION',
                         'MAT-PANEL-TITLE','MAT-PANEL-DESCRIPTION','BLOCKQUOTE','LABEL','FIGCAPTION']);
  const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','BUTTON','SELECT','OPTION','INPUT','TEXTAREA']);
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const blocks = [];
  let current = null;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => {
      for (let p = n.parentElement; p && p !== root; p = p.parentElement)
        if (SKIP.has(p.tagName)) return NodeFilter.FILTER_REJECT;
      return clean(n.textContent) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    let el = n.parentElement;
    while (el && el !== root && !BLOCK.has(el.tagName)) el = el.parentElement;
    let tag = el ? el.tagName.toLowerCase() : 'p';
    const heading = el && el.closest('h1,h2,h3,h4,h5,h6');
    if (heading) { el = heading; tag = heading.tagName.toLowerCase(); }
    else if (el && el.closest('mat-panel-title')) { el = el.closest('mat-panel-title'); tag = 'h5'; }
    else if (el && tag !== 'li' && el.closest('li')) { el = el.closest('li'); tag = 'li'; }
    if (current && current.el === el) { current.text += ' ' + clean(n.textContent); continue; }
    let depth = 0;
    for (let p = el; p && p !== root; p = p.parentElement) if (p.tagName === 'UL' || p.tagName === 'OL') depth++;
    current = {el, tag, depth, text: clean(n.textContent)};
    blocks.push(current);
  }
  const out = [];
  for (const b of blocks) {
    const text = clean(b.text);
    if (!text) continue;
    const prev = out[out.length - 1];
    if (prev && prev.text === text) continue;
    out.push({tag: b.tag, depth: b.depth, text});
  }
  return {title: document.title, text: clean(root.textContent), blocks: out};
}
"""


def sha256(text: str) -> str:
    """Empreinte SHA-256 hexadécimale d'un texte (détection de changements)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def blocks_to_markdown(title: str, blocks: list[dict]) -> str:
    """Convertit les blocs extraits en Markdown lisible."""
    lines = [f"# {title}", ""]
    for b in blocks:
        tag, text = b["tag"], b["text"]
        if tag in {"h1", "h2", "h3"}:
            lines += ["", f"## {text}", ""]
        elif tag in {"h4", "h5", "h6"}:
            lines += ["", f"### {text}", ""]
        elif tag == "li":
            lines.append(f"{'  ' * max(b['depth'] - 1, 0)}- {text}")
        else:
            lines += [text, ""]
    return "\n".join(lines).strip() + "\n"


def wait_render(page, ms: int = 2500) -> None:
    """Attend le rendu Angular (le site ne devient jamais « networkidle »)."""
    page.wait_for_selector("main", timeout=60_000)
    page.wait_for_timeout(ms)


def scrape_pages(out: Path, langs: list[str]) -> list[dict]:
    """Rend chaque page avec Chromium et sauvegarde texte + structure."""
    from playwright.sync_api import sync_playwright

    records: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for lang in langs:
            (out / "pages" / lang).mkdir(parents=True, exist_ok=True)
            ctx = browser.new_context(user_agent=USER_AGENT)
            page = ctx.new_page()
            page.goto(f"{BASE_URL}/home", wait_until="domcontentloaded", timeout=60_000)
            wait_render(page, 3000)
            if lang in LANG_LINK_TEXT and not page.evaluate(SWITCH_LANG_JS, LANG_LINK_TEXT[lang]):
                log.warning("Lien de langue « %s » introuvable", LANG_LINK_TEXT[lang])
            page.wait_for_timeout(1500)
            for p in PAGES:
                url = f"{BASE_URL}{p.path}"
                try:
                    page.evaluate(SPA_NAVIGATE_JS, p.path)
                    wait_render(page)
                    if page.evaluate(EXPAND_PANELS_JS):
                        page.wait_for_timeout(800)
                    data = page.evaluate(EXTRACT_JS)
                except Exception as exc:  # noqa: BLE001 — on continue sur les autres pages
                    log.error("Échec %s [%s] : %s", url, lang, exc)
                    continue
                record = {
                    "slug": p.slug,
                    "categorie": p.categorie,
                    "langue": lang,
                    "source_url": url,
                    "titre": data["title"],
                    "blocks": data["blocks"],
                    "texte": data["text"],
                    "sha256": sha256(data["text"]),
                    "collecte_le": datetime.now(timezone.utc).isoformat(),
                }
                base = out / "pages" / lang / p.slug
                base.with_suffix(".json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                base.with_suffix(".md").write_text(blocks_to_markdown(data["title"], data["blocks"]), encoding="utf-8")
                log.info("OK %-24s [%s] %5d car. — %s", p.slug, lang, len(data["text"]), data["title"])
                records.append({k: record[k] for k in ("slug", "langue", "source_url", "sha256", "collecte_le")})
                time.sleep(POLITE_DELAY_S)
            ctx.close()
        browser.close()
    return records


def scrape_api(out: Path) -> list[dict]:
    """Télécharge les référentiels publics JSON."""
    (out / "api").mkdir(parents=True, exist_ok=True)
    records = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    for name, path in API_ENDPOINTS.items():
        url = f"{API_URL}{path}"
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.error("Échec API %s : %s", url, exc)
            continue
        (out / "api" / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("OK api/%s (%d éléments)", name, len(payload) if isinstance(payload, list) else 1)
        records.append({"nom": name, "source_url": url, "sha256": sha256(resp.text)})
        time.sleep(POLITE_DELAY_S)
    return records


def scrape_i18n(out: Path, langs: list[str]) -> list[dict]:
    """Télécharge les fichiers de libellés officiels du portail."""
    (out / "i18n").mkdir(parents=True, exist_ok=True)
    records = []
    for lang in langs:
        url = f"{BASE_URL}/assets/i18n/{lang}.json"
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("i18n %s indisponible : %s", lang, exc)
            continue
        (out / "i18n" / f"{lang}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        records.append({"langue": lang, "source_url": url, "sha256": sha256(resp.text)})
    return records


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "raw" / "cnie"))
    parser.add_argument("--langs", default="fr,ar")
    parser.add_argument("--skip-pages", action="store_true", help="API + i18n uniquement (sans navigateur)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()]

    manifest = {
        "source": BASE_URL,
        "editeur": "Direction Générale de la Sûreté Nationale (DGSN)",
        "collecte_le": datetime.now(timezone.utc).isoformat(),
        "api": scrape_api(out),
        "i18n": scrape_i18n(out, langs + ["en"]),
        "pages": [] if args.skip_pages else scrape_pages(out, langs),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Manifest écrit : %d pages, %d référentiels", len(manifest["pages"]), len(manifest["api"]))
    return 0 if manifest["pages"] or args.skip_pages else 1


if __name__ == "__main__":
    sys.exit(main())
