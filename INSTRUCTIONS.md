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
- [x] Security analysis prompt: extended the review schema with a distinct
      `security_issues` list (category/severity/file/description/
      recommendation), separate from `bugs`, with prompt instructions not
      to double-report the same finding in both. Chose this over
      Bandit/Semgrep because the platform reviews arbitrary-language repos
      and the prompt-only approach needed no new subprocess/sandboxing
      infra — can still add a static tool later to complement it.
- [x] Unit test generation for changed functions — on demand, not
      automatic (see "Done when" below).
- [x] Documentation generation (docstrings + a short markdown snippet) for
      changed code — also on demand.
- [x] Add Qdrant (skipped LangChain — chunk/embed/upsert/query directly via
      `qdrant-client` + OpenAI embeddings was simpler and needed no extra
      framework): indexes a connected repo's default branch once at
      connect-time, retrieved chunks get folded into the review prompt as
      extra context beyond the diff. Indexing is best-effort (failures
      logged, not retried) and query_context() fails open — a Qdrant/
      embedding problem degrades to a diff-only review, never blocks it.
- [ ] (Stretch, deferred) Local LLM via Ollama/Llama 3 as a fallback/
      cheaper mode. Not started — explicitly marked stretch in the plan;
      revisit if OpenAI cost/availability becomes a real constraint.

**Done when:** the review comment includes security notes, and a generated
test file / doc snippet can be produced on demand from the dashboard.

Verified: backend — ruff clean; mocked end-to-end tests covering the
security schema (strict-mode shape), the webhook → `index_repository_task`
trigger (fires once on repo creation, not on redelivery), the full
`process_pull_request` pipeline with RAG context threaded into
`run_ai_review`, and both `generate-tests`/`generate-docs` endpoints via
`TestClient`. Frontend — `tsc`/`eslint`/`next build` clean; walked the PR
detail page in headless Chrome against a mocked backend and confirmed the
Bugs/Security sections and both Generate panels render correctly with no
console warnings. **Not yet exercised end-to-end against a live repo** —
in particular, indexing a real repo's file tree and RAG actually changing
review quality is unverified beyond the mocked pipeline test above.

Known limitations to revisit later: indexing doesn't re-run on push (only
at connect-time), so retrieved context can drift stale; no re-index
endpoint yet (see README); generated tests/docs are ephemeral (not
persisted, not posted back to GitHub).

### Phase 5 — SonarQube integration
- [x] Run a SonarQube scan (self-hosted, via docker-compose) as part of the
      PR pipeline: `app/services/sonar.py` shallow-clones the PR head
      (`git fetch refs/pull/{n}/head`), auto-creates a per-repo Sonar
      project (`codereviewai_{repository_id}`) if missing, and runs
      `sonar-scanner` with `sonar.qualitygate.wait=true` so the scan blocks
      until the quality gate is computed.
- [x] Merge Sonar's quality-gate results into the same review report as the
      AI output: `app/services/review_comment.py` gates on *both* the AI
      pipeline and (when enabled) the Sonar pipeline reaching a terminal
      state, row-locks the Review to avoid a double-post race, and edits
      the existing GitHub review (`PUT .../reviews/{id}`) if one pipeline
      already posted before the other finished — so it's always one
      comment, never two, regardless of which finishes first.
- [x] Off by default (`SONARQUBE_ENABLED=false`) — chose this because,
      unlike every other integration so far, this one needs a real running
      SonarQube instance plus `git`/`sonar-scanner`/a JVM in the worker
      image, none of which exist in this dev sandbox. Self-hosted via
      docker-compose (profile-gated, `--profile sonarqube`) rather than
      SonarCloud, matching every other service in the stack being local
      with no external account needed.

**Done when:** a PR review shows both AI findings and Sonar quality-gate
status together.

Verified: DB migration (0002) applies cleanly; ruff clean; the full
`run_sonar_scan` task mocked end-to-end (project ensure/checkout/scanner
all mocked) including the specific edge case where sonar-scanner exits
non-zero for a *failed quality gate* (correctly recorded as a normal
`completed` result with `quality_gate=ERROR`, not an infra failure) versus
a genuine infra error (correctly recorded as `sonar_status=failed`); the
webhook enqueues `run_sonar_scan` only when the flag is on (confirmed both
ways); the unified-comment gating/locking logic (wait for both, post once,
edit on the second finisher) tested directly against SQLite. Frontend
tsc/eslint/build clean, quality-gate badge + issues list confirmed in a
headless-Chrome walkthrough against mocked data.

**Not verified — cannot be, in this sandbox:** the actual `git`/
`sonar-scanner`/JRE installation in the Dockerfile (no Docker here to
build it), and a real scan against a live SonarQube instance. The
Dockerfile changes are based on SonarQube's documented scanner-CLI install
steps and a version (6.2.1.4610) confirmed to actually resolve/download,
but the build itself is untested. Try `docker compose --profile sonarqube
up --build` and open a real PR before relying on this.

### Phase 6 — CI/CD & deployment automation
- [x] `.github/workflows`: run backend/frontend tests + lint on every PR
      (`backend-ci.yml`: ruff + pytest; `frontend-ci.yml`: eslint + tsc +
      next build).
- [x] Docker build + push images on merge to main (`docker-publish.yml`,
      pushes to GHCR — no extra registry account needed, uses the repo's
      own `GITHUB_TOKEN`). Added `apps/frontend/Dockerfile.prod` (multi-
      stage, `next.config.ts` `output: "standalone"`) since the existing
      frontend Dockerfile is dev-only (`npm run dev` + volume mounts for
      compose); the backend's existing Dockerfile is reused as-is.
- [x] Kubernetes manifests / Helm chart for the platform itself
      (`infra/k8s/helm/codereviewai`: backend + worker + frontend
      Deployments, Postgres/Redis/Qdrant Deployments with PVCs for the
      first and third, ConfigMap/Secret, NGINX Ingress).
- [x] NGINX ingress in front of the frontend/backend — two hosts
      (`codereviewai.local` → frontend, `api.codereviewai.local` →
      backend), not path-based, since the backend's routes are mounted at
      root with no `/api` prefix.
- [x] Terraform — deferred with rationale, see `infra/terraform/README.md`:
      the chosen target is local kind (see below), which has no cloud
      account/VPC/managed-DB for Terraform to declare.
- [x] Slack notification on deploy success/failure — a step in
      `docker-publish.yml` posts to `secrets.SLACK_WEBHOOK_URL` if set,
      skips cleanly if not (no Slack workspace connected in this
      environment to test against a real webhook).

**Done when:** merging to main automatically builds, tests, and deploys the
platform itself to a real (or local kind/minikube) Kubernetes cluster.

Verified: backend — added a real (previously-missing) `apps/backend/tests/`
suite (health check, JWT roundtrip/expiry/tamper, webhook signature
verify/reject) since no test files existed anywhere in the repo despite
earlier phases' verification notes describing tests that were run but never
persisted; `ruff check` and `pytest` both clean. Frontend — `eslint`,
`tsc --noEmit`, and `next build` (both the dev config and the new
standalone-output prod build) all clean. Both production Docker images
(`apps/backend/Dockerfile`, `apps/frontend/Dockerfile.prod`) were actually
built and booted via plain `docker run` — this also closes out Phase 5's
"Dockerfile changes... untested" caveat for the backend image, which builds
and serves `/health` correctly (previously only inferred from documented
install steps, never built).

The Helm chart was verified against a **real local kind cluster**, not just
`helm lint`/`helm template`: created the cluster, `kind load docker-image`d
both images, `helm upgrade --install --wait` brought up all 6
pods (backend, worker, frontend, postgres, redis, qdrant) to Ready, alembic
migrated a real Postgres to head (`0002`) via the init container, the
Celery worker connected to Redis and registered all three tasks, and both
`/health` (backend) and `/` (frontend) returned HTTP 200 through their
ClusterIP services. This caught and fixed two real bugs that pure
templating couldn't have: `uv run` (no `--no-sync`) re-triggers a
lockfile/build check on every container start, which needs PyPI reachable
and hangs/fails on any network-restricted cluster — fixed by adding
`--no-sync` to the chart's `alembic`/`celery` command overrides; and the
GitHub App private key Secret was mounted at `/run/secrets`, which is where
Kubernetes' own automatic service-account-token mount also lands on
Debian-based images (`/var/run` → `/run`) — a read-only mount there
silently blocked kubelet from creating its own subdirectory underneath, so
the backend/worker containers never started at all. Moved to
`/etc/secrets/github-app`.

Not verified: the ingress path (no real DNS/browser test — done via
`kubectl exec`-based `curl` against the ClusterIP services rather than
through ingress-nginx, since the sandbox's port 80 was already bound by
something else; `kind-config.yaml`'s port mappings and the two-host Ingress
are per kind's documented recipe but untested against a live nginx
controller). The Slack webhook step and GHCR push are untested against
real credentials (no Slack workspace or GHCR push permissions available
here) — the workflow YAML is syntactically valid and the skip-if-unset
logic was reasoned through, not run.

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
