from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.db import session as _session_mod
from app.db.session import get_db
from app.models.user import User
from app.services.ai.llm.router import LLMRouter, get_llm_router
from app.services.emotion import EmotionAnalyzer, LLMEmotionAnalyzer
from app.services.stt.router import STTRouter, get_stt_router

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=True)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """Authenticate and return the user, using a short-lived DB session.

    We deliberately do NOT use the request-scoped `get_db` here because that
    session would remain checked out for the lifetime of the endpoint (e.g.
    across long LLM calls), and Neon closes idle SSL sockets under those
    conditions, causing rollback-on-close failures. A short session keeps the
    connection tied only to the auth query.
    """
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, refresh=False)
        if payload.get("type") != "access":
            raise creds_exc
        sub = payload.get("sub")
        pca_claim = payload.get("pca")
    except jwt.PyJWTError:
        raise creds_exc

    if not sub:
        raise creds_exc

    stmt = (
        select(User)
        .where(User.id == sub)
        .options(selectinload(User.profile), selectinload(User.preferences))
    )
    async with _session_mod.SessionLocal() as db:
        user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise creds_exc
    # §3.1: reject tokens issued before the last password change / logout-all.
    if pca_claim is not None and user.password_changed_at is not None:
        if int(user.password_changed_at.timestamp()) > int(pca_claim):
            raise creds_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_router() -> LLMRouter:
    return get_llm_router()


LLMRouterDep = Annotated[LLMRouter, Depends(get_router)]


def get_emotion_analyzer(llm: LLMRouterDep) -> EmotionAnalyzer:
    return LLMEmotionAnalyzer(llm)


EmotionAnalyzerDep = Annotated[EmotionAnalyzer, Depends(get_emotion_analyzer)]


def get_stt() -> STTRouter:
    return get_stt_router()


STTRouterDep = Annotated[STTRouter, Depends(get_stt)]


def rate_limit(
    bucket: str,
    *,
    limit: int | None = None,
    window_seconds: float = 60.0,
    limit_setting: str | None = None,
):
    """Per-user sliding-window rate limit dependency (plan §12).

    Pass either an explicit `limit` or a `limit_setting` attribute name to
    read from `Settings` at request time (so tests can monkeypatch it).
    Returns 429 with `Retry-After` when the window is full. Skips entirely
    when `settings.rate_limit_enabled` is False.
    """
    from app.services.rate_limit import get_limiter

    async def _dep(user: "CurrentUser") -> None:  # type: ignore[valid-type]
        from app.core.config import get_settings

        s = get_settings()
        if not s.rate_limit_enabled:
            return
        active_limit = (
            limit if limit is not None else int(getattr(s, limit_setting or "", 0))
        )
        if active_limit <= 0:
            return
        allowed, retry = get_limiter().check(
            f"{bucket}:{user.id}",
            limit=active_limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
                headers={"Retry-After": str(int(retry) + 1)},
            )

    return _dep


def client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting (§3.1).

    Honors `X-Forwarded-For` (Render/Vercel put the client IP first) then
    falls back to the socket peer. Uses only the first hop to prevent a
    caller from spoofing IPs by injecting extras.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def rate_limit_ip(
    bucket: str,
    *,
    limit_setting: str,
    window_seconds: float = 60.0,
    key_extractor=None,
):
    """Pre-auth rate limit keyed by IP (+ optional secondary key).

    Used by `/auth/*` endpoints where no user is available yet. The secondary
    key (e.g. attempted email) prevents a single IP from being used to lock
    out a specific account while still catching credential stuffing.
    """
    from app.services.rate_limit import get_limiter

    async def _dep(request: Request) -> None:
        from app.core.config import get_settings

        s = get_settings()
        if not s.rate_limit_enabled:
            return
        active_limit = int(getattr(s, limit_setting, 0))
        if active_limit <= 0:
            return
        secondary = ""
        if key_extractor is not None:
            try:
                # Read + restore the body so downstream handlers still see it.
                body = await request.body()
                secondary = key_extractor(body) or ""
            except Exception:  # noqa: BLE001
                secondary = ""
        key = f"{bucket}:{client_ip(request)}"
        if secondary:
            key = f"{key}:{secondary}"
        allowed, retry = get_limiter().check(
            key, limit=active_limit, window_seconds=window_seconds
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again shortly.",
                headers={"Retry-After": str(int(retry) + 1)},
            )

    return _dep
