import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.github_app import build_authorize_url, exchange_oauth_code, fetch_github_user

router = APIRouter(prefix="/auth/github", tags=["auth"])

CALLBACK_PATH = "/auth/github/callback"
STATE_COOKIE = "oauth_state"


@router.get("/login")
def login(response: Response) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    redirect_uri = f"{settings.backend_url}{CALLBACK_PATH}"
    redirect = RedirectResponse(build_authorize_url(redirect_uri, state))
    redirect.set_cookie(STATE_COOKIE, state, httponly=True, max_age=600, samesite="lax")
    return redirect


@router.get("/callback")
def callback(
    code: str,
    state: str,
    oauth_state: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not oauth_state or state != oauth_state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")

    redirect_uri = f"{settings.backend_url}{CALLBACK_PATH}"
    access_token = exchange_oauth_code(code, redirect_uri)
    profile = fetch_github_user(access_token)

    user = db.query(User).filter(User.github_id == profile["id"]).one_or_none()
    if user is None:
        user = User(
            github_id=profile["id"],
            github_login=profile["login"],
            email=profile.get("email"),
            avatar_url=profile.get("avatar_url"),
        )
        db.add(user)
    else:
        user.github_login = profile["login"]
        user.email = profile.get("email")
        user.avatar_url = profile.get("avatar_url")
    db.commit()
    db.refresh(user)

    jwt_token = create_access_token(subject=str(user.id))
    redirect = RedirectResponse(f"{settings.frontend_url}/auth/callback?token={jwt_token}")
    redirect.delete_cookie(STATE_COOKIE)
    return redirect
