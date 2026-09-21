"""Password hashing + JWT helpers.

Password hashing uses the ``bcrypt`` library directly (instead of passlib) because
passlib 1.7.4 is not compatible with bcrypt >= 4.1/5.x, and direct bcrypt is a
smaller, fully supported surface for this MVP.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt
from jose import JWTError, jwt

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY

# bcrypt only reads the first 72 bytes of a password.
_BCRYPT_MAX_BYTES = 72

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email or ""))


def _encode_password(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plain password with bcrypt (random salt per hash)."""
    return bcrypt.hashpw(_encode_password(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plain password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_encode_password(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int, expires_minutes: int | None = None
) -> str:
    """Create a signed JWT with the user id in the ``sub`` claim."""
    minutes = expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode a JWT; raises ``jose.JWTError`` when invalid/expired."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


__all__ = [
    "JWTError",
    "create_access_token",
    "decode_token",
    "hash_password",
    "is_valid_email",
    "verify_password",
]
