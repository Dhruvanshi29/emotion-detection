"""Failure-mode tests (Phase 13, plan §13).

Covers auth failures, missing resources, oversized uploads, and consent gates.
"""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "F"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_missing_bearer_token_returns_401(client):
    r = await client.get("/chat/conversations")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_malformed_bearer_token_returns_401(client):
    r = await client.get(
        "/chat/conversations",
        headers={"Authorization": "Bearer nonsense.jwt.value"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_shape_returns_401(client):
    # A syntactically valid but bogus token.
    fake = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiJub3Blin0."
        "invalidsig"
    )
    r = await client.get(
        "/chat/conversations", headers={"Authorization": f"Bearer {fake}"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(client):
    email = "dup-fail@example.com"
    body = {"email": email, "password": "wellness123", "display_name": "D"}
    r1 = await client.post("/auth/register", json=body)
    assert r1.status_code == 201
    r2 = await client.post("/auth/register", json=body)
    assert r2.status_code in (400, 409)


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    email = "wrongpw@example.com"
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "W"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "not-it"}
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Missing / invalid resource ids
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unknown_conversation_returns_404(client):
    h = await _register(client, "conv-404@example.com")
    r = await client.get("/chat/conversations/00000000-0000-0000-0000-000000000000", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unknown_memory_returns_404(client):
    h = await _register(client, "mem-404@example.com")
    r = await client.get(
        "/memory/00000000-0000-0000-0000-000000000000", headers=h
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unknown_therapist_slug_returns_404(client):
    h = await _register(client, "th-404@example.com")
    r = await client.get("/therapists/does-not-exist", headers=h)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_empty_chat_message_rejected(client):
    h = await _register(client, "empty-chat@example.com")
    r = await client.post("/chat/message", json={"content": ""}, headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_oversized_chat_message_rejected(client):
    h = await _register(client, "big-chat@example.com")
    r = await client.post(
        "/chat/message", json={"content": "x" * 10_000}, headers=h
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bad_reminder_time_format_rejected(client):
    h = await _register(client, "bad-time@example.com")
    r = await client.post(
        "/reminders",
        json={
            "title": "hydrate",
            "kind": "hydration",
            "recurrence": "daily",
            "time_of_day": "25:99",  # invalid
            "timezone": "UTC",
        },
        headers=h,
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Voice consent + upload guardrails
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_voice_analyze_requires_mic_consent(client):
    h = await _register(client, "voice-noconsent@example.com")
    files = {"file": ("clip.wav", b"NEUTRAL", "audio/wav")}
    r = await client.post("/emotion/audio", files=files, headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_voice_analyze_rejects_empty_upload(client):
    h = await _register(client, "voice-empty@example.com")
    # Grant mic consent.
    await client.post(
        "/consent", json={"kind": "mic", "granted": True}, headers=h
    )
    files = {"file": ("clip.wav", b"", "audio/wav")}
    r = await client.post("/emotion/audio", files=files, headers=h)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_voice_analyze_rejects_oversized_upload(client, monkeypatch):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "voice_max_upload_bytes", 32, raising=False)
    h = await _register(client, "voice-huge@example.com")
    await client.post(
        "/consent", json={"kind": "mic", "granted": True}, headers=h
    )
    files = {"file": ("clip.wav", b"NEUTRAL:" + b"x" * 200, "audio/wav")}
    r = await client.post("/emotion/audio", files=files, headers=h)
    assert r.status_code == 413


# --------------------------------------------------------------------------- #
# Cross-user isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cannot_read_other_users_reminder(client):
    ha = await _register(client, "iso-a@example.com")
    hb = await _register(client, "iso-b@example.com")
    r = await client.post(
        "/reminders",
        json={
            "title": "walk",
            "kind": "custom",
            "recurrence": "daily",
            "time_of_day": "08:00",
            "timezone": "UTC",
        },
        headers=ha,
    )
    rid = r.json()["id"]
    r2 = await client.get(f"/reminders/{rid}", headers=hb)
    assert r2.status_code == 404
