from __future__ import annotations

import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, EmotionAnalyzerDep, LLMRouterDep
from app.db import session as _session_mod
from app.db.session import get_db
from app.schemas.journal import (
    JournalAnalysisRead,
    JournalCreate,
    JournalEntryList,
    JournalEntryRead,
    JournalUpdate,
)
from app.services import emotion_service, journal_service
from app.services.ai.journal import JournalReflector, LLMJournalReflector
from app.services.ai.llm.router import LLMRouter
from app.services.emotion import EmotionAnalyzer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/journal", tags=["journal"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_journal_reflector(llm: LLMRouterDep) -> JournalReflector:
    return LLMJournalReflector(llm)


ReflectorDep = Annotated[JournalReflector, Depends(get_journal_reflector)]


def _preview(text: str, n: int = 140) -> str:
    t = " ".join((text or "").split())
    return (t[: n - 1] + "…") if len(t) > n else t


def _to_read(entry) -> JournalEntryRead:
    analysis = (
        JournalAnalysisRead.model_validate(entry.analysis) if entry.analysis else None
    )
    return JournalEntryRead(
        id=entry.id,
        title=entry.title,
        content=entry.content,
        mood=entry.mood,
        tags=list(entry.tags) if entry.tags else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        analysis=analysis,
    )


async def _analyze_entry_bg(
    reflector: JournalReflector,
    analyzer: EmotionAnalyzer,
    *,
    user_id: str,
    entry_id: str,
    title: Optional[str],
    content: str,
    mood: Optional[int],
) -> None:
    """Runs reflection + emotion analysis in the background after entry creation."""
    try:
        reflection = await reflector.reflect(title=title, content=content, mood=mood)
    except Exception as e:  # pragma: no cover
        log.warning("journal bg: reflector failed: %s", e)
        reflection = None

    try:
        emotion_result = await analyzer.analyze(content)
    except Exception as e:  # pragma: no cover
        log.warning("journal bg: emotion analyzer failed: %s", e)
        emotion_result = None

    try:
        async with _session_mod.SessionLocal() as db:
            if reflection is not None:
                await journal_service.persist_reflection(
                    db,
                    user_id=user_id,
                    entry_id=entry_id,
                    reflection=reflection,
                )
            if emotion_result is not None:
                await emotion_service.persist_result(
                    db,
                    user_id=user_id,
                    text=content,
                    source="journal",
                    source_ref_id=entry_id,
                    result=emotion_result,
                )
    except Exception as e:  # pragma: no cover
        log.warning("journal bg: persist failed: %s", e)


@router.post("", response_model=JournalEntryRead, status_code=201)
async def create_journal(
    req: JournalCreate,
    user: CurrentUser,
    db: DbDep,
    reflector: ReflectorDep,
    analyzer: EmotionAnalyzerDep,
    background: BackgroundTasks,
) -> JournalEntryRead:
    entry = await journal_service.create_entry(
        db,
        user_id=user.id,
        title=req.title,
        content=req.content,
        mood=req.mood,
        tags=req.tags,
    )

    if req.analyze:
        background.add_task(
            _analyze_entry_bg,
            reflector,
            analyzer,
            user_id=user.id,
            entry_id=entry.id,
            title=entry.title,
            content=entry.content,
            mood=entry.mood,
        )

    return _to_read(entry)


@router.get("", response_model=List[JournalEntryList])
async def list_journal(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[JournalEntryList]:
    entries = await journal_service.list_entries(
        db, user_id=user.id, limit=limit, offset=offset
    )
    return [
        JournalEntryList(
            id=e.id,
            title=e.title,
            mood=e.mood,
            tags=list(e.tags) if e.tags else None,
            created_at=e.created_at,
            updated_at=e.updated_at,
            has_analysis=e.analysis is not None,
            preview=_preview(e.content),
        )
        for e in entries
    ]


@router.get("/{entry_id}", response_model=JournalEntryRead)
async def get_journal(
    entry_id: str,
    user: CurrentUser,
    db: DbDep,
) -> JournalEntryRead:
    entry = await journal_service.get_entry(db, user_id=user.id, entry_id=entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    return _to_read(entry)


@router.patch("/{entry_id}", response_model=JournalEntryRead)
async def update_journal(
    entry_id: str,
    patch: JournalUpdate,
    user: CurrentUser,
    db: DbDep,
) -> JournalEntryRead:
    entry = await journal_service.update_entry(
        db,
        user_id=user.id,
        entry_id=entry_id,
        title=patch.title,
        content=patch.content,
        mood=patch.mood,
        tags=patch.tags,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    return _to_read(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_journal(
    entry_id: str,
    user: CurrentUser,
    db: DbDep,
) -> None:
    ok = await journal_service.delete_entry(db, user_id=user.id, entry_id=entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="journal entry not found")


@router.post("/{entry_id}/analyze", response_model=JournalEntryRead)
async def analyze_journal(
    entry_id: str,
    user: CurrentUser,
    reflector: ReflectorDep,
    analyzer: EmotionAnalyzerDep,
) -> JournalEntryRead:
    """Synchronous reflection + emotion analysis for an existing entry.

    Runs the LLM calls without holding a DB connection (see chat/emotion for
    the same pattern) and then persists the result in a short-lived session.
    """
    # Load entry contents in a short session.
    async with _session_mod.SessionLocal() as db:
        entry = await journal_service.get_entry(
            db, user_id=user.id, entry_id=entry_id
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="journal entry not found")
        title = entry.title
        content = entry.content
        mood = entry.mood

    reflection = await reflector.reflect(title=title, content=content, mood=mood)
    try:
        emotion_result = await analyzer.analyze(content)
    except Exception as e:  # pragma: no cover
        log.warning("journal analyze: emotion analyzer failed: %s", e)
        emotion_result = None

    async with _session_mod.SessionLocal() as db:
        entry = await journal_service.persist_reflection(
            db,
            user_id=user.id,
            entry_id=entry_id,
            reflection=reflection,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="journal entry not found")

    if emotion_result is not None:
        async with _session_mod.SessionLocal() as db:
            await emotion_service.persist_result(
                db,
                user_id=user.id,
                text=content,
                source="journal",
                source_ref_id=entry_id,
                result=emotion_result,
            )

    async with _session_mod.SessionLocal() as db:
        entry = await journal_service.get_entry(
            db, user_id=user.id, entry_id=entry_id
        )
        if entry is None:
            raise HTTPException(status_code=404, detail="journal entry not found")
        return _to_read(entry)
