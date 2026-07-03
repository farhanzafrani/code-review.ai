from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.pull_request import PullRequest


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|running|completed|failed
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Independent Sonar pipeline — None/unset when Sonar isn't enabled for
    # the deployment, so it never blocks the AI pipeline's own comment.
    sonar_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sonar_quality_gate: Mapped[str | None] = mapped_column(String(16), nullable=True)  # OK|ERROR|NONE
    sonar_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # GitHub review id, so a second pipeline finishing later can update
    # the same comment instead of posting a duplicate.
    github_review_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pull_request: Mapped["PullRequest"] = relationship()  # noqa: F821
