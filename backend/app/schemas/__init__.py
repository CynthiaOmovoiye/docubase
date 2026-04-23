"""
Pydantic schemas for request/response contracts.

Organised by domain. All API boundaries use these — never ORM models directly.
"""

from app.schemas.twins import (
    TwinConfigResponse,
    TwinConfigUpdateRequest,
    TwinCreateRequest,
    TwinResponse,
    TwinUpdateRequest,
)
from app.schemas.users import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.workspaces import (
    WorkspaceCreateRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)

__all__ = [
    # Users / Auth
    "UserRegisterRequest",
    "UserLoginRequest",
    "UserResponse",
    "UserUpdateRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    # Workspaces
    "WorkspaceCreateRequest",
    "WorkspaceUpdateRequest",
    "WorkspaceResponse",
    # Twins
    "TwinCreateRequest",
    "TwinUpdateRequest",
    "TwinResponse",
    "TwinConfigResponse",
    "TwinConfigUpdateRequest",
]
