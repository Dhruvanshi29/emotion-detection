"""Cross-cutting HTTP middleware (Phase 15 — Security & Testing Master Plan).

- ``RequestIDMiddleware`` — attaches an X-Request-ID for log correlation and
  echoes it back on the response (§10).
- ``BodySizeLimitMiddleware`` — enforces a hard cap on request body size
  before anything else parses it (§3.3, defense against oversize-JSON DoS).
- ``RedactingLogFilter`` — strips Authorization/Bearer tokens and refresh
  tokens out of log records (§3.6).
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import deque
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx


_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_INCOMING_REQUEST_ID_LEN = 128


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request/response.

    If the client sent one (bounded length, ASCII printable), reuse it; else
    generate a UUID4. The ID is stored on ``request.state.request_id`` so
    downstream handlers can log it.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(_REQUEST_ID_HEADER, "")
        if incoming and len(incoming) <= _MAX_INCOMING_REQUEST_ID_LEN and incoming.isascii():
            rid = incoming
        else:
            rid = str(uuid.uuid4())
        request.state.request_id = rid
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[_REQUEST_ID_HEADER] = rid
        return response


class BodySizeLimitMiddleware:
    """Reject requests whose ``Content-Length`` exceeds ``max_bytes``.

    Runs before Pydantic/JSON parsing, so a 20 MB POST is refused with 413
    without ever being buffered into memory. File-upload endpoints that
    legitimately need a larger cap can bypass this by declaring the route
    exempt (matched by prefix in ``exempt_prefixes``).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        exempt_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)
        self.exempt_prefixes = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        for pref in self.exempt_prefixes:
            if path.startswith(pref):
                await self.app(scope, receive, send)
                return

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get(b"content-length", b"")
        if content_length.isdigit() and int(content_length) > self.max_bytes:
            response = JSONResponse({"detail": "Request body too large."}, status_code=413)
            await response(scope, receive, send)
            return

        received = 0
        buffered: deque[Message] = deque()
        while True:
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    response = JSONResponse(
                        {"detail": "Request body too large."}, status_code=413
                    )
                    await response(scope, receive, send)
                    return
                buffered.append(message)
                if not message.get("more_body", False):
                    break
            else:
                buffered.append(message)
                break

        async def replay_receive() -> Message:
            if buffered:
                return buffered.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)


# --- Log redaction ---------------------------------------------------------

_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=\-]{6,}")
_AUTH_HEADER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)['\"]?[^\s'\",;}]+")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}")
_REFRESH_JSON_RE = re.compile(r'"refresh_token"\s*:\s*"[^"]{6,}"')
_PASSWORD_JSON_RE = re.compile(r'"password"\s*:\s*"[^"]{1,}"')


def redact_sensitive(text: str) -> str:
    if not text:
        return text
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", text)
    text = _JWT_RE.sub("[JWT_REDACTED]", text)
    text = _REFRESH_JSON_RE.sub('"refresh_token":"[REDACTED]"', text)
    text = _PASSWORD_JSON_RE.sub('"password":"[REDACTED]"', text)
    return text


class RedactingLogFilter(logging.Filter):
    """Redact bearer tokens, Authorization headers and JWTs from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        redacted = redact_sensitive(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def install_log_redaction() -> None:
    """Attach the redaction filter to the root logger and uvicorn loggers."""
    flt = RedactingLogFilter()
    logging.getLogger().addFilter(flt)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "app"):
        logging.getLogger(name).addFilter(flt)
