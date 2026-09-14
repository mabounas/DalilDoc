# Collecte des données CNIE — www.cnie.ma

## Source

Portail officiel de la Carte Nationale d'Identité Électronique, édité par la
**Direction Générale de la Sûreté Nationale (DGSN)**. Collecte du 13/09/2026.

## Pourquoi un navigateur headless

`www.cnie.ma` est une application **Angular** : le HTML servi ne contient qu'un
loader, le contenu éditorial est rendu côté client. Le scraper
([`scraper/cnie_scraper.py`](../scraper/cnie_scraper.py)) utilise donc
**Playwright (Chromium)**.

Particularités gérées :

| Constat | Solution |
|---|---|
| Langue par défaut : arabe, choix gardé en mémoire (ngx-translate) | clic JS sur « Français », puis navigation interne au routeur (`pushState`) sans rechargement |
| FAQ en `mat-expansion-panel` repliés | dépliage + lecture de `textContent` (inclut le texte masqué) |
| Le site n'atteint jamais l'état `networkidle` (analytics) | attentes fixes après rendu de `<main>` |

## Ce qui est collecté

| Type | Contenu | Sortie |
|---|---|---|
| Pages (FR + AR) | procédures (1re demande, renouvellement), droits de timbre, normes photo, à qui s'adresser, FAQ, cas particuliers, réglementation, à propos | `data/raw/cnie/pages/<lang>/<slug>.{json,md}` |
| API publique `/cnie-api` (GET) | types de demande (`NR`, `DR`), motifs de duplicata (perte, vol, détérioration), types de profession | `data/raw/cnie/api/*.json` |
| Libellés i18n | fichiers de traduction du portail (fr, ar, en) | `data/raw/cnie/i18n/*.json` |
| Manifeste | date, URL, empreinte SHA-256 de chaque ressource (détection de changements) | `data/raw/cnie/manifest.json` |

Aucune donnée personnelle n'est collectée : uniquement les pages publiques
d'information et des référentiels publics. Les formulaires (pré-demande,
suivi, RDV) ne sont jamais soumis.

## Relancer la collecte

```bash
pip install -r scraper/requirements.txt
python -m playwright install chromium
python scraper/cnie_scraper.py            # FR + AR
python scraper/cnie_scraper.py --skip-pages   # API + i18n seulement
```

Comparer ensuite les `sha256` du manifeste avec la collecte précédente : un
changement signale une page à revoir dans le back-office.

## De la collecte brute à la base de connaissances

`data/knowledge/cin.json` structure le contenu brut en **6 démarches** au
format attendu par le moteur RAG et le back-office :

| Slug | Source |
|---|---|
| `cin-premiere-demande` | /static/procedure, /static/procedure/frais-timbre, normes photo, FAQ |
| `cin-renouvellement` | /static/procedure, FAQ |
| `cin-perte-vol-deterioration` | /static/procedure, référentiel `motifduplicata`, FAQ (code PIN) |
| `cin-mineur` | /static/procedure (la page dédiée du portail est vide : « à compléter par la DGSN ») |
| `cin-cas-particuliers` | /pages/practical-informations |
| `cin-pre-demande-en-ligne` | FAQ « Utilisation du site », libellés i18n (RDV du samedi) |

Règles de structuration :

- **FR et AR** : textes officiels repris du portail (reformulation minimale pour les listes).
- **Darija, EN, PT, ES** : traductions **non officielles**, marquées comme telles
  (`traductions` en tête du fichier) — à valider dans le back-office avant
  exploitation terrain.
- Aucune information absente du portail n'est ajoutée : `delai_jours` reste
  `null` (le portail ne publie pas de délai).
