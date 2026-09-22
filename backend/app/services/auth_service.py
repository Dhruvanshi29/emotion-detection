"""Auth service — token issuance, rotation and family-revocation (§3.1).

Server-side ledger of refresh tokens (`RefreshToken` table) enables:
- Rotation: every /auth/refresh returns a fresh token and revokes the old row.
- Reuse detection: presenting a revoked or unknown token revokes the entire
  family (all descendants), forcing full re-login on any device that was
  ever handed a compromised token.
- Logout: revoke a single family; Logout-all: bump `password_changed_at`,
  which invalidates every previously issued access token via the `pca` claim.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.auth_action import AuthActionToken
from app.models.user import User
from app.schemas.auth import TokenPair


class RefreshTokenReuseError(Exception):
    """Raised when another request already consumed a refresh token."""


async def verify_google_identity_token(token: str, project_id: str) -> dict:
    """Verify a Google Identity Platform token without service-account keys."""
    import asyncio

    def _verify() -> dict:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        return id_token.verify_firebase_token(
            token,
            Request(),
            audience=project_id,
        )

    return await asyncio.to_thread(_verify)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_mfa_secret() -> str:
    """Create a standard 160-bit base32 TOTP secret."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, *, at: datetime | None = None) -> str:
    """Generate an RFC 6238 SHA-1 TOTP code (also useful for verification tests)."""
    try:
        key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid TOTP secret") from exc
    counter = int((at or _utcnow()).timestamp()) // 30
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str, *, at: datetime | None = None) -> bool:
    """Verify RFC 6238 SHA-1 TOTP with a one-step clock-skew window."""
    if not secret or not code.isdigit() or len(code) != 6:
        return False
    timestamp = int((at or _utcnow()).timestamp())
    for drift in (-1, 0, 1):
        try:
            candidate = totp_code(secret, at=datetime.fromtimestamp(timestamp + drift * 30, timezone.utc))
        except ValueError:
            return False
        if hmac.compare_digest(candidate, code):
            return True
    return False


async def issue_token_pair(
    db: AsyncSession,
    user: User,
    *,
    family_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
) -> TokenPair:
    """Mint an access + refresh token pair and record the refresh row.

    Pass ``family_id`` to keep an existing family (used during rotation);
    omit to start a fresh family (new login).
    """
    token, jti, fam, expires_at = create_refresh_token(user.id, family_id=family_id)
    db.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            family_id=fam,
            expires_at=expires_at,
            user_agent=(user_agent or None),
            ip=(ip or None),
        )
    )
    await db.commit()
    access = create_access_token(
        user.id, password_changed_at=user.password_changed_at
    )
    return TokenPair(access_token=access, refresh_token=token)


async def rotate_refresh_token(
    db: AsyncSession,
    user: User,
    *,
    presented_jti: str,
    family_id: str,
    user_agent: Optional[str] = None,
    ip: Optional[str] = None,
) -> TokenPair:
    """Atomically consume the presented row and mint its replacement.

    The ``revoked_at IS NULL`` predicate is the concurrency guard. Two
    simultaneous refreshes may both read the old row, but only one can update
    it; the loser is treated as token reuse and the family is revoked.
    """
    now = _utcnow()
    new_token, new_jti, _, new_exp = create_refresh_token(
        user.id, family_id=family_id
    )
    result = await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.jti == presented_jti,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now, replaced_by=new_jti)
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        await db.rollback()
        await revoke_family(db, family_id)
        raise RefreshTokenReuseError
    db.add(
        RefreshToken(
            jti=new_jti,
            user_id=user.id,
            family_id=family_id,
            expires_at=new_exp,
            user_agent=(user_agent or None),
            ip=(ip or None),
        )
    )
    await db.commit()
    access = create_access_token(
        user.id, password_changed_at=user.password_changed_at
    )
    return TokenPair(access_token=access, refresh_token=new_token)


async def revoke_family(db: AsyncSession, family_id: str) -> int:
    """Revoke every non-revoked row in the family. Returns count revoked."""
    now = _utcnow()
    r = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()
    return int(getattr(r, "rowcount", 0) or 0)


async def revoke_all_for_user(db: AsyncSession, user_id: str) -> int:
    now = _utcnow()
    r = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.commit()
    return int(getattr(r, "rowcount", 0) or 0)


async def get_refresh_row(db: AsyncSession, jti: str) -> Optional[RefreshToken]:
    return (
        await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalar_one_or_none()


async def bump_password_changed_at(db: AsyncSession, user: User) -> None:
    """Invalidate every previously issued access token for the user."""
    # Add 1 second so the integer-epoch `pca` claim is strictly greater than
    # any token issued in the same wall-clock second (the compare in
    # `get_current_user` uses `>` on integer seconds).
    now = _utcnow().replace(microsecond=0) + timedelta(seconds=1)
    await db.execute(
        update(User).where(User.id == user.id).values(password_changed_at=now)
    )
    user.password_changed_at = now
    await db.commit()


async def issue_action_token(
    db: AsyncSession,
    *,
    user_id: str,
    purpose: str,
    ttl: timedelta,
) -> str:
    """Issue a single-use opaque token while persisting only its digest."""
    now = _utcnow()
    await db.execute(
        update(AuthActionToken)
        .where(
            AuthActionToken.user_id == user_id,
            AuthActionToken.purpose == purpose,
            AuthActionToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw = secrets.token_urlsafe(40)
    db.add(
        AuthActionToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            expires_at=now + ttl,
        )
    )
    await db.commit()
    return raw


async def consume_action_token(
    db: AsyncSession,
    *,
    raw_token: str,
    purpose: str,
) -> Optional[User]:
    """Atomically consume a valid action token and return its user."""
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = (
        await db.execute(
            select(AuthActionToken).where(
                AuthActionToken.token_hash == digest,
                AuthActionToken.purpose == purpose,
            )
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= _utcnow():
        return None
    result = await db.execute(
        update(AuthActionToken)
        .where(AuthActionToken.id == row.id, AuthActionToken.used_at.is_(None))
        .values(used_at=_utcnow())
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        await db.rollback()
        return None
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    await db.commit()
    return user


async def list_active_sessions(db: AsyncSession, user_id: str) -> list[dict]:
    rows = list(
        (
            await db.execute(
                select(RefreshToken)
                .where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > _utcnow(),
                )
                .order_by(RefreshToken.created_at.desc())
            )
        ).scalars().all()
    )
    grouped: dict[str, list[RefreshToken]] = {}
    for row in rows:
        grouped.setdefault(row.family_id, []).append(row)
    result: list[dict] = []
    for family_id, family in grouped.items():
        newest = max(family, key=lambda item: item.created_at)
        oldest = min(family, key=lambda item: item.created_at)
        result.append(
            {
                "family_id": family_id,
                "created_at": oldest.created_at,
                "last_seen_at": newest.created_at,
                "expires_at": newest.expires_at,
                "user_agent": newest.user_agent,
                "ip": newest.ip,
            }
        )
    return result
