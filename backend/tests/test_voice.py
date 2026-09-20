"""Voice pipeline (STT + acoustic features + emotion) tests."""
from __future__ import annotations

import io
import math
import struct
import wave

import pytest


async def _register(client, email: str, *, mic_consent: bool) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "wellness123", "display_name": "V"},
    )
    r = await client.post(
        "/auth/login", json={"email": email, "password": "wellness123"}
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if mic_consent:
        await client.patch("/users/me", headers=headers, json={"mic_consent": True})
    return headers


def _make_wav(marker: bytes, *, seconds: float = 2.5, framerate: int = 16000) -> bytes:
    """Build a small mono 16-bit PCM WAV whose sample data contains `marker`.

    The stub STT dispatches on markers found anywhere in the audio bytes
    (SAD:/JOY:/ANGRY:/…). We prepend the marker as raw bytes into the data
    chunk, then follow with a real-looking signal so the WAV feature
    extractor has something meaningful to compute.
    """
    n_frames = int(framerate * seconds)
    body = bytearray(marker)  # marker lives in the sample data as-is

    # Alternate ~200 ms of tone with ~100 ms of silence so 30 ms framing
    # produces a mix of speech and pause frames.
    block = int(framerate * 0.2)   # 200 ms of signal
    gap = int(framerate * 0.1)     # 100 ms of silence
    i = 0
    while i < n_frames:
        for j in range(min(block, n_frames - i)):
            v = int(4000 * math.sin(2 * math.pi * 220.0 * (i + j) / framerate))
            body.extend(struct.pack("<h", v))
        i += block
        for _ in range(min(gap, max(0, n_frames - i))):
            body.extend(struct.pack("<h", 0))
        i += gap

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(bytes(body))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_audio_requires_auth(client):
    r = await client.post(
        "/emotion/audio",
        files={"file": ("x.wav", b"RIFF....WAVE", "audio/wav")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_audio_requires_mic_consent(client):
    h = await _register(client, "novoice@example.com", mic_consent=False)
    wav = _make_wav(b"JOY:")
    r = await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("x.wav", wav, "audio/wav")},
    )
    assert r.status_code == 403
    assert "consent" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_audio_pipeline_end_to_end(client):
    h = await _register(client, "voice@example.com", mic_consent=True)
    wav = _make_wav(b"SAD:", seconds=2.5)

    r = await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("clip.wav", wav, "audio/wav")},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["voice_analysis_id"]
    assert body["emotion_event_id"]
    assert "sad" in body["transcript"].lower()
    assert body["language"] == "en"
    assert body["stt_provider"] == "stub"

    # Acoustic features should be present for WAV input.
    assert body["features_available"] is True
    assert body["duration_seconds"] and body["duration_seconds"] > 1.0
    assert body["energy_rms"] is not None and body["energy_rms"] > 0
    # Every 10th frame is silent -> pause ratio > 0.
    assert body["pause_ratio"] is not None and body["pause_ratio"] > 0

    assert body["word_count"] and body["word_count"] > 0
    assert body["speech_rate_wpm"] and body["speech_rate_wpm"] > 0

    # Transcript emotion is stubbed: 'sad' -> sadness/negative.
    assert body["dominant_emotion"] == "sadness"
    assert body["sentiment"] == "negative"
    assert set(body["scores"].keys()) == {
        "joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral"
    }


@pytest.mark.asyncio
async def test_audio_appears_as_voice_source_in_events(client):
    h = await _register(client, "vevents@example.com", mic_consent=True)
    wav = _make_wav(b"JOY:")
    await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("clip.wav", wav, "audio/wav")},
        data={"source": "adhoc"},
    )
    events = await client.get("/emotion/events?source=voice", headers=h)
    assert events.status_code == 200
    body = events.json()
    assert len(body) == 1
    assert body[0]["source"] == "voice"
    assert body[0]["dominant_emotion"] == "joy"


@pytest.mark.asyncio
async def test_get_and_list_voice_analysis(client):
    h = await _register(client, "vget@example.com", mic_consent=True)
    wav = _make_wav(b"ANGRY:")
    r = await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("clip.wav", wav, "audio/wav")},
    )
    vid = r.json()["voice_analysis_id"]

    g = await client.get(f"/emotion/voice/{vid}", headers=h)
    assert g.status_code == 200
    assert g.json()["transcript"].lower().startswith("i am")

    lst = await client.get("/emotion/voice", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()) == 1


@pytest.mark.asyncio
async def test_voice_ownership_isolation(client):
    h1 = await _register(client, "vown1@example.com", mic_consent=True)
    h2 = await _register(client, "vown2@example.com", mic_consent=True)

    wav = _make_wav(b"JOY:")
    r = await client.post(
        "/emotion/audio",
        headers=h1,
        files={"file": ("clip.wav", wav, "audio/wav")},
    )
    vid = r.json()["voice_analysis_id"]

    g = await client.get(f"/emotion/voice/{vid}", headers=h2)
    assert g.status_code == 404

    lst2 = await client.get("/emotion/voice", headers=h2)
    assert lst2.json() == []


@pytest.mark.asyncio
async def test_empty_upload_rejected(client):
    h = await _register(client, "vempty@example.com", mic_consent=True)
    r = await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("clip.wav", b"", "audio/wav")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_size_limit_enforced(client, monkeypatch):
    h = await _register(client, "vbig@example.com", mic_consent=True)

    from app.core import config as cfg_mod
    settings = cfg_mod.get_settings()
    monkeypatch.setattr(settings, "voice_max_upload_bytes", 128)

    wav = _make_wav(b"JOY:", seconds=1.0)  # ~32 KB > 128 B cap
    r = await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("clip.wav", wav, "audio/wav")},
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_stt_providers_endpoint(client):
    h = await _register(client, "vprov@example.com", mic_consent=True)
    r = await client.get("/emotion/stt-providers", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["chain"] == ["stub"]
    assert body["available"] == ["stub"]


@pytest.mark.asyncio
async def test_non_wav_content_type_skips_features_gracefully(client):
    h = await _register(client, "vnowav@example.com", mic_consent=True)
    # Send bytes that sniff as WebM (EBML magic) so the content-signature
    # check (§3.5) passes; feature extractor should decline cleanly since
    # it only understands WAV.
    payload = b"\x1a\x45\xdf\xa3" + b"JOY:" + b"\x00" * 512
    r = await client.post(
        "/emotion/audio",
        headers=h,
        files={"file": ("clip.webm", payload, "audio/webm")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["features_available"] is False
    # But transcript-based emotion still worked.
    assert body["dominant_emotion"] == "joy"


@pytest.mark.asyncio
async def test_extract_features_direct_wav_and_nonwav():
    from app.services.audio.features import extract_features

    wav = _make_wav(b"", seconds=1.0)
    feat = extract_features(wav, content_type="audio/wav")
    assert feat.features_available is True
    assert feat.duration_seconds and feat.duration_seconds > 0.9
    assert feat.energy_rms is not None

    # Non-WAV falls back to stt_duration for duration and no acoustic fields.
    feat2 = extract_features(b"\x00" * 32, content_type="audio/webm", stt_duration=1.5)
    assert feat2.features_available is False
    assert feat2.duration_seconds == 1.5
    assert feat2.energy_rms is None
