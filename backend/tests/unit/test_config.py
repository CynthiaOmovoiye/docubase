"""Settings validation edge cases."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_placeholder_secrets_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "change-me-to-a-long-random-string")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-to-another-long-random-string")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.delenv("DOCBASE_ALEMBIC", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "Secret key" in str(exc.value)


def test_placeholder_secrets_allowed_for_alembic_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "change-me-to-a-long-random-string")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-to-another-long-random-string")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("DOCBASE_ALEMBIC", "1")
    monkeypatch.setenv("APP_ENV", "development")
    s = Settings()
    assert s.app_secret_key.startswith("change-me")


def _valid_secrets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "y" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")


def test_cors_allow_origins_includes_loopback_doctwin_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_secrets_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    s = Settings()
    assert s.cors_allow_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_cors_allow_origins_reverse_localhost_twin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_secrets_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", "http://127.0.0.1:5173")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    s = Settings()
    assert s.cors_allow_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]


def test_cors_allow_origins_production_no_loopback_twin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_secrets_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")
    s = Settings()
    assert s.cors_allow_origins == ["http://localhost:5173"]


def test_cors_allowed_origins_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _valid_secrets_env(monkeypatch)
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://a.example:3000, https://b.example ",
    )
    s = Settings()
    assert s.cors_allow_origins == ["http://a.example:3000", "https://b.example"]


def test_cors_allowed_origins_strips_inline_space_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mimics mistaken `// comment` after a URL in .env (dotenv does not treat // as comment)."""
    _valid_secrets_env(monkeypatch)
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173 //oops",
    )
    s = Settings()
    assert s.cors_allow_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_placeholder_secrets_rejected_in_production_even_with_alembic_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "change-me-to-a-long-random-string")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-to-another-long-random-string")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("DOCBASE_ALEMBIC", "1")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValidationError):
        Settings()
