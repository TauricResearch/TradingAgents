from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.core.security import create_access_token, hash_password, verify_password
from backend.models import User
from backend.schemas import SettingsIn, UserOut

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = SettingsIn().model_dump()


def seed_admin(db: Session, email: str, password: str, name: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        email=email,
        name=name,
        password_hash=hash_password(password),
        role="admin",
        settings_json=json.dumps(DEFAULT_SETTINGS),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Seeded local admin user", extra={"user_id": user.id})
    return user


def authenticate(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid email or password")
    token = create_access_token(user.id, {"role": user.role, "email": user.email})
    return user, token


def register_user(db: Session, email: str, password: str, name: str) -> tuple[User, str]:
    if db.query(User).filter(User.email == email).first():
        raise ValueError("Email already registered")
    role = "admin" if db.query(User).count() == 0 else "user"
    user = User(
        email=email,
        name=name,
        password_hash=hash_password(password),
        role=role,
        settings_json=json.dumps(DEFAULT_SETTINGS),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, {"role": user.role, "email": user.email})
    return user, token


def user_settings(user: User) -> dict:
    if not user.settings_json:
        return DEFAULT_SETTINGS.copy()
    try:
        return {**DEFAULT_SETTINGS, **json.loads(user.settings_json)}
    except json.JSONDecodeError:
        return DEFAULT_SETTINGS.copy()


def to_user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)
