from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field, field_validator

from .portfolio import PortfolioConfig
from .trading import Trade


class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BacktestConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(default="Backtest")
    description: str | None = None

    tickers: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    interval: str = Field(default="1d")

    portfolio_config: PortfolioConfig = Field(default_factory=PortfolioConfig)

    warmup_period: int = Field(default=20, ge=0)
    rebalance_frequency: str | None = Field(default=None)

    use_agent_pipeline: bool = Field(default=True)
    agent_config: dict = Field(default_factory=dict)

    benchmark_ticker: str | None = Field(default="SPY")
    risk_free_rate: Decimal = Field(default=Decimal("0.05"), ge=0)

    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValueError("end_date must be > start_date")
        return v

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str]) -> list[str]:
        return [t.upper().strip() for t in v]

    @computed_field
    @property
    def trading_days_estimate(self) -> int:
        delta = self.end_date - self.start_date
        return int(delta.days * 252 / 365)


class EquityCurvePoint(BaseModel):
    timestamp: datetime
    equity: Decimal
    cash: Decimal
    positions_value: Decimal
    benchmark_value: Decimal | None = None
    drawdown: Decimal = Field(default=Decimal("0"))
    drawdown_percent: Decimal = Field(default=Decimal("0"))


class TradeLog(BaseModel):
    trades: list[Trade] = Field(default_factory=list)
    total_trades: int = Field(default=0, ge=0)
    winning_trades: int = Field(default=0, ge=0)
    losing_trades: int = Field(default=0, ge=0)
    break_even_trades: int = Field(default=0, ge=0)

    @computed_field
    @property
    def win_rate(self) -> Decimal | None:
        if self.total_trades == 0:
            return None
        return Decimal(self.winning_trades) / Decimal(self.total_trades) * 100

    @computed_field
    @property
    def loss_rate(self) -> Decimal | None:
        if self.total_trades == 0:
            return None
        return Decimal(self.losing_trades) / Decimal(self.total_trades) * 100

    def add_trade(self, trade: Trade) -> None:
        self.trades.append(trade)
        self.total_trades += 1
        if trade.is_closed and trade.pnl is not None:
            if trade.pnl > 0:
                self.winning_trades += 1
            elif trade.pnl < 0:
                self.losing_trades += 1
            else:
                self.break_even_trades += 1

    @property
    def gross_profit(self) -> Decimal:
        return sum(
            t.pnl for t in self.trades if t.is_closed and t.pnl and t.pnl > 0
        ) or Decimal("0")

    @property
    def gross_loss(self) -> Decimal:
        return abs(
            sum(t.pnl for t in self.trades if t.is_closed and t.pnl and t.pnl < 0)
            or Decimal("0")
        )

    @property
    def profit_factor(self) -> Decimal | None:
        if self.gross_loss == 0:
            return None
        return self.gross_profit / self.gross_loss

    @property
    def avg_win(self) -> Decimal | None:
        wins = [t.pnl for t in self.trades if t.is_closed and t.pnl and t.pnl > 0]
        if not wins:
            return None
        return sum(wins) / len(wins)

    @property
    def avg_loss(self) -> Decimal | None:
        losses = [t.pnl for t in self.trades if t.is_closed and t.pnl and t.pnl < 0]
        if not losses:
            return None
        return sum(losses) / len(losses)

    @property
    def avg_holding_period(self) -> float | None:
        periods = [
            t.holding_period for t in self.trades if t.holding_period is not None
        ]
        if not periods:
            return None
        return sum(periods) / len(periods)


class BacktestMetrics(BaseModel):
    total_return: Decimal = Field(default=Decimal("0"))
    total_return_percent: Decimal = Field(default=Decimal("0"))
    annualized_return: Decimal = Field(default=Decimal("0"))

    benchmark_return: Decimal | None = None
    benchmark_return_percent: Decimal | None = None
    alpha: Decimal | None = None
    beta: Decimal | None = None

    volatility: Decimal = Field(default=Decimal("0"), ge=0)
    annualized_volatility: Decimal = Field(default=Decimal("0"), ge=0)
    downside_volatility: Decimal = Field(default=Decimal("0"), ge=0)

    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    calmar_ratio: Decimal | None = None
    information_ratio: Decimal | None = None

    max_drawdown: Decimal = Field(default=Decimal("0"), ge=0)
    max_drawdown_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    max_drawdown_duration: int | None = None
    avg_drawdown: Decimal = Field(default=Decimal("0"), ge=0)

    total_trades: int = Field(default=0, ge=0)
    win_rate: Decimal | None = Field(default=None, ge=0, le=100)
    profit_factor: Decimal | None = None
    avg_trade_pnl: Decimal | None = None
    avg_win: Decimal | None = None
    avg_loss: Decimal | None = None
    largest_win: Decimal | None = None
    largest_loss: Decimal | None = None
    avg_holding_period_days: float | None = None

    total_commission: Decimal = Field(default=Decimal("0"), ge=0)
    total_slippage: Decimal = Field(default=Decimal("0"), ge=0)

    trading_days: int = Field(default=0, ge=0)
    start_equity: Decimal = Field(gt=0)
    end_equity: Decimal = Field(gt=0)

    def to_summary_dict(self) -> dict:
        return {
            "Performance": {
                "Total Return": f"{self.total_return_percent:.2f}%",
                "Annualized Return": f"{self.annualized_return:.2f}%",
                "Sharpe Ratio": f"{self.sharpe_ratio:.2f}"
                if self.sharpe_ratio
                else "N/A",
                "Sortino Ratio": f"{self.sortino_ratio:.2f}"
                if self.sortino_ratio
                else "N/A",
                "Max Drawdown": f"{self.max_drawdown_percent:.2f}%",
            },
            "Risk": {
                "Volatility (Ann.)": f"{self.annualized_volatility:.2f}%",
                "Calmar Ratio": f"{self.calmar_ratio:.2f}"
                if self.calmar_ratio
                else "N/A",
                "Beta": f"{self.beta:.2f}" if self.beta else "N/A",
            },
            "Trading": {
                "Total Trades": self.total_trades,
                "Win Rate": f"{self.win_rate:.1f}%" if self.win_rate else "N/A",
                "Profit Factor": f"{self.profit_factor:.2f}"
                if self.profit_factor
                else "N/A",
                "Avg Holding Period": f"{self.avg_holding_period_days:.1f} days"
                if self.avg_holding_period_days
                else "N/A",
            },
            "Costs": {
                "Total Commission": f"${self.total_commission:.2f}",
                "Total Slippage": f"${self.total_slippage:.2f}",
            },
        }


class BacktestResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    config: BacktestConfig
    metrics: BacktestMetrics
    trade_log: TradeLog
    equity_curve: list[EquityCurvePoint] = Field(default_factory=list)
    daily_returns: list[Decimal] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    status: BacktestStatus = Field(default=BacktestStatus.COMPLETED)
    error_message: str | None = None

    @computed_field
    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "config": {
                "name": self.config.name,
                "tickers": self.config.tickers,
                "start_date": self.config.start_date.isoformat(),
                "end_date": self.config.end_date.isoformat(),
                "initial_cash": float(self.config.portfolio_config.initial_cash),
            },
            "metrics": self.metrics.to_summary_dict(),
            "trade_summary": {
                "total_trades": self.trade_log.total_trades,
                "winning_trades": self.trade_log.winning_trades,
                "losing_trades": self.trade_log.losing_trades,
                "win_rate": float(self.trade_log.win_rate)
                if self.trade_log.win_rate
                else None,
            },
            "duration_seconds": self.duration_seconds,
            "status": self.status,
        }
