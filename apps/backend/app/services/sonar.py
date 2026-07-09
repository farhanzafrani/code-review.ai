"""SonarQube integration: static analysis to run alongside the AI review.

Off by default (settings.sonarqube_enabled) — this is the one integration
in the codebase that shells out to external tools (git, sonar-scanner)
against a real checkout of the PR, rather than just calling an HTTP API,
so it needs a running SonarQube instance and a scanner-capable image to
mean anything. See README for setup.
"""

import logging
import os
import stat
import subprocess
import tempfile

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 300
GIT_TIMEOUT_SECONDS = 60


def project_key(repository_id: int) -> str:
    return f"codereviewai_{repository_id}"


def _auth() -> tuple[str, str]:
    return (settings.sonarqube_token, "")


def _run_no_secrets(cmd: list[str], description: str, **kwargs) -> None:
    """subprocess.run(cmd, check=True, ...), but on failure raises with
    `description` in place of the real argv.

    subprocess.CalledProcessError/TimeoutExpired stringify their full argv
    — callers here pass GitHub tokens and the Sonar token as command
    arguments, and those exceptions end up persisted to Review.sonar_result
    and posted straight into the GitHub PR comment (format_sonar_section
    renders result["error"]), plus logged. A failed clone or a failed
    quality gate (an expected, routine outcome, not a rare error path) must
    never leak either token there. `from None` also suppresses the original
    exception from the traceback Python prints, not just its top-level str().
    """
    try:
        subprocess.run(cmd, check=True, capture_output=True, **kwargs)
    except subprocess.CalledProcessError as exc:
        raise subprocess.CalledProcessError(exc.returncode, description) from None
    except subprocess.TimeoutExpired as exc:
        raise subprocess.TimeoutExpired(description, exc.timeout) from None


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
    """Shallow-clone the repo and check out the PR's head commit into dest_dir.

    The installation token is handed to git via GIT_ASKPASS rather than
    embedded in the remote URL — not just so it can't show up in a
    sanitized exception's argv, but so git's own stderr (e.g. on an auth
    failure, which often echoes back the URL it tried) can't echo it back
    either. The askpass script is a separate temp file, not inside
    dest_dir: `git clone` requires its target directory to be empty.
    """
    askpass_fd, askpass_path = tempfile.mkstemp(prefix="sonar-askpass-", suffix=".sh")
    try:
        with os.fdopen(askpass_fd, "w") as f:
            f.write(f"#!/bin/sh\necho '{token}'\n")
        os.chmod(askpass_path, stat.S_IRWXU)

        env = {**os.environ, "GIT_ASKPASS": askpass_path, "GIT_TERMINAL_PROMPT": "0"}
        remote = f"https://x-access-token@github.com/{owner}/{repo_name}.git"

        _run_no_secrets(
            ["git", "clone", "--depth", "1", "--no-checkout", remote, dest_dir],
            "git clone",
            env=env,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        _run_no_secrets(
            ["git", "fetch", "--depth", "1", "origin", f"refs/pull/{pr_number}/head"],
            "git fetch",
            cwd=dest_dir,
            env=env,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    finally:
        os.remove(askpass_path)

    _run_no_secrets(
        ["git", "checkout", "FETCH_HEAD"],
        "git checkout",
        cwd=dest_dir,
        timeout=GIT_TIMEOUT_SECONDS,
    )


def run_scanner(key: str, name: str, source_dir: str) -> None:
    """Run sonar-scanner against source_dir, blocking until the quality gate
    is computed. Raises subprocess.CalledProcessError on scan/gate failure —
    a failed quality gate is a normal outcome the caller should still record,
    not treat as an infrastructure error (see run_sonar_scan in tasks.py).

    The token goes in via SONAR_TOKEN (supported since scanner-cli 4.7+),
    not a -D flag: a -Dsonar.token=... argument would otherwise sit in this
    subprocess's argv on every single failed-quality-gate run — the normal
    case this function is explicitly designed to let happen, not the rare
    exception — and _run_no_secrets only protects the exception path.
    """
    env = {**os.environ, "SONAR_TOKEN": settings.sonarqube_token}
    _run_no_secrets(
        [
            "sonar-scanner",
            f"-Dsonar.projectKey={key}",
            f"-Dsonar.projectName={name}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={settings.sonarqube_url}",
            "-Dsonar.qualitygate.wait=true",
            "-Dsonar.qualitygate.timeout=120",
        ],
        "sonar-scanner",
        cwd=source_dir,
        env=env,
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
