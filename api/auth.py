"""Authentication and authorization module."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = getattr(settings, 'SECRET_KEY', secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = getattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', 60 * 24)  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Token payload data."""
    sub: str  # Subject (user identifier)
    exp: datetime
    scopes: list[str] = []


class User(BaseModel):
    """User model for authentication."""
    username: str
    disabled: bool = False
    scopes: list[str] = ["read", "write"]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        if sub is None:
            return None
        exp = datetime.fromtimestamp(payload.get("exp", 0))
        scopes = payload.get("scopes", [])
        return TokenData(sub=sub, exp=exp, scopes=scopes)
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        return None


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header)
) -> Optional[User]:
    """Get current user from token or API key (optional - returns None if not authenticated)."""
    # Check API key first
    if api_key:
        configured_api_key = getattr(settings, 'API_KEY', None)
        if configured_api_key and api_key == configured_api_key:
            return User(username="api_user", scopes=["read", "write"])

    # Check Bearer token
    if credentials:
        token_data = decode_token(credentials.credentials)
        if token_data:
            return User(username=token_data.sub, scopes=token_data.scopes)

    return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header)
) -> User:
    """Get current user from token or API key (required)."""
    # Check if auth is disabled
    if getattr(settings, 'AUTH_DISABLED', True):
        return User(username="anonymous", scopes=["read", "write"])

    user = await get_current_user_optional(credentials, api_key)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user (not disabled)."""
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled"
        )
    return current_user


def require_scope(required_scope: str):
    """Dependency factory for requiring a specific scope."""
    async def scope_checker(user: User = Depends(get_current_active_user)) -> User:
        if required_scope not in user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' required"
            )
        return user
    return scope_checker


# Convenience dependencies
RequireRead = Depends(require_scope("read"))
RequireWrite = Depends(require_scope("write"))
RequireAdmin = Depends(require_scope("admin"))


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, list[datetime]] = {}

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed for the given key."""
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)

        if key not in self._requests:
            self._requests[key] = []

        # Clean old requests
        self._requests[key] = [t for t in self._requests[key] if t > minute_ago]

        if len(self._requests[key]) >= self.requests_per_minute:
            return False

        self._requests[key].append(now)
        return True


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=100)


async def check_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Check rate limit for the current user."""
    if not rate_limiter.is_allowed(user.username):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    return user
