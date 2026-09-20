"""Auth flow tests: register, login, refresh, error cases."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_register_and_login_happy_path(client):
    payload = {
        "email": "alice@example.com",
        "password": "wellness123",
        "display_name": "Alice",
    }
    r = await client.post("/auth/register", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["profile"]["display_name"] == "Alice"
    assert body["profile"]["timezone"] == "UTC"
    assert body["preferences"]["theme"] in {"system", "dark", "light"}

    r = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wellness123"},
    )
    assert r.status_code == 200, r.text
    tokens = r.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["token_type"].lower() == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "wellness123"}
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "wellness123"},
    )
    r = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "wrongpass"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_flow(client):
    await client.post(
        "/auth/register",
        json={"email": "carol@example.com", "password": "wellness123"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "wellness123"},
    )
    refresh_token = login.json()["refresh_token"]
    r = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200, r.text
    assert r.json().get("access_token")


@pytest.mark.asyncio
async def test_refresh_with_invalid_token(client):
    r = await client.post("/auth/refresh", json={"refresh_token": "not-a-token"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_google_identity_login_creates_and_reuses_local_account(
    client, monkeypatch
):
    from app.core.config import get_settings
    from app.services import auth_service

    monkeypatch.setattr(
        get_settings(), "google_identity_platform_project_id", "wellness-test"
    )

    async def verified(_token: str, project_id: str) -> dict:
        assert project_id == "wellness-test"
        return {
            "sub": "google-subject-123",
            "email": "google-user@example.com",
            "email_verified": True,
            "name": "Google User",
        }

    monkeypatch.setattr(auth_service, "verify_google_identity_token", verified)
    body = {"id_token": "x" * 200}

    first = await client.post("/auth/google", json=body)
    second = await client.post("/auth/google", json=body)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {second.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "google-user@example.com"
    assert me.json()["is_verified"] is True
    assert me.json()["profile"]["display_name"] == "Google User"


@pytest.mark.asyncio
async def test_google_identity_login_requires_verified_email(client, monkeypatch):
    from app.core.config import get_settings
    from app.services import auth_service

    monkeypatch.setattr(
        get_settings(), "google_identity_platform_project_id", "wellness-test"
    )

    async def unverified(_token: str, _project_id: str) -> dict:
        return {
            "sub": "google-subject-unverified",
            "email": "unverified@example.com",
            "email_verified": False,
        }

    monkeypatch.setattr(auth_service, "verify_google_identity_token", unverified)
    r = await client.post("/auth/google", json={"id_token": "x" * 200})
    assert r.status_code == 401
