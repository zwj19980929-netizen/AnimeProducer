"""Authentication API routes."""

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from api.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    User,
    get_current_active_user,
)
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request model."""
    username: str
    password: str


# Simple in-memory user store (replace with database in production)
_users_db: dict[str, dict] = {}


def _init_default_user():
    """Initialize default admin user if configured."""
    admin_username = getattr(settings, 'ADMIN_USERNAME', 'admin')
    admin_password = getattr(settings, 'ADMIN_PASSWORD', None)

    if admin_password and admin_username not in _users_db:
        _users_db[admin_username] = {
            "username": admin_username,
            "hashed_password": get_password_hash(admin_password),
            "disabled": False,
            "scopes": ["read", "write", "admin"]
        }
        logger.info(f"Default admin user '{admin_username}' initialized")


# Initialize default user on module load
_init_default_user()


@router.post("/login", response_model=Token)
async def login(request: LoginRequest) -> Token:
    """Authenticate user and return access token."""
    user_data = _users_db.get(request.username)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(request.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user_data.get("disabled", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    access_token = create_access_token(
        data={
            "sub": user_data["username"],
            "scopes": user_data.get("scopes", ["read", "write"])
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest) -> Token:
    """Register a new user."""
    # Check if registration is enabled
    if not getattr(settings, 'ALLOW_REGISTRATION', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is disabled"
        )

    if request.username in _users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Create new user
    _users_db[request.username] = {
        "username": request.username,
        "hashed_password": get_password_hash(request.password),
        "disabled": False,
        "scopes": ["read", "write"]
    }

    # Generate token for new user
    access_token = create_access_token(
        data={
            "sub": request.username,
            "scopes": ["read", "write"]
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    logger.info(f"New user registered: {request.username}")

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Get current user information."""
    return current_user


@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user: User = Depends(get_current_active_user)
) -> Token:
    """Refresh access token."""
    access_token = create_access_token(
        data={
            "sub": current_user.username,
            "scopes": current_user.scopes
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
