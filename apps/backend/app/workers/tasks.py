import logging
import subprocess
import tempfile

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.services import sonar
from app.services.ai_review import run_ai_review
from app.services.github_api import get_pr_diff
from app.services.github_app import get_installation_access_token
from app.services.rag import index_repository, query_context
from app.services.review_comment import maybe_post_comment
from app.services.task_log import append_log
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.process_pull_request")
def process_pull_request(review_id: int) -> None:
    """Fetch the PR diff, run the AI review, and post the result back to GitHub."""
    db = SessionLocal()
    try:
        review = db.get(Review, review_id)
        if review is None:
            logger.warning("process_pull_request: review %s not found", review_id)
            return

        pr = db.get(PullRequest, review.pull_request_id)
        repo = db.get(Repository, pr.repository_id)
        review.status = "running"
        db.commit()
        append_log(review_id, f"Starting AI review of {repo.full_name}#{pr.number}")

        try:
            owner, repo_name = repo.full_name.split("/", 1)
            token = get_installation_access_token(repo.github_installation_id)
            append_log(review_id, "Fetching PR diff from GitHub…")
            diff = get_pr_diff(token, owner, repo_name, pr.number)

            if not diff.strip():
                review.status = "completed"
                review.summary = "No reviewable diff content (empty or binary-only change)."
                append_log(review_id, "Diff is empty — nothing to review.")
            else:
                truncated = len(diff) > settings.max_diff_chars
                diff_for_review = diff[: settings.max_diff_chars]
                append_log(review_id, "Querying RAG index for related context…")
                context_chunks = query_context(repo.id, f"{pr.title}\n{diff_for_review[:4000]}")
                append_log(review_id, "Running AI review…")
                ai_result = run_ai_review(diff_for_review, pr.title, context_chunks=context_chunks)
                ai_result["truncated"] = truncated

                review.status = "completed"
                review.summary = ai_result["summary"]
                review.raw_result = ai_result
                append_log(review_id, "AI review complete.")
            db.commit()
        except Exception as exc:
            logger.exception("AI review failed for PR #%s", pr.number)
            review.status = "failed"
            review.summary = f"Review failed: {exc}"
            append_log(review_id, f"AI review failed: {exc}")
            db.commit()

        append_log(review_id, "Posting result to GitHub…")
        try:
            maybe_post_comment(db, review_id)
        except Exception:
            # Posting is a separate concern from the AI review itself —
            # review.status is already correctly recorded above (including
            # "failed", if that's what happened). A broken GitHub token/API
            # call here must not also crash the whole task and drop it into
            # Celery's own FAILURE state on top of that — surfaced by a
            # burst load test (scripts/load_test_webhooks.py) where every
            # task in the batch hit this exact path and each one crashed
            # the task instead of leaving a clean "failed" review behind.
            db.rollback()
            logger.exception("Failed to post PR comment for review %s", review_id)
            append_log(review_id, "Failed to post result to GitHub.")
        append_log(review_id, "Done.")
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.run_sonar_scan")
def run_sonar_scan(review_id: int) -> None:
    """Scan the PR's head commit with SonarQube; no-op if not enabled."""
    if not settings.sonarqube_enabled:
        return

    db = SessionLocal()
    try:
        review = db.get(Review, review_id)
        if review is None:
            logger.warning("run_sonar_scan: review %s not found", review_id)
            return

        pr = db.get(PullRequest, review.pull_request_id)
        repo = db.get(Repository, pr.repository_id)
        review.sonar_status = "running"
        db.commit()
        append_log(review_id, f"Starting Sonar scan of {repo.full_name}#{pr.number}")

        try:
            owner, repo_name = repo.full_name.split("/", 1)
            token = get_installation_access_token(repo.github_installation_id)
            key = sonar.project_key(repo.id)
            append_log(review_id, "Ensuring Sonar project exists…")
            sonar.ensure_project(key, repo.full_name)

            with tempfile.TemporaryDirectory() as tmp:
                append_log(review_id, "Checking out PR head commit…")
                sonar.checkout_pr_head(owner, repo_name, pr.number, token, tmp)
                try:
                    append_log(review_id, "Running sonar-scanner…")
                    sonar.run_scanner(key, repo.full_name, tmp)
                except subprocess.CalledProcessError as exc:
                    # sonar-scanner also exits non-zero on a failed quality
                    # gate — that's a real result, not an error, so we still
                    # fetch the actual gate status below instead of failing.
                    logger.info("sonar-scanner exited non-zero for %s: %s", repo.full_name, exc)

            append_log(review_id, "Fetching quality gate status…")
            gate = sonar.get_quality_gate_status(key)
            issues = sonar.get_issues(key)

            review.sonar_status = "completed"
            review.sonar_quality_gate = gate["status"]
            review.sonar_result = {"quality_gate": gate, "issues": issues}
            append_log(review_id, f"Sonar scan complete — quality gate: {gate['status']}")
            db.commit()
        except Exception as exc:
            logger.exception("Sonar scan failed for PR #%s", pr.number)
            review.sonar_status = "failed"
            review.sonar_result = {"error": str(exc)}
            append_log(review_id, f"Sonar scan failed: {exc}")
            db.commit()

        try:
            maybe_post_comment(db, review_id)
        except Exception:
            # See the matching comment in process_pull_request — posting
            # failing must not crash the task on top of an already-recorded
            # sonar_status.
            db.rollback()
            logger.exception("Failed to post PR comment for review %s", review_id)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.index_repository_task")
def index_repository_task(repository_id: int) -> None:
    """Best-effort repo indexing for RAG — failures are logged, not retried."""
    db = SessionLocal()
    try:
        repo = db.get(Repository, repository_id)
        if repo is None:
            logger.warning("index_repository_task: repository %s not found", repository_id)
            return
        try:
            owner, repo_name = repo.full_name.split("/", 1)
            token = get_installation_access_token(repo.github_installation_id)
            count = index_repository(repo.id, token, owner, repo_name)
            logger.info("Indexed %d chunks for %s", count, repo.full_name)
        except Exception:
            logger.exception("Failed to index repository %s", repo.full_name)
    finally:
        db.close()
