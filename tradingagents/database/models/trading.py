from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingagents.database.base import Base

if TYPE_CHECKING:
    from tradingagents.database.models.analysis import AnalysisSession


class TradingDecision(Base):
    __tablename__ = "trading_decisions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_sessions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(
        Enum("buy", "sell", "hold", name="trade_decision"),
        nullable=False,
    )
    trader_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_decision_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    session: Mapped["AnalysisSession"] = relationship(
        "AnalysisSession", back_populates="trading_decision"
    )
    execution: Mapped["TradeExecution | None"] = relationship(
        "TradeExecution",
        back_populates="decision",
        uselist=False,
        cascade="all, delete-orphan",
    )


class TradeExecution(Base):
    __tablename__ = "trade_executions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("trading_decisions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str] = mapped_column(
        Enum("buy", "sell", "hold", name="trade_action"),
        nullable=False,
    )
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "executed", "cancelled", "failed", name="execution_status"),
        default="pending",
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    decision: Mapped["TradingDecision"] = relationship(
        "TradingDecision", back_populates="execution"
    )


class TradeReflection(Base):
    __tablename__ = "trade_reflections"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    original_decision: Mapped[str] = mapped_column(
        Enum("buy", "sell", "hold", name="reflection_decision"),
        nullable=False,
    )
    actual_outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reflection_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)
    profit_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
