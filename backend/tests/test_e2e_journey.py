"""End-to-end user journey (Phase 13).

Walks a single user through the platform's primary surfaces: register, log in,
grant consent, chat, journal, complete a wellness exercise, schedule a
reminder, save a memory, view the dashboard, and export/delete their data.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_full_user_journey(client):
    email = "journey@example.com"
    password = "wellness123"

    # 1. Register + login
    r = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "J"},
    )
    assert r.status_code == 201

    r = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    h = {"Authorization": f"Bearer {tokens['access_token']}"}

    # 2. Look at own profile
    me = (await client.get("/users/me", headers=h)).json()
    assert me["email"] == email

    # 3. Grant consent for memory + data processing
    for kind in ("memory", "data_processing", "terms"):
        r = await client.post(
            "/consent",
            json={"kind": kind, "granted": True, "source": "signup"},
            headers=h,
        )
        assert r.status_code == 201

    # 4. Send a chat message
    r = await client.post(
        "/chat/message",
        json={"content": "I've been feeling stressed at work lately."},
        headers=h,
    )
    assert r.status_code == 200
    chat = r.json()
    assert chat["risk_level"] in ("low", "medium", "none")
    conv_id = chat["conversation_id"]

    r = await client.get("/chat/conversations", headers=h)
    assert r.status_code == 200
    assert any(c["id"] == conv_id for c in r.json())

    # 5. Write a journal entry
    r = await client.post(
        "/journal",
        json={
            "title": "Tuesday check-in",
            "content": "Deadline stress but a good walk after lunch helped.",
            "mood": 4,
        },
        headers=h,
    )
    assert r.status_code == 201

    # 6. Wellness: list catalog, start a session
    r = await client.get("/wellness/exercises", headers=h)
    assert r.status_code == 200
    exercises = r.json()
    assert exercises
    ex_slug = exercises[0]["slug"]
    r = await client.post(
        "/wellness/sessions",
        json={"exercise_slug": ex_slug},
        headers=h,
    )
    assert r.status_code == 201
    session_id = r.json()["id"]
    r = await client.patch(
        f"/wellness/sessions/{session_id}",
        json={"completed": True, "rating": 5, "notes": "helpful"},
        headers=h,
    )
    assert r.status_code == 200

    # 7. Create a reminder
    r = await client.post(
        "/reminders",
        json={
            "title": "Evening check-in",
            "kind": "chat_checkin",
            "recurrence": "daily",
            "time_of_day": "19:00",
            "timezone": "UTC",
        },
        headers=h,
    )
    assert r.status_code == 201

    # 8. Save + search a memory
    r = await client.post(
        "/memory",
        json={
            "kind": "preference",
            "title": "Walks help",
            "content": "Short lunchtime walks reset my mood.",
            "pinned": True,
        },
        headers=h,
    )
    assert r.status_code == 201

    r = await client.post(
        "/memory/search", json={"query": "walk", "k": 3}, headers=h
    )
    assert r.status_code == 200
    hits = r.json()["hits"]
    assert len(hits) >= 1
    assert "pinned" in hits[0]["reasons"]

    # 9. Dashboard summary reflects the activity above
    r = await client.get("/dashboard/summary", headers=h)
    assert r.status_code == 200
    summary = r.json()
    assert summary["total_chat_messages"] >= 1
    assert summary["total_journal_entries"] >= 1
    assert summary["total_wellness_sessions"] >= 1
    assert summary["active_reminders"] >= 1

    # 10. Audit log recorded consent + export intent
    r = await client.get("/audit", headers=h)
    assert r.status_code == 200
    actions = {i["action"] for i in r.json()["items"]}
    assert any(a.startswith("consent.") for a in actions)

    # 11. Export bundle then delete just the chat category
    r = await client.get("/privacy/export", headers=h)
    assert r.status_code == 200
    dump = r.json()
    assert dump["counts"]["memories"] >= 1
    assert dump["counts"]["journal_entries"] >= 1

    r = await client.delete("/privacy/data/chat", headers=h)
    assert r.status_code == 200
    assert (await client.get("/chat/conversations", headers=h)).json() == []
    # Journal untouched.
    assert len((await client.get("/journal", headers=h)).json()) >= 1

    # 12. Delete the account entirely and confirm the token is dead
    r = await client.request(
        "DELETE",
        "/privacy/account",
        json={"confirm": "DELETE"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["counts"]["memory"] >= 1

    r = await client.get("/users/me", headers=h)
    assert r.status_code == 401
