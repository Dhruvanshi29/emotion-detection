"""Data export + deletion (plan §12 §13).

`export_user_data` builds a plain JSON snapshot of everything the platform
holds for a user. `delete_category` empties a category. `delete_account`
removes the User row and relies on CASCADE FKs to clear all owned data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditEvent, ConsentEvent
from app.models.auth_identity import AuthIdentity
from app.models.chat import Conversation, Message, RiskAssessment, SafetyEvent
from app.models.emotion import EmotionEvent, EmotionScore
from app.models.facial import FacialAnalysis
from app.models.journal import JournalAnalysis, JournalEntry
from app.models.memory import ConversationSummary, UserMemory
from app.models.reminder import Notification, Reminder
from app.models.user import User
from app.models.voice import VoiceAnalysis
from app.models.wellness import ExerciseSession, UserGoal


def _row_to_dict(row: Any, *, exclude: set[str] | None = None) -> Dict[str, Any]:
    """Serialize SQLAlchemy row to a JSON-safe dict via __table__.columns."""
    exclude = exclude or set()
    out: Dict[str, Any] = {}
    for col in row.__table__.columns:
        if col.name in exclude:
            continue
        v = getattr(row, col.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        out[col.name] = v
    return out


async def export_user_data(db: AsyncSession, user_id: str) -> Dict[str, Any]:
    user = (
        await db.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.profile), selectinload(User.preferences))
        )
    ).scalar_one_or_none()
    if user is None:
        raise LookupError("user_not_found")

    convs = (
        await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .options(selectinload(Conversation.messages))
            .order_by(Conversation.created_at.asc())
        )
    ).scalars().all()

    chat_dump: List[Dict[str, Any]] = []
    for c in convs:
        chat_dump.append(
            {
                **_row_to_dict(c),
                "messages": [_row_to_dict(m) for m in c.messages],
            }
        )

    async def _all(model, order_col=None):
        q = select(model).where(model.user_id == user_id)
        if order_col is not None:
            q = q.order_by(order_col)
        rows = (await db.execute(q)).scalars().all()
        return [_row_to_dict(r) for r in rows]

    data: Dict[str, Any] = {
        "chat": chat_dump,
        "journal_entries": await _all(JournalEntry, JournalEntry.created_at.asc()),
        "emotion_events": await _all(EmotionEvent, EmotionEvent.created_at.asc()),
        "voice_analyses": await _all(VoiceAnalysis, VoiceAnalysis.created_at.asc()),
        "facial_analyses": await _all(FacialAnalysis, FacialAnalysis.created_at.asc()),
        "exercise_sessions": await _all(ExerciseSession, ExerciseSession.started_at.asc()),
        "user_goals": await _all(UserGoal, UserGoal.created_at.asc()),
        "reminders": await _all(Reminder, Reminder.created_at.asc()),
        "notifications": await _all(Notification, Notification.scheduled_for.asc()),
        "memories": await _all(UserMemory, UserMemory.created_at.asc()),
        "conversation_summaries": await _all(
            ConversationSummary, ConversationSummary.created_at.asc()
        ),
        "consent_events": [
            _row_to_dict(e)
            for e in (
                await db.execute(
                    select(ConsentEvent)
                    .where(ConsentEvent.user_id == user_id)
                    .order_by(ConsentEvent.created_at.asc())
                )
            ).scalars().all()
        ],
        "audit_events": [
            _row_to_dict(e)
            for e in (
                await db.execute(
                    select(AuditEvent)
                    .where(AuditEvent.user_id == user_id)
                    .order_by(AuditEvent.created_at.asc())
                )
            ).scalars().all()
        ],
        "auth_identities": [
            _row_to_dict(identity, exclude={"subject"})
            for identity in (
                await db.execute(
                    select(AuthIdentity)
                    .where(AuthIdentity.user_id == user_id)
                    .order_by(AuthIdentity.created_at.asc())
                )
            ).scalars().all()
        ],
    }

    counts = {k: len(v) for k, v in data.items()}

    user_dict = _row_to_dict(user, exclude={"hashed_password"})
    user_dict["profile"] = (
        _row_to_dict(user.profile) if user.profile is not None else None
    )
    user_dict["preferences"] = (
        _row_to_dict(user.preferences) if user.preferences is not None else None
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user": user_dict,
        "counts": counts,
        "data": data,
    }


# category -> list of (Model, extra_filter_or_None). Delete order matters when
# a table's rows have children with CASCADE.
_CATEGORY_MAP = {
    "chat": [SafetyEvent, Conversation],  # SafetyEvent first for orphan rows
    "journal": [JournalEntry],  # cascades to JournalAnalysis
    "emotion": [EmotionEvent],  # cascades to EmotionScore
    "voice": [VoiceAnalysis],
    "facial": [FacialAnalysis],
    "wellness": [ExerciseSession, UserGoal],
    "reminders": [Reminder, Notification],
    "memory": [UserMemory, ConversationSummary],
    "audit": [ConsentEvent, AuditEvent],
}


async def delete_category(db: AsyncSession, user_id: str, category: str) -> int:
    models = _CATEGORY_MAP.get(category)
    if models is None:
        raise ValueError(f"unknown category: {category}")
    total = 0
    for model in models:
        res = await db.execute(delete(model).where(model.user_id == user_id))
        total += int(res.rowcount or 0)
    await db.commit()
    return total


async def delete_account(db: AsyncSession, user_id: str) -> Dict[str, int]:
    """Delete the user and return per-category counts prior to removal."""
    counts: Dict[str, int] = {}
    # Snapshot counts so caller can report on what was cleared.
    from sqlalchemy import func

    async def _count(model) -> int:
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(
                        select(model).where(model.user_id == user_id).subquery()
                    )
                )
            ).scalar_one()
        )

    for cat, models in _CATEGORY_MAP.items():
        n = 0
        for m in models:
            n += await _count(m)
        counts[cat] = n

    # Delete user; CASCADE clears everything owned. audit_events.user_id has
    # ON DELETE SET NULL so its history remains but is anonymized.
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise LookupError("user_not_found")
    await db.delete(user)
    await db.commit()
    return counts
