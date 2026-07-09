from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    yield session
    session.close()


@pytest.fixture
def client(db_session: Session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, github_id=1, github_login="octocat"
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_pr(db: Session) -> PullRequest:
    repo = Repository(github_repo_id=1, full_name="acme/widgets", github_installation_id=1)
    db.add(repo)
    db.flush()
    pr = PullRequest(
        repository_id=repo.id,
        github_pr_id=1,
        number=1,
        title="t",
        head_sha="a",
        base_sha="b",
        html_url="https://github.com/acme/widgets/pull/1",
    )
    db.add(pr)
    db.commit()
    return pr


def test_logs_empty_when_no_review(client: TestClient, db_session: Session) -> None:
    pr = _seed_pr(db_session)
    resp = client.get(f"/pull-requests/{pr.id}/logs")
    assert resp.status_code == 200
    assert resp.json() == {"lines": []}


def test_logs_returns_latest_review_lines(client: TestClient, db_session: Session) -> None:
    pr = _seed_pr(db_session)
    review = Review(pull_request_id=pr.id, status="running")
    db_session.add(review)
    db_session.commit()

    with patch(
        "app.api.routes.pull_requests.get_logs", return_value=["[00:00:00] Starting…"]
    ) as mock_get_logs:
        resp = client.get(f"/pull-requests/{pr.id}/logs")

    assert resp.status_code == 200
    assert resp.json() == {"lines": ["[00:00:00] Starting…"]}
    mock_get_logs.assert_called_once_with(review.id)


def test_logs_404_for_unknown_pr(client: TestClient) -> None:
    resp = client.get("/pull-requests/999/logs")
    assert resp.status_code == 404
