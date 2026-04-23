"""
Pydantic schemas for request/response contracts.

Organised by domain. All API boundaries use these — never ORM models directly.
"""

from app.schemas.users import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    UserUpdateRequest,
    TokenResponse,
    RefreshTokenRequest,
)
from app.schemas.workspaces import (
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
    WorkspaceResponse,
)
from app.schemas.twins import (
    TwinCreateRequest,
    TwinUpdateRequest,
    TwinResponse,
    TwinConfigResponse,
    TwinConfigUpdateRequest,
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
