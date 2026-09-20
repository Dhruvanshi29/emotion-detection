"""Facial analysis persistence (plan §6, §7, §13).

The classifier runs on-device (plan §addendum) so we only receive derived
signals here. This service re-derives dominant_emotion / sentiment /
confidence from the submitted score distribution so the client cannot claim
one label while sending a distribution that contradicts it.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emotion import EmotionEvent, EmotionScore
from app.models.facial import FacialAnalysis
from app.schemas.facial import (
    FacialAnalyzeRequest,
    dominant_and_sentiment,
    normalize_scores,
)

logger = logging.getLogger(__name__)


async def persist_submission(
    db: AsyncSession,
    *,
    user_id: str,
    req: FacialAnalyzeRequest,
) -> tuple[FacialAnalysis, EmotionEvent]:
    scores = normalize_scores(req.scores)
    dom, sent, conf = dominant_and_sentiment(scores)

    event = EmotionEvent(
        user_id=user_id,
        source="face",
        source_ref_id=req.source_ref_id,
        text=None,
        dominant_emotion=dom,
        sentiment=sent,
        confidence=conf,
        signals=list(req.signals),
        provider=req.model_provider,
        model=req.model_name,
    )
    db.add(event)
    await db.flush()
    for emo, s in scores.items():
        db.add(EmotionScore(event_id=event.id, emotion=emo, score=float(s)))

    fa = FacialAnalysis(
        user_id=user_id,
        source=req.source,
        source_ref_id=req.source_ref_id,
        sample_count=req.sample_count,
        duration_seconds=req.duration_seconds,
        faces_detected_ratio=req.faces_detected_ratio,
        dominant_emotion=dom,
        sentiment=sent,
        confidence=conf,
        scores=scores,
        signals=list(req.signals),
        model_provider=req.model_provider,
        model_name=req.model_name,
        emotion_event_id=event.id,
    )
    db.add(fa)
    await db.commit()
    await db.refresh(fa)
    await db.refresh(event)
    return fa, event


async def get_facial_analysis(
    db: AsyncSession, *, user_id: str, facial_id: str
) -> Optional[FacialAnalysis]:
    stmt = select(FacialAnalysis).where(
        FacialAnalysis.id == facial_id, FacialAnalysis.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_facial_analyses(
    db: AsyncSession,
    *,
    user_id: str,
    limit: int = 50,
    source: Optional[str] = None,
) -> List[FacialAnalysis]:
    stmt = select(FacialAnalysis).where(FacialAnalysis.user_id == user_id)
    if source:
        stmt = stmt.where(FacialAnalysis.source == source)
    stmt = stmt.order_by(desc(FacialAnalysis.created_at)).limit(min(max(1, limit), 200))
    return list((await db.execute(stmt)).scalars().all())
