"""Wellness (Phase 7) — library, sessions, goals, deterministic recommendations."""
from __future__ import annotations

import pytest


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "W"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_library_requires_auth(client):
    r = await client.get("/wellness/exercises")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_library_and_lookup(client):
    h = await _register(client, "w-list@example.com")
    r = await client.get("/wellness/exercises", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 8
    # All items have the mandatory fields.
    for item in body:
        assert item["id"] and item["slug"] and item["title"]
        assert item["category"] in {"breathing", "grounding", "reflection", "movement"}

    # Category filter.
    r2 = await client.get("/wellness/exercises?category=breathing", headers=h)
    assert r2.status_code == 200
    assert all(x["category"] == "breathing" for x in r2.json())

    # Single lookup.
    r3 = await client.get("/wellness/exercises/box-breathing-4-4-4-4", headers=h)
    assert r3.status_code == 200
    assert r3.json()["slug"] == "box-breathing-4-4-4-4"

    r4 = await client.get("/wellness/exercises/does-not-exist", headers=h)
    assert r4.status_code == 404


@pytest.mark.asyncio
async def test_goals_lifecycle(client):
    h = await _register(client, "w-goals@example.com")

    r = await client.post("/wellness/goals", headers=h, json={"kind": "reduce_stress"})
    assert r.status_code == 201
    goal_id = r.json()["id"]
    assert r.json()["kind"] == "reduce_stress"

    lst = await client.get("/wellness/goals", headers=h)
    assert lst.status_code == 200
    assert any(g["kind"] == "reduce_stress" for g in lst.json())

    # Duplicate add is idempotent.
    r2 = await client.post("/wellness/goals", headers=h, json={"kind": "reduce_stress"})
    assert r2.status_code == 201
    assert r2.json()["id"] == goal_id

    # Reject unknown kinds.
    bad = await client.post("/wellness/goals", headers=h, json={"kind": "nonsense"})
    assert bad.status_code == 422

    d = await client.delete(f"/wellness/goals/{goal_id}", headers=h)
    assert d.status_code == 204
    d2 = await client.delete(f"/wellness/goals/{goal_id}", headers=h)
    assert d2.status_code == 404


@pytest.mark.asyncio
async def test_session_flow_and_ratings(client):
    h = await _register(client, "w-sess@example.com")
    r = await client.post(
        "/wellness/sessions", headers=h, json={"exercise_slug": "gratitude-three"}
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["exercise_slug"] == "gratitude-three"
    assert r.json()["completed_at"] is None

    upd = await client.patch(
        f"/wellness/sessions/{sid}",
        headers=h,
        json={"completed": True, "rating": 5, "notes": "helpful"},
    )
    assert upd.status_code == 200
    assert upd.json()["completed_at"] is not None
    assert upd.json()["rating"] == 5
    assert upd.json()["notes"] == "helpful"

    hist = await client.get("/wellness/sessions", headers=h)
    assert hist.status_code == 200
    assert len(hist.json()) == 1

    # Bad slug -> 404
    bad = await client.post(
        "/wellness/sessions", headers=h, json={"exercise_slug": "no-such-thing"}
    )
    assert bad.status_code == 404

    # Rating bounds
    bad_rating = await client.patch(
        f"/wellness/sessions/{sid}", headers=h, json={"rating": 6}
    )
    assert bad_rating.status_code == 422


@pytest.mark.asyncio
async def test_session_ownership_isolation(client):
    h1 = await _register(client, "w-own1@example.com")
    h2 = await _register(client, "w-own2@example.com")
    r = await client.post(
        "/wellness/sessions", headers=h1, json={"exercise_slug": "gratitude-three"}
    )
    sid = r.json()["id"]

    upd = await client.patch(
        f"/wellness/sessions/{sid}", headers=h2, json={"completed": True}
    )
    assert upd.status_code == 404
    hist = await client.get("/wellness/sessions", headers=h2)
    assert hist.json() == []


@pytest.mark.asyncio
async def test_recommendations_baseline(client):
    """With no history and no goals, we still return a ranked list."""
    h = await _register(client, "w-rec-empty@example.com")
    r = await client.get("/wellness/recommendations?limit=3", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert 1 <= len(body["items"]) <= 3
    for it in body["items"]:
        assert "exercise" in it and "score" in it and "reasons" in it
    assert body["recent_dominant_emotion"] is None
    assert body["active_goals"] == []


@pytest.mark.asyncio
async def test_recommendations_react_to_emotion_and_goal(client):
    """Recent 'anger' + goal 'manage_anger' should surface anger-targeted exercises."""
    h = await _register(client, "w-rec@example.com")

    # Seed a recent emotion event via /emotion/text (StubEmotionAnalyzer maps
    # keywords to emotions — 'angry' -> anger).
    er = await client.post(
        "/emotion/text",
        headers=h,
        json={"text": "I feel so angry right now", "source": "adhoc"},
    )
    assert er.status_code == 200

    await client.post("/wellness/goals", headers=h, json={"kind": "manage_anger"})

    r = await client.get("/wellness/recommendations?limit=5", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["recent_dominant_emotion"] == "anger"
    assert "manage_anger" in body["active_goals"]

    top = body["items"][0]
    top_slug = top["exercise"]["slug"]
    # Any exercise that targets anger + a manage_anger goal should be near the top.
    assert top_slug in {
        "physiological-sigh",
        "box-breathing-4-4-4-4",
        "name-it-to-tame-it",
        "gentle-stretch-2min",
        "self-compassion-break",
    }
    assert top["score"] > 1.0
    joined = " ".join(top["reasons"]).lower()
    assert "anger" in joined or "manage_anger" in joined


@pytest.mark.asyncio
async def test_recommendation_penalizes_recent_use(client):
    """A just-completed exercise gets down-weighted vs alternatives."""
    h = await _register(client, "w-rec-fresh@example.com")
    await client.post(
        "/emotion/text",
        headers=h,
        json={"text": "I feel so angry right now", "source": "adhoc"},
    )
    await client.post("/wellness/goals", headers=h, json={"kind": "manage_anger"})

    baseline = await client.get("/wellness/recommendations?limit=5", headers=h)
    top_slug = baseline.json()["items"][0]["exercise"]["slug"]
    top_score = baseline.json()["items"][0]["score"]

    # Start the top exercise -> it should drop in the next ranking.
    await client.post(
        "/wellness/sessions", headers=h, json={"exercise_slug": top_slug}
    )
    after = await client.get("/wellness/recommendations?limit=5", headers=h)
    for it in after.json()["items"]:
        if it["exercise"]["slug"] == top_slug:
            assert it["score"] < top_score
            assert any("recent" in r.lower() for r in it["reasons"])
            break
    else:
        pytest.fail("expected the previously-top exercise to still be listed")
