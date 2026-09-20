"""Journal CRUD + reflection tests."""
from __future__ import annotations

import pytest


async def _auth(client, email="journal@example.com") -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "J"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_journal_requires_auth(client):
    r = await client.post("/journal", json={"content": "hi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_lists_and_reads_entry(client):
    h = await _auth(client, "j1@example.com")

    r = await client.post(
        "/journal",
        headers=h,
        json={
            "title": "A quiet evening",
            "content": "I feel a little sad and lonely tonight but okay.",
            "mood": 2,
            "tags": ["evening", "reflection"],
            "analyze": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"]
    assert body["title"] == "A quiet evening"
    assert body["mood"] == 2
    assert body["tags"] == ["evening", "reflection"]
    entry_id = body["id"]

    # BackgroundTasks run after response is sent, so analysis should have
    # been persisted by the time we GET the entry.
    r_get = await client.get(f"/journal/{entry_id}", headers=h)
    assert r_get.status_code == 200
    detail = r_get.json()
    assert detail["content"].startswith("I feel a little sad")
    assert detail["analysis"] is not None
    a = detail["analysis"]
    assert a["reflection_prompt"]
    assert a["summary"].startswith("[stub summary]")
    assert a["dominant_emotion"] == "sadness"
    assert a["sentiment"] == "negative"

    # And it should appear in the list, with a preview + has_analysis.
    r_list = await client.get("/journal", headers=h)
    assert r_list.status_code == 200
    entries = r_list.json()
    assert len(entries) == 1
    row = entries[0]
    assert row["id"] == entry_id
    assert row["has_analysis"] is True
    assert row["preview"].startswith("I feel a little sad")
    assert "content" not in row  # list rows are compact


@pytest.mark.asyncio
async def test_analyze_true_also_records_emotion_event(client):
    h = await _auth(client, "j2@example.com")

    r = await client.post(
        "/journal",
        headers=h,
        json={"content": "I feel so happy and grateful today", "mood": 5},
    )
    assert r.status_code == 201
    entry_id = r.json()["id"]

    events = await client.get("/emotion/events?source=journal", headers=h)
    assert events.status_code == 200
    body = events.json()
    assert len(body) == 1
    assert body[0]["source"] == "journal"
    assert body[0]["source_ref_id"] == entry_id
    assert body[0]["dominant_emotion"] == "joy"


@pytest.mark.asyncio
async def test_analyze_false_skips_background(client):
    h = await _auth(client, "j3@example.com")
    r = await client.post(
        "/journal",
        headers=h,
        json={"content": "Just a quick note", "analyze": False},
    )
    assert r.status_code == 201
    entry_id = r.json()["id"]

    detail = await client.get(f"/journal/{entry_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["analysis"] is None

    # No emotion event either.
    events = await client.get("/emotion/events?source=journal", headers=h)
    assert events.status_code == 200
    assert events.json() == []


@pytest.mark.asyncio
async def test_manual_analyze_upserts_analysis(client):
    h = await _auth(client, "j4@example.com")
    r = await client.post(
        "/journal",
        headers=h,
        json={"content": "Feeling neutral about things.", "analyze": False},
    )
    entry_id = r.json()["id"]

    an = await client.post(f"/journal/{entry_id}/analyze", headers=h)
    assert an.status_code == 200
    body = an.json()
    assert body["analysis"] is not None
    assert body["analysis"]["reflection_prompt"]
    # neutral content -> stub returns 'neutral'
    assert body["analysis"]["dominant_emotion"] == "neutral"

    # Re-analyzing replaces the previous row (no duplicate).
    an2 = await client.post(f"/journal/{entry_id}/analyze", headers=h)
    assert an2.status_code == 200

    # Only one analysis persisted (the model has UNIQUE on entry_id).
    detail = await client.get(f"/journal/{entry_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["analysis"]["provider"] == "stub"


@pytest.mark.asyncio
async def test_patch_and_delete_entry(client):
    h = await _auth(client, "j5@example.com")
    r = await client.post(
        "/journal",
        headers=h,
        json={"content": "first draft", "analyze": False},
    )
    entry_id = r.json()["id"]

    p = await client.patch(
        f"/journal/{entry_id}",
        headers=h,
        json={"title": "Updated", "mood": 4, "tags": ["a", "b"]},
    )
    assert p.status_code == 200
    assert p.json()["title"] == "Updated"
    assert p.json()["mood"] == 4

    d = await client.delete(f"/journal/{entry_id}", headers=h)
    assert d.status_code == 204

    g = await client.get(f"/journal/{entry_id}", headers=h)
    assert g.status_code == 404


@pytest.mark.asyncio
async def test_ownership_isolation(client):
    h1 = await _auth(client, "own1@example.com")
    h2 = await _auth(client, "own2@example.com")

    r = await client.post(
        "/journal",
        headers=h1,
        json={"content": "private note", "analyze": False},
    )
    entry_id = r.json()["id"]

    # user 2 cannot see user 1's entry
    g = await client.get(f"/journal/{entry_id}", headers=h2)
    assert g.status_code == 404
    p = await client.patch(
        f"/journal/{entry_id}", headers=h2, json={"title": "hijack"}
    )
    assert p.status_code == 404
    d = await client.delete(f"/journal/{entry_id}", headers=h2)
    assert d.status_code == 404
    a = await client.post(f"/journal/{entry_id}/analyze", headers=h2)
    assert a.status_code == 404

    # user 2's list is empty
    lst2 = await client.get("/journal", headers=h2)
    assert lst2.json() == []


@pytest.mark.asyncio
async def test_content_validation(client):
    h = await _auth(client, "val@example.com")
    r = await client.post("/journal", headers=h, json={"content": ""})
    assert r.status_code == 422
    r2 = await client.post(
        "/journal", headers=h, json={"content": "ok", "mood": 9}
    )
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_fallback_reflection_direct():
    from app.services.ai.journal import _fallback_reflection

    ref = _fallback_reflection("I feel scared and anxious", mood=2)
    assert ref.reflection_prompt
    assert ref.dominant_emotion in {"fear", "sadness"}
    assert ref.provider == "fallback"

    ref2 = _fallback_reflection("", mood=None)
    assert ref2.reflection_prompt
    assert ref2.provider == "fallback"


@pytest.mark.asyncio
async def test_extract_json_handles_prose_and_fences():
    from app.services.ai.journal import _extract_json

    payload = (
        "Sure! Here you go:\n```json\n"
        '{"summary":"you sounded gentle","themes":["rest"],'
        '"key_feelings":["tender"],"dominant_emotion":"sadness",'
        '"sentiment":"negative","confidence":0.7,'
        '"reflection_prompt":"What would rest look like tonight?"}\n```'
    )
    obj = _extract_json(payload)
    assert obj is not None
    assert obj["dominant_emotion"] == "sadness"
    assert obj["reflection_prompt"].startswith("What would rest")
