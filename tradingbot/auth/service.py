"""
AuthService — register, password login, and SMS-code login.

Password hashing uses stdlib `hashlib.scrypt` (no third-party deps).
SMS verification has no provider configured; codes are printed to the
console / logger, and held in-process for `SMS_CODE_TTL` seconds.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from .database import UserDatabase, UserRecord

logger = logging.getLogger(__name__)


# Username: 3–32 chars, letters/digits/underscore
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
# Phone: simple — 6–15 digits, optional leading +
_PHONE_RE = re.compile(r"^\+?\d{6,15}$")
# Email: minimal sanity check
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SMS_CODE_TTL = 300  # seconds


class AuthError(Exception):
    """Raised for any user-facing auth failure. The message is i18n key + args-free fallback."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code  # short machine code, e.g. "username_taken"


@dataclass
class _PendingCode:
    code: str
    expires_at: float


class AuthService:
    def __init__(self, db: UserDatabase):
        self._db = db
        # phone -> _PendingCode (in-process only; fine for single-process Streamlit)
        self._pending_codes: dict[str, _PendingCode] = {}

    # ------------------------------------------------------------------ #
    # Register                                                             #
    # ------------------------------------------------------------------ #

    def register(
        self,
        username: str,
        password: str,
        confirm_password: str,
        phone: str,
        email: Optional[str] = None,
    ) -> UserRecord:
        username = (username or "").strip()
        phone = (phone or "").strip()
        email = (email or "").strip() or None

        if not _USERNAME_RE.match(username):
            raise AuthError("username_invalid")
        if not _PHONE_RE.match(phone):
            raise AuthError("phone_invalid")
        if email and not _EMAIL_RE.match(email):
            raise AuthError("email_invalid")
        if len(password) < 8:
            raise AuthError("password_too_short")
        if password != confirm_password:
            raise AuthError("password_mismatch")

        if self._db.get_by_username(username) is not None:
            raise AuthError("username_taken")
        if self._db.get_by_phone(phone) is not None:
            raise AuthError("phone_taken")

        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        return self._db.insert_user(username, phone, email, pw_hash, salt)

    # ------------------------------------------------------------------ #
    # Password login                                                       #
    # ------------------------------------------------------------------ #

    def login_with_password(self, identifier: str, password: str) -> UserRecord:
        """Identifier may be a username OR a phone number."""
        identifier = (identifier or "").strip()
        if not identifier or not password:
            raise AuthError("missing_credentials")

        if _PHONE_RE.match(identifier):
            user = self._db.get_by_phone(identifier)
        else:
            user = self._db.get_by_username(identifier)

        if user is None:
            raise AuthError("invalid_credentials")
        if _hash_password(password, user.salt) != user.password_hash:
            raise AuthError("invalid_credentials")
        return user

    # ------------------------------------------------------------------ #
    # SMS-code login                                                       #
    # ------------------------------------------------------------------ #

    def send_sms_code(self, phone: str) -> str:
        """
        Generate a 6-digit code, store it in-process, and 'deliver' it.

        No SMS provider is configured — the code is printed to the logger so
        the developer can read it from the console. Returns the code so the
        UI may optionally display it in DEV mode.
        """
        phone = (phone or "").strip()
        if not _PHONE_RE.match(phone):
            raise AuthError("phone_invalid")
        if self._db.get_by_phone(phone) is None:
            raise AuthError("phone_not_registered")

        code = f"{secrets.randbelow(1_000_000):06d}"
        self._pending_codes[phone] = _PendingCode(
            code=code, expires_at=time.time() + SMS_CODE_TTL
        )
        logger.warning("[SMS-STUB] verification code for %s: %s", phone, code)
        print(f"[SMS-STUB] verification code for {phone}: {code}")
        return code

    def login_with_code(self, phone: str, code: str) -> UserRecord:
        phone = (phone or "").strip()
        code = (code or "").strip()
        pending = self._pending_codes.get(phone)
        if pending is None:
            raise AuthError("code_not_requested")
        if time.time() > pending.expires_at:
            self._pending_codes.pop(phone, None)
            raise AuthError("code_expired")
        if not secrets.compare_digest(pending.code, code):
            raise AuthError("code_invalid")

        user = self._db.get_by_phone(phone)
        if user is None:
            raise AuthError("phone_not_registered")
        self._pending_codes.pop(phone, None)
        return user


# ---------------------------------------------------------------------- #
# Password hashing                                                         #
# ---------------------------------------------------------------------- #

def _hash_password(password: str, salt: str) -> str:
    """scrypt with conservative parameters; returns hex digest."""
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return digest.hex()


# ---------------------------------------------------------------------- #
# Default db path                                                          #
# ---------------------------------------------------------------------- #

def default_users_db_path() -> str:
    return os.environ.get(
        "TRADINGBOT_USERS_DB",
        os.path.expanduser("~/.tradingagents/users.db"),
    )
