"""F2 BacktestHarness — orchestrator for the two invocation modes.

Watchlist mode: open + maturation (this file, Tasks 14-15).
Brief-scoped mode: open from persisted runs + maturation (Task 16).

The harness is decoupled from TradingAgentsGraph via the GraphRunner
Protocol so tests can substitute a fast mock. Same for prices via
PriceFallbackChain (or anything quacking get_bars(...) → Bars).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Protocol, Tuple

from tradingagents.backtest.prices import Resolution
from tradingagents.backtest.simulator import (
    compute_returns, max_drawdown, position_from_decision,
    sharpe_ratio, total_return, win_rate,
)
from tradingagents.backtest.reflection import write_outcome_log_on_close


class GraphRunner(Protocol):
    """Anything that can invoke a per-persona graph and persist a runs row."""
    def run(self, *, ticker: str, trade_date: str, persona_id: str,
            conn: sqlite3.Connection) -> Tuple[str, str]:
        """Return ``(run_id, decision)``. The runs row must already be written."""
        ...


@dataclass
class BacktestHarness:
    conn: sqlite3.Connection
    data_dir: str
    graph_runner: GraphRunner
    price_chain: object   # any get_bars(...) → Bars producer
    resolution: Resolution = Resolution.DAILY
    benchmark: str = "SPY"

    def run_watchlist(
        self,
        *,
        tickers: List[str],
        personas: List[str],
        start_date: date,
        end_date: date,
    ) -> int:
        """Open one backtest covering tickers × personas. Auto-mature if
        ``end_date <= today``. Returns the new ``backtest_id``."""
        backtest_id = self._insert_backtests_row(
            triggered_by_brief_id=None,
            universe=tickers,
            start_date=start_date,
            end_date=end_date,
        )

        for ticker in tickers:
            for persona_id in personas:
                self._open_forward_test(
                    backtest_id=backtest_id,
                    ticker=ticker,
                    persona_id=persona_id,
                    start_date=start_date,
                    end_date=end_date,
                )

        if end_date <= date.today():
            self._mature_all_open(backtest_id=backtest_id, end_date=end_date)
            self._close_backtest(backtest_id)

        return backtest_id

    def run_brief_scoped(
        self,
        *,
        brief_id: str,
        window_days: int = 30,
    ) -> int:
        """Open forward tests for every run_id in the brief.

        Reads the brief, resolves each run_id → (ticker, persona_id, decision,
        started_ts), opens a backtest_runs row using those decisions WITHOUT
        re-invoking the graph. Auto-matures if scheduled_close_date <= today.
        """
        brief_row = self.conn.execute(
            "SELECT generated_ts, run_ids FROM briefs WHERE brief_id = ?",
            (brief_id,),
        ).fetchone()
        if brief_row is None:
            raise ValueError(f"brief_id {brief_id!r} not found")
        generated_ts = brief_row["generated_ts"]
        run_ids = json.loads(brief_row["run_ids"])

        entry_date = date.fromisoformat(generated_ts.split("T")[0])
        end_date = entry_date + timedelta(days=window_days)

        seed_rows: List[Tuple[str, str, str, str]] = []
        for run_id in run_ids:
            r = self.conn.execute(
                "SELECT ticker, persona_id, decision FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if r is None:
                raise ValueError(
                    f"run_id {run_id!r} referenced by brief but missing"
                )
            seed_rows.append(
                (run_id, r["ticker"], r["persona_id"] or "",
                 r["decision"] or "HOLD")
            )

        universe = sorted({t for (_, t, _, _) in seed_rows})
        backtest_id = self._insert_backtests_row(
            triggered_by_brief_id=brief_id,
            universe=universe,
            start_date=entry_date,
            end_date=end_date,
        )

        for run_id, ticker, persona_id, decision in seed_rows:
            try:
                position = position_from_decision(decision)
            except ValueError:
                position = 0

            try:
                entry_price, price_source = self._fetch_spot_price(
                    ticker, entry_date,
                )
            except Exception as e:
                self._insert_backtest_run_errored(
                    backtest_id=backtest_id, ticker=ticker,
                    persona_id=persona_id, run_id=run_id,
                    error=f"entry price fetch failed: {e!r}",
                )
                continue

            try:
                benchmark_entry_price, _ = self._fetch_spot_price(
                    self.benchmark, entry_date,
                )
            except Exception:
                benchmark_entry_price = None

            metrics = {
                "status": "open",
                "run_id": run_id,
                "decision": decision,
                "position": position,
                "entry_date": entry_date.isoformat(),
                "entry_price": entry_price,
                "benchmark": self.benchmark,
                "benchmark_entry_price": benchmark_entry_price,
                "scheduled_close_date": end_date.isoformat(),
                "resolution": str(self.resolution.value),
                "price_source": price_source,
            }
            self.conn.execute(
                "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
                " VALUES (?, ?, ?, ?)",
                (backtest_id, persona_id, ticker, json.dumps(metrics)),
            )
            self.conn.commit()

        if end_date <= date.today():
            self._mature_all_open(backtest_id=backtest_id, end_date=end_date)
            self._close_backtest(backtest_id)

        return backtest_id

    # ---------- internals ----------

    def _insert_backtests_row(
        self,
        *,
        triggered_by_brief_id: Optional[str],
        universe: List[str],
        start_date: date,
        end_date: date,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO backtests "
            "(triggered_by_brief_id, universe, start_date, end_date, status, "
            " report_path, created_ts) VALUES (?, ?, ?, ?, 'open', NULL, ?)",
            (
                triggered_by_brief_id,
                json.dumps(universe),
                start_date.isoformat(),
                end_date.isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def _fetch_spot_price(
        self,
        ticker: str,
        target_date: date,
        *,
        lookback_days: int = 5,
    ) -> Tuple[float, str]:
        """Fetch the spot close price for ``ticker`` as of ``target_date``.

        Tries the exact date first. If empty (non-trading day — weekend,
        holiday), retries with a ``lookback_days``-day window and returns
        the most recent close. Matches trading convention: a decision on a
        Sunday uses Friday's close.

        Returns ``(price, source_name)``.
        """
        # First try: exact-date query (preserves prior semantics for tests
        # whose fixtures only respond to start==end).
        try:
            bars = self.price_chain.get_bars(
                ticker, target_date, target_date, self.resolution,
            )
        except Exception:
            bars = None
        if bars is not None and bars.bars:
            return bars.bars[0][1], bars.source

        # Fallback: look-back window for non-trading days.
        bars = self.price_chain.get_bars(
            ticker, target_date - timedelta(days=lookback_days), target_date,
            self.resolution,
        )
        if not bars.bars:
            raise RuntimeError(
                f"no bars for {ticker} in window "
                f"{target_date - timedelta(days=lookback_days)}..{target_date}"
            )
        return bars.bars[-1][1], bars.source

    def _open_forward_test(
        self,
        *,
        backtest_id: int,
        ticker: str,
        persona_id: str,
        start_date: date,
        end_date: date,
    ) -> None:
        # 1. Invoke the graph at start_date — produces runs row + decision.
        run_id, decision = self.graph_runner.run(
            ticker=ticker,
            trade_date=start_date.isoformat(),
            persona_id=persona_id,
            conn=self.conn,
        )

        # 2. Fetch entry price (allow look-back for non-trading start dates).
        try:
            entry_price, price_source = self._fetch_spot_price(ticker, start_date)
        except Exception as e:
            self._insert_backtest_run_errored(
                backtest_id=backtest_id, ticker=ticker, persona_id=persona_id,
                run_id=run_id, error=f"entry price fetch failed: {e!r}",
            )
            return

        # 3. Fetch entry benchmark price too (best-effort).
        try:
            benchmark_entry_price, _ = self._fetch_spot_price(self.benchmark, start_date)
        except Exception:
            benchmark_entry_price = None

        # 4. Translate decision → position.
        try:
            position = position_from_decision(decision)
        except ValueError:
            position = 0  # unknown → flat (HOLD-ish)

        metrics = {
            "status": "open",
            "run_id": run_id,
            "decision": decision,
            "position": position,
            "entry_date": start_date.isoformat(),
            "entry_price": entry_price,
            "benchmark": self.benchmark,
            "benchmark_entry_price": benchmark_entry_price,
            "scheduled_close_date": end_date.isoformat(),
            "resolution": str(self.resolution.value),
            "price_source": price_source,
        }
        self.conn.execute(
            "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
            " VALUES (?, ?, ?, ?)",
            (backtest_id, persona_id, ticker, json.dumps(metrics)),
        )
        self.conn.commit()

    def _insert_backtest_run_errored(
        self,
        *,
        backtest_id: int,
        ticker: str,
        persona_id: str,
        run_id: Optional[str],
        error: str,
    ) -> None:
        metrics = {
            "status": "errored",
            "run_id": run_id,
            "error": error,
            "errored_sources": [],
        }
        self.conn.execute(
            "INSERT INTO backtest_runs (backtest_id, persona_id, ticker, metrics)"
            " VALUES (?, ?, ?, ?)",
            (backtest_id, persona_id, ticker, json.dumps(metrics)),
        )
        self.conn.commit()

    def _mature_all_open(self, *, backtest_id: int, end_date: date) -> None:
        """Walk every open backtest_runs row for this backtest and close it."""
        rows = list(self.conn.execute(
            "SELECT btr_id, persona_id, ticker, metrics "
            "FROM backtest_runs WHERE backtest_id = ?",
            (backtest_id,),
        ))
        for row in rows:
            metrics = json.loads(row["metrics"])
            if metrics.get("status") != "open":
                continue
            self._mature_one(
                btr_id=row["btr_id"],
                persona_id=row["persona_id"],
                ticker=row["ticker"],
                metrics=metrics,
                end_date=end_date,
            )

    def _mature_one(
        self,
        *,
        btr_id: int,
        persona_id: str,
        ticker: str,
        metrics: dict,
        end_date: date,
    ) -> None:
        entry_date = date.fromisoformat(metrics["entry_date"])
        entry_price = metrics["entry_price"]
        position = metrics["position"]
        resolution = Resolution(metrics["resolution"])

        # Fetch the full window. Failures mark the row errored.
        try:
            bars = self.price_chain.get_bars(
                ticker, entry_date, end_date, resolution,
            )
        except Exception as e:
            metrics["status"] = "errored"
            metrics["error"] = f"price fetch failed during maturation: {e!r}"
            self._update_metrics(btr_id, metrics)
            return

        if not bars.bars:
            metrics["status"] = "errored"
            metrics["error"] = "empty bars for maturation window"
            self._update_metrics(btr_id, metrics)
            return

        exit_price = bars.bars[-1][1]
        returns = compute_returns(bars, position=position)

        # Benchmark — best-effort; if it fails, alpha defaults to total_return.
        try:
            bench_bars = self.price_chain.get_bars(
                self.benchmark, entry_date, end_date, resolution,
            )
            bench_entry = bench_bars.bars[0][1] if bench_bars.bars else None
            bench_exit = bench_bars.bars[-1][1] if bench_bars.bars else None
            if bench_entry and bench_entry > 0:
                bench_return = (bench_exit - bench_entry) / bench_entry
            else:
                bench_return = 0.0
        except Exception:
            bench_entry, bench_exit, bench_return = None, None, 0.0

        tr = total_return(entry=entry_price, exit=exit_price, position=position)
        metrics.update({
            "status": "closed",
            "close_date": end_date.isoformat(),
            "exit_price": exit_price,
            "benchmark_exit_price": bench_exit,
            "total_return": tr,
            "benchmark_return": bench_return,
            "alpha": tr - bench_return,
            "returns": returns,
            "sharpe": sharpe_ratio(returns, resolution=resolution),
            "max_drawdown": max_drawdown(returns),
            "win_rate": win_rate(returns),
            "holding_days_elapsed": (end_date - entry_date).days,
        })
        self._update_metrics(btr_id, metrics)

        write_outcome_log_on_close(
            self.conn,
            run_id=metrics["run_id"],
            ticker=ticker,
            persona_id=persona_id,
            decision=metrics["decision"],
            alpha=metrics["alpha"],
            total_return=metrics["total_return"],
            backtest_id=self._backtest_id_for(btr_id),
            close_date=metrics["close_date"],
            benchmark=self.benchmark,
        )

    def _update_metrics(self, btr_id: int, metrics: dict) -> None:
        self.conn.execute(
            "UPDATE backtest_runs SET metrics = ? WHERE btr_id = ?",
            (json.dumps(metrics), btr_id),
        )
        self.conn.commit()

    def _backtest_id_for(self, btr_id: int) -> int:
        row = self.conn.execute(
            "SELECT backtest_id FROM backtest_runs WHERE btr_id = ?", (btr_id,),
        ).fetchone()
        return row["backtest_id"]

    def _close_backtest(self, backtest_id: int) -> None:
        self.conn.execute(
            "UPDATE backtests SET status='closed' WHERE backtest_id=?",
            (backtest_id,),
        )
        self.conn.commit()
