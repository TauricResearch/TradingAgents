#!/usr/bin/env python3
"""Utility to reset autopilot state and seed sample history for testing."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

# Ensure the project root (one level up from `scripts/`) is importable when the
# script is executed via `python scripts/...` without installing the package.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.services.account import AccountService
from tradingagents.services.auto_trade import AutoTradeResult, AutoTradeService
from tradingagents.services.hypothesis_store import HypothesisStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        default=DEFAULT_CONFIG.get("results_dir", "./results"),
        help="Root directory for TradingAgents results (default: %(default)s)",
    )
    parser.add_argument(
        "--memory-dir",
        default=((DEFAULT_CONFIG.get("auto_trade", {}) or {}).get("memory", {}) or {}).get("dir", "./results/memory"),
        help="Directory that stores ticker memory snapshots (default pulled from config).",
    )
    parser.add_argument(
        "--fixture",
        default="docs/fixtures/autopilot_seed.json",
        help="JSON file containing seed hypotheses/events/memory.",
    )
    parser.add_argument(
        "--skip-fixture",
        action="store_true",
        help="Only wipe state; do not load the fixture data.",
    )
    parser.add_argument(
        "--auto-trade",
        action="store_true",
        help="Run a fresh auto-trade after seeding (requires Alpaca MCP).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt when deleting existing data.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir = Path(args.results_dir).expanduser().resolve()
    hypothesis_dir = results_dir / "hypotheses"
    autopilot_dir = results_dir / "autopilot"
    memory_dir = Path(args.memory_dir).expanduser().resolve()

    targets = [hypothesis_dir, autopilot_dir, memory_dir]
    existing = [path for path in targets if path.exists()]
    if existing and not args.force:
        response = input(
            "This will delete existing hypotheses/autopilot/memory data. Continue? [y/N] "
        ).strip()
        if response.lower() not in {"y", "yes"}:
            print("Aborted.")
            sys.exit(1)

    for path in targets:
        reset_directory(path)

    if args.skip_fixture:
        print("State cleared. No fixture loaded (per --skip-fixture).")
    else:
        seed_fixture(Path(args.fixture), hypothesis_dir, autopilot_dir, memory_dir)

    if args.auto_trade:
        run_auto_trade(results_dir)

    print("\nDone. You can now run `python main.py --autopilot` to test from the seeded state.")


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def seed_fixture(fixture_path: Path, hypothesis_dir: Path, autopilot_dir: Path, memory_dir: Path) -> None:
    if not fixture_path.exists():
        print(f"Fixture {fixture_path} not found; skipping seed.")
        return

    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    hypotheses = payload.get("hypotheses") or []
    if hypotheses:
        out_path = hypothesis_dir / "hypotheses.json"
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(hypotheses, handle, indent=2)
        print(f"Seeded {len(hypotheses)} hypothesis records → {out_path}")

    events = payload.get("events") or []
    if events:
        out_path = autopilot_dir / "events.json"
        autopilot_dir.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(events, handle, indent=2)
        print(f"Seeded {len(events)} autopilot events → {out_path}")

    memory_entries: Dict[str, Any] = payload.get("memory") or {}
    if memory_entries:
        memory_dir.mkdir(parents=True, exist_ok=True)
        for ticker, entries in memory_entries.items():
            ticker_path = memory_dir / f"{ticker.upper()}.json"
            with ticker_path.open("w", encoding="utf-8") as handle:
                json.dump(entries, handle, indent=2)
        print(f"Seeded memory for {len(memory_entries)} ticker(s) → {memory_dir}")


def run_auto_trade(results_dir: Path) -> None:
    print("Running fresh auto-trade to capture new hypotheses …")
    config = DEFAULT_CONFIG.copy()
    graph = TradingAgentsGraph(debug=False, config=config, skip_initial_probes=True)
    try:
        account_service = AccountService(config.get("alpaca_mcp", {}))
        snapshot = account_service.refresh()
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"Failed to refresh account snapshot: {exc}")
        return

    auto_trader = AutoTradeService(config=config, graph=graph)
    try:
        result: AutoTradeResult = auto_trader.run(snapshot)
    except Exception as exc:  # pragma: no cover - surfaced for operator
        print(f"Auto-trade run failed: {exc}")
        return

    store = HypothesisStore(results_dir / "hypotheses")
    new_records = store.record_result(result)
    print(f"Auto-trade run complete. Recorded {len(new_records)} new hypothesis entries.")


if __name__ == "__main__":
    main()
