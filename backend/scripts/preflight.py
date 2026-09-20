"""Preflight environment check for production deploys (plan §19, Phase 14).

Fails fast (exit 1) if any required-for-production setting is missing or set
to a known-unsafe development default. Intended to run as the first step of a
CI post-deploy job — or locally with ``APP_ENV=production`` to dry-run.

Usage:
    python scripts/preflight.py

Checks:
  * DATABASE_URL is set and is NOT SQLite
  * JWT_SECRET / JWT_REFRESH_SECRET are set and NOT the dev defaults
  * CORS_ALLOWED_ORIGINS is non-empty
  * At least one LLM provider key is set
  * SENTRY_DSN is set (warning only, plan §14 recommends but does not require)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

# Allow running as `python scripts/preflight.py` from the backend/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


DEV_JWT_MARKERS = ("dev-only", "change-in-production")


def _fail(msg: str, errors: List[str]) -> None:
    errors.append(msg)


def _warn(msg: str, warnings: List[str]) -> None:
    warnings.append(msg)


def _check_provider_keys(s) -> Tuple[bool, str]:
    keys = {
        "groq": s.groq_api_key,
        "openrouter": s.openrouter_api_key,
        "nvidia": s.nvidia_api_key,
        "gemini": s.gemini_api_key,
    }
    set_keys = [name for name, v in keys.items() if v]
    return (len(set_keys) > 0, ", ".join(set_keys) if set_keys else "<none>")


def main() -> int:
    s = get_settings()
    errors: List[str] = []
    warnings: List[str] = []

    print(f"preflight: env={s.app_env} version={s.app_version}")

    if not s.is_production:
        print("preflight: APP_ENV is not 'production' — running in advisory mode.")

    # DATABASE_URL
    if not s.database_url:
        _fail("DATABASE_URL is empty", errors)
    elif s.database_url.startswith("sqlite"):
        if s.is_production:
            _fail(f"DATABASE_URL is SQLite in production ({s.database_url})", errors)
        else:
            _warn("DATABASE_URL is SQLite (fine for dev, not for prod)", warnings)

    # JWT secrets
    for name, val in (("JWT_SECRET", s.jwt_secret), ("JWT_REFRESH_SECRET", s.jwt_refresh_secret)):
        if not val:
            _fail(f"{name} is empty", errors)
        elif any(m in val for m in DEV_JWT_MARKERS):
            (_fail if s.is_production else _warn)(
                f"{name} still uses the dev default", errors if s.is_production else warnings
            )
        elif len(val) < 32:
            _fail(f"{name} is shorter than 32 chars (HS256 minimum recommended)", errors)

    # CORS
    if s.is_production and not s.cors_allowed_origins_list:
        _fail("CORS_ALLOWED_ORIGINS is empty (production blocks all origins)", errors)

    # LLM providers
    has_key, names = _check_provider_keys(s)
    if not has_key:
        _fail("No LLM provider key set (need at least one of groq/openrouter/nvidia/gemini)", errors)
    else:
        print(f"preflight: LLM providers with keys: {names}")

    # Sentry (warning only)
    if s.is_production and not s.sentry_dsn:
        _warn("SENTRY_DSN not set — error monitoring disabled", warnings)

    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[FAIL] {e}")

    if errors:
        print(f"preflight: FAILED ({len(errors)} error(s))")
        return 1
    print("preflight: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
