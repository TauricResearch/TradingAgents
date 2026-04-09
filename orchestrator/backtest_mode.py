import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List

from orchestrator.signals import FinalSignal

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    records: List[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class BacktestMode:
    def __init__(self, orchestrator):
        self._orchestrator = orchestrator

    def run(self, tickers: List[str], start_date: str, end_date: str) -> BacktestResult:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        records = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # skip weekends
                date_str = current.strftime("%Y-%m-%d")
                for ticker in tickers:
                    try:
                        sig = self._orchestrator.get_combined_signal(ticker, date_str)
                        records.append({
                            "ticker": ticker,
                            "date": date_str,
                            "direction": sig.direction,
                            "confidence": sig.confidence,
                            "quant_direction": sig.quant_signal.direction if sig.quant_signal else None,
                            "llm_direction": sig.llm_signal.direction if sig.llm_signal else None,
                        })
                    except Exception as e:
                        logger.error("BacktestMode: failed for %s %s: %s", ticker, date_str, e)
            current += timedelta(days=1)

        summary = self._compute_summary(records, tickers)
        return BacktestResult(records=records, summary=summary)

    def _compute_summary(self, records: List[dict], tickers: List[str]) -> dict:
        summary = {}
        for ticker in tickers:
            ticker_records = [r for r in records if r["ticker"] == ticker]
            if not ticker_records:
                summary[ticker] = {"total_days": 0}
                continue
            directions = [r["direction"] for r in ticker_records]
            confidences = [r["confidence"] for r in ticker_records]
            summary[ticker] = {
                "total_days": len(ticker_records),
                "buy_days": directions.count(1),
                "sell_days": directions.count(-1),
                "hold_days": directions.count(0),
                "avg_confidence": sum(confidences) / len(confidences),
            }
        return summary
