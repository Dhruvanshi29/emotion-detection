"""Reminders + Notifications API (plan §10)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.reminder import (
    NotificationList,
    NotificationRead,
    NotificationStatusUpdate,
    ReminderCreate,
    ReminderList,
    ReminderRead,
    ReminderUpdate,
)
from app.services import reminders_service

router = APIRouter(tags=["reminders"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/reminders", response_model=ReminderList)
async def list_reminders(
    user: CurrentUser,
    db: DbDep,
    active_only: bool = Query(False),
) -> ReminderList:
    rows = await reminders_service.list_reminders(
        db, user_id=user.id, active_only=active_only
    )
    return ReminderList(
        items=[ReminderRead.model_validate(r) for r in rows], total=len(rows)
    )


@router.post(
    "/reminders", response_model=ReminderRead, status_code=status.HTTP_201_CREATED
)
async def create_reminder(
    payload: ReminderCreate, user: CurrentUser, db: DbDep
) -> ReminderRead:
    r = await reminders_service.create_reminder(db, user_id=user.id, payload=payload)
    return ReminderRead.model_validate(r)


@router.get("/reminders/{reminder_id}", response_model=ReminderRead)
async def get_reminder(
    reminder_id: str, user: CurrentUser, db: DbDep
) -> ReminderRead:
    r = await reminders_service.get_reminder(
        db, user_id=user.id, reminder_id=reminder_id
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return ReminderRead.model_validate(r)


@router.patch("/reminders/{reminder_id}", response_model=ReminderRead)
async def update_reminder(
    reminder_id: str,
    patch: ReminderUpdate,
    user: CurrentUser,
    db: DbDep,
) -> ReminderRead:
    r = await reminders_service.get_reminder(
        db, user_id=user.id, reminder_id=reminder_id
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    try:
        r = await reminders_service.update_reminder(db, reminder=r, patch=patch)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid reminder schedule",
        ) from exc
    return ReminderRead.model_validate(r)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: str, user: CurrentUser, db: DbDep
) -> None:
    r = await reminders_service.get_reminder(
        db, user_id=user.id, reminder_id=reminder_id
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await reminders_service.delete_reminder(db, reminder=r)


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(
    user: CurrentUser,
    db: DbDep,
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> NotificationList:
    items, total, unread = await reminders_service.list_notifications(
        db, user_id=user.id, unread_only=unread_only, skip=skip, limit=limit
    )
    return NotificationList(
        items=[NotificationRead.model_validate(n) for n in items],
        total=total,
        unread=unread,
    )


@router.post(
    "/notifications/{notification_id}/read", response_model=NotificationRead
)
async def mark_notification_read(
    notification_id: str, user: CurrentUser, db: DbDep
) -> NotificationRead:
    n = await reminders_service.get_notification(
        db, user_id=user.id, notification_id=notification_id
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    n = await reminders_service.mark_notification(db, notification=n, status="read")
    return NotificationRead.model_validate(n)


@router.patch("/notifications/{notification_id}", response_model=NotificationRead)
async def update_notification_status(
    notification_id: str,
    payload: NotificationStatusUpdate,
    user: CurrentUser,
    db: DbDep,
) -> NotificationRead:
    n = await reminders_service.get_notification(
        db, user_id=user.id, notification_id=notification_id
    )
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    n = await reminders_service.mark_notification(
        db, notification=n, status=payload.status
    )
    return NotificationRead.model_validate(n)


@router.post("/reminders/dispatch")
async def dispatch_reminders(
    user: CurrentUser,
    db: DbDep,
    now: Optional[datetime] = Query(
        None,
        description="ISO-8601 UTC timestamp; dev/test only. If omitted, uses server clock.",
    ),
) -> dict:
    """Dev/test endpoint — synchronously drains the queue.

    The user parameter enforces auth (so no unauthenticated tick) but the
    dispatcher operates over ALL users' reminders — this endpoint is intended
    for the in-process worker path and local testing only.
    """
    # This endpoint operates across all accounts and exists only to make local
    # development and deterministic tests convenient. The worker is the sole
    # production dispatcher.
    if get_settings().is_production:
        raise HTTPException(status_code=404, detail="Not found")
    created = await reminders_service.dispatch_due(db, now_utc=now)
    return {"created": created, "actor": user.id}
