"""Coordinates posting a single unified PR comment from two independent
async pipelines (AI review, Sonar scan) that may finish in either order.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.review import Review
from app.services.ai_review import format_review_comment
from app.services.github_api import post_pr_review, update_pr_review
from app.services.github_app import get_installation_access_token
from app.services.notifications import notify_review_terminal
from app.services.sonar import format_sonar_section

logger = logging.getLogger(__name__)

_TERMINAL = ("completed", "failed")


def maybe_post_comment(db: Session, review_id: int) -> None:
    """Post (or update) the PR comment once every enabled pipeline is done.

    Row-locks the Review so two pipelines finishing near-simultaneously
    can't both post the initial comment — whichever finishes second sees
    github_review_id already set and edits it instead.
    """
    review = db.execute(
        select(Review).where(Review.id == review_id).with_for_update()
    ).scalar_one()

    ai_done = review.status in _TERMINAL
    sonar_needed = settings.sonarqube_enabled
    sonar_done = (not sonar_needed) or (review.sonar_status in _TERMINAL)
    if not (ai_done and sonar_done):
        db.commit()  # release the row lock; nothing else to do yet
        return

    ai_body = (
        format_review_comment(review.raw_result)
        if review.raw_result
        else (review.summary or "AI review failed.")
    )
    if sonar_needed:
        sonar_body = format_sonar_section(
            review.sonar_status, review.sonar_quality_gate, review.sonar_result
        )
        body = f"{ai_body}\n\n---\n\n{sonar_body}"
    else:
        body = ai_body

    pr = review.pull_request
    repo = pr.repository
    owner, repo_name = repo.full_name.split("/", 1)
    token = get_installation_access_token(repo.github_installation_id)

    if review.github_review_id:
        update_pr_review(token, owner, repo_name, pr.number, review.github_review_id, body)
    else:
        result = post_pr_review(token, owner, repo_name, pr.number, body)
        review.github_review_id = result["id"]

    notify_review_terminal(db, review)
    db.commit()
