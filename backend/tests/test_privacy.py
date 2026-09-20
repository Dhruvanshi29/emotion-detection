"""Consent, audit, and data-lifecycle tests (Phase 12)."""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "P"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# Consent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_consent_requires_auth(client):
    r = await client.get("/consent")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_consent_flow_records_event_and_updates_prefs(client):
    h = await _register(client, "consent-flow@example.com")

    r = await client.get("/consent", headers=h)
    assert r.status_code == 200
    state = r.json()
    assert state["mic"] is False
    assert state["camera"] is False
    assert state["history"] == []

    # Grant mic consent.
    r = await client.post(
        "/consent",
        json={"kind": "mic", "granted": True, "source": "settings"},
        headers=h,
    )
    assert r.status_code == 201
    evt = r.json()
    assert evt["kind"] == "mic"
    assert evt["granted"] is True

    # Revoke.
    r = await client.post(
        "/consent",
        json={"kind": "mic", "granted": False, "notes": "changed my mind"},
        headers=h,
    )
    assert r.status_code == 201

    # State reflects latest = False and history has both events.
    r = await client.get("/consent", headers=h)
    state = r.json()
    assert state["mic"] is False
    assert len(state["history"]) >= 2
    # History is newest-first.
    assert state["history"][0]["granted"] is False


@pytest.mark.asyncio
async def test_consent_rejects_bad_kind(client):
    h = await _register(client, "consent-bad@example.com")
    r = await client.post(
        "/consent", json={"kind": "telemetry", "granted": True}, headers=h
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_consent_terms_and_data_processing_stored_as_events(client):
    h = await _register(client, "consent-terms@example.com")
    await client.post(
        "/consent",
        json={"kind": "terms", "granted": True, "source": "signup"},
        headers=h,
    )
    await client.post(
        "/consent",
        json={"kind": "data_processing", "granted": True, "source": "signup"},
        headers=h,
    )
    state = (await client.get("/consent", headers=h)).json()
    assert state["terms"] is True
    assert state["data_processing"] is True


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_audit_lists_own_consent_events(client):
    h = await _register(client, "audit-user@example.com")
    await client.post(
        "/consent", json={"kind": "memory", "granted": True}, headers=h
    )
    r = await client.get("/audit", headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["category"] == "consent" for i in items)


@pytest.mark.asyncio
async def test_audit_isolated_per_user(client):
    ha = await _register(client, "audit-a@example.com")
    hb = await _register(client, "audit-b@example.com")
    await client.post(
        "/consent", json={"kind": "memory", "granted": False}, headers=ha
    )
    items_b = (await client.get("/audit", headers=hb)).json()["items"]
    # B should see nothing from A.
    assert all(i["category"] != "consent" for i in items_b)


# --------------------------------------------------------------------------- #
# Data export
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_export_returns_user_bundle_without_password(client):
    h = await _register(client, "export-user@example.com")
    # Seed a memory so the export bundle is non-trivial.
    await client.post(
        "/memory",
        json={"kind": "fact", "title": "Coffee", "content": "I like flat whites."},
        headers=h,
    )
    r = await client.get("/privacy/export", headers=h)
    assert r.status_code == 200
    dump = r.json()
    assert dump["user"]["email"] == "export-user@example.com"
    assert "hashed_password" not in dump["user"]
    assert dump["counts"]["memories"] == 1
    assert len(dump["data"]["memories"]) == 1
    # Export itself is audited.
    audit = (await client.get("/audit", headers=h)).json()["items"]
    assert any(i["action"] == "data.exported" for i in audit)


# --------------------------------------------------------------------------- #
# Category deletion
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_category_delete_clears_only_that_bucket(client):
    h = await _register(client, "cat-del@example.com")
    await client.post(
        "/memory",
        json={"kind": "fact", "title": "Cat", "content": "I have a tabby."},
        headers=h,
    )
    await client.post(
        "/journal",
        json={"title": "day", "content": "A quiet morning walk in the park."},
        headers=h,
    )

    r = await client.delete("/privacy/data/memory", headers=h)
    assert r.status_code == 200
    assert r.json() == {"category": "memory", "deleted": 1}

    # Memories gone.
    mems = (await client.get("/memory", headers=h)).json()
    assert mems["items"] == []
    # Journal untouched.
    ents = (await client.get("/journal", headers=h)).json()
    assert len(ents) == 1


@pytest.mark.asyncio
async def test_category_delete_rejects_unknown_category(client):
    h = await _register(client, "cat-bad@example.com")
    r = await client.delete("/privacy/data/telemetry", headers=h)
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Account deletion
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_delete_account_requires_confirm_word(client):
    h = await _register(client, "acct-del-1@example.com")
    r = await client.request(
        "DELETE", "/privacy/account", json={"confirm": "yes"}, headers=h
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_delete_account_cascades(client):
    h = await _register(client, "acct-del-2@example.com")
    await client.post(
        "/memory",
        json={"kind": "fact", "title": "Book", "content": "I read fantasy novels."},
        headers=h,
    )
    r = await client.request(
        "DELETE", "/privacy/account", json={"confirm": "DELETE"}, headers=h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["memory"] == 1

    # Token no longer resolves — user gone.
    r = await client.get("/users/me", headers=h)
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Rate limit end-to-end (chat)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_chat_rate_limit_returns_429(client, monkeypatch):
    from app.services.rate_limit import get_limiter

    get_limiter().reset()
    # Enable the limiter and squeeze the budget to 1/minute so the second
    # request in the same window trips 429.
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(s, "chat_rate_limit_per_minute", 1, raising=False)

    h = await _register(client, "rl-chat@example.com")
    body = {"content": "Hello there"}

    r1 = await client.post("/chat/message", json=body, headers=h)
    assert r1.status_code == 200

    r2 = await client.post("/chat/message", json=body, headers=h)
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers

    # Reset so later tests aren't blocked.
    get_limiter().reset()
    monkeypatch.setattr(s, "rate_limit_enabled", False, raising=False)
