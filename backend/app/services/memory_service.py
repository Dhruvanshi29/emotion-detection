"""Memory service — CRUD, hybrid retrieval, extraction, summarization (Phase 11).

Retrieval is hybrid so that even with a lightweight local embedder the results
stay useful:
  * cosine similarity on hash-bag embeddings (semantic-ish)
  * substring keyword bonus (literal match)
  * pinned + importance boosts (user intent)

The extraction and summarization functions do NOT hit the LLM router — they
run deterministic heuristics so tests are stable. A production deployment can
override `summarize_conversation` to call an LLM.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation, Message
from app.models.memory import ConversationSummary, UserMemory
from app.models.user import UserPreferences
from app.schemas.memory import MemoryCandidate, MemoryCreate, MemoryUpdate
from app.services.embeddings import _tokens, cosine, get_embedder


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryDisabledError(RuntimeError):
    """Raised when the user has disabled AI memory via preferences (§3.3)."""


async def _memory_enabled(db: AsyncSession, user_id: str) -> bool:
    row = (
        await db.execute(
            select(UserPreferences.memory_enabled).where(
                UserPreferences.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    # Default to True when the row is missing so tests / seed users work.
    return True if row is None else bool(row)


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


async def create_memory(
    db: AsyncSession, *, user_id: str, payload: MemoryCreate
) -> UserMemory:
    if not await _memory_enabled(db, user_id):
        raise MemoryDisabledError("memory disabled by user preference")
    embedder = get_embedder()
    vec = embedder.embed([f"{payload.title}\n{payload.content}"])[0]
    row = UserMemory(
        user_id=user_id,
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        source=payload.source,
        source_ref_id=payload.source_ref_id,
        tags=payload.tags,
        importance=payload.importance,
        pinned=payload.pinned,
        embedding=vec,
        embedding_model=embedder.name,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_memory(
    db: AsyncSession, *, user_id: str, memory_id: str
) -> Optional[UserMemory]:
    q = select(UserMemory).where(
        UserMemory.id == memory_id, UserMemory.user_id == user_id
    )
    return (await db.execute(q)).scalar_one_or_none()


async def list_memories(
    db: AsyncSession,
    *,
    user_id: str,
    kind: Optional[str] = None,
    pinned: Optional[bool] = None,
    include_inactive: bool = False,
) -> List[UserMemory]:
    q = select(UserMemory).where(UserMemory.user_id == user_id)
    if not include_inactive:
        q = q.where(UserMemory.is_active.is_(True))
    if kind is not None:
        q = q.where(UserMemory.kind == kind)
    if pinned is not None:
        q = q.where(UserMemory.pinned.is_(pinned))
    q = q.order_by(
        UserMemory.pinned.desc(),
        UserMemory.importance.desc(),
        UserMemory.updated_at.desc(),
    )
    return list((await db.execute(q)).scalars().all())


async def update_memory(
    db: AsyncSession, *, memory: UserMemory, patch: MemoryUpdate
) -> UserMemory:
    data = patch.model_dump(exclude_unset=True)
    content_changed = False
    for k, v in data.items():
        if k in {"title", "content"} and getattr(memory, k) != v:
            content_changed = True
        setattr(memory, k, v)
    if content_changed:
        embedder = get_embedder()
        memory.embedding = embedder.embed([f"{memory.title}\n{memory.content}"])[0]
        memory.embedding_model = embedder.name
    await db.commit()
    await db.refresh(memory)
    return memory


async def delete_memory(db: AsyncSession, *, memory: UserMemory) -> None:
    await db.delete(memory)
    await db.commit()


async def delete_all_memories(db: AsyncSession, *, user_id: str) -> int:
    """Memory controls (§13) — hard-delete every memory for a user."""
    res = await db.execute(
        delete(UserMemory).where(UserMemory.user_id == user_id)
    )
    await db.commit()
    return int(res.rowcount or 0)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #


def _keyword_bonus(query: str, memory: UserMemory) -> float:
    """Substring + token-overlap bonus in [0, 0.35]."""
    q = (query or "").lower().strip()
    if not q:
        return 0.0
    hay = f"{memory.title}\n{memory.content}".lower()
    bonus = 0.0
    if q in hay:
        bonus += 0.25
    q_tokens = set(_tokens(query))
    m_tokens = set(_tokens(hay))
    if q_tokens and m_tokens:
        overlap = len(q_tokens & m_tokens) / max(len(q_tokens), 1)
        bonus += 0.1 * overlap
    return min(bonus, 0.35)


def _score_reasons(
    *, sim: float, kbonus: float, memory: UserMemory
) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = sim + kbonus
    if kbonus > 0:
        reasons.append("keyword match")
    if sim >= 0.4:
        reasons.append("semantic")
    if memory.pinned:
        score += 0.15
        reasons.append("pinned")
    if memory.importance >= 0.8:
        score += 0.05
        reasons.append("important")
    return score, reasons


async def retrieve(
    db: AsyncSession,
    *,
    user_id: str,
    query: str,
    k: int = 5,
    kinds: Optional[List[str]] = None,
) -> List[Dict]:
    if not await _memory_enabled(db, user_id):
        return []
    q = select(UserMemory).where(
        UserMemory.user_id == user_id, UserMemory.is_active.is_(True)
    )
    if kinds:
        q = q.where(UserMemory.kind.in_(list(kinds)))
    rows = list((await db.execute(q)).scalars().all())
    if not rows:
        return []
    embedder = get_embedder()
    qvec = embedder.embed([query])[0]

    scored: List[Tuple[float, List[str], UserMemory]] = []
    for m in rows:
        sim = cosine(qvec, m.embedding or []) if m.embedding else 0.0
        kbonus = _keyword_bonus(query, m)
        score, reasons = _score_reasons(sim=sim, kbonus=kbonus, memory=m)
        # Prune noise: nothing to say and nothing similar.
        if score <= 0 and not reasons:
            continue
        scored.append((score, reasons, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"memory": m, "score": round(s, 4), "reasons": r}
        for s, r, m in scored[:k]
    ]


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


_PATTERNS: List[Tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"\bI (?:love|like|enjoy|prefer)\s+([^.!?\n]+)", re.I), "preference", 0.75),
    (re.compile(r"\bI (?:hate|dislike|don't like|do not like)\s+([^.!?\n]+)", re.I), "preference", 0.7),
    (re.compile(r"\bI want to\s+([^.!?\n]+)", re.I), "goal", 0.7),
    (re.compile(r"\bI(?:'m| am) trying to\s+([^.!?\n]+)", re.I), "goal", 0.75),
    (re.compile(r"\bMy goal is to\s+([^.!?\n]+)", re.I), "goal", 0.85),
    (re.compile(r"\bI(?:'m| am) a\s+([^.!?\n]+)", re.I), "fact", 0.65),
    (re.compile(r"\bI live in\s+([^.!?\n]+)", re.I), "fact", 0.7),
    (re.compile(r"\bI work as\s+([^.!?\n]+)", re.I), "fact", 0.7),
]


def extract_candidates(text: str, *, limit: int = 8) -> List[MemoryCandidate]:
    seen: set[str] = set()
    out: List[MemoryCandidate] = []
    for pat, kind, conf in _PATTERNS:
        for m in pat.finditer(text):
            body = m.group(1).strip().rstrip(",;:")
            body = re.sub(r"\s+", " ", body)
            if len(body) < 3 or len(body) > 200:
                continue
            content = m.group(0).strip()
            # Dedup on kind + first content word so "hiking" and "hiking so much"
            # collapse into a single memory candidate.
            first_word = body.split()[0].lower()
            key = f"{kind}:{first_word}"
            if key in seen:
                continue
            seen.add(key)
            title_words = body.split()
            title = " ".join(title_words[:6])
            out.append(
                MemoryCandidate(
                    kind=kind, title=title[:160], content=content[:400], confidence=conf
                )
            )
            if len(out) >= limit:
                return out
    return out


# --------------------------------------------------------------------------- #
# Conversation summaries
# --------------------------------------------------------------------------- #


def _extractive_summary(messages: List[Message]) -> Tuple[str, List[str]]:
    """Cheap deterministic fallback — pull the first sentence of each user
    turn, plus a short digest of the last assistant turn."""
    key_points: List[str] = []
    for m in messages:
        if m.role != "user":
            continue
        first = re.split(r"[.!?\n]", m.content, maxsplit=1)[0].strip()
        if 6 < len(first) < 200:
            key_points.append(first)
    if not key_points:
        for m in messages[:3]:
            key_points.append(m.content[:120].strip())
    key_points = key_points[:8]
    joined = "; ".join(key_points)
    tail = ""
    for m in reversed(messages):
        if m.role == "assistant":
            tail = m.content.strip().split("\n")[0][:200]
            break
    body = f"Recent themes: {joined}."
    if tail:
        body += f" Companion last said: {tail}"
    return body[:2000], key_points


async def get_summary(
    db: AsyncSession, *, user_id: str, conversation_id: str
) -> Optional[ConversationSummary]:
    q = select(ConversationSummary).where(
        ConversationSummary.conversation_id == conversation_id,
        ConversationSummary.user_id == user_id,
    )
    return (await db.execute(q)).scalar_one_or_none()


async def summarize_conversation(
    db: AsyncSession, *, user_id: str, conversation_id: str
) -> ConversationSummary:
    conv = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        raise LookupError("conversation_not_found")

    msgs = list(
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
        ).scalars().all()
    )

    summary, key_points = _extractive_summary(msgs)
    embedder = get_embedder()
    vec = embedder.embed([summary])[0]

    existing = await get_summary(
        db, user_id=user_id, conversation_id=conversation_id
    )
    last_id = msgs[-1].id if msgs else None
    if existing is None:
        row = ConversationSummary(
            conversation_id=conversation_id,
            user_id=user_id,
            summary=summary,
            key_points=key_points,
            message_count=len(msgs),
            last_message_id=last_id,
            embedding=vec,
            embedding_model=embedder.name,
            provider="extractive",
            model="deterministic-v1",
        )
        db.add(row)
    else:
        existing.summary = summary
        existing.key_points = key_points
        existing.message_count = len(msgs)
        existing.last_message_id = last_id
        existing.embedding = vec
        existing.embedding_model = embedder.name
        existing.provider = "extractive"
        existing.model = "deterministic-v1"
        row = existing
    await db.commit()
    await db.refresh(row)
    return row


__all__ = [
    "create_memory",
    "get_memory",
    "list_memories",
    "update_memory",
    "delete_memory",
    "delete_all_memories",
    "retrieve",
    "extract_candidates",
    "get_summary",
    "summarize_conversation",
]
