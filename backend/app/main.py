from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.emotion import router as emotion_router
from app.api.journal import router as journal_router
from app.api.memory import router as memory_router
from app.api.privacy import router as privacy_router
from app.api.reminders import router as reminders_router
from app.api.users import router as users_router
from app.api.wellness import router as wellness_router
from app.api.therapists import router as therapists_router
from app.core.config import get_settings
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import configure_json_logging
from app.core.metrics import MetricsMiddleware, metrics_endpoint
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestIDMiddleware,
    install_log_redaction,
)
from app.db import session as _session_mod
from app.services import reminders_service, task_queue, therapist_service, wellness_service

settings = get_settings()
if settings.log_format.lower() == "json":
    configure_json_logging(settings.log_level)
else:
    logging.basicConfig(level=settings.log_level.upper())
log = logging.getLogger(__name__)
install_log_redaction()

# ---------- Optional Sentry (Phase 14, §19) ----------
if settings.sentry_dsn:
    try:
        import sentry_sdk  # type: ignore

        _SENSITIVE_HEADERS = ("authorization", "cookie", "set-cookie", "x-api-key")

        def _scrub_event(event, hint):  # noqa: ANN001
            """Strip request bodies, cookies, and auth headers before shipping."""
            try:
                req = event.get("request") or {}
                req.pop("data", None)
                req.pop("cookies", None)
                headers = req.get("headers") or {}
                if isinstance(headers, dict):
                    for k in list(headers.keys()):
                        if k.lower() in _SENSITIVE_HEADERS:
                            headers[k] = "[REDACTED]"
                # Neutralize URL query strings so tokens in query params don't leak.
                if "query_string" in req:
                    req["query_string"] = "[REDACTED]"
                user = event.get("user") or {}
                user.pop("email", None)
                user.pop("ip_address", None)
            except Exception:  # noqa: BLE001
                pass
            return event

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            environment=settings.app_env,
            release=(
                f"{settings.app_version}+{settings.git_sha[:7]}"
                if settings.git_sha
                else settings.app_version
            ),
            send_default_pii=False,
            before_send=_scrub_event,
        )
        log.info("sentry: initialized (env=%s)", settings.app_env)
    except Exception as e:  # noqa: BLE001
        log.warning("sentry: init failed (%s)", e)


async def _scheduler_loop(interval_seconds: float) -> None:
    import asyncio

    while True:
        try:
            async with _session_mod.SessionLocal() as db:
                created = await reminders_service.dispatch_due(db)
                delivered = await reminders_service.deliver_pending_email_notifications(db)
                pushed = await reminders_service.deliver_pending_push_notifications(db)
                jobs = await task_queue.process_pending(db)
                if created:
                    log.info("reminders: dispatched %d notifications", created)
                if delivered:
                    log.info("reminders: delivered %d emails", delivered)
                if pushed:
                    log.info("reminders: delivered %d push notifications", pushed)
                if jobs:
                    log.info("tasks: completed %d durable jobs", jobs)
        except Exception as e:  # noqa: BLE001
            log.warning("reminders: dispatch failed (%s)", e)
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import asyncio

    task: "asyncio.Task[None] | None" = None
    try:
        async with _session_mod.SessionLocal() as db:
            inserted = await wellness_service.ensure_seed(db)
            if inserted:
                log.info("wellness: seeded %d exercises", inserted)
            if not settings.is_production:
                t_inserted = await therapist_service.ensure_seed(db)
                if t_inserted:
                    log.info("therapists: seeded %d development professionals", t_inserted)
    except Exception as e:  # noqa: BLE001
        log.warning("seed skipped (%s)", e)
    if settings.reminders_scheduler_enabled:
        task = asyncio.create_task(
            _scheduler_loop(settings.reminders_scheduler_interval_seconds)
        )
        log.info(
            "reminders: scheduler started (every %.1fs)",
            settings.reminders_scheduler_interval_seconds,
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


app = FastAPI(
    title="Emotional Wellness Platform — Backend",
    version="0.1.0",
    description=(
        "Provider-agnostic LLM adapters (NVIDIA NIM, OpenRouter, Groq, Gemini) "
        "with automatic fallback. See plan.txt §4 and Addendum §A."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        settings.cors_allowed_origins_list
        if settings.is_production
        else ["*"]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Body-size limit runs first (outer middleware) so it can 413 before we spend
# CPU parsing. File-upload endpoints declare their own larger caps and are
# exempt here. RequestID runs after so the header appears on 413 responses too.
app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=settings.max_json_body_bytes,
    exempt_prefixes=("/emotion/audio",),
)
app.add_middleware(RequestIDMiddleware)

# Idempotency runs inside RequestID so replays keep the same X-Request-ID
# semantic (fresh id per request, cache still keyed by header).
if settings.idempotency_enabled:
    app.add_middleware(
        IdempotencyMiddleware,
        ttl_seconds=settings.idempotency_ttl_seconds,
        redis_url=settings.redis_url,
    )

# Metrics collection wraps everything else so it can time and label all routes.
if settings.metrics_enabled:
    app.add_middleware(MetricsMiddleware)
    app.add_route("/metrics", metrics_endpoint(settings.metrics_bearer_token))


@app.get("/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "version": settings.app_version,
        "commit": settings.git_sha[:7] if settings.git_sha else None,
    }


@app.get("/ready", tags=["health"])
async def ready() -> dict:
    """Readiness probe. Verifies DB connectivity — used by Render + smoke tests."""
    try:
        async with _session_mod.SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as e:  # noqa: BLE001
        # Return 503 so orchestrators keep old instance until DB is reachable.
        from fastapi import HTTPException

        log.warning("readiness check failed: %s", e)
        raise HTTPException(status_code=503, detail="database unavailable") from e


app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(emotion_router)
app.include_router(journal_router)
app.include_router(wellness_router)
app.include_router(therapists_router)
app.include_router(reminders_router)
app.include_router(dashboard_router)
app.include_router(memory_router)
app.include_router(privacy_router)
