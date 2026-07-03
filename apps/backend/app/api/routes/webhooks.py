import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.workers.tasks import index_repository_task, process_pull_request, run_sonar_scan

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


def _verify_signature(raw_body: bytes, signature_header: str | None) -> None:
    if not signature_header:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing signature")
    expected = "sha256=" + hmac.new(
        settings.github_app_webhook_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")


def _upsert_repository(db: Session, repo_payload: dict, installation_id: int) -> tuple[Repository, bool]:
    repo = db.query(Repository).filter(Repository.github_repo_id == repo_payload["id"]).one_or_none()
    created = False
    if repo is None:
        repo = Repository(
            github_repo_id=repo_payload["id"],
            full_name=repo_payload["full_name"],
            github_installation_id=installation_id,
        )
        db.add(repo)
        db.flush()
        created = True
    else:
        repo.full_name = repo_payload["full_name"]
        repo.is_active = True
    return repo, created


def _handle_installation(db: Session, payload: dict) -> list[int]:
    installation_id = payload["installation"]["id"]
    action = payload["action"]
    if action == "deleted":
        repos = db.query(Repository).filter(Repository.github_installation_id == installation_id)
        repos.update({Repository.is_active: False})
        return []
    new_repo_ids = []
    for repo_payload in payload.get("repositories", []):
        repo, created = _upsert_repository(db, repo_payload, installation_id)
        if created:
            new_repo_ids.append(repo.id)
    return new_repo_ids


def _handle_installation_repositories(db: Session, payload: dict) -> list[int]:
    installation_id = payload["installation"]["id"]
    new_repo_ids = []
    for repo_payload in payload.get("repositories_added", []):
        repo, created = _upsert_repository(db, repo_payload, installation_id)
        if created:
            new_repo_ids.append(repo.id)
    for repo_payload in payload.get("repositories_removed", []):
        repo = db.query(Repository).filter(Repository.github_repo_id == repo_payload["id"]).one_or_none()
        if repo:
            repo.is_active = False
    return new_repo_ids


def _handle_pull_request(db: Session, payload: dict) -> list[int]:
    if payload["action"] not in ("opened", "synchronize", "reopened"):
        return []

    installation_id = payload["installation"]["id"]
    repo, created = _upsert_repository(db, payload["repository"], installation_id)

    pr_payload = payload["pull_request"]
    pr = db.query(PullRequest).filter(PullRequest.github_pr_id == pr_payload["id"]).one_or_none()
    if pr is None:
        pr = PullRequest(
            repository_id=repo.id,
            github_pr_id=pr_payload["id"],
            number=pr_payload["number"],
            title=pr_payload["title"],
            head_sha=pr_payload["head"]["sha"],
            base_sha=pr_payload["base"]["sha"],
            html_url=pr_payload["html_url"],
            state=pr_payload["state"],
        )
        db.add(pr)
    else:
        pr.title = pr_payload["title"]
        pr.head_sha = pr_payload["head"]["sha"]
        pr.state = pr_payload["state"]
    db.flush()

    review = Review(pull_request_id=pr.id, status="pending")
    db.add(review)
    db.flush()

    db.commit()
    process_pull_request.delay(review.id)
    if settings.sonarqube_enabled:
        run_sonar_scan.delay(review.id)
    return [repo.id] if created else []


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()
    _verify_signature(raw_body, x_hub_signature_256)
    payload = await request.json()

    if x_github_event == "ping":
        return {"status": "pong"}

    db = SessionLocal()
    try:
        new_repo_ids: list[int] = []
        if x_github_event == "installation":
            new_repo_ids = _handle_installation(db, payload)
        elif x_github_event == "installation_repositories":
            new_repo_ids = _handle_installation_repositories(db, payload)
        elif x_github_event == "pull_request":
            new_repo_ids = _handle_pull_request(db, payload)
        else:
            logger.info("Ignoring unhandled GitHub event: %s", x_github_event)
        db.commit()
    finally:
        db.close()

    for repo_id in new_repo_ids:
        index_repository_task.delay(repo_id)

    return {"status": "accepted"}
