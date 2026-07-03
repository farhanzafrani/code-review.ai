from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.review import Review
from app.models.user import User
from app.schemas.pull_request import PullRequestOut
from app.schemas.repository import RepositoryOut

router = APIRouter(prefix="/repositories", tags=["repositories"])


def _latest_review(db: Session, pull_request_id: int) -> Review | None:
    return (
        db.query(Review)
        .filter(Review.pull_request_id == pull_request_id)
        .order_by(Review.created_at.desc())
        .first()
    )


@router.get("", response_model=list[RepositoryOut])
def list_repositories(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Repository]:
    return db.query(Repository).filter(Repository.is_active.is_(True)).order_by(Repository.full_name).all()


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> None:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    repo.is_active = False
    db.commit()


@router.get("/{repository_id}/pull-requests", response_model=list[PullRequestOut])
def list_pull_requests(
    repository_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[PullRequest]:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")

    prs = (
        db.query(PullRequest)
        .filter(PullRequest.repository_id == repository_id)
        .order_by(PullRequest.created_at.desc())
        .all()
    )
    for pr in prs:
        pr.latest_review = _latest_review(db, pr.id)
    return prs
