"""Prometheus metrics (Phase 15 P1 §5.2).

Registers a small, curated set of counters/histograms. All metrics are no-ops
when the ``prometheus_client`` package is missing so the app still boots.

Exposed metrics:
    http_requests_total{method,path_template,status}
    http_request_duration_seconds{method,path_template}
    llm_provider_failures_total{provider}
    safety_high_risk_hits_total
    db_connection_errors_total
    auth_login_failures_total
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


log = logging.getLogger("app.metrics")


try:  # pragma: no cover - optional dep
    from prometheus_client import (  # type: ignore
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
    )

    _AVAILABLE = True
except Exception:  # noqa: BLE001
    _AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain"


class _Noop:
    def labels(self, *a: Any, **k: Any) -> "_Noop":
        return self

    def inc(self, *a: Any, **k: Any) -> None:
        return None

    def observe(self, *a: Any, **k: Any) -> None:
        return None


if _AVAILABLE:
    _REGISTRY = CollectorRegistry()
    http_requests_total = Counter(
        "http_requests_total",
        "HTTP requests processed",
        ["method", "path", "status"],
        registry=_REGISTRY,
    )
    http_request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        registry=_REGISTRY,
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    llm_provider_failures_total = Counter(
        "llm_provider_failures_total",
        "LLM provider errors by provider",
        ["provider"],
        registry=_REGISTRY,
    )
    safety_high_risk_hits_total = Counter(
        "safety_high_risk_hits_total",
        "Chat messages classified as high risk",
        registry=_REGISTRY,
    )
    db_connection_errors_total = Counter(
        "db_connection_errors_total",
        "DB connectivity errors observed by /ready or workers",
        registry=_REGISTRY,
    )
    auth_login_failures_total = Counter(
        "auth_login_failures_total",
        "Failed login attempts",
        registry=_REGISTRY,
    )
else:  # pragma: no cover
    _REGISTRY = None  # type: ignore[assignment]
    http_requests_total = _Noop()  # type: ignore[assignment]
    http_request_duration = _Noop()  # type: ignore[assignment]
    llm_provider_failures_total = _Noop()  # type: ignore[assignment]
    safety_high_risk_hits_total = _Noop()  # type: ignore[assignment]
    db_connection_errors_total = _Noop()  # type: ignore[assignment]
    auth_login_failures_total = _Noop()  # type: ignore[assignment]


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count + latency, using the route template as the label.

    We use the matched route so we don't blow up the metric cardinality with
    every unique path (e.g. /memory/{id}).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not _AVAILABLE:
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path) if route else request.url.path
        try:
            http_requests_total.labels(
                request.method, path, str(response.status_code)
            ).inc()
            http_request_duration.labels(request.method, path).observe(elapsed)
        except Exception:  # noqa: BLE001
            pass
        return response


def metrics_endpoint(bearer_token: str = "") -> Callable[[Request], Any]:
    """Factory returning a Starlette-compatible /metrics handler."""

    async def _handler(request: Request) -> Response:
        if not _AVAILABLE:
            return PlainTextResponse(
                "prometheus_client not installed", status_code=501
            )
        if bearer_token:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {bearer_token}":
                return PlainTextResponse("unauthorized", status_code=401)
        data = generate_latest(_REGISTRY)
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return _handler
