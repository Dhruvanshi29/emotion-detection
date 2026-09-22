"""Idempotency-Key support (Phase 15 P1 §5.3).

Clients that send an ``Idempotency-Key`` header on POST /chat/message or
POST /journal will get the previously stored response for that (user, method,
path, key) tuple. Prevents duplicate writes on retry.

Storage uses Redis when ``REDIS_URL`` is configured, allowing multiple web
replicas to share replays. Development and transient Redis outages fall back
to a bounded process-local store.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


log = logging.getLogger("app.idempotency")

_HEADER = "idempotency-key"
_MAX_KEY_LEN = 200
_METHODS = frozenset({"POST", "PUT", "PATCH"})
_ELIGIBLE_PREFIXES = ("/chat/message", "/journal")


class _InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        row = self._data.get(key)
        if not row:
            return None
        exp, payload = row
        if exp < time.time():
            self._data.pop(key, None)
            return None
        return payload

    async def set(self, key: str, payload: dict[str, Any], ttl: int) -> None:
        # Opportunistic sweep so the dict doesn't grow forever in dev.
        if len(self._data) > 1024:
            now = time.time()
            for k, (exp, _) in list(self._data.items()):
                if exp < now:
                    self._data.pop(k, None)
        self._data[key] = (time.time() + ttl, payload)


_STORE = _InMemoryStore()


class _RedisStore:
    """Shared idempotency store with a safe local fallback for outages."""

    def __init__(self, url: str) -> None:
        from redis.asyncio import from_url

        self.client = from_url(url, decode_responses=True)
        self.fallback = _InMemoryStore()

    @staticmethod
    def _key(key: str) -> str:
        return "saaya:idempotency:" + hashlib.sha256(key.encode("utf-8")).hexdigest()

    async def get(self, key: str) -> Optional[dict[str, Any]]:
        try:
            raw = await self.client.get(self._key(key))
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            log.warning("redis idempotency read failed; using local fallback (%s)", type(exc).__name__)
            return await self.fallback.get(key)

    async def set(self, key: str, payload: dict[str, Any], ttl: int) -> None:
        try:
            await self.client.set(self._key(key), json.dumps(payload), ex=ttl)
        except Exception as exc:  # noqa: BLE001
            log.warning("redis idempotency write failed; using local fallback (%s)", type(exc).__name__)
            await self.fallback.set(key, payload, ttl)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, ttl_seconds: int, redis_url: str = "") -> None:
        super().__init__(app)
        self.ttl = int(ttl_seconds)
        self.store = _RedisStore(redis_url) if redis_url else _STORE

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method not in _METHODS:
            return await call_next(request)
        if not any(request.url.path.startswith(p) for p in _ELIGIBLE_PREFIXES):
            return await call_next(request)
        raw_key = request.headers.get(_HEADER, "").strip()
        if not raw_key or len(raw_key) > _MAX_KEY_LEN or not raw_key.isascii():
            return await call_next(request)

        # Bind key to a one-way token fingerprint so users cannot collide and
        # bearer credentials are never retained in the cache.
        auth = request.headers.get("authorization", "")
        auth_fingerprint = hashlib.sha256(auth.encode("utf-8")).hexdigest()
        body_hash = hashlib.sha256(await request.body()).hexdigest()
        cache_key = (
            f"{auth_fingerprint}|{request.method}|{request.url.path}|{raw_key}"
        )
        cached = await self.store.get(cache_key)
        if cached is not None:
            if cached.get("request_hash") != body_hash:
                return JSONResponse(
                    content={
                        "detail": (
                            "Idempotency-Key was already used with a different "
                            "request body"
                        )
                    },
                    status_code=409,
                )
            response = JSONResponse(
                content=cached["body"],
                status_code=cached["status"],
            )
            response.headers["Idempotent-Replay"] = "true"
            return response

        response = await call_next(request)
        # Only cache successful writes with a JSON body.
        if 200 <= response.status_code < 300:
            body_bytes = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body_bytes += chunk
            try:
                body_json = json.loads(body_bytes.decode("utf-8"))
            except Exception:  # noqa: BLE001
                body_json = None
            if body_json is not None:
                await self.store.set(
                    cache_key,
                    {
                        "status": response.status_code,
                        "body": body_json,
                        "request_hash": body_hash,
                    },
                    ttl=self.ttl,
                )
            # Rebuild the response since we consumed the iterator.
            new = Response(
                content=body_bytes,
                status_code=response.status_code,
                media_type=response.media_type,
            )
            for k, v in response.headers.items():
                if k.lower() not in ("content-length",):
                    new.headers[k] = v
            return new
        return response
