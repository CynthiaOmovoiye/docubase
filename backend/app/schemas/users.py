"""
User and auth schemas.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if v.isdigit():
            raise ValueError("Password must not be all digits")
        return v

    @field_validator("display_name", mode="before")
    @classmethod
    def sanitise_display_name(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        # Strip leading/trailing whitespace and collapse internal runs
        v = " ".join(v.split())
        # Reject strings that are purely whitespace after stripping
        if not v:
            return None
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("display_name", mode="before")
    @classmethod
    def sanitise_display_name(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        v = " ".join(v.split())
        return v or None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str
