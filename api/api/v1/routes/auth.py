"""
Authentication routes for login and current-user info.
"""
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models.user import User
from schemas.user import Token, UserLogin, UserResponse
from services.auth_service import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)) -> Any:
    """
    Login with email and password.

    Args:
        user_credentials: Login credentials.
        db: Database session.

    Returns:
        An access token.

    Raises:
        HTTPException: If credentials are invalid.
    """
    user = authenticate_user(db, user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)) -> Any:
    """
    Get current user information.

    Args:
        current_user: The authenticated user.

    Returns:
        The current user.
    """
    return current_user
