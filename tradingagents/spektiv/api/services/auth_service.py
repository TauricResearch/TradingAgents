"""Authentication service for password hashing and JWT tokens."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from pwdlib import PasswordHash

from spektiv.api.config import settings


# Password hashing with Argon2
pwd_context = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2.

    Args:
        password: Plain text password

    Returns:
        Hashed password string

    Example:
        >>> hashed = hash_password("SecurePassword123!")
        >>> hashed.startswith("$argon2")
        True
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password to verify against

    Returns:
        True if password matches, False otherwise

    Example:
        >>> hashed = hash_password("SecurePassword123!")
        >>> verify_password("SecurePassword123!", hashed)
        True
        >>> verify_password("WrongPassword", hashed)
        False
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in the token (e.g., {"sub": "username"})
        expires_delta: Token expiration time (default: from settings)

    Returns:
        Encoded JWT token

    Example:
        >>> token = create_access_token({"sub": "testuser"})
        >>> isinstance(token, str)
        True
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token to decode

    Returns:
        Decoded token payload, or None if invalid

    Example:
        >>> token = create_access_token({"sub": "testuser"})
        >>> payload = decode_access_token(token)
        >>> payload["sub"]
        'testuser'
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
