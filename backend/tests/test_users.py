"""User /users/me tests: get, patch profile + preferences, auth guard."""
from __future__ import annotations

import pytest


async def _register_and_auth(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "User"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "wellness123"},
    )
    tok = login.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get("/users/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client):
    headers = await _register_and_auth(client, "dave@example.com")
    r = await client.get("/users/me", headers=headers)
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == "dave@example.com"
    assert "profile" in me and "preferences" in me


@pytest.mark.asyncio
async def test_patch_profile_and_preferences(client):
    headers = await _register_and_auth(client, "eve@example.com")
    r = await client.patch(
        "/users/me",
        headers=headers,
        json={
            "display_name": "Eve S.",
            "timezone": "America/New_York",
            "age_confirmed": True,
            "dob_year": 1995,
            "theme": "dark",
            "mic_consent": True,
            "memory_enabled": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["profile"]["display_name"] == "Eve S."
    assert body["profile"]["timezone"] == "America/New_York"
    assert body["profile"]["age_confirmed"] is True
    assert body["profile"]["dob_year"] == 1995
    assert body["preferences"]["theme"] == "dark"
    assert body["preferences"]["mic_consent"] is True
    assert body["preferences"]["memory_enabled"] is False


@pytest.mark.asyncio
async def test_patch_partial_only_updates_provided_fields(client):
    headers = await _register_and_auth(client, "frank@example.com")
    r = await client.patch("/users/me", headers=headers, json={"theme": "light"})
    assert r.status_code == 200
    assert r.json()["preferences"]["theme"] == "light"
    # Other prefs should still exist with defaults
    r2 = await client.get("/users/me", headers=headers)
    assert r2.json()["preferences"]["notification_email"] is True
