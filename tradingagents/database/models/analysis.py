from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingagents.database.base import Base

if TYPE_CHECKING:
    from tradingagents.database.models.trading import TradingDecision


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", name="session_status"),
        default="pending",
        nullable=False,
    )

    analyst_reports: Mapped[list["AnalystReport"]] = relationship(
        "AnalystReport", back_populates="session", cascade="all, delete-orphan"
    )
    investment_debate: Mapped["InvestmentDebate | None"] = relationship(
        "InvestmentDebate",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    risk_debate: Mapped["RiskDebate | None"] = relationship(
        "RiskDebate",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    trading_decision: Mapped["TradingDecision | None"] = relationship(
        "TradingDecision",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AnalystReport(Base):
    __tablename__ = "analyst_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_sessions.id"), nullable=False, index=True
    )
    analyst_type: Mapped[str] = mapped_column(
        Enum("market", "sentiment", "news", "fundamentals", name="analyst_type"),
        nullable=False,
    )
    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    session: Mapped["AnalysisSession"] = relationship(
        "AnalysisSession", back_populates="analyst_reports"
    )


class InvestmentDebate(Base):
    __tablename__ = "investment_debates"

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
    bull_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    bear_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    debate_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    investment_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    debate_rounds: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    session: Mapped["AnalysisSession"] = relationship(
        "AnalysisSession", back_populates="investment_debate"
    )


class RiskDebate(Base):
    __tablename__ = "risk_debates"

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
    risky_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    safe_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    neutral_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    debate_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    debate_rounds: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    session: Mapped["AnalysisSession"] = relationship(
        "AnalysisSession", back_populates="risk_debate"
    )
