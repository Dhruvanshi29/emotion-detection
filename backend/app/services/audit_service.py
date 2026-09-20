"""Audit logging service (plan §12).

Writes to `audit_events` with a short-lived session so callers on hot paths
(e.g. chat send) don't hold a DB connection during LLM calls.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.middleware import redact_sensitive
from app.db import session as _session_mod
from app.models.audit import AuditEvent


# Keys whose values should always be dropped from audit `details` payloads.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "content",
        "message",
    }
)

_MAX_STR = 500
_MAX_DEPTH = 4


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    """Return a copy of `value` with secrets removed and long strings truncated."""
    if depth > _MAX_DEPTH:
        return "[TRUNCATED_DEPTH]"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if key.lower() in _SENSITIVE_KEYS:
                out[key] = "[REDACTED]"
            else:
                out[key] = _sanitize(v, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, depth=depth + 1) for v in value][:50]
    if isinstance(value, str):
        cleaned = redact_sensitive(value)
        return cleaned if len(cleaned) <= _MAX_STR else cleaned[:_MAX_STR] + "…"
    return value


async def log_event(
    *,
    user_id: Optional[str],
    category: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Fire-and-forget audit write. Swallows errors so it never breaks callers."""
    try:
        clean_details = _sanitize(details) if details else None
        async with _session_mod.SessionLocal() as db:
            db.add(
                AuditEvent(
                    user_id=user_id,
                    category=category,
                    action=action,
                    details=clean_details,
                    ip=ip,
                    user_agent=(user_agent or "")[:255] or None,
                )
            )
            await db.commit()
    except Exception:
        # Auditing must never crash a real request path.
        pass


async def log_event_in(
    db: AsyncSession,
    *,
    user_id: Optional[str],
    category: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditEvent:
    """Same as log_event but on an existing session (used inside transactions)."""
    evt = AuditEvent(
        user_id=user_id,
        category=category,
        action=action,
        details=_sanitize(details) if details else None,
        ip=ip,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(evt)
    await db.flush()
    return evt


async def list_for_user(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int = 100,
    categories: Optional[Sequence[str]] = None,
) -> tuple[list[AuditEvent], int]:
    q = select(AuditEvent).where(AuditEvent.user_id == user_id)
    if categories:
        q = q.where(AuditEvent.category.in_(list(categories)))
    total = (
        await db.execute(
            select(func.count()).select_from(q.subquery())
        )
    ).scalar_one()
    rows = (
        await db.execute(
            q.order_by(AuditEvent.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)
