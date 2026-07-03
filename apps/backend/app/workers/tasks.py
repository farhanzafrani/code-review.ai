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

        try:
            owner, repo_name = repo.full_name.split("/", 1)
            token = get_installation_access_token(repo.github_installation_id)
            diff = get_pr_diff(token, owner, repo_name, pr.number)

            if not diff.strip():
                review.status = "completed"
                review.summary = "No reviewable diff content (empty or binary-only change)."
            else:
                truncated = len(diff) > settings.max_diff_chars
                diff_for_review = diff[: settings.max_diff_chars]
                context_chunks = query_context(repo.id, f"{pr.title}\n{diff_for_review[:4000]}")
                ai_result = run_ai_review(diff_for_review, pr.title, context_chunks=context_chunks)
                ai_result["truncated"] = truncated

                review.status = "completed"
                review.summary = ai_result["summary"]
                review.raw_result = ai_result
            db.commit()
        except Exception as exc:
            logger.exception("AI review failed for PR #%s", pr.number)
            review.status = "failed"
            review.summary = f"Review failed: {exc}"
            db.commit()

        maybe_post_comment(db, review_id)
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

        try:
            owner, repo_name = repo.full_name.split("/", 1)
            token = get_installation_access_token(repo.github_installation_id)
            key = sonar.project_key(repo.id)
            sonar.ensure_project(key, repo.full_name)

            with tempfile.TemporaryDirectory() as tmp:
                sonar.checkout_pr_head(owner, repo_name, pr.number, token, tmp)
                try:
                    sonar.run_scanner(key, repo.full_name, tmp)
                except subprocess.CalledProcessError as exc:
                    # sonar-scanner also exits non-zero on a failed quality
                    # gate — that's a real result, not an error, so we still
                    # fetch the actual gate status below instead of failing.
                    logger.info("sonar-scanner exited non-zero for %s: %s", repo.full_name, exc)

            gate = sonar.get_quality_gate_status(key)
            issues = sonar.get_issues(key)

            review.sonar_status = "completed"
            review.sonar_quality_gate = gate["status"]
            review.sonar_result = {"quality_gate": gate, "issues": issues}
            db.commit()
        except Exception as exc:
            logger.exception("Sonar scan failed for PR #%s", pr.number)
            review.sonar_status = "failed"
            review.sonar_result = {"error": str(exc)}
            db.commit()

        maybe_post_comment(db, review_id)
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
