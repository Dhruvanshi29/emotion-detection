from __future__ import annotations

from functools import lru_cache
import base64
from pathlib import Path
from typing import List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/.env  (independent of CWD)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    app_env: str = "development"
    app_role: str = "web"
    app_port: int = 8000
    log_level: str = "INFO"
    # Semantic version + commit SHA surfaced in /health for deploy verification.
    app_version: str = "0.1.0"
    git_sha: str = ""

    # ---------- Phase 14: production wiring ----------
    # Comma-separated list of origins the frontend is served from.
    # In development we allow "*"; in production this MUST be set.
    cors_allowed_origins: str = ""
    # Optional error monitoring (§14, §19). Empty = disabled.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    # Database — SQLite by default for local dev; Neon Postgres in prod.
    # Example (Neon): postgresql+asyncpg://user:pass@host/dbname?ssl=require
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    db_echo: bool = False

    # Auth / JWT — set real values in .env; these dev defaults are 32+ bytes to satisfy HS256.
    jwt_secret: str = "dev-only-jwt-secret-change-in-production-please"
    jwt_refresh_secret: str = "dev-only-refresh-secret-change-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 30
    # Browser sessions keep refresh credentials in a Secure HttpOnly cookie.
    auth_cookie_name: str = "saaya_refresh"
    csrf_cookie_name: str = "saaya_csrf"
    auth_cookie_domain: str = ""
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    frontend_url: str = "http://localhost:5173"

    # Optional SMTP delivery. Empty host keeps email delivery disabled while
    # preserving verification/reset token issuance and in-app notifications.
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True

    # Optional Web Push delivery (VAPID). Leave blank to hide push controls.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:support@example.com"

    # Comma-separated verified account emails allowed to curate therapist
    # profiles and review reports. Empty means the admin API is closed.
    therapist_admin_emails: str = ""

    # Google Cloud Identity Platform / Firebase Auth. Empty disables Google
    # sign-in while preserving local email/password auth.
    google_identity_platform_project_id: str = ""

    # Provider chain
    llm_provider_chain: str = "groq,openrouter,nvidia,gemini"

    # NVIDIA NIM
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.1-8b-instruct"
    # Reasoning models (Kimi-K3, etc.) accept: low | medium | high | max. Empty = omit.
    nvidia_reasoning_effort: str = ""

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.1-8b-instruct:free"
    openrouter_app_url: str = "http://localhost:8000"
    openrouter_app_name: str = "EmotionalWellnessDev"

    # Groq
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"

    # Gemini
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-2.0-flash"

    # Generation defaults
    llm_max_tokens: int = Field(default=512, ge=1, le=32000)
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)

    # ---------- Speech-to-text (plan §7, Addendum §A) ----------
    stt_provider_chain: str = "groq"
    groq_stt_model: str = "whisper-large-v3"
    stt_timeout_seconds: float = Field(default=90.0, gt=0)
    # Hard cap on upload size (plan §21 cost guard). Groq's Whisper free-tier
    # accepts up to ~25 MB per request.
    voice_max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    voice_max_duration_seconds: float = Field(default=600.0, gt=0)

    # ---------- Reminders scheduler (Phase 9) ----------
    # Off by default so tests and dev iterations don't spawn background tasks.
    # Enable in production (or when integration-testing the worker path).
    reminders_scheduler_enabled: bool = False
    reminders_scheduler_interval_seconds: float = Field(default=60.0, gt=0)

    # ---------- Memory (Phase 11) ----------
    memory_embedding_dims: int = Field(default=256, ge=32, le=4096)
    memory_retrieve_default_k: int = Field(default=5, ge=1, le=25)
    # Optional OpenAI-compatible embedding endpoint. Empty values preserve the
    # deterministic local fallback for development and offline operation.
    embedding_api_base: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # ---------- Rate limits (Phase 12) ----------
    # Off in tests so noisy loops don't need per-test resets.
    rate_limit_enabled: bool = False
    chat_rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    journal_rate_limit_per_minute: int = Field(default=20, ge=1, le=600)
    voice_rate_limit_per_minute: int = Field(default=10, ge=1, le=600)
    # ---------- Auth rate limits (Phase 15 §3.1) — keyed by IP + email ----------
    auth_login_rate_limit_per_minute: int = Field(default=10, ge=1, le=600)
    auth_register_rate_limit_per_minute: int = Field(default=5, ge=1, le=600)
    auth_refresh_rate_limit_per_minute: int = Field(default=30, ge=1, le=600)
    auth_change_password_rate_limit_per_minute: int = Field(default=5, ge=1, le=600)
    # ---------- Request body cap (Phase 15 §3.3) ----------
    max_json_body_bytes: int = Field(default=1 * 1024 * 1024, ge=1024)

    # ---------- Observability (Phase 15 P1 §5) ----------
    # "json" enables structured JSON logging; anything else keeps plain text.
    log_format: str = "text"
    # Expose /metrics for Prometheus scraping.
    metrics_enabled: bool = False
    # Optional bearer token that Prometheus must send to scrape /metrics.
    metrics_bearer_token: str = ""

    # ---------- Idempotency (Phase 15 P1 §5.3) ----------
    idempotency_enabled: bool = True
    idempotency_ttl_seconds: int = Field(default=600, ge=1, le=86400)

    # ---------- Field-level encryption (Phase 15 P1 §5.4) ----------
    # 32-byte URL-safe base64 key. Empty = passthrough (dev/tests).
    field_encryption_key: str = ""

    # ---------- Redis (Phase 15 P1 §5.5) ----------
    redis_url: str = ""

    # ---------- Retention (Phase 15 P1 §5.6) ----------
    retention_purge_enabled: bool = False
    retention_purge_interval_seconds: float = Field(default=86400.0, gt=0)
    retention_audit_days: int = Field(default=365, ge=30)
    retention_notification_days: int = Field(default=90, ge=7)

    @field_validator("llm_provider_chain")
    @classmethod
    def _strip_chain(cls, v: str) -> str:
        return ",".join(p.strip().lower() for p in v.split(",") if p.strip())

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_postgres_url(cls, value: str) -> str:
        """Translate a standard Neon/libpq URL into asyncpg parameters.

        Neon returns ``postgresql://...?sslmode=require&channel_binding=require``.
        SQLAlchemy passes URL query parameters as keyword arguments, while
        asyncpg expects ``ssl`` (not ``sslmode``) and has no
        ``channel_binding`` keyword. Normalize both before engine creation.
        """
        v = str(value)
        low = v.lower()
        if not low.startswith(("postgresql://", "postgres://", "postgresql+asyncpg://")):
            return v
        parts = urlsplit(v)
        scheme = "postgresql+asyncpg"
        query = []
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            low_key = key.lower()
            if low_key == "channel_binding":
                continue
            if low_key == "sslmode":
                key = "ssl"
            query.append((key, val))
        return urlunsplit(
            (scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    @field_validator("database_url")
    @classmethod
    def _require_tls_in_production(cls, v: str, info) -> str:
        # Only Postgres URLs are checked; SQLite is dev-only and rejected below.
        app_env = (info.data.get("app_env") or "").lower()
        if app_env != "production":
            return v
        low = v.lower()
        if low.startswith("sqlite"):
            raise ValueError("SQLite is not allowed in production")
        if "postgres" in low:
            if "ssl=require" not in low and "ssl=verify-full" not in low:
                raise ValueError(
                    "production DATABASE_URL must include sslmode=require (normalized to ssl=require)"
                )
        return v

    @model_validator(mode="after")
    def _production_must_fail_closed(self) -> "Settings":
        """Refuse to boot production with development-grade security values.

        The deployment preflight remains useful for operator-friendly output,
        but it is not guaranteed to run for every process (notably workers).
        Enforcing the invariants here keeps every entry point fail-closed.
        """
        if not self.is_production:
            return self

        low_db = self.database_url.lower()
        if low_db.startswith("sqlite"):
            raise ValueError("SQLite is not allowed in production")
        if not low_db.startswith(("postgresql+asyncpg://", "postgres+asyncpg://")):
            raise ValueError(
                "production DATABASE_URL must use the asyncpg PostgreSQL driver"
            )
        if not any(
            marker in low_db
            for marker in ("ssl=require", "ssl=verify-full")
        ):
            raise ValueError("production DATABASE_URL must require TLS")

        if self.app_role.lower() != "worker":
            origins = self.cors_allowed_origins_list
            if not origins or "*" in origins:
                raise ValueError(
                    "production CORS_ALLOWED_ORIGINS must contain explicit origins"
                )
            if any(not origin.lower().startswith("https://") for origin in origins):
                raise ValueError("production CORS origins must use HTTPS")

            unsafe_markers = ("dev-only", "change-in-production")
            for name, value in (
                ("JWT_SECRET", self.jwt_secret),
                ("JWT_REFRESH_SECRET", self.jwt_refresh_secret),
            ):
                if len(value) < 32 or any(
                    m in value.lower() for m in unsafe_markers
                ):
                    raise ValueError(f"{name} must be a strong production secret")
            if self.jwt_secret == self.jwt_refresh_secret:
                raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must be different")
            if self.jwt_algorithm not in {"HS256", "HS384", "HS512"}:
                raise ValueError("JWT_ALGORITHM must be an approved HMAC algorithm")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            if self.auth_cookie_samesite.lower() not in {"lax", "strict", "none"}:
                raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        if not self.field_encryption_key:
            raise ValueError("FIELD_ENCRYPTION_KEY is required in production")
        try:
            raw_key = self.field_encryption_key.strip()
            key = bytes.fromhex(raw_key) if len(raw_key) == 64 else base64.urlsafe_b64decode(raw_key + "=" * (-len(raw_key) % 4))
        except (ValueError, TypeError) as exc:
            raise ValueError("FIELD_ENCRYPTION_KEY must be valid hex or base64") from exc
        if len(key) != 32:
            raise ValueError("FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return self

    @property
    def provider_chain(self) -> List[str]:
        return [p for p in self.llm_provider_chain.split(",") if p]

    @property
    def cors_allowed_origins_list(self) -> List[str]:
        return [
            o.strip()
            for o in self.cors_allowed_origins.split(",")
            if o.strip()
        ]

    @property
    def therapist_admin_emails_list(self) -> List[str]:
        return [email.strip().lower() for email in self.therapist_admin_emails.split(",") if email.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def stt_provider_chain_list(self) -> List[str]:
        return [
            p.strip().lower()
            for p in self.stt_provider_chain.split(",")
            if p.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
