"""Memory + summary API (plan §10, Phase 11)."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.schemas.memory import (
    BulkDeleteResult,
    ConversationSummaryRead,
    MemoryCreate,
    MemoryExtractRequest,
    MemoryExtractResult,
    MemoryList,
    MemoryRead,
    MemorySearchHit,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpdate,
)
from app.services import memory_service

router = APIRouter(prefix="/memory", tags=["memory"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=MemoryList)
async def list_memory(
    user: CurrentUser,
    db: DbDep,
    kind: Optional[str] = Query(None),
    pinned: Optional[bool] = Query(None),
) -> MemoryList:
    rows = await memory_service.list_memories(
        db, user_id=user.id, kind=kind, pinned=pinned
    )
    return MemoryList(
        items=[MemoryRead.model_validate(r) for r in rows], total=len(rows)
    )


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate, user: CurrentUser, db: DbDep
) -> MemoryRead:
    try:
        row = await memory_service.create_memory(db, user_id=user.id, payload=payload)
    except memory_service.MemoryDisabledError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI memory is disabled in your preferences.",
        )
    return MemoryRead.model_validate(row)


@router.delete("", response_model=BulkDeleteResult)
async def delete_all_memory(user: CurrentUser, db: DbDep) -> BulkDeleteResult:
    n = await memory_service.delete_all_memories(db, user_id=user.id)
    return BulkDeleteResult(deleted=n)


@router.post("/search", response_model=MemorySearchResult)
async def search_memory(
    payload: MemorySearchRequest, user: CurrentUser, db: DbDep
) -> MemorySearchResult:
    hits = await memory_service.retrieve(
        db,
        user_id=user.id,
        query=payload.query,
        k=payload.k,
        kinds=payload.kinds,
    )
    return MemorySearchResult(
        query=payload.query,
        hits=[
            MemorySearchHit(
                memory=MemoryRead.model_validate(h["memory"]),
                score=h["score"],
                reasons=h["reasons"],
            )
            for h in hits
        ],
    )


@router.post("/extract", response_model=MemoryExtractResult)
async def extract_memory(
    payload: MemoryExtractRequest, user: CurrentUser
) -> MemoryExtractResult:
    _ = user  # auth-only
    candidates = memory_service.extract_candidates(payload.text)
    return MemoryExtractResult(candidates=candidates)


@router.get(
    "/summaries/{conversation_id}", response_model=ConversationSummaryRead
)
async def get_summary(
    conversation_id: str, user: CurrentUser, db: DbDep
) -> ConversationSummaryRead:
    row = await memory_service.get_summary(
        db, user_id=user.id, conversation_id=conversation_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return ConversationSummaryRead.model_validate(row)


@router.post(
    "/summaries/{conversation_id}", response_model=ConversationSummaryRead
)
async def summarize(
    conversation_id: str, user: CurrentUser, db: DbDep
) -> ConversationSummaryRead:
    try:
        row = await memory_service.summarize_conversation(
            db, user_id=user.id, conversation_id=conversation_id
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationSummaryRead.model_validate(row)


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(memory_id: str, user: CurrentUser, db: DbDep) -> MemoryRead:
    row = await memory_service.get_memory(
        db, user_id=user.id, memory_id=memory_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return MemoryRead.model_validate(row)


@router.patch("/{memory_id}", response_model=MemoryRead)
async def patch_memory(
    memory_id: str, patch: MemoryUpdate, user: CurrentUser, db: DbDep
) -> MemoryRead:
    row = await memory_service.get_memory(
        db, user_id=user.id, memory_id=memory_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    row = await memory_service.update_memory(db, memory=row, patch=patch)
    return MemoryRead.model_validate(row)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(
    memory_id: str, user: CurrentUser, db: DbDep
) -> None:
    row = await memory_service.get_memory(
        db, user_id=user.id, memory_id=memory_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    await memory_service.delete_memory(db, memory=row)
