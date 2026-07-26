# Backend Deployment Runbook

Production CI/CD for the `ai-assistant` backend.
Repo: `Ryan1712/ai-assistant` | Registry: `ghcr.io/ryan1712/ai-assistant`

---

## Table of Contents
1. [How a deploy runs](#how-a-deploy-runs)
2. [GitHub Secrets to create](#github-secrets-to-create)
3. [GHCR pull auth](#ghcr-pull-auth)
4. [Action pinning and Dependabot](#action-pinning-and-dependabot)
5. [One-time VPS setup](#one-time-vps-setup)
6. [Rollback](#rollback)
7. [Assumptions and out-of-scope](#assumptions-and-out-of-scope)

---

## How a deploy runs

```
git push origin main
       │
       ▼
GitHub Actions: deploy.yml
       │
       ├─ [job: test]          pytest tests/ -v  ← hard gate; failure stops everything
       │
       ├─ [job: build-and-push]  (permissions: packages:write)
       │       docker build backend/  (multi-layer GHA cache)
       │       docker push ghcr.io/ryan1712/ai-assistant:latest
       │       docker push ghcr.io/ryan1712/ai-assistant:<commit-sha>
       │
       └─ [job: deploy]  (permissions: packages:read only)
               scp backend/docker-compose.prod.yml → VPS:$VPS_APP_DIR/
               scp backend/scripts/deploy.sh      → VPS:$VPS_APP_DIR/
               ssh VPS → cd $VPS_APP_DIR && bash deploy.sh <sha-image>
                       │
                       ├─ flock mutex (prevents concurrent deploys)
                       ├─ docker login ghcr.io (ephemeral GITHUB_TOKEN)
                       ├─ docker pull <sha-image>
                       ├─ docker compose --profile migration run --rm migrate
                       │     └─ alembic upgrade head (profile-gated one-shot)
                       ├─ docker compose up -d  (migrate NOT started — profile-gated)
                       ├─ curl http://127.0.0.1:8010/api/v1/health  ← health gate
                       │     └─ on failure: print api logs, exit 1 → GHA job goes red
                       └─ docker image prune -f
```

The `ci.yml` workflow covers PRs and feature branches (test only, no build/push/deploy).

---

## GitHub Secrets to create

Go to `https://github.com/Ryan1712/ai-assistant/settings/secrets/actions` and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `VPS_HOST` | Yes | IP address or hostname of the VPS (e.g. `203.0.113.10`) |
| `VPS_USER` | Yes | SSH username on the VPS (e.g. `deploy` or `ubuntu`) |
| `VPS_SSH_KEY` | Yes | Private key (PEM/OpenSSH) whose public key is in `~/.ssh/authorized_keys` on VPS |
| `VPS_APP_DIR` | Yes | Absolute path where files are deployed (e.g. `/opt/ai-assistant`) |
| `VPS_PORT` | No | SSH port; omit to use the default `22` |

**No secret is needed to push to GHCR.** The built-in `GITHUB_TOKEN` has `packages: write`
scoped to the `build-and-push` job only, and is used automatically by `docker/login-action`.

---

## GHCR pull auth

The workflow forwards the ephemeral `GITHUB_TOKEN` to the VPS SSH step as `GHCR_TOKEN`.
`deploy.sh` uses it to authenticate before pulling:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin
```

This token is valid for the duration of the workflow run only (minutes). It requires the
GHCR package to be **private** (the default) and linked to the repo.

**Fallback options if the ephemeral token approach is insufficient:**

Option A — Long-lived PAT (personal access token):
1. Create a GitHub PAT at `https://github.com/settings/tokens` with scope `read:packages`.
2. Add it as repository secret `GHCR_PAT`.
3. In `deploy.sh`, replace `$GHCR_TOKEN` / `$ACTOR` with the PAT and `ryan1712`:
   ```bash
   echo "$GHCR_PAT" | docker login ghcr.io -u ryan1712 --password-stdin
   ```
4. Add `GHCR_PAT` to the `envs:` list in `deploy.yml`'s SSH step.

Option B — Make the GHCR package public:
Go to the package settings on GitHub and set visibility to **Public**. No auth needed on
the VPS for `docker pull`. Only choose this if the image contains no secrets (it should not).

---

## Action pinning and Dependabot

Third-party actions that handle the SSH private key (`appleboy/ssh-action` and
`appleboy/scp-action`) are pinned to immutable commit SHAs in `deploy.yml`, with
a trailing comment showing the human-readable tag:

```yaml
uses: appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2  # v1
uses: appleboy/scp-action@917f8b81dfc1ccd331fef9e2d61bdc6c8be94634  # v0.1.7
```

SHA-pinning prevents a compromised tag from exfiltrating `VPS_SSH_KEY`. Docker
official actions (`docker/*`) and `actions/*` are on major-version tags, which
is acceptable because they are maintained by Docker Inc. and GitHub respectively.

`.github/dependabot.yml` is configured with the `github-actions` ecosystem on a
weekly schedule. Dependabot opens PRs that bump the SHA pins when new versions of
the appleboy actions are released, so the pins stay current without manual tracking.

---

## One-time VPS setup

Run these commands once on a fresh VPS. After this, every `git push origin main`
handles everything automatically.

### 1. Install Docker with the Compose plugin

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker          # apply group without logout
docker compose version # must print v2.x
```

### 2. Create the app directory

```bash
sudo mkdir -p /opt/ai-assistant
sudo chown "$USER":"$USER" /opt/ai-assistant
```

Replace `/opt/ai-assistant` with whatever you set as `VPS_APP_DIR`.

### 3. Place the production .env

```bash
cd /opt/ai-assistant
# copy from repo, then edit with real values:
cp /path/to/your/.env.example .env
```

Edit `.env` with real values. **Critical production differences from `.env.example`:**

```bash
# Postgres password — must match POSTGRES_PASSWORD below
POSTGRES_PASSWORD=<strong-random-password>   # e.g. openssl rand -hex 32

# DATABASE_URL: use Docker service name "postgres" as host, NOT "localhost"
# Password must match POSTGRES_PASSWORD above
DATABASE_URL=postgresql+asyncpg://app:<strong-random-password>@postgres:5432/app

# Strong JWT secret
JWT_SECRET=<openssl rand -hex 32>

# Real Anthropic key
ANTHROPIC_API_KEY=sk-ant-...

# Redis: use Docker service name, NOT localhost
REDIS_URL=redis://redis:6379
```

**Never commit `.env` to git.** It is in `.gitignore`.

### 4. Bootstrap the database (first deploy only)

On the very first deploy, `docker-compose.prod.yml` and `deploy.sh` do not yet exist on
the VPS — copy them manually for the initial bootstrap, then let CI take over from there:

```bash
scp backend/docker-compose.prod.yml deploy@<VPS_HOST>:/opt/ai-assistant/
scp backend/scripts/deploy.sh       deploy@<VPS_HOST>:/opt/ai-assistant/

ssh deploy@<VPS_HOST>
cd /opt/ai-assistant

# Start postgres first so alembic can connect; wait for healthcheck
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml ps  # confirm postgres healthy

# Login to GHCR (use a PAT with read:packages for this one-time step)
echo "<PAT>" | docker login ghcr.io -u ryan1712 --password-stdin

# Pull image and run migrations (profile-gated one-shot service)
IMAGE=ghcr.io/ryan1712/ai-assistant:latest \
  docker compose -f docker-compose.prod.yml --profile migration run --rm migrate

# Start all services (migrate NOT started — profile-gated)
IMAGE=ghcr.io/ryan1712/ai-assistant:latest \
  docker compose -f docker-compose.prod.yml up -d

# Verify API is healthy
curl http://127.0.0.1:8010/api/v1/health
```

After this first bootstrap, every subsequent deploy is fully automated via GitHub Actions.

### 5. Add the deploy SSH key

Generate a dedicated key pair (do NOT reuse your personal key):

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/deploy_key -N ""
```

- Append `~/.ssh/deploy_key.pub` to `~/.ssh/authorized_keys` on the VPS.
- Add the contents of `~/.ssh/deploy_key` (private key) as the `VPS_SSH_KEY` GitHub secret.

---

## Rollback

Every successful deploy pushes two tags to GHCR:
- `latest` — always points to the most recent main commit
- `<commit-sha>` — pinned, immutable, used for rollback

**Rollback procedure:**

Option A — Re-run the workflow at the target commit:
1. Go to `Actions` → `Deploy` in the GitHub UI.
2. Find the workflow run for the commit you want to restore.
3. Click "Re-run all jobs".

Option B — Manual SSH rollback (fastest):

```bash
ssh deploy@<VPS_HOST>
cd /opt/ai-assistant

export GHCR_TOKEN=<read:packages PAT>
export ACTOR=ryan1712
export IMAGE=ghcr.io/ryan1712/ai-assistant:<target-sha>

bash deploy.sh "$IMAGE"
```

This re-runs migrations (idempotent if no schema changes since that commit), restarts
api + worker with the pinned image, and verifies the health endpoint before finishing.

---

## Assumptions and out-of-scope

| Topic | Decision |
|-------|----------|
| Reverse proxy / TLS | Out of scope. A Caddy or Nginx proxy in front of `127.0.0.1:8010` handles HTTPS termination. The `ports:` binding in compose intentionally listens on loopback only. |
| Health endpoint | `GET /api/v1/health` on port 8010. deploy.sh polls this after `up -d`; failure triggers a log dump and exits 1 (GHA deploy job goes red). |
| Database backups | Out of scope. Add `pgdump` cron or use managed Postgres if this is critical. |
| Multi-region / multi-VPS | Out of scope. This pipeline deploys to a single VPS. |
| GHCR package visibility | Defaults to **private** (linked to repo). Collaborators with repo access can pull. Use the PAT fallback or make it public if needed. |
| Alembic async driver | `env.py` uses `asyncpg` wrapped in `asyncio.run()`. The `alembic upgrade head` CLI command is fully compatible — no special flags needed. The `DATABASE_URL` must use `postgresql+asyncpg://` scheme and `postgres` as the hostname (Docker service name). |
| Migration profile gate | The `migrate` service has `profiles: ["migration"]`. `docker compose up -d` never starts it automatically. The controlled invocation is `docker compose --profile migration run --rm migrate`. |
| Non-root Docker user | The current `backend/Dockerfile` runs as root inside the container. Recommended improvement: add a non-root user before `CMD`. |
| Concurrent deploy protection | `deploy.sh` acquires a `flock` lock on `/tmp/deploy-ai-assistant.lock`. A second concurrent invocation on the same host exits immediately with an error rather than racing. |
