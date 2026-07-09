from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class Notification(Base):
    """A global feed, not per-user — the app has no repo/PR ownership model
    to scope notifications to a specific user yet (any authenticated user
    can see every connected repo). Marking one read is a shared action
    across all users, matching that existing level of tenancy rather than
    inventing a per-user read-state model the rest of the app doesn't have.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))  # review_completed|review_failed|quality_gate_failed
    message: Mapped[str] = mapped_column(String(512))
    pull_request_id: Mapped[int | None] = mapped_column(ForeignKey("pull_requests.id"), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
