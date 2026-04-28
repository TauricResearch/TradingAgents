"""
AutoTrader — the central orchestrator that wires all layers together.

Flow for each ticker on each trading day:
  1. Run TradingAgentsGraph.propagate(ticker, date) → raw signal
  2. SignalMapper converts signal → OrderInstruction + proposed qty
  3. RiskGate validates the instruction
  4. If approved, AlpacaBroker (or MockBroker) submits the order
  5. PortfolioManager records the fill + agent reasoning
  6. On SELL: realised P&L is fed back into TradingAgentsGraph.reflect_and_remember()

AutoTrader also handles:
  - Pre-market analysis runs (before market open)
  - Post-market reflection and daily snapshot
  - Human-in-the-loop approval mode (optional)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from tradingbot.broker.base import BrokerAdapter, OrderSide, OrderType
from tradingbot.broker.signal_mapper import SignalMapper
from tradingbot.portfolio.database import PortfolioDatabase
from tradingbot.portfolio.manager import PortfolioManager
from tradingbot.risk.gate import RiskGate

logger = logging.getLogger(__name__)


class AutoTrader:
    """
    Ties TradingAgentsGraph, RiskGate, BrokerAdapter, and PortfolioManager
    into a single callable pipeline.

    Usage (automated):
        trader = AutoTrader(graph, broker, db, config)
        trader.run_watchlist(["AAPL", "NVDA"])

    Usage (human-in-the-loop):
        trader = AutoTrader(graph, broker, db, config, require_approval=True)
        trader.run_watchlist(["AAPL"])
        # → prints signal + plan, waits for y/n before executing
    """

    def __init__(
        self,
        trading_graph,                 # TradingAgentsGraph instance
        broker: BrokerAdapter,
        db: PortfolioDatabase,
        config: Dict[str, Any],
        require_approval: bool = False,
    ):
        self._graph = trading_graph
        self._broker = broker
        self._db = db
        self._config = config
        self._require_approval = require_approval

        self._portfolio = PortfolioManager(broker, db)
        self._risk_gate = RiskGate(
            broker=broker,
            db=db,
            max_single_position_pct=config.get("max_single_position_pct", 0.10),
            max_total_exposure_pct=config.get("max_total_exposure_pct", 0.80),
            daily_loss_limit_pct=config.get("daily_loss_limit_pct", -0.02),
            min_cash_reserve=config.get("min_cash_reserve", 1_000.0),
            require_market_open=not config.get("paper_trading", True),
        )
        self._mapper = SignalMapper(
            full_position_pct=config.get("full_position_pct", 0.05),
            partial_position_pct=config.get("partial_position_pct", 0.03),
            partial_exit_pct=config.get("partial_exit_pct", 0.50),
        )

        # Pending signals waiting for human approval: ticker → (instruction, qty, price, state, signal)
        self._pending: Dict[str, Tuple] = {}

    # ------------------------------------------------------------------ #
    # Main entry points                                                    #
    # ------------------------------------------------------------------ #

    def run_watchlist(
        self,
        tickers: Optional[List[str]] = None,
        trade_date: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Analyse and (if approved) execute trades for every ticker in the watchlist.

        Args:
            tickers:    Override config watchlist for this run.
            trade_date: ISO date string (defaults to today).

        Returns:
            Dict mapping ticker → outcome string for logging / display.
        """
        if trade_date is None:
            trade_date = date.today().isoformat()
        watchlist = tickers or self._config.get("watchlist", [])

        outcomes: Dict[str, str] = {}
        for ticker in watchlist:
            try:
                outcome = self.run_single(ticker, trade_date)
                outcomes[ticker] = outcome
            except Exception as exc:
                logger.exception("Error processing %s: %s", ticker, exc)
                outcomes[ticker] = f"ERROR: {exc}"

        return outcomes

    def run_single(self, ticker: str, trade_date: Optional[str] = None) -> str:
        """
        Full pipeline for one ticker: analyse → risk-check → execute.

        Returns a human-readable outcome string.
        """
        if trade_date is None:
            trade_date = date.today().isoformat()

        ticker = ticker.upper()
        logger.info("=== AutoTrader: processing %s for %s ===", ticker, trade_date)

        # Step 1 — Analysis
        signal, reasoning, final_state = self._run_analysis(ticker, trade_date)
        logger.info("%s signal: %s", ticker, signal)

        # Step 2 — Map signal to order instruction
        instruction = self._mapper.map(signal)
        logger.info("%s instruction: %s (allocate %.0f%%)", ticker, instruction.reason,
                    instruction.allocation_fraction * 100)

        if not instruction.should_trade:
            return f"HOLD — {instruction.reason}"

        # Step 3 — Compute proposed quantity
        proposed_qty, proposed_price = self._compute_qty(ticker, instruction)
        if proposed_qty <= 0:
            return f"SKIP — could not compute valid quantity for {ticker}"

        # Step 4 — Human approval gate (optional)
        if self._require_approval:
            approved = self._ask_human(ticker, signal, instruction, proposed_qty, proposed_price, reasoning)
            if not approved:
                return "SKIPPED by user"

        # Step 5 — Risk gate
        verdict = self._risk_gate.validate(ticker, instruction, proposed_qty, proposed_price)
        if not verdict.approved:
            logger.warning("Risk gate REJECTED %s: %s", ticker, verdict.reason)
            return f"REJECTED by risk gate: {verdict.reason}"

        final_qty = verdict.adjusted_qty if verdict.adjusted_qty else proposed_qty
        logger.info("Risk gate APPROVED %s: %.4f shares", ticker, final_qty)

        # Step 6 — Execute
        return self._execute(ticker, instruction, final_qty, signal, reasoning, trade_date, final_state)

    # ------------------------------------------------------------------ #
    # Post-market jobs                                                     #
    # ------------------------------------------------------------------ #

    def post_market(self, snapshot_date: Optional[str] = None) -> None:
        """
        End-of-day tasks: take a portfolio snapshot and log performance.
        Call this after market close (e.g. 4:30 PM ET).
        """
        snap = self._portfolio.take_snapshot(snapshot_date)
        metrics = self._portfolio.get_performance_metrics()
        logger.info(
            "Post-market summary | equity=$%.2f | daily_pnl=$%.2f (%.2f%%) | "
            "win_rate=%.1f%% | sharpe=%.2f | max_dd=%.2f%%",
            snap.total_value,
            snap.daily_pnl,
            snap.daily_pnl_pct * 100,
            metrics.win_rate * 100,
            metrics.sharpe_ratio,
            metrics.max_drawdown * 100,
        )

    # ------------------------------------------------------------------ #
    # Accessors for the dashboard                                          #
    # ------------------------------------------------------------------ #

    @property
    def portfolio(self) -> PortfolioManager:
        return self._portfolio

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _run_analysis(self, ticker: str, trade_date: str):
        """Run TradingAgentsGraph and return (signal, reasoning, state)."""
        final_state, signal = self._graph.propagate(ticker, trade_date)
        reasoning = final_state.get("final_trade_decision", "")
        return signal, reasoning, final_state

    def _compute_qty(self, ticker: str, instruction) -> Tuple[float, float]:
        """Compute proposed share quantity from account state and current price."""
        try:
            price = self._broker.get_latest_price(ticker)
        except Exception as exc:
            logger.error("Could not fetch price for %s: %s", ticker, exc)
            return 0.0, 0.0

        account = self._broker.get_account()

        if instruction.side == OrderSide.BUY:
            qty = self._mapper.compute_buy_qty(instruction, account.cash, price)
        else:
            pos = self._broker.get_position(ticker)
            held = pos.qty if pos else 0.0
            qty = self._mapper.compute_sell_qty(instruction, held)

        return qty, price

    def _execute(
        self,
        ticker: str,
        instruction,
        qty: float,
        signal: str,
        reasoning: str,
        trade_date: str,
        final_state: dict,
    ) -> str:
        """Submit order and record it; handle reflection on SELL."""
        try:
            order = self._broker.submit_order(
                ticker=ticker,
                qty=qty,
                side=instruction.side,
                order_type=OrderType.MARKET,
            )
        except Exception as exc:
            logger.exception("Order submission failed for %s: %s", ticker, exc)
            return f"ORDER FAILED: {exc}"

        if instruction.side == OrderSide.SELL:
            trade, realized_pnl = self._portfolio.close_and_record(
                order=order,
                signal=signal,
                agent_reasoning=reasoning,
                trade_date=trade_date,
            )
            # Close the reflection loop — agents learn from this outcome.
            try:
                self._graph.reflect_and_remember(realized_pnl)
                logger.info("Agent memory updated with P&L $%.2f for %s", realized_pnl, ticker)
            except Exception as exc:
                logger.warning("Reflection failed for %s: %s", ticker, exc)
            return (
                f"SOLD {qty:.4f} shares @ ${order.filled_avg_price:.2f} | "
                f"realised P&L ${realized_pnl:+.2f}"
            )
        else:
            self._portfolio.record_trade(
                order=order,
                signal=signal,
                agent_reasoning=reasoning,
                trade_date=trade_date,
            )
            return (
                f"BOUGHT {qty:.4f} shares @ ${order.filled_avg_price:.2f} | "
                f"signal={signal}"
            )

    def _ask_human(self, ticker, signal, instruction, qty, price, reasoning) -> bool:
        """Interactive approval prompt (used when require_approval=True)."""
        print(f"\n{'='*60}")
        print(f"  TRADE PROPOSAL: {ticker}")
        print(f"  Signal : {signal}")
        print(f"  Action : {instruction.side.value.upper()} {qty:.4f} shares @ ~${price:.2f}")
        print(f"  Value  : ~${qty * price:.2f}")
        print(f"  Reason : {instruction.reason}")
        print(f"  Agent summary (first 400 chars):\n{reasoning[:400]}")
        print(f"{'='*60}")
        try:
            answer = input("  Approve? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("y", "yes")
