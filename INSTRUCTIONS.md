# AI Code Review & DevOps Assistant

## Objective

Build a platform that watches GitHub pull requests, uses AI to explain
changes, detect bugs, flag security issues, suggest fixes, and generate
tests/docs — then automates the pipeline from merge to deployment
(build → test → containerize → deploy → notify).

Think "GitHub + SonarQube + ChatGPT + Jenkins, glued into one product."

**Definition of success (v1):** a developer opens a PR on a connected repo
and, within a couple of minutes, sees an AI-generated review comment on
GitHub (bugs found, explanation, suggested fix) — driven entirely by this
platform, with the result also visible on a web dashboard.

Everything past that (SonarQube, RAG, local LLM, Kubernetes, Terraform) is
valuable but secondary. **Do not start those until the v1 slice above works
end-to-end.**

---

## Working agreement for Claude Code

- Build one vertical slice at a time (Phase 1 before Phase 2, etc.). Do not
  scaffold the whole tech stack up front.
- After each phase, there should be something runnable/demoable locally via
  `docker compose up`.
- Prefer the simplest tool that satisfies the phase (e.g. plain `requests`
  before LangChain, a single OpenAI call before RAG).
- Treat GitHub Actions / Kubernetes / Terraform changes, and anything that
  touches real GitHub repos or posts real PR comments, as requiring explicit
  confirmation before running — these have external, hard-to-reverse effects.
- Use a monorepo layout:
  ```
  /apps/frontend      Next.js dashboard
  /apps/backend       FastAPI app + Celery workers
  /infra/docker        Dockerfiles, docker-compose.yml
  /infra/k8s           Kubernetes manifests / Helm chart (Phase 6+)
  /infra/terraform     IaC (Phase 6+)
  /.github/workflows   CI/CD (Phase 6)
  ```
- After finishing a phase, update the checklist in this file
  (`- [ ]` → `- [x]`) so future sessions know where things stand.

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React, Next.js, TypeScript, Tailwind CSS, ShadCN UI, Chart.js |
| Backend | Python, FastAPI, Celery, Redis, WebSockets, JWT auth |
| AI | OpenAI GPT (primary), LangChain, Qdrant (RAG), local LLM via Ollama/Llama 3 (stretch) |
| Data | PostgreSQL, Redis, Qdrant |
| DevOps | Docker, Docker Compose, Kubernetes, Helm, NGINX, GitHub Actions, Terraform |

## Target architecture

```
                React + Next.js
                       │
              NGINX Reverse Proxy
                       │
                FastAPI Backend
                       │
      ┌───────────────┼───────────────┐
      │               │               │
 PostgreSQL        Redis          Celery
      │               │           Workers
      └───────────────┼───────────────┘
                      │
      ┌───────────────┼────────────────┐
      │               │                │
   OpenAI         Local LLM        Qdrant
      │           (stretch)      (RAG, Phase 4)
      └───────────────┬────────────────┘
                      │
              GitHub API / Webhooks
                      │
                 Docker Compose → Kubernetes (Phase 6)
                      │
               GitHub Actions CI/CD (Phase 6)
```

---

## Phased implementation plan

### Phase 0 — Scaffolding & local environment
- [x] Init git repo with the monorepo layout above, root `README.md`.
- [x] `infra/docker/docker-compose.yml` with `postgres`, `redis` (add `qdrant`
      later in Phase 4).
- [x] `.env.example` for secrets (GitHub App creds, OpenAI key, DB URL).
- [x] Empty FastAPI app (`apps/backend`) that boots via `docker compose up`.
- [ ] Empty Next.js app (`apps/frontend`) that boots via `docker compose up`
      — deferred to Phase 3, no point scaffolding it before it's needed.

**Done when:** `docker compose up` starts Postgres, Redis, an empty FastAPI
`/health` endpoint, and the Next.js default page.

### Phase 1 — Backend skeleton: auth + GitHub webhook intake

- [x] SQLAlchemy models + Alembic migrations: `User`, `Repository`,
      `PullRequest`, `Review`.
- [x] GitHub OAuth login → issue JWT. (Implemented via GitHub App
      "Sign in with GitHub", not a separate OAuth App.)
- [x] GitHub App set up so a user can connect a repo (installing the app
      registers `Repository` rows via the `installation` /
      `installation_repositories` webhook events).
- [x] `POST /webhooks/github` endpoint: verify signature, parse
      `pull_request` events (opened/synchronize/reopened), persist a
      `PullRequest` row, enqueue a Celery task with the review id.
- [x] Celery + Redis wired up as the task queue (worker container in compose).

**Done when:** opening/pushing to a PR on a real connected test repo creates
a row in Postgres and a Celery task fires (log it, no AI yet). Verified via
ruff, alembic upgrade against a scratch DB, and an in-process signature
check — see `README.md` for how to wire up a real GitHub App and confirm it
end-to-end against a live repo (needs a reachable webhook URL, e.g. ngrok).

### Phase 2 — AI code review MVP (the core vertical slice)
- [x] Celery task: fetch the PR diff via GitHub API (diff media type on
      `GET /repos/.../pulls/{n}`).
- [x] Single OpenAI call: prompt with the diff, ask for bugs found,
      plain-English explanation, and suggested fixes as structured JSON
      (OpenAI Structured Outputs, `app/services/ai_review.py`).
- [x] Post the result back as a PR review comment via the GitHub API
      (`POST /pulls/{n}/reviews`, `app/services/github_api.py`).
- [x] Store the `Review` result (status, summary, raw JSON) in Postgres.

**Done when:** a PR on the test repo gets a real AI-generated review comment
automatically, with no manual steps. **This is the v1 milestone — stop and
validate it works reliably before moving on.**

Verified so far: ruff clean, and a fully mocked run of
`process_pull_request` against an in-memory SQLite DB (installation token /
diff fetch / OpenAI call / GitHub post all mocked) exercising both the
success path (`Review.status == "completed"`, summary + raw findings
persisted, correct owner/repo/PR number threaded through) and the failure
path (`Review.status == "failed"` with the error message, no exception
propagated). **Not yet verified against a real GitHub App + live OpenAI
key** — do that next: set `OPENAI_API_KEY` and open a real PR on the
connected test repo, confirm the review comment actually lands.

### Phase 3 — Frontend dashboard
- [x] GitHub OAuth login flow in Next.js, calling the backend for the JWT
      (backend callback redirects to `/auth/callback?token=...`, stored in
      localStorage via `lib/auth-context.tsx`).
- [x] Repo list page (`/dashboard`): connect (link to the GitHub App
      install page) / disconnect (`DELETE /repositories/{id}`).
- [x] PR list page (`/dashboard/repositories/[id]`) showing review status
      per PR.
- [x] Review detail page (`/dashboard/pull-requests/[id]`) rendering the AI
      output (summary, per-bug severity/file/description/suggestion)
      alongside the live diff (fetched from GitHub via the backend).
- [x] Polling (every 4s while a review is pending/running) so status
      updates without a manual refresh — chose polling over WebSockets per
      the "simplest tool that satisfies the phase" rule.
- [x] New backend endpoints to support the above: `GET/DELETE
      /repositories`, `GET /repositories/{id}/pull-requests`, `GET
      /pull-requests/{id}`, `GET /pull-requests/{id}/diff`, plus CORS.

**Done when:** a user can log in, connect a repo, and watch a PR's AI review
appear on the dashboard without touching GitHub directly.

Verified: backend — ruff clean, new endpoints exercised end-to-end against
an in-memory SQLite DB via `TestClient` (list/disconnect repos, list PRs
with nested latest review, PR detail). Frontend — `tsc --noEmit`, `eslint`,
and `next build` all clean; walked the full flow in headless Chrome against
a mocked backend (OAuth callback → dashboard → repo → PR list → review
detail with findings) and fixed two real issues found that way: a wrong
"back" link (was using the PR id instead of the repository id) and a Base
UI `nativeButton` console warning on link-styled buttons. The diff panel
degrades gracefully (just doesn't render) when the diff fetch fails, which
is what happens without a real GitHub App installation — **not yet
verified against a live GitHub App + real repo**, only mocked data.

### Phase 4 — Expand AI capabilities
- [ ] Security analysis prompt (or pair the LLM with a static tool like
      Bandit/Semgrep and have the LLM summarize findings).
- [ ] Unit test generation for changed functions.
- [ ] Documentation generation (docstrings / README diffs) for changed code.
- [ ] Add Qdrant + LangChain: index the repo's codebase so review prompts
      are RAG-augmented with relevant context beyond the diff.
- [ ] (Stretch) Local LLM via Ollama/Llama 3 as a fallback/cheaper mode,
      selectable via config.

**Done when:** the review comment includes security notes, and a generated
test file / doc snippet can be produced on demand from the dashboard.

### Phase 5 — SonarQube integration
- [ ] Run a SonarQube scan (self-hosted or Sonar API) as part of the PR
      pipeline.
- [ ] Merge Sonar's quality-gate results into the same review report as the
      AI output (single unified PR comment/dashboard view).

**Done when:** a PR review shows both AI findings and Sonar quality-gate
status together.

### Phase 6 — CI/CD & deployment automation
- [ ] `.github/workflows`: run backend/frontend tests + lint on every PR.
- [ ] Docker build + push images on merge to main.
- [ ] Kubernetes manifests / Helm chart for the platform itself
      (backend, frontend, worker, Postgres, Redis, Qdrant).
- [ ] NGINX ingress in front of the frontend/backend.
- [ ] Terraform for the underlying cloud infra (cluster, DB, networking) —
      scope to whatever provider is actually being used.
- [ ] Slack notification on deploy success/failure.

**Done when:** merging to main automatically builds, tests, and deploys the
platform itself to a real (or local kind/minikube) Kubernetes cluster.

### Phase 7 — Monitoring & notifications
- [ ] Structured logging + basic metrics (e.g. Prometheus) for backend and
      workers.
- [ ] Live build/deploy logs surfaced on the dashboard.
- [ ] Notification center (Slack + in-app) for review completed, quality
      gate failed, deploy succeeded/failed.

### Phase 8 — Hardening
- [ ] Rate limiting on webhook + API endpoints.
- [ ] Secrets management review (no plaintext tokens in DB/logs).
- [ ] Load test the webhook → Celery → AI pipeline under burst PR activity.
- [ ] Autoscaling config for Celery workers in Kubernetes.

---

## Non-goals for now

- Multi-tenant billing/SaaS packaging.
- Supporting VCS other than GitHub.
- Building a custom LLM instead of using OpenAI/Llama 3.

## Advanced concepts exercised

Event-driven architecture, background workers, async programming,
WebSockets, OAuth, Docker networking, Kubernetes, vector search, prompt
engineering, CI/CD, infrastructure as code.
