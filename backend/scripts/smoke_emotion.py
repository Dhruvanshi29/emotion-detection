"""Phase-3 live smoke: hit /emotion/text against NVIDIA + Neon."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000")
EMAIL = f"smoke_emotion_{uuid.uuid4().hex[:6]}@example.com"
PW = "wellness123"


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=600) as c:
        r = await c.post(
            "/auth/register",
            json={"email": EMAIL, "password": PW, "display_name": "Smoke"},
        )
        assert r.status_code in (201, 400), r.text
        r = await c.post("/auth/login", json={"email": EMAIL, "password": PW})
        r.raise_for_status()
        token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        cases = [
            ("I'm feeling really down and lonely today", "sadness", "negative"),
            ("Just got promoted at work, feeling amazing!", "joy", "positive"),
            ("I'm so angry at how they treated me", "anger", "negative"),
        ]
        for text, exp_dom, exp_sent in cases:
            r = await c.post("/emotion/text", headers=h, json={"text": text})
            r.raise_for_status()
            body = r.json()
            print(json.dumps({"text": text, "result": body}, indent=2))
            print(
                f"  expected dominant~{exp_dom} sentiment~{exp_sent} :: "
                f"got dominant={body['dominant_emotion']} sentiment={body['sentiment']} "
                f"provider={body['provider']} model={body['model']}"
            )

        # Trigger a chat message and verify background emotion event linked
        r = await c.post(
            "/chat/message",
            headers=h,
            json={"content": "I feel a bit sad and tired today, honestly"},
        )
        r.raise_for_status()
        msg_id = r.json()["user_message_id"]
        print(f"chat user message: {msg_id}")

        # Poll for the background event
        for _ in range(20):
            await asyncio.sleep(1.0)
            e = await c.get(f"/emotion/message/{msg_id}", headers=h)
            e.raise_for_status()
            body = e.json()
            if body:
                print("linked emotion event:")
                print(json.dumps(body, indent=2, default=str))
                break
        else:
            print("no emotion event linked yet")
            return 1

        r = await c.get("/emotion/events", headers=h)
        r.raise_for_status()
        print(f"total events for user: {len(r.json())}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
