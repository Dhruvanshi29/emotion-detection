"""Consent + privacy + audit endpoints (plan §12 §13)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db.session import get_db
from app.schemas.privacy import (
    AuditEventOut,
    AuditList,
    CategoryDeleteResult,
    ConsentEventOut,
    ConsentState,
    ConsentUpdate,
    DataExport,
    DeleteAccountRequest,
    DeleteAccountResult,
    PRIVACY_CATEGORIES,
)
from app.services import audit_service, consent_service, privacy_service

router = APIRouter(tags=["privacy"])


def _client_ip(request: Request) -> Optional[str]:
    if request.client is None:
        return None
    return request.client.host


def _user_agent(request: Request) -> Optional[str]:
    return request.headers.get("user-agent")


# ---------- Consent ----------


@router.get("/consent", response_model=ConsentState)
async def get_consent(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentState:
    prefs = user.preferences
    latest = await consent_service.latest_by_kind(db, user.id)
    hist = await consent_service.history(db, user.id, limit=100)
    return ConsentState(
        mic=bool(prefs and prefs.mic_consent),
        camera=bool(prefs and prefs.camera_consent),
        memory=bool(prefs and prefs.memory_enabled),
        data_processing=bool(
            latest.get("data_processing") and latest["data_processing"].granted
        ),
        terms=bool(latest.get("terms") and latest["terms"].granted),
        history=[ConsentEventOut.model_validate(h) for h in hist],
    )


@router.post(
    "/consent", response_model=ConsentEventOut, status_code=status.HTTP_201_CREATED
)
async def update_consent(
    payload: ConsentUpdate,
    user: CurrentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentEventOut:
    evt = await consent_service.set_consent(
        db,
        user_id=user.id,
        kind=payload.kind,
        granted=payload.granted,
        source=payload.source,
        notes=payload.notes,
    )
    await audit_service.log_event(
        user_id=user.id,
        category="consent",
        action=f"consent.{payload.kind}.{'granted' if payload.granted else 'revoked'}",
        details={"source": payload.source},
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return ConsentEventOut.model_validate(evt)


# ---------- Audit trail ----------


@router.get("/audit", response_model=AuditList)
async def list_audit(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
    category: Optional[str] = Query(default=None),
) -> AuditList:
    cats: Optional[List[str]] = [category] if category else None
    rows, total = await audit_service.list_for_user(
        db, user.id, limit=limit, categories=cats
    )
    return AuditList(
        items=[AuditEventOut.model_validate(r) for r in rows], total=total
    )


# ---------- Data export ----------


@router.get("/privacy/export", response_model=DataExport)
async def export_data(
    user: CurrentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataExport:
    dump = await privacy_service.export_user_data(db, user.id)
    await audit_service.log_event(
        user_id=user.id,
        category="privacy",
        action="data.exported",
        details={"counts": dump["counts"]},
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return DataExport(**dump)


# ---------- Category deletion ----------


@router.delete("/privacy/data/{category}", response_model=CategoryDeleteResult)
async def delete_data_category(
    category: str,
    user: CurrentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CategoryDeleteResult:
    if category not in PRIVACY_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"category must be one of {PRIVACY_CATEGORIES}",
        )
    deleted = await privacy_service.delete_category(db, user.id, category)
    await audit_service.log_event(
        user_id=user.id,
        category="privacy",
        action=f"data.deleted.{category}",
        details={"deleted": deleted},
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return CategoryDeleteResult(category=category, deleted=deleted)


# ---------- Account deletion ----------


@router.delete("/privacy/account", response_model=DeleteAccountResult)
async def delete_account(
    payload: DeleteAccountRequest,
    user: CurrentUser,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeleteAccountResult:
    uid = user.id
    # Log BEFORE deletion so the audit row survives via ON DELETE SET NULL.
    await audit_service.log_event(
        user_id=uid,
        category="account",
        action="account.deleted",
        details=None,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    try:
        counts = await privacy_service.delete_account(db, uid)
    except LookupError:
        raise HTTPException(status_code=404, detail="user_not_found")
    return DeleteAccountResult(
        user_id=uid,
        deleted_at=datetime.now(timezone.utc),
        counts=counts,
    )
