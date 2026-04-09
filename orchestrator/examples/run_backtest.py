"""
Example: Run orchestrator backtest for 宁德时代 (300750.SZ) over 2023.

Usage:
    cd /path/to/TradingAgents
    QUANT_BACKTEST_PATH=/path/to/quant_backtest python orchestrator/examples/run_backtest.py
"""
import json
import logging
import os
import sys

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from orchestrator.config import OrchestratorConfig
from orchestrator.orchestrator import TradingOrchestrator
from orchestrator.backtest_mode import BacktestMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

config = OrchestratorConfig(
    quant_backtest_path=os.environ.get("QUANT_BACKTEST_PATH", ""),
    cache_dir="orchestrator/cache",
)

orchestrator = TradingOrchestrator(config)
backtest = BacktestMode(orchestrator)

result = backtest.run(
    tickers=["300750.SZ"],
    start_date="2023-01-01",
    end_date="2023-12-31",
)

print(f"\n=== Backtest Summary ===")
print(json.dumps(result.summary, indent=2, ensure_ascii=False))
print(f"\nTotal records: {len(result.records)}")
if result.records:
    print(f"First record: {result.records[0]}")
    print(f"Last record:  {result.records[-1]}")
