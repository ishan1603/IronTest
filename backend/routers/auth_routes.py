"""GitHub OAuth sign-in."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import github_client
from auth import current_user
from config import get_settings
from db import User, get_session, utcnow
from security import create_session_token, encrypt_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# The OAuth state is a short-lived signed token rather than server-side
# storage, so CSRF protection survives a restart and multiple workers.
STATE_TTL_MINUTES = 10
STATE_AUDIENCE = "github-oauth-state"


def _issue_state() -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "aud": STATE_AUDIENCE,
            "nonce": secrets.token_urlsafe(16),
            "iat": now,
            "exp": now + timedelta(minutes=STATE_TTL_MINUTES),
        },
        settings.resolved_secret_key(),
        algorithm=settings.jwt_algorithm,
    )


def _state_is_valid(state: str) -> bool:
    settings = get_settings()
    try:
        jwt.decode(
            state,
            settings.resolved_secret_key(),
            algorithms=[settings.jwt_algorithm],
            audience=STATE_AUDIENCE,
        )
        return True
    except jwt.PyJWTError:
        return False


def _redirect_to_frontend(**params: str) -> RedirectResponse:
    settings = get_settings()
    return RedirectResponse(f"{settings.frontend_url.rstrip('/')}/auth/callback?{urlencode(params)}")


@router.get("/github/login")
async def github_login():
    """Begin the OAuth dance."""
    settings = get_settings()
    if not settings.github_oauth_configured:
        raise HTTPException(
            status_code=503,
            detail="GitHub sign-in is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.",
        )
    return RedirectResponse(github_client.authorize_url(_issue_state()))


@router.get("/github/callback")
async def github_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: Session = Depends(get_session),
):
    """Complete OAuth and hand the frontend a session token.

    Failures redirect back to the UI with a message rather than rendering an
    API error page the user cannot act on.
    """
    if error:
        return _redirect_to_frontend(error=error)
    if not code or not state:
        return _redirect_to_frontend(error="GitHub did not return an authorization code.")
    if not _state_is_valid(state):
        return _redirect_to_frontend(error="Sign-in request expired. Please try again.")

    try:
        access_token, scopes = await github_client.exchange_code_for_token(code)
        profile = await github_client.fetch_viewer(access_token)
    except github_client.GitHubError as exc:
        logger.warning("OAuth callback failed: %s", exc)
        return _redirect_to_frontend(error=str(exc))

    user = session.scalar(select(User).where(User.github_id == profile["github_id"]))
    if user is None:
        user = User(github_id=profile["github_id"], login=profile["login"])
        session.add(user)

    # Refresh on every login: the profile or granted scopes may have changed.
    user.login = profile["login"]
    user.name = profile["name"]
    user.email = profile["email"]
    user.avatar_url = profile["avatar_url"]
    user.encrypted_access_token = encrypt_token(access_token)
    user.token_scopes = scopes
    user.last_login_at = utcnow()

    session.commit()

    return _redirect_to_frontend(token=create_session_token(user.id))


@router.get("/me")
async def me(user: User = Depends(current_user)):
    """The signed-in user. Never includes the GitHub token."""
    return {
        "id": user.id,
        "login": user.login,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/api-key")
async def get_api_key(user: User = Depends(current_user)):
    return {"api_key": user.api_key}


@router.post("/api-key")
async def rotate_api_key(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user.api_key = "irt_" + secrets.token_urlsafe(28)
    session.commit()
    return {"api_key": user.api_key}


@router.delete("/api-key", status_code=204)
async def revoke_api_key(user: User = Depends(current_user), session: Session = Depends(get_session)):
    user.api_key = None
    session.commit()


@router.post("/logout")
async def logout(user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Drop the stored GitHub token.

    Session JWTs are stateless and stay valid until they expire; clearing the
    GitHub token is what actually revokes this server's access to the user's
    code, which is the meaningful part.
    """
    user.encrypted_access_token = None
    user.token_scopes = ""
    session.commit()
    return {"status": "signed_out"}
