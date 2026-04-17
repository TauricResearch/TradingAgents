"""
Example: Run orchestrator live mode for a list of tickers.

Usage:
    cd /path/to/TradingAgents
    QUANT_BACKTEST_PATH=/path/to/quant_backtest python orchestrator/examples/run_live.py
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from orchestrator.config import OrchestratorConfig
from orchestrator.orchestrator import TradingOrchestrator
from orchestrator.live_mode import LiveMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TICKERS = ["300750.SZ", "603259.SS"]

config = OrchestratorConfig(
    quant_backtest_path=os.environ.get("QUANT_BACKTEST_PATH", ""),
    cache_dir="orchestrator/cache",
)

orchestrator = TradingOrchestrator(config)
live = LiveMode(orchestrator)


async def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\n=== Live Signals for {today} ===")
    results = await live.run_once(TICKERS, date=today)
    print(json.dumps(results, indent=2, ensure_ascii=False))


asyncio.run(main())
