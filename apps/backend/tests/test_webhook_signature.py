import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app.api.routes.webhooks import _verify_signature
from app.core.config import settings


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(
        settings.github_app_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()


def test_valid_signature_passes() -> None:
    body = b'{"action": "opened"}'
    _verify_signature(body, _sign(body))


def test_missing_signature_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _verify_signature(b"{}", None)
    assert exc_info.value.status_code == 401


def test_invalid_signature_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _verify_signature(b'{"action": "opened"}', "sha256=deadbeef")
    assert exc_info.value.status_code == 401


def test_signature_for_different_body_rejected() -> None:
    signature = _sign(b'{"action": "opened"}')
    with pytest.raises(HTTPException) as exc_info:
        _verify_signature(b'{"action": "closed"}', signature)
    assert exc_info.value.status_code == 401
