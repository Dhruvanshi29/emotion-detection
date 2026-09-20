from __future__ import annotations

import json
import logging
import secrets
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, client_ip, rate_limit_ip
from app.core.security import (
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth_identity import AuthIdentity
from app.models.user import User, UserPreferences, UserProfile
from app.schemas.auth import (
    ChangePasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    SimpleMessage,
    TokenPair,
)
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _email_from_body(body: bytes) -> str:
    """Extract `email` from a JSON body for pre-auth rate limiting."""
    try:
        obj = json.loads(body or b"{}")
        v = obj.get("email")
        return str(v).strip().lower() if isinstance(v, str) else ""
    except (ValueError, TypeError):
        return ""


async def _load_user(db: AsyncSession, user_id: str) -> User | None:
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.profile), selectinload(User.preferences))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            rate_limit_ip(
                "auth_register",
                limit_setting="auth_register_rate_limit_per_minute",
                key_extractor=_email_from_body,
            )
        )
    ],
)
async def register(
    req: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    existing = (
        await db.execute(select(User).where(User.email == req.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(email=req.email.lower(), hashed_password=hash_password(req.password))
    user.profile = UserProfile(display_name=req.display_name, timezone=req.timezone)
    user.preferences = UserPreferences()
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        # The initial lookup is intentionally friendly, but the unique index
        # is authoritative when two registrations race.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc

    loaded = await _load_user(db, user.id)
    assert loaded is not None
    return loaded


@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[
        Depends(
            rate_limit_ip(
                "auth_login",
                limit_setting="auth_login_rate_limit_per_minute",
                key_extractor=_email_from_body,
            )
        )
    ],
)
async def login(
    req: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    user = (
        await db.execute(select(User).where(User.email == req.email.lower()))
    ).scalar_one_or_none()
    if user is None or not verify_password(req.password, user.hashed_password):
        # Generic message — do not disclose whether the email exists (§3.1).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )
    return await auth_service.issue_token_pair(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )

@router.post(
    "/google",
    response_model=TokenPair,
    dependencies=[
        Depends(
            rate_limit_ip(
                "auth_google",
                limit_setting="auth_login_rate_limit_per_minute",
            )
        )
    ],
)
async def google_login(
    req: GoogleLoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """Exchange a Google Identity Platform ID token for a local session."""
    project_id = get_settings().google_identity_platform_project_id.strip()
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )
    try:
        claims = await auth_service.verify_google_identity_token(
            req.id_token, project_id
        )
    except Exception as exc:  # noqa: BLE001
        log.info("auth: rejected Google identity token (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google identity token",
        ) from exc

    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not subject or not email or claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email must be verified",
        )

    identity = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "google",
                AuthIdentity.subject == subject,
            )
        )
    ).scalar_one_or_none()
    user = None
    if identity is not None:
        user = (
            await db.execute(select(User).where(User.id == identity.user_id))
        ).scalar_one_or_none()
    else:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                hashed_password=hash_password(secrets.token_urlsafe(48)),
                is_verified=True,
            )
            user.profile = UserProfile(
                display_name=(str(claims.get("name") or "").strip() or None),
                timezone="UTC",
            )
            user.preferences = UserPreferences()
            db.add(user)
            await db.flush()
        else:
            user.is_verified = True
        db.add(
            AuthIdentity(
                user_id=user.id,
                provider="google",
                subject=subject,
                email_at_link=email,
            )
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            log.warning("auth: concurrent Google account link collision")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Google account is already linked; please try again",
            ) from exc

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )
    return await auth_service.issue_token_pair(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    dependencies=[
        Depends(
            rate_limit_ip(
                "auth_refresh",
                limit_setting="auth_refresh_rate_limit_per_minute",
            )
        )
    ],
)
async def refresh(
    req: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    try:
        payload = decode_token(req.refresh_token, refresh=True)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
        )
    sub = payload.get("sub")
    jti = payload.get("jti")
    fam = payload.get("fam")
    if not sub or not jti or not fam:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    row = await auth_service.get_refresh_row(db, jti)
    if row is None:
        # Unknown JTI while token signature is valid = reuse of a rotated
        # token or forgery — kill the whole family defensively.
        await auth_service.revoke_family(db, fam)
        log.warning("auth: unknown refresh jti presented (fam=%s)", fam)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    if row.revoked_at is not None:
        # Reuse detected — revoke the entire family (§3.1).
        await auth_service.revoke_family(db, row.family_id)
        log.warning("auth: refresh reuse detected, family revoked (fam=%s)", fam)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. Please sign in again.",
        )
    if row.family_id != fam or row.user_id != sub:
        await auth_service.revoke_family(db, row.family_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user = (await db.execute(select(User).where(User.id == sub))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer valid"
        )
    try:
        return await auth_service.rotate_refresh_token(
            db,
            user,
            presented_jti=jti,
            family_id=row.family_id,
            user_agent=request.headers.get("user-agent"),
            ip=client_ip(request),
        )
    except auth_service.RefreshTokenReuseError as exc:
        log.warning("auth: concurrent refresh reuse detected (fam=%s)", fam)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. Please sign in again.",
        ) from exc


@router.post("/logout", response_model=SimpleMessage)
async def logout(
    req: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    """Revoke the presented refresh family (this device / browser)."""
    if not req.refresh_token:
        return SimpleMessage(detail="ok")
    try:
        payload = decode_token(req.refresh_token, refresh=True)
    except jwt.PyJWTError:
        # Be quiet on invalid tokens so logout always looks the same to a caller.
        return SimpleMessage(detail="ok")
    fam = payload.get("fam")
    if fam:
        await auth_service.revoke_family(db, fam)
    return SimpleMessage(detail="ok")


@router.post(
    "/logout-all",
    response_model=SimpleMessage,
)
async def logout_all(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    """Revoke every refresh family AND invalidate every existing access token."""
    await auth_service.revoke_all_for_user(db, user.id)
    await auth_service.bump_password_changed_at(db, user)
    return SimpleMessage(detail="ok")


@router.post(
    "/change-password",
    response_model=TokenPair,
    dependencies=[
        Depends(
            rate_limit_ip(
                "auth_change_password",
                limit_setting="auth_change_password_rate_limit_per_minute",
            )
        )
    ],
)
async def change_password(
    req: ChangePasswordRequest,
    user: CurrentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    """Re-auth with the current password, then rotate credentials.

    Invalidates every prior refresh token AND every prior access token, then
    issues a fresh pair so the caller stays signed in on this device (§3.1).
    """
    if not verify_password(req.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password"
        )
    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from current password",
        )
    user.hashed_password = hash_password(req.new_password)
    await db.commit()
    await auth_service.revoke_all_for_user(db, user.id)
    await auth_service.bump_password_changed_at(db, user)
    return await auth_service.issue_token_pair(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )

