# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


_VALID_SOURCES = ("backtest", "paper", "real")
_VALID_SIGNALS = ("BUY", "SELL", "HOLD")


@dataclass
class TradeRecord:
    """A single trade entry produced by analysis or execution."""

    # Required fields
    ticker: str
    trade_date: str
    signal: str  # BUY, SELL, HOLD
    entry_price: float
    quantity: int
    source: str  # backtest, paper, real

    # Optional — filled when trade is closed
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    # Agent context captured at decision time
    analyst_reports: Dict[str, Any] = field(default_factory=dict)
    debate_summary: str = ""
    risk_decision: str = ""
    persona: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in _VALID_SOURCES:
            raise ValueError(
                f"source must be one of {_VALID_SOURCES}, got {self.source!r}"
            )
        if self.signal not in _VALID_SIGNALS:
            raise ValueError(
                f"signal must be one of {_VALID_SIGNALS}, got {self.signal!r}"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TradeRecord":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class PerformanceMetrics:
    """Aggregated performance statistics for a set of trades."""

    total_trades: int
    win_rate: float
    avg_return: float
    cumulative_return: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # days
    alpha: float
    beta: float
    profit_factor: float
    avg_holding_days: float
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    monthly_returns: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""

    ticker: str
    config_snapshot: Dict[str, Any]
    start_date: str
    end_date: str
    benchmark: str
    trades: List[TradeRecord]
    metrics: PerformanceMetrics
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)
