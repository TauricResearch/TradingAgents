#!/usr/bin/env python3
"""Generate LLM summaries for all analyses that don't have one yet.

Usage:
    python scripts/summarize_analyses.py          # Summarise all unsaved analyses
    python scripts/summarize_analyses.py --ticker TKA.DE  # Only one ticker
    python scripts/summarize_analyses.py --all              # Regenerate all

Pipeline:
    1. Scan ~/.tradingagents/logs/ for full_states_log_*.json files
    2. Check if summary_*.json already exists (skip if cached)
    3. Call OpenRouter API to generate structured summary
    4. Write summary_*.json next to the log file

Run this daily to keep analysis summaries up to date.
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LOGS_DIR = Path(os.getenv(
    "TRADINGAGENTS_RESULTS_DIR",
    Path.home() / ".tradingagents" / "logs",
)).expanduser()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("SUMMARY_MODEL", "openai/gpt-5.4-mini")

SYSTEM_PROMPT = """You are a financial analyst explaining trading decisions in plain English.
Given an analysis decision, extract these fields as JSON:
- signal: the recommendation (Buy/Hold/Sell/Overweight/Underweight)
- confidence: 0-1 number
- position_size: recommended position sizing
- entry_strategy: how and when to enter the position
- risk_management: stop losses, invalidation levels, risk controls
- time_horizon: expected holding period
- catalysts: what events or conditions to monitor
- risks: key risk factors
- plain_english: a 2-3 sentence explanation of what this means for an investor

Respond with ONLY valid JSON. No markdown, no explanation."""


def find_analyses(ticker_filter: str | None = None) -> list[Path]:
    """Find all analysis log files."""
    if not LOGS_DIR.exists():
        print(f"Logs directory not found: {LOGS_DIR}")
        return []

    results = []
    for ticker_dir in sorted(LOGS_DIR.iterdir()):
        if not ticker_dir.is_dir():
            continue
        if ticker_filter and ticker_dir.name != ticker_filter:
            continue

        log_dir = ticker_dir / "TradingAgentsStrategy_logs"
        if not log_dir.exists():
            continue

        for log_file in sorted(log_dir.glob("full_states_log_*.json")):
            summary_file = log_dir / f"summary_{log_file.stem.replace('full_states_log_', '')}.json"
            results.append((log_file, summary_file))

    return results


def generate_summary(decision: str, reports: dict, ticker: str, date: str) -> dict:
    """Call OpenRouter API to generate summary."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set in .env")

    user_prompt = (
        f"Analyse this trading decision for {ticker} on {date}.\n\n"
        f"Decision:\n{decision[:2000]}\n\n"
        f"Agent reports:\n{json.dumps(reports, indent=2)[:2000]}"
    )

    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }).encode()

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API error {e.code}: {e.read().decode()[:200]}")

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Empty response from LLM")

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"plain_english": content}


def main():
    parser = argparse.ArgumentParser(description="Generate LLM summaries for analyses")
    parser.add_argument("--ticker", help="Only process this ticker")
    parser.add_argument("--all", action="store_true", help="Regenerate all summaries (ignore cache)")
    args = parser.parse_args()

    analyses = find_analyses(args.ticker)
    if not analyses:
        print("No analyses found.")
        return

    print(f"Found {len(analyses)} analyses")
    done = 0
    skipped = 0
    errors = 0

    for log_file, summary_file in analyses:
        date = log_file.stem.replace("full_states_log_", "")
        ticker = log_file.parent.parent.name

        if not args.all and summary_file.exists():
            print(f"  SKIP {ticker} {date} (cached)")
            skipped += 1
            continue

        print(f"  PROCESS {ticker} {date}... ", end="", flush=True)

        try:
            with open(log_file) as f:
                state = json.load(f)

            decision = str(state.get("final_trade_decision", ""))
            reports = {}
            for key, value in state.items():
                if isinstance(value, str) and key.endswith("_report") and value:
                    reports[key.replace("_report", "")] = value[:1000]

            summary = generate_summary(decision, reports, ticker, date)

            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)

            print(f"OK ({summary.get('signal', '?')}, conf {summary.get('confidence', '?')})")
            done += 1
            time.sleep(1)  # Rate limit

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

    print(f"\nDone: {done} generated, {skipped} cached, {errors} errors")


if __name__ == "__main__":
    main()
