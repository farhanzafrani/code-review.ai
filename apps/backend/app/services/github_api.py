"""Per-repository GitHub REST calls made with an installation access token.

Distinct from `github_app.py`, which handles app-level auth (the app's own
JWT, installation tokens, and the user sign-in OAuth exchange).
"""

import httpx

GITHUB_API = "https://api.github.com"


def get_pr_diff(token: str, owner: str, repo: str, pr_number: int) -> str:
    """Return the unified diff text for a PR."""
    resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.text


def post_pr_review(
    token: str,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    event: str = "COMMENT",
) -> dict:
    """Post a top-level PR review (not per-line comments) with the given body."""
    resp = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"body": body, "event": event},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()
