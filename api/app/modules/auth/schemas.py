"""Auth Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TokenPayload(BaseModel):
    sub: UUID
    email: str
    name: str
    iat: int
    exp: int


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    avatar_url: Optional[str] = None


class AccessTokenResponse(BaseModel):
    access_token: str
    expires_in: int
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int
