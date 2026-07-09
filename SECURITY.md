# Secrets management review (Phase 8)

A pass over every place a secret (GitHub App private key/tokens, OpenAI
key, SonarQube token, Slack webhook URL, JWT secret) could end up
persisted to the database, written to logs, or otherwise exposed outside
its intended use — done as part of Phase 8's hardening pass, not a
one-time audit to file away: re-check this list whenever a new external
call or exception path is added.

## Found and fixed

1. **GitHub installation token and SonarQube token leaked into
   `Review.sonar_result`, GitHub PR comments, and worker logs.**
   `app/services/sonar.py`'s `checkout_pr_head` embedded the GitHub
   installation token directly in the git remote URL
   (`https://x-access-token:{token}@github.com/...`), and `run_scanner`
   passed the SonarQube token as a `-Dsonar.token=...` CLI argument. Both
   were passed as `subprocess.run(...)` argv. `subprocess.CalledProcessError`
   and `TimeoutExpired` stringify their *full* argv — and `tasks.py`
   persisted `str(exc)` to `Review.sonar_result["error"]`, which
   `format_sonar_section` renders straight into the GitHub PR comment, and
   also logged it via `logger.exception`/`logger.info`. Worse, the
   sonar-scanner leak wasn't even a rare error path: sonar-scanner exits
   non-zero on a **failed quality gate**, which is an expected, routine
   outcome this code explicitly handles as a normal result, not a rare
   failure — so the token leaked on every failed gate, not just infra
   errors.

   Fixed in three parts:
   - `_run_no_secrets()` wraps every subprocess call and re-raises with a
     plain description (`"git clone"`, `"sonar-scanner"`, ...) in place of
     the real argv, so no exception downstream of it — however it's later
     logged or stored — can carry a secret. `from None` also drops the
     original exception from the printed traceback, not just its `str()`.
   - The GitHub token now goes to git via `GIT_ASKPASS` (a short-lived temp
     script, not the tempdir being cloned into) instead of the remote URL
     — this also stops git's own stderr from potentially echoing the
     credential-bearing URL back on an auth failure, which the argv-only
     fix wouldn't have caught.
   - The SonarQube token now goes in via the `SONAR_TOKEN` environment
     variable (supported since scanner-cli 4.7+) instead of a `-D` flag,
     so it's never in argv in the first place — closing the gap that
     `_run_no_secrets` alone doesn't cover (a *successful* run's argv is
     never turned into an exception, but it's still visible to anything
     that can read this process's `/proc/<pid>/cmdline` on the host).

   Regression tests: `tests/test_sonar_secrets.py`.

2. **Session JWT passed as a `?token=...` query parameter in the OAuth
   redirect.** `app/api/routes/auth.py`'s callback redirected to
   `{frontend_url}/auth/callback?token=...`. Query params get written to
   this app's own access logs and any reverse proxy's logs in front of it,
   and land in browser history — a URL fragment (`#token=...`) is never
   sent to a server at all, so it can't appear in any of those places.
   Fixed by switching to a fragment and updating the frontend callback
   page to read `window.location.hash` instead of `useSearchParams()`
   (fragments aren't part of the query string Next.js parses).

   Regression test: `tests/test_auth_callback.py`.

## Reviewed, no issue found

- **GitHub installation tokens are never persisted.**
  `get_installation_access_token()` fetches a fresh token per use; no
  model has a column for it. Same for the GitHub OAuth user access token
  in `auth.py`'s callback — used once to fetch the profile, then
  discarded.
- **`github_api.py` / `github_app.py` always pass tokens via the
  `Authorization` header**, never in a URL — `httpx.HTTPStatusError`'s
  `str()` includes the request URL and response body but not request
  headers, so a failed GitHub API call can't leak the token through its
  exception message the way the subprocess calls above could.
- **No secret is ever passed to `logging`.** Grepped every
  `logger.*`/`print` call against `settings` and found none that logs the
  `Settings` object or an individual secret field directly.
- **Frontend has zero `console.*` calls** — the JWT (read from
  `localStorage` via `lib/auth-context.tsx`) is never logged client-side.
- **`.gitignore` already excludes `.env` and `*.pem`** — verified no
  secret-bearing file has ever been committed (`git log --all
  --diff-filter=A` for either pattern comes up empty).
- **Kubernetes**: the GitHub App private key and Slack webhook URL are
  Secret-backed, not ConfigMap-backed, in the Helm chart (`values.yaml`'s
  `secrets:` block, documented as override-only — see `infra/k8s/README.md`).

## Known residual risk (not fixed — accepted for this project's scope)

- **JWTs are bearer tokens with no revocation mechanism** and a 24h
  default expiry (`JWT_EXPIRE_MINUTES`) — there's no server-side session
  store to invalidate one early (e.g. on logout, this only clears
  `localStorage` client-side). Acceptable for this project's scope (see
  "Non-goals" in `INSTRUCTIONS.md` — no multi-tenant/SaaS hardening), but
  worth knowing before reusing this auth pattern somewhere sensitive.
- **Notifications and repository visibility are global, not per-user**
  (see Phase 7's notes) — this is a tenancy gap, not a secrets leak, but
  it's adjacent enough to flag here: any authenticated user can see every
  connected repo's PRs, reviews, and notifications.
