"""
Authentication utilities - JWT and encryption
"""
import os
import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import base64

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-please-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# Encryption key derived from JWT_SECRET (for settings encryption)
def _get_fernet_key() -> bytes:
    """Generate a Fernet-compatible key from JWT_SECRET"""
    # Use SHA256 to get a consistent 32-byte key, then base64 encode
    key_hash = hashlib.sha256(JWT_SECRET.encode()).digest()
    return base64.urlsafe_b64encode(key_hash)

_fernet = Fernet(_get_fernet_key())


def create_access_token(user_data: Dict[str, Any]) -> str:
    """
    Create a JWT access token for a user
    
    Args:
        user_data: Dict containing user info (id, email, name, avatar_url)
    
    Returns:
        JWT token string
    """
    payload = {
        "sub": str(user_data["id"]),  # Subject (user ID)
        "email": user_data["email"],
        "name": user_data.get("name"),
        "avatar_url": user_data.get("avatar_url"),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT access token
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def encrypt_settings(settings_json: str) -> str:
    """
    Encrypt user settings JSON string
    
    Args:
        settings_json: JSON string of user settings
    
    Returns:
        Encrypted string (base64 encoded)
    """
    encrypted = _fernet.encrypt(settings_json.encode())
    return encrypted.decode()


def decrypt_settings(encrypted_settings: str) -> str:
    """
    Decrypt user settings
    
    Args:
        encrypted_settings: Encrypted settings string
    
    Returns:
        Decrypted JSON string
    """
    decrypted = _fernet.decrypt(encrypted_settings.encode())
    return decrypted.decode()


def get_user_id_from_token(token: str) -> Optional[str]:
    """Extract user ID from a valid token"""
    payload = verify_access_token(token)
    if payload:
        return payload.get("sub")
    return None
