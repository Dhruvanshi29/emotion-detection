from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, EmotionAnalyzerDep, STTRouterDep
from app.core.config import get_settings
from app.db import session as _session_mod
from app.db.session import get_db
from app.schemas.emotion import (
    EmotionAnalyzeRequest,
    EmotionAnalyzeResponse,
    EmotionEventRead,
)
from app.schemas.voice import (
    STTProvidersStatus,
    VoiceAnalysisRead,
    VoiceAnalyzeResponse,
)
from app.schemas.facial import (
    FacialAnalysisRead,
    FacialAnalyzeRequest,
    FacialAnalyzeResponse,
)
from app.services import emotion_service, facial_service, voice_service
from app.services.stt.base import STTProviderError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/emotion", tags=["emotion"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/text", response_model=EmotionAnalyzeResponse)
async def analyze_text(
    req: EmotionAnalyzeRequest,
    user: CurrentUser,
    analyzer: EmotionAnalyzerDep,
) -> EmotionAnalyzeResponse:
    # Do the LLM call FIRST without a live DB connection to avoid Neon
    # terminating an idle SSL socket during a long-running analyzer call.
    # Then open a fresh short-lived session for persistence.
    result = await analyzer.analyze(req.text)
    async with _session_mod.SessionLocal() as db:
        event = await emotion_service.persist_result(
            db,
            user_id=user.id,
            text=req.text,
            source=req.source,
            source_ref_id=req.source_ref_id,
            result=result,
        )
    return EmotionAnalyzeResponse(
        event_id=event.id,
        dominant_emotion=result.dominant_emotion,
        sentiment=result.sentiment,
        confidence=result.confidence,
        scores=result.scores,
        signals=result.signals,
        provider=result.provider,
        model=result.model,
    )


@router.get("/events", response_model=List[EmotionEventRead])
async def list_events(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=500),
    since: Optional[datetime] = None,
    source: Optional[str] = None,
) -> List[EmotionEventRead]:
    events = await emotion_service.list_events(
        db, user_id=user.id, limit=limit, since=since, source=source
    )
    return [EmotionEventRead.model_validate(e) for e in events]


@router.get("/message/{message_id}", response_model=Optional[EmotionEventRead])
async def get_event_for_message(
    message_id: str,
    user: CurrentUser,
    db: DbDep,
) -> Optional[EmotionEventRead]:
    """Look up the (async) emotion event linked to a chat message, if ready yet."""
    event = await emotion_service.get_event_for_ref(
        db, user_id=user.id, source_ref_id=message_id
    )
    return EmotionEventRead.model_validate(event) if event else None


@router.get("/stt-providers", response_model=STTProvidersStatus)
def stt_providers_status(stt: STTRouterDep) -> STTProvidersStatus:
    return STTProvidersStatus(
        chain=stt._settings.stt_provider_chain_list,
        available=stt.available_providers(),
    )


@router.post("/audio", response_model=VoiceAnalyzeResponse)
async def analyze_audio(
    user: CurrentUser,
    stt: STTRouterDep,
    analyzer: EmotionAnalyzerDep,
    file: UploadFile = File(...),
    source: str = Form(default="adhoc"),
    source_ref_id: Optional[str] = Form(default=None),
    language: Optional[str] = Form(default=None),
    provider: Optional[str] = Form(default=None),
) -> VoiceAnalyzeResponse:
    """Transcribe an audio recording, extract acoustic signals, and analyze
    emotion from the transcript. Requires explicit `mic_consent` on the user
    (plan §13/§18). Raw audio is NEVER persisted."""

    prefs = user.preferences
    if prefs is None or not prefs.mic_consent:
        raise HTTPException(
            status_code=403,
            detail="microphone consent required — enable it in your profile",
        )

    settings = get_settings()
    # Read at most one byte beyond the cap. Reading the entire upload first
    # would let a malicious multipart request exhaust worker memory before the
    # size check ran (this route is intentionally exempt from the JSON cap).
    audio = await file.read(settings.voice_max_upload_bytes + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(audio) > settings.voice_max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"audio too large (>{settings.voice_max_upload_bytes} bytes)",
        )

    # §3.5: validate the file by its content signature, not the client-supplied
    # Content-Type / filename. Refuse anything that isn't a recognized audio
    # container so the STT provider can't be tricked into processing a
    # disguised payload.
    from app.services.audio.sniff import is_allowed_audio

    allowed, sniffed = is_allowed_audio(audio)
    if not allowed:
        raise HTTPException(
            status_code=415,
            detail="unsupported audio format",
        )
    effective_content_type = sniffed or (
        file.content_type or "application/octet-stream"
    )

    try:
        result = await voice_service.run_pipeline(
            stt,
            analyzer,
            audio=audio,
            filename=file.filename or "audio",
            content_type=effective_content_type,
            language=language,
            preferred=provider,
        )
    except STTProviderError as e:
        log.warning("voice: STT failed: %s", e)
        raise HTTPException(
            status_code=502, detail="transcription provider unavailable"
        ) from e

    # Reject over-long recordings after transcription (cheap way to enforce
    # duration cap when the client didn't tell us up-front).
    duration = result.features.duration_seconds or result.stt.duration_seconds
    if duration is not None and duration > settings.voice_max_duration_seconds:
        raise HTTPException(
            status_code=413,
            detail=(
                f"recording too long ({duration:.0f}s > "
                f"{settings.voice_max_duration_seconds:.0f}s cap)"
            ),
        )

    async with _session_mod.SessionLocal() as db:
        va, ev = await voice_service.persist_pipeline(
            db,
            user_id=user.id,
            source=source,
            source_ref_id=source_ref_id,
            result=result,
        )

    e = result.emotion
    return VoiceAnalyzeResponse(
        voice_analysis_id=va.id,
        emotion_event_id=ev.id if ev else None,
        transcript=va.transcript,
        language=va.language,
        duration_seconds=va.duration_seconds,
        word_count=va.word_count,
        speech_rate_wpm=va.speech_rate_wpm,
        features_available=va.features_available,
        energy_rms=va.energy_rms,
        pause_ratio=va.pause_ratio,
        stt_provider=va.stt_provider,
        stt_model=va.stt_model,
        dominant_emotion=e.dominant_emotion if e else None,
        sentiment=e.sentiment if e else None,
        confidence=e.confidence if e else None,
        scores=e.scores if e else {},
        signals=e.signals if e else [],
        emotion_provider=e.provider if e else None,
        emotion_model=e.model if e else None,
    )


@router.get("/voice/{voice_id}", response_model=VoiceAnalysisRead)
async def get_voice_analysis(
    voice_id: str,
    user: CurrentUser,
    db: DbDep,
) -> VoiceAnalysisRead:
    va = await voice_service.get_voice_analysis(
        db, user_id=user.id, voice_id=voice_id
    )
    if va is None:
        raise HTTPException(status_code=404, detail="voice analysis not found")
    return VoiceAnalysisRead.model_validate(va)


@router.get("/voice", response_model=List[VoiceAnalysisRead])
async def list_voice_analyses(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = None,
) -> List[VoiceAnalysisRead]:
    rows = await voice_service.list_voice_analyses(
        db, user_id=user.id, limit=limit, source=source
    )
    return [VoiceAnalysisRead.model_validate(r) for r in rows]


@router.post("/video", response_model=FacialAnalyzeResponse)
async def submit_facial_signals(
    req: FacialAnalyzeRequest,
    user: CurrentUser,
) -> FacialAnalyzeResponse:
    """Submit browser-derived facial signals (plan §6, §13).

    Raw frames, thumbnails, embeddings and landmark coordinates are NEVER
    accepted here. The client must run its face/expression classifier
    on-device and send only the aggregated distribution.
    """
    prefs = user.preferences
    if prefs is None or not prefs.camera_consent:
        raise HTTPException(
            status_code=403,
            detail="camera consent required — enable it in your profile",
        )

    async with _session_mod.SessionLocal() as db:
        fa, ev = await facial_service.persist_submission(
            db, user_id=user.id, req=req
        )

    return FacialAnalyzeResponse(
        facial_analysis_id=fa.id,
        emotion_event_id=ev.id,
        sample_count=fa.sample_count,
        duration_seconds=fa.duration_seconds,
        faces_detected_ratio=fa.faces_detected_ratio,
        dominant_emotion=fa.dominant_emotion,
        sentiment=fa.sentiment,
        confidence=fa.confidence,
        scores=fa.scores or {},
        signals=list(fa.signals or []),
        model_provider=fa.model_provider,
        model_name=fa.model_name,
    )


@router.get("/face/{facial_id}", response_model=FacialAnalysisRead)
async def get_facial_analysis(
    facial_id: str,
    user: CurrentUser,
    db: DbDep,
) -> FacialAnalysisRead:
    fa = await facial_service.get_facial_analysis(
        db, user_id=user.id, facial_id=facial_id
    )
    if fa is None:
        raise HTTPException(status_code=404, detail="facial analysis not found")
    return FacialAnalysisRead.model_validate(fa)


@router.get("/face", response_model=List[FacialAnalysisRead])
async def list_facial_analyses(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = None,
) -> List[FacialAnalysisRead]:
    rows = await facial_service.list_facial_analyses(
        db, user_id=user.id, limit=limit, source=source
    )
    return [FacialAnalysisRead.model_validate(r) for r in rows]
