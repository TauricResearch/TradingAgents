import sys
from pathlib import Path

from fastapi import APIRouter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tradingagents.agents.utils.memory import TradingMemoryLog  # noqa: E402
from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402

router = APIRouter(prefix="/memory", tags=["Memory"])

@router.get("")
async def get_memory_log(ticker: str | None = None):
    """Retrieve persistent trading memory decisions, reflections, and past lessons."""
    memory_log = TradingMemoryLog(DEFAULT_CONFIG)
    entries = memory_log.load_entries()

    if ticker:
        ticker_upper = ticker.strip().upper()
        entries = [e for e in entries if e.get("ticker", "").upper() == ticker_upper]

    return {
        "total_entries": len(entries),
        "entries": entries
    }

@router.get("/{ticker}")
async def get_memory_for_ticker(ticker: str):
    """Retrieve memory entries for a specific ticker."""
    return await get_memory_log(ticker=ticker)

