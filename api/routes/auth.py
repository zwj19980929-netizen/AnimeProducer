"""Authentication API routes."""

import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import select

from api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    User,
    create_access_token,
    get_current_active_user,
    get_password_hash,
    verify_password,
)
from api.deps import DBSession
from config import settings
from core.models import UserAccount

logger = logging.getLogger(__name__)
router = APIRouter()

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


class LoginRequest(BaseModel):
    """Login request model."""

    username: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request model."""

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


class AuthBootstrapResponse(BaseModel):
    """Frontend bootstrap data for auth UI."""

    auth_disabled: bool
    allow_registration: bool
    has_users: bool


def _validate_username(username: str) -> str:
    if not _USERNAME_PATTERN.match(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be 3-32 chars and contain only letters, numbers, _ or -",
        )
    return username


def _issue_token(account: UserAccount) -> Token:
    access_token = create_access_token(
        data={
            "sub": account.username,
            "scopes": list(account.scopes or ["read", "write"]),
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/bootstrap", response_model=AuthBootstrapResponse)
def auth_bootstrap(session: DBSession) -> AuthBootstrapResponse:
    """Expose auth availability so the UI can choose login/register flows."""

    has_users = session.exec(select(UserAccount.id)).first() is not None
    return AuthBootstrapResponse(
        auth_disabled=getattr(settings, "AUTH_DISABLED", False),
        allow_registration=getattr(settings, "ALLOW_REGISTRATION", True),
        has_users=has_users,
    )


@router.post("/login", response_model=Token)
def login(request: LoginRequest, session: DBSession) -> Token:
    """Authenticate user and return access token."""

    account = session.exec(
        select(UserAccount).where(UserAccount.username == request.username)
    ).first()
    if not account or not verify_password(request.password, account.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if account.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return _issue_token(account)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, session: DBSession) -> Token:
    """Register a new user."""

    if not getattr(settings, "ALLOW_REGISTRATION", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is disabled",
        )

    username = _validate_username(request.username)
    existing = session.exec(
        select(UserAccount).where(UserAccount.username == username)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    account = UserAccount(
        username=username,
        hashed_password=get_password_hash(request.password),
        scopes=["read", "write"],
        updated_at=datetime.utcnow(),
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    logger.info("New user registered: %s", account.username)
    return _issue_token(account)


@router.get("/me", response_model=User)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Get current user information."""

    return current_user


@router.post("/refresh", response_model=Token)
def refresh_token(
    session: DBSession,
    current_user: User = Depends(get_current_active_user),
) -> Token:
    """Refresh access token."""

    account = session.exec(
        select(UserAccount).where(UserAccount.username == current_user.username)
    ).first()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _issue_token(account)
