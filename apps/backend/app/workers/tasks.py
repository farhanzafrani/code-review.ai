import logging

from app.db.session import SessionLocal
from app.models.pull_request import PullRequest
from app.models.review import Review
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.process_pull_request")
def process_pull_request(review_id: int) -> None:
    """Phase 1: prove the webhook -> queue -> worker pipeline works.

    Phase 2 replaces the body of this task with: fetch the diff, call the
    LLM, and post the result back as a PR review comment.
    """
    db = SessionLocal()
    try:
        review = db.get(Review, review_id)
        if review is None:
            logger.warning("process_pull_request: review %s not found", review_id)
            return

        pr = db.get(PullRequest, review.pull_request_id)
        review.status = "running"
        db.commit()

        logger.info(
            "Received PR #%s (%s) for AI review — AI review lands in Phase 2",
            pr.number if pr else "?",
            pr.title if pr else "?",
        )

        review.status = "completed"
        review.summary = "Webhook -> Celery pipeline OK. AI review not implemented yet (Phase 2)."
        db.commit()
    finally:
        db.close()
