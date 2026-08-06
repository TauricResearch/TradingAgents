"""Bounded, resumable signal backtest for TradingAgents decisions.

The graph analyzes a session after its close. A simulated position enters at
the next session's open and exits at the close of the Nth holding session.
It records independent signal outcomes and also builds a synchronized,
constraint-aware portfolio equity curve across the requested universe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import yfinance as yf

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio_backtest import (
    aggregate_signal_records,
    portfolio_diagnostics,
    portfolio_result_dict,
    simulate_portfolio,
)

BACKTEST_SCHEMA_VERSION = 2
_EXPOSURE = {
    "buy": 1.0,
    "overweight": 0.5,
    "hold": 0.0,
    "underweight": -0.5,
    "sell": -1.0,
}


@dataclass(frozen=True)
class SignalOutcome:
    ticker: str
    decision_date: str
    action: str
    exposure: float
    entry_date: str | None
    exit_date: str | None
    entry_price: float | None
    exit_price: float | None
    asset_return: float | None
    benchmark_return: float | None
    net_return: float | None
    excess_return: float | None
    holding_sessions: int
    cost_bps_per_side: float


def _date_index(frame: pd.DataFrame) -> list[str]:
    return [pd.Timestamp(value).date().isoformat() for value in frame.index]


def evaluate_signal(
    *,
    ticker: str,
    decision_date: str,
    action: str,
    prices: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
    holding_sessions: int = 5,
    cost_bps_per_side: float = 5.0,
) -> SignalOutcome:
    """Evaluate one after-close signal without any future-data fallback."""
    normalized_action = action.strip().lower()
    if normalized_action not in _EXPOSURE:
        raise ValueError(f"unsupported action {action!r}")
    if holding_sessions < 1:
        raise ValueError("holding_sessions must be >= 1")
    if cost_bps_per_side < 0:
        raise ValueError("cost_bps_per_side must be >= 0")
    exposure = _EXPOSURE[normalized_action]
    dates = _date_index(prices)
    try:
        decision_position = dates.index(decision_date)
    except ValueError:
        return SignalOutcome(
            ticker, decision_date, action, exposure, None, None, None, None,
            None, None, None, None, holding_sessions, cost_bps_per_side,
        )
    entry_position = decision_position + 1
    exit_position = entry_position + holding_sessions - 1
    if exit_position >= len(prices):
        return SignalOutcome(
            ticker, decision_date, action, exposure, None, None, None, None,
            None, None, None, None, holding_sessions, cost_bps_per_side,
        )

    entry_date = dates[entry_position]
    exit_date = dates[exit_position]
    benchmark_dates = _date_index(benchmark_prices)
    if entry_date not in benchmark_dates or exit_date not in benchmark_dates:
        return SignalOutcome(
            ticker, decision_date, action, exposure, None, None, None, None,
            None, None, None, None, holding_sessions, cost_bps_per_side,
        )

    entry_price = float(prices.iloc[entry_position]["Open"])
    exit_price = float(prices.iloc[exit_position]["Close"])
    benchmark_entry = float(
        benchmark_prices.iloc[benchmark_dates.index(entry_date)]["Open"]
    )
    benchmark_exit = float(
        benchmark_prices.iloc[benchmark_dates.index(exit_date)]["Close"]
    )
    asset_return = exit_price / entry_price - 1.0
    benchmark_return = benchmark_exit / benchmark_entry - 1.0
    round_trip_cost = 2.0 * cost_bps_per_side / 10_000 if exposure else 0.0
    net_return = exposure * asset_return - round_trip_cost
    excess_return = net_return - benchmark_return
    return SignalOutcome(
        ticker=ticker,
        decision_date=decision_date,
        action=action,
        exposure=exposure,
        entry_date=entry_date,
        exit_date=exit_date,
        entry_price=entry_price,
        exit_price=exit_price,
        asset_return=asset_return,
        benchmark_return=benchmark_return,
        net_return=net_return,
        excess_return=excess_return,
        holding_sessions=holding_sessions,
        cost_bps_per_side=cost_bps_per_side,
    )


def _load_prices(ticker: str, start: str, end: str, holding_sessions: int) -> pd.DataFrame:
    # Retain enough pre-start history for point-in-time baselines and later
    # attribution without issuing a second vendor request.
    start_dt = datetime.strptime(start, "%Y-%m-%d") - timedelta(days=90)
    end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(
        days=holding_sessions * 3 + 10
    )
    frame = yf.Ticker(ticker).history(
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        # Adjusted OHLC incorporates splits and cash distributions into the
        # realized-return series instead of silently dropping corporate actions.
        auto_adjust=True,
    )
    if frame.empty or "Open" not in frame or "Close" not in frame:
        raise RuntimeError(f"no usable OHLC data for {ticker}")
    return frame.sort_index()


def _decision_dates(frame: pd.DataFrame, start: str, end: str) -> list[str]:
    return [date for date in _date_index(frame) if start <= date <= end]


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"Ignoring malformed JSONL line {line_number} in {path}.")
    return rows


def _fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _decision_code_fingerprint() -> str:
    """Hash the installed package as a build identity (including operations)."""
    package = Path(__file__).resolve().parent
    # This is intentionally conservative: changing a vendor adapter, config
    # default, model client, parser, prompt, or portfolio helper creates a new
    # strategy identity even if the edit later proves outcome-neutral.
    paths = sorted(package.rglob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(package)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _strategy_code_fingerprint() -> str:
    """Hash only modules capable of changing economic decision semantics."""
    package = Path(__file__).resolve().parent
    roots = [package / "agents", package / "graph"]
    paths = [package / "portfolio_backtest.py", package / "dataflows" / "media_features.py",
             package / "dataflows" / "media_history.py"]
    for root in roots:
        paths.extend(root.rglob("*.py"))
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(str(path.relative_to(package)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _signal_fingerprint(manifest: dict) -> str:
    """Economic identity intentionally excludes the operational build ID."""
    return _fingerprint({key: value for key, value in manifest.items() if key != "build_id"})


def _database_identity(url: str | None) -> str:
    """Return a credential-independent hash for the logical data store."""
    raw = url or ""
    parsed = urlsplit(raw)
    if parsed.scheme and parsed.hostname:
        logical = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or ''}{parsed.path}"
    else:
        logical = raw
    return hashlib.sha256(logical.encode()).hexdigest()[:12]


_DECISION_CONFIG_KEYS = (
    "anthropic_effort", "backend_url", "collected_media_enabled",
    "data_vendors", "global_news_article_limit", "global_news_lookback_days",
    "global_news_novelty_lookback_days", "global_news_queries", "google_thinking_level",
    "llm_max_retries", "macro_themes", "max_debate_rounds", "max_recur_limit",
    "max_risk_discuss_rounds", "news_article_limit", "online_tools", "output_language",
    "tool_vendors",
)


def _signal_manifest(
    args, analysts: tuple[str, ...], identity_aliases: dict[str, str] | None = None
) -> dict:
    database_id = _database_identity(args.db)
    return {
        "schema_version": BACKTEST_SCHEMA_VERSION,
        "protocol_code_id": _strategy_code_fingerprint(),
        "build_id": _decision_code_fingerprint(),
        "analysts": list(analysts),
        "llm_provider": DEFAULT_CONFIG["llm_provider"],
        "quick_model": DEFAULT_CONFIG["quick_think_llm"],
        "deep_model": DEFAULT_CONFIG["deep_think_llm"],
        "temperature": DEFAULT_CONFIG.get("temperature"),
        "reasoning_effort": DEFAULT_CONFIG.get("openai_reasoning_effort"),
        "collected_media": True,
        "database_id": database_id,
        "decision_timing": "after-close",
        "execution_timing": "next-open",
        # Paper trading and older programmatic callers do not expose the
        # backtest-only CLI flag; their ordinary identity mode is "none".
        "identity_control": getattr(args, "identity_control", "none"),
        "identity_aliases": identity_aliases or {},
        "global_topics_only": bool(getattr(args, "global_topics_only", False)),
        "decision_config": {
            key: DEFAULT_CONFIG.get(key) for key in _DECISION_CONFIG_KEYS
        },
    }


def _identity_aliases(tickers: list[str], mode: str) -> dict[str, str]:
    """Return real -> LLM-visible identifiers for a negative-control run."""
    if mode == "none":
        return {ticker: ticker for ticker in tickers}
    if mode != "ticker-mask":
        raise ValueError(f"unsupported identity control {mode!r}")
    return {ticker: f"ASSET_{index:03d}" for index, ticker in enumerate(sorted(tickers), 1)}


def _reevaluate_records(
    records: list[dict],
    *,
    prices: dict[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    holding_sessions: int,
    cost_bps_per_side: float,
) -> list[dict]:
    """Recompute outcomes so cached decisions never retain stale evaluation settings."""
    evaluated = []
    for row in records:
        ticker = row["ticker"]
        outcome = evaluate_signal(
            ticker=ticker,
            decision_date=row["decision_date"],
            action=row["action"],
            prices=prices[ticker],
            benchmark_prices=benchmark_prices,
            holding_sessions=holding_sessions,
            cost_bps_per_side=cost_bps_per_side,
        )
        evaluated.append({**row, **asdict(outcome)})
    return evaluated


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_portfolio_outputs(path: Path, payload: dict) -> tuple[Path, Path]:
    portfolio_path = path.with_suffix(".portfolio.json")
    equity_path = path.with_suffix(".equity.csv")
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    temp = portfolio_path.with_suffix(portfolio_path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(portfolio_path)
    equity_rows = []
    for row in payload["result"]["equity"]:
        flat = {key: value for key, value in row.items() if key != "weights"}
        flat.update({f"weight_{ticker}": weight for ticker, weight in row["weights"].items()})
        equity_rows.append(flat)
    pd.DataFrame(equity_rows).to_csv(equity_path, index=False)
    return portfolio_path, equity_path


def _print_summary(records: list[dict]) -> None:
    resolved = [row for row in records if row.get("net_return") is not None]
    if not resolved:
        print("No outcomes are resolvable yet; decisions were saved for later evaluation.")
        return
    returns = [row["net_return"] for row in resolved]
    excess = [row["excess_return"] for row in resolved]
    hit_rate = sum(value > 0 for value in returns) / len(returns)
    print(
        f"Resolved signals: {len(resolved)} · hit rate: {hit_rate:.1%} · "
        f"mean net return: {statistics.fmean(returns):.2%} · "
        f"median: {statistics.median(returns):.2%} · "
        f"mean excess vs benchmark: {statistics.fmean(excess):.2%}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", required=True, help="Comma-separated symbols")
    parser.add_argument("--start", required=True, help="First decision date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Last decision date YYYY-MM-DD")
    parser.add_argument("--benchmark", default="SPY")
    parser.add_argument("--holding-sessions", type=int, default=5)
    parser.add_argument("--cost-bps", type=float, default=5.0, help="Cost per side")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage per turnover")
    parser.add_argument("--annual-borrow-bps", type=float, default=300.0)
    parser.add_argument("--portfolio-mode", choices=("long-only", "long-short", "market-neutral"),
                        default="long-only")
    parser.add_argument("--gross-limit", type=float, default=1.0)
    parser.add_argument("--max-weight", type=float, default=0.25)
    parser.add_argument("--tail-sessions", type=int, default=5)
    parser.add_argument("--replicates", type=int, default=1,
                        help="Independent LLM decisions per ticker/date to average")
    parser.add_argument("--placebo-trials", type=int, default=100,
                        help="Within-date ticker permutations for the selection placebo")
    parser.add_argument(
        "--identity-control", choices=("none", "ticker-mask"), default="none",
        help="Mask ticker IDs from the LLM; issuer names inside captured prose are not redacted",
    )
    parser.add_argument(
        "--global-topics-only", action="store_true",
        help="Use market data plus broad global narratives; block ticker-specific media",
    )
    parser.add_argument(
        "--analysts", default="market,social,news",
        help="Comma-separated analysts; fundamentals is blocked because point-in-time filings are unavailable",
    )
    parser.add_argument("--max-runs", type=int, default=3, help="Hard LLM-run safety cap")
    parser.add_argument("--db", default=os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL"))
    parser.add_argument("--output", default="backtest-results.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="Print schedule without LLM calls")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    if args.start > args.end:
        parser.error("--start must be on or before --end")
    if args.max_runs < 1:
        parser.error("--max-runs must be >= 1")
    if args.replicates < 1:
        parser.error("--replicates must be >= 1")
    if args.placebo_trials < 0:
        parser.error("--placebo-trials must be >= 0")
    if min(args.cost_bps, args.slippage_bps, args.annual_borrow_bps) < 0:
        parser.error("cost, slippage, and borrow rates must be >= 0")
    analysts = tuple(value.strip() for value in args.analysts.split(",") if value.strip())
    if "fundamentals" in analysts:
        parser.error(
            "fundamentals is not point-in-time safe in this dataset; omit it from backtests"
        )
    unknown = set(analysts) - {"market", "social", "news"}
    if unknown:
        parser.error("unknown analyst(s): " + ", ".join(sorted(unknown)))
    if args.global_topics_only and "social" in analysts:
        parser.error("--global-topics-only is incompatible with the ticker-specific social analyst")

    tickers = [value.strip().upper() for value in args.tickers.split(",") if value.strip()]
    if not tickers:
        parser.error("--tickers must contain at least one symbol")
    visible_symbols = _identity_aliases(tickers, args.identity_control)
    manifest = _signal_manifest(
        args,
        analysts,
        visible_symbols if args.identity_control == "ticker-mask" else {},
    )
    signal_fingerprint = _signal_fingerprint(manifest)
    price_buffer_sessions = max(args.holding_sessions, args.tail_sessions)
    benchmark_prices = _load_prices(
        args.benchmark, args.start, args.end, price_buffer_sessions
    )
    dates = _decision_dates(benchmark_prices, args.start, args.end)
    schedule = [
        (ticker, date, replicate)
        for date in dates for ticker in tickers for replicate in range(args.replicates)
    ]
    output = Path(args.output).expanduser()
    existing_records = _load_records(output)
    if args.dry_run:
        print(
            f"Signal configuration: {signal_fingerprint} · "
            f"up to {len(schedule)} graph runs (database cache not inspected)."
        )
        for ticker, date, replicate in schedule:
            print(f"  {date} {ticker} replicate={replicate + 1}")
        return
    if not args.db:
        parser.error("captured-media database required: pass --db or set MEDIA_DB_URL/DATABASE_URL")
    from tradingagents.dataflows.media_history import collected_window_fingerprint

    data_fingerprints = {}
    for ticker, date, _ in schedule:
        key = (ticker, date)
        if key not in data_fingerprints:
            start_date = (
                datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)
            ).strftime("%Y-%m-%d")
            data_fingerprints[key] = collected_window_fingerprint(
                ticker, start_date, date, db_url=args.db
            )
    existing = {
        (
            row.get("ticker"), row.get("decision_date"), row.get("replicate", 0),
            row.get("data_fingerprint"),
        )
        for row in existing_records if row.get("signal_fingerprint") == signal_fingerprint
    }
    schedule = [
        pair for pair in schedule
        if (*pair, data_fingerprints[(pair[0], pair[1])]) not in existing
    ]
    print(
        f"Signal configuration: {signal_fingerprint} · "
        f"scheduled {len(schedule)} new graph runs ({len(existing)} cached records checked)."
    )
    for ticker, date, replicate in schedule:
        print(f"  {date} {ticker} replicate={replicate + 1}")
    if len(schedule) > args.max_runs:
        parser.error(
            f"schedule has {len(schedule)} LLM runs, above --max-runs={args.max_runs}; "
            "narrow the dates/tickers or explicitly raise the cap"
        )

    config = DEFAULT_CONFIG.copy()
    config.update({
        "backtest_mode": True,
        "checkpoint_enabled": False,
        "collected_media_enabled": True,
        "media_db_url": args.db,
        "results_dir": str(output.parent / "agent-runs"),
        "global_topics_only": args.global_topics_only,
    })
    config["research_symbol_aliases"] = (
        {visible: real for real, visible in visible_symbols.items()}
        if args.identity_control == "ticker-mask" else {}
    )
    price_cache = {
        ticker: _load_prices(ticker, args.start, args.end, price_buffer_sessions)
        for ticker in tickers
    }
    records = []
    graph = None
    if schedule:
        # Import only after schedule/cost validation so cached portfolio
        # recalculation and --dry-run do not initialize an LLM client.
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        graph = TradingAgentsGraph(
            selected_analysts=analysts,
            debug=args.debug,
            config=config,
        )
    for ticker, date, replicate in schedule:
        assert graph is not None
        _, action = graph.propagate(visible_symbols[ticker], date)
        outcome = evaluate_signal(
            ticker=ticker,
            decision_date=date,
            action=action,
            prices=price_cache[ticker],
            benchmark_prices=benchmark_prices,
            holding_sessions=args.holding_sessions,
            cost_bps_per_side=args.cost_bps,
        )
        row = {
            **asdict(outcome),
            "benchmark": args.benchmark,
            "replicate": replicate,
            "signal_fingerprint": signal_fingerprint,
            "data_fingerprint": data_fingerprints[(ticker, date)],
            "signal_manifest": manifest,
            "analysts": list(analysts),
            "llm_provider": config["llm_provider"],
            "quick_model": config["quick_think_llm"],
            "deep_model": config["deep_think_llm"],
            "final_decision": graph.curr_state["final_trade_decision"],
        }
        _append_jsonl(output, row)
        records.append(row)
        status = f"net={outcome.net_return:.2%}" if outcome.net_return is not None else "pending"
        print(f"Saved {date} {ticker}: {action} ({status})")
    experiment_records = [
        row for row in existing_records + records
        if row.get("signal_fingerprint") == signal_fingerprint
        and row.get("ticker") in tickers
        and int(row.get("replicate", 0)) < args.replicates
        and args.start <= row.get("decision_date", "") <= args.end
        and row.get("data_fingerprint") == data_fingerprints.get(
            (row.get("ticker"), row.get("decision_date"))
        )
    ]
    experiment_records = _reevaluate_records(
        experiment_records,
        prices=price_cache,
        benchmark_prices=benchmark_prices,
        holding_sessions=args.holding_sessions,
        cost_bps_per_side=args.cost_bps,
    )
    _print_summary(experiment_records)
    signals = aggregate_signal_records(experiment_records, tickers)
    portfolio_manifest = {
        "signal_fingerprint": signal_fingerprint,
        "tickers": tickers,
        "start": args.start,
        "end": args.end,
        "benchmark": args.benchmark,
        "mode": args.portfolio_mode,
        "gross_limit": args.gross_limit,
        "max_weight": args.max_weight,
        "trading_cost_bps": args.cost_bps,
        "slippage_bps": args.slippage_bps,
        "annual_borrow_bps": args.annual_borrow_bps,
        "tail_sessions": args.tail_sessions,
        "holding_sessions": args.holding_sessions,
        "replicates": args.replicates,
        "placebo_trials": args.placebo_trials,
    }
    portfolio = simulate_portfolio(
        signals=signals,
        prices=price_cache,
        benchmark_prices=benchmark_prices,
        mode=args.portfolio_mode,
        gross_limit=args.gross_limit,
        max_weight=args.max_weight,
        trading_cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        annual_borrow_bps=args.annual_borrow_bps,
        tail_sessions=args.tail_sessions,
    )
    simulation_kwargs = {
        "mode": args.portfolio_mode,
        "gross_limit": args.gross_limit,
        "max_weight": args.max_weight,
        "trading_cost_bps": args.cost_bps,
        "slippage_bps": args.slippage_bps,
        "annual_borrow_bps": args.annual_borrow_bps,
        "tail_sessions": args.tail_sessions,
    }
    payload = {
        "portfolio_fingerprint": _fingerprint(portfolio_manifest),
        "manifest": portfolio_manifest,
        "result": portfolio_result_dict(portfolio),
        "diagnostics": portfolio_diagnostics(
            result=portfolio,
            signals=signals,
            prices=price_cache,
            benchmark_prices=benchmark_prices,
            holding_sessions=args.holding_sessions,
            placebo_trials=args.placebo_trials,
            simulation_kwargs=simulation_kwargs,
        ),
    }
    portfolio_path, equity_path = _write_portfolio_outputs(output, payload)
    metrics = portfolio.metrics
    print(
        f"Portfolio: total={metrics.total_return:.2%} · benchmark={metrics.benchmark_return:.2%} "
        f"· excess={metrics.excess_return:.2%} · max drawdown={metrics.max_drawdown:.2%} "
        f"· turnover={metrics.total_turnover:.2f}x"
    )
    print(f"Saved {portfolio_path} and {equity_path}")


if __name__ == "__main__":
    main()
