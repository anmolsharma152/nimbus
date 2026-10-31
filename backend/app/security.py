"""Security utilities for encryption, decryption, and JWT session handling."""

import base64
import hashlib
import hmac
import datetime
from typing import Optional, Dict, Any
import jwt
from cryptography.fernet import Fernet

from .settings import settings, secret_value


def _jwt_secret() -> str:
    return secret_value(settings.JWT_SECRET_KEY)


def _get_fernet_key() -> bytes:
    """Derives a deterministic 32-byte url-safe base64 Fernet key from the JWT_SECRET_KEY."""
    digest = hashlib.sha256(_jwt_secret().encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypts a plaintext secret string (e.g. GitHub OAuth token or API key) using Fernet."""
    if not plaintext:
        return None
    f = Fernet(_get_fernet_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts a ciphertext string back to plaintext. Returns None if invalid or empty."""
    if not ciphertext:
        return None
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        # If it was already plaintext or decryption failed, return original if non-empty
        return ciphertext


def internal_api_token() -> str:
    """Derives the shared worker -> API token from JWT_SECRET_KEY so both processes agree without extra config."""
    return hmac.new(
        _jwt_secret().encode("utf-8"), b"nimbus-internal-events", hashlib.sha256
    ).hexdigest()


def verify_internal_api_token(token: Optional[str]) -> bool:
    """Constant-time check of a worker-supplied internal token."""
    return bool(token) and hmac.compare_digest(token, internal_api_token())


def create_access_token(data: Dict[str, Any], expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Generates a signed JWT session token containing user claims."""
    to_encode = data.copy()
    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, _jwt_secret(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a signed JWT session token. Returns payload dict or None."""
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except (jwt.PyJWTError, Exception):
        return None


STREAM_TICKET_PURPOSE = "task_stream"
STREAM_TICKET_TTL = datetime.timedelta(seconds=60)


def create_stream_ticket(user_id: int, task_id: int) -> str:
    """Short-lived token for one task's WebSocket stream.

    The browser connects to the API's WebSocket directly (the frontend's /api proxy can't carry
    upgrades), where the first-party session cookie isn't sent. The ticket goes in the URL instead,
    so it is scoped to one task, expires quickly, and is never accepted as a session.
    """
    return create_access_token(
        {"sub": str(user_id), "task_id": task_id, "purpose": STREAM_TICKET_PURPOSE},
        expires_delta=STREAM_TICKET_TTL,
    )


def verify_stream_ticket(ticket: Optional[str], task_id: int) -> Optional[str]:
    """Returns the ticket's user id (as a string) if it is a valid stream ticket for this task."""
    payload = decode_access_token(ticket) if ticket else None
    if not payload or payload.get("purpose") != STREAM_TICKET_PURPOSE or payload.get("task_id") != task_id:
        return None
    return payload.get("sub")
