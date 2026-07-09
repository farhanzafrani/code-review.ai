"""Fixed-window rate limiting, keyed by client IP, backed by Redis (already
a dependency — no new service needed). The webhook endpoint is the more
exposed one (unauthenticated, internet-facing, and the entry point into
the whole review pipeline), so it gets a tighter window than the rest of
the API.
"""

import time

import redis
from fastapi import Request
from starlette.responses import JSONResponse

from app.core.config import settings

_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)

WEBHOOK_LIMIT = 60
WEBHOOK_WINDOW_SECONDS = 60
API_LIMIT = 120
API_WINDOW_SECONDS = 60

_EXEMPT_PATHS = {"/health", "/metrics"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """True if this request is allowed (and has been counted against the
    window); False if the caller is over the limit.

    Fails open on a Redis error — a broker hiccup must never take down the
    whole API's ability to serve requests just because it also can't count
    them.
    """
    try:
        bucket = f"ratelimit:{key}:{int(time.time() // window_seconds)}"
        count = _redis.incr(bucket)
        if count == 1:
            _redis.expire(bucket, window_seconds)
        return count <= limit
    except Exception:
        return True


async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path in _EXEMPT_PATHS:
        return await call_next(request)

    ip = _client_ip(request)
    if path.startswith("/webhooks"):
        allowed = check_rate_limit(f"webhook:{ip}", WEBHOOK_LIMIT, WEBHOOK_WINDOW_SECONDS)
    else:
        allowed = check_rate_limit(f"api:{ip}", API_LIMIT, API_WINDOW_SECONDS)

    if not allowed:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    return await call_next(request)
