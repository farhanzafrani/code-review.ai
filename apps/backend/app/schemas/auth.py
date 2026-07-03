from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    github_login: str
    email: str | None
    avatar_url: str | None

    class Config:
        from_attributes = True
