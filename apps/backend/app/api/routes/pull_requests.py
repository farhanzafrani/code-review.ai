from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User
from app.schemas.generation import GenerationResult
from app.schemas.pull_request import PullRequestDetailOut
from app.services.ai_generate import generate_docs, generate_tests
from app.services.github_api import get_pr_diff
from app.services.github_app import get_installation_access_token
from app.services.task_log import get_logs

router = APIRouter(prefix="/pull-requests", tags=["pull-requests"])


def _get_pr_or_404(db: Session, pull_request_id: int) -> PullRequest:
    pr = db.get(PullRequest, pull_request_id)
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pull request not found")
    return pr


def _fetch_diff(db: Session, pr: PullRequest) -> str:
    repo = db.get(Repository, pr.repository_id)
    owner, repo_name = repo.full_name.split("/", 1)
    token = get_installation_access_token(repo.github_installation_id)
    return get_pr_diff(token, owner, repo_name, pr.number)


@router.get("/{pull_request_id}", response_model=PullRequestDetailOut)
def get_pull_request(
    pull_request_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> PullRequest:
    pr = _get_pr_or_404(db, pull_request_id)
    repo = db.get(Repository, pr.repository_id)
    pr.repository_full_name = repo.full_name
    pr.latest_review = (
        db.query(Review)
        .filter(Review.pull_request_id == pr.id)
        .order_by(Review.created_at.desc())
        .first()
    )
    return pr


@router.get("/{pull_request_id}/diff", response_class=PlainTextResponse)
def get_pull_request_diff(
    pull_request_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> str:
    pr = _get_pr_or_404(db, pull_request_id)
    return _fetch_diff(db, pr)


@router.get("/{pull_request_id}/logs")
def get_pull_request_logs(
    pull_request_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    pr = _get_pr_or_404(db, pull_request_id)
    review = (
        db.query(Review)
        .filter(Review.pull_request_id == pr.id)
        .order_by(Review.created_at.desc())
        .first()
    )
    if review is None:
        return {"lines": []}
    return {"lines": get_logs(review.id)}


@router.post("/{pull_request_id}/generate-tests", response_model=GenerationResult)
def post_generate_tests(
    pull_request_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    pr = _get_pr_or_404(db, pull_request_id)
    diff = _fetch_diff(db, pr)
    return generate_tests(diff, pr.title)


@router.post("/{pull_request_id}/generate-docs", response_model=GenerationResult)
def post_generate_docs(
    pull_request_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    pr = _get_pr_or_404(db, pull_request_id)
    diff = _fetch_diff(db, pr)
    return generate_docs(diff, pr.title)
