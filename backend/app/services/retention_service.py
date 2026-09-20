"""Data-retention purge service (Phase 15 P1 §5.6).

Deletes:
    * refresh_tokens whose ``expires_at`` is in the past
    * notifications older than ``retention_notification_days``
    * audit_events older than ``retention_audit_days``

Kept intentionally narrow — user content (journal, chat, memory) is preserved
unless the user asks for erasure via the privacy API. Compliance-driven long-
term retention should be revisited before broad launch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


log = logging.getLogger("app.retention")


async def purge_once(
    db: AsyncSession,
    *,
    audit_days: int,
    notification_days: int,
) -> Dict[str, int]:
    """Run one purge cycle. Returns per-table deletion counts."""
    from app.models.audit import AuditEvent
    from app.models.reminder import Notification
    from app.models.refresh_token import RefreshToken

    now = datetime.now(timezone.utc)
    counts: Dict[str, int] = {}

    r1 = await db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < now)
    )
    counts["refresh_tokens"] = r1.rowcount or 0

    cutoff_n = now - timedelta(days=notification_days)
    r2 = await db.execute(
        delete(Notification).where(Notification.created_at < cutoff_n)
    )
    counts["notifications"] = r2.rowcount or 0

    cutoff_a = now - timedelta(days=audit_days)
    r3 = await db.execute(
        delete(AuditEvent).where(AuditEvent.created_at < cutoff_a)
    )
    counts["audit_events"] = r3.rowcount or 0

    await db.commit()
    total = sum(counts.values())
    if total:
        log.info("retention purge: %s", counts)
    return counts
