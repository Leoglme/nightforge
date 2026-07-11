"""
User Pydantic schemas for request/response validation.
"""
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from enums.user_role import UserRole


class UserBase(BaseModel):
    """Base user schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr = Field(...)
    role: UserRole = Field(default=UserRole.USER)


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(..., min_length=6, max_length=100)


class UserResponse(UserBase):
    """Schema for user response."""

    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr = Field(...)
    password: str = Field(..., min_length=1)


class Token(BaseModel):
    """Schema for authentication token."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token data."""

    email: Optional[str] = None
