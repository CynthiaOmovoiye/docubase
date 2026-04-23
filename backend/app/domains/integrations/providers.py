"""
OAuth provider configuration.

Defines static configuration for each supported OAuth provider.
Runtime values (client IDs, secrets, redirect URIs) come from settings — never here.

GitLab URLs are templated because GitLab can be self-hosted; the base URL is
filled in at runtime from settings.gitlab_base_url.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthProvider:
    """
    Immutable configuration for an OAuth 2.0 provider.

    URL fields on GitLab are templates — use str.format(gitlab_base_url=...) at runtime.
    All other providers have concrete URLs.
    """

    name: str
    auth_url: str
    token_url: str
    scopes: list[str]
    user_info_url: str


GITHUB = OAuthProvider(
    name="github",
    auth_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    # repo = read/write on all repos (required for private repo ingestion);
    # read:user = fetch login/name for provider_username
    scopes=["repo", "read:user"],
    user_info_url="https://api.github.com/user",
)

GITLAB = OAuthProvider(
    name="gitlab",
    auth_url="{gitlab_base_url}/oauth/authorize",
    token_url="{gitlab_base_url}/oauth/token",
    scopes=["read_api", "read_repository"],
    user_info_url="{gitlab_base_url}/api/v4/user",
)

GOOGLE_DRIVE = OAuthProvider(
    name="google_drive",
    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    scopes=[
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
    user_info_url="https://www.googleapis.com/oauth2/v2/userinfo",
)

# Registry — keyed by provider name for O(1) lookup in service and API layers
PROVIDERS: dict[str, OAuthProvider] = {
    GITHUB.name: GITHUB,
    GITLAB.name: GITLAB,
    GOOGLE_DRIVE.name: GOOGLE_DRIVE,
}
