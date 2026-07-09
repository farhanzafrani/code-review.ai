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


def test_callback_missing_state_rejected_for_plain_login(client: TestClient) -> None:
    # No oauth_state cookie set (as if login() was never called) and no
    # state param either — must be rejected, not silently accepted.
    resp = client.get("/auth/github/callback", params={"code": "abc"}, follow_redirects=False)
    assert resp.status_code == 400


def test_callback_mismatched_state_rejected(client: TestClient) -> None:
    client.cookies.set("oauth_state", "xyz")
    resp = client.get(
        "/auth/github/callback",
        params={"code": "abc", "state": "not-xyz"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_callback_accepts_installation_flow_without_state(client: TestClient) -> None:
    """Installing the App directly from GitHub (with "Request user
    authorization during installation" on) redirects here with
    `installation_id`/`setup_action=install` and NO `state` at all, since
    we never initiated that flow — there's no login() call to have set the
    oauth_state cookie either. Real regression: this used to be a hard 422
    because `state` was a required parameter, discovered by actually
    installing a real GitHub App rather than by a unit test.
    """
    with (
        patch("app.api.routes.auth.exchange_oauth_code", return_value="gh-access-token"),
        patch(
            "app.api.routes.auth.fetch_github_user",
            return_value={"id": 1, "login": "octocat", "email": None, "avatar_url": None},
        ),
    ):
        resp = client.get(
            "/auth/github/callback",
            params={"code": "abc", "installation_id": "12345", "setup_action": "install"},
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    assert "#token=" in resp.headers["location"]
