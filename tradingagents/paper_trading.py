"""Forward-only paper portfolio with immutable decisions and price marks."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from tradingagents import backtest
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio_backtest import rating_score, target_weights

logger = logging.getLogger(__name__)


class DecisionWindowClosedError(ValueError):
    """Expected control flow when it is unsafe to freeze a new decision."""


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class PaperStore:
    """Small SQLite/Postgres ledger; all decision and mark rows are append-only."""

    _DDL = (
        """CREATE TABLE IF NOT EXISTS paper_runs (
            run_id TEXT PRIMARY KEY, created_utc REAL NOT NULL, config_json TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS paper_decisions (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, ticker TEXT NOT NULL,
            replicate INTEGER NOT NULL, created_utc REAL NOT NULL, action TEXT NOT NULL,
            score REAL NOT NULL, data_fingerprint TEXT NOT NULL,
            signal_fingerprint TEXT NOT NULL, final_decision TEXT NOT NULL,
            PRIMARY KEY (run_id, decision_date, ticker, replicate)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_targets (
            run_id TEXT NOT NULL, decision_date TEXT NOT NULL, entry_date TEXT NOT NULL,
            created_utc REAL NOT NULL, weights_json TEXT NOT NULL,
            PRIMARY KEY (run_id, decision_date)
        )""",
        """CREATE TABLE IF NOT EXISTS paper_marks (
            run_id TEXT NOT NULL, session_date TEXT NOT NULL, captured_utc REAL NOT NULL,
            nav REAL NOT NULL, benchmark_nav REAL NOT NULL, period_return REAL NOT NULL,
            benchmark_period_return REAL NOT NULL, turnover REAL NOT NULL,
            trading_cost REAL NOT NULL, borrow_cost REAL NOT NULL,
            weights_json TEXT NOT NULL, opens_json TEXT NOT NULL,
            benchmark_open REAL NOT NULL, target_decision_date TEXT,
            PRIMARY KEY (run_id, session_date)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_paper_target_entry ON paper_targets (run_id, entry_date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_target_entry "
        "ON paper_targets (run_id, entry_date)",
    )

    def __init__(self, url: str):
        if not url:
            raise ValueError("paper ledger database URL is required")
        self._sqlite = False
        self._media_store = None
        if url.startswith("sqlite:///") or "://" not in url:
            raw = url[len("sqlite:///"):] if url.startswith("sqlite:///") else url
            path = Path(raw).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path))
            self.conn.row_factory = sqlite3.Row
            self._sqlite = True
            for statement in self._DDL:
                self.conn.execute(statement)
            self.conn.commit()
        else:
            from sqlalchemy import create_engine

            from tradingagents.dataflows.media_store import _normalize_pg_url

            self.engine = create_engine(_normalize_pg_url(url), pool_pre_ping=True)
            with self.engine.begin() as conn:
                for statement in self._DDL:
                    conn.exec_driver_sql(statement)

    @contextmanager
    def _transaction(self):
        if self._sqlite:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        else:
            with self.engine.begin() as conn:
                yield conn

    def _execute(self, conn, sql: str, params: dict | None = None):
        if self._sqlite:
            return conn.execute(sql, params or {})
        from sqlalchemy import text

        return conn.execute(text(sql), params or {})

    def _rows(self, sql: str, params: dict | None = None) -> list[dict]:
        if self._sqlite:
            return [dict(row) for row in self.conn.execute(sql, params or {}).fetchall()]
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]

    def create_run(self, run_id: str, config: dict, created_utc: float) -> bool:
        existing = self._rows(
            "SELECT config_json FROM paper_runs WHERE run_id=:run_id", {"run_id": run_id}
        )
        encoded = _canonical(config)
        if existing:
            if existing[0]["config_json"] != encoded:
                raise ValueError(f"paper run {run_id!r} already exists with different config")
            return False
        with self._transaction() as conn:
            self._execute(
                conn,
                "INSERT INTO paper_runs (run_id,created_utc,config_json) "
                "VALUES (:run_id,:created_utc,:config_json)",
                {"run_id": run_id, "created_utc": created_utc, "config_json": encoded},
            )
        return True

    def run_config(self, run_id: str) -> dict:
        rows = self._rows(
            "SELECT config_json FROM paper_runs WHERE run_id=:run_id", {"run_id": run_id}
        )
        if not rows:
            raise ValueError(f"unknown paper run {run_id!r}")
        return json.loads(rows[0]["config_json"])

    def has_decision(self, run_id: str, decision_date: str) -> bool:
        return bool(self._rows(
            "SELECT 1 AS found FROM paper_targets "
            "WHERE run_id=:run_id AND decision_date=:decision_date",
            {"run_id": run_id, "decision_date": decision_date},
        ))

    def record_decision_set(
        self,
        run_id: str,
        decision_date: str,
        entry_date: str,
        created_utc: float,
        decisions: list[dict],
        weights: dict[str, float],
    ) -> None:
        """Atomically append a complete cross-section; duplicates always fail."""
        with self._transaction() as conn:
            for row in decisions:
                self._execute(conn, """
                    INSERT INTO paper_decisions
                    (run_id,decision_date,ticker,replicate,created_utc,action,score,
                     data_fingerprint,signal_fingerprint,final_decision)
                    VALUES (:run_id,:decision_date,:ticker,:replicate,:created_utc,:action,
                            :score,:data_fingerprint,:signal_fingerprint,:final_decision)
                """, {**row, "run_id": run_id, "decision_date": decision_date,
                       "created_utc": created_utc})
            self._execute(conn, """
                INSERT INTO paper_targets
                (run_id,decision_date,entry_date,created_utc,weights_json)
                VALUES (:run_id,:decision_date,:entry_date,:created_utc,:weights_json)
            """, {
                "run_id": run_id, "decision_date": decision_date,
                "entry_date": entry_date, "created_utc": created_utc,
                "weights_json": _canonical(weights),
            })

    def target_for_entry(self, run_id: str, entry_date: str) -> dict | None:
        rows = self._rows(
            "SELECT decision_date,weights_json FROM paper_targets "
            "WHERE run_id=:run_id AND entry_date=:entry_date",
            {"run_id": run_id, "entry_date": entry_date},
        )
        if not rows:
            return None
        if len(rows) > 1:
            raise ValueError(f"multiple paper targets enter on {entry_date}")
        return {
            "decision_date": rows[0]["decision_date"],
            "weights": json.loads(rows[0]["weights_json"]),
        }

    def first_entry_date(self, run_id: str) -> str | None:
        rows = self._rows(
            "SELECT MIN(entry_date) AS date FROM paper_targets WHERE run_id=:run_id",
            {"run_id": run_id},
        )
        return rows[0]["date"] if rows and rows[0]["date"] else None

    def latest_mark(self, run_id: str) -> dict | None:
        rows = self._rows(
            "SELECT * FROM paper_marks WHERE run_id=:run_id "
            "ORDER BY session_date DESC LIMIT 1", {"run_id": run_id},
        )
        if not rows:
            return None
        row = rows[0]
        row["weights"] = json.loads(row.pop("weights_json"))
        row["opens"] = json.loads(row.pop("opens_json"))
        return row

    def record_mark(self, run_id: str, mark: dict) -> None:
        payload = dict(mark)
        payload.update({
            "run_id": run_id,
            "weights_json": _canonical(payload.pop("weights")),
            "opens_json": _canonical(payload.pop("opens")),
        })
        with self._transaction() as conn:
            self._execute(conn, """
                INSERT INTO paper_marks
                (run_id,session_date,captured_utc,nav,benchmark_nav,period_return,
                 benchmark_period_return,turnover,trading_cost,borrow_cost,
                 weights_json,opens_json,benchmark_open,target_decision_date)
                VALUES (:run_id,:session_date,:captured_utc,:nav,:benchmark_nav,
                        :period_return,:benchmark_period_return,:turnover,:trading_cost,
                        :borrow_cost,:weights_json,:opens_json,:benchmark_open,
                        :target_decision_date)
            """, payload)

    def status(self, run_id: str) -> dict:
        config = self.run_config(run_id)
        decisions = self._rows(
            "SELECT COUNT(*) AS count, COUNT(DISTINCT decision_date) AS dates "
            "FROM paper_decisions WHERE run_id=:run_id", {"run_id": run_id},
        )[0]
        marks = self._rows(
            "SELECT COUNT(*) AS count, MIN(session_date) AS start_date, "
            "MAX(session_date) AS end_date FROM paper_marks WHERE run_id=:run_id",
            {"run_id": run_id},
        )[0]
        latest = self.latest_mark(run_id)
        return {
            "run_id": run_id,
            "config": config,
            "decision_rows": decisions["count"],
            "decision_dates": decisions["dates"],
            "mark_count": marks["count"],
            "start_date": marks["start_date"],
            "end_date": marks["end_date"],
            "nav": latest["nav"] if latest else 1.0,
            "benchmark_nav": latest["benchmark_nav"] if latest else 1.0,
        }

    def close(self) -> None:
        if self._sqlite:
            self.conn.close()
        else:
            self.engine.dispose()


def _calendar():
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise RuntimeError(
            "paper trading requires exchange_calendars; install tradingagents[poller]"
        ) from exc
    return xcals.get_calendar("XNYS")


def decision_window(decision_date: str) -> tuple[datetime, datetime, str]:
    """Immutable-recording window: data cutoff through the next session open."""
    calendar = _calendar()
    session = pd.Timestamp(decision_date)
    if not calendar.is_session(session):
        raise ValueError(f"{decision_date} is not an XNYS session")
    cutoff = (
        datetime.strptime(decision_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        + timedelta(days=1)
    )
    next_session = calendar.next_session(session)
    next_open = calendar.session_open(next_session).to_pydatetime().astimezone(timezone.utc)
    return cutoff, next_open, next_session.date().isoformat()


def current_decision_date(now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    calendar = _calendar()
    # Start on the prior calendar date: at 01:00 UTC on a Tuesday, Tuesday is
    # an exchange session label but has not opened yet; Monday is the decision
    # whose immutable recording window is active.
    candidate = calendar.date_to_session(
        pd.Timestamp(now.date() - timedelta(days=1)), direction="previous"
    )
    for _ in range(10):
        date = candidate.date().isoformat()
        cutoff, next_open, _ = decision_window(date)
        if cutoff <= now < next_open:
            return date
        if now >= next_open:
            break
        candidate = calendar.previous_session(candidate)
    raise DecisionWindowClosedError(
        "not inside the safe after-cutoff, before-next-open decision window"
    )


def next_session_date(session_date: str) -> str:
    return _calendar().next_session(pd.Timestamp(session_date)).date().isoformat()


def session_open_utc(session_date: str) -> datetime:
    calendar = _calendar()
    session = pd.Timestamp(session_date)
    if not calendar.is_session(session):
        raise ValueError(f"{session_date} is not an XNYS session")
    return calendar.session_open(session).to_pydatetime().astimezone(timezone.utc)


def advance_mark(
    *,
    previous: dict | None,
    session_date: str,
    captured_utc: float,
    opens: dict[str, float],
    benchmark_open: float,
    target: dict | None,
    trading_cost_bps: float,
    slippage_bps: float,
    annual_borrow_bps: float,
    asset_returns: dict[str, float] | None = None,
    benchmark_period_return_override: float | None = None,
) -> dict:
    """Advance one immutable open-to-open paper mark."""
    if min(trading_cost_bps, slippage_bps, annual_borrow_bps) < 0:
        raise ValueError("cost, slippage, and borrow rates must be >= 0")
    if previous is None:
        if target is None:
            raise ValueError("the first paper mark requires an entering target")
        nav = benchmark_nav = 1.0
        weights = dict.fromkeys(opens, 0.0)
        period_return = benchmark_period_return = borrow_cost = 0.0
    else:
        if set(previous["weights"]) != set(opens):
            raise ValueError("paper price cross-section does not match existing weights")
        if asset_returns is None:
            asset_returns = {
                ticker: opens[ticker] / previous["opens"][ticker] - 1.0 for ticker in opens
            }
        elif set(asset_returns) != set(opens):
            raise ValueError("paper return cross-section does not match prices")
        gross_return = sum(
            previous["weights"][ticker] * asset_returns[ticker] for ticker in opens
        )
        short_exposure = sum(
            abs(weight) for weight in previous["weights"].values() if weight < 0
        )
        borrow_cost = short_exposure * annual_borrow_bps / 10_000 / 252
        period_return = gross_return - borrow_cost
        nav = previous["nav"] * (1.0 + period_return)
        benchmark_period_return = (
            benchmark_period_return_override
            if benchmark_period_return_override is not None
            else benchmark_open / previous["benchmark_open"] - 1.0
        )
        benchmark_nav = previous["benchmark_nav"] * (1.0 + benchmark_period_return)
        denominator = 1.0 + period_return
        if denominator <= 0:
            raise ValueError("paper portfolio equity was exhausted")
        weights = {
            ticker: previous["weights"][ticker] * (1.0 + asset_returns[ticker]) / denominator
            for ticker in opens
        }

    turnover = trading_cost = 0.0
    target_decision_date = None
    if target is not None:
        target_weights_map = target["weights"]
        if set(target_weights_map) != set(opens):
            raise ValueError("paper target cross-section does not match prices")
        turnover = sum(abs(target_weights_map[ticker] - weights[ticker]) for ticker in opens)
        trading_cost = turnover * (trading_cost_bps + slippage_bps) / 10_000
        nav *= 1.0 - trading_cost
        period_return = (1.0 + period_return) * (1.0 - trading_cost) - 1.0
        weights = target_weights_map
        target_decision_date = target["decision_date"]
    if not math.isfinite(nav) or nav <= 0:
        raise ValueError("invalid paper NAV")
    return {
        "session_date": session_date,
        "captured_utc": captured_utc,
        "nav": nav,
        "benchmark_nav": benchmark_nav,
        "period_return": period_return,
        "benchmark_period_return": benchmark_period_return,
        "turnover": turnover,
        "trading_cost": trading_cost,
        "borrow_cost": borrow_cost,
        "weights": weights,
        "opens": opens,
        "benchmark_open": benchmark_open,
        "target_decision_date": target_decision_date,
    }


def _open_on(ticker: str, session_date: str) -> float:
    frame = backtest._load_prices(ticker, session_date, session_date, 1)
    rows = {
        pd.Timestamp(index).date().isoformat(): row for index, row in frame.iterrows()
    }
    if session_date not in rows:
        raise RuntimeError(f"no adjusted open for {ticker} on {session_date}")
    return float(rows[session_date]["Open"])


def _consistent_vintage_open_return(
    ticker: str, previous_session: str, session_date: str
) -> float:
    """Compute both adjusted opens from one download vintage.

    Corporate-action adjustments can change historical prices. Fetching both
    endpoints together makes the captured forward return internally consistent
    even when a split or dividend occurred since the prior immutable mark.
    """
    frame = backtest._load_prices(ticker, previous_session, session_date, 1)
    rows = {
        pd.Timestamp(index).date().isoformat(): row for index, row in frame.iterrows()
    }
    missing = [date for date in (previous_session, session_date) if date not in rows]
    if missing:
        raise RuntimeError(f"no adjusted open for {ticker} on {', '.join(missing)}")
    return float(rows[session_date]["Open"]) / float(rows[previous_session]["Open"]) - 1.0


def mark_next(store: PaperStore, run_id: str, captured_utc: float | None = None) -> dict:
    config = store.run_config(run_id)
    previous = store.latest_mark(run_id)
    session_date = (
        next_session_date(previous["session_date"])
        if previous else store.first_entry_date(run_id)
    )
    if session_date is None:
        raise ValueError("paper run has no target to mark")
    captured = captured_utc or datetime.now(timezone.utc).timestamp()
    if datetime.fromtimestamp(captured, timezone.utc) < session_open_utc(session_date):
        raise ValueError(f"cannot mark {session_date} before its market open")
    target = store.target_for_entry(run_id, session_date)
    opens = {ticker: _open_on(ticker, session_date) for ticker in config["tickers"]}
    asset_returns = None
    benchmark_return = None
    if previous is not None:
        asset_returns = {
            ticker: _consistent_vintage_open_return(
                ticker, previous["session_date"], session_date
            )
            for ticker in config["tickers"]
        }
        benchmark_return = _consistent_vintage_open_return(
            config["benchmark"], previous["session_date"], session_date
        )
    mark = advance_mark(
        previous=previous,
        session_date=session_date,
        captured_utc=captured,
        opens=opens,
        benchmark_open=_open_on(config["benchmark"], session_date),
        target=target,
        trading_cost_bps=config["cost_bps"],
        slippage_bps=config["slippage_bps"],
        annual_borrow_bps=config["annual_borrow_bps"],
        asset_returns=asset_returns,
        benchmark_period_return_override=benchmark_return,
    )
    store.record_mark(run_id, mark)
    return mark


def _run_config(args, signal_fingerprint: str) -> dict:
    return {
        "tickers": sorted({value.strip().upper() for value in args.tickers.split(",") if value.strip()}),
        "benchmark": args.benchmark.upper(),
        "analysts": [value.strip() for value in args.analysts.split(",") if value.strip()],
        "replicates": args.replicates,
        "portfolio_mode": args.portfolio_mode,
        "gross_limit": args.gross_limit,
        "max_weight": args.max_weight,
        "cost_bps": args.cost_bps,
        "slippage_bps": args.slippage_bps,
        "annual_borrow_bps": args.annual_borrow_bps,
        "signal_fingerprint": signal_fingerprint,
        "global_topics_only": args.global_topics_only,
    }


def decide(args, now_utc: datetime | None = None) -> dict:
    """Run a complete forward cross-section, then atomically freeze it."""
    now = now_utc or datetime.now(timezone.utc)
    decision_date = current_decision_date(now)
    _, _, entry_date = decision_window(decision_date)
    analysts = tuple(value.strip() for value in args.analysts.split(",") if value.strip())
    if "fundamentals" in analysts:
        raise ValueError("fundamentals is not point-in-time safe for paper parity")
    unknown = set(analysts) - {"market", "social", "news"}
    if unknown:
        raise ValueError("unknown analyst(s): " + ", ".join(sorted(unknown)))
    manifest_args = SimpleNamespace(
        db=args.db,
        identity_control="none",
        global_topics_only=args.global_topics_only,
    )
    manifest = backtest._signal_manifest(manifest_args, analysts)
    signal_fingerprint = backtest._fingerprint(manifest)
    run_config = _run_config(args, signal_fingerprint)
    store = PaperStore(args.db)
    try:
        store.create_run(args.run_id, run_config, now.timestamp())
        if store.has_decision(args.run_id, decision_date):
            raise ValueError(
                f"paper decision {args.run_id}/{decision_date} is already frozen"
            )
        from tradingagents.dataflows.media_history import collected_window_fingerprint
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = DEFAULT_CONFIG.copy()
        config.update({
            "backtest_mode": True,
            "checkpoint_enabled": False,
            "collected_media_enabled": True,
            "media_db_url": args.db,
            "results_dir": args.results_dir,
            "global_topics_only": args.global_topics_only,
        })
        graph = TradingAgentsGraph(
            selected_analysts=analysts, debug=args.debug, config=config
        )
        decisions = []
        scores: dict[str, list[float]] = {ticker: [] for ticker in run_config["tickers"]}
        for ticker in run_config["tickers"]:
            start_date = (
                datetime.strptime(decision_date, "%Y-%m-%d") - timedelta(days=7)
            ).strftime("%Y-%m-%d")
            data_fingerprint = collected_window_fingerprint(
                ticker, start_date, decision_date, db_url=args.db
            )
            for replicate in range(args.replicates):
                _, action = graph.propagate(ticker, decision_date)
                score = rating_score(action)
                scores[ticker].append(score)
                decisions.append({
                    "ticker": ticker,
                    "replicate": replicate,
                    "action": action,
                    "score": score,
                    "data_fingerprint": data_fingerprint,
                    "signal_fingerprint": signal_fingerprint,
                    "final_decision": graph.curr_state["final_trade_decision"],
                })
        averaged = {
            ticker: sum(values) / len(values) for ticker, values in scores.items()
        }
        weights = target_weights(
            averaged,
            mode=args.portfolio_mode,
            gross_limit=args.gross_limit,
            max_weight=args.max_weight,
        )
        store.record_decision_set(
            args.run_id, decision_date, entry_date, now.timestamp(), decisions, weights
        )
        return {"decision_date": decision_date, "entry_date": entry_date,
                "weights": weights, "decision_rows": len(decisions)}
    finally:
        store.close()


def _common_arguments(parser) -> None:
    default_run_id = os.getenv("PAPER_RUN_ID")
    parser.add_argument("--run-id", default=default_run_id, required=not bool(default_run_id))
    parser.add_argument("--db", default=os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL"),
                        required=not bool(os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL")))


def _decision_arguments(parser) -> None:
    _common_arguments(parser)
    default_tickers = os.getenv("PAPER_TICKERS")
    parser.add_argument("--tickers", default=default_tickers, required=not bool(default_tickers))
    parser.add_argument("--benchmark", default=os.getenv("PAPER_BENCHMARK", "SPY"))
    parser.add_argument("--analysts", default=os.getenv("PAPER_ANALYSTS", "market,social,news"))
    parser.add_argument("--replicates", type=int, default=int(os.getenv("PAPER_REPLICATES", "1")))
    parser.add_argument("--portfolio-mode", default=os.getenv("PAPER_PORTFOLIO_MODE", "long-only"),
                        choices=("long-only", "long-short", "market-neutral"))
    parser.add_argument("--gross-limit", type=float, default=1.0)
    parser.add_argument("--max-weight", type=float, default=0.25)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--annual-borrow-bps", type=float, default=300.0)
    parser.add_argument("--results-dir", default="results/paper-agent-runs")
    parser.add_argument("--debug", action="store_true")
    global_only_default = os.getenv("PAPER_GLOBAL_TOPICS_ONLY", "false").lower() in {
        "1", "true", "yes", "on"
    }
    parser.add_argument("--global-topics-only", action="store_true", default=global_only_default)


def cycle(args, now_utc: datetime | None = None) -> dict:
    """Mark all due sessions, then freeze today's decision exactly once."""
    now = now_utc or datetime.now(timezone.utc)
    decision_date = current_decision_date(now)
    marks = []
    already_frozen = False
    store = PaperStore(args.db)
    try:
        try:
            store.run_config(args.run_id)
        except ValueError:
            pass
        else:
            while True:
                previous = store.latest_mark(args.run_id)
                due = (
                    next_session_date(previous["session_date"])
                    if previous else store.first_entry_date(args.run_id)
                )
                if due is None or due > decision_date:
                    break
                marks.append(mark_next(store, args.run_id, now.timestamp()))
            already_frozen = store.has_decision(args.run_id, decision_date)
    finally:
        store.close()
    decision = None if already_frozen else decide(args, now)
    return {
        "decision_date": decision_date,
        "marks_recorded": [mark["session_date"] for mark in marks],
        "decision_recorded": decision is not None,
        "decision": decision,
    }


def next_daemon_run(now_utc: datetime | None = None) -> datetime:
    """Next 00:05 UTC, immediately after the captured-media daily cutoff."""
    now = now_utc or datetime.now(timezone.utc)
    candidate = now.replace(hour=0, minute=5, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _record_daemon_heartbeat(db_url: str, key: str, captured_utc: float) -> None:
    from tradingagents.dataflows.media_store import open_store

    store = open_store(db_url)
    try:
        store.set_meta(key, captured_utc)
    finally:
        store.close()


def _cycle_with_retries(
    args,
    *,
    attempts: int = 3,
    retry_seconds: float = 300.0,
    sleep_fn=time.sleep,
) -> dict | None:
    """Run a paper cycle with bounded retries while keeping the daemon alive."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        now = datetime.now(timezone.utc)
        try:
            result = cycle(args, now)
            _record_daemon_heartbeat(args.db, "paper:last_success_utc", now.timestamp())
            return result
        except DecisionWindowClosedError as exc:
            # Expected outside-window control flow; no data or ledger failure.
            logger.warning("Paper cycle skipped: %s", exc)
            return None
        except Exception:  # noqa: BLE001 — keep the scheduled worker alive
            logger.exception("Paper cycle attempt %d/%d failed", attempt, attempts)
            try:
                _record_daemon_heartbeat(args.db, "paper:last_failure_utc", now.timestamp())
            except Exception:  # noqa: BLE001
                logger.exception("Could not record paper failure heartbeat")
            if attempt < attempts:
                sleep_fn(retry_seconds)
    raise RuntimeError(f"paper cycle failed after {attempts} attempts")


def daemon(args) -> None:
    """Run one idempotent paper cycle after each UTC data cutoff."""
    attempts = int(os.getenv("PAPER_RETRY_ATTEMPTS", "3"))
    retry_seconds = float(os.getenv("PAPER_RETRY_SECONDS", "300"))
    while True:
        result = _cycle_with_retries(
            args, attempts=attempts, retry_seconds=retry_seconds
        )
        if result is not None:
            print(json.dumps(result), flush=True)
        wake = next_daemon_run(datetime.now(timezone.utc))
        time.sleep(max(1.0, (wake - datetime.now(timezone.utc)).total_seconds()))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    decide_parser = commands.add_parser("decide", help="Freeze the current forward decision")
    _decision_arguments(decide_parser)
    cycle_parser = commands.add_parser(
        "cycle", help="Mark due opens and freeze the current decision once"
    )
    _decision_arguments(cycle_parser)
    daemon_parser = commands.add_parser(
        "daemon", help="Run an idempotent cycle daily at 00:05 UTC"
    )
    _decision_arguments(daemon_parser)
    mark_parser = commands.add_parser("mark", help="Capture and mark the next portfolio open")
    _common_arguments(mark_parser)
    status_parser = commands.add_parser("status", help="Show immutable ledger status")
    _common_arguments(status_parser)
    args = parser.parse_args(argv)

    if args.command in {"decide", "cycle", "daemon"}:
        if args.replicates < 1:
            parser.error("--replicates must be >= 1")
        if min(args.cost_bps, args.slippage_bps, args.annual_borrow_bps) < 0:
            parser.error("cost, slippage, and borrow rates must be >= 0")
        analysts = {value.strip() for value in args.analysts.split(",") if value.strip()}
        if args.global_topics_only and "social" in analysts:
            parser.error(
                "--global-topics-only is incompatible with the ticker-specific social analyst"
            )
        if args.command == "daemon":
            daemon(args)
            return
        try:
            result = decide(args) if args.command == "decide" else cycle(args)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return

    store = PaperStore(args.db)
    try:
        if args.command == "mark":
            result = mark_next(store, args.run_id)
        else:
            result = store.status(args.run_id)
    finally:
        store.close()
    if args.command == "status":
        from tradingagents.dataflows.media_store import open_store

        heartbeat_store = open_store(args.db)
        try:
            result["last_success_utc"] = heartbeat_store.get_meta("paper:last_success_utc")
            result["last_failure_utc"] = heartbeat_store.get_meta("paper:last_failure_utc")
        finally:
            heartbeat_store.close()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
