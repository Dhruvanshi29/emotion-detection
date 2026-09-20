"""Voice analysis orchestration (plan §7).

Pipeline: STT -> acoustic features -> text emotion on the transcript -> persist.
Raw audio bytes are consumed here and MUST NOT be persisted anywhere.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emotion import EmotionEvent
from app.models.voice import VoiceAnalysis
from app.services import emotion_service
from app.services.audio import AcousticFeatures, extract_features
from app.services.emotion import EmotionAnalyzer, TextEmotionResult
from app.services.stt import STTResult, STTRouter

logger = logging.getLogger(__name__)


@dataclass
class VoicePipelineResult:
    stt: STTResult
    features: AcousticFeatures
    emotion: Optional[TextEmotionResult]
    speech_rate_wpm: Optional[float]
    word_count: int


async def run_pipeline(
    router: STTRouter,
    analyzer: EmotionAnalyzer,
    *,
    audio: bytes,
    filename: str,
    content_type: str,
    language: Optional[str] = None,
    preferred: Optional[str] = None,
) -> VoicePipelineResult:
    """Run STT + acoustic + emotion outside any DB session (Neon-safe)."""
    stt = await router.transcribe(
        audio,
        filename=filename,
        content_type=content_type,
        language=language,
        preferred=preferred,
    )

    features = extract_features(
        audio, content_type=content_type, stt_duration=stt.duration_seconds
    )

    words = [w for w in stt.text.split() if w.strip()]
    word_count = len(words)
    duration = features.duration_seconds or stt.duration_seconds
    speech_rate_wpm: Optional[float] = None
    if duration and duration > 0 and word_count > 0:
        speech_rate_wpm = word_count / (duration / 60.0)

    emotion: Optional[TextEmotionResult] = None
    if stt.text.strip():
        try:
            emotion = await analyzer.analyze(stt.text)
        except Exception as e:  # pragma: no cover
            logger.warning("voice.pipeline: emotion analysis failed: %s", e)

    return VoicePipelineResult(
        stt=stt,
        features=features,
        emotion=emotion,
        speech_rate_wpm=speech_rate_wpm,
        word_count=word_count,
    )


async def persist_pipeline(
    db: AsyncSession,
    *,
    user_id: str,
    source: str,
    source_ref_id: Optional[str],
    result: VoicePipelineResult,
) -> tuple[VoiceAnalysis, Optional[EmotionEvent]]:
    emotion_event: Optional[EmotionEvent] = None
    if result.emotion is not None and result.stt.text.strip():
        emotion_event = await emotion_service.persist_result(
            db,
            user_id=user_id,
            text=result.stt.text,
            source="voice",
            source_ref_id=source_ref_id,
            result=result.emotion,
        )

    va = VoiceAnalysis(
        user_id=user_id,
        source=source,
        source_ref_id=source_ref_id,
        transcript=result.stt.text,
        language=result.stt.language,
        duration_seconds=result.features.duration_seconds
        or result.stt.duration_seconds,
        energy_rms=result.features.energy_rms,
        pause_ratio=result.features.pause_ratio,
        speech_rate_wpm=result.speech_rate_wpm,
        word_count=result.word_count,
        features_available=result.features.features_available,
        stt_provider=result.stt.provider,
        stt_model=result.stt.model,
        emotion_event_id=emotion_event.id if emotion_event else None,
    )
    db.add(va)
    await db.commit()
    await db.refresh(va)
    return va, emotion_event


async def get_voice_analysis(
    db: AsyncSession, *, user_id: str, voice_id: str
) -> Optional[VoiceAnalysis]:
    stmt = select(VoiceAnalysis).where(
        VoiceAnalysis.id == voice_id, VoiceAnalysis.user_id == user_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_voice_analyses(
    db: AsyncSession,
    *,
    user_id: str,
    limit: int = 50,
    source: Optional[str] = None,
) -> List[VoiceAnalysis]:
    stmt = select(VoiceAnalysis).where(VoiceAnalysis.user_id == user_id)
    if source:
        stmt = stmt.where(VoiceAnalysis.source == source)
    stmt = stmt.order_by(desc(VoiceAnalysis.created_at)).limit(min(max(1, limit), 200))
    return list((await db.execute(stmt)).scalars().all())
