import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


class LiveMode:
    """
    Triggers signal computation for a list of tickers and broadcasts
    results via a callback (e.g., WebSocket send).
    """

    def __init__(self, orchestrator):
        self._orchestrator = orchestrator

    async def run_once(self, tickers: List[str], date: Optional[str] = None) -> List[dict]:
        """
        Compute combined signals for all tickers on the given date (default: today).
        Returns list of signal dicts.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        results = []
        for ticker in tickers:
            try:
                sig = await asyncio.to_thread(
                    self._orchestrator.get_combined_signal, ticker, date
                )
                results.append({
                    "ticker": ticker,
                    "date": date,
                    "direction": sig.direction,
                    "confidence": sig.confidence,
                    "quant_direction": sig.quant_signal.direction if sig.quant_signal else None,
                    "llm_direction": sig.llm_signal.direction if sig.llm_signal else None,
                    "timestamp": sig.timestamp.isoformat(),
                })
            except Exception as e:
                logger.error("LiveMode: failed for %s %s: %s", ticker, date, e)
                results.append({
                    "ticker": ticker,
                    "date": date,
                    "error": str(e),
                })
        return results
