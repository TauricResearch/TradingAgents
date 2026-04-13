import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from orchestrator.contracts.config_schema import CONTRACT_VERSION
from orchestrator.contracts.error_taxonomy import ReasonCode

logger = logging.getLogger(__name__)


class LiveMode:
    """
    Triggers signal computation for a list of tickers and broadcasts
    results via a callback (e.g., WebSocket send).
    """

    def __init__(self, orchestrator):
        self._orchestrator = orchestrator

    @staticmethod
    def _serialize_result(signal) -> dict:
        return {
            "direction": signal.direction,
            "confidence": signal.confidence,
            "quant_direction": signal.quant_signal.direction if signal.quant_signal else None,
            "llm_direction": signal.llm_signal.direction if signal.llm_signal else None,
            "timestamp": signal.timestamp.isoformat(),
        }

    @staticmethod
    def _serialize_degradation(signal, data_quality: Optional[dict]) -> dict:
        metadata = getattr(signal, "metadata", {}) or {}
        return {
            "degraded": bool(getattr(signal, "degrade_reason_codes", ())) or bool(data_quality),
            "reason_codes": list(getattr(signal, "degrade_reason_codes", ()) or ()),
            "source_diagnostics": metadata.get("source_diagnostics") or {},
        }

    @staticmethod
    def _contract_version(signal) -> str:
        metadata = getattr(signal, "metadata", {}) or {}
        return getattr(signal, "contract_version", None) or metadata.get("contract_version") or CONTRACT_VERSION

    def _serialize_signal(self, *, ticker: str, date: str, signal) -> dict:
        metadata = getattr(signal, "metadata", {}) or {}
        data_quality = metadata.get("data_quality")
        degradation = self._serialize_degradation(signal, data_quality)
        return {
            "contract_version": self._contract_version(signal),
            "ticker": ticker,
            "date": date,
            "status": "degraded_success" if degradation["degraded"] else "completed",
            "result": self._serialize_result(signal),
            "error": None,
            "degradation": degradation,
            "data_quality": data_quality,
        }

    @staticmethod
    def _serialize_error(*, ticker: str, date: str, exc: Exception) -> dict:
        reason_codes = []
        if isinstance(exc, ValueError) and "both quant and llm signals are None" in str(exc):
            reason_codes.append(ReasonCode.BOTH_SIGNALS_UNAVAILABLE.value)
        return {
            "contract_version": CONTRACT_VERSION,
            "ticker": ticker,
            "date": date,
            "status": "failed",
            "result": None,
            "error": {
                "code": "live_signal_failed",
                "message": str(exc),
                "retryable": False,
            },
            "degradation": {
                "degraded": bool(reason_codes),
                "reason_codes": reason_codes,
                "source_diagnostics": {},
            },
            "data_quality": None,
        }

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
                results.append(self._serialize_signal(ticker=ticker, date=date, signal=sig))
            except Exception as e:
                logger.error("LiveMode: failed for %s %s: %s", ticker, date, e)
                results.append(self._serialize_error(ticker=ticker, date=date, exc=e))
        return results
