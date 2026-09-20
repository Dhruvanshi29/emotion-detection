"""Post-deploy smoke test (plan §20).

Run against a live deployment URL. Verifies:
  1. /health responds with the expected env + version
  2. /ready succeeds (DB reachable)
  3. /chat/providers returns at least one provider

Usage:
    python scripts/smoke.py                    # defaults to http://127.0.0.1:8000
    SMOKE_BASE=https://api.example.com python scripts/smoke.py

Exit code 0 = success, non-zero = failure (suitable for CI post-deploy gates).
"""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000").rstrip("/")
EXPECT_ENV = os.environ.get("SMOKE_EXPECT_ENV")  # optional guard
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "15"))


def _check(name: str, ok: bool, detail: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    line = f"[{marker}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if not ok:
        sys.exit(1)


def main() -> None:
    print(f"smoke: base={BASE}")
    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as c:
        # 1. /health
        r = c.get("/health")
        _check("GET /health status 200", r.status_code == 200, str(r.status_code))
        body = r.json()
        _check("/health has status=ok", body.get("status") == "ok", str(body))
        if EXPECT_ENV:
            _check(
                f"/health env={EXPECT_ENV}",
                body.get("env") == EXPECT_ENV,
                f"got {body.get('env')}",
            )
        print(f"       version={body.get('version')} commit={body.get('commit')}")

        # 2. /ready
        r = c.get("/ready")
        _check("GET /ready status 200", r.status_code == 200, r.text[:200])

        # 3. /chat/providers
        r = c.get("/chat/providers")
        _check("GET /chat/providers status 200", r.status_code == 200, str(r.status_code))
        payload = r.json()
        chain = payload.get("chain") if isinstance(payload, dict) else None
        available = payload.get("available") if isinstance(payload, dict) else None
        _check(
            "provider chain non-empty",
            isinstance(chain, list) and len(chain) > 0,
            f"chain={chain}",
        )
        _check(
            "at least one LLM provider available",
            isinstance(available, list) and len(available) > 0,
            f"available={available}",
        )

    print("smoke: OK")


if __name__ == "__main__":
    main()
