"""Security utilities for encryption, decryption, and JWT session handling."""

import base64
import hashlib
import datetime
from typing import Optional, Dict, Any
import jwt
from cryptography.fernet import Fernet

from .settings import settings


def _get_fernet_key() -> bytes:
    """Derives a deterministic 32-byte url-safe base64 Fernet key from the JWT_SECRET_KEY."""
    digest = hashlib.sha256(settings.JWT_SECRET_KEY.encode("utf-8")).digest()
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


def create_access_token(data: Dict[str, Any], expires_delta: Optional[datetime.timedelta] = None) -> str:
    """Generates a signed JWT session token containing user claims."""
    to_encode = data.copy()
    now = datetime.datetime.now(datetime.timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a signed JWT session token. Returns payload dict or None."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except (jwt.PyJWTError, Exception):
        return None
