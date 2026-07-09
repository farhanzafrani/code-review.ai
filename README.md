# AI Code Review & DevOps Assistant

See [`INSTRUCTIONS.md`](INSTRUCTIONS.md) for the project objective and the
full phased implementation plan. This README covers day-to-day setup for
what's built so far (Phase 0 + 1: backend skeleton, auth, webhook intake;
Phase 2: AI review of the PR diff, posted back to GitHub; Phase 3: Next.js
dashboard for logging in, connecting repos, and watching reviews land;
Phase 4: security findings, on-demand test/doc generation, and a Qdrant-
backed RAG pass so reviews see more than just the raw diff; Phase 5:
optional SonarQube static analysis merged into the same PR comment; Phase
6: CI on every PR, Docker images published to GHCR on merge, and a Helm
chart for deploying the platform itself to a local kind cluster; Phase 7:
structured JSON logging, Prometheus metrics, live pipeline logs on the PR
detail page, and in-app/Slack notifications when a review finishes;
Phase 8: rate limiting, a secrets audit that found and fixed two real
token leaks (see `SECURITY.md`), a burst-load test script, and CPU-based
autoscaling for the worker in Kubernetes).

## Status

All 8 phases in `INSTRUCTIONS.md` are complete (the one intentional
exception: the Phase 4 local-LLM/Ollama stretch goal, explicitly scoped as
optional and never required). Every claim has been checked against
something real where this environment allows it — real docker-compose
stacks, real kind clusters, a real burst-load run — not just mocked tests;
several of those checks caught and fixed genuine bugs rather than just
confirming things worked.

What hasn't been exercised, and can't be from a sandbox: a live GitHub
App + real OpenAI key reviewing an actual PR end-to-end (the Phase 2 "v1
milestone" is only verified via mocks/local infra so far), ingress-nginx
routing through real DNS, and Slack/GHCR delivery against real
credentials. Standing up a real GitHub App and opening a real PR against
a connected repo is the one remaining step no amount of further local
work substitutes for.

## Layout

```
apps/backend/    FastAPI app + Celery worker
apps/frontend/   Next.js dashboard (TypeScript, Tailwind, shadcn/ui)
infra/docker/    docker-compose.yml for local dev
infra/k8s/       Helm chart + kind config to deploy this platform itself
infra/terraform/ deferred — see infra/terraform/README.md
.github/workflows/  CI (lint+test on PR) and image publish (on merge to main)
```

## 1. Create a GitHub App

Phase 1 uses a GitHub App for both "Sign in with GitHub" and repo webhooks.

1. Go to **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Homepage URL: `http://localhost:3000` (placeholder until Phase 3).
3. **Callback URL**: `http://localhost:8000/auth/github/callback`, and check
   *"Request user authorization (OAuth) during installation"* — this gives
   the app a Client ID/Secret for the login flow, in addition to its App ID.
4. **Webhook URL**: wherever this backend is reachable from the internet
   (see the tunnel note below for local dev). Set a **Webhook secret** —
   generate one with `openssl rand -hex 32`.
5. **Permissions**: Repository → *Pull requests*: Read & write. *Contents*:
   Read-only.
6. **Subscribe to events**: Pull request.
7. Create the app, then generate and download a **private key** (`.pem`).
8. Install the app on a test repository.

Fill in `.env` (copy from `.env.example`):

- `GITHUB_APP_ID` — shown on the app's settings page.
- `GITHUB_APP_CLIENT_ID` / `GITHUB_APP_CLIENT_SECRET` — from the same page.
- `GITHUB_APP_PRIVATE_KEY_PATH` — path to the downloaded `.pem` (mount it
  into the container; don't commit it — it's gitignored via `*.pem`).
- `GITHUB_APP_WEBHOOK_SECRET` — the secret you set in step 4.
- `JWT_SECRET` — any random string for signing this app's own session JWTs.

### Exposing your local backend for webhooks

GitHub needs to reach your webhook URL, so for local dev use a tunnel, e.g.:

```
ngrok http 8000
```

Then set the GitHub App's Webhook URL to `<ngrok-url>/webhooks/github`.

## 2. Set up OpenAI

Phase 2 calls OpenAI to review the diff. Fill in `.env`:

- `OPENAI_API_KEY` — from https://platform.openai.com/api-keys.
- `OPENAI_MODEL` — defaults to `gpt-4o-mini`; any model that supports
  [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
  works.
- `MAX_DIFF_CHARS` — diffs longer than this are truncated before being sent
  to the model (defaults to 30,000).

Phase 4 also uses OpenAI for embeddings (`EMBEDDING_MODEL`, defaults to
`text-embedding-3-small`) — no extra key needed, same `OPENAI_API_KEY`.

## 3. (Optional) Set up SonarQube

Off by default (`SONARQUBE_ENABLED=false`) — unlike everything else in this
app, this integration shells out to `git` and `sonar-scanner` against a
real checkout of the PR and needs a running SonarQube instance, so it's a
heavier local dependency. Skip this section unless you specifically want
quality-gate results merged into the PR comment.

1. Start it: `docker compose -f infra/docker/docker-compose.yml --profile sonarqube up -d sonarqube`
   (needs ~2GB+ RAM; first boot takes a minute or two). On Linux you may
   need to raise `vm.max_map_count` first: `sudo sysctl -w vm.max_map_count=262144`.
2. Open `http://localhost:9000`, log in with `admin` / `admin`, and set a
   new password when prompted.
3. **My Account → Security → Generate Token** (a "Global Analysis Token"
   is fine — it needs permission to create projects, which the admin
   account has by default).
4. In `.env`: set `SONARQUBE_ENABLED=true` and `SONARQUBE_TOKEN` to that
   token. `SONARQUBE_URL` already defaults to `http://sonarqube:9000` to
   match the compose network.
5. Restart the `backend`/`worker` containers.

There's no manual per-repo setup — the worker creates a SonarQube project
per connected repo on first scan (key: `codereviewai_{repository_id}`).

## 4. Run it

With Docker available:

```
cp .env.example .env   # then fill in the GitHub/OpenAI values above
docker compose -f infra/docker/docker-compose.yml up --build
```

This starts Postgres, Redis, Qdrant, the FastAPI backend (with `alembic
upgrade head` run automatically on boot), a Celery worker, and the Next.js
frontend on `http://localhost:3000`.

Without Docker:

```
# backend
cd apps/backend
uv sync
cp ../../.env.example .env   # adjust DATABASE_URL/REDIS_URL to localhost
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# in another terminal:
uv run celery -A app.workers.celery_app worker --loglevel=info

# frontend (in another terminal)
cd apps/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

## 5. Try it

- Open `http://localhost:3000` → **Sign in with GitHub** → you land on
  `/dashboard`.
- Click **Connect a repo** (only shown once `NEXT_PUBLIC_GITHUB_APP_SLUG`
  is set in `apps/frontend/.env.local`) to install the GitHub App, or just
  install it directly from the app's GitHub settings page.
- Open the repo from the dashboard to see its PRs and review status
  (Pending → Reviewing… → Reviewed/Failed, polling automatically).
- Click into a PR to see the AI summary, per-bug findings, and the diff.
- Opening/pushing to a PR on a connected repo creates a `PullRequest` +
  `Review` row, fires a Celery task, and within a minute or two a real AI
  review comment appears both on GitHub and on the dashboard — now
  including a **Security** section alongside **Bugs**. Check worker logs
  if it doesn't show up — the task marks the `Review` row `failed` with an
  error message on any GitHub/OpenAI error instead of raising.
- Installing the app on a repo also queues a one-time background index of
  its default branch into Qdrant (best-effort — logged, not retried).
  Later reviews on that repo retrieve relevant existing code as extra
  context beyond the diff. Indexing does **not** re-run on every push, so
  it can drift from the repo's current state; re-trigger manually if
  needed (see note below).
- On a PR's detail page, click **Generate** under **Unit tests** or
  **Documentation** to get an on-demand, synchronous LLM pass over that
  PR's diff — not persisted, not posted to GitHub, just shown in the UI.
- If `SONARQUBE_ENABLED=true`, every PR also gets a Sonar scan running
  alongside the AI review. Whichever finishes first posts the PR comment;
  the other edits that same comment in place when it finishes, so you get
  one unified comment instead of two — see the **SonarQube** card and the
  quality gate badge on the PR detail page. A failed quality gate is a
  normal scan result, not an error — it's recorded and shown just like a
  passing one.
- While a review is pending/running, the PR detail page shows a **Pipeline
  logs** panel with the worker's step-by-step progress (fetching the diff,
  running the AI review, running Sonar, posting the comment) — polled from
  Redis, not persisted, so it expires after an hour.
- The bell icon in the dashboard header shows in-app notifications for
  review completed/failed and quality-gate-failed. If `SLACK_WEBHOOK_URL`
  is set, the same events also post to Slack. Notifications are a shared
  feed across all users, not per-user — see Phase 7 in `INSTRUCTIONS.md`
  for why.

Backend API reference (all except `/health`, `/metrics`, and the two
`/auth/github/*` routes require `Authorization: Bearer <token>`):

- `GET /health` — liveness check.
- `GET /metrics` — Prometheus metrics (HTTP request count/latency). The
  worker serves its own separately on `WORKER_METRICS_PORT` (9200).
- `GET /auth/github/login` / `GET /auth/github/callback` — OAuth flow;
  callback redirects to `${FRONTEND_URL}/auth/callback#token=...` (a URL
  fragment, not a query param — see Phase 8 in `INSTRUCTIONS.md`).
- `GET /users/me` — the logged-in user.
- `GET /repositories`, `DELETE /repositories/{id}` — list / disconnect.
- `GET /repositories/{id}/pull-requests` — PRs + latest review status.
- `GET /pull-requests/{id}` — PR detail + latest review.
- `GET /pull-requests/{id}/diff` — live unified diff, proxied from GitHub.
- `GET /pull-requests/{id}/logs` — latest review's pipeline log lines.
- `POST /pull-requests/{id}/generate-tests` — on-demand test generation.
- `POST /pull-requests/{id}/generate-docs` — on-demand doc generation.
- `GET /notifications` — recent notifications (`?unread_only=true` to filter).
- `POST /notifications/{id}/read`, `POST /notifications/read-all`.

There's no re-index endpoint yet — to force a fresh index, delete the
repo's Qdrant collection (`repo_{id}`) and re-deliver an `installation`
webhook, or call `app.services.rag.index_repository(...)` directly.

## 6. CI/CD and deploying the platform itself (Phase 6)

Every PR touching `apps/backend` or `apps/frontend` runs lint + tests via
GitHub Actions (`.github/workflows/backend-ci.yml` /
`frontend-ci.yml`). Merging to `main` builds and pushes the backend +
frontend images to `ghcr.io/<owner>/codereviewai-{backend,frontend}`
(`.github/workflows/docker-publish.yml`), then notifies a Slack webhook if
`SLACK_WEBHOOK_URL` is set as a repo secret (skipped otherwise).

To run this platform itself in Kubernetes (a local kind cluster — see
[`infra/k8s/README.md`](infra/k8s/README.md) for the full walkthrough,
verified end-to-end against a real cluster):

```
kind create cluster --config infra/k8s/kind-config.yaml --name codereviewai
docker build -t codereviewai-backend:local apps/backend
docker build -t codereviewai-frontend:local -f apps/frontend/Dockerfile.prod apps/frontend
kind load docker-image codereviewai-backend:local codereviewai-frontend:local --name codereviewai
helm upgrade --install codereviewai infra/k8s/helm/codereviewai --wait
```

## 7. Hardening (Phase 8)

- Every endpoint is rate-limited by client IP (`app/core/rate_limit.py`):
  60/min for `/webhooks/github`, 120/min for everything else except
  `/health` and `/metrics`. An over-limit request gets a plain `429`.
- See [`SECURITY.md`](SECURITY.md) for the secrets-management review —
  what was audited, two real token leaks that were found and fixed, and
  the residual risks that were consciously left as-is.
- `apps/backend/scripts/load_test_webhooks.py` fires a concurrent burst of
  signed synthetic `pull_request` webhooks at a real running backend, to
  exercise the webhook → DB → Celery path under load without needing real
  GitHub/OpenAI credentials:
  ```
  cd apps/backend
  uv run python scripts/load_test_webhooks.py --secret "$GITHUB_APP_WEBHOOK_SECRET" --count 100 --concurrency 20
  ```
- The worker Deployment has a CPU-based `HorizontalPodAutoscaler` (on by
  default, 1-5 replicas at 70% target) — needs `metrics-server` on the
  cluster, see `infra/k8s/README.md`.

## Development

```
cd apps/backend
uv run ruff check app tests    # lint
uv run pytest                  # unit tests
uv run alembic revision --autogenerate -m "message"   # new migration

cd apps/frontend
npm run lint                   # eslint
npx tsc --noEmit               # typecheck
npm run build                  # production build (dev config)
```
