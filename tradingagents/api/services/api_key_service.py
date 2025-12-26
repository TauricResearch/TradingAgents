"""API key service for secure key generation and hashing.

This module provides utilities for generating and verifying API keys:
- Generate secure random API keys with 'ta_' prefix
- Hash API keys using bcrypt (via pwdlib)
- Verify plain API keys against hashed values

Security:
- Never store plain API keys in the database
- Use bcrypt for hashing (via pwdlib PasswordHash)
- API keys are URL-safe base64 encoded (32 bytes)
"""

import secrets
from pwdlib import PasswordHash


# API key hashing with bcrypt (same context as passwords for consistency)
api_key_context = PasswordHash.recommended()


def generate_api_key() -> str:
    """
    Generate a secure random API key.

    Returns a URL-safe API key with the 'ta_' prefix followed by
    32 bytes of random data encoded as base64.

    Format: ta_<base64_url_safe_32_bytes>
    Example: ta_vK9x8pL2mN3qR5sT7uW1yZ4aB6cD8eF0gH2jK4lM6n

    Returns:
        str: Generated API key (plaintext)

    Security:
        - Uses secrets.token_urlsafe() for cryptographically strong randomness
        - 32 bytes = 256 bits of entropy
        - Never store the returned value directly in database

    Example:
        >>> api_key = generate_api_key()
        >>> api_key.startswith("ta_")
        True
        >>> len(api_key) > 40  # ta_ + base64(32 bytes)
        True
    """
    # Generate 32 bytes (256 bits) of cryptographically secure random data
    # URL-safe base64 encoding makes it safe for URLs and headers
    random_part = secrets.token_urlsafe(32)

    return f"ta_{random_part}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key using bcrypt.

    Uses the same pwdlib PasswordHash context as password hashing
    for consistency. The hashed value can be safely stored in the database.

    Args:
        api_key: Plain text API key (from generate_api_key())

    Returns:
        str: Bcrypt hash of the API key

    Security:
        - Uses bcrypt algorithm (via Argon2 default from pwdlib)
        - Hash is one-way and computationally expensive to reverse
        - Store this hash in database, not the plain API key

    Example:
        >>> api_key = generate_api_key()
        >>> hashed = hash_api_key(api_key)
        >>> hashed != api_key  # Hash is different from plain key
        True
        >>> len(hashed) > 50  # Bcrypt hashes are long
        True
    """
    return api_key_context.hash(api_key)


def verify_api_key(plain_api_key: str, hashed_api_key: str) -> bool:
    """
    Verify a plain API key against a hash.

    Checks if the provided plain API key matches the stored hash.
    Uses constant-time comparison to prevent timing attacks.

    Args:
        plain_api_key: Plain text API key (from user request)
        hashed_api_key: Hashed API key (from database)

    Returns:
        bool: True if API key matches hash, False otherwise

    Security:
        - Uses constant-time comparison
        - Safe against timing attacks
        - Computationally expensive to slow down brute force

    Example:
        >>> api_key = generate_api_key()
        >>> hashed = hash_api_key(api_key)
        >>> verify_api_key(api_key, hashed)
        True
        >>> verify_api_key("wrong_key", hashed)
        False
    """
    try:
        return api_key_context.verify(plain_api_key, hashed_api_key)
    except Exception:
        # If verification fails for any reason (malformed hash, etc.)
        # return False rather than raising an exception
        return False
