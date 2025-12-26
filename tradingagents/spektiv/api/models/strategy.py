"""Strategy model for trading strategies."""

from typing import Optional, Dict, Any
from sqlalchemy import String, Boolean, Integer, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spektiv.api.models.base import Base, TimestampMixin


class Strategy(Base, TimestampMixin):
    """Strategy model for storing trading strategies."""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship to user
    user: Mapped["User"] = relationship("User", back_populates="strategies")

    def __repr__(self) -> str:
        return f"<Strategy(id={self.id}, name='{self.name}', user_id={self.user_id})>"
