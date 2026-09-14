-- WathiqaDoc — schéma initial (CDC §04, PROMPT 3)
-- PostgreSQL 16 + pgvector
--
-- Types alignés sur les modèles SQLAlchemy (backend/app/db.py) :
--   identifiants UUID stockés en VARCHAR(36) (générés par gen_random_uuid()),
--   listes et contenus multilingues en JSONB.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS demarches (
  id              VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  slug            VARCHAR(100) UNIQUE NOT NULL,
  categorie       VARCHAR(50) NOT NULL,
  titre_fr        TEXT NOT NULL,
  titre_ar        TEXT,
  titre_darija    TEXT,
  titre_en        TEXT,
  titre_pt        TEXT,
  titre_es        TEXT,
  administration  VARCHAR(200),
  delai_jours     INTEGER,
  cout_mad        DECIMAL(10,2) DEFAULT 0,
  actif           BOOLEAN DEFAULT TRUE,
  statut          VARCHAR(20) NOT NULL DEFAULT 'brouillon'
                  CHECK (statut IN ('brouillon','review','valide','production','inactif')),
  version         INTEGER DEFAULT 1,
  source_url      TEXT,
  valide_par      VARCHAR(100),
  contenu         JSONB NOT NULL DEFAULT '{}'::jsonb,   -- conditions, exceptions, tarifs, faq (multilingue)
  cree_le         TIMESTAMPTZ DEFAULT NOW(),
  mis_a_jour_le   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents_requis (
  id          VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  demarche_id VARCHAR(36) REFERENCES demarches(id) ON DELETE CASCADE,
  ordre       SMALLINT NOT NULL,
  nom_fr      TEXT NOT NULL,
  nom_ar      TEXT,
  nom_darija  TEXT,
  nom_en      TEXT,
  nom_pt      TEXT,
  nom_es      TEXT,
  obligatoire BOOLEAN DEFAULT TRUE,
  condition   TEXT,
  format      JSONB DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS documents_requis_demarche_idx ON documents_requis (demarche_id, ordre);

CREATE TABLE IF NOT EXISTS chunks (
  id              VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  demarche_id     VARCHAR(36) REFERENCES demarches(id) ON DELETE CASCADE,
  type_chunk      VARCHAR(50) NOT NULL,
  langue          VARCHAR(10) NOT NULL,
  contenu         TEXT NOT NULL,
  embedding       vector(1536),
  tokens_count    INTEGER,
  version         INTEGER DEFAULT 1,
  source_url      TEXT,
  cree_le         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_langue_idx ON chunks (langue);

CREATE TABLE IF NOT EXISTS historique_interactions (
  id              VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  session_id      VARCHAR(36) NOT NULL,
  borne_id        VARCHAR(50),
  requete_texte   TEXT,                -- expurgé des données personnelles avant écriture
  langue_detectee VARCHAR(10),
  demarche_id     VARCHAR(100),        -- slug de la démarche (historique conservé même si elle est supprimée)
  chunks_utilises JSONB,
  score_confiance FLOAT,
  hors_perimetre  BOOLEAN DEFAULT FALSE,
  temps_ms        INTEGER,
  cree_le         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS historique_cree_le_idx ON historique_interactions (cree_le);

CREATE TABLE IF NOT EXISTS admin_users (
  id            VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  email         VARCHAR(200) UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role          VARCHAR(20) DEFAULT 'editor' CHECK (role IN ('editor','reviewer','super-admin')),
  totp_secret   TEXT,
  cree_le       TIMESTAMPTZ DEFAULT NOW()
);

-- Versionnement (CDC §09) : instantané complet de chaque version.
CREATE TABLE IF NOT EXISTS demarches_versions (
  id           VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  demarche_id  VARCHAR(36) REFERENCES demarches(id) ON DELETE CASCADE,
  version      INTEGER NOT NULL,
  snapshot     JSONB NOT NULL,
  publiee      BOOLEAN NOT NULL DEFAULT FALSE,   -- la borne sert la dernière version publiée
  auteur       VARCHAR(200),
  cree_le      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (demarche_id, version)
);

-- Journal d'accès admin (CDC §10).
CREATE TABLE IF NOT EXISTS admin_access_logs (
  id        SERIAL PRIMARY KEY,
  email     VARCHAR(200),
  action    VARCHAR(100) NOT NULL,
  cible     TEXT,
  ip_hash   VARCHAR(64),
  cree_le   TIMESTAMPTZ DEFAULT NOW()
);
