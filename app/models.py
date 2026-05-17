"""
SQLAlchemy ORM models for Python-owned tables.

The shared Neon database has a Prisma-owned half (User, Role, App,
AppMember, etc. — managed from the Node side) and a Python-owned half
(runs, decisions, agent_reports — managed here). This file declares
the Python-owned half.

We don't model the Prisma-owned tables here. user_id columns are plain
String FKs without an SQLAlchemy ForeignKey constraint — the constraint
exists at the DB level (added in the initial Alembic migration). Why:
modeling Prisma tables in two places drifts; pure schema-level FK is
enough for referential integrity without doubling-up the ORM layer.

Treat this file as a python-temp-pro template — replace these three
models with whatever the spawned service needs.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db import Base


def _uuid() -> str:
    """UUID4 hex string — matches the format Prisma uses for User.id."""
    return str(uuid4())


class Run(Base):
    """
    A single multi-agent analysis run. Created by the Node-side worker
    (lyceum-fund/apps/worker) when a user kicks off `analyzeTicker`;
    state transitions managed here as the TradingAgents pipeline runs.

    status values:
      - pending    — created, not yet started
      - running    — TradingAgents in flight
      - complete   — finished successfully; decision row exists
      - failed     — exception during run; see metadata for details
      - cancelled  — operator cancelled (future)
    """

    __tablename__ = "runs"

    id           = Column(String, primary_key=True, default=_uuid)
    user_id      = Column(String, nullable=False)          # FK to User.id (Prisma-owned)
    ticker       = Column(String, nullable=False)
    # Trade date the analysis targets. Stored as ISO string (YYYY-MM-DD) so
    # we don't have to argue about timezones — TradingAgents treats this
    # opaquely.
    trade_date   = Column(String, nullable=False)
    status       = Column(String, nullable=False, default="pending")
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    decisions     = relationship("Decision",    back_populates="run", cascade="all, delete-orphan")
    agent_reports = relationship("AgentReport", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_runs_user_id_created_at", "user_id", "created_at"),
        Index("ix_runs_status",             "status"),
    )


class Decision(Base):
    """
    Final BUY/SELL/HOLD verdict from the TradingAgents pipeline plus the
    rationale text. One per completed run.
    """

    __tablename__ = "decisions"

    id         = Column(String, primary_key=True, default=_uuid)
    run_id     = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    decision   = Column(String, nullable=False)   # "BUY" | "SELL" | "HOLD"
    rationale  = Column(Text,   nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("Run", back_populates="decisions")

    __table_args__ = (
        Index("ix_decisions_run_id", "run_id"),
    )


class AgentReport(Base):
    """
    Per-step output from a single agent in the TradingAgents pipeline.
    Replaces TauricResearch's `~/.tradingagents/memory/trading_memory.md`
    file-based persistence (TT-182c will wire the actual swap).

    agent_name examples:
      - "market_analyst"
      - "social_media_analyst"
      - "news_analyst"
      - "fundamentals_analyst"
      - "bull_researcher"
      - "bear_researcher"
      - "trader"
      - "risk_manager"
    """

    __tablename__ = "agent_reports"

    id         = Column(String, primary_key=True, default=_uuid)
    run_id     = Column(String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String, nullable=False)
    content    = Column(Text,   nullable=False)
    # TT-295: per-agent structured extraction. Pydantic schemas in
    # app/services/extractors/schemas.py define the per-agent shape;
    # callbacks.py runs a gpt-4o-mini extractor on every chain end.
    # Null when extraction fails or no schema is defined for the agent.
    #
    # Python attr is `report_metadata`, not `metadata`, because the latter
    # is reserved on SQLAlchemy's declarative Base (Base.metadata is the
    # schema's MetaData instance). The DB column is still named "metadata"
    # via the explicit `name=` arg — Prisma + GraphQL both read it as
    # `metadata` since they only see the column name.
    report_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("Run", back_populates="agent_reports")

    __table_args__ = (
        Index("ix_agent_reports_run_id",          "run_id"),
        Index("ix_agent_reports_run_id_agent",    "run_id", "agent_name"),
        # GIN index on metadata — enables future filtering like "all
        # market_analyst reports with RSI > 70" via JSONB containment.
        Index("ix_agent_reports_metadata", "metadata", postgresql_using="gin"),
    )
