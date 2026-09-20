"""Best-effort acoustic feature extraction (plan §7).

- WAV (PCM): compute energy_rms, pause_ratio, and duration from the raw
  samples using stdlib only (no ffmpeg/librosa needed).
- Any other container (webm, mp3, m4a, etc.): return duration from STT
  segments if provided; leave acoustic fields None.

Pitch (F0) is intentionally NOT computed here — reliable pitch tracking
needs a numerical DSP stack. Marking it as future work per plan §7.
Raw audio bytes are consumed here and MUST NOT be persisted (§18).
"""
from __future__ import annotations

import io
import logging
import math
import struct
import wave
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AcousticFeatures:
    features_available: bool
    duration_seconds: Optional[float] = None
    energy_rms: Optional[float] = None
    pause_ratio: Optional[float] = None
    # Frames scanned during analysis — useful for debugging without leaking audio.
    frame_count: Optional[int] = None


def extract_features(
    audio: bytes,
    *,
    content_type: str,
    stt_duration: Optional[float] = None,
) -> AcousticFeatures:
    ct = (content_type or "").lower()
    is_wav = ct.startswith("audio/wav") or ct.startswith("audio/x-wav") or ct.startswith(
        "audio/wave"
    )
    if not is_wav:
        # Sniff RIFF header as a fallback (browsers sometimes send audio/webm even
        # when the encoded content is actually a WAV).
        is_wav = len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"

    if not is_wav:
        return AcousticFeatures(
            features_available=False, duration_seconds=stt_duration
        )

    try:
        return _analyze_wav(audio)
    except (wave.Error, EOFError, struct.error, ValueError) as e:
        logger.warning("acoustic: WAV analysis failed: %s", e)
        return AcousticFeatures(
            features_available=False, duration_seconds=stt_duration
        )


def _analyze_wav(audio: bytes) -> AcousticFeatures:
    with wave.open(io.BytesIO(audio), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if n_frames == 0 or framerate == 0 or sampwidth not in (1, 2, 4):
        return AcousticFeatures(features_available=False)

    duration = n_frames / float(framerate)

    if sampwidth == 1:
        # 8-bit PCM is unsigned in WAV.
        samples = [(b - 128) / 128.0 for b in raw]
        max_amp = 1.0
    elif sampwidth == 2:
        n = len(raw) // 2
        ints = struct.unpack("<" + "h" * n, raw[: n * 2])
        max_amp = 32768.0
        samples = [x / max_amp for x in ints]
    else:  # sampwidth == 4
        n = len(raw) // 4
        ints = struct.unpack("<" + "i" * n, raw[: n * 4])
        max_amp = float(1 << 31)
        samples = [x / max_amp for x in ints]

    if n_channels > 1:
        # Downmix to mono by averaging channels.
        merged = []
        for i in range(0, len(samples), n_channels):
            group = samples[i : i + n_channels]
            merged.append(sum(group) / len(group))
        samples = merged

    if not samples:
        return AcousticFeatures(features_available=False, duration_seconds=duration)

    total_sq = 0.0
    for s in samples:
        total_sq += s * s
    rms = math.sqrt(total_sq / len(samples))

    # Frame the signal (~30 ms) and count low-energy frames as pauses.
    frame_len = max(1, int(framerate * 0.03))
    frames_scanned = 0
    pause_frames = 0
    # A pause threshold at 20% of RMS works reasonably across gain levels; if the
    # audio is silence RMS will be ~0 and we skip the ratio.
    threshold = max(rms * 0.2, 1e-4)
    for start in range(0, len(samples), frame_len):
        chunk = samples[start : start + frame_len]
        if not chunk:
            continue
        frames_scanned += 1
        sq = 0.0
        for s in chunk:
            sq += s * s
        frame_rms = math.sqrt(sq / len(chunk))
        if frame_rms < threshold:
            pause_frames += 1

    pause_ratio: Optional[float] = None
    if rms > 1e-4 and frames_scanned > 0:
        pause_ratio = pause_frames / frames_scanned

    return AcousticFeatures(
        features_available=True,
        duration_seconds=duration,
        energy_rms=rms,
        pause_ratio=pause_ratio,
        frame_count=frames_scanned,
    )
