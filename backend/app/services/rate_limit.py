"""Sliding-window rate limiter (plan §12).

Two backends with the same ``check(bucket, *, limit, window_seconds)`` API:

* ``RateLimiter`` — in-process (default for dev / single-worker).
* ``RedisRateLimiter`` — shared across replicas via Redis sorted sets. Auto-
  selected when ``REDIS_URL`` is configured. Falls back to in-process on any
  connection error so a Redis outage never 500s user requests.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict, Optional, Tuple


log = logging.getLogger("app.rate_limit")


class RateLimiter:
    """Fixed-window-length sliding log. O(N) per check where N = limit."""

    def __init__(self) -> None:
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(
        self,
        bucket: str,
        *,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> Tuple[bool, float]:
        """Return (allowed, retry_after_seconds).

        `retry_after_seconds` is 0 when allowed.
        """
        if limit <= 0:
            return True, 0.0
        t = time.monotonic() if now is None else now
        cutoff = t - window_seconds
        with self._lock:
            q = self._buckets[bucket]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                # Time until the oldest entry falls out of the window.
                retry = q[0] + window_seconds - t
                return False, max(retry, 0.0)
            q.append(t)
            return True, 0.0

    def reset(self, bucket: str | None = None) -> None:
        with self._lock:
            if bucket is None:
                self._buckets.clear()
            else:
                self._buckets.pop(bucket, None)


class RedisRateLimiter:
    """Sliding-window limiter backed by Redis ZSET (one key per bucket)."""

    _KEY_PREFIX = "rl:"
    _CHECK_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local cutoff = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local member = ARGV[5]
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  redis.call('EXPIRE', key, ttl)
  return {0, oldest[2] or now}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return {1, 0}
"""

    def __init__(self, url: str) -> None:
        import redis  # type: ignore

        self._redis = redis.Redis.from_url(url, socket_timeout=1.0)
        self._fallback = RateLimiter()

    def check(
        self,
        bucket: str,
        *,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> Tuple[bool, float]:
        if limit <= 0:
            return True, 0.0
        t = time.time() if now is None else now
        key = self._KEY_PREFIX + bucket
        try:
            allowed, oldest = self._redis.eval(
                self._CHECK_SCRIPT,
                1,
                key,
                t,
                t - window_seconds,
                limit,
                int(window_seconds) + 1,
                f"{t}:{time.time_ns()}",
            )
        except Exception as e:  # noqa: BLE001
            # Never punish users for a Redis outage.
            log.warning("redis rate limit unavailable, falling back: %s", e)
            return self._fallback.check(
                bucket, limit=limit, window_seconds=window_seconds, now=now
            )
        if int(allowed) == 0:
            return False, max(float(oldest) + window_seconds - t, 0.0)
        return True, 0.0

    def reset(self, bucket: str | None = None) -> None:
        try:
            if bucket is None:
                for k in self._redis.scan_iter(self._KEY_PREFIX + "*"):
                    self._redis.delete(k)
            else:
                self._redis.delete(self._KEY_PREFIX + bucket)
        except Exception:  # noqa: BLE001
            pass
        self._fallback.reset(bucket)


_limiter: Optional[object] = None


def get_limiter():
    """Return the process-wide limiter, selecting Redis when configured."""
    global _limiter
    if _limiter is not None:
        return _limiter
    try:
        from app.core.config import get_settings

        url = get_settings().redis_url
    except Exception:  # noqa: BLE001
        url = ""
    if url:
        try:
            _limiter = RedisRateLimiter(url)
            log.info("rate limiter: redis backend (%s)", url.split("@")[-1])
            return _limiter
        except Exception as e:  # noqa: BLE001
            log.warning("rate limiter: redis unavailable, using in-process (%s)", e)
    _limiter = RateLimiter()
    return _limiter


def reset_limiter_for_tests() -> None:
    """Force re-selection of the backend (used by pytest fixtures)."""
    global _limiter
    _limiter = None
