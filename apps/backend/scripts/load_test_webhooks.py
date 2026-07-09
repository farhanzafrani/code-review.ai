"""Load-test the webhook -> Celery -> AI pipeline with a burst of synthetic
`pull_request` webhooks, fired concurrently at a real running backend.

Deliberately doesn't touch GitHub or OpenAI — it fires at this app's own
/webhooks/github with a fake installation, so the downstream AI/Sonar
tasks fail fast (no real installation to fetch a token for) once they hit
the worker. That's fine for what this measures: whether the webhook
endpoint, its rate limiter, and the DB writes hold up under a burst -
not whether a real AI review completes.

Usage:
    uv run python scripts/load_test_webhooks.py --count 200 --concurrency 20
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import time

import httpx


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payload(seq: int, repo_id: int) -> dict:
    return {
        "action": "opened",
        "installation": {"id": 999000 + repo_id},
        "repository": {
            "id": repo_id,
            "full_name": "loadtest/repo",
        },
        "pull_request": {
            "id": 500_000 + seq,
            "number": seq,
            "title": f"Load test PR #{seq}",
            "head": {"sha": f"{seq:040x}"},
            "base": {"sha": "0" * 40},
            "html_url": f"https://github.com/loadtest/repo/pull/{seq}",
            "state": "open",
        },
    }


async def _fire_one(
    client: httpx.AsyncClient, url: str, secret: str, seq: int, repo_id: int
) -> tuple[int, float]:
    body = json.dumps(_payload(seq, repo_id)).encode()
    headers = {
        "X-Hub-Signature-256": _sign(secret, body),
        "X-GitHub-Event": "pull_request",
        "Content-Type": "application/json",
    }
    start = time.perf_counter()
    try:
        resp = await client.post(url, content=body, headers=headers, timeout=20)
        return resp.status_code, time.perf_counter() - start
    except httpx.HTTPError:
        return -1, time.perf_counter() - start


async def run(url: str, secret: str, count: int, concurrency: int, repo_id: int) -> None:
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(seq: int) -> tuple[int, float]:
        async with semaphore:
            return await _fire_one(client, url, secret, seq, repo_id)

    async with httpx.AsyncClient() as client:
        start = time.perf_counter()
        results = await asyncio.gather(*(bounded(i) for i in range(1, count + 1)))
        wall_clock = time.perf_counter() - start

    statuses: dict[int, int] = {}
    latencies = []
    for status, latency in results:
        statuses[status] = statuses.get(status, 0) + 1
        latencies.append(latency)
    latencies.sort()

    def pct(p: float) -> float:
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    print(f"Sent {count} requests at concurrency {concurrency} in {wall_clock:.2f}s "
          f"({count / wall_clock:.1f} req/s)")
    print("Status code counts:", dict(sorted(statuses.items())))
    print(f"Latency (s): min={latencies[0]:.3f} p50={pct(0.5):.3f} "
          f"p95={pct(0.95):.3f} max={latencies[-1]:.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000/webhooks/github")
    parser.add_argument("--secret", required=True, help="GITHUB_APP_WEBHOOK_SECRET the backend is using")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--repo-id", type=int, default=1, help="synthetic repository id to burst against")
    args = parser.parse_args()

    asyncio.run(run(args.url, args.secret, args.count, args.concurrency, args.repo_id))
