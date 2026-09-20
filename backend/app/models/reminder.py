"""Reminders + notifications (plan §9 Automation, §10 Reminders, Phase 9).

Design goals:
- Deterministic, timezone-aware recurrence rules that can be unit-tested with a
  frozen `now` — no live worker required for tests.
- Never store PII in the notification body beyond what the user typed into
  their own reminder title/message.
- The dispatcher advances `next_fire_at` atomically after inserting a matching
  Notification so a crash mid-flight can retry idempotently.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


REMINDER_KINDS = ("chat_checkin", "journal", "exercise", "hydration", "custom")
RECURRENCE_KINDS = ("once", "daily", "weekly")
NOTIFICATION_STATUSES = ("scheduled", "delivered", "read", "dismissed", "failed")
NOTIFICATION_CHANNELS = ("in_app",)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="custom")

    recurrence: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")
    # ISO weekdays (0=Mon..6=Sun); ignored unless recurrence == "weekly".
    weekdays: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # "HH:MM" 24h in `timezone`.
    time_of_day: Mapped[str] = mapped_column(String(5), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Precomputed for a cheap indexed query; recomputed after each dispatch.
    next_fire_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fire_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    reminder_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("reminders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="custom")
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="in_app")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="delivered")

    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


__all__ = [
    "REMINDER_KINDS",
    "RECURRENCE_KINDS",
    "NOTIFICATION_STATUSES",
    "NOTIFICATION_CHANNELS",
    "Reminder",
    "Notification",
]
