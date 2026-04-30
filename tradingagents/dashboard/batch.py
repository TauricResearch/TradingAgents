from __future__ import annotations

import argparse
import traceback
from pathlib import Path
from time import perf_counter
from typing import Iterable, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from .extract import build_analysis_record, utc_now_iso
from .models import BatchSummary
from .storage import AnalysisRepository


DEFAULT_TICKERS = ["NVDA", "AAPL", "MSFT"]
DEFAULT_ARTIFACT_DIR = Path("artifacts") / "dashboard"


def build_batch_config(base_dir: str | Path, *, use_hermes_codex_auth: bool = False):
    artifact_dir = Path(base_dir)
    raw_results_dir = artifact_dir / "raw_results"
    cache_dir = artifact_dir / "cache"
    memory_dir = artifact_dir / "memory"
    config = DEFAULT_CONFIG.copy()
    config["results_dir"] = str(raw_results_dir)
    config["data_cache_dir"] = str(cache_dir)
    config["memory_log_path"] = str(memory_dir / "trading_memory.md")
    config["openai_use_hermes_codex_auth"] = use_hermes_codex_auth
    config["output_language"] = "Korean"
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["quick_think_llm"] = "gpt-5.4-mini"
    config["deep_think_llm"] = "gpt-5.4-mini"
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    return config


def run_batch_analysis(
    tickers: Iterable[str],
    trade_date: str,
    *,
    artifact_dir: str | Path = DEFAULT_ARTIFACT_DIR,
    use_hermes_codex_auth: bool = False,
    debug: bool = False,
) -> BatchSummary:
    tickers = [ticker.upper() for ticker in tickers]
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    repository = AnalysisRepository(artifact_dir)
    config = build_batch_config(
        artifact_dir,
        use_hermes_codex_auth=use_hermes_codex_auth,
    )
    graph = TradingAgentsGraph(debug=debug, config=config)

    completed = 0
    failed = []
    run_ids: List[str] = []

    for ticker in tickers:
        started = perf_counter()
        try:
            final_state, _ = graph.propagate(ticker, trade_date)
            raw_log_path = artifact_dir / "raw_results" / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"
            record = build_analysis_record(
                final_state,
                generated_at=utc_now_iso(),
                raw_log_path=str(raw_log_path),
                metadata={
                    "elapsed_seconds": round(perf_counter() - started, 2),
                    "llm_provider": config["llm_provider"],
                    "quick_think_llm": config["quick_think_llm"],
                    "deep_think_llm": config["deep_think_llm"],
                },
            )
            stored = repository.save(record)
            run_ids.append(stored["run_id"])
            completed += 1
        except Exception as exc:  # pragma: no cover - exercised by live runs
            failed.append(
                {
                    "ticker": ticker,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

    return {
        "artifact_dir": str(artifact_dir),
        "trade_date": trade_date,
        "tickers": tickers,
        "completed": completed,
        "failed": failed,
        "run_ids": run_ids,
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TradingAgents batch analyses and persist dashboard data.")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--openai-use-hermes-codex-auth", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    summary = run_batch_analysis(
        args.tickers,
        args.trade_date,
        artifact_dir=args.artifact_dir,
        use_hermes_codex_auth=args.openai_use_hermes_codex_auth,
        debug=args.debug,
    )
    print(summary)
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
