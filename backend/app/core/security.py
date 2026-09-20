from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import uuid

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _encode(payload: Dict[str, Any], secret: str, ttl: timedelta) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    body = {**payload, "iat": now, "exp": now + ttl}
    return jwt.encode(body, secret, algorithm=s.jwt_algorithm)


def create_access_token(
    subject: str,
    *,
    password_changed_at: Optional[datetime] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Create an access token.

    ``password_changed_at`` is embedded as the ``pca`` (password-change-at)
    epoch claim. `get_current_user` compares it to the User row and rejects
    the token if the stored value is newer, revoking every session issued
    before a password change or logout-all (§3.1).
    """
    s = get_settings()
    payload: Dict[str, Any] = {"sub": subject, "type": "access"}
    if password_changed_at is not None:
        payload["pca"] = int(password_changed_at.timestamp())
    if extra:
        payload.update(extra)
    return _encode(payload, s.jwt_secret, timedelta(minutes=s.jwt_access_ttl_minutes))


def create_refresh_token(
    subject: str,
    *,
    jti: Optional[str] = None,
    family_id: Optional[str] = None,
) -> tuple[str, str, str, datetime]:
    """Create a refresh token bound to a server-side ledger row.

    Returns ``(token, jti, family_id, expires_at)`` so the caller can persist
    a ``RefreshToken`` row with matching identifiers for rotation + reuse
    detection (§3.1).
    """
    s = get_settings()
    the_jti = jti or str(uuid.uuid4())
    fam = family_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=s.jwt_refresh_ttl_days)
    payload = {
        "sub": subject,
        "type": "refresh",
        "jti": the_jti,
        "fam": fam,
    }
    body = {**payload, "iat": now, "exp": exp}
    token = jwt.encode(body, s.jwt_refresh_secret, algorithm=s.jwt_algorithm)
    return token, the_jti, fam, exp


def decode_token(token: str, *, refresh: bool = False) -> Dict[str, Any]:
    s = get_settings()
    secret = s.jwt_refresh_secret if refresh else s.jwt_secret
    return jwt.decode(token, secret, algorithms=[s.jwt_algorithm])
