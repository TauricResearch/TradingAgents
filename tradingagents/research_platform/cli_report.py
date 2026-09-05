"""Command-line entry point for local personal research reports."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from .agent_contracts import TradeDirection, TradeHorizon, TradeSignal
from .artifact_store import JsonArtifactStore
from .data_contracts import DataProvider
from .research_workflow import ResearchWorkflowConfig, run_ticker_research
from .risk_contracts import RiskPolicy
from .run_archive import JsonResearchRunArchive
from .yfinance_provider import YFinanceDataUnavailableError, YFinanceProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tradingagents.research_platform.cli_report",
        description="Generate a local personal stock research report.",
    )
    parser.add_argument("symbol", help="Ticker symbol, e.g. NVDA or AAPL.")
    parser.add_argument("--as-of", type=_parse_date, default=date.today(), help="Report date.")
    parser.add_argument("--lookback-days", type=int, default=90, help="Historical lookback.")
    parser.add_argument("--currency", default=None, help="Optional quote currency label.")
    parser.add_argument("--output-dir", default="research_reports", help="Directory for Markdown reports.")
    parser.add_argument("--cache-dir", default=None, help="Optional JSONL artifact cache directory.")
    parser.add_argument(
        "--yfinance-cache-dir",
        default=None,
        help="Optional writable directory for yfinance's local cache.",
    )
    parser.add_argument("--news-limit", type=int, default=20, help="Max yfinance news items to request.")
    parser.add_argument("--initial-cash", type=float, default=100_000.0, help="Backtest initial cash.")

    signal_group = parser.add_argument_group("manual signal")
    signal_group.add_argument("--direction", choices=[item.value for item in TradeDirection])
    signal_group.add_argument("--signal-date", type=_parse_date, default=None)
    signal_group.add_argument("--horizon", choices=[item.value for item in TradeHorizon], default="medium")
    signal_group.add_argument("--confidence", type=_parse_unit_interval, default=0.5)
    signal_group.add_argument("--position-pct", type=_parse_unit_interval, default=None)
    signal_group.add_argument("--expected-return-pct", type=_parse_signed_pct, default=None)
    signal_group.add_argument("--stop-loss-pct", type=_parse_unit_interval, default=None)
    signal_group.add_argument("--rationale", default="Manual CLI signal.")

    risk_group = parser.add_argument_group("risk policy")
    risk_group.add_argument("--max-single-position-pct", type=_parse_unit_interval, default=0.10)
    risk_group.add_argument("--default-position-pct", type=_parse_unit_interval, default=0.03)
    risk_group.add_argument("--min-signal-confidence", type=_parse_unit_interval, default=0.55)
    risk_group.add_argument("--max-drawdown-pct", type=_parse_unit_interval, default=0.15)
    risk_group.add_argument("--current-position-pct", type=_parse_unit_interval, default=0.0)
    risk_group.add_argument("--portfolio-drawdown-pct", type=_parse_unit_interval, default=0.0)
    risk_group.add_argument("--realized-volatility-pct", type=_parse_unit_interval, default=None)

    execution_group = parser.add_argument_group("backtest execution")
    execution_group.add_argument("--commission-bps", type=float, default=0.0)
    execution_group.add_argument("--slippage-bps", type=float, default=0.0)
    execution_group.add_argument("--allow-short", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    provider_factory: Callable[[argparse.Namespace], DataProvider] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_signal_args(parser, args)

    try:
        provider = (
            provider_factory(args)
            if provider_factory is not None
            else YFinanceProvider(news_limit=args.news_limit, cache_dir=args.yfinance_cache_dir)
        )
    except YFinanceDataUnavailableError as exc:
        print(f"Data provider error: {exc}", file=sys.stderr)
        return 2
    store = JsonArtifactStore(args.cache_dir) if args.cache_dir else None
    archive = JsonResearchRunArchive(args.cache_dir) if args.cache_dir else None
    signal = _build_manual_signal(args)
    policy = RiskPolicy(
        max_single_position_pct=args.max_single_position_pct,
        default_position_pct=args.default_position_pct,
        min_signal_confidence=args.min_signal_confidence,
        max_portfolio_drawdown_pct=args.max_drawdown_pct,
        max_realized_volatility_pct=args.realized_volatility_pct,
    )
    config = ResearchWorkflowConfig(
        symbol=args.symbol.upper(),
        as_of_date=args.as_of,
        lookback_days=args.lookback_days,
        currency=args.currency,
        initial_cash=args.initial_cash,
        current_position_pct=args.current_position_pct,
        portfolio_drawdown_pct=args.portfolio_drawdown_pct,
        realized_volatility_pct=args.realized_volatility_pct,
    )
    config = config.model_copy(
        update={
            "execution": config.execution.model_copy(
                update={
                    "commission_bps": args.commission_bps,
                    "slippage_bps": args.slippage_bps,
                    "allow_short": args.allow_short,
                }
            )
        }
    )

    try:
        result = run_ticker_research(
            config=config,
            provider=provider,
            store=store,
            signal=signal,
            risk_policy=policy,
            output_dir=Path(args.output_dir),
            archive=archive,
        )
    except YFinanceDataUnavailableError as exc:
        print(f"Data provider error: {exc}", file=sys.stderr)
        return 2
    if result.report_path is None:
        print("Report rendered but no output path was requested.")
    else:
        print(f"Report written: {result.report_path}")
    if result.archived_run is not None:
        print(f"Research run archived: {result.archived_run.run_id}")
    if signal is None:
        print("No manual signal supplied; report includes data and deterministic notes only.")
    elif result.bundle.risk_review is not None:
        print(f"Risk decision: {result.bundle.risk_review.decision.value}")
    return 0


def _build_manual_signal(args: argparse.Namespace) -> TradeSignal | None:
    if args.direction is None:
        return None
    return TradeSignal(
        symbol=args.symbol.upper(),
        as_of_date=args.signal_date or args.as_of,
        direction=TradeDirection(args.direction),
        horizon=TradeHorizon(args.horizon),
        confidence=args.confidence,
        rationale=args.rationale,
        proposed_position_pct=args.position_pct,
        expected_return_pct=args.expected_return_pct,
        stop_loss_pct=args.stop_loss_pct,
    )


def _validate_signal_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    signal_values = [
        args.signal_date,
        args.position_pct,
        args.expected_return_pct,
        args.stop_loss_pct,
    ]
    if args.direction is None and any(value is not None for value in signal_values):
        parser.error("--direction is required when signal fields are supplied")
    if args.lookback_days < 1:
        parser.error("--lookback-days must be >= 1")
    if args.news_limit < 1:
        parser.error("--news-limit must be >= 1")
    if args.initial_cash <= 0:
        parser.error("--initial-cash must be > 0")
    if args.commission_bps < 0 or args.slippage_bps < 0:
        parser.error("--commission-bps and --slippage-bps must be >= 0")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _parse_unit_interval(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed > 1:
        parsed = parsed / 100.0
    if parsed < 0 or parsed > 1:
        raise argparse.ArgumentTypeError("expected a decimal 0-1 or percent 0-100")
    return parsed


def _parse_signed_pct(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if abs(parsed) > 1:
        parsed = parsed / 100.0
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
