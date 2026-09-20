from __future__ import annotations

from typing import Annotated, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import CurrentUser, EmotionAnalyzerDep, LLMRouterDep, rate_limit
from app.db import session as _session_mod
from app.db.session import get_db
from app.schemas.chat import (
    ChatRequest,
    ChatSendRequest,
    ChatSendResponse,
    ConversationRead,
    ConversationUpdate,
    ConversationWithMessages,
    MessageRead,
    ProvidersStatus,
)
from app.services import chat_service, emotion_service
from app.services.ai.llm import ChatMessage, LLMProviderError
from app.services.emotion import EmotionAnalyzer

router = APIRouter(prefix="/chat", tags=["chat"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _analyze_message_bg(
    analyzer: EmotionAnalyzer,
    *,
    user_id: str,
    message_id: str,
    text: str,
) -> None:
    """Run emotion analysis on a persisted user message in its own session."""
    import logging

    log = logging.getLogger(__name__)
    try:
        # LLM call FIRST, no DB connection held during it.
        result = await analyzer.analyze(text)
    except Exception as e:  # pragma: no cover
        log.warning("emotion bg: analyzer failed: %s", e)
        return

    try:
        async with _session_mod.SessionLocal() as db:
            await emotion_service.persist_result(
                db,
                user_id=user_id,
                text=text,
                source="chat",
                source_ref_id=message_id,
                result=result,
            )
    except Exception as e:  # pragma: no cover
        log.warning("emotion bg: persist failed: %s", e)


@router.get("/providers", response_model=ProvidersStatus)
def providers_status(llm: LLMRouterDep) -> ProvidersStatus:
    return ProvidersStatus(
        chain=llm._settings.provider_chain, available=llm.available_providers()
    )


@router.post("/message", response_model=ChatSendResponse)
async def chat_message(
    req: ChatSendRequest,
    user: CurrentUser,
    db: DbDep,
    llm: LLMRouterDep,
    analyzer: EmotionAnalyzerDep,
    background: BackgroundTasks,
    _rl: None = Depends(
        rate_limit(
            "chat_message",
            limit_setting="chat_rate_limit_per_minute",
            window_seconds=60.0,
        )
    ),
) -> ChatSendResponse:
    try:
        result = await chat_service.send_message(
            db,
            llm,
            user_id=user.id,
            conversation_id=req.conversation_id,
            content=req.content,
            provider=req.provider,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="conversation not found")

    background.add_task(
        _analyze_message_bg,
        analyzer,
        user_id=user.id,
        message_id=result.user_message.id,
        text=result.user_message.content,
    )

    a = result.assistant_message
    return ChatSendResponse(
        conversation_id=result.conversation.id,
        user_message_id=result.user_message.id,
        assistant_message_id=a.id,
        text=a.content,
        risk_level=result.risk_level,
        provider=a.provider,
        model=a.model,
        prompt_tokens=a.prompt_tokens,
        completion_tokens=a.completion_tokens,
    )


@router.get("/conversations", response_model=List[ConversationRead])
async def list_conversations(
    user: CurrentUser,
    db: DbDep,
    include_archived: bool = False,
) -> List[ConversationRead]:
    convs = await chat_service.list_conversations(
        db, user_id=user.id, include_archived=include_archived
    )
    return [ConversationRead.model_validate(c) for c in convs]


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationWithMessages
)
async def get_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: DbDep,
) -> ConversationWithMessages:
    conv = await chat_service.get_conversation(
        db, user_id=user.id, conversation_id=conversation_id
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ConversationWithMessages(
        id=conv.id,
        title=conv.title,
        archived=conv.archived,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[MessageRead.model_validate(m) for m in conv.messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
async def update_conversation(
    conversation_id: str,
    patch: ConversationUpdate,
    user: CurrentUser,
    db: DbDep,
) -> ConversationRead:
    conv = await chat_service.update_conversation(
        db,
        user_id=user.id,
        conversation_id=conversation_id,
        title=patch.title,
        archived=patch.archived,
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return ConversationRead.model_validate(conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: DbDep,
) -> None:
    ok = await chat_service.delete_conversation(
        db, user_id=user.id, conversation_id=conversation_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="conversation not found")


# Stateless streaming for early UI use; persistence-aware streaming will land
# alongside the SSE UI in a follow-up slice.
@router.post("/stream")
async def chat_stream(req: ChatRequest, llm: LLMRouterDep, _user: CurrentUser):
    async def event_source():
        try:
            async for delta in llm.stream(
                [ChatMessage(role=m.role, content=m.content) for m in req.messages],
                preferred=req.provider,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            ):
                yield {"event": "delta", "data": delta}
            yield {"event": "done", "data": ""}
        except LLMProviderError as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_source())
