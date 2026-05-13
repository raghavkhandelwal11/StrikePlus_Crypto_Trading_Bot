"""Symmetric encryption for at-rest secrets like the wallet private key.

Uses Fernet (AES-128-CBC + HMAC) with a key derived from a password via PBKDF2.
The decrypted private key lives only in process memory.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Salt is fixed-per-deployment. Override via env if you rotate keys.
_DEFAULT_SALT = b"ctb-v1-salt-do-not-share"
_KDF_ITERATIONS = 480_000


def _derive_key(password: str, salt: bytes = _DEFAULT_SALT) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_secret(plaintext: str, password: str) -> str:
    """Return a base64 ciphertext that can be stored in env or config."""
    f = Fernet(_derive_key(password))
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str, password: str) -> str:
    """Decrypt a previously encrypted secret. Raises ValueError on tamper/wrong password."""
    f = Fernet(_derive_key(password))
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt secret: wrong password or corrupted ciphertext") from e


def load_private_key(encrypted: Optional[str], password: Optional[str]) -> Optional[str]:
    """Decrypt the configured wallet private key. Returns None if not configured."""
    if not encrypted or not password:
        return None
    return decrypt_secret(encrypted, password)
