from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.rate_limit import check_rate_limit
from app.main import app


class _FakeRedis:
    """In-memory stand-in for the handful of Redis calls check_rate_limit
    makes — this test suite has no live Redis to talk to, and the real
    fail-open behavior on a Redis error would otherwise mask every one of
    these assertions (every call would just return True)."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def expire(self, key: str, seconds: int) -> None:
        pass


def test_check_rate_limit_allows_under_limit() -> None:
    with patch("app.core.rate_limit._redis", _FakeRedis()):
        for _ in range(5):
            assert check_rate_limit("k", limit=5, window_seconds=60) is True


def test_check_rate_limit_rejects_over_limit() -> None:
    with patch("app.core.rate_limit._redis", _FakeRedis()):
        for _ in range(3):
            assert check_rate_limit("k", limit=3, window_seconds=60) is True
        assert check_rate_limit("k", limit=3, window_seconds=60) is False


def test_check_rate_limit_keys_are_independent() -> None:
    with patch("app.core.rate_limit._redis", _FakeRedis()):
        assert check_rate_limit("key-a", limit=1, window_seconds=60) is True
        assert check_rate_limit("key-a", limit=1, window_seconds=60) is False
        assert check_rate_limit("key-b", limit=1, window_seconds=60) is True


def test_check_rate_limit_fails_open_on_redis_error() -> None:
    class _BrokenRedis:
        def incr(self, key: str) -> int:
            raise ConnectionError("redis is down")

    with patch("app.core.rate_limit._redis", _BrokenRedis()):
        assert check_rate_limit("k", limit=1, window_seconds=60) is True
        assert check_rate_limit("k", limit=1, window_seconds=60) is True


def test_health_endpoint_is_exempt_from_rate_limiting() -> None:
    class _RejectAllRedis:
        def incr(self, key: str) -> int:
            return 999999

        def expire(self, key: str, seconds: int) -> None:
            pass

    with patch("app.core.rate_limit._redis", _RejectAllRedis()):
        client = TestClient(app)
        for _ in range(5):
            assert client.get("/health").status_code == 200
