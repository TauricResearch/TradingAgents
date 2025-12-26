"""User model for authentication."""

from typing import List, Optional
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingagents.api.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User model for authentication and authorization.

    Attributes:
        id: Primary key
        username: Unique username for authentication
        email: Unique email address
        hashed_password: Bcrypt hashed password
        full_name: Optional full name
        is_active: Whether user account is active
        is_superuser: Whether user has admin privileges
        tax_jurisdiction: Tax jurisdiction code (e.g., "US", "US-CA", "AU")
        timezone: IANA timezone identifier (e.g., "America/New_York", "UTC")
        api_key_hash: Bcrypt hash of API key (if user has API key)
        is_verified: Whether user email is verified
        strategies: Related Strategy objects owned by this user
        portfolios: Related Portfolio objects owned by this user
        settings: Related Settings object for this user (one-to-one)
    """

    __tablename__ = "users"

    # Primary identification
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # User status and permissions
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Issue #3: Profile fields
    tax_jurisdiction: Mapped[str] = mapped_column(
        String(10),
        default="AU",
        nullable=False,
        comment="Tax jurisdiction code (e.g., US, US-CA, AU-NSW)"
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="Australia/Sydney",
        nullable=False,
        comment="IANA timezone identifier (e.g., America/New_York, UTC)"
    )
    api_key_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        unique=True,
        comment="Bcrypt hash of API key for programmatic access"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether user email has been verified"
    )

    # Relationship to strategies
    strategies: Mapped[List["Strategy"]] = relationship(
        "Strategy",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Relationship to portfolios (Issue #4: DB-3)
    portfolios: Mapped[List["Portfolio"]] = relationship(
        "Portfolio",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Relationship to settings (Issue #5: DB-4) - one-to-one
    settings: Mapped[Optional["Settings"]] = relationship(
        "Settings",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
