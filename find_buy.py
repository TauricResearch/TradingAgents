"""Analyze remaining screened candidates until TradingAgents returns a Buy."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env", override=True)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


CANDIDATES = [
    "000612.SZ",
    "600426.SS",
    "601901.SS",
    "000783.SZ",
    "601108.SS",
    "000951.SZ",
    "600585.SS",
    "600863.SS",
    "600060.SS",
    "600233.SS",
    "000963.SZ",
    "000596.SZ",
    "600867.SS",
    "600595.SS",
    "603369.SS",
    "603596.SS",
    "000933.SZ",
    "601001.SS",
    "603799.SS",
    "601799.SS",
    "601018.SS",
    "605090.SS",
    "000157.SZ",
    "600166.SS",
    "000887.SZ",
    "600021.SS",
    "600363.SS",
    "601377.SS",
    "603556.SS",
    "600428.SS",
]
DATE = "2026-08-25"
BUY_WORDS = {"buy"}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    for ticker in CANDIDATES:
        print(f"\n=== ANALYZING {ticker} ===", flush=True)
        config = DEFAULT_CONFIG.copy()
        config["results_dir"] = str(Path.cwd() / "results")
        config["data_cache_dir"] = str(Path.cwd() / "cache")
        config["output_language"] = "Chinese"
        config["checkpoint_enabled"] = False

        try:
            graph = TradingAgentsGraph(
                selected_analysts=("market", "social", "news", "fundamentals"),
                debug=False,
                config=config,
            )
            final_state, decision = graph.propagate(ticker, DATE, asset_type="stock")
            report_dir = Path(config["results_dir"]) / ticker / DATE
            report_dir.mkdir(parents=True, exist_ok=True)
            graph.save_reports(final_state, ticker, report_dir)
            print(f"DECISION {ticker}: {decision}", flush=True)
            if str(decision).strip().lower() in BUY_WORDS:
                print(f"FOUND BUY: {ticker} ({decision})", flush=True)
                return
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {ticker}: {type(exc).__name__}: {exc}", flush=True)
            continue

    print("NO BUY FOUND in candidate list", flush=True)


if __name__ == "__main__":
    main()
