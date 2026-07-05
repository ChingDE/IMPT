"""services/crypto.py — symmetric encryption for secrets stored at rest.

Used to encrypt GitHub OAuth tokens before they are written to the database.
The key comes from settings.GITHUB_TOKEN_KEY if set (a urlsafe-base64 32-byte
Fernet key); otherwise it is derived deterministically from SECRET_KEY so the
feature works without extra configuration. For production, set GITHUB_TOKEN_KEY
to a dedicated key (generate with: Fernet.generate_key().decode()).
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from config.settings import get_settings

log = logging.getLogger(__name__)


def _fernet() -> Fernet:
    s = get_settings()
    key = (getattr(s, "GITHUB_TOKEN_KEY", "") or "").strip()
    if key:
        key_bytes = key.encode()
    else:
        # Derive a valid 32-byte urlsafe key from SECRET_KEY.
        digest = hashlib.sha256(s.SECRET_KEY.encode()).digest()
        key_bytes = base64.urlsafe_b64encode(digest)
    return Fernet(key_bytes)


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: Optional[str]) -> Optional[str]:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception) as exc:  # noqa: BLE001
        log.warning("Token decryption failed: %s", exc)
        return None
