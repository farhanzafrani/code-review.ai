"""Regression tests for a real leak: git/sonar-scanner failures used to
stringify their full argv (including the GitHub installation token and the
Sonar token), and that string got persisted to Review.sonar_result, posted
into the GitHub PR comment, and logged — on every failed quality gate, not
just rare errors. See app/services/sonar.py's _run_no_secrets docstring.
"""

import subprocess
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services import sonar

FAKE_TOKEN = "ghs_supersecretinstallationtoken"  # noqa: S105
FAKE_SONAR_TOKEN = "squ_supersecretsonartoken"  # noqa: S105


def test_checkout_pr_head_failure_does_not_leak_token(tmp_path) -> None:
    dest = tmp_path / "checkout"
    with patch(
        "app.services.sonar.subprocess.run",
        side_effect=subprocess.CalledProcessError(
            128, ["git", "clone", "--depth", "1", "--no-checkout", f"https://x-access-token:{FAKE_TOKEN}@github.com/acme/widgets.git", str(dest)]
        ),
    ):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            sonar.checkout_pr_head("acme", "widgets", 1, FAKE_TOKEN, str(dest))

    assert FAKE_TOKEN not in str(exc_info.value)
    assert exc_info.value.cmd == "git clone"


def test_run_scanner_failure_does_not_leak_sonar_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "sonarqube_token", FAKE_SONAR_TOKEN)
    with patch(
        "app.services.sonar.subprocess.run",
        side_effect=subprocess.CalledProcessError(
            1, ["sonar-scanner", f"-Dsonar.token={FAKE_SONAR_TOKEN}"]
        ),
    ):
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            sonar.run_scanner("key", "name", str(tmp_path))

    assert FAKE_SONAR_TOKEN not in str(exc_info.value)


def test_run_scanner_passes_token_via_env_not_argv(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "sonarqube_token", FAKE_SONAR_TOKEN)
    with patch("app.services.sonar.subprocess.run") as mock_run:
        sonar.run_scanner("key", "name", str(tmp_path))

    args, kwargs = mock_run.call_args
    assert not any(FAKE_SONAR_TOKEN in arg for arg in args[0])
    assert kwargs["env"]["SONAR_TOKEN"] == FAKE_SONAR_TOKEN


def test_checkout_pr_head_does_not_embed_token_in_remote_url(tmp_path) -> None:
    dest = tmp_path / "checkout"
    with patch("app.services.sonar.subprocess.run") as mock_run:
        sonar.checkout_pr_head("acme", "widgets", 1, FAKE_TOKEN, str(dest))

    for call in mock_run.call_args_list:
        cmd = call.args[0]
        assert not any(FAKE_TOKEN in arg for arg in cmd)
