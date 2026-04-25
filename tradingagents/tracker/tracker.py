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

"""TradeTracker for recording live/paper trades with JSON persistence."""

import json
import os
from typing import Any, Dict, List, Optional

from tradingagents.backtest.models import PerformanceMetrics, TradeRecord
from tradingagents.backtest.performance import PerformanceCalculator


class TradeTracker:
    """Records and persists live/paper trades, provides filtering and
    performance analytics.

    Trades are stored per-ticker as JSON files under:
        {results_dir}/trades/{ticker}/trades.json
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self._storage_dir = config["results_dir"]
        self._persona = config.get("persona")
        self._calculator = PerformanceCalculator()
        self._trades: List[TradeRecord] = []
        self._load_existing()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_trade(
        self,
        ticker: str,
        trade_date: str,
        signal: str,
        price: float,
        quantity: int,
        source: str,
        agent_state: Dict[str, Any],
    ) -> TradeRecord:
        """Create a new TradeRecord, persist it to disk, and return it.

        Args:
            ticker: Stock ticker symbol.
            trade_date: Date of the trade (YYYY-MM-DD).
            signal: Trade signal — BUY, SELL, or HOLD.
            price: Entry price per share.
            quantity: Number of shares.
            source: Trade source — backtest, paper, or real.
            agent_state: Raw agent state dict captured at decision time.

        Returns:
            The newly created TradeRecord.
        """
        analyst_reports = self._extract_reports(agent_state)
        debate_summary = self._extract_debate(agent_state)
        risk_decision = self._extract_risk(agent_state)

        record = TradeRecord(
            ticker=ticker,
            trade_date=trade_date,
            signal=signal,
            entry_price=price,
            quantity=quantity,
            source=source,
            analyst_reports=analyst_reports,
            debate_summary=debate_summary,
            risk_decision=risk_decision,
            persona=self._persona,
        )

        self._trades.append(record)
        self._save_ticker(ticker)
        return record

    def close_position(
        self,
        ticker: str,
        exit_date: str,
        exit_price: float,
    ) -> TradeRecord:
        """Close the most recent open position for *ticker*.

        Fills exit fields and computes PnL.

        Args:
            ticker: Stock ticker symbol.
            exit_date: Date the position was closed (YYYY-MM-DD).
            exit_price: Price per share at exit.

        Returns:
            The updated TradeRecord with exit and PnL fields filled.

        Raises:
            ValueError: If no open position exists for the given ticker.
        """
        # Find the most recent open trade for this ticker (reverse search)
        target: Optional[TradeRecord] = None
        for trade in reversed(self._trades):
            if trade.ticker == ticker and trade.exit_price is None:
                target = trade
                break

        if target is None:
            raise ValueError(f"No open position found for ticker {ticker!r}")

        target.exit_date = exit_date
        target.exit_price = exit_price
        target.pnl = (exit_price - target.entry_price) * target.quantity
        target.pnl_pct = (
            ((exit_price - target.entry_price) / target.entry_price) * 100
        )

        self._save_ticker(ticker)
        return target

    def get_trades(
        self,
        ticker: Optional[str] = None,
        source: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[TradeRecord]:
        """Return trades matching the given filters.

        All filter parameters are optional; when ``None`` they are not applied.

        Args:
            ticker: Filter by ticker symbol.
            source: Filter by source (backtest, paper, real).
            start_date: Include trades on or after this date (YYYY-MM-DD).
            end_date: Include trades on or before this date (YYYY-MM-DD).

        Returns:
            List of matching TradeRecord objects.
        """
        result = self._trades

        if ticker is not None:
            result = [t for t in result if t.ticker == ticker]

        if source is not None:
            result = [t for t in result if t.source == source]

        if start_date is not None:
            result = [t for t in result if t.trade_date >= start_date]

        if end_date is not None:
            result = [t for t in result if t.trade_date <= end_date]

        return result

    def get_open_positions(self) -> List[TradeRecord]:
        """Return all trades that have not yet been closed (exit_price is None)."""
        return [t for t in self._trades if t.exit_price is None]

    def get_performance(
        self,
        ticker: Optional[str] = None,
        source: Optional[str] = None,
        benchmark: str = "SPY",
        initial_capital: float = 1_000_000.0,
    ) -> PerformanceMetrics:
        """Compute performance metrics for matching closed trades.

        Delegates calculation to :class:`PerformanceCalculator`.

        Args:
            ticker: Filter by ticker (optional).
            source: Filter by source (optional).
            benchmark: Benchmark ticker for alpha/beta (default ``SPY``).
            initial_capital: Starting capital assumption.

        Returns:
            PerformanceMetrics dataclass.
        """
        trades = self.get_trades(ticker=ticker, source=source)
        closed = [t for t in trades if t.exit_price is not None]

        if not closed:
            return self._calculator.calculate([], initial_capital, benchmark, "", "")

        dates = [t.trade_date for t in closed]
        exit_dates = [t.exit_date for t in closed if t.exit_date]
        start = min(dates) if dates else ""
        end = max(exit_dates) if exit_dates else ""

        return self._calculator.calculate(
            closed, initial_capital, benchmark, start, end
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save_ticker(self, ticker: str) -> None:
        """Write all trades for *ticker* to its JSON file on disk."""
        ticker_dir = os.path.join(self._storage_dir, "trades", ticker)
        os.makedirs(ticker_dir, exist_ok=True)

        ticker_trades = [t for t in self._trades if t.ticker == ticker]
        filepath = os.path.join(ticker_dir, "trades.json")

        with open(filepath, "w") as f:
            json.dump([t.to_dict() for t in ticker_trades], f, indent=2)

    def _load_existing(self) -> None:
        """Scan storage_dir/trades/ for existing JSON files and load them."""
        trades_root = os.path.join(self._storage_dir, "trades")
        if not os.path.isdir(trades_root):
            return

        for ticker_name in os.listdir(trades_root):
            ticker_dir = os.path.join(trades_root, ticker_name)
            if not os.path.isdir(ticker_dir):
                continue

            filepath = os.path.join(ticker_dir, "trades.json")
            if not os.path.isfile(filepath):
                continue

            with open(filepath) as f:
                data = json.load(f)

            for entry in data:
                self._trades.append(TradeRecord.from_dict(entry))

    # ------------------------------------------------------------------
    # Agent state extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_reports(state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract analyst reports from the agent state dict."""
        report_keys = (
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
        )
        return {k: state.get(k, "") for k in report_keys if k in state}

    @staticmethod
    def _extract_debate(state: Dict[str, Any]) -> str:
        """Extract investment debate summary from the agent state dict."""
        debate = state.get("investment_debate_state", {})
        if not debate:
            return ""

        parts = []
        if debate.get("bull_history"):
            parts.append(f"Bull: {debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"Bear: {debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"Judge: {debate['judge_decision']}")
        return "\n".join(parts)

    @staticmethod
    def _extract_risk(state: Dict[str, Any]) -> str:
        """Extract risk debate decision from the agent state dict."""
        risk = state.get("risk_debate_state", {})
        if not risk:
            return ""
        return risk.get("judge_decision", "")
