#!/usr/bin/env bash
# Slow Mo API — production deploy (pull GHCR image or build locally)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env)
DOCKER=(docker)

if [ ! -f .env ]; then
  echo "Missing .env — copy from .env.prod.example and fill secrets before deploy."
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if ! docker info >/dev/null 2>&1; then
  COMPOSE=(sudo docker compose -f docker-compose.prod.yml --env-file .env)
  DOCKER=(sudo docker)
fi

ghcr_login() {
  user="${GHCR_USERNAME:-}"
  token="${GHCR_TOKEN:-${GHCR_PULL_TOKEN:-}}"
  if [ -z "$user" ] || [ -z "$token" ]; then
    echo "GHCR_USERNAME / GHCR_TOKEN not set — skipping docker login."
    echo "For private GHCR pulls, add a GitHub PAT (read:packages) to .env."
    return 0
  fi
  echo "Logging in to ghcr.io as ${user}..."
  echo "${token}" | "${DOCKER[@]}" login ghcr.io -u "${user}" --password-stdin
}

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required (Neon Postgres connection string)."
  exit 1
fi

if [ "${DEPLOY_BUILD_LOCAL:-0}" = "1" ]; then
  echo "Building API image locally..."
  "${COMPOSE[@]}" build --pull
  echo "Starting API (recreate)..."
  "${COMPOSE[@]}" up -d --force-recreate --remove-orphans
else
  ghcr_login
  echo "Image ref: ${SLOWMO_API_IMAGE:-"(unset)"}"
  echo "Pulling image from registry..."
  "${COMPOSE[@]}" pull
  echo "Starting API (recreate so new digests are used)..."
  "${COMPOSE[@]}" up -d --force-recreate --remove-orphans
fi

echo "Status:"
"${COMPOSE[@]}" ps
echo
"${DOCKER[@]}" image inspect "${SLOWMO_API_IMAGE:-slowmo-api:prod}" \
  --format '{{.Id}} {{index .RepoDigests 0}}' 2>/dev/null || true
