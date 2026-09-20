"""Field-level encryption (Phase 15 P1 §5.4).

Provides an ``EncryptedText`` SQLAlchemy TypeDecorator that transparently
encrypts values on write using AES-256-GCM and decrypts on read.

Design goals:

* **Backward compatible.** Rows written before encryption is enabled remain
  readable — a decrypt failure falls back to returning the raw value. Columns
  can be flipped from ``Text`` to ``EncryptedText`` without a data migration.
* **No key = passthrough.** When ``FIELD_ENCRYPTION_KEY`` is empty (dev / tests)
  the type behaves like ``Text``. Turn it on in production via env.
* **Ciphertext prefix.** Encrypted values are stored as ``enc:v1:<b64>`` so a
  reader can distinguish encrypted rows from legacy plaintext in one glance.

Ciphertext layout (after the ``enc:v1:`` prefix), base64-url-encoded:
    12-byte nonce || AES-GCM(ciphertext || 16-byte tag)
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.types import TypeDecorator


log = logging.getLogger("app.crypto")

_PREFIX = "enc:v1:"


def _load_key() -> Optional[bytes]:
    """Read the 32-byte AES key from settings (base64 or hex) or return None."""
    # Delayed import so tests can monkeypatch settings before first use.
    try:
        from app.core.config import get_settings

        raw = get_settings().field_encryption_key.strip()
    except Exception:  # noqa: BLE001
        raw = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    try:
        # Accept base64url (with or without padding) or hex.
        if len(raw) == 64:
            key = bytes.fromhex(raw)
        else:
            pad = "=" * (-len(raw) % 4)
            key = base64.urlsafe_b64decode(raw + pad)
    except Exception as e:  # noqa: BLE001
        log.error("FIELD_ENCRYPTION_KEY parse failed: %s", e)
        return None
    if len(key) != 32:
        log.error("FIELD_ENCRYPTION_KEY must decode to 32 bytes (got %d)", len(key))
        return None
    return key


def _get_cipher():
    """Return an AESGCM instance or None if disabled / unavailable."""
    key = _load_key()
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM(key)
    except Exception as e:  # noqa: BLE001
        log.error("cryptography import failed: %s", e)
        return None


def encrypt_str(plaintext: str) -> str:
    """Encrypt a UTF-8 string. If encryption is disabled, return as-is."""
    if plaintext is None:
        return plaintext  # type: ignore[return-value]
    if plaintext.startswith(_PREFIX):
        # Already encrypted — don't double-encrypt.
        return plaintext
    cipher = _get_cipher()
    if cipher is None:
        return plaintext
    nonce = os.urandom(12)
    ct = cipher.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return _PREFIX + blob


def decrypt_str(value: str) -> str:
    """Decrypt an ``enc:v1:`` blob. Non-encrypted or failing values pass through."""
    if not value or not value.startswith(_PREFIX):
        return value
    cipher = _get_cipher()
    if cipher is None:
        # Key missing after data was written encrypted — return the raw blob
        # rather than crash. Operators must restore the key.
        return value
    try:
        raw = base64.urlsafe_b64decode(value[len(_PREFIX) :].encode("ascii"))
        nonce, ct = raw[:12], raw[12:]
        return cipher.decrypt(nonce, ct, associated_data=None).decode("utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("decrypt failed, returning raw value: %s", e)
        return value


class EncryptedText(TypeDecorator):
    """SQLAlchemy ``Text`` column that transparently encrypts on save."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:  # noqa: D401
        if value is None:
            return None
        return encrypt_str(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> Any:  # noqa: D401
        if value is None:
            return None
        return decrypt_str(str(value))


class EncryptedString(TypeDecorator):
    """Same as ``EncryptedText`` but backed by ``String(n)`` for shorter fields."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:  # noqa: D401
        if value is None:
            return None
        return encrypt_str(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> Any:  # noqa: D401
        if value is None:
            return None
        return decrypt_str(str(value))
