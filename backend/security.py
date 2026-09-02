"""Token encryption at rest and signed session tokens.

GitHub OAuth tokens grant read access to a user's private source, so they are
encrypted with a key derived from SECRET_KEY rather than stored as plaintext
columns. Session tokens are JWTs so the API stays stateless across the
multiple workers a free-tier host may run.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


def _fernet() -> Fernet:
    """Fernet key derived deterministically from SECRET_KEY.

    Rotating SECRET_KEY invalidates stored tokens, which forces a re-login
    rather than surfacing corrupt credentials.
    """
    secret = get_settings().resolved_secret_key().encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(raw: str) -> str:
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_token(stored: str | None) -> str:
    """Return the plaintext token, or "" when it cannot be decrypted."""
    if not stored:
        return ""
    try:
        return _fernet().decrypt(stored.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Key rotation or a corrupt row: treat as logged out, never raise.
        return ""


def create_session_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=settings.session_ttl_hours),
    }
    return jwt.encode(payload, settings.resolved_secret_key(), algorithm=settings.jwt_algorithm)


def read_session_token(token: str) -> str | None:
    """Return the user id from a valid token, else None."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.resolved_secret_key(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    return str(subject) if subject else None
