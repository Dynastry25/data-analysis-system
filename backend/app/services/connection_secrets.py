"""Encryption for connection credentials (plan 3.4).

A connection's password, API key or token is the most sensitive
thing a data platform holds on a user's behalf, and the blast radius
of getting it wrong is the user's *database*, not just their rows in
ours. So the secret is encrypted at rest with a key derived from
``SECRET_KEY``, never returned by any endpoint, and never logged.

Two rules, both of them load-bearing:

* **The key comes from ``SECRET_KEY`` by derivation, not by being the
  secret itself.** A direct Fernet key would be stable but would
  force ``SECRET_KEY`` into a specific format; deriving with PBKDF2
  lets the operator keep the secret format they already have. The
  cost is one derivation per process, cached.
* **A wrong key fails loudly and safely.** If ``SECRET_KEY`` has
  changed since the credential was written, decryption raises rather
  than returning garbage -- an operator can then re-enter the
  password. Silently treating a broken ciphertext as "no password"
  would send a connection off with half its credentials missing and
  give a confusing 500 instead of a clear one.
"""

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT = b"statflow-connection-credentials-v1"
_ITERATIONS = 200_000
_fernet: "Fernet | None" = None


def _fernet_for(secret: str) -> Fernet:
    """Derive the process's Fernet key from SECRET_KEY (cached)."""
    global _fernet
    if _fernet is not None:
        return _fernet
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))
    _fernet = Fernet(key)
    return _fernet


def _secret_key() -> str:
    from app import config

    secret = getattr(config, "SECRET_KEY", "") or os.environ.get("SECRET_KEY") or ""
    if not secret:
        raise RuntimeError(
            "SECRET_KEY is not set; connection credentials cannot be encrypted. "
            "Set SECRET_KEY before saving a database or API connection."
        )
    return secret


def encrypt(plaintext: str) -> str:
    """Encrypt a credential for storage; returns a Fernet token."""
    if not plaintext:
        return ""
    return _fernet_for(_secret_key()).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a stored credential.

    Raises ``RuntimeError`` with a plain-language message when the
    key has changed (the operator must re-enter the credential) --
    a broken ciphertext must never be read as an empty password.
    """
    if not token:
        return ""
    try:
        return _fernet_for(_secret_key()).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "This connection's credential cannot be decrypted: the server's "
            "SECRET_KEY has changed since it was saved. Re-enter the database "
            "or API password to restore the connection."
        ) from exc


def reset_cache() -> None:
    """Drop the derived key (tests, and a SECRET_KEY rotation)."""
    global _fernet
    _fernet = None
