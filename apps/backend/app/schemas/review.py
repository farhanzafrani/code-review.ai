from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    summary: str | None
    raw_result: dict | None
    created_at: datetime
    updated_at: datetime
