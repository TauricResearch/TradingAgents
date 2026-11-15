"""Run a BABA CLI smoke test with a matured R4 decision in an isolated log."""

import argparse
import os
from datetime import datetime, time
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import yfinance
from dotenv import load_dotenv


def latest_test_dates() -> tuple[str, str]:
    bars = yfinance.Ticker("BABA").history(period="1mo", interval="1d", auto_adjust=False)
    now = datetime.now(ZoneInfo("America/New_York"))
    sessions = [
        stamp.date() for stamp in bars.index
        if stamp.date() < now.date()
        or (stamp.date() == now.date() and now.time() >= time(17))
    ]
    if len(sessions) < 11:
        raise RuntimeError("Yahoo returned too few completed BABA sessions for the latest test")
    return sessions[-11].isoformat(), sessions[-1].isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest", action="store_true", help="use the latest completed BABA session")
    args = parser.parse_args()
    load_dotenv(Path.cwd() / ".env", override=False)
    load_dotenv(Path.cwd() / ".env.enterprise", override=False)
    if not os.environ.get("OPENAI_COMPATIBLE_API_KEY"):
        raise SystemExit("OPENAI_COMPATIBLE_API_KEY is required")

    yfinance.set_tz_cache_location(str(Path.cwd() / ".venv" / "r4-live-yf-cache"))
    decision_date, analysis_date = (
        latest_test_dates() if args.latest else ("2026-10-01", "2026-10-15")
    )
    run_dir = Path.cwd().parent / "pre_evidence" / f"cli-r4-{uuid4().hex[:8]}"
    run_dir.mkdir(parents=True)
    settings = {
        "TRADINGAGENTS_MEMORY_LOG_PATH": str(run_dir / "memory.md"),
        "TRADINGAGENTS_RESULTS_DIR": str(run_dir / "results"),
        "TRADINGAGENTS_CACHE_DIR": str(run_dir / "cache"),
        "TRADINGAGENTS_LLM_PROVIDER": "openai_compatible",
        "TRADINGAGENTS_LLM_BACKEND_URL": "https://llm.cs.cityu.edu.hk/v1",
        "TRADINGAGENTS_QUICK_THINK_LLM": "CS5351/DeepSeek-V4-Flash",
        "TRADINGAGENTS_DEEP_THINK_LLM": "CS5351/DeepSeek-V4-Flash",
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
        "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
        "TRADINGAGENTS_MAX_TOOL_ROUNDS": "2",
        "TRADINGAGENTS_MAX_TOKENS": "4096",
    }
    os.environ.update(settings)

    import cli.prefs
    from cli.main import app
    from tradingagents.memory import TradingMemoryLog

    cli.prefs._PREFS_PATH = run_dir / "cli_prefs.json"
    memory = TradingMemoryLog({"memory_log_path": settings["TRADINGAGENTS_MEMORY_LOG_PATH"]})
    memory.store_decision(
        "BABA",
        decision_date,
        "**Rating**: Buy\n\nTest-only thesis: BABA may outperform SPY over five trading days.",
    )
    print(f"CLI evidence directory: {run_dir}", flush=True)
    print(f"Test dates: previous {decision_date}; analysis {analysis_date}", flush=True)

    app(
        args=[
            "--checkpoint",
            "--ticker", "BABA",
            "--date", analysis_date,
            "--analysts", "market",
            "--no-save",
            "--no-show",
            "--no-html",
        ],
        standalone_mode=False,
    )

    entries = memory.load_entries()
    previous = next(e for e in entries if e["date"] == decision_date and e["ticker"] == "BABA")
    current = next(e for e in entries if e["date"] == analysis_date and e["ticker"] == "BABA")
    if previous["pending"] or not previous["reflection"].strip():
        raise RuntimeError("CLI did not settle the previous R4 decision with a reflection")
    if not current["pending"]:
        raise RuntimeError("CLI did not record the new analysis as pending")
    print("R4 CLI LIVE SMOKE: PASS")
    print(f"Previous decision: resolved {previous['resolved']}, net {previous['raw']}, alpha {previous['alpha']}")
    print(f"New BABA analysis: pending on {analysis_date}")
    print(f"Memory log: {settings['TRADINGAGENTS_MEMORY_LOG_PATH']}")


if __name__ == "__main__":
    main()
