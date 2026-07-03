import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.services.ai_review import format_review_comment, run_ai_review
from app.services.github_api import get_pr_diff, post_pr_review
from app.services.github_app import get_installation_access_token
from app.services.rag import index_repository, query_context
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
                db.commit()
                return

            truncated = len(diff) > settings.max_diff_chars
            diff_for_review = diff[: settings.max_diff_chars]
            context_chunks = query_context(repo.id, f"{pr.title}\n{diff_for_review[:4000]}")
            ai_result = run_ai_review(diff_for_review, pr.title, context_chunks=context_chunks)

            comment_body = format_review_comment(ai_result, truncated=truncated)
            post_pr_review(token, owner, repo_name, pr.number, comment_body)

            review.status = "completed"
            review.summary = ai_result["summary"]
            review.raw_result = ai_result
            db.commit()
        except Exception as exc:
            logger.exception("AI review failed for PR #%s", pr.number)
            review.status = "failed"
            review.summary = f"Review failed: {exc}"
            db.commit()
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
