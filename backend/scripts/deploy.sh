#!/usr/bin/env bash
# deploy.sh — idempotent VPS deploy script for the ai-assistant backend.
#
# Called by the GitHub Actions SSH step with the SHA-pinned image as $1.
# Can also be run manually on the VPS for rollback:
#
#   IMAGE=ghcr.io/ryan1712/ai-assistant:<sha> GHCR_TOKEN=<pat> ACTOR=<ghuser> \
#     bash deploy.sh ghcr.io/ryan1712/ai-assistant:<sha>
#
# Required env vars (set by the GHA SSH step):
#   GHCR_TOKEN  — GITHUB_TOKEN forwarded from workflow (or a read:packages PAT)
#   ACTOR       — GitHub username used to authenticate with GHCR
#
# Usage:
#   bash deploy.sh [IMAGE]
#   IMAGE defaults to ghcr.io/ryan1712/ai-assistant:latest if omitted.

set -euo pipefail

# ── Mutex: prevent two deploys running concurrently on the same host ──────────
# flock -n exits immediately (exit 1) if the lock is held by another process.
exec 9>/tmp/deploy-ai-assistant.lock
flock -n 9 || { echo "ERROR: another deploy is already in progress — aborting." >&2; exit 1; }

# Clean up gracefully if the script is interrupted mid-flight.
trap 'echo "Deploy interrupted." >&2; exit 130' HUP INT TERM

export IMAGE="${1:-ghcr.io/ryan1712/ai-assistant:latest}"
COMPOSE_FILE="docker-compose.prod.yml"
HEALTH_URL="http://127.0.0.1:8010/api/v1/health"

echo "========================================"
echo " ai-assistant backend deploy"
echo " Image : $IMAGE"
echo " Time  : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================"

# ── 1. Authenticate with GHCR ─────────────────────────────────────────────────
echo "[1/6] Logging in to GHCR..."
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin

# ── 2. Pull the new image ──────────────────────────────────────────────────────
# Pull once; all compose services that use ${IMAGE} share the same layers.
echo "[2/6] Pulling image: $IMAGE"
docker pull "$IMAGE"

# ── 3. Run database migrations ────────────────────────────────────────────────
# The migrate service is profile-gated ("migration") so `up -d` never starts it
# automatically.  depends_on: condition: service_healthy ensures postgres is
# ready before alembic connects.  If postgres is stopped (e.g. after a VPS
# reboot), compose starts it and waits for the healthcheck before running migrate.
echo "[3/6] Running alembic upgrade head..."
docker compose -f "$COMPOSE_FILE" --profile migration run --rm migrate

# ── 4. Bring services up (api + worker + postgres + redis) ─────────────────────
# `up -d` is idempotent: recreates containers whose image/config changed, leaves
# unchanged containers (postgres, redis) untouched.  The migration profile is NOT
# activated here, so the migrate service is never started by this command.
echo "[4/6] Starting / updating services..."
docker compose -f "$COMPOSE_FILE" up -d

# ── 5. Health-check gate ───────────────────────────────────────────────────────
# Poll the API health endpoint for up to ~30 s (10 retries × 3 s delay).
# If the api container fails to come up, print recent logs and fail the deploy.
echo "[5/6] Waiting for API health check..."
if curl --fail --silent --show-error \
        --retry 10 --retry-delay 3 --retry-connrefused \
        "$HEALTH_URL"; then
  echo ""
  echo "API is healthy."
else
  echo ""
  echo "ERROR: API did not become healthy in time. Last 50 log lines:" >&2
  docker compose -f "$COMPOSE_FILE" logs --tail=50 api >&2
  exit 1
fi

# ── 6. Prune dangling images ───────────────────────────────────────────────────
echo "[6/6] Pruning unused images..."
docker image prune -f

echo "========================================"
echo " Deploy complete."
echo " Running: $IMAGE"
echo "========================================"
