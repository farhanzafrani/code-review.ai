"""SonarQube integration: static analysis to run alongside the AI review.

Off by default (settings.sonarqube_enabled) — this is the one integration
in the codebase that shells out to external tools (git, sonar-scanner)
against a real checkout of the PR, rather than just calling an HTTP API,
so it needs a running SonarQube instance and a scanner-capable image to
mean anything. See README for setup.
"""

import logging
import subprocess

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 300
GIT_TIMEOUT_SECONDS = 60


def project_key(repository_id: int) -> str:
    return f"codereviewai_{repository_id}"


def _auth() -> tuple[str, str]:
    return (settings.sonarqube_token, "")


def ensure_project(key: str, name: str) -> None:
    """Create the Sonar project if it doesn't already exist."""
    resp = httpx.get(
        f"{settings.sonarqube_url}/api/projects/search",
        params={"projects": key},
        auth=_auth(),
        timeout=20,
    )
    resp.raise_for_status()
    if resp.json().get("components"):
        return

    resp = httpx.post(
        f"{settings.sonarqube_url}/api/projects/create",
        params={"project": key, "name": name},
        auth=_auth(),
        timeout=20,
    )
    resp.raise_for_status()


def checkout_pr_head(owner: str, repo_name: str, pr_number: int, token: str, dest_dir: str) -> None:
    """Shallow-clone the repo and check out the PR's head commit into dest_dir."""
    remote = f"https://x-access-token:{token}@github.com/{owner}/{repo_name}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--no-checkout", remote, dest_dir],
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", f"refs/pull/{pr_number}/head"],
        cwd=dest_dir,
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    subprocess.run(
        ["git", "checkout", "FETCH_HEAD"],
        cwd=dest_dir,
        check=True,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )


def run_scanner(key: str, name: str, source_dir: str) -> None:
    """Run sonar-scanner against source_dir, blocking until the quality gate
    is computed. Raises subprocess.CalledProcessError on scan/gate failure —
    a failed quality gate is a normal outcome the caller should still record,
    not treat as an infrastructure error (see run_sonar_scan in tasks.py)."""
    subprocess.run(
        [
            "sonar-scanner",
            f"-Dsonar.projectKey={key}",
            f"-Dsonar.projectName={name}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={settings.sonarqube_url}",
            f"-Dsonar.token={settings.sonarqube_token}",
            "-Dsonar.qualitygate.wait=true",
            "-Dsonar.qualitygate.timeout=120",
        ],
        cwd=source_dir,
        check=True,
        capture_output=True,
        timeout=SCAN_TIMEOUT_SECONDS,
    )


def get_quality_gate_status(key: str) -> dict:
    resp = httpx.get(
        f"{settings.sonarqube_url}/api/qualitygates/project_status",
        params={"projectKey": key},
        auth=_auth(),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["projectStatus"]


def get_issues(key: str, max_issues: int = 100) -> list[dict]:
    resp = httpx.get(
        f"{settings.sonarqube_url}/api/issues/search",
        params={"componentKeys": key, "resolved": "false", "ps": max_issues},
        auth=_auth(),
        timeout=20,
    )
    resp.raise_for_status()
    return [
        {
            "rule": issue["rule"],
            "severity": issue["severity"],
            "message": issue["message"],
            "component": issue["component"],
            "line": issue.get("line"),
        }
        for issue in resp.json().get("issues", [])
    ]


_GATE_EMOJI = {"OK": "✅", "ERROR": "❌", "NONE": "⚪"}


def format_sonar_section(status: str | None, quality_gate: str | None, result: dict | None) -> str:
    lines = ["## 🛡️ SonarQube", ""]

    if status in (None, "pending", "running"):
        lines.append("Scan in progress…")
        lines.append("")
        return "\n".join(lines)

    if status == "failed":
        error = (result or {}).get("error", "unknown error")
        lines.append(f"Scan failed: {error}")
        lines.append("")
        return "\n".join(lines)

    emoji = _GATE_EMOJI.get(quality_gate or "NONE", "⚪")
    lines.append(f"**Quality Gate: {emoji} {quality_gate or 'NONE'}**")
    lines.append("")

    issues = (result or {}).get("issues", [])
    if issues:
        lines.append(f"### Issues ({len(issues)})")
        lines.append("")
        for issue in issues:
            loc = f"{issue['component']}:{issue['line']}" if issue.get("line") else issue["component"]
            lines.append(f"- **{issue['severity']}** `{loc}` — {issue['message']}")
        lines.append("")
    else:
        lines.append("No open issues.")
        lines.append("")

    return "\n".join(lines)
