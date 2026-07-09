from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token


def test_roundtrip() -> None:
    token = create_access_token(subject="42")
    assert decode_access_token(token) == "42"


def test_expired_token_rejected() -> None:
    payload = {"sub": "42", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    expired = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)


def test_tampered_token_rejected() -> None:
    token = create_access_token(subject="42")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token + "tampered")
