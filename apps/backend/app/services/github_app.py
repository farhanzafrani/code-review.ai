"""GitHub App integration: app-level JWT, installation tokens, and the
user "Sign in with GitHub" OAuth exchange (GitHub Apps reuse the same
/login/oauth/* endpoints as OAuth Apps when user authorization is enabled).
"""

import time

import httpx
import jwt

from app.core.config import settings

GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"


def generate_app_jwt() -> str:
    """Short-lived JWT identifying the GitHub App itself (RS256, max 10 min)."""
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": settings.github_app_id}
    with open(settings.github_app_private_key_path, "rb") as f:
        private_key = f.read()
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_access_token(installation_id: int) -> str:
    """Exchange the app JWT for a token scoped to one installation (repos)."""
    app_jwt = generate_app_jwt()
    resp = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def build_authorize_url(redirect_uri: str, state: str) -> str:
    return (
        f"{GITHUB_WEB}/login/oauth/authorize"
        f"?client_id={settings.github_app_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )


def exchange_oauth_code(code: str, redirect_uri: str) -> str:
    """Exchange a login callback code for a user access token."""
    resp = httpx.post(
        f"{GITHUB_WEB}/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.github_app_client_id,
            "client_secret": settings.github_app_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"GitHub OAuth exchange failed: {data}")
    return data["access_token"]


def fetch_github_user(access_token: str) -> dict:
    resp = httpx.get(
        f"{GITHUB_API}/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
