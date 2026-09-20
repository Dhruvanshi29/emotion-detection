"""Chat service: persistence + LLM orchestration + safety routing (plan §13)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import (
    Conversation,
    Message,
    RiskAssessment,
    SafetyEvent,
)
from app.services.ai.llm import ChatMessage, LLMProviderError, LLMResponse
from app.services.ai.llm.router import LLMRouter
from app.services.ai.system_prompts import (
    SAFE_HIGH_RISK_REPLY,
    SAFE_UNSAFE_OUTPUT_REPLY,
    WELLNESS_SYSTEM_PROMPT,
)
from app.services.safety import classify, scan_output

# How many prior turns (user+assistant combined) to include as context.
HISTORY_TURNS = 12


@dataclass
class SendResult:
    conversation: Conversation
    user_message: Message
    assistant_message: Message
    risk_level: str


async def get_or_create_conversation(
    db: AsyncSession, *, user_id: str, conversation_id: Optional[str]
) -> Conversation:
    if conversation_id:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        conv = (await db.execute(stmt)).scalar_one_or_none()
        if conv is None:
            raise LookupError("conversation not found")
        return conv

    conv = Conversation(user_id=user_id, title=None)
    db.add(conv)
    await db.flush()
    return conv


async def _load_recent_messages(
    db: AsyncSession, *, conversation_id: str, limit: int
) -> List[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(reversed(rows))


def _build_prompt(
    history: List[Message],
    user_content: str,
    memory_context: str = "",
) -> List[ChatMessage]:
    system = WELLNESS_SYSTEM_PROMPT
    if memory_context:
        system = f"{system}\n\n{memory_context}"
    msgs: List[ChatMessage] = [ChatMessage(role="system", content=system)]
    for m in history:
        if m.role in ("user", "assistant"):
            msgs.append(ChatMessage(role=m.role, content=m.content))
    msgs.append(ChatMessage(role="user", content=user_content))
    return msgs


def _derive_title(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return (t[:57] + "…") if len(t) > 60 else t


async def send_message(
    db: AsyncSession,
    router: LLMRouter,
    *,
    user_id: str,
    conversation_id: Optional[str],
    content: str,
    provider: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> SendResult:
    """Persist the user turn, classify risk, call LLM (or return safe reply),
    persist the assistant turn, and return everything."""

    # Strip control chars / bidi overrides / zero-width joiners before we
    # persist or classify, so log-scrapers and downstream reviewers see the
    # same text the safety classifier saw (§4.1).
    from app.services.ai.safety.prompt_guard import sanitize_user_text

    content = sanitize_user_text(content, max_len=8000)
    if not content:
        raise ValueError("empty message after sanitization")

    conv = await get_or_create_conversation(
        db, user_id=user_id, conversation_id=conversation_id
    )

    risk = classify(content)

    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=content,
        risk_level=risk.level,
    )
    db.add(user_msg)
    await db.flush()

    if risk.level != "none":
        db.add(
            RiskAssessment(
                message_id=user_msg.id,
                level=risk.level,
                categories=risk.categories,
                rationale=risk.rationale,
            )
        )

    if risk.level == "high":
        # Skip the LLM entirely — safety copy is the response.
        db.add(
            SafetyEvent(
                user_id=user_id,
                conversation_id=conv.id,
                event_type="high_risk_safe_reply",
                payload={
                    "categories": risk.categories,
                    "user_message_id": user_msg.id,
                },
            )
        )
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=SAFE_HIGH_RISK_REPLY,
            provider="safety",
            model="rules-v1",
            risk_level="high",
        )
        db.add(assistant_msg)
    else:
        # Load prior turns (excluding the message we just added) for context.
        prior = await _load_recent_messages(
            db, conversation_id=conv.id, limit=HISTORY_TURNS + 1
        )
        prior = [m for m in prior if m.id != user_msg.id]

        # Retrieve relevant memories (respects UserPreferences.memory_enabled;
        # returns [] silently when memory is off).
        memory_context = ""
        try:
            from app.services import memory_service
            from app.services.ai.safety.prompt_guard import wrap_untrusted_context

            hits = await memory_service.retrieve(
                db, user_id=user_id, query=content, k=3
            )
            if hits:
                lines = []
                for h in hits:
                    m = h["memory"]
                    lines.append(f"- ({m.kind}) {m.title}: {m.content}")
                memory_context = wrap_untrusted_context(
                    "Relevant user memories:\n" + "\n".join(lines),
                    label="memory",
                )
        except Exception:  # noqa: BLE001
            # Memory is best-effort; never fail the chat turn.
            memory_context = ""

        prompt = _build_prompt(
            prior[-HISTORY_TURNS:], content, memory_context=memory_context
        )

        # Persist the user turn and release the NullPool connection before the
        # potentially slow provider call. Holding a Neon connection idle for
        # tens of seconds makes it vulnerable to server-side idle disconnects
        # and needlessly consumes a database connection.
        await db.commit()

        try:
            llm: LLMResponse = await router.complete(
                prompt,
                preferred=provider,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            unsafe = scan_output(llm.text)
            if unsafe.detected:
                db.add(
                    SafetyEvent(
                        user_id=user_id,
                        conversation_id=conv.id,
                        event_type="unsafe_output_rewritten",
                        payload={
                            "categories": unsafe.categories,
                            "provider": llm.provider,
                            "model": llm.model,
                            "original_preview": llm.text[:200],
                        },
                    )
                )
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=SAFE_UNSAFE_OUTPUT_REPLY,
                    provider="safety",
                    model="output-guard-v1",
                )
            else:
                assistant_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=llm.text,
                    provider=llm.provider,
                    model=llm.model,
                    prompt_tokens=llm.prompt_tokens,
                    completion_tokens=llm.completion_tokens,
                )
        except LLMProviderError:
            assistant_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content=(
                    "I'm having trouble reaching my language model right now. "
                    "Can you try again in a moment? If it keeps happening, "
                    "reaching out to a friend or a professional is always a good option."
                ),
                provider="fallback",
                model="static",
            )
        db.add(assistant_msg)

    if not conv.title:
        conv.title = _derive_title(content)

    await db.commit()
    await db.refresh(conv)
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return SendResult(
        conversation=conv,
        user_message=user_msg,
        assistant_message=assistant_msg,
        risk_level=risk.level,
    )


async def list_conversations(
    db: AsyncSession, *, user_id: str, include_archived: bool = False
) -> List[Conversation]:
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if not include_archived:
        stmt = stmt.where(Conversation.archived.is_(False))
    stmt = stmt.order_by(desc(Conversation.updated_at))
    return list((await db.execute(stmt)).scalars().all())


async def get_conversation(
    db: AsyncSession, *, user_id: str, conversation_id: str
) -> Optional[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .options(selectinload(Conversation.messages))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_conversation(
    db: AsyncSession,
    *,
    user_id: str,
    conversation_id: str,
    title: Optional[str] = None,
    archived: Optional[bool] = None,
) -> Optional[Conversation]:
    conv = await get_conversation(
        db, user_id=user_id, conversation_id=conversation_id
    )
    if conv is None:
        return None
    if title is not None:
        conv.title = title
    if archived is not None:
        conv.archived = archived
    await db.commit()
    await db.refresh(conv)
    return conv


async def delete_conversation(
    db: AsyncSession, *, user_id: str, conversation_id: str
) -> bool:
    conv = await get_conversation(
        db, user_id=user_id, conversation_id=conversation_id
    )
    if conv is None:
        return False
    await db.delete(conv)
    await db.commit()
    return True
