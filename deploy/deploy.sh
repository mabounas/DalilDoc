#!/usr/bin/env bash
# Déploiement WathiqaDoc sur un VPS Ubuntu (Docker Compose).
#
#   curl -fsSLo deploy.sh https://raw.githubusercontent.com/mabounas/DalilDoc/main/deploy/deploy.sh
#   bash deploy.sh
#   (pas de « curl | bash » : sudo doit pouvoir demander le mot de passe sur le terminal)
#
# Variables optionnelles : API_PORT, BORNE_PORT, ADMIN_PORT, BIND_ADDR, APP_DIR, BRANCH
#
# Conçu pour un serveur partagé : aucun nettoyage Docker global, ports liés à 127.0.0.1,
# builds séquentiels (RAM), aucune modification de nginx ni du pare-feu.
#
# Idempotent : relancer le script met à jour le code et reconstruit les conteneurs.
# Les secrets (.env) sont générés au premier lancement puis conservés.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/mabounas/DalilDoc.git}"
APP_DIR="${APP_DIR:-/opt/wathiqadoc}"
BRANCH="${BRANCH:-main}"
API_PORT="${API_PORT:-8100}"; BORNE_PORT="${BORNE_PORT:-3100}"; ADMIN_PORT="${ADMIN_PORT:-3101}"
BIND_ADDR="${BIND_ADDR:-127.0.0.1}"

log() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }

log "1/6 Prérequis (git, curl, Docker)"
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl git
  curl -fsSL https://get.docker.com | sudo sh
fi
if ! docker compose version >/dev/null 2>&1; then
  sudo apt-get install -y docker-compose-plugin || sudo apt-get install -y docker-compose-v2
fi
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then DOCKER="sudo docker"; fi

log "2/6 Espace disque"
df -h / | tail -1
AVAIL_KB=$(df -Pk / | awk 'NR==2 {print $4}')
if [ "$AVAIL_KB" -lt 4000000 ]; then
  # Pas de « docker system prune » : il supprimerait les images d'autres projets du serveur.
  echo "✖ Moins de 4 Go libres : libérez de l'espace (ex. docker builder prune) puis relancez."; exit 1
fi

log "3/6 Code source ($BRANCH) dans $APP_DIR"
# Le dépôt appartient à l'utilisateur courant : git sans sudo (évite « dubious ownership »).
sudo mkdir -p "$APP_DIR"
sudo chown "$(id -u):$(id -g)" "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

log "4/6 Configuration (.env)"
if [ ! -f .env ]; then
  rand() { openssl rand -hex "$1"; }
  ADMIN_PASSWORD="$(rand 12)"
  cp .env.example .env
  sed -i \
    -e "s|^DB_PASSWORD=.*|DB_PASSWORD=$(rand 24)|" \
    -e "s|^JWT_SECRET=.*|JWT_SECRET=$(rand 32)|" \
    -e "s|^ADMIN_BOOTSTRAP_PASSWORD=.*|ADMIN_BOOTSTRAP_PASSWORD=${ADMIN_PASSWORD}|" \
    -e "s|^DATABASE_URL=.*|# DATABASE_URL défini par docker-compose|" \
    .env
  cat >> .env <<EOF

# ── Déploiement VPS ──
API_PORT=${API_PORT}
BORNE_PORT=${BORNE_PORT}
ADMIN_PORT=${ADMIN_PORT}
BIND_ADDR=${BIND_ADDR}
# Vide : la borne et l'admin appellent l'API en relatif (/api) via leur propre proxy.
PUBLIC_API_URL=
BORNE_ID=borne-01
EOF
  chmod 600 .env
  echo "Identifiants back-office (à noter, affichés une seule fois) :"
  echo "  e-mail       : $(grep ^ADMIN_BOOTSTRAP_EMAIL .env | cut -d= -f2)"
  echo "  mot de passe : ${ADMIN_PASSWORD}"
else
  echo ".env existant conservé."
fi

set -a; . ./.env; set +a
for port in "$API_PORT" "$BORNE_PORT" "$ADMIN_PORT"; do
  if ss -ltn "sport = :$port" | grep -q LISTEN && ! $DOCKER compose ps --format '{{.Ports}}' 2>/dev/null | grep -q ":$port->"; then
    echo "✖ Le port $port est déjà utilisé sur ce serveur. Relancez avec API_PORT/BORNE_PORT/ADMIN_PORT (supprimez .env pour régénérer)."; exit 1
  fi
done

log "5/6 Build (séquentiel, pour ménager la RAM) & démarrage"
for svc in api frontend admin; do
  $DOCKER compose build "$svc"
done
$DOCKER compose up -d --remove-orphans

log "6/6 Vérification"
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${API_PORT}/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 4
done
curl -fsS "http://localhost:${API_PORT}/api/v1/health" && echo
$DOCKER compose ps

# Une clé renseignée commence par un caractère non blanc (les lignes vides portent un commentaire).
if grep -qE '^OPENAI_API_KEY=[^[:space:]#]' .env && grep -qE '^ANTHROPIC_API_KEY=[^[:space:]#]' .env; then
  $DOCKER compose exec -T api python -m scripts.index_vectors || echo "⚠ Indexation vectorielle échouée (voir logs api)"
fi

cat <<EOF

✅ WathiqaDoc déployé (écoute locale ${BIND_ADDR})
   Borne        : http://${BIND_ADDR}:${BORNE_PORT}
   Back-office  : http://${BIND_ADDR}:${ADMIN_PORT}
   API (docs)   : http://${BIND_ADDR}:${API_PORT}/docs
Accès public : ajoutez un vhost nginx (proxy_pass vers ces ports) + certbot.
Sans clés API, le moteur tourne en mode local (recherche lexicale + réponse extractive).
Ajoutez les clés dans $APP_DIR/.env puis relancez ce script pour activer Whisper/Claude/ElevenLabs.
EOF
