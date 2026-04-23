"""
OAuth provider configuration.

Defines static configuration for each supported OAuth provider.
Runtime values (client IDs, secrets, redirect URIs) come from settings — never here.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthProvider:
    """Immutable configuration for an OAuth 2.0 provider."""

    name: str
    auth_url: str
    token_url: str
    scopes: list[str]
    user_info_url: str


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

PROVIDERS: dict[str, OAuthProvider] = {
    GOOGLE_DRIVE.name: GOOGLE_DRIVE,
}
