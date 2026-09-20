"""Audio content-signature (magic-byte) validation (§3.5).

We do NOT trust the browser-supplied ``Content-Type`` header or filename
extension. This module inspects the leading bytes of the upload and returns
a canonical audio MIME (e.g. ``audio/wav``) or ``None`` if unrecognized.

Recognized: WAV (RIFF), OGG/OPUS, WebM/Matroska, MP3 (ID3 or MPEG frame),
M4A/MP4 (`ftyp`), FLAC. That's the full set of formats the browser
MediaRecorder API produces + the common upload formats.
"""
from __future__ import annotations

from typing import Optional


def sniff_audio_mime(data: bytes) -> Optional[str]:
    if not data or len(data) < 4:
        return None

    head = data[:16]

    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        # EBML / Matroska container — used by WebM Opus recordings.
        return "audio/webm"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"ID3"):
        return "audio/mpeg"
    # MP3 without ID3 tag: MPEG audio frame sync (11 bits set).
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "audio/mpeg"
    # ISO Base Media File Format (MP4 / M4A): "....ftyp<brand>"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"M4A ", b"mp42", b"isom", b"iso2", b"mp41"):
            return "audio/mp4"
        return "audio/mp4"
    return None


ALLOWED_AUDIO_MIMES = frozenset(
    {"audio/wav", "audio/ogg", "audio/webm", "audio/mpeg", "audio/mp4", "audio/flac"}
)


def is_allowed_audio(data: bytes) -> tuple[bool, Optional[str]]:
    """Return ``(allowed, sniffed_mime)`` after magic-byte validation."""
    m = sniff_audio_mime(data)
    return (m in ALLOWED_AUDIO_MIMES if m else False), m
