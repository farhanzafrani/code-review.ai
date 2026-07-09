import http.server
import os
import tempfile
import threading
import time

# Must be set before prometheus_client's Counter/Histogram are constructed
# below: Celery's default pool is prefork, so tasks actually execute in
# forked child processes, not the parent that serves /metrics. Without
# multiprocess mode, each child increments its own private copy of the
# metric and the parent's HTTP server never sees it. This env var switches
# prometheus_client to write per-process counters to disk and aggregate
# them at scrape time instead.
os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", tempfile.mkdtemp(prefix="prometheus_multiproc_"))

from celery import Celery  # noqa: E402
from celery.signals import (  # noqa: E402
    after_setup_logger,
    after_setup_task_logger,
    task_postrun,
    task_prerun,
    worker_process_shutdown,
    worker_ready,
)
from prometheus_client import (  # noqa: E402
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

from app.core.config import settings  # noqa: E402
from app.core.logging import JSONFormatter  # noqa: E402

TASKS_TOTAL = Counter("celery_tasks_total", "Total Celery tasks", ["task", "state"])
TASK_DURATION_SECONDS = Histogram(
    "celery_task_duration_seconds", "Celery task duration", ["task"]
)
_task_start_times: dict[str, float] = {}

celery_app = Celery(
    "codereviewai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@after_setup_logger.connect
@after_setup_task_logger.connect
def _use_json_formatter(logger, **kwargs) -> None:
    # Celery installs its own handlers/formatters on worker startup, which
    # would otherwise override app.core.logging's plain-text default — so
    # re-format its handlers here instead of fighting that setup.
    for handler in logger.handlers:
        handler.setFormatter(JSONFormatter())


class _MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # keep worker logs clean
        pass


@worker_ready.connect
def _start_metrics_server(**kwargs) -> None:
    server = http.server.HTTPServer(("0.0.0.0", settings.worker_metrics_port), _MetricsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


@worker_process_shutdown.connect
def _cleanup_multiproc_files(pid=None, **kwargs) -> None:
    if pid is not None:
        multiprocess.mark_process_dead(pid)


@task_prerun.connect
def _record_task_start(task_id, **kwargs) -> None:
    _task_start_times[task_id] = time.perf_counter()


@task_postrun.connect
def _record_task_end(task_id, task, state, **kwargs) -> None:
    start = _task_start_times.pop(task_id, None)
    if start is not None:
        TASK_DURATION_SECONDS.labels(task.name).observe(time.perf_counter() - start)
    TASKS_TOTAL.labels(task.name, state).inc()
