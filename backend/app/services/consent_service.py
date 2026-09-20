"""Consent bookkeeping (plan §12 / §13).

Records a durable ConsentEvent per change AND mirrors the current value onto
UserPreferences so hot paths can gate features with a cheap boolean check.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ConsentEvent
from app.models.user import UserPreferences

# Prefs columns that mirror a subset of ConsentEvent.kind values.
_KIND_TO_PREFS_ATTR = {
    "mic": "mic_consent",
    "camera": "camera_consent",
    "memory": "memory_enabled",
}


async def set_consent(
    db: AsyncSession,
    *,
    user_id: str,
    kind: str,
    granted: bool,
    source: str = "settings",
    notes: Optional[str] = None,
) -> ConsentEvent:
    evt = ConsentEvent(
        user_id=user_id,
        kind=kind,
        granted=granted,
        source=source,
        notes=notes,
    )
    db.add(evt)
    attr = _KIND_TO_PREFS_ATTR.get(kind)
    if attr is not None:
        prefs = (
            await db.execute(
                select(UserPreferences).where(UserPreferences.user_id == user_id)
            )
        ).scalar_one_or_none()
        if prefs is None:
            prefs = UserPreferences(user_id=user_id)
            db.add(prefs)
        setattr(prefs, attr, granted)
    await db.commit()
    await db.refresh(evt)
    return evt


async def latest_by_kind(db: AsyncSession, user_id: str) -> dict[str, ConsentEvent]:
    rows = (
        await db.execute(
            select(ConsentEvent)
            .where(ConsentEvent.user_id == user_id)
            .order_by(ConsentEvent.created_at.desc())
        )
    ).scalars().all()
    out: dict[str, ConsentEvent] = {}
    for r in rows:
        out.setdefault(r.kind, r)
    return out


async def history(
    db: AsyncSession, user_id: str, *, limit: int = 100
) -> List[ConsentEvent]:
    return list(
        (
            await db.execute(
                select(ConsentEvent)
                .where(ConsentEvent.user_id == user_id)
                .order_by(ConsentEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )
