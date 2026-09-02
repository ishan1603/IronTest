"""Request authentication.

Every data route depends on current_user, so an unauthenticated request is
rejected before any handler runs rather than relying on each handler to check.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from db import User, get_session
from security import decrypt_token, read_session_token


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """The signed-in user, or 401."""
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with GitHub to continue.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = read_session_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account no longer exists.",
        )
    return user


def optional_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User | None:
    """Like current_user, but returns None instead of raising."""
    token = _bearer_token(authorization)
    if not token:
        return None
    user_id = read_session_token(token)
    return session.get(User, user_id) if user_id else None


def github_token(user: User = Depends(current_user)) -> str:
    """The user's decrypted GitHub token, or 401 when re-auth is needed."""
    token = decrypt_token(user.encrypted_access_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GitHub access has expired. Please reconnect your account.",
        )
    return token
