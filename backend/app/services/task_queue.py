"""Durable database queue for recoverable AI analysis jobs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_job import TaskJob

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue(db: AsyncSession, *, kind: str, dedupe_key: str, payload: dict) -> TaskJob | None:
    row = TaskJob(kind=kind, dedupe_key=dedupe_key, payload=payload)
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
        return row
    except IntegrityError:
        await db.rollback()
        return None


async def _run_payload(db: AsyncSession, row: TaskJob) -> None:
    from app.services.ai.llm.router import get_llm_router
    from app.services.emotion import LLMEmotionAnalyzer

    payload = dict(row.payload or {})
    analyzer = LLMEmotionAnalyzer(get_llm_router())
    if row.kind == "chat_emotion":
        from app.services import emotion_service

        result = await analyzer.analyze(str(payload["text"]))
        await emotion_service.persist_result(
            db,
            user_id=str(payload["user_id"]),
            text=str(payload["text"]),
            source="chat",
            source_ref_id=str(payload["message_id"]),
            result=result,
        )
        return
    if row.kind == "journal_analysis":
        from app.services import emotion_service, journal_service
        from app.services.ai.journal import LLMJournalReflector

        reflector = LLMJournalReflector(get_llm_router())
        reflection = await reflector.reflect(
            title=payload.get("title"),
            content=str(payload["content"]),
            mood=payload.get("mood"),
        )
        await journal_service.persist_reflection(
            db,
            user_id=str(payload["user_id"]),
            entry_id=str(payload["entry_id"]),
            reflection=reflection,
        )
        emotion = await analyzer.analyze(str(payload["content"]))
        await emotion_service.persist_result(
            db,
            user_id=str(payload["user_id"]),
            text=str(payload["content"]),
            source="journal",
            source_ref_id=str(payload["entry_id"]),
            result=emotion,
        )
        return
    raise ValueError(f"unknown task kind: {row.kind}")


async def process_pending(db: AsyncSession, *, limit: int = 10) -> int:
    now = _now()
    rows = list(
        (
            await db.execute(
                select(TaskJob)
                .where(
                    or_(
                        TaskJob.status == "queued",
                        and_(
                            TaskJob.status == "running",
                            TaskJob.locked_at < now - timedelta(minutes=15),
                        ),
                    ),
                    TaskJob.available_at <= now,
                    TaskJob.attempts < 5,
                )
                .order_by(TaskJob.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
    )
    for row in rows:
        row.status = "running"
        row.locked_at = now
        row.attempts += 1
    await db.commit()

    completed = 0
    for row in rows:
        try:
            await _run_payload(db, row)
            row.status = "completed"
            row.completed_at = _now()
            row.last_error = None
            completed += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("task %s failed on attempt %d (%s)", row.id, row.attempts, type(exc).__name__)
            row.status = "failed" if row.attempts >= 5 else "queued"
            row.available_at = _now() + timedelta(minutes=min(30, 2 ** row.attempts))
            row.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
        finally:
            row.locked_at = None
            await db.commit()
    return completed
