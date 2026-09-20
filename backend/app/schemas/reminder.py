"""Reminder + notification schemas (Phase 9)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.reminder import (
    NOTIFICATION_STATUSES,
    RECURRENCE_KINDS,
    REMINDER_KINDS,
)

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _validate_time(v: str) -> str:
    if not _TIME_RE.match(v):
        raise ValueError("time_of_day must be HH:MM 24h")
    return v


def _validate_weekdays(v: Optional[List[int]]) -> Optional[List[int]]:
    if v is None:
        return None
    if not v:
        raise ValueError("weekdays must contain at least one day")
    out = sorted({int(x) for x in v})
    for d in out:
        if d < 0 or d > 6:
            raise ValueError("weekdays entries must be 0..6")
    return out


class ReminderBase(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: Optional[str] = Field(default=None, max_length=2000)
    kind: str = "custom"
    recurrence: str = "daily"
    weekdays: Optional[List[int]] = None
    time_of_day: str
    timezone: str = Field(default="UTC", max_length=64)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in REMINDER_KINDS:
            raise ValueError(f"kind must be one of {REMINDER_KINDS}")
        return v

    @field_validator("recurrence")
    @classmethod
    def _rec(cls, v: str) -> str:
        if v not in RECURRENCE_KINDS:
            raise ValueError(f"recurrence must be one of {RECURRENCE_KINDS}")
        return v

    @field_validator("time_of_day")
    @classmethod
    def _tod(cls, v: str) -> str:
        return _validate_time(v)

    @field_validator("weekdays")
    @classmethod
    def _wd(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        return _validate_weekdays(v)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {v}") from exc
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "ReminderBase":
        if self.recurrence == "weekly" and not self.weekdays:
            raise ValueError("weekly recurrence requires at least one weekday")
        if self.recurrence == "once" and self.start_date is None:
            raise ValueError("once recurrence requires start_date")
        if (
            self.end_date is not None
            and self.start_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date cannot be before start_date")
        return self


class ReminderCreate(ReminderBase):
    is_active: bool = True


class ReminderUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    message: Optional[str] = Field(default=None, max_length=2000)
    kind: Optional[str] = None
    recurrence: Optional[str] = None
    weekdays: Optional[List[int]] = None
    time_of_day: Optional[str] = None
    timezone: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in REMINDER_KINDS:
            raise ValueError(f"kind must be one of {REMINDER_KINDS}")
        return v

    @field_validator("recurrence")
    @classmethod
    def _rec(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in RECURRENCE_KINDS:
            raise ValueError(f"recurrence must be one of {RECURRENCE_KINDS}")
        return v

    @field_validator("time_of_day")
    @classmethod
    def _tod(cls, v: Optional[str]) -> Optional[str]:
        return _validate_time(v) if v is not None else None

    @field_validator("weekdays")
    @classmethod
    def _wd(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        return _validate_weekdays(v)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {v}") from exc
        return v


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    message: Optional[str]
    kind: str
    recurrence: str
    weekdays: Optional[List[int]]
    time_of_day: str
    timezone: str
    start_date: Optional[date]
    end_date: Optional[date]
    is_active: bool
    next_fire_at: Optional[datetime]
    last_fired_at: Optional[datetime]
    fire_count: int
    created_at: datetime
    updated_at: datetime


class ReminderList(BaseModel):
    items: List[ReminderRead]
    total: int


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reminder_id: Optional[str]
    kind: str
    channel: str
    title: str
    body: Optional[str]
    status: str
    scheduled_for: datetime
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    created_at: datetime


class NotificationList(BaseModel):
    items: List[NotificationRead]
    total: int
    unread: int


class NotificationStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _s(cls, v: str) -> str:
        if v not in NOTIFICATION_STATUSES:
            raise ValueError(f"status must be one of {NOTIFICATION_STATUSES}")
        return v


__all__ = [
    "ReminderCreate",
    "ReminderUpdate",
    "ReminderRead",
    "ReminderList",
    "NotificationRead",
    "NotificationList",
    "NotificationStatusUpdate",
]
