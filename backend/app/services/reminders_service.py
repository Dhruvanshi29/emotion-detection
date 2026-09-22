"""Reminder scheduler + dispatcher (Phase 9).

`compute_next_fire` is a pure function so tests can pin `from_utc` and assert
exact fire times across DST boundaries.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reminder import Notification, Reminder
from app.models.user import User, UserPreferences
from app.schemas.reminder import ReminderCreate, ReminderUpdate
from app.services import email_service, push_service
from app.models.push_subscription import PushSubscription


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def compute_next_fire(
    *,
    recurrence: str,
    weekdays: Optional[List[int]],
    time_of_day: str,
    tz_name: str,
    start_date: Optional[date],
    end_date: Optional[date],
    from_utc: datetime,
    last_fired_at: Optional[datetime] = None,
) -> Optional[datetime]:
    """Return the next UTC datetime at which this schedule should fire.

    `from_utc` is the "as of" moment; results are always strictly greater than
    it (so a reminder that just fired at exactly `from_utc` moves forward).
    Returns `None` if the reminder has no future fires (e.g., a `once` that
    already fired or an `end_date` in the past).
    """
    if from_utc.tzinfo is None:
        from_utc = from_utc.replace(tzinfo=timezone.utc)
    tz = _tz(tz_name)
    tod = _parse_hhmm(time_of_day)
    local_now = from_utc.astimezone(tz)

    if recurrence == "once":
        if start_date is None:
            return None
        if last_fired_at is not None:
            return None
        local_dt = datetime.combine(start_date, tod, tzinfo=tz)
        if local_dt <= local_now:
            return None
        if end_date is not None and start_date > end_date:
            return None
        return local_dt.astimezone(timezone.utc)

    # daily / weekly share the same walk-forward loop.
    valid_weekdays: List[int]
    if recurrence == "daily":
        valid_weekdays = list(range(7))
    elif recurrence == "weekly":
        valid_weekdays = sorted({int(x) for x in (weekdays or [])})
        if not valid_weekdays:
            return None
    else:
        return None

    scan_date = local_now.date()
    if start_date is not None and scan_date < start_date:
        scan_date = start_date

    # Same-day candidate first, then walk forward up to two weeks.
    for _ in range(15):
        if end_date is not None and scan_date > end_date:
            return None
        if scan_date.weekday() in valid_weekdays:
            local_dt = datetime.combine(scan_date, tod, tzinfo=tz)
            if local_dt > local_now:
                return local_dt.astimezone(timezone.utc)
        scan_date = scan_date + timedelta(days=1)
    return None


async def _apply_next_fire(reminder: Reminder, *, from_utc: datetime) -> None:
    reminder.next_fire_at = compute_next_fire(
        recurrence=reminder.recurrence,
        weekdays=reminder.weekdays,
        time_of_day=reminder.time_of_day,
        tz_name=reminder.timezone,
        start_date=reminder.start_date,
        end_date=reminder.end_date,
        from_utc=from_utc,
        last_fired_at=reminder.last_fired_at,
    )
    if reminder.next_fire_at is None and reminder.recurrence == "once":
        reminder.is_active = False


async def create_reminder(
    db: AsyncSession, *, user_id: str, payload: ReminderCreate
) -> Reminder:
    r = Reminder(
        user_id=user_id,
        title=payload.title,
        message=payload.message,
        kind=payload.kind,
        recurrence=payload.recurrence,
        weekdays=payload.weekdays,
        time_of_day=payload.time_of_day,
        timezone=payload.timezone,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=payload.is_active,
    )
    await _apply_next_fire(r, from_utc=datetime.now(timezone.utc))
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def get_reminder(
    db: AsyncSession, *, user_id: str, reminder_id: str
) -> Optional[Reminder]:
    q = select(Reminder).where(
        Reminder.id == reminder_id, Reminder.user_id == user_id
    )
    return (await db.execute(q)).scalar_one_or_none()


async def list_reminders(
    db: AsyncSession, *, user_id: str, active_only: bool = False
) -> List[Reminder]:
    q = select(Reminder).where(Reminder.user_id == user_id)
    if active_only:
        q = q.where(Reminder.is_active.is_(True))
    q = q.order_by(Reminder.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def update_reminder(
    db: AsyncSession,
    *,
    reminder: Reminder,
    patch: ReminderUpdate,
) -> Reminder:
    data = patch.model_dump(exclude_unset=True)
    # Validate the effective schedule, not just the partial patch. Without
    # this, changing a daily reminder to weekly without weekdays (or to once
    # without a start date) silently creates a reminder that can never fire.
    effective = ReminderCreate.model_validate(
        {
            "title": reminder.title,
            "message": reminder.message,
            "kind": reminder.kind,
            "recurrence": reminder.recurrence,
            "weekdays": reminder.weekdays,
            "time_of_day": reminder.time_of_day,
            "timezone": reminder.timezone,
            "start_date": reminder.start_date,
            "end_date": reminder.end_date,
            "is_active": reminder.is_active,
            **data,
        }
    )
    validated = effective.model_dump()
    schedule_changed = False
    for k, v in data.items():
        v = validated[k]
        if k in {
            "recurrence",
            "weekdays",
            "time_of_day",
            "timezone",
            "start_date",
            "end_date",
            "is_active",
        } and getattr(reminder, k) != v:
            schedule_changed = True
        setattr(reminder, k, v)
    if schedule_changed:
        if reminder.is_active:
            await _apply_next_fire(reminder, from_utc=datetime.now(timezone.utc))
        else:
            reminder.next_fire_at = None
    await db.commit()
    await db.refresh(reminder)
    return reminder


async def delete_reminder(db: AsyncSession, *, reminder: Reminder) -> None:
    await db.delete(reminder)
    await db.commit()


async def dispatch_due(
    db: AsyncSession, *, now_utc: Optional[datetime] = None, limit: int = 100
) -> int:
    """Fire all reminders whose next_fire_at <= now.

    Returns the number of notifications created. Safe to call repeatedly; each
    reminder advances its own `next_fire_at` so the same fire won't repeat.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    q = (
        select(Reminder)
        .where(Reminder.is_active.is_(True), Reminder.next_fire_at.is_not(None))
        .where(Reminder.next_fire_at <= now)
        .order_by(Reminder.next_fire_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list((await db.execute(q)).scalars().all())
    created = 0
    for r in rows:
        scheduled = r.next_fire_at or now
        notif = Notification(
            user_id=r.user_id,
            reminder_id=r.id,
            kind=r.kind,
            channel="in_app",
            title=r.title,
            body=r.message,
            status="delivered",
            scheduled_for=scheduled,
            delivered_at=now,
        )
        db.add(notif)
        if email_service.configured():
            prefs = (
                await db.execute(
                    select(UserPreferences).where(UserPreferences.user_id == r.user_id)
                )
            ).scalar_one_or_none()
            if prefs is not None and prefs.notification_email:
                db.add(
                    Notification(
                        user_id=r.user_id,
                        reminder_id=r.id,
                        kind=r.kind,
                        channel="email",
                        title=r.title,
                        body=r.message,
                        status="scheduled",
                        scheduled_for=scheduled,
                    )
                )
        if push_service.configured():
            has_push = (
                await db.execute(
                    select(PushSubscription.id)
                    .where(PushSubscription.user_id == r.user_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if has_push is not None:
                db.add(
                    Notification(
                        user_id=r.user_id,
                        reminder_id=r.id,
                        kind=r.kind,
                        channel="push",
                        title=r.title,
                        body=r.message,
                        status="scheduled",
                        scheduled_for=scheduled,
                    )
                )
        r.last_fired_at = now
        r.fire_count = (r.fire_count or 0) + 1
        await _apply_next_fire(r, from_utc=now)
        created += 1
    if created:
        await db.commit()
    return created


async def deliver_pending_email_notifications(
    db: AsyncSession, *, limit: int = 50
) -> int:
    """Deliver queued reminder emails with bounded retries."""
    if not email_service.configured():
        return 0
    rows = list(
        (
            await db.execute(
                select(Notification, User.email)
                .join(User, User.id == Notification.user_id)
                .where(
                    Notification.channel == "email",
                    Notification.status.in_(("scheduled", "failed")),
                    Notification.delivery_attempts < 3,
                )
                .order_by(Notification.created_at.asc())
                .limit(limit)
            )
        ).all()
    )
    delivered = 0
    for notification, email in rows:
        notification.delivery_attempts += 1
        notification.last_attempt_at = datetime.now(timezone.utc)
        ok = await email_service.send_email(
            to=email,
            subject=f"Saaya reminder: {notification.title}",
            text=notification.body or notification.title,
        )
        notification.status = "delivered" if ok else "failed"
        if ok:
            notification.delivered_at = datetime.now(timezone.utc)
            delivered += 1
    if rows:
        await db.commit()
    return delivered


async def deliver_pending_push_notifications(db: AsyncSession, *, limit: int = 50) -> int:
    """Deliver durable Web Push outbox rows with bounded retries."""
    if not push_service.configured():
        return 0
    rows = list(
        (
            await db.execute(
                select(Notification)
                .where(
                    Notification.channel == "push",
                    Notification.status.in_(("scheduled", "failed")),
                    Notification.delivery_attempts < 3,
                )
                .order_by(Notification.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
    )
    delivered = 0
    for notification in rows:
        notification.delivery_attempts += 1
        notification.last_attempt_at = datetime.now(timezone.utc)
        ok = await push_service.send_user(
            db,
            user_id=notification.user_id,
            title=notification.title,
            body=notification.body or notification.title,
        )
        notification.status = "delivered" if ok else "failed"
        if ok:
            notification.delivered_at = datetime.now(timezone.utc)
            delivered += 1
    if rows:
        await db.commit()
    return delivered


async def list_notifications(
    db: AsyncSession,
    *,
    user_id: str,
    unread_only: bool = False,
    limit: int = 50,
    skip: int = 0,
) -> Tuple[List[Notification], int, int]:
    # Email delivery rows are an internal durable outbox. Only in-app rows
    # belong in the user's notification centre and unread badge.
    base = select(Notification).where(
        Notification.user_id == user_id, Notification.channel == "in_app"
    )
    if unread_only:
        base = base.where(Notification.read_at.is_(None))
    total = (
        await db.execute(
            select(func.count()).select_from(base.subquery())
        )
    ).scalar_one()
    unread_q = select(func.count()).select_from(
        select(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.channel == "in_app",
            Notification.read_at.is_(None),
        )
        .subquery()
    )
    unread = (await db.execute(unread_q)).scalar_one()
    q = (
        base.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    )
    items = list((await db.execute(q)).scalars().all())
    return items, int(total), int(unread)


async def get_notification(
    db: AsyncSession, *, user_id: str, notification_id: str
) -> Optional[Notification]:
    q = select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user_id
    )
    return (await db.execute(q)).scalar_one_or_none()


async def mark_notification(
    db: AsyncSession, *, notification: Notification, status: str
) -> Notification:
    notification.status = status
    if status == "read" and notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notification)
    return notification


__all__ = [
    "compute_next_fire",
    "create_reminder",
    "get_reminder",
    "list_reminders",
    "update_reminder",
    "delete_reminder",
    "dispatch_due",
    "deliver_pending_email_notifications",
    "deliver_pending_push_notifications",
    "list_notifications",
    "get_notification",
    "mark_notification",
]
