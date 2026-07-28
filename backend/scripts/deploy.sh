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
echo "[1/7] Logging in to GHCR..."
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin

# ── 2. Pull the new image ──────────────────────────────────────────────────────
# Pull once; all compose services that use ${IMAGE} share the same layers.
echo "[2/7] Pulling image: $IMAGE"
docker pull "$IMAGE"

# ── 3. Stop app containers before migrating ────────────────────────────────────
# The old api + worker hold DB connections/locks on the very tables a migration may
# need to ALTER: `ADD COLUMN` takes an ACCESS EXCLUSIVE lock on the table, and the
# agent worker in particular keeps a transaction open across slow LLM calls — so an
# otherwise-instant additive migration blocks on the table lock until the SSH step's
# command_timeout fires (this hung deploy 30290290185 for 10 min).  Stopping api +
# worker first releases those locks so migrate acquires the lock immediately.
# postgres + redis stay up (not listed → untouched), so migrate can still connect.
# `stop` on a not-yet-created service is a harmless no-op (covers the first deploy).
echo "[3/7] Stopping api + worker to release table locks..."
docker compose -f "$COMPOSE_FILE" stop api worker || true

# ── 4. Run database migrations ────────────────────────────────────────────────
# The migrate service is profile-gated ("migration") so `up -d` never starts it
# automatically.  depends_on: condition: service_healthy ensures postgres is
# ready before alembic connects.  If postgres is stopped (e.g. after a VPS
# reboot), compose starts it and waits for the healthcheck before running migrate.
echo "[4/7] Running alembic upgrade head..."
docker compose -f "$COMPOSE_FILE" --profile migration run --rm migrate

# ── 5. Bring services up (api + worker + postgres + redis) ─────────────────────
# `up -d` is idempotent: recreates containers whose image/config changed (and starts
# the api + worker we stopped in step 3), leaves unchanged containers (postgres,
# redis) untouched.  The migration profile is NOT activated here, so the migrate
# service is never started by this command.
echo "[5/7] Starting / updating services..."
docker compose -f "$COMPOSE_FILE" up -d

# ── 6. Health-check gate ───────────────────────────────────────────────────────
# Poll the API health endpoint until it returns 2xx (up to ~60s = 20 × 3s).
# A bash loop instead of `curl --retry` so we retry on ANY failure — including
# "connection reset by peer" (curl exit 56) while uvicorn is still booting, which
# `--retry`/`--retry-connrefused` do NOT cover — and stay portable across curl
# versions (curl < 7.71 has no --retry-all-errors).
echo "[6/7] Waiting for API health check..."
healthy=0
for attempt in $(seq 1 20); do
  if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  echo "  attempt $attempt/20: API not ready yet, retrying in 3s..."
  sleep 3
done
if [ "$healthy" = 1 ]; then
  echo "API is healthy."
else
  echo "ERROR: API did not become healthy in time. Last 50 log lines:" >&2
  docker compose -f "$COMPOSE_FILE" logs --tail=50 api >&2
  exit 1
fi

# ── 7. Prune dangling images ───────────────────────────────────────────────────
echo "[7/7] Pruning unused images..."
docker image prune -f

echo "========================================"
echo " Deploy complete."
echo " Running: $IMAGE"
echo "========================================"
