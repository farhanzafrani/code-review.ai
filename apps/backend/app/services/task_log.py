"""Redis-backed step-by-step log lines for a single review's pipeline run,
so the dashboard can show "live" progress instead of just a status enum.

Deliberately not persisted to Postgres — this is transient progress
output, not an audit trail, so a capped/expiring Redis list is the
simplest tool that satisfies the phase.
"""

import logging
from datetime import datetime, timezone

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)

_MAX_LINES = 200
_TTL_SECONDS = 3600


def _key(review_id: int) -> str:
    return f"review_logs:{review_id}"


def append_log(review_id: int, message: str) -> None:
    """Best-effort: a Redis hiccup must never fail the review pipeline
    it's merely narrating — logged, not retried."""
    try:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        key = _key(review_id)
        _redis.rpush(key, f"[{timestamp}] {message}")
        _redis.ltrim(key, -_MAX_LINES, -1)
        _redis.expire(key, _TTL_SECONDS)
    except Exception:
        logger.exception("Failed to append pipeline log for review %s", review_id)


def get_logs(review_id: int) -> list[str]:
    try:
        return _redis.lrange(_key(review_id), 0, -1)
    except Exception:
        logger.exception("Failed to read pipeline logs for review %s", review_id)
        return []
