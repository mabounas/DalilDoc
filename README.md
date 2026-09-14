# WathiqaDoc · وثيقة دوك

Agent IA civique pour bornes citoyennes au Maroc : le citoyen demande, à la voix
ou au clavier, **quels documents fournir** pour sa démarche — en darija, arabe,
français, anglais, portugais ou espagnol. Architecture RAG « zéro hallucination » :
les réponses proviennent uniquement de la base de connaissances validée.

**Phase 1 livrée : Carte Nationale d'Identité Électronique (CNIE)**, données
collectées sur le portail officiel [www.cnie.ma](https://www.cnie.ma) (DGSN).

## Structure du monorepo

```
├── scraper/     Collecte Playwright de www.cnie.ma (pages FR/AR, API publique, i18n)
├── data/
│   ├── raw/cnie/        Données brutes horodatées + manifeste SHA-256
│   └── knowledge/       Base de connaissances structurée (cin.json, 6 démarches × 6 langues)
├── rag/         Moteur RAG : chunking, langdetect (darija), retrieval, génération Claude
├── backend/     API FastAPI (borne + back-office JWT), tests pytest
├── frontend/    Borne Next.js 14 (kiosque, voix, clavier RTL, hors ligne), tests Jest
├── admin/       Back-office Vite + React (workflow, versions, analytics)
├── db/          Migrations PostgreSQL + pgvector
├── docs/        Documentation (collecte, architecture)
└── docker-compose.yml
```

## Démarrage rapide (sans clé API)

Le moteur fonctionne entièrement **en local** sans clé : recherche TF-IDF
multilingue + réponse extractive tirée de la base (mode borne hors ligne).

```bash
# API (http://localhost:8000/docs)
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env        # ADMIN_BOOTSTRAP_* pour le premier compte
uvicorn app.main:app --reload
```

```bash
# Borne (http://localhost:3000)
cd frontend && npm install && npm run dev
```

```bash
# Back-office (http://localhost:3001)
cd admin && npm install && npm run dev
```

Au premier lancement, l'API crée le schéma (SQLite par défaut), le super-admin
initial, et importe `data/knowledge/cin.json`.

## Mode production (clés API)

Avec `OPENAI_API_KEY` et `ANTHROPIC_API_KEY` renseignées (`RAG_MODE=auto`) :

| Étape | Service |
|---|---|
| STT | Whisper (OpenAI) + détection darija/MSA |
| Embeddings | `text-embedding-3-small` → Qdrant (repli pgvector) |
| Génération | Claude Sonnet 5 (`LLM_MODEL`), 250 tokens max, repli extractif si erreur ou réponse tronquée |
| TTS | ElevenLabs `eleven_multilingual_v2` (repli synthèse du navigateur) |

```bash
cp .env.example .env   # renseigner clés, DB_PASSWORD, JWT_SECRET
docker compose up -d --build
docker compose exec api python -m scripts.index_vectors   # indexation Qdrant
```

## API

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/v1/query` | question → langue → RAG → réponse + documents + score |
| POST | `/api/v1/voice/transcribe` | audio base64 → texte + langue |
| POST | `/api/v1/voice/synthesize` | texte → audio MP3 base64 |
| GET | `/api/v1/demarches` · `/api/v1/demarches/{slug}` | démarches publiées |
| GET | `/api/v1/offline-cache` | paquet hors ligne de la borne |
| GET | `/api/v1/health` | état DB / RAG / Qdrant / Redis |
| POST | `/api/admin/auth/login` · `/auth/refresh` | JWT 8 h + refresh 7 j (2FA super-admin) |
| GET/POST/PUT | `/api/admin/demarches[/{id}]` | CRUD (chaque enregistrement = nouvelle version) |
| POST | `/api/admin/demarches/{id}/submit` · `/publish` · `/deactivate` · `/rollback/{v}` | workflow |
| GET | `/api/admin/analytics` · `/api/admin/interactions` | statistiques anonymisées |

## Tests

```bash
cd backend && python -m pytest -q     # 29 tests : RAG, routage, API, RGPD, workflow
cd frontend && npx jest               # composants borne + mode hors ligne
```

## Sécurité & RGPD

- Audio jamais stocké (libéré après transcription) ; texte journalisé expurgé (n° CIN, téléphones, e-mails, dates).
- Session = UUID anonyme en mémoire côté borne, aucun cookie persistant.
- Rate limiting : 30 requêtes/min et 5 transcriptions/min par borne (Redis, repli mémoire).
- Mots de passe PBKDF2-SHA256, JWT, TOTP pour super-admin, journal d'accès admin (IP hachée).

## Sources & traductions

Voir [docs/SCRAPING.md](docs/SCRAPING.md). Les textes FR/AR proviennent du portail
officiel ; les versions darija/EN/PT/ES sont des traductions **non officielles**
à valider dans le back-office.
