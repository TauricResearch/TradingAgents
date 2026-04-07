from __future__ import annotations

import argparse
import json
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

import yfinance as yf

from tradingagents.agents.utils.instrument_resolver import resolve_instrument
from cli.stats_handler import StatsCallbackHandler
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import save_report_bundle

from .config import ScheduledAnalysisConfig, load_scheduled_config, with_overrides
from .site import build_site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a non-interactive scheduled TradingAgents analysis and build a static report site."
    )
    parser.add_argument("--config", default="config/scheduled_analysis.toml", help="Path to scheduled analysis TOML config.")
    parser.add_argument("--archive-dir", help="Override archive directory for run history.")
    parser.add_argument("--site-dir", help="Override generated site output directory.")
    parser.add_argument("--tickers", help="Comma-separated ticker override.")
    parser.add_argument("--trade-date", help="Optional YYYY-MM-DD override for all tickers.")
    parser.add_argument("--site-only", action="store_true", help="Only rebuild the static site from archived runs.")
    parser.add_argument("--strict", action="store_true", help="Return a non-zero exit code if any ticker fails.")
    parser.add_argument("--label", default="github-actions", help="Run label for archived metadata.")
    args = parser.parse_args(argv)

    config = with_overrides(
        load_scheduled_config(args.config),
        archive_dir=args.archive_dir,
        site_dir=args.site_dir,
        tickers=_parse_ticker_override(args.tickers),
        trade_date=args.trade_date,
    )

    if args.site_only:
        manifests = build_site(config.storage.archive_dir, config.storage.site_dir, config.site)
        print(
            f"Rebuilt static site at {config.storage.site_dir} from {len(manifests)} archived run(s)."
        )
        return 0

    manifest = execute_scheduled_run(config, run_label=args.label)
    print(
        f"Completed run {manifest['run_id']} with status {manifest['status']} "
        f"({manifest['summary']['successful_tickers']} success / {manifest['summary']['failed_tickers']} failed)."
    )
    return 1 if args.strict and manifest["summary"]["failed_tickers"] else 0


def execute_scheduled_run(
    config: ScheduledAnalysisConfig,
    *,
    run_label: str = "manual",
) -> dict[str, Any]:
    tz = ZoneInfo(config.run.timezone)
    started_at = datetime.now(tz)
    run_id = _build_run_id(started_at, run_label)
    run_dir = config.storage.archive_dir / "runs" / started_at.strftime("%Y") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ticker_summaries: list[dict[str, Any]] = []
    engine_results_dir = run_dir / "engine-results"

    for ticker in config.run.tickers:
        ticker_summary = _run_single_ticker(
            config=config,
            ticker=ticker,
            run_dir=run_dir,
            engine_results_dir=engine_results_dir,
        )
        ticker_summaries.append(ticker_summary)

        if ticker_summary["status"] != "success" and not config.run.continue_on_ticker_error:
            break

    finished_at = datetime.now(tz)
    failures = sum(1 for item in ticker_summaries if item["status"] != "success")
    successes = len(ticker_summaries) - failures
    status = "success"
    if failures and successes:
        status = "partial_failure"
    elif failures:
        status = "failed"

    manifest = {
        "version": 1,
        "run_id": run_id,
        "label": run_label,
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "timezone": config.run.timezone,
        "settings": _settings_snapshot(config),
        "summary": {
            "total_tickers": len(ticker_summaries),
            "successful_tickers": successes,
            "failed_tickers": failures,
        },
        "tickers": ticker_summaries,
    }

    _write_json(run_dir / "run.json", manifest)
    _write_json(config.storage.archive_dir / "latest-run.json", manifest)
    build_site(config.storage.archive_dir, config.storage.site_dir, config.site)
    return manifest


def resolve_trade_date(
    ticker: str,
    config: ScheduledAnalysisConfig,
) -> str:
    normalized_symbol = resolve_instrument(ticker).primary_symbol
    mode = config.run.trade_date_mode
    if mode == "explicit" and config.run.explicit_trade_date:
        return config.run.explicit_trade_date

    now = datetime.now(ZoneInfo(config.run.timezone))
    if mode == "today":
        return now.date().isoformat()
    if mode == "previous_business_day":
        return _previous_business_day(now.date()).isoformat()

    if not _looks_like_yahoo_ticker_format(normalized_symbol):
        raise RuntimeError(
            f"Could not resolve the latest available trade date for {ticker} ({normalized_symbol}); "
            f"symbol format looks invalid for Yahoo Finance. Expected examples: AAPL, BRK.B, 005930.KS."
        )

    history = yf.Ticker(normalized_symbol).history(
        period=f"{config.run.latest_market_data_lookback_days}d",
        interval="1d",
        auto_adjust=False,
    )
    if history.empty:
        symbol_hint = _ticker_hint(normalized_symbol)
        raise RuntimeError(
            f"Could not resolve the latest available trade date for {ticker} ({normalized_symbol}); "
            f"yfinance returned no rows.{symbol_hint}"
        )

    last_index = history.index[-1]
    last_value = getattr(last_index, "to_pydatetime", lambda: last_index)()
    last_date = last_value.date() if hasattr(last_value, "date") else last_value
    if not isinstance(last_date, date):
        raise RuntimeError(f"Unexpected trade date index value for {ticker}: {last_index!r}")
    return last_date.isoformat()


def _looks_like_yahoo_ticker_format(symbol: str) -> bool:
    if not symbol:
        return False
    if symbol.count(".") > 1:
        return False
    if symbol[0] == "." or symbol[-1] == ".":
        return False
    for ch in symbol:
        if not (ch.isalnum() or ch in ".-"):
            return False
    return True


def _ticker_hint(symbol: str) -> str:
    normalized = symbol.upper()
    common_typos = {
        "APPL": " APPL is likely an invalid ticker; if you intended Apple, use 'AAPL'.",
    }
    return common_typos.get(
        normalized,
        " The symbol may be wrong (typo or delisted) or currently unavailable on Yahoo Finance.",
    )


def _run_single_ticker(
    *,
    config: ScheduledAnalysisConfig,
    ticker: str,
    run_dir: Path,
    engine_results_dir: Path,
) -> dict[str, Any]:
    ticker_dir = run_dir / "tickers" / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    ticker_started = datetime.now(ZoneInfo(config.run.timezone))
    timer_start = perf_counter()
    analysis_date = ticker_started.date().isoformat()

    try:
        trade_date = resolve_trade_date(ticker, config)
        stats_handler = StatsCallbackHandler()
        graph = TradingAgentsGraph(
            config.run.analysts,
            debug=False,
            config=_graph_config(config, engine_results_dir),
            callbacks=[stats_handler],
        )
        final_state, decision = graph.propagate(
            ticker,
            trade_date,
            analysis_date=analysis_date,
        )

        report_dir = ticker_dir / "report"
        report_file = save_report_bundle(
            final_state,
            ticker,
            report_dir,
            generated_at=ticker_started,
            language=config.run.output_language,
        )
        final_state_path = ticker_dir / "final_state.json"
        _write_json(final_state_path, _serialize_final_state(final_state))

        graph_log = (
            engine_results_dir
            / ticker
            / "TradingAgentsStrategy_logs"
            / f"full_states_log_{trade_date}.json"
        )
        copied_graph_log = None
        if graph_log.exists():
            copied_graph_log = ticker_dir / graph_log.name
            copied_graph_log.write_text(graph_log.read_text(encoding="utf-8"), encoding="utf-8")

        metrics = stats_handler.get_stats()
        analysis_payload = {
            "ticker": ticker,
            "status": "success",
            "trade_date": trade_date,
            "analysis_date": analysis_date,
            "decision": str(decision),
            "started_at": ticker_started.isoformat(),
            "finished_at": datetime.now(ZoneInfo(config.run.timezone)).isoformat(),
            "duration_seconds": round(perf_counter() - timer_start, 2),
            "metrics": metrics,
            "provider": config.llm.provider,
            "models": {
                "quick_model": config.llm.quick_model,
                "deep_model": config.llm.deep_model,
            },
        }
        analysis_path = ticker_dir / "analysis.json"
        _write_json(analysis_path, analysis_payload)

        return {
            "ticker": ticker,
            "status": "success",
            "trade_date": trade_date,
            "analysis_date": analysis_date,
            "decision": str(decision),
            "started_at": ticker_started.isoformat(),
            "finished_at": analysis_payload["finished_at"],
            "duration_seconds": analysis_payload["duration_seconds"],
            "metrics": metrics,
            "artifacts": {
                "analysis_json": _relative_to_run(run_dir, analysis_path),
                "report_markdown": _relative_to_run(run_dir, report_file),
                "final_state_json": _relative_to_run(run_dir, final_state_path),
                "graph_log_json": _relative_to_run(run_dir, copied_graph_log) if copied_graph_log else None,
            },
        }
    except Exception as exc:
        error_payload = {
            "ticker": ticker,
            "status": "failed",
            "analysis_date": analysis_date,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "started_at": ticker_started.isoformat(),
            "finished_at": datetime.now(ZoneInfo(config.run.timezone)).isoformat(),
            "duration_seconds": round(perf_counter() - timer_start, 2),
        }
        error_path = ticker_dir / "error.json"
        _write_json(error_path, error_payload)

        return {
            "ticker": ticker,
            "status": "failed",
            "analysis_date": analysis_date,
            "trade_date": None,
            "decision": None,
            "error": str(exc),
            "started_at": error_payload["started_at"],
            "finished_at": error_payload["finished_at"],
            "duration_seconds": error_payload["duration_seconds"],
            "metrics": {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0},
            "artifacts": {
                "error_json": _relative_to_run(run_dir, error_path),
            },
        }


def _graph_config(config: ScheduledAnalysisConfig, engine_results_dir: Path) -> dict[str, Any]:
    graph_config = DEFAULT_CONFIG.copy()
    graph_config["results_dir"] = str(engine_results_dir)
    graph_config["llm_provider"] = config.llm.provider
    graph_config["quick_think_llm"] = config.llm.quick_model
    graph_config["deep_think_llm"] = config.llm.deep_model
    graph_config["max_debate_rounds"] = config.run.max_debate_rounds
    graph_config["max_risk_discuss_rounds"] = config.run.max_risk_discuss_rounds
    graph_config["output_language"] = config.run.output_language
    graph_config["codex_reasoning_effort"] = config.llm.codex_reasoning_effort
    graph_config["codex_summary"] = config.llm.codex_summary
    graph_config["codex_personality"] = config.llm.codex_personality
    graph_config["codex_request_timeout"] = config.llm.codex_request_timeout
    graph_config["codex_max_retries"] = config.llm.codex_max_retries
    graph_config["codex_cleanup_threads"] = config.llm.codex_cleanup_threads
    if config.llm.codex_workspace_dir:
        graph_config["codex_workspace_dir"] = config.llm.codex_workspace_dir
    if config.llm.codex_binary:
        graph_config["codex_binary"] = config.llm.codex_binary
    return graph_config


def _serialize_final_state(final_state: dict[str, Any]) -> dict[str, Any]:
    investment_debate = final_state.get("investment_debate_state") or {}
    risk_debate = final_state.get("risk_debate_state") or {}
    return {
        "company_of_interest": final_state.get("company_of_interest"),
        "trade_date": final_state.get("trade_date"),
        "analysis_date": final_state.get("analysis_date"),
        "market_report": final_state.get("market_report"),
        "sentiment_report": final_state.get("sentiment_report"),
        "news_report": final_state.get("news_report"),
        "fundamentals_report": final_state.get("fundamentals_report"),
        "investment_debate_state": {
            "bull_history": investment_debate.get("bull_history", ""),
            "bear_history": investment_debate.get("bear_history", ""),
            "history": investment_debate.get("history", ""),
            "current_response": investment_debate.get("current_response", ""),
            "judge_decision": investment_debate.get("judge_decision", ""),
        },
        "trader_investment_plan": final_state.get("trader_investment_plan", ""),
        "investment_plan": final_state.get("investment_plan", ""),
        "risk_debate_state": {
            "aggressive_history": risk_debate.get("aggressive_history", ""),
            "conservative_history": risk_debate.get("conservative_history", ""),
            "neutral_history": risk_debate.get("neutral_history", ""),
            "history": risk_debate.get("history", ""),
            "judge_decision": risk_debate.get("judge_decision", ""),
        },
        "final_trade_decision": final_state.get("final_trade_decision", ""),
    }


def _settings_snapshot(config: ScheduledAnalysisConfig) -> dict[str, Any]:
    return {
        "provider": config.llm.provider,
        "quick_model": config.llm.quick_model,
        "deep_model": config.llm.deep_model,
        "codex_reasoning_effort": config.llm.codex_reasoning_effort,
        "output_language": config.run.output_language,
        "analysts": list(config.run.analysts),
        "trade_date_mode": config.run.trade_date_mode,
        "max_debate_rounds": config.run.max_debate_rounds,
        "max_risk_discuss_rounds": config.run.max_risk_discuss_rounds,
    }


def _build_run_id(started_at: datetime, run_label: str) -> str:
    clean_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in run_label.strip()) or "run"
    return f"{started_at.strftime('%Y%m%dT%H%M%S')}_{clean_label}"


def _parse_ticker_override(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _previous_business_day(current: date) -> date:
    candidate = current - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _relative_to_run(run_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    return path.relative_to(run_dir).as_posix()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
