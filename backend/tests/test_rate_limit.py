"""Tests for the in-memory sliding-window rate limiter (Phase 12)."""
from __future__ import annotations

from app.services.rate_limit import RateLimiter


def test_rate_limiter_allows_within_window() -> None:
    rl = RateLimiter()
    for i in range(5):
        allowed, retry = rl.check("u", limit=5, window_seconds=60, now=i * 0.1)
        assert allowed, f"iteration {i}"
        assert retry == 0.0


def test_rate_limiter_blocks_after_limit() -> None:
    rl = RateLimiter()
    for i in range(3):
        rl.check("u", limit=3, window_seconds=60, now=i)
    allowed, retry = rl.check("u", limit=3, window_seconds=60, now=3.5)
    assert allowed is False
    assert retry > 0


def test_rate_limiter_recovers_after_window() -> None:
    rl = RateLimiter()
    for i in range(3):
        rl.check("u", limit=3, window_seconds=10, now=i)
    # Fully outside the window — all three should have aged out.
    allowed, _ = rl.check("u", limit=3, window_seconds=10, now=100)
    assert allowed is True


def test_rate_limiter_separate_buckets() -> None:
    rl = RateLimiter()
    for i in range(3):
        rl.check("a", limit=3, window_seconds=60, now=i)
    # 'b' should still have its full budget.
    allowed, _ = rl.check("b", limit=3, window_seconds=60, now=3.5)
    assert allowed is True


def test_rate_limiter_reset() -> None:
    rl = RateLimiter()
    for i in range(3):
        rl.check("u", limit=3, window_seconds=60, now=i)
    rl.reset("u")
    allowed, _ = rl.check("u", limit=3, window_seconds=60, now=3.5)
    assert allowed is True


def test_rate_limiter_zero_limit_short_circuits() -> None:
    rl = RateLimiter()
    allowed, retry = rl.check("u", limit=0, window_seconds=60, now=1.0)
    assert allowed is True
    assert retry == 0.0
