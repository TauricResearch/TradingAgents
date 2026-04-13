"""Short interest squeeze-risk scanner.

Surfaces stocks with structurally elevated short interest where any positive
catalyst (earnings beat, news, options activity) could force rapid short covering.

Research basis: docs/iterations/research/2026-04-12-short-interest-squeeze.md
Key insight: High SI alone predicts *negative* long-term returns (mean reversion);
the edge is using high SI as a squeeze-risk flag for downstream cross-scanner
ranker scoring, not as a directional buy signal on its own.
"""

from typing import Any, Dict, List

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

_SIGNAL_LABELS = {
    "extreme_squeeze_risk": "extreme squeeze risk",
    "high_squeeze_potential": "high squeeze potential",
    "moderate_squeeze_potential": "moderate squeeze potential",
    "low_squeeze_potential": "low squeeze potential",
}


class ShortSqueezeScanner(BaseScanner):
    """Scan for stocks with high short interest and elevated squeeze risk."""

    name = "short_squeeze"
    pipeline = "edge"
    strategy = "short_squeeze"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.min_short_interest_pct = self.scanner_config.get("min_short_interest_pct", 15.0)
        self.min_days_to_cover = self.scanner_config.get("min_days_to_cover", 2.0)
        self.top_n = self.scanner_config.get("top_n", 20)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info(f"📉 Scanning short interest (SI >{self.min_short_interest_pct}%)...")

        try:
            from tradingagents.dataflows.finviz_scraper import get_short_interest

            raw = get_short_interest(
                min_short_interest_pct=self.min_short_interest_pct,
                min_days_to_cover=self.min_days_to_cover,
                top_n=self.top_n,
                return_structured=True,
            )

            if not raw:
                logger.info("No short squeeze candidates found")
                return []

            logger.info(f"Found {len(raw)} high short interest candidates")

            candidates = []
            for item in raw:
                ticker = item.get("ticker", "").upper().strip()
                if not ticker:
                    continue

                si_pct = item.get("short_interest_pct", 0)
                dtc = item.get("days_to_cover", 0.0)
                signal = item.get("signal", "low_squeeze_potential")
                label = _SIGNAL_LABELS.get(signal, signal)

                # Priority based on squeeze intensity
                if signal == "extreme_squeeze_risk":
                    priority = Priority.CRITICAL.value
                elif signal == "high_squeeze_potential":
                    priority = Priority.HIGH.value
                else:
                    priority = Priority.MEDIUM.value

                dtc_str = f"{dtc:.1f}" if dtc else "N/A"
                context = (
                    f"Short interest {si_pct:.1f}% of float, {dtc_str} days to cover — {label}"
                    " | squeeze risk elevates if catalyst arrives"
                )

                candidates.append(
                    {
                        "ticker": ticker,
                        "source": self.name,
                        "context": context,
                        "priority": priority,
                        "strategy": self.strategy,
                        "short_interest_pct": si_pct,
                        "days_to_cover": dtc,
                        "squeeze_signal": signal,
                    }
                )

            candidates = candidates[: self.limit]
            return candidates

        except Exception as e:
            logger.warning(f"⚠️  Short squeeze scanner failed: {e}")
            return []


SCANNER_REGISTRY.register(ShortSqueezeScanner)
