"""
Application configuration.

All settings loaded from environment variables via pydantic-settings.
No hardcoded values. No secrets in code.
"""

import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    # Optional comma-separated list; when set, replaces default CORS origin logic.
    cors_allowed_origins: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_allow_origins(self) -> list[str]:
        """Origins permitted by CORSMiddleware (must match the browser's Origin header)."""
        raw = self.cors_allowed_origins.strip()
        if raw:
            return _normalize_cors_origin_list(raw.split(","))

        primary = self.frontend_url.rstrip("/")
        out: list[str] = [primary]

        # Local dev: Vite is often opened as http://127.0.0.1:5173 while FRONTEND_URL uses localhost.
        if self.app_env == "development":
            alt = _alternate_loopback_origin(primary)
            if alt and alt not in out:
                out.append(alt)
        return out

    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ─── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ─── Auth ─────────────────────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7  # reduced from 30; pair with token rotation

    # ─── LLM ──────────────────────────────────────────────────────────────────
    # OpenRouter uses the OpenAI SDK against https://openrouter.ai/api/v1
    llm_provider: Literal["openrouter", "openai", "anthropic", "local"] = (
        "openrouter"
    )
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    # Optional OpenRouter attribution (https://openrouter.ai/docs/api/reference/overview)
    openrouter_http_referer: str = ""
    openrouter_app_title: str = "docbase"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.2

    # ─── Embeddings ───────────────────────────────────────────────────────────
    embedding_provider: str = "local"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_fallback_provider: str = ""
    embedding_fallback_model: str = ""

    # Jina AI embeddings — free tier: 1M tokens/month, no credit card required
    # Get a key at: https://jina.ai/  (sign in → API Keys)
    # Set EMBEDDING_PROVIDER=jina and EMBEDDING_MODEL=jina-embeddings-v3
    jina_api_key: str = ""
    jina_embed_batch_size: int = 32
    jina_embed_batch_delay_ms: int = 1500
    jina_embed_max_retries: int = 3
    jina_embed_retry_base_delay_ms: int = 2000
    jina_embed_retry_max_delay_ms: int = 15000

    # Voyage AI embeddings — configure as a backup provider when the primary
    # embedder is rate-limited. Use a model that matches EMBEDDING_DIMENSIONS.
    voyage_api_key: str = ""

    # ─── Storage ──────────────────────────────────────────────────────────────
    storage_backend: Literal["local", "s3"] = "local"
    # /tmp is world-readable on Linux.  Default to a path under the app home.
    # In production, set STORAGE_LOCAL_PATH to a directory with mode 0700,
    # or use S3 (STORAGE_BACKEND=s3).
    storage_local_path: str = "/var/lib/docbase/uploads"

    # ─── Policy / Safety ──────────────────────────────────────────────────────
    policy_blocked_file_patterns: str = (
        ".env,.env.*,*.pem,*.key,*.p12,*.pfx,secrets.*,credentials.*"
    )
    policy_secret_scan_enabled: bool = True

    @property
    def policy_blocked_patterns_list(self) -> list[str]:
        return [p.strip() for p in self.policy_blocked_file_patterns.split(",")]

    # ─── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    sentry_dsn: str = ""

    # Langfuse — LLM observability (https://langfuse.com)
    # Self-hosted: set langfuse_host to your instance URL.
    # Cloud: leave langfuse_host as default and set the two keys from
    #   https://cloud.langfuse.com → Project → Settings → API Keys
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    # ─── Reranking ────────────────────────────────────────────────────────────
    # Cohere Rerank API — enables cross-encoder reranking after vector retrieval.
    # Get a key at https://dashboard.cohere.com/api-keys (free tier available).
    # Leave empty to skip reranking (vector order is used instead).
    cohere_api_key: str = ""

    # ─── Chat retrieval / generation latency budgets ─────────────────────────
    chat_retrieval_latency_budget_ms: int = 3000
    chat_generation_latency_budget_ms: int = 9000
    chat_verification_latency_budget_ms: int = 1000
    chat_total_latency_budget_ms: int = 12000
    workspace_chat_total_latency_budget_ms: int = 18000

    # Active LLM-as-judge: reject drafts and regenerate with feedback (adds latency).
    chat_quality_gate_enabled: bool = True
    # Extra generation rounds after the first draft (0 = gate only logs accept/reject, no regen).
    chat_quality_gate_max_regenerations: int = 2
    # When True (default): if the judge LLM call itself fails (timeout, malformed JSON, provider
    # error), serve the current draft rather than raising. Set False in high-trust environments
    # where serving an unjudged answer is unacceptable — the chat call will 500 instead.
    chat_quality_gate_fail_open: bool = True

    # ─── OAuth integrations ───────────────────────────────────────────────────
    # Google OAuth 2.0 credentials (from Google Cloud Console)
    google_client_id: str = ""
    google_client_secret: str = ""

    # OAuth redirect base — must match what's registered in each provider's app settings
    # Defaults to app_base_url so it works in dev without extra config.
    @property
    def oauth_redirect_base(self) -> str:
        return self.app_base_url.rstrip("/")

    @field_validator("app_secret_key", "jwt_secret_key")
    @classmethod
    def secret_must_not_be_default(cls, v: str) -> str:
        if v.startswith("change-me"):
            # Alembic loads the full app stack but only needs DATABASE_URL; env.py sets this.
            if os.environ.get("DOCBASE_ALEMBIC") == "1" and os.getenv(
                "APP_ENV", "development"
            ).lower() != "production":
                return v
            raise ValueError(
                "Secret key has not been changed from the default. "
                "Set a real secret in your .env file."
            )
        return v

    @field_validator("database_url")
    @classmethod
    def database_url_must_not_use_default_password(cls, v: str) -> str:
        """
        Reject the well-known default database password in production.

        The docker-compose.yml ships with 'doctwin_pass' as the Postgres password.
        If someone copies .env.example without changing the DATABASE_URL this
        validator will catch it before the app starts in production.
        """
        env = os.getenv("APP_ENV", "development").lower()
        if env == "production" and "doctwin_pass" in v:
            raise ValueError(
                "DATABASE_URL contains the default password 'doctwin_pass'. "
                "Change the database password before deploying to production."
            )
        return v

    @field_validator("jina_embed_batch_size")
    @classmethod
    def jina_batch_size_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("JINA_EMBED_BATCH_SIZE must be at least 1.")
        return v

    @field_validator(
        "jina_embed_batch_delay_ms",
        "jina_embed_max_retries",
        "jina_embed_retry_base_delay_ms",
        "jina_embed_retry_max_delay_ms",
    )
    @classmethod
    def jina_rate_limit_tuning_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Jina embedding tuning values must be non-negative.")
        return v


def _normalize_cors_origin_list(segments: list[str]) -> list[str]:
    """Strip whitespace; drop mistaken `//` suffixes (dotenv does not treat // as a comment)."""
    out: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        token = segment.strip()
        if not token:
            continue
        if " " in token:
            token = token.split()[0].strip()
        token = token.rstrip("/")
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _alternate_loopback_origin(url: str) -> str | None:
    """Return the same port/scheme with localhost <-> 127.0.0.1 swapped, or None."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return None
    host = parsed.hostname
    if host == "localhost":
        new_host = "127.0.0.1"
    elif host == "127.0.0.1":
        new_host = "localhost"
    else:
        return None
    port = parsed.port
    netloc = new_host if port is None else f"{new_host}:{port}"
    return f"{parsed.scheme}://{netloc}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
