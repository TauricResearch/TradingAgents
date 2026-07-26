"""
TradingScheduler — APScheduler wrapper that drives AutoTrader on a daily calendar.

Three jobs per trading day (times configurable in tradingbot/config.py):

  pre_market  (default 08:00 ET)  — run agent analysis on full watchlist
  order_submit(default 09:35 ET)  — execute approved signals via broker
  post_market (default 16:30 ET)  — snapshot portfolio, run reflection

Usage:
    from tradingbot.scheduler import TradingScheduler
    sched = TradingScheduler(auto_trader, config)
    sched.start()          # blocking; Ctrl-C to stop

    # or: run one-shot jobs manually
    sched.run_pre_market()
    sched.run_order_submission()
    sched.run_post_market()
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Wraps APScheduler to fire AutoTrader jobs on a weekday-only schedule.

    Pending signals produced by pre_market are stored on the AutoTrader
    instance and consumed by order_submit, so the two jobs communicate
    through shared state rather than a queue.
    """

    def __init__(self, auto_trader, config: Dict[str, Any]):
        self._trader = auto_trader
        self._config = config
        self._timezone = config.get("timezone", "America/New_York")
        self._scheduler = self._build_scheduler()

    # ------------------------------------------------------------------ #
    # Public interface                                                      #
    # ------------------------------------------------------------------ #

    def start(self, blocking: bool = True) -> None:
        """Start the scheduler. Blocks until KeyboardInterrupt if blocking=True."""
        logger.info("TradingScheduler starting (tz=%s)", self._timezone)
        self._scheduler.start()
        if blocking:
            try:
                import time
                while True:
                    time.sleep(60)
            except (KeyboardInterrupt, SystemExit):
                logger.info("TradingScheduler shutting down")
                self._scheduler.shutdown()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------ #
    # One-shot job methods (also called by APScheduler triggers)          #
    # ------------------------------------------------------------------ #

    def run_pre_market(self, trade_date: Optional[str] = None) -> None:
        """
        Run agent analysis on the full watchlist.

        Results are cached on AutoTrader._pending so order_submit can
        execute them without re-running the (expensive) LLM pipeline.
        """
        if trade_date is None:
            trade_date = date.today().isoformat()
        watchlist = self._config.get("watchlist", [])
        logger.info("PRE-MARKET: analysing %d tickers for %s", len(watchlist), trade_date)

        for ticker in watchlist:
            try:
                ticker = ticker.upper()
                signal, reasoning, final_state = self._trader._run_analysis(ticker, trade_date)
                from tradingbot.broker.signal_mapper import SignalMapper
                mapper = self._trader._mapper
                instruction = mapper.map(signal)
                qty, price = self._trader._compute_qty(ticker, instruction)
                # Cache for order_submit phase
                self._trader._pending[ticker] = (instruction, qty, price, final_state, signal, reasoning)
                logger.info("Pre-market %s: signal=%s qty=%.4f price=%.2f", ticker, signal, qty, price)
            except Exception as exc:
                logger.exception("Pre-market analysis failed for %s: %s", ticker, exc)

    def run_order_submission(self, trade_date: Optional[str] = None) -> None:
        """
        Execute all pending signals that passed the risk gate.
        Drains AutoTrader._pending after processing.
        """
        if trade_date is None:
            trade_date = date.today().isoformat()

        pending = dict(self._trader._pending)
        self._trader._pending.clear()

        if not pending:
            logger.info("ORDER SUBMISSION: no pending signals")
            return

        logger.info("ORDER SUBMISSION: executing %d signals", len(pending))
        for ticker, payload in pending.items():
            instruction, qty, price, final_state, signal, reasoning = payload
            try:
                if not instruction.should_trade or qty <= 0:
                    logger.info("Skipping %s (no trade required)", ticker)
                    continue

                verdict = self._trader._risk_gate.validate(ticker, instruction, qty, price)
                if not verdict.approved:
                    logger.warning("REJECTED %s: %s", ticker, verdict.reason)
                    continue

                final_qty = verdict.adjusted_qty or qty
                outcome = self._trader._execute(
                    ticker, instruction, final_qty, signal, reasoning, trade_date, final_state
                )
                logger.info("EXECUTED %s: %s", ticker, outcome)

            except Exception as exc:
                logger.exception("Order submission failed for %s: %s", ticker, exc)

    def run_post_market(self, snapshot_date: Optional[str] = None) -> None:
        """Take portfolio snapshot and trigger agent reflection."""
        if snapshot_date is None:
            snapshot_date = date.today().isoformat()
        logger.info("POST-MARKET: taking snapshot for %s", snapshot_date)
        try:
            self._trader.post_market(snapshot_date)
        except Exception as exc:
            logger.exception("Post-market job failed: %s", exc)

    # ------------------------------------------------------------------ #
    # APScheduler setup                                                    #
    # ------------------------------------------------------------------ #

    def _build_scheduler(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise ImportError(
                "apscheduler is required. Install with: pip install apscheduler"
            ) from exc

        scheduler = BackgroundScheduler(timezone=self._timezone)

        pre_h, pre_m = self._parse_time(self._config.get("pre_market_time", "08:00"))
        ord_h, ord_m = self._parse_time(self._config.get("order_submission_time", "09:35"))
        post_h, post_m = self._parse_time(self._config.get("post_market_time", "16:30"))

        # Monday–Friday only (day_of_week='mon-fri')
        scheduler.add_job(
            self.run_pre_market,
            CronTrigger(day_of_week="mon-fri", hour=pre_h, minute=pre_m, timezone=self._timezone),
            id="pre_market",
            name="Pre-market analysis",
            misfire_grace_time=300,
        )
        scheduler.add_job(
            self.run_order_submission,
            CronTrigger(day_of_week="mon-fri", hour=ord_h, minute=ord_m, timezone=self._timezone),
            id="order_submit",
            name="Order submission",
            misfire_grace_time=300,
        )
        scheduler.add_job(
            self.run_post_market,
            CronTrigger(day_of_week="mon-fri", hour=post_h, minute=post_m, timezone=self._timezone),
            id="post_market",
            name="Post-market reflection",
            misfire_grace_time=300,
        )

        logger.info(
            "Scheduled jobs: pre_market=%02d:%02d, order_submit=%02d:%02d, post_market=%02d:%02d ET",
            pre_h, pre_m, ord_h, ord_m, post_h, post_m,
        )
        return scheduler

    @staticmethod
    def _parse_time(time_str: str):
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
