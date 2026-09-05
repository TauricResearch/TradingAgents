"""Run a TradingAgents analysis for a single ticker without the interactive CLI."""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env", override=True)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    raw_args = sys.argv[1:]
    fresh = "--fresh" in raw_args
    args = [arg for arg in raw_args if arg != "--fresh"]
    ticker = args[0] if args else "000021.SZ"
    date = args[1] if len(args) > 1 else "2026-08-24"

    try:
        config = DEFAULT_CONFIG.copy()
        config["results_dir"] = str(Path.cwd() / "results")
        config["data_cache_dir"] = str(Path.cwd() / "cache")
        config["output_language"] = "Chinese"
        config["checkpoint_enabled"] = not fresh

        graph = TradingAgentsGraph(
            selected_analysts=("market", "social", "news", "fundamentals"),
            debug=True,
            config=config,
        )

        final_state, decision = graph.propagate(ticker, date, asset_type="stock")

        report_dir = Path(config["results_dir"]) / ticker / date
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = graph.save_reports(final_state, ticker, report_dir)

        print("\n=== FINAL DECISION ===")
        print(decision)
        print(f"\nReports saved to: {report_path}")
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 - fail with a clear, non-traceback line
        print(f"ERROR: analysis failed for {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
