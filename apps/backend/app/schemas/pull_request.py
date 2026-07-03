from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.review import ReviewOut


class PullRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    title: str
    html_url: str
    state: str
    created_at: datetime
    updated_at: datetime
    latest_review: ReviewOut | None = None


class PullRequestDetailOut(PullRequestOut):
    repository_id: int
    repository_full_name: str
