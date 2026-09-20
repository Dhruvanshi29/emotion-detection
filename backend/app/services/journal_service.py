"""Journal CRUD + AI reflection orchestration (plan §4, §10)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.journal import JournalAnalysis, JournalEntry
from app.services.ai.journal import JournalReflection, JournalReflector


async def create_entry(
    db: AsyncSession,
    *,
    user_id: str,
    title: Optional[str],
    content: str,
    mood: Optional[int],
    tags: Optional[List[str]],
) -> JournalEntry:
    from app.services.ai.safety.prompt_guard import sanitize_user_text

    content = sanitize_user_text(content, max_len=20000)
    if title:
        title = sanitize_user_text(title, max_len=200) or None
    entry = JournalEntry(
        user_id=user_id,
        title=title,
        content=content,
        mood=mood,
        tags=tags,
    )
    db.add(entry)
    await db.commit()
    fetched = await get_entry(db, user_id=user_id, entry_id=entry.id)
    assert fetched is not None
    return fetched


async def get_entry(
    db: AsyncSession, *, user_id: str, entry_id: str
) -> Optional[JournalEntry]:
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == entry_id, JournalEntry.user_id == user_id)
        .options(selectinload(JournalEntry.analysis))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_entries(
    db: AsyncSession,
    *,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> List[JournalEntry]:
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.user_id == user_id)
        .options(selectinload(JournalEntry.analysis))
        .order_by(desc(JournalEntry.created_at))
        .offset(max(0, offset))
        .limit(min(max(1, limit), 200))
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_entries(db: AsyncSession, *, user_id: str) -> int:
    stmt = select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id)
    return int((await db.execute(stmt)).scalar_one() or 0)


async def update_entry(
    db: AsyncSession,
    *,
    user_id: str,
    entry_id: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    mood: Optional[int] = None,
    tags: Optional[List[str]] = None,
) -> Optional[JournalEntry]:
    entry = await get_entry(db, user_id=user_id, entry_id=entry_id)
    if entry is None:
        return None
    if title is not None:
        entry.title = title
    if content is not None:
        entry.content = content
    if mood is not None:
        entry.mood = mood
    if tags is not None:
        entry.tags = tags
    await db.commit()
    fetched = await get_entry(db, user_id=user_id, entry_id=entry_id)
    return fetched


async def delete_entry(
    db: AsyncSession, *, user_id: str, entry_id: str
) -> bool:
    entry = await get_entry(db, user_id=user_id, entry_id=entry_id)
    if entry is None:
        return False
    await db.delete(entry)
    await db.commit()
    return True


async def analyze_entry(
    db: AsyncSession,
    reflector: JournalReflector,
    *,
    user_id: str,
    entry_id: str,
) -> Tuple[Optional[JournalEntry], Optional[JournalReflection]]:
    """Load entry, run reflection outside the DB session, then upsert analysis."""
    entry = await get_entry(db, user_id=user_id, entry_id=entry_id)
    if entry is None:
        return None, None
    title = entry.title
    content = entry.content
    mood = entry.mood

    reflection = await reflector.reflect(title=title, content=content, mood=mood)
    entry = await persist_reflection(
        db, user_id=user_id, entry_id=entry_id, reflection=reflection
    )
    return entry, reflection


async def persist_reflection(
    db: AsyncSession,
    *,
    user_id: str,
    entry_id: str,
    reflection: JournalReflection,
) -> Optional[JournalEntry]:
    entry = await get_entry(db, user_id=user_id, entry_id=entry_id)
    if entry is None:
        return None
    if entry.analysis is not None:
        await db.delete(entry.analysis)
        await db.flush()

    analysis = JournalAnalysis(
        entry_id=entry.id,
        summary=reflection.summary,
        themes=reflection.themes or None,
        reflection_prompt=reflection.reflection_prompt,
        key_feelings=reflection.key_feelings or None,
        dominant_emotion=reflection.dominant_emotion,
        sentiment=reflection.sentiment,
        confidence=reflection.confidence,
        provider=reflection.provider,
        model=reflection.model,
    )
    db.add(analysis)
    await db.commit()
    entry = await get_entry(db, user_id=user_id, entry_id=entry_id)
    return entry
