"""Chat conversation + safety tests."""
from __future__ import annotations

import pytest


async def _auth(client, email="chat@example.com") -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "C"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_message_requires_auth(client):
    r = await client.post("/chat/message", json={"content": "hi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_message_creates_conversation_and_reply(client):
    headers = await _auth(client, "conv1@example.com")
    r = await client.post(
        "/chat/message", headers=headers, json={"content": "I'm feeling stressed today"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_id"]
    assert body["assistant_message_id"]
    assert body["risk_level"] == "low"  # "stressed" -> low
    assert "[stub reply]" in body["text"]
    assert body["provider"] == "stub"


@pytest.mark.asyncio
async def test_history_is_sent_to_llm(client):
    headers = await _auth(client, "hist@example.com")
    r1 = await client.post(
        "/chat/message",
        headers=headers,
        json={"content": "Hi, my name is River"},
    )
    conv_id = r1.json()["conversation_id"]

    r2 = await client.post(
        "/chat/message",
        headers=headers,
        json={"conversation_id": conv_id, "content": "What did I just tell you?"},
    )
    assert r2.status_code == 200
    # The stub records the last prompt it received; the prior turn must be in it.
    stub = client.stub_llm  # type: ignore[attr-defined]
    roles = [m.role for m in stub.last_prompt]
    contents = [m.content for m in stub.last_prompt]
    assert roles[0] == "system"
    assert "River" in " ".join(contents)


@pytest.mark.asyncio
async def test_high_risk_skips_llm_and_returns_safe_copy(client):
    headers = await _auth(client, "hi@example.com")
    r = await client.post(
        "/chat/message",
        headers=headers,
        json={"content": "I want to kill myself"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["risk_level"] == "high"
    assert body["provider"] == "safety"
    assert "988" in body["text"] or "emergency" in body["text"].lower()


@pytest.mark.asyncio
async def test_list_and_get_conversation(client):
    headers = await _auth(client, "list@example.com")
    r1 = await client.post(
        "/chat/message", headers=headers, json={"content": "First chat message"}
    )
    conv_id = r1.json()["conversation_id"]

    r_list = await client.get("/chat/conversations", headers=headers)
    assert r_list.status_code == 200
    convs = r_list.json()
    assert any(c["id"] == conv_id for c in convs)
    assert convs[0]["title"] is not None

    r_get = await client.get(f"/chat/conversations/{conv_id}", headers=headers)
    assert r_get.status_code == 200
    conv = r_get.json()
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_update_and_delete_conversation(client):
    headers = await _auth(client, "upd@example.com")
    r1 = await client.post(
        "/chat/message", headers=headers, json={"content": "Something"}
    )
    conv_id = r1.json()["conversation_id"]

    r = await client.patch(
        f"/chat/conversations/{conv_id}",
        headers=headers,
        json={"title": "Renamed", "archived": True},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"
    assert r.json()["archived"] is True

    # Archived by default excluded from list
    r_list = await client.get("/chat/conversations", headers=headers)
    assert all(c["id"] != conv_id for c in r_list.json())

    # But visible with include_archived
    r_list2 = await client.get(
        "/chat/conversations?include_archived=true", headers=headers
    )
    assert any(c["id"] == conv_id for c in r_list2.json())

    r_del = await client.delete(f"/chat/conversations/{conv_id}", headers=headers)
    assert r_del.status_code == 204

    r_get = await client.get(f"/chat/conversations/{conv_id}", headers=headers)
    assert r_get.status_code == 404


@pytest.mark.asyncio
async def test_cannot_access_other_users_conversation(client):
    a_headers = await _auth(client, "a@example.com")
    b_headers = await _auth(client, "b@example.com")

    r = await client.post(
        "/chat/message", headers=a_headers, json={"content": "mine"}
    )
    conv_id = r.json()["conversation_id"]

    r_get = await client.get(
        f"/chat/conversations/{conv_id}", headers=b_headers
    )
    assert r_get.status_code == 404

    r_send = await client.post(
        "/chat/message",
        headers=b_headers,
        json={"conversation_id": conv_id, "content": "leak?"},
    )
    assert r_send.status_code == 404


@pytest.mark.asyncio
async def test_providers_endpoint_uses_stub(client):
    r = await client.get("/chat/providers")
    assert r.status_code == 200
    body = r.json()
    assert "stub" in body["available"]
