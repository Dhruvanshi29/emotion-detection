from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, client_ip, rate_limit, rate_limit_ip
from app.core.security import (
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth_identity import AuthIdentity
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserPreferences, UserProfile
from app.schemas.auth import (
    ChangePasswordRequest,
    AccessToken,
    ActionTokenRequest,
    DeviceSession,
    EmailRequest,
    GoogleLoginRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    PasswordResetRequest,
    SimpleMessage,
    TokenPair,
    MFASetupResponse,
    MFASetupRequest,
    MFACodeRequest,
    MFADisableRequest,
)
from app.schemas.user import UserOut
from app.services import auth_service
from app.services import email_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)


def _set_browser_cookies(response: Response, pair: TokenPair) -> str:
    s = get_settings()
    csrf = secrets.token_urlsafe(24)
    common = {
        "secure": s.auth_cookie_secure,
        "samesite": s.auth_cookie_samesite.lower(),
        "domain": s.auth_cookie_domain or None,
        "path": "/",
    }
    response.set_cookie(
        s.auth_cookie_name,
        pair.refresh_token,
        httponly=True,
        max_age=s.jwt_refresh_ttl_days * 86400,
        **common,
    )
    response.set_cookie(
        s.csrf_cookie_name,
        csrf,
        httponly=False,
        max_age=s.jwt_refresh_ttl_days * 86400,
        **common,
    )
    return csrf


def _clear_browser_cookies(response: Response) -> None:
    s = get_settings()
    for name in (s.auth_cookie_name, s.csrf_cookie_name):
        response.delete_cookie(
            name,
            domain=s.auth_cookie_domain or None,
            path="/",
            secure=s.auth_cookie_secure,
            samesite=s.auth_cookie_samesite.lower(),
        )


def _require_csrf(request: Request) -> None:
    s = get_settings()
    cookie = request.cookies.get(s.csrf_cookie_name, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    origin = request.headers.get("origin")
    if origin and s.is_production and origin not in s.cors_allowed_origins_list:
        raise HTTPException(status_code=403, detail="Origin is not allowed")


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
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    current_year = datetime.now(timezone.utc).year
    supplied_age_gate = req.age_confirmed or req.dob_year is not None
    if (get_settings().is_production or supplied_age_gate) and (
        not req.age_confirmed
        or req.dob_year is None
        or current_year - req.dob_year < 18
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Saaya is currently available only to people aged 18 or older",
        )
    existing = (
        await db.execute(select(User).where(User.email == req.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(email=req.email.lower(), hashed_password=hash_password(req.password))
    user.profile = UserProfile(
        display_name=req.display_name,
        timezone=req.timezone,
        age_confirmed=req.age_confirmed,
        dob_year=req.dob_year,
    )
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
    token = await auth_service.issue_action_token(
        db, user_id=user.id, purpose="verify_email", ttl=timedelta(hours=24)
    )
    background.add_task(email_service.send_verification, to=user.email, token=token)
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
    if user.mfa_enabled and not auth_service.verify_totp(
        user.mfa_secret or "", req.mfa_code or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid 6-digit authenticator code is required",
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
            # A matching email is not proof that the caller controls the local
            # password account. Linking is an authenticated, explicit action.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already uses this email. Sign in with your password, then link Google from Profile.",
            )
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
    new_hash = hash_password(req.new_password)
    await db.execute(
        update(User).where(User.id == user.id).values(hashed_password=new_hash)
    )
    user.hashed_password = new_hash
    await db.commit()
    await auth_service.revoke_all_for_user(db, user.id)
    await auth_service.bump_password_changed_at(db, user)
    return await auth_service.issue_token_pair(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
    )


# ---------------------------------------------------------------------------
# Browser-safe session endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/browser/login",
    response_model=AccessToken,
    dependencies=[Depends(rate_limit_ip("auth_browser_login", limit_setting="auth_login_rate_limit_per_minute", key_extractor=_email_from_body))],
)
async def browser_login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessToken:
    pair = await login(req, request, db)
    csrf = _set_browser_cookies(response, pair)
    return AccessToken(access_token=pair.access_token, csrf_token=csrf)


@router.post(
    "/browser/google",
    response_model=AccessToken,
    dependencies=[Depends(rate_limit_ip("auth_browser_google", limit_setting="auth_login_rate_limit_per_minute"))],
)
async def browser_google_login(
    req: GoogleLoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessToken:
    pair = await google_login(req, request, db)
    csrf = _set_browser_cookies(response, pair)
    return AccessToken(access_token=pair.access_token, csrf_token=csrf)


@router.post(
    "/browser/refresh",
    response_model=AccessToken,
    dependencies=[Depends(rate_limit_ip("auth_browser_refresh", limit_setting="auth_refresh_rate_limit_per_minute"))],
)
async def browser_refresh(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessToken:
    _require_csrf(request)
    token = request.cookies.get(get_settings().auth_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="No browser session")
    pair = await refresh(RefreshRequest(refresh_token=token), request, db)
    csrf = _set_browser_cookies(response, pair)
    return AccessToken(access_token=pair.access_token, csrf_token=csrf)


@router.post("/browser/logout", response_model=SimpleMessage)
async def browser_logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    _require_csrf(request)
    token = request.cookies.get(get_settings().auth_cookie_name)
    if token:
        await logout(LogoutRequest(refresh_token=token), db)
    _clear_browser_cookies(response)
    return SimpleMessage(detail="ok")


@router.post("/browser/change-password", response_model=AccessToken)
async def browser_change_password(
    req: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessToken:
    _require_csrf(request)
    pair = await change_password(req, user, request, db)
    csrf = _set_browser_cookies(response, pair)
    return AccessToken(access_token=pair.access_token, csrf_token=csrf)


# ---------------------------------------------------------------------------
# Email verification, account recovery, and device sessions
# ---------------------------------------------------------------------------


@router.post(
    "/email/verify/request",
    response_model=SimpleMessage,
    dependencies=[Depends(rate_limit("email_verification", limit=3, window_seconds=3600))],
)
async def request_email_verification(
    background: BackgroundTasks,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    if user.is_verified:
        return SimpleMessage(detail="Email is already verified")
    token = await auth_service.issue_action_token(
        db, user_id=user.id, purpose="verify_email", ttl=timedelta(hours=24)
    )
    background.add_task(email_service.send_verification, to=user.email, token=token)
    return SimpleMessage(detail="Verification email requested")


@router.post("/email/verify/confirm", response_model=SimpleMessage)
async def confirm_email_verification(
    req: ActionTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    user = await auth_service.consume_action_token(
        db, raw_token=req.token, purpose="verify_email"
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user.is_verified = True
    await db.commit()
    return SimpleMessage(detail="Email verified")


@router.post(
    "/password/forgot",
    response_model=SimpleMessage,
    dependencies=[Depends(rate_limit_ip("password_forgot", limit_setting="auth_register_rate_limit_per_minute", key_extractor=_email_from_body))],
)
async def forgot_password(
    req: EmailRequest,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    user = (
        await db.execute(select(User).where(User.email == req.email.lower()))
    ).scalar_one_or_none()
    if user is not None and user.is_active:
        token = await auth_service.issue_action_token(
            db, user_id=user.id, purpose="password_reset", ttl=timedelta(minutes=30)
        )
        background.add_task(email_service.send_password_reset, to=user.email, token=token)
    # Always return the same response to prevent account enumeration.
    return SimpleMessage(detail="If the account exists, a reset link has been sent")


@router.post("/password/reset", response_model=SimpleMessage)
async def reset_password(
    req: PasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    user = await auth_service.consume_action_token(
        db, raw_token=req.token, purpose="password_reset"
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    new_hash = hash_password(req.new_password)
    await db.execute(
        update(User).where(User.id == user.id).values(hashed_password=new_hash)
    )
    user.hashed_password = new_hash
    await auth_service.revoke_all_for_user(db, user.id)
    await auth_service.bump_password_changed_at(db, user)
    await db.commit()
    return SimpleMessage(detail="Password updated")


@router.get("/sessions", response_model=list[DeviceSession])
async def list_sessions(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DeviceSession]:
    rows = await auth_service.list_active_sessions(db, user.id)
    return [DeviceSession.model_validate(row) for row in rows]


@router.delete("/sessions/{family_id}", response_model=SimpleMessage)
async def revoke_session(
    family_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    owned = (
        (
            await db.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == family_id,
                RefreshToken.user_id == user.id,
            )
            )
        ).scalars().first()
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await auth_service.revoke_family(db, family_id)
    return SimpleMessage(detail="Session revoked")


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def begin_mfa_setup(
    req: MFASetupRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MFASetupResponse:
    if user.mfa_enabled:
        raise HTTPException(
            status_code=409,
            detail="Disable the current authenticator before replacing it",
        )
    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid current password")
    secret = auth_service.create_mfa_secret()
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(mfa_secret=secret, mfa_enabled=False)
    )
    await db.commit()
    from urllib.parse import quote

    label = quote(f"Saaya:{user.email}")
    issuer = quote("Saaya")
    return MFASetupResponse(
        secret=secret,
        otpauth_uri=f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&digits=6&period=30",
    )


@router.post("/mfa/confirm", response_model=SimpleMessage)
async def confirm_mfa(
    req: MFACodeRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    if not user.mfa_secret or not auth_service.verify_totp(user.mfa_secret, req.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    await db.execute(update(User).where(User.id == user.id).values(mfa_enabled=True))
    await db.commit()
    return SimpleMessage(detail="Authenticator MFA enabled")


@router.delete("/mfa", response_model=SimpleMessage)
async def disable_mfa(
    req: MFADisableRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    if not verify_password(req.password, user.hashed_password) or not auth_service.verify_totp(user.mfa_secret or "", req.code):
        raise HTTPException(status_code=401, detail="Password or authenticator code is invalid")
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(mfa_enabled=False, mfa_secret=None)
    )
    await db.commit()
    return SimpleMessage(detail="Authenticator MFA disabled")


@router.post("/google/link", response_model=SimpleMessage)
async def link_google_account(
    req: GoogleLoginRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SimpleMessage:
    project_id = get_settings().google_identity_platform_project_id.strip()
    if not project_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        claims = await auth_service.verify_google_identity_token(req.id_token, project_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid Google identity token") from exc
    subject = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not subject or claims.get("email_verified") is not True or email != user.email.lower():
        raise HTTPException(status_code=400, detail="Use a verified Google account with the same email")
    existing = (
        await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "google", AuthIdentity.subject == subject
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.user_id != user.id:
        raise HTTPException(status_code=409, detail="That Google account is linked elsewhere")
    if existing is None:
        db.add(AuthIdentity(user_id=user.id, provider="google", subject=subject, email_at_link=email))
    await db.execute(update(User).where(User.id == user.id).values(is_verified=True))
    await db.commit()
    return SimpleMessage(detail="Google account linked")

