"""Reminders + notifications (Phase 9)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services import reminders_service
from app.services.reminders_service import compute_next_fire


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "R"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Pure scheduling logic
# --------------------------------------------------------------------------- #


def test_compute_next_fire_daily_same_day():
    # 2026-01-05 is Monday. From 08:00 UTC / 09:00 Berlin, next 09:30 Berlin is
    # today at 08:30 UTC.
    from_utc = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
    nxt = compute_next_fire(
        recurrence="daily",
        weekdays=None,
        time_of_day="09:30",
        tz_name="Europe/Berlin",
        start_date=None,
        end_date=None,
        from_utc=from_utc,
    )
    assert nxt == datetime(2026, 1, 5, 8, 30, tzinfo=timezone.utc)


def test_compute_next_fire_daily_rolls_to_next_day():
    # 10:00 UTC already past 09:30 Berlin (08:30 UTC), so tomorrow.
    from_utc = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    nxt = compute_next_fire(
        recurrence="daily",
        weekdays=None,
        time_of_day="09:30",
        tz_name="Europe/Berlin",
        start_date=None,
        end_date=None,
        from_utc=from_utc,
    )
    assert nxt == datetime(2026, 1, 6, 8, 30, tzinfo=timezone.utc)


def test_compute_next_fire_weekly_wraps_across_week():
    # Wed 2026-01-07 15:00 UTC; schedule fires Mon/Fri at 09:00 America/New_York.
    from_utc = datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)
    nxt = compute_next_fire(
        recurrence="weekly",
        weekdays=[0, 4],  # Mon, Fri
        time_of_day="09:00",
        tz_name="America/New_York",
        start_date=None,
        end_date=None,
        from_utc=from_utc,
    )
    # Next occurrence is Fri 2026-01-09 09:00 New York = 14:00 UTC.
    assert nxt == datetime(2026, 1, 9, 14, 0, tzinfo=timezone.utc)


def test_compute_next_fire_once_returns_none_after_fire():
    from_utc = datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc)
    once = compute_next_fire(
        recurrence="once",
        weekdays=None,
        time_of_day="10:00",
        tz_name="UTC",
        start_date=date(2026, 3, 15),
        end_date=None,
        from_utc=from_utc,
    )
    assert once == datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

    already_fired = compute_next_fire(
        recurrence="once",
        weekdays=None,
        time_of_day="10:00",
        tz_name="UTC",
        start_date=date(2026, 3, 15),
        end_date=None,
        from_utc=from_utc,
        last_fired_at=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
    )
    assert already_fired is None


def test_compute_next_fire_respects_end_date():
    from_utc = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    nxt = compute_next_fire(
        recurrence="daily",
        weekdays=None,
        time_of_day="08:00",
        tz_name="UTC",
        start_date=None,
        end_date=date(2026, 5, 31),
        from_utc=from_utc,
    )
    assert nxt is None


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_requires_auth(client):
    r = await client.get("/reminders")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_crud_flow(client):
    h = await _register(client, "r-crud@example.com")

    r = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "Morning check-in",
            "message": "How are you feeling today?",
            "kind": "chat_checkin",
            "recurrence": "daily",
            "time_of_day": "09:00",
            "timezone": "America/New_York",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rid = body["id"]
    assert body["title"] == "Morning check-in"
    assert body["kind"] == "chat_checkin"
    assert body["next_fire_at"] is not None
    assert body["is_active"] is True

    got = await client.get(f"/reminders/{rid}", headers=h)
    assert got.status_code == 200
    assert got.json()["id"] == rid

    patched = await client.patch(
        f"/reminders/{rid}",
        headers=h,
        json={"time_of_day": "18:00", "recurrence": "weekly", "weekdays": [0, 2, 4]},
    )
    assert patched.status_code == 200
    assert patched.json()["recurrence"] == "weekly"
    assert patched.json()["weekdays"] == [0, 2, 4]

    lst = await client.get("/reminders", headers=h)
    assert lst.status_code == 200
    assert lst.json()["total"] == 1

    dele = await client.delete(f"/reminders/{rid}", headers=h)
    assert dele.status_code == 204

    lst2 = await client.get("/reminders", headers=h)
    assert lst2.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_validation_errors(client):
    h = await _register(client, "r-valid@example.com")
    # weekly without weekdays
    bad = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "x",
            "recurrence": "weekly",
            "time_of_day": "09:00",
            "timezone": "UTC",
        },
    )
    assert bad.status_code == 422

    # invalid time
    bad2 = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "x",
            "recurrence": "daily",
            "time_of_day": "25:00",
            "timezone": "UTC",
        },
    )
    assert bad2.status_code == 422

    # unknown timezone
    bad3 = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "x",
            "recurrence": "daily",
            "time_of_day": "09:00",
            "timezone": "Atlantis/Poseidonia",
        },
    )
    assert bad3.status_code == 422

    # once with no start_date
    bad4 = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "x",
            "recurrence": "once",
            "time_of_day": "09:00",
            "timezone": "UTC",
        },
    )
    assert bad4.status_code == 422


@pytest.mark.asyncio
async def test_patch_validates_effective_schedule(client):
    h = await _register(client, "r-patch-valid@example.com")
    created = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "daily",
            "recurrence": "daily",
            "time_of_day": "09:00",
            "timezone": "UTC",
        },
    )
    rid = created.json()["id"]
    bad = await client.patch(
        f"/reminders/{rid}", headers=h, json={"recurrence": "weekly"}
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_dispatch_endpoint_hidden_in_production(client, monkeypatch):
    h = await _register(client, "r-prod-dispatch@example.com")
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "app_env", "production")
    r = await client.post("/reminders/dispatch", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_dispatch_fires_and_creates_notification(client, test_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    h = await _register(client, "r-dispatch@example.com")
    # A daily 09:00 UTC reminder — set next_fire_at way back so dispatch triggers.
    r = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "Water break",
            "message": "Sip some water.",
            "kind": "hydration",
            "recurrence": "daily",
            "time_of_day": "09:00",
            "timezone": "UTC",
        },
    )
    assert r.status_code == 201
    rid = r.json()["id"]

    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as db:
        created = await reminders_service.dispatch_due(
            db, now_utc=datetime(2099, 1, 1, tzinfo=timezone.utc)
        )
    assert created >= 1

    lst = await client.get("/notifications", headers=h)
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] >= 1
    assert body["unread"] >= 1
    n = body["items"][0]
    assert n["title"] == "Water break"
    assert n["kind"] == "hydration"
    assert n["reminder_id"] == rid
    assert n["read_at"] is None

    # Second dispatch at the same "now" should not double-fire because
    # next_fire_at was advanced past that moment.
    async with SessionLocal() as db:
        again = await reminders_service.dispatch_due(
            db, now_utc=datetime(2099, 1, 1, 0, 30, tzinfo=timezone.utc)
        )
    assert again == 0


@pytest.mark.asyncio
async def test_dispatch_marks_once_reminder_inactive(client, test_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    h = await _register(client, "r-once@example.com")
    r = await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "One-time nudge",
            "recurrence": "once",
            "time_of_day": "09:00",
            "timezone": "UTC",
            "start_date": "2030-01-01",
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as db:
        created = await reminders_service.dispatch_due(
            db, now_utc=datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
        )
    assert created == 1

    got = await client.get(f"/reminders/{rid}", headers=h)
    assert got.status_code == 200
    body = got.json()
    assert body["is_active"] is False
    assert body["next_fire_at"] is None
    assert body["fire_count"] == 1


@pytest.mark.asyncio
async def test_mark_notification_read(client, test_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    h = await _register(client, "r-read@example.com")
    await client.post(
        "/reminders",
        headers=h,
        json={
            "title": "Stretch",
            "recurrence": "daily",
            "time_of_day": "07:00",
            "timezone": "UTC",
        },
    )
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as db:
        await reminders_service.dispatch_due(
            db, now_utc=datetime(2099, 1, 1, tzinfo=timezone.utc)
        )

    lst = await client.get("/notifications", headers=h)
    nid = lst.json()["items"][0]["id"]

    read = await client.post(f"/notifications/{nid}/read", headers=h)
    assert read.status_code == 200
    assert read.json()["status"] == "read"
    assert read.json()["read_at"] is not None

    after = await client.get("/notifications?unread_only=true", headers=h)
    assert after.status_code == 200
    assert all(n["id"] != nid for n in after.json()["items"])


@pytest.mark.asyncio
async def test_reminder_isolation_between_users(client, test_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    h1 = await _register(client, "r-iso-a@example.com")
    h2 = await _register(client, "r-iso-b@example.com")

    r1 = await client.post(
        "/reminders",
        headers=h1,
        json={
            "title": "Only mine",
            "recurrence": "daily",
            "time_of_day": "08:00",
            "timezone": "UTC",
        },
    )
    rid = r1.json()["id"]

    forbidden = await client.get(f"/reminders/{rid}", headers=h2)
    assert forbidden.status_code == 404

    # Even after dispatch, user B sees no notifications.
    SessionLocal = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with SessionLocal() as db:
        await reminders_service.dispatch_due(
            db, now_utc=datetime(2099, 1, 1, tzinfo=timezone.utc)
        )

    b_notifs = await client.get("/notifications", headers=h2)
    assert b_notifs.json()["total"] == 0
