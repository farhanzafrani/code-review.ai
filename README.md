# AI Code Review & DevOps Assistant

See [`INSTRUCTIONS.md`](INSTRUCTIONS.md) for the project objective and the
full phased implementation plan. This README covers day-to-day setup for
what's built so far (Phase 0 + 1: backend skeleton, auth, webhook intake;
Phase 2: AI review of the PR diff, posted back to GitHub; Phase 3: Next.js
dashboard for logging in, connecting repos, and watching reviews land;
Phase 4: security findings, on-demand test/doc generation, and a Qdrant-
backed RAG pass so reviews see more than just the raw diff).

## Layout

```
apps/backend/    FastAPI app + Celery worker
apps/frontend/   Next.js dashboard (TypeScript, Tailwind, shadcn/ui)
infra/docker/    docker-compose.yml for local dev
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

## 3. Run it

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

## 4. Try it

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

Backend API reference (all except `/health` and the two `/auth/github/*`
routes require `Authorization: Bearer <token>`):

- `GET /health` — liveness check.
- `GET /auth/github/login` / `GET /auth/github/callback` — OAuth flow;
  callback redirects to `${FRONTEND_URL}/auth/callback?token=...`.
- `GET /users/me` — the logged-in user.
- `GET /repositories`, `DELETE /repositories/{id}` — list / disconnect.
- `GET /repositories/{id}/pull-requests` — PRs + latest review status.
- `GET /pull-requests/{id}` — PR detail + latest review.
- `GET /pull-requests/{id}/diff` — live unified diff, proxied from GitHub.
- `POST /pull-requests/{id}/generate-tests` — on-demand test generation.
- `POST /pull-requests/{id}/generate-docs` — on-demand doc generation.

There's no re-index endpoint yet — to force a fresh index, delete the
repo's Qdrant collection (`repo_{id}`) and re-deliver an `installation`
webhook, or call `app.services.rag.index_repository(...)` directly.

## Development

```
cd apps/backend
uv run ruff check app          # lint
uv run alembic revision --autogenerate -m "message"   # new migration

cd apps/frontend
npm run lint                   # eslint
npx tsc --noEmit               # typecheck
npm run build                  # production build
```
