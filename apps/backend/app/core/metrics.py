import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)


def _path_template(request: Request) -> str:
    # The route's path template (e.g. "/pull-requests/{pull_request_id}"),
    # not the raw URL — using raw paths would give every PR id its own
    # label value and blow up Prometheus's cardinality.
    route = request.scope.get("route")
    return route.path if route is not None else request.url.path


async def prometheus_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    path = _path_template(request)
    HTTP_REQUESTS_TOTAL.labels(request.method, path, response.status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(request.method, path).observe(duration)
    return response


def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
