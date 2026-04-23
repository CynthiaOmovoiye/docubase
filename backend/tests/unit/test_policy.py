"""
Unit tests for the policy/safety domain.

These tests have no DB or external dependencies.
Policy logic must be deterministic and fast.
"""


from app.domains.policy.rules import (
    can_surface_code_snippet,
    is_file_blocked,
    redact_sensitive_content,
    scan_content_for_secrets,
)


class TestFileBlocking:

    def test_env_file_is_blocked(self):
        decision = is_file_blocked(".env")
        assert decision.allowed is False
        assert decision.tier == "always_blocked"

    def test_env_local_is_blocked(self):
        decision = is_file_blocked(".env.local")
        assert decision.allowed is False

    def test_pem_file_is_blocked(self):
        decision = is_file_blocked("certs/server.pem")
        assert decision.allowed is False

    def test_private_key_is_blocked(self):
        decision = is_file_blocked("keys/private.key")
        assert decision.allowed is False

    def test_readme_is_allowed(self):
        decision = is_file_blocked("README.md")
        assert decision.allowed is True

    def test_python_source_is_allowed(self):
        decision = is_file_blocked("src/auth/service.py")
        assert decision.allowed is True

    def test_nested_env_file_is_blocked(self):
        decision = is_file_blocked("config/.env.production")
        assert decision.allowed is False


class TestSecretScanning:

    def test_detects_api_key_assignment(self):
        content = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz1234567890"'
        flags = scan_content_for_secrets(content)
        assert len(flags) > 0

    def test_detects_openai_key(self):
        content = "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz12345678"
        flags = scan_content_for_secrets(content)
        assert len(flags) > 0

    def test_detects_openrouter_key(self):
        content = (
            "OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnopqrstuvwxyz1234567890"
        )
        flags = scan_content_for_secrets(content)
        assert len(flags) > 0

    def test_detects_private_key_header(self):
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
        flags = scan_content_for_secrets(content)
        assert len(flags) > 0

    def test_clean_content_returns_empty(self):
        content = "def hello():\n    return 'world'\n"
        flags = scan_content_for_secrets(content)
        assert flags == []

    def test_auth_type_annotations_are_not_secrets(self):
        content = """
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

async def get_current_user(token: str = Depends(oauth2_scheme)):
    return token
"""
        flags = scan_content_for_secrets(content)
        assert flags == []

    def test_settings_secret_key_reference_is_not_secret_value(self):
        content = """
return jwt.encode(
    to_encode,
    settings.secret_key,
    algorithm=settings.jwt_algorithm,
)
"""
        flags = scan_content_for_secrets(content)
        assert flags == []

    def test_detects_yaml_style_quoted_password_value(self):
        content = 'database:\n  password: "supersecretpassword123"\n'
        flags = scan_content_for_secrets(content)
        assert len(flags) > 0


class TestCodeSnippetPolicy:

    def test_snippets_blocked_by_default(self):
        decision = can_surface_code_snippet(allow_code_snippets=False)
        assert decision.allowed is False
        assert decision.tier == "opt_in_blocked"

    def test_snippets_allowed_when_enabled(self):
        decision = can_surface_code_snippet(allow_code_snippets=True)
        assert decision.allowed is True
        assert decision.tier == "opt_in"


class TestRedaction:

    def test_redacts_secret_line(self):
        content = 'password = "supersecretpassword123"\nprint("hello")'
        result = redact_sensitive_content(content)
        assert "supersecretpassword123" not in result
        assert "[REDACTED" in result
        assert 'print("hello")' in result

    def test_clean_content_unchanged(self):
        content = "def greet(name):\n    return f'Hello, {name}'"
        result = redact_sensitive_content(content)
        assert result == content
