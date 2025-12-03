from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tradingagents.database.base import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tickers: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), default="1d", nullable=False)
    initial_cash: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_free_rate: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    use_agent_pipeline: Mapped[bool] = mapped_column(default=True, nullable=False)
    agent_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", name="backtest_status"),
        default="pending",
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    metrics: Mapped["BacktestMetricsRecord | None"] = relationship(
        "BacktestMetricsRecord",
        back_populates="backtest_run",
        uselist=False,
        cascade="all, delete-orphan",
    )
    trades: Mapped[list["BacktestTrade"]] = relationship(
        "BacktestTrade", back_populates="backtest_run", cascade="all, delete-orphan"
    )
    equity_curve: Mapped[list["EquityCurveRecord"]] = relationship(
        "EquityCurveRecord", back_populates="backtest_run", cascade="all, delete-orphan"
    )


class BacktestMetricsRecord(Base):
    __tablename__ = "backtest_metrics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    backtest_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_runs.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    total_return: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_return_percent: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    annualized_return: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    annualized_volatility: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    downside_volatility: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    sortino_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    calmar_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    information_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown_percent: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    max_drawdown_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_trade_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_win: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_win: Mapped[float | None] = mapped_column(Float, nullable=True)
    largest_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_holding_period_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    trading_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_equity: Mapped[float] = mapped_column(Float, nullable=False)
    end_equity: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    backtest_run: Mapped["BacktestRun"] = relationship(
        "BacktestRun", back_populates="metrics"
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    backtest_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backtest_runs.id"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(
        Enum("buy", "sell", name="trade_side"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exit_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_closed: Mapped[bool] = mapped_column(default=False, nullable=False)
    holding_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    backtest_run: Mapped["BacktestRun"] = relationship(
        "BacktestRun", back_populates="trades"
    )


class EquityCurveRecord(Base):
    __tablename__ = "equity_curve_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    backtest_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backtest_runs.id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    positions_value: Mapped[float] = mapped_column(Float, nullable=False)
    benchmark_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    drawdown_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    backtest_run: Mapped["BacktestRun"] = relationship(
        "BacktestRun", back_populates="equity_curve"
    )
