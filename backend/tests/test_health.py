"""Health endpoint sanity test."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    # Phase 14: /health now surfaces version + commit for deploy verification.
    assert "version" in body
    assert "env" in body
    assert "commit" in body


@pytest.mark.asyncio
async def test_ready(client):
    """Phase 14: /ready must succeed when the DB is reachable."""
    r = await client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ready"
    assert body.get("db") == "ok"
