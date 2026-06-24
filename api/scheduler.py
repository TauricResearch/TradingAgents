import datetime
import json
import logging
import os
import sqlite3
import threading
from typing import Optional

import redis
import redis.asyncio as aioredis

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from api.config import REDIS_URL
from api.database import get_db_connection
from api.signals_engine import normalize_signal

logger = logging.getLogger("pulse-trading-signals-service")

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)


class RedisSSEHub:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url

    def broadcast(self, signal: dict) -> None:
        try:
            r = redis.from_url(self._redis_url, decode_responses=True)
            r.publish("pulse:trading_signals", json.dumps(signal, default=str))
            logger.info("Signal broadcast to Redis channel 'pulse:trading_signals'")
        except Exception as e:
            logger.error("Redis broadcast failed: %s", e)


sse_hub = RedisSSEHub(REDIS_URL)


class SignalScheduler:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.check_interval_seconds = int(
            os.getenv("TRADING_SIGNALS_CHECK_INTERVAL_SECONDS", "60")
        )
        self.run_cadence_hours = int(os.getenv("TRADING_SIGNALS_CADENCE_HOURS", "24"))

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("SignalScheduler started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        import time

        while self._running:
            try:
                self.run_scheduler_cycle()
            except Exception as e:
                logger.error("Scheduler cycle error: %s", e)
            for _ in range(self.check_interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

    def run_scheduler_cycle(self, force_ticker: Optional[str] = None) -> None:
        conn = get_db_connection()
        tickers = []
        try:
            if force_ticker:
                row = conn.execute(
                    "SELECT ticker, asset_type FROM watchlist_tickers WHERE ticker = ?",
                    (force_ticker.upper(),),
                ).fetchone()
                if row:
                    tickers = [dict(row)]
            else:
                tickers = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT ticker, asset_type FROM watchlist_tickers"
                    ).fetchall()
                ]
        finally:
            conn.close()

        for t in tickers:
            ticker, asset_type = t["ticker"], t["asset_type"]
            conn = get_db_connection()
            run_needed = True
            latest_sig = None
            try:
                latest_sig = conn.execute(
                    "SELECT generated_at, signal_type, reasoning_summary FROM trading_signals "
                    "WHERE ticker = ? ORDER BY generated_at DESC LIMIT 1",
                    (ticker,),
                ).fetchone()
                if latest_sig and not force_ticker:
                    fmt = (
                        "%Y-%m-%d %H:%M:%S"
                        if "." not in latest_sig["generated_at"]
                        else "%Y-%m-%d %H:%M:%S.%f"
                    )
                    last_run = datetime.datetime.strptime(
                        latest_sig["generated_at"], fmt
                    )
                    if (datetime.datetime.now() - last_run) < datetime.timedelta(
                        hours=self.run_cadence_hours
                    ):
                        run_needed = False
            finally:
                conn.close()

            if run_needed:
                logger.info("Running TradingAgents for %s", ticker)
                try:
                    self.execute_agent_run(ticker, asset_type, latest_sig)
                except Exception as e:
                    logger.error("Agent run failed for %s: %s", ticker, e)

    def execute_agent_run(
        self, ticker: str, asset_type: str, latest_sig: Optional[sqlite3.Row] = None
    ) -> None:
        config = {**DEFAULT_CONFIG, "output_language": "English"}
        graph = TradingAgentsGraph(config=config, debug=False)
        trade_date = datetime.datetime.now().strftime("%Y-%m-%d")
        final_state, _ = graph.propagate(ticker, trade_date, asset_type=asset_type)

        signal_dict = normalize_signal(ticker, asset_type, final_state)

        if latest_sig and (
            latest_sig["signal_type"] == signal_dict["signal_type"]
            and latest_sig["reasoning_summary"] == signal_dict["reasoning_summary"]
        ):
            logger.info("Skipping duplicate signal for %s (thesis unchanged).", ticker)
            return

        conn = get_db_connection()
        try:
            conn.execute(
                """
                INSERT INTO trading_signals (
                    id, ticker, asset_type, signal_type, confidence, time_horizon,
                    price_target, entry_price, stop_loss, position_sizing,
                    reasoning_summary, generated_at, source_run_id,
                    name, grade, rr, agent_votes, sentiment_score, sentiment_band,
                    market_report, news_report, fundamentals_report, sentiment_report,
                    pm_report, trader_report, investment_debate, risk_debate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_dict["id"],
                    signal_dict["ticker"],
                    signal_dict["asset_type"],
                    signal_dict["signal_type"],
                    signal_dict["confidence"],
                    signal_dict["time_horizon"],
                    signal_dict["price_target"],
                    signal_dict["entry_price"],
                    signal_dict["stop_loss"],
                    signal_dict["position_sizing"],
                    signal_dict["reasoning_summary"],
                    signal_dict["generated_at"].strftime("%Y-%m-%d %H:%M:%S.%f"),
                    signal_dict["source_run_id"],
                    signal_dict.get("name"),
                    signal_dict.get("grade"),
                    signal_dict.get("rr"),
                    json.dumps(signal_dict["agent_votes"])
                    if signal_dict.get("agent_votes")
                    else None,
                    signal_dict.get("sentiment_score"),
                    signal_dict.get("sentiment_band"),
                    signal_dict.get("market_report"),
                    signal_dict.get("news_report"),
                    signal_dict.get("fundamentals_report"),
                    signal_dict.get("sentiment_report"),
                    signal_dict.get("pm_report"),
                    signal_dict.get("trader_report"),
                    signal_dict.get("investment_debate"),
                    signal_dict.get("risk_debate"),
                ),
            )
            conn.commit()
            logger.info(
                "Signal saved for %s: %s", ticker, signal_dict["signal_type"].upper()
            )
        finally:
            conn.close()

        sse_hub.broadcast(signal_dict)


scheduler = SignalScheduler()
