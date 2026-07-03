"""Per-repository GitHub REST calls made with an installation access token.

Distinct from `github_app.py`, which handles app-level auth (the app's own
JWT, installation tokens, and the user sign-in OAuth exchange).
"""

import base64

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


def update_pr_review(
    token: str,
    owner: str,
    repo: str,
    pr_number: int,
    review_id: int,
    body: str,
) -> dict:
    """Edit the body of an already-submitted PR review (e.g. to merge in
    results that finished after the review was first posted)."""
    resp = httpx.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"body": body},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def get_default_branch(token: str, owner: str, repo: str) -> str:
    resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["default_branch"]


def list_repo_files(token: str, owner: str, repo: str, ref: str) -> list[dict]:
    """Return blob entries ({path, size}) from the repo tree at `ref`, recursively."""
    resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params={"recursive": "1"},
        timeout=30,
    )
    resp.raise_for_status()
    tree = resp.json().get("tree", [])
    return [
        {"path": entry["path"], "size": entry.get("size", 0)}
        for entry in tree
        if entry.get("type") == "blob"
    ]


def get_file_content(token: str, owner: str, repo: str, path: str, ref: str) -> str | None:
    """Return a text file's decoded content, or None if it's missing/binary."""
    resp = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        params={"ref": ref},
        timeout=20,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8")
    except UnicodeDecodeError:
        return None
