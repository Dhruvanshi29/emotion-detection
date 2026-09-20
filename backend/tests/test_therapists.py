"""Therapist directory (Phase 8) — discovery, verification, reporting."""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "T"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_list_requires_auth(client):
    r = await client.get("/therapists")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_default_list_only_verified(client):
    h = await _register(client, "t-list@example.com")
    r = await client.get("/therapists", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["items"], "seeded therapists should show up"
    # The pending one MUST NOT be listed by default.
    slugs = [x["slug"] for x in body["items"]]
    assert "nadia-almeida-pending" not in slugs
    for it in body["items"]:
        assert it["verified"] is True
        assert it["verification_status"] == "verified"
    # Shape checks.
    a = body["items"][0]
    for k in ("id", "slug", "full_name", "title", "specializations", "languages"):
        assert k in a


@pytest.mark.asyncio
async def test_unverified_can_be_included_but_never_endorsed(client):
    h = await _register(client, "t-unv@example.com")
    r = await client.get("/therapists?verified_only=false", headers=h)
    assert r.status_code == 200
    slugs = [x["slug"] for x in r.json()["items"]]
    assert "nadia-almeida-pending" in slugs
    for it in r.json()["items"]:
        if it["slug"] == "nadia-almeida-pending":
            assert it["verified"] is False
            assert it["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_filter_by_specialization_language_country_modality_price(client):
    h = await _register(client, "t-filter@example.com")

    r = await client.get(
        "/therapists?specialization=anxiety&language=en", headers=h
    )
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert "anxiety" in it["specializations"]
        assert "en" in it["languages"]

    r2 = await client.get("/therapists?country=IN", headers=h)
    assert r2.status_code == 200
    assert r2.json()["total"] >= 1
    assert all(it["country_code"] == "IN" for it in r2.json()["items"])

    r3 = await client.get("/therapists?modality=in_person", headers=h)
    assert r3.status_code == 200
    assert all(it["offers_in_person"] for it in r3.json()["items"])

    r4 = await client.get("/therapists?price_max=125", headers=h)
    assert r4.status_code == 200
    for it in r4.json()["items"]:
        # Either unpriced or minimum fits under 125.
        assert it["session_price_min"] is None or it["session_price_min"] <= 125

    r5 = await client.get("/therapists?accepts_new_clients=true", headers=h)
    assert r5.status_code == 200
    assert all(it["accepts_new_clients"] for it in r5.json()["items"])


@pytest.mark.asyncio
async def test_ordering(client):
    h = await _register(client, "t-order@example.com")
    r = await client.get("/therapists?order=name&limit=50", headers=h)
    names = [it["full_name"] for it in r.json()["items"]]
    assert names == sorted(names)

    r2 = await client.get("/therapists?order=price_asc&limit=50", headers=h)
    prices = [
        it["session_price_min"]
        for it in r2.json()["items"]
        if it["session_price_min"] is not None
    ]
    assert prices == sorted(prices)


@pytest.mark.asyncio
async def test_detail_and_disclaimer(client):
    h = await _register(client, "t-detail@example.com")
    r = await client.get("/therapists/dr-amelia-chen", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "dr-amelia-chen"
    assert body["bio"]
    assert body["verified"] is True
    assert body["verification"]["status"] == "verified"
    assert body["verification"]["license_number"]
    assert body["availability"]
    # Plan §22 disclaimer must be surfaced on every profile.
    assert "does not endorse" in body["disclaimer"].lower()


@pytest.mark.asyncio
async def test_detail_hides_unverified(client):
    h = await _register(client, "t-hidden@example.com")
    r = await client.get("/therapists/nadia-almeida-pending", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detail_missing_slug(client):
    h = await _register(client, "t-404@example.com")
    r = await client.get("/therapists/does-not-exist", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_report_flow(client):
    h = await _register(client, "t-report@example.com")
    r = await client.post(
        "/therapists/dr-amelia-chen/report",
        headers=h,
        json={"kind": "outdated_info", "notes": "The phone number is wrong."},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "outdated_info"
    assert body["status"] == "open"

    bad = await client.post(
        "/therapists/dr-amelia-chen/report", headers=h, json={"kind": "nope"}
    )
    assert bad.status_code == 422

    missing = await client.post(
        "/therapists/does-not-exist/report",
        headers=h,
        json={"kind": "outdated_info"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_search_by_name(client):
    h = await _register(client, "t-search@example.com")
    r = await client.get("/therapists?q=Amelia", headers=h)
    assert r.status_code == 200
    slugs = [it["slug"] for it in r.json()["items"]]
    assert "dr-amelia-chen" in slugs
