"""Settings model for user risk profiles and alert preferences.

This module defines the Settings model for managing user trading preferences,
risk profiles, and alert configurations. Each user has exactly one Settings
record (one-to-one relationship).

Model Fields:
    - id: Primary key
    - user_id: Foreign key to users table (unique, one-to-one)
    - risk_profile: User's risk tolerance (CONSERVATIVE, MODERATE, AGGRESSIVE)
    - risk_score: Numeric risk score from 0 (very conservative) to 10 (very aggressive)
    - max_position_pct: Maximum percentage of portfolio for single position (0-100)
    - max_portfolio_risk_pct: Maximum portfolio-wide risk percentage (0-100)
    - investment_horizon_years: Investment time horizon in years (>= 0)
    - alert_preferences: JSON configuration for email/SMS/push notifications
    - created_at, updated_at: Automatic timestamps

Relationships:
    - user: One-to-one relationship with User model
    - Cascade delete when user is deleted

Constraints:
    - Unique constraint on user_id (one settings per user)
    - Check constraint: risk_score >= 0 AND risk_score <= 10
    - Check constraint: max_position_pct >= 0 AND max_position_pct <= 100
    - Check constraint: max_portfolio_risk_pct >= 0 AND max_portfolio_risk_pct <= 100
    - Check constraint: investment_horizon_years >= 0

Follows SQLAlchemy 2.0 patterns with Mapped[] and mapped_column().
"""

from enum import Enum as PyEnum
from typing import Optional, Dict, Any
from decimal import Decimal

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum,
    event,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates, Session

from spektiv.api.models.base import Base, TimestampMixin


class RiskProfile(str, PyEnum):
    """Enum for user risk tolerance profiles.

    CONSERVATIVE: Low risk tolerance, focus on capital preservation
    MODERATE: Balanced risk/reward approach (default)
    AGGRESSIVE: High risk tolerance, focus on growth
    """

    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class Settings(Base, TimestampMixin):
    """Settings model for user preferences and risk management.

    A settings record configures a user's trading preferences including
    risk tolerance, position sizing limits, and alert configurations.
    Each user has exactly one settings record (one-to-one relationship).

    Attributes:
        id: Primary key, auto-increment
        user_id: Foreign key to users.id (cascade delete, unique)
        risk_profile: Risk tolerance profile (CONSERVATIVE, MODERATE, AGGRESSIVE)
        risk_score: Numeric risk score 0-10 (Decimal 5,2)
        max_position_pct: Max % of portfolio for single position (Decimal 5,2)
        max_portfolio_risk_pct: Max portfolio-wide risk % (Decimal 5,2)
        investment_horizon_years: Investment time horizon in years
        alert_preferences: JSON config for notifications (email, SMS, push)
        user: Relationship to User model
        created_at: Timestamp when created (auto)
        updated_at: Timestamp when last updated (auto)

    Constraints:
        - user_id must be unique (one-to-one with User)
        - risk_score must be between 0 and 10 (inclusive)
        - max_position_pct must be between 0 and 100 (inclusive)
        - max_portfolio_risk_pct must be between 0 and 100 (inclusive)
        - investment_horizon_years must be >= 0

    Example:
        >>> from decimal import Decimal
        >>> settings = Settings(
        ...     user_id=1,
        ...     risk_profile=RiskProfile.MODERATE,
        ...     risk_score=Decimal("5.0"),
        ...     max_position_pct=Decimal("10.0"),
        ...     max_portfolio_risk_pct=Decimal("2.0"),
        ...     investment_horizon_years=5,
        ...     alert_preferences={
        ...         "email": {
        ...             "enabled": True,
        ...             "address": "user@example.com",
        ...             "alert_types": ["price_alert", "portfolio_alert"]
        ...         }
        ...     }
        ... )
        >>> session.add(settings)
        >>> await session.commit()
    """

    __tablename__ = "settings"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign key to user (cascade delete, unique for one-to-one)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User who owns these settings (one-to-one)"
    )

    # Risk profile (enum)
    risk_profile: Mapped[RiskProfile] = mapped_column(
        Enum(RiskProfile, native_enum=False, length=20),
        nullable=False,
        default=RiskProfile.MODERATE,
        comment="Risk tolerance: CONSERVATIVE, MODERATE, or AGGRESSIVE"
    )

    # Risk score (0-10 scale with 2 decimal places)
    risk_score: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        default=Decimal("5.0"),
        comment="Numeric risk score from 0 (conservative) to 10 (aggressive)"
    )

    # Position sizing limits (percentages with 2 decimal places)
    max_position_pct: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        default=Decimal("10.0"),
        comment="Maximum percentage of portfolio for single position (0-100)"
    )

    max_portfolio_risk_pct: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=False,
        default=Decimal("2.0"),
        comment="Maximum portfolio-wide risk percentage (0-100)"
    )

    # Investment horizon
    investment_horizon_years: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        comment="Investment time horizon in years"
    )

    # Alert preferences (JSON)
    alert_preferences: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="JSON configuration for email/SMS/push notifications"
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="settings"
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Unique constraint: one settings per user
        UniqueConstraint(
            "user_id",
            name="uq_settings_user_id"
        ),
        # Check constraints: valid numeric ranges
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 10",
            name="ck_settings_risk_score_range"
        ),
        CheckConstraint(
            "max_position_pct >= 0 AND max_position_pct <= 100",
            name="ck_settings_max_position_pct_range"
        ),
        CheckConstraint(
            "max_portfolio_risk_pct >= 0 AND max_portfolio_risk_pct <= 100",
            name="ck_settings_max_portfolio_risk_pct_range"
        ),
        CheckConstraint(
            "investment_horizon_years >= 0",
            name="ck_settings_investment_horizon_positive"
        ),
        # Note: Index on user_id is auto-created by unique=True parameter above
    )

    @validates("risk_profile")
    def validate_risk_profile(self, key: str, value) -> RiskProfile:
        """Validate and convert risk profile to RiskProfile enum.

        Args:
            key: Field name (risk_profile)
            value: Risk profile value (str or RiskProfile)

        Returns:
            RiskProfile enum value

        Raises:
            ValueError: If value is not a valid risk profile
        """
        # If already a RiskProfile, return it
        if isinstance(value, RiskProfile):
            return value

        # Try to convert string to RiskProfile
        if isinstance(value, str):
            try:
                return RiskProfile[value.upper()]
            except KeyError:
                raise ValueError(
                    f"Invalid risk profile '{value}'. "
                    f"Must be one of: {', '.join([p.value for p in RiskProfile])}"
                )

        # Invalid type
        raise ValueError(
            f"Risk profile must be string or RiskProfile enum, got {type(value)}"
        )

    def __repr__(self) -> str:
        """String representation of Settings.

        Returns:
            String showing settings ID, user ID, and risk profile
        """
        return (
            f"<Settings(id={self.id}, "
            f"user_id={self.user_id}, "
            f"risk_profile={self.risk_profile.value}, "
            f"risk_score={self.risk_score})>"
        )


# Event listener for before_flush validation
# This ensures business rules are validated before database commit
@event.listens_for(Session, "before_flush")
def validate_settings_before_flush(session, flush_context, instances):
    """Validate Settings objects before flushing to database.

    This event listener checks business rules that cannot be enforced
    by database constraints (data normalization, complex business logic).
    Database-enforced constraints (CheckConstraints) will raise IntegrityError
    from the database itself.

    Args:
        session: SQLAlchemy session
        flush_context: Flush context
        instances: Instances being flushed

    Raises:
        ValueError: If validation fails for business logic violations
    """
    for obj in session.new | session.dirty:
        if isinstance(obj, Settings):
            # Ensure alert_preferences is never None (should default to empty dict)
            if obj.alert_preferences is None:
                obj.alert_preferences = {}

            # Note: Numeric range validations (risk_score, max_position_pct, etc.)
            # are handled by database CheckConstraints and will raise IntegrityError
            # if violated. We don't duplicate those checks here.

            # Note: Nested JSON mutations (e.g., modifying settings.alert_preferences["key"]["nested"] = value)
            # are not automatically tracked by SQLAlchemy. Users should either:
            # 1. Reassign the entire dict: settings.alert_preferences = {...}
            # 2. Use flag_modified(settings, "alert_preferences") explicitly
            # 3. Use a custom MutableDict implementation for nested tracking
