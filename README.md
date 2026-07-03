# AI Code Review & DevOps Assistant

See [`INSTRUCTIONS.md`](INSTRUCTIONS.md) for the project objective and the
full phased implementation plan. This README covers day-to-day setup for
what's built so far (Phase 0 + 1: backend skeleton, auth, webhook intake;
Phase 2: AI review of the PR diff, posted back to GitHub).

## Layout

```
apps/backend/    FastAPI app + Celery worker (implemented)
apps/frontend/   Next.js dashboard (Phase 3, not yet built)
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

## 3. Run it

With Docker available:

```
cp .env.example .env   # then fill in the GitHub values above
docker compose -f infra/docker/docker-compose.yml up --build
```

This starts Postgres, Redis, the FastAPI backend (with `alembic upgrade
head` run automatically on boot), and a Celery worker.

Without Docker, for local backend-only development:

```
cd apps/backend
uv sync
cp ../../.env.example .env   # adjust DATABASE_URL/REDIS_URL to localhost
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# in another terminal:
uv run celery -A app.workers.celery_app worker --loglevel=info
```

## 4. Try it

- `GET /health` — liveness check.
- `GET /auth/github/login` — starts the GitHub OAuth flow, redirects to
  GitHub, and on callback returns `{"access_token": "...", "token_type":
  "bearer"}`. Use that as a `Authorization: Bearer <token>` header.
- `GET /users/me` — protected route, returns the logged-in user.
- Install the GitHub App on a repo → a `Repository` row is created.
- Open or push to a PR on that repo → a `PullRequest` + `Review` row is
  created, a Celery task fires, and within a minute or two a real AI review
  comment appears on the PR (findings + summary). Check worker logs if it
  doesn't show up — the task marks the `Review` row `failed` with an error
  message on any GitHub/OpenAI error instead of raising.

## Development

```
cd apps/backend
uv run ruff check app          # lint
uv run alembic revision --autogenerate -m "message"   # new migration
```
