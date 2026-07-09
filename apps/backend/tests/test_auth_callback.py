"""A session JWT in a ?token=... query param would land in this app's own
access logs, any reverse proxy's logs, and browser history — a URL
fragment (#token=...) never gets sent to a server at all. Regression test
for that fix (see Phase 8 in INSTRUCTIONS.md).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    app.dependency_overrides[get_db] = lambda: session_local()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_callback_redirects_with_fragment_not_query_param(client: TestClient) -> None:
    client.cookies.set("oauth_state", "xyz")
    with (
        patch("app.api.routes.auth.exchange_oauth_code", return_value="gh-access-token"),
        patch(
            "app.api.routes.auth.fetch_github_user",
            return_value={"id": 1, "login": "octocat", "email": None, "avatar_url": None},
        ),
    ):
        resp = client.get(
            "/auth/github/callback",
            params={"code": "abc", "state": "xyz"},
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "#token=" in location
    assert "?token=" not in location
