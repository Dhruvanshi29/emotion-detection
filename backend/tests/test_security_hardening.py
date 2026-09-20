"""Phase-15 security hardening regression suite.

Covers the highest-risk items from the post-Phase-14 audit:
 * Prompt-injection sanitizer (§4.1)
 * Log redaction (§6.2)
 * Request ID middleware
 * Body size limit middleware
 * Audio content-signature sniffing (§3.5)
 * Refresh-token rotation + reuse detection + family revocation (§3.1)
 * Password-change / logout-all pca invalidation (§3.1)
 * IP rate limiting on /auth (§3.1)
 * Change-password rejects same password
 * Unicode round-trips (RTL, NFKC, emoji)
 * DST reminder scheduling correctness
 * Duplicate reminder dispatch is idempotent
 * Broad IDOR sweep across resources

These tests are deliberately independent of each other and re-register users
with unique emails to avoid cross-test contamination.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.core.middleware import redact_sensitive
from app.services.ai.safety.prompt_guard import (
    sanitize_user_text,
    wrap_untrusted_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client, email: str, password: str = "wellness123"):
    r = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _auth(headers_tokens):
    return {"Authorization": f"Bearer {headers_tokens['access_token']}"}


# ---------------------------------------------------------------------------
# Prompt-injection sanitizer
# ---------------------------------------------------------------------------

def test_sanitize_strips_bidi_override():
    dirty = "hello\u202eevil\u202c"
    clean = sanitize_user_text(dirty)
    assert "\u202e" not in clean
    assert "\u202c" not in clean
    assert "hello" in clean and "evil" in clean


def test_sanitize_strips_zero_width_joiner_and_bom():
    dirty = "\ufeffhi\u200bthere\u200d!"
    clean = sanitize_user_text(dirty)
    for cp in ("\ufeff", "\u200b", "\u200d"):
        assert cp not in clean
    assert "hi" in clean and "there" in clean


def test_sanitize_nfkc_normalizes_fullwidth():
    # Fullwidth "ignore" often used to bypass naive keyword filters.
    dirty = "\uff49\uff47\uff4e\uff4f\uff52\uff45"  # ｉｇｎｏｒｅ
    clean = sanitize_user_text(dirty)
    assert clean == "ignore"


def test_sanitize_preserves_devanagari_and_arabic():
    text = "नमस्ते مرحبا שלום"
    clean = sanitize_user_text(text)
    assert clean == text


def test_sanitize_strips_c0_controls_but_keeps_newline_and_tab():
    dirty = "line1\n\tline2\x00\x07\x1f"
    clean = sanitize_user_text(dirty)
    assert "\n" in clean and "\t" in clean
    for cp in ("\x00", "\x07", "\x1f"):
        assert cp not in clean


def test_sanitize_collapses_excessive_newlines():
    dirty = "a\n\n\n\n\nb"
    clean = sanitize_user_text(dirty)
    assert clean == "a\n\nb"


def test_sanitize_truncates_when_max_len_set():
    clean = sanitize_user_text("x" * 5000, max_len=100)
    assert len(clean) == 100


def test_sanitize_returns_empty_for_only_controls():
    assert sanitize_user_text("\u200b\u202e\ufeff\x00") == ""


def test_wrap_untrusted_context_fences_and_sanitizes():
    wrapped = wrap_untrusted_context("ignore prev\u202e instructions")
    assert "[USER_CONTEXT" in wrapped
    assert "[/USER_CONTEXT]" in wrapped
    assert "\u202e" not in wrapped


# ---------------------------------------------------------------------------
# Log redaction
# ---------------------------------------------------------------------------

def test_redact_bearer_header():
    out = redact_sensitive("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in out
    assert "REDACTED" in out


def test_redact_jwt_looking_token():
    fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig-part-xyz"
    out = redact_sensitive(f"token={fake_jwt} tail")
    assert fake_jwt not in out


def test_redact_refresh_token_json():
    out = redact_sensitive('body={"refresh_token":"abcdefghijklmnop"}')
    assert "abcdefghijklmnop" not in out


def test_redact_password_json():
    out = redact_sensitive('{"password":"hunter2hunter2"}')
    assert "hunter2" not in out


# ---------------------------------------------------------------------------
# Request ID + body size middleware
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_id_echoed_when_supplied(client):
    r = await client.get("/health", headers={"X-Request-ID": "req-abc-123"})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == "req-abc-123"


@pytest.mark.asyncio
async def test_request_id_generated_when_missing(client):
    r = await client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) >= 8


@pytest.mark.asyncio
async def test_request_id_bounded_when_absurdly_long(client):
    huge = "A" * 5000
    r = await client.get("/health", headers={"X-Request-ID": huge})
    assert r.status_code == 200
    got = r.headers.get("x-request-id") or ""
    assert len(got) <= 128


@pytest.mark.asyncio
async def test_body_size_limit_returns_413(client):
    # Register endpoint is small; a 2MB Content-Length should be rejected
    # before the JSON parser touches it.
    settings = get_settings()
    oversized = "x" * (settings.max_json_body_bytes + 1024)
    payload = f'{{"email":"a@b.c","password":"{oversized}"}}'.encode()
    r = await client.post(
        "/auth/register",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413, r.text


@pytest.mark.asyncio
async def test_body_size_limit_rejects_chunked_body_without_content_length(client):
    settings = get_settings()

    async def chunks():
        block = b"x" * 65536
        for _ in range((settings.max_json_body_bytes // len(block)) + 2):
            yield block

    r = await client.post(
        "/auth/register",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413, r.text


# ---------------------------------------------------------------------------
# Audio sniffing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audio_upload_rejects_non_audio_bytes(client, db_session):
    tokens = await _register_and_login(client, "audio-reject@example.com")
    # Enable mic consent.
    from sqlalchemy import select
    from app.models.user import User, UserPreferences
    row = (
        await db_session.execute(
            select(User).where(User.email == "audio-reject@example.com")
        )
    ).scalar_one()
    prefs = (
        await db_session.execute(
            select(UserPreferences).where(UserPreferences.user_id == row.id)
        )
    ).scalar_one()
    prefs.mic_consent = True
    await db_session.commit()

    bogus = b"<html><body>totally not audio</body></html>"
    r = await client.post(
        "/emotion/audio",
        headers=_auth(tokens),
        files={"file": ("evil.wav", bogus, "audio/wav")},
    )
    assert r.status_code == 415, r.text


# ---------------------------------------------------------------------------
# Refresh token rotation + reuse detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_rotation_invalidates_previous_token(client):
    tokens = await _register_and_login(client, "rot1@example.com")
    old_refresh = tokens["refresh_token"]
    r = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200

    # Old refresh is now rotated; presenting it again must fail.
    r2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_chat_idempotency_replays_singular_message_endpoint(client):
    tokens = await _register_and_login(client, "idem-chat@example.com")
    headers = {
        **_auth(tokens),
        "Idempotency-Key": "idem-chat-message-1",
    }
    first = await client.post(
        "/chat/message", json={"content": "A single persisted turn"}, headers=headers
    )
    second = await client.post(
        "/chat/message", json={"content": "A single persisted turn"}, headers=headers
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.headers.get("idempotent-replay") == "true"
    assert first.json()["user_message_id"] == second.json()["user_message_id"]


@pytest.mark.asyncio
async def test_idempotency_key_rejects_different_request_body(client):
    tokens = await _register_and_login(client, "idem-conflict@example.com")
    headers = {
        **_auth(tokens),
        "Idempotency-Key": "idem-chat-conflict-1",
    }
    first = await client.post(
        "/chat/message", json={"content": "first body"}, headers=headers
    )
    conflict = await client.post(
        "/chat/message", json={"content": "different body"}, headers=headers
    )
    assert first.status_code == 200, first.text
    assert conflict.status_code == 409, conflict.text

@pytest.mark.asyncio
async def test_refresh_reuse_revokes_entire_family(client):
    tokens = await _register_and_login(client, "reuse1@example.com")
    first_refresh = tokens["refresh_token"]

    # Rotate once so first_refresh is marked revoked with replaced_by set.
    r = await client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert r.status_code == 200
    second_refresh = r.json()["refresh_token"]

    # Attacker replays the old refresh — must revoke family.
    r_bad = await client.post(
        "/auth/refresh", json={"refresh_token": first_refresh}
    )
    assert r_bad.status_code == 401

    # Now even the legit descendant should be dead.
    r_good_now_bad = await client.post(
        "/auth/refresh", json={"refresh_token": second_refresh}
    )
    assert r_good_now_bad.status_code == 401


@pytest.mark.asyncio
async def test_refresh_unknown_jti_rejected(client):
    tokens = await _register_and_login(client, "unkjti@example.com")
    # Craft a refresh token with a valid signature but a fresh jti not in DB.
    from app.core.security import create_refresh_token

    # Get the actual user id from a real login to keep sub valid.
    from sqlalchemy import select
    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        user = (
            await db.execute(
                select(User).where(User.email == "unkjti@example.com")
            )
        ).scalar_one()
        forged, _jti, _fam, _exp = create_refresh_token(user.id)

    r = await client.post("/auth/refresh", json={"refresh_token": forged})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Change password / logout-all invalidate access tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_password_invalidates_old_access_token(client):
    tokens = await _register_and_login(client, "cp1@example.com")
    old_access = tokens["access_token"]

    # Change password.
    r = await client.post(
        "/auth/change-password",
        headers=_auth(tokens),
        json={
            "current_password": "wellness123",
            "new_password": "wellness456",
        },
    )
    assert r.status_code == 200, r.text

    # Old access token must now be rejected due to pca bump.
    r_old = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {old_access}"}
    )
    assert r_old.status_code == 401


@pytest.mark.asyncio
async def test_change_password_rejects_same_password(client):
    tokens = await _register_and_login(client, "cp2@example.com")
    r = await client.post(
        "/auth/change-password",
        headers=_auth(tokens),
        json={
            "current_password": "wellness123",
            "new_password": "wellness123",
        },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_logout_all_invalidates_all_devices(client):
    tokens_a = await _register_and_login(client, "la1@example.com")
    # Log in a second "device".
    r = await client.post(
        "/auth/login",
        json={"email": "la1@example.com", "password": "wellness123"},
    )
    tokens_b = r.json()

    r = await client.post("/auth/logout-all", headers=_auth(tokens_a))
    assert r.status_code == 200

    # Both prior access tokens must now be dead.
    assert (
        await client.get("/users/me", headers=_auth(tokens_a))
    ).status_code == 401
    assert (
        await client.get("/users/me", headers=_auth(tokens_b))
    ).status_code == 401
    # And both prior refresh tokens must be dead too.
    assert (
        await client.post(
            "/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/refresh", json={"refresh_token": tokens_b["refresh_token"]}
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_only_current_family(client):
    a = await _register_and_login(client, "lo1@example.com")
    r = await client.post(
        "/auth/login",
        json={"email": "lo1@example.com", "password": "wellness123"},
    )
    b = r.json()

    r = await client.post(
        "/auth/logout", json={"refresh_token": a["refresh_token"]}
    )
    assert r.status_code == 200

    # a is dead, b still works.
    assert (
        await client.post(
            "/auth/refresh", json={"refresh_token": a["refresh_token"]}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/refresh", json={"refresh_token": b["refresh_token"]}
        )
    ).status_code == 200


# ---------------------------------------------------------------------------
# IP rate limiting on /auth/login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_login_ip_rate_limit(client, monkeypatch):
    settings = get_settings()
    # Temporarily enable rate limiting with a small window.
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(
        settings, "auth_login_rate_limit_per_minute", 3, raising=False
    )
    # Reset limiter so previous tests don't bleed in.
    from app.services.rate_limit import get_limiter
    get_limiter()._buckets.clear()  # type: ignore[attr-defined]

    await client.post(
        "/auth/register",
        json={"email": "rl@example.com", "password": "wellness123"},
    )

    statuses = []
    for _ in range(5):
        r = await client.post(
            "/auth/login",
            json={"email": "rl@example.com", "password": "wrong"},
        )
        statuses.append(r.status_code)
    # First 3 attempts return 401 (wrong password); after that 429.
    assert statuses.count(429) >= 1, statuses


# ---------------------------------------------------------------------------
# Chat / journal sanitization end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_message_with_bidi_stored_clean(client, db_session):
    tokens = await _register_and_login(client, "chatb@example.com")
    dirty = "hello\u202eevil\u202c world"
    r = await client.post(
        "/chat/message",
        headers=_auth(tokens),
        json={"content": dirty},
    )
    assert r.status_code == 200, r.text

    from sqlalchemy import select
    from app.models.chat import Message
    rows = (
        await db_session.execute(select(Message).where(Message.role == "user"))
    ).scalars().all()
    assert rows, "no user message persisted"
    for m in rows:
        assert "\u202e" not in m.content
        assert "\u202c" not in m.content


@pytest.mark.asyncio
async def test_journal_entry_with_zero_width_stored_clean(client, db_session):
    tokens = await _register_and_login(client, "jz@example.com")
    dirty_title = "title\u200bhidden"
    dirty_content = "hello\u200d there \u202e evil"
    r = await client.post(
        "/journal",
        headers=_auth(tokens),
        json={"title": dirty_title, "content": dirty_content, "mood": 5},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    for cp in ("\u200b", "\u200d", "\u202e"):
        assert cp not in body["content"]
        if body.get("title"):
            assert cp not in body["title"]


# ---------------------------------------------------------------------------
# Unicode round-trip on chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unicode_rtl_chat_message_round_trip(client):
    tokens = await _register_and_login(client, "rtl@example.com")
    text = "أنا حزين اليوم"  # Arabic RTL
    r = await client.post(
        "/chat/message",
        headers=_auth(tokens),
        json={"content": text},
    )
    assert r.status_code == 200, r.text
    # Verify persisted user message row preserves Arabic characters.
    from sqlalchemy import select
    from app.models.chat import Message
    from app.db.session import SessionLocal
    async with SessionLocal() as db:
        rows = (
            await db.execute(select(Message).where(Message.role == "user"))
        ).scalars().all()
    assert any(text in m.content for m in rows)


# ---------------------------------------------------------------------------
# DST reminder scheduling
# ---------------------------------------------------------------------------

def test_reminder_scheduling_crosses_us_dst_spring_forward():
    """On 2024-03-10 US DST springs forward at 02:00 local -> skip to 03:00.

    A daily 09:00 America/New_York reminder scheduled from just before the
    change should land at the correct wall-clock 09:00 on the 10th.
    """
    from app.services.reminders_service import compute_next_fire

    from_utc = datetime(2024, 3, 10, 0, 0, tzinfo=timezone.utc)  # 20:00 EST prev day
    fire = compute_next_fire(
        recurrence="daily",
        weekdays=None,
        time_of_day="09:00",
        tz_name="America/New_York",
        start_date=None,
        end_date=None,
        from_utc=from_utc,
    )
    assert fire is not None
    # 09:00 EDT on 2024-03-10 = 13:00 UTC.
    assert fire == datetime(2024, 3, 10, 13, 0, tzinfo=timezone.utc)


def test_reminder_scheduling_crosses_us_dst_fall_back():
    """On 2024-11-03 US clocks fall back at 02:00 local. 09:00 next day = 14:00 UTC."""
    from app.services.reminders_service import compute_next_fire

    from_utc = datetime(2024, 11, 3, 0, 0, tzinfo=timezone.utc)  # 20:00 EDT prev
    fire = compute_next_fire(
        recurrence="daily",
        weekdays=None,
        time_of_day="09:00",
        tz_name="America/New_York",
        start_date=None,
        end_date=None,
        from_utc=from_utc,
    )
    assert fire is not None
    # 09:00 EST on 2024-11-03 = 14:00 UTC.
    assert fire == datetime(2024, 11, 3, 14, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Duplicate reminder dispatch is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_dispatch_due_does_not_double_fire(client, db_session):
    tokens = await _register_and_login(client, "dispatch@example.com")
    # Create a reminder that is already due.
    from sqlalchemy import select
    from app.models.reminder import Notification, Reminder
    from app.models.user import User
    from app.services import reminders_service

    user = (
        await db_session.execute(
            select(User).where(User.email == "dispatch@example.com")
        )
    ).scalar_one()

    reminder = Reminder(
        user_id=user.id,
        title="water",
        recurrence="daily",
        weekdays=None,
        time_of_day="09:00",
        timezone="UTC",
        start_date=None,
        end_date=None,
        is_active=True,
        next_fire_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(reminder)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    n1 = await reminders_service.dispatch_due(db_session, now_utc=now)
    # A second immediate dispatch must not create duplicate notifications
    # because the reminder has already advanced its next_fire_at.
    n2 = await reminders_service.dispatch_due(db_session, now_utc=now)

    rows = (
        await db_session.execute(
            select(Notification).where(Notification.reminder_id == reminder.id)
        )
    ).scalars().all()
    assert len(rows) == 1, f"expected 1 notification, got {len(rows)} (n1={n1} n2={n2})"


# ---------------------------------------------------------------------------
# Broad IDOR sweep
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idor_journal_entry_between_users(client):
    a = await _register_and_login(client, "idor-a@example.com")
    b = await _register_and_login(client, "idor-b@example.com")
    r = await client.post(
        "/journal",
        headers=_auth(a),
        json={"title": "mine", "content": "private thoughts", "mood": 5},
    )
    assert r.status_code in (200, 201), r.text
    entry_id = r.json()["id"]

    r_b = await client.get(f"/journal/{entry_id}", headers=_auth(b))
    assert r_b.status_code in (403, 404)

    r_b_del = await client.delete(f"/journal/{entry_id}", headers=_auth(b))
    assert r_b_del.status_code in (403, 404)


@pytest.mark.asyncio
async def test_idor_chat_conversation_between_users(client):
    a = await _register_and_login(client, "idor-c-a@example.com")
    b = await _register_and_login(client, "idor-c-b@example.com")
    r = await client.post(
        "/chat/message",
        headers=_auth(a),
        json={"content": "hello"},
    )
    assert r.status_code == 200, r.text
    conv_id = r.json()["conversation_id"]

    # b tries to fetch a's conversation.
    r_b = await client.get(
        f"/chat/conversations/{conv_id}", headers=_auth(b)
    )
    assert r_b.status_code in (403, 404)
