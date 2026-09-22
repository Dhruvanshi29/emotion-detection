from __future__ import annotations

import pytest

from app.services.auth_service import totp_code


@pytest.mark.asyncio
async def test_authenticator_mfa_login_flow(client):
    email = "mfa-flow@example.com"
    password = "wellness123"
    assert (await client.post("/auth/register", json={"email": email, "password": password})).status_code == 201
    login = await client.post("/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    setup = await client.post(
        "/auth/mfa/setup", headers=headers, json={"password": password}
    )
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = totp_code(secret)
    assert (await client.post("/auth/mfa/confirm", headers=headers, json={"code": code})).status_code == 200

    replacement = await client.post(
        "/auth/mfa/setup", headers=headers, json={"password": password}
    )
    assert replacement.status_code == 409

    missing = await client.post("/auth/login", json={"email": email, "password": password})
    assert missing.status_code == 401
    accepted = await client.post(
        "/auth/login", json={"email": email, "password": password, "mfa_code": totp_code(secret)}
    )
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_registration_enforces_supplied_age_gate(client):
    underage = await client.post(
        "/auth/register",
        json={
            "email": "minor@example.com",
            "password": "wellness123",
            "age_confirmed": True,
            "dob_year": 2020,
        },
    )
    assert underage.status_code == 422


@pytest.mark.asyncio
async def test_browser_session_uses_httponly_refresh_and_csrf(client):
    email = "browser-session@example.com"
    password = "wellness123"
    await client.post("/auth/register", json={"email": email, "password": password})
    login = await client.post("/auth/browser/login", json={"email": email, "password": password})
    assert login.status_code == 200
    body = login.json()
    assert "refresh_token" not in body
    assert body["csrf_token"]
    cookies = login.headers.get_list("set-cookie")
    assert any("saaya_refresh=" in value and "HttpOnly" in value for value in cookies)

    refreshed = await client.post(
        "/auth/browser/refresh",
        headers={"X-CSRF-Token": body["csrf_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
