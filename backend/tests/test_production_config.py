from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "database_url": (
            "postgresql+asyncpg://user:password@db.example.com/app?ssl=require"
        ),
        "cors_allowed_origins": "https://app.example.com",
        "jwt_secret": "a" * 48,
        "jwt_refresh_secret": "b" * 48,
        "auth_cookie_secure": True,
        "field_encryption_key": "11" * 32,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_production_settings_are_accepted():
    assert _production().is_production


def test_neon_libpq_url_is_normalized_for_asyncpg():
    settings = _production(
        database_url=(
            "postgresql://user:password@db-pooler.example.com/app"
            "?sslmode=require&channel_binding=require"
        )
    )
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert "ssl=require" in settings.database_url
    assert "sslmode" not in settings.database_url
    assert "channel_binding" not in settings.database_url


def test_production_worker_only_requires_database_settings():
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_role="worker",
        database_url=(
            "postgresql://user:password@db-pooler.example.com/app"
            "?sslmode=require&channel_binding=require"
        ),
        field_encryption_key="22" * 32,
    )
    assert settings.app_role == "worker"


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": "sqlite+aiosqlite:///./prod.db"},
        {"cors_allowed_origins": ""},
        {"cors_allowed_origins": "*"},
        {"cors_allowed_origins": "http://app.example.com"},
        {"jwt_secret": "dev-only-jwt-secret-change-in-production-please"},
        {"jwt_refresh_secret": "short"},
        {"jwt_refresh_secret": "a" * 48},
        {"jwt_algorithm": "none"},
        {"auth_cookie_secure": False},
        {"field_encryption_key": ""},
    ],
)
def test_unsafe_production_settings_are_rejected(overrides):
    with pytest.raises(ValidationError):
        _production(**overrides)
