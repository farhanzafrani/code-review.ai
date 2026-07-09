"""Notification fan-out for a review reaching a terminal state.

Called once, from review_comment.maybe_post_comment, at the single point
where both the AI and (if enabled) Sonar pipelines have reached a terminal
state — the same gating that ensures only one PR comment gets posted also
ensures each of these fires exactly once per review.
"""

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import Notification
from app.models.review import Review

logger = logging.getLogger(__name__)


def _create(db: Session, type_: str, message: str, pull_request_id: int) -> None:
    db.add(Notification(type=type_, message=message, pull_request_id=pull_request_id))
    _post_slack(message)


def _post_slack(message: str) -> None:
    """Best-effort: a Slack outage or bad webhook URL must never affect the
    review pipeline it's reporting on — logged, not retried."""
    if not settings.slack_webhook_url:
        return
    try:
        httpx.post(settings.slack_webhook_url, json={"text": message}, timeout=5)
    except Exception:
        logger.exception("Failed to post Slack notification")


def notify_review_terminal(db: Session, review: Review) -> None:
    pr = review.pull_request
    repo = pr.repository
    label = f"{repo.full_name}#{pr.number} ({pr.title})"

    if review.status == "completed":
        _create(db, "review_completed", f"Review completed for {label}", pr.id)
    elif review.status == "failed":
        _create(db, "review_failed", f"Review failed for {label}: {review.summary}", pr.id)

    if settings.sonarqube_enabled and review.sonar_quality_gate == "ERROR":
        _create(db, "quality_gate_failed", f"Quality gate FAILED for {label}", pr.id)
