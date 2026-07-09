from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.models.notification import Notification
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.services.notifications import notify_review_terminal


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(bind=engine)


def _seed_review(db: Session, status: str, sonar_quality_gate: str | None = None) -> Review:
    repo = Repository(github_repo_id=1, full_name="acme/widgets", github_installation_id=1)
    db.add(repo)
    db.flush()
    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=1,
        number=42,
        title="Add widget",
        head_sha="abc",
        base_sha="def",
        html_url="https://github.com/acme/widgets/pull/42",
    )
    db.add(pr)
    db.flush()
    review = Review(pull_request_id=pr.id, status=status, sonar_quality_gate=sonar_quality_gate)
    db.add(review)
    db.flush()
    return review


def test_completed_review_creates_notification() -> None:
    db = _make_session()
    review = _seed_review(db, "completed")
    with patch("app.services.notifications.httpx.post") as mock_post:
        notify_review_terminal(db, review)
    db.commit()

    notifications = db.query(Notification).all()
    assert len(notifications) == 1
    assert notifications[0].type == "review_completed"
    mock_post.assert_not_called()  # no SLACK_WEBHOOK_URL configured by default


def test_failed_review_creates_notification() -> None:
    db = _make_session()
    review = _seed_review(db, "failed")
    review.summary = "boom"
    with patch("app.services.notifications.httpx.post"):
        notify_review_terminal(db, review)
    db.commit()

    notifications = db.query(Notification).all()
    assert len(notifications) == 1
    assert notifications[0].type == "review_failed"
    assert "boom" in notifications[0].message


def test_failed_quality_gate_creates_extra_notification() -> None:
    db = _make_session()
    review = _seed_review(db, "completed", sonar_quality_gate="ERROR")
    with patch.object(settings, "sonarqube_enabled", True), patch(
        "app.services.notifications.httpx.post"
    ):
        notify_review_terminal(db, review)
    db.commit()

    types = {n.type for n in db.query(Notification).all()}
    assert types == {"review_completed", "quality_gate_failed"}


def test_slack_webhook_posted_when_configured() -> None:
    db = _make_session()
    review = _seed_review(db, "completed")
    with patch.object(settings, "slack_webhook_url", "https://hooks.slack.test/x"), patch(
        "app.services.notifications.httpx.post"
    ) as mock_post:
        notify_review_terminal(db, review)
    db.commit()

    mock_post.assert_called_once()


def test_slack_failure_does_not_raise() -> None:
    db = _make_session()
    review = _seed_review(db, "completed")
    with patch.object(settings, "slack_webhook_url", "https://hooks.slack.test/x"), patch(
        "app.services.notifications.httpx.post", side_effect=RuntimeError("network down")
    ):
        notify_review_terminal(db, review)  # must not raise
    db.commit()

    assert db.query(Notification).count() == 1
