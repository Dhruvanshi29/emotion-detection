"""Text emotion analysis tests."""
from __future__ import annotations

import pytest


async def _auth(client, email="emo@example.com") -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "E"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_emotion_text_requires_auth(client):
    r = await client.post("/emotion/text", json={"text": "hi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_analyze_text_returns_structured_result(client):
    headers = await _auth(client, "e1@example.com")
    r = await client.post(
        "/emotion/text",
        headers=headers,
        json={"text": "I feel so happy and grateful today"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_id"]
    assert body["dominant_emotion"] == "joy"
    assert body["sentiment"] == "positive"
    assert 0.0 <= body["confidence"] <= 1.0
    assert set(body["scores"].keys()) == {
        "joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral"
    }
    assert body["provider"] == "stub"


@pytest.mark.asyncio
async def test_list_events_scoped_to_user(client):
    h1 = await _auth(client, "u1@example.com")
    h2 = await _auth(client, "u2@example.com")

    await client.post("/emotion/text", headers=h1, json={"text": "I feel sad and lonely"})
    await client.post("/emotion/text", headers=h1, json={"text": "I'm so happy!"})
    await client.post("/emotion/text", headers=h2, json={"text": "Feeling angry"})

    r1 = await client.get("/emotion/events", headers=h1)
    assert r1.status_code == 200
    e1 = r1.json()
    assert len(e1) == 2
    dominants = {ev["dominant_emotion"] for ev in e1}
    assert dominants == {"joy", "sadness"}
    for ev in e1:
        assert len(ev["scores"]) == 7

    r2 = await client.get("/emotion/events", headers=h2)
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["dominant_emotion"] == "anger"


@pytest.mark.asyncio
async def test_events_filter_by_source(client):
    headers = await _auth(client, "src@example.com")
    await client.post(
        "/emotion/text",
        headers=headers,
        json={"text": "I feel happy", "source": "journal"},
    )
    await client.post(
        "/emotion/text",
        headers=headers,
        json={"text": "I feel sad", "source": "adhoc"},
    )
    r = await client.get("/emotion/events?source=journal", headers=headers)
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    assert events[0]["source"] == "journal"


@pytest.mark.asyncio
async def test_chat_message_triggers_emotion_analysis(client):
    headers = await _auth(client, "chatemo@example.com")
    r = await client.post(
        "/chat/message",
        headers=headers,
        json={"content": "I feel really sad and lonely today"},
    )
    assert r.status_code == 200
    user_msg_id = r.json()["user_message_id"]

    # Background task should have finished by now (AsyncClient awaits it).
    ev = await client.get(f"/chat/../emotion/message/{user_msg_id}", headers=headers)
    # The URL above resolves oddly on some routers; use the direct one.
    ev = await client.get(f"/emotion/message/{user_msg_id}", headers=headers)
    assert ev.status_code == 200
    body = ev.json()
    assert body is not None
    assert body["source"] == "chat"
    assert body["source_ref_id"] == user_msg_id
    assert body["dominant_emotion"] == "sadness"


@pytest.mark.asyncio
async def test_lexicon_fallback_direct():
    from app.services.emotion.text import _lexicon_analyze

    res = _lexicon_analyze("I feel so happy and grateful today")
    assert res.dominant_emotion == "joy"
    assert res.sentiment == "positive"
    assert res.provider == "lexicon"
    assert abs(sum(res.scores.values()) - 1.0) < 1e-6

    res2 = _lexicon_analyze("I feel scared and anxious about everything")
    assert res2.dominant_emotion == "fear"
    assert res2.sentiment == "negative"

    res3 = _lexicon_analyze("The sky is blue.")
    # No lexicon hits -> neutral
    assert res3.dominant_emotion == "neutral"


@pytest.mark.asyncio
async def test_extract_json_handles_code_fences():
    from app.services.emotion.text import _extract_json

    payload = (
        "Here you go:\n```json\n"
        '{"dominant_emotion":"joy","sentiment":"positive","confidence":0.9,'
        '"scores":{"joy":0.9,"sadness":0,"anger":0,"fear":0,"surprise":0.05,'
        '"disgust":0,"neutral":0.05},"signals":["upbeat tone"]}\n```'
    )
    obj = _extract_json(payload)
    assert obj is not None
    assert obj["dominant_emotion"] == "joy"
    assert obj["scores"]["joy"] == 0.9
