"""Persist EmotionEvent + EmotionScore rows and query them for endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.emotion import EmotionEvent, EmotionScore
from app.services.emotion.text import EmotionAnalyzer, TextEmotionResult


async def analyze_and_persist(
    db: AsyncSession,
    analyzer: EmotionAnalyzer,
    *,
    user_id: str,
    text: str,
    source: str,
    source_ref_id: Optional[str] = None,
) -> tuple[EmotionEvent, TextEmotionResult]:
    result = await analyzer.analyze(text)
    event = await persist_result(
        db,
        user_id=user_id,
        text=text,
        source=source,
        source_ref_id=source_ref_id,
        result=result,
    )
    return event, result


async def persist_result(
    db: AsyncSession,
    *,
    user_id: str,
    text: str,
    source: str,
    source_ref_id: Optional[str],
    result: TextEmotionResult,
) -> EmotionEvent:
    """Persist a pre-computed analyzer result. Kept separate from analysis so
    endpoints can run the LLM call outside any DB transaction (Neon's SSL
    proxy will close idle connections held during long HTTP calls)."""
    event = EmotionEvent(
        user_id=user_id,
        source=source,
        source_ref_id=source_ref_id,
        text=text[:4000] if text else None,
        dominant_emotion=result.dominant_emotion,
        sentiment=result.sentiment,
        confidence=result.confidence,
        signals=result.signals,
        provider=result.provider,
        model=result.model,
    )
    db.add(event)
    await db.flush()

    for emo, score in result.scores.items():
        db.add(EmotionScore(event_id=event.id, emotion=emo, score=float(score)))

    await db.commit()
    await db.refresh(event)
    return event


async def list_events(
    db: AsyncSession,
    *,
    user_id: str,
    limit: int = 50,
    since: Optional[datetime] = None,
    source: Optional[str] = None,
) -> List[EmotionEvent]:
    stmt = (
        select(EmotionEvent)
        .where(EmotionEvent.user_id == user_id)
        .options(selectinload(EmotionEvent.scores))
        .order_by(desc(EmotionEvent.created_at))
        .limit(min(limit, 500))
    )
    if since is not None:
        stmt = stmt.where(EmotionEvent.created_at >= since)
    if source:
        stmt = stmt.where(EmotionEvent.source == source)
    return list((await db.execute(stmt)).scalars().all())


async def get_event_for_ref(
    db: AsyncSession,
    *,
    user_id: str,
    source_ref_id: str,
) -> Optional[EmotionEvent]:
    stmt = (
        select(EmotionEvent)
        .where(
            EmotionEvent.user_id == user_id,
            EmotionEvent.source_ref_id == source_ref_id,
        )
        .options(selectinload(EmotionEvent.scores))
        .order_by(desc(EmotionEvent.created_at))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
