"""Facial analysis (Phase 6) tests — browser-derived signals only."""
from __future__ import annotations

import pytest


async def _register(client, email: str, *, camera_consent: bool) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "F"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if camera_consent:
        await client.patch(
            "/users/me", headers=headers, json={"camera_consent": True}
        )
    return headers


def _submission(**overrides) -> dict:
    body = {
        "source": "adhoc",
        "sample_count": 24,
        "duration_seconds": 12.0,
        "faces_detected_ratio": 0.85,
        "scores": {
            "joy": 0.55,
            "sadness": 0.05,
            "anger": 0.03,
            "fear": 0.05,
            "surprise": 0.1,
            "disgust": 0.02,
            "neutral": 0.2,
        },
        "signals": ["frequent-smile", "steady-gaze"],
        "model_provider": "browser-heuristic",
        "model_name": "browser-v0",
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_video_requires_auth(client):
    r = await client.post("/emotion/video", json=_submission())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_video_requires_camera_consent(client):
    h = await _register(client, "nocam@example.com", camera_consent=False)
    r = await client.post("/emotion/video", headers=h, json=_submission())
    assert r.status_code == 403
    assert "camera" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_video_submission_end_to_end(client):
    h = await _register(client, "face@example.com", camera_consent=True)
    r = await client.post("/emotion/video", headers=h, json=_submission())
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["facial_analysis_id"]
    assert body["emotion_event_id"]
    assert body["dominant_emotion"] == "joy"
    assert body["sentiment"] == "positive"
    assert 0.0 <= body["confidence"] <= 1.0
    assert set(body["scores"].keys()) == {
        "joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral"
    }
    # Server re-normalizes scores so they sum ~1.
    total = sum(body["scores"].values())
    assert 0.99 <= total <= 1.01
    assert body["sample_count"] == 24
    assert body["faces_detected_ratio"] == 0.85
    assert body["signals"] == ["frequent-smile", "steady-gaze"]

    # An emotion_event row with source="face" now exists.
    events = await client.get("/emotion/events?source=face", headers=h)
    assert events.status_code == 200
    ev = events.json()
    assert len(ev) == 1
    assert ev[0]["source"] == "face"
    assert ev[0]["dominant_emotion"] == "joy"
    assert ev[0]["id"] == body["emotion_event_id"]


@pytest.mark.asyncio
async def test_video_score_validation(client):
    h = await _register(client, "badscores@example.com", camera_consent=True)

    r = await client.post("/emotion/video", headers=h, json=_submission(scores={}))
    assert r.status_code == 422

    r = await client.post(
        "/emotion/video",
        headers=h,
        json=_submission(scores={"joy": 0.5, "bogus": 0.5}),
    )
    assert r.status_code == 422

    r = await client.post(
        "/emotion/video",
        headers=h,
        json=_submission(scores={"joy": 1.5}),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_video_server_ignores_client_labels(client):
    """Client cannot claim a label that contradicts its own score distribution."""
    h = await _register(client, "spoof@example.com", camera_consent=True)
    # Client sends a sadness-dominant distribution but its "signals" say joy —
    # we still re-derive from scores.
    body = _submission(
        signals=["client-claims-joy"],
        scores={
            "joy": 0.1,
            "sadness": 0.6,
            "anger": 0.05,
            "fear": 0.05,
            "surprise": 0.05,
            "disgust": 0.05,
            "neutral": 0.1,
        },
    )
    r = await client.post("/emotion/video", headers=h, json=body)
    assert r.status_code == 200
    assert r.json()["dominant_emotion"] == "sadness"
    assert r.json()["sentiment"] == "negative"


@pytest.mark.asyncio
async def test_get_and_list_facial_analysis(client):
    h = await _register(client, "fget@example.com", camera_consent=True)
    r = await client.post("/emotion/video", headers=h, json=_submission())
    fid = r.json()["facial_analysis_id"]

    g = await client.get(f"/emotion/face/{fid}", headers=h)
    assert g.status_code == 200
    assert g.json()["dominant_emotion"] == "joy"

    lst = await client.get("/emotion/face", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()) == 1


@pytest.mark.asyncio
async def test_facial_ownership_isolation(client):
    h1 = await _register(client, "fown1@example.com", camera_consent=True)
    h2 = await _register(client, "fown2@example.com", camera_consent=True)
    r = await client.post("/emotion/video", headers=h1, json=_submission())
    fid = r.json()["facial_analysis_id"]

    g = await client.get(f"/emotion/face/{fid}", headers=h2)
    assert g.status_code == 404
    lst = await client.get("/emotion/face", headers=h2)
    assert lst.json() == []


@pytest.mark.asyncio
async def test_video_rejects_raw_frame_payload(client):
    """Sanity: adding an unknown 'frames' field is silently dropped; core
    contract stays derived-signals-only."""
    h = await _register(client, "frames@example.com", camera_consent=True)
    payload = _submission()
    payload["frames"] = ["data:image/png;base64,AAA="]  # nope
    r = await client.post("/emotion/video", headers=h, json=payload)
    assert r.status_code == 200
    # The unknown field must NOT round-trip in response.
    assert "frames" not in r.json()
