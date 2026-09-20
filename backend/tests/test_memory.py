"""Memory service + API (Phase 11).

Retrieval assertions rely on the deterministic HashEmbedder — same input →
same vector, so cosine similarity is stable across runs.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.chat import Conversation, Message
from app.models.user import User
from app.services.embeddings import HashEmbedder, cosine
from app.services.memory_service import extract_candidates


async def _register(client, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "M"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user_id(sess: AsyncSession, email: str) -> str:
    row = (await sess.execute(select(User).where(User.email == email))).scalar_one()
    return row.id


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_hash_embedder_is_deterministic_and_normalized():
    e = HashEmbedder(dims=128)
    v1 = e.embed(["I love hiking in the mountains"])[0]
    v2 = e.embed(["I love hiking in the mountains"])[0]
    assert v1 == v2
    # Unit vector.
    assert 0.98 < sum(x * x for x in v1) ** 0.5 < 1.02


def test_hash_embedder_similarity_ordering():
    e = HashEmbedder(dims=256)
    q = e.embed(["running practice for anxiety relief"])[0]
    a = e.embed(["running helps my anxiety"])[0]
    b = e.embed(["I bake sourdough on weekends"])[0]
    assert cosine(q, a) > cosine(q, b)
    assert cosine(q, a) > 0
    # Empty vs anything is 0.
    assert cosine([], a) == 0.0


def test_extract_candidates_from_natural_text():
    text = (
        "So I love hiking on weekends. I want to sleep better. "
        "I'm a graphic designer. My goal is to journal every day. "
        "Also I dislike loud open offices."
    )
    cands = extract_candidates(text)
    kinds = {c.kind for c in cands}
    assert "preference" in kinds
    assert "goal" in kinds
    assert "fact" in kinds
    goals = [c for c in cands if c.kind == "goal"]
    assert any("sleep" in c.content.lower() for c in goals)
    assert any("journal" in c.content.lower() for c in goals)
    prefs = [c for c in cands if c.kind == "preference"]
    assert any("hiking" in c.content.lower() for c in prefs)


def test_extract_candidates_deduplicates():
    text = "I love hiking. I love hiking. I love hiking so much."
    cands = extract_candidates(text)
    # Same body ("hiking") should not produce more than one preference entry.
    prefs = [c for c in cands if "hiking" in c.content.lower()]
    assert len(prefs) == 1


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_requires_auth(client):
    r = await client.get("/memory")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_crud_flow(client):
    h = await _register(client, "mem-crud@example.com")

    r = await client.post(
        "/memory",
        headers=h,
        json={
            "kind": "preference",
            "title": "Loves hiking",
            "content": "User enjoys weekend hikes and mountain trails.",
            "tags": ["hobby", "outdoors"],
            "importance": 0.7,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    mid = body["id"]
    assert body["title"] == "Loves hiking"
    assert body["tags"] == ["hobby", "outdoors"]
    assert body["embedding_model"] == "hash-v1"

    got = await client.get(f"/memory/{mid}", headers=h)
    assert got.status_code == 200

    patched = await client.patch(
        f"/memory/{mid}",
        headers=h,
        json={"pinned": True, "content": "User loves mountains and forest walks."},
    )
    assert patched.status_code == 200
    assert patched.json()["pinned"] is True

    lst = await client.get("/memory", headers=h)
    assert lst.status_code == 200
    assert lst.json()["total"] == 1

    dele = await client.delete(f"/memory/{mid}", headers=h)
    assert dele.status_code == 204

    empty = await client.get("/memory", headers=h)
    assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_create_validation(client):
    h = await _register(client, "mem-val@example.com")
    bad_kind = await client.post(
        "/memory",
        headers=h,
        json={"kind": "nonsense", "title": "x", "content": "y"},
    )
    assert bad_kind.status_code == 422

    empty_title = await client.post(
        "/memory", headers=h, json={"title": "", "content": "y"}
    )
    assert empty_title.status_code == 422

    bad_importance = await client.post(
        "/memory",
        headers=h,
        json={"title": "ok", "content": "y", "importance": 2.5},
    )
    assert bad_importance.status_code == 422


@pytest.mark.asyncio
async def test_search_ranks_pinned_and_keyword_matches_first(client):
    h = await _register(client, "mem-search@example.com")
    # Distractors
    await client.post(
        "/memory",
        headers=h,
        json={
            "kind": "fact",
            "title": "Works remotely",
            "content": "User works from home in a small studio.",
        },
    )
    await client.post(
        "/memory",
        headers=h,
        json={
            "kind": "preference",
            "title": "Likes coffee",
            "content": "Drinks two espressos a day.",
        },
    )
    # Target
    tgt = await client.post(
        "/memory",
        headers=h,
        json={
            "kind": "goal",
            "title": "Better sleep",
            "content": "Wants to improve sleep quality with a wind-down routine.",
            "pinned": True,
            "importance": 0.9,
        },
    )
    tid = tgt.json()["id"]

    res = await client.post(
        "/memory/search",
        headers=h,
        json={"query": "sleep routine", "k": 3},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["hits"], "expected at least one hit"
    top = body["hits"][0]
    assert top["memory"]["id"] == tid
    assert "pinned" in top["reasons"]
    assert top["score"] > 0


@pytest.mark.asyncio
async def test_search_filters_by_kind(client):
    h = await _register(client, "mem-kind@example.com")
    await client.post(
        "/memory",
        headers=h,
        json={"kind": "preference", "title": "A", "content": "loves running"},
    )
    await client.post(
        "/memory",
        headers=h,
        json={"kind": "goal", "title": "B", "content": "wants to run a 5k"},
    )
    res = await client.post(
        "/memory/search",
        headers=h,
        json={"query": "run", "k": 5, "kinds": ["goal"]},
    )
    assert res.status_code == 200
    for h_ in res.json()["hits"]:
        assert h_["memory"]["kind"] == "goal"


@pytest.mark.asyncio
async def test_extract_endpoint(client):
    h = await _register(client, "mem-extract@example.com")
    r = await client.post(
        "/memory/extract",
        headers=h,
        json={
            "text": "I love long walks. My goal is to journal 3 times a week.",
            "source": "chat",
        },
    )
    assert r.status_code == 200
    body = r.json()
    kinds = {c["kind"] for c in body["candidates"]}
    assert "preference" in kinds
    assert "goal" in kinds


@pytest.mark.asyncio
async def test_delete_all_memories(client):
    h = await _register(client, "mem-nuke@example.com")
    for i in range(3):
        await client.post(
            "/memory",
            headers=h,
            json={"title": f"m{i}", "content": f"content {i}"},
        )
    lst = await client.get("/memory", headers=h)
    assert lst.json()["total"] == 3

    dele = await client.delete("/memory", headers=h)
    assert dele.status_code == 200
    assert dele.json()["deleted"] == 3

    empty = await client.get("/memory", headers=h)
    assert empty.json()["total"] == 0


@pytest.mark.asyncio
async def test_summarize_conversation(client, test_engine):
    email = "mem-sum@example.com"
    h = await _register(client, email)
    Session = async_sessionmaker(
        test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with Session() as db:
        uid = await _user_id(db, email)
        conv = Conversation(user_id=uid, title="Anxious about the interview")
        db.add(conv)
        await db.flush()
        db.add(
            Message(
                conversation_id=conv.id,
                role="user",
                content="I have a job interview tomorrow and I'm anxious.",
            )
        )
        db.add(
            Message(
                conversation_id=conv.id,
                role="assistant",
                content="That sounds stressful. What's on your mind about it?",
            )
        )
        db.add(
            Message(
                conversation_id=conv.id,
                role="user",
                content="I keep worrying I'll blank on a question.",
            )
        )
        db.add(
            Message(
                conversation_id=conv.id,
                role="assistant",
                content="A short breathing exercise before you go in can help.",
            )
        )
        await db.commit()
        cid = conv.id

    made = await client.post(f"/memory/summaries/{cid}", headers=h)
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["message_count"] == 4
    assert body["provider"] == "extractive"
    assert body["summary"]
    assert body["key_points"] and len(body["key_points"]) >= 2

    got = await client.get(f"/memory/summaries/{cid}", headers=h)
    assert got.status_code == 200
    assert got.json()["id"] == body["id"]

    # Re-summarize is idempotent (same conversation → one row updated).
    again = await client.post(f"/memory/summaries/{cid}", headers=h)
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]


@pytest.mark.asyncio
async def test_summarize_missing_conversation(client):
    h = await _register(client, "mem-sum-404@example.com")
    r = await client.post(
        "/memory/summaries/00000000-0000-0000-0000-000000000000", headers=h
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_memory_user_isolation(client):
    ha = await _register(client, "mem-iso-a@example.com")
    hb = await _register(client, "mem-iso-b@example.com")
    created = await client.post(
        "/memory",
        headers=ha,
        json={"title": "Only mine", "content": "private note"},
    )
    mid = created.json()["id"]

    # B cannot see, patch, or delete A's memory.
    assert (await client.get(f"/memory/{mid}", headers=hb)).status_code == 404
    assert (
        await client.patch(
            f"/memory/{mid}", headers=hb, json={"pinned": True}
        )
    ).status_code == 404
    assert (await client.delete(f"/memory/{mid}", headers=hb)).status_code == 404

    lst_b = await client.get("/memory", headers=hb)
    assert lst_b.json()["total"] == 0
