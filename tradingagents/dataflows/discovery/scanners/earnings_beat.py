"""Post-Earnings Announcement Drift (PEAD) scanner.

Surfaces stocks that recently reported significant EPS beats, capturing
the well-documented post-earnings drift effect: beaten stocks tend to
continue drifting upward for 7–30 days after the announcement.

Research basis: docs/iterations/research/2026-04-14-pead-earnings-beat.md
Key insight: PEAD edge is strongest for small-to-mid caps with >10% EPS
surprise (Bernard & Thomas 1989; QuantPedia 15% annualized, 1987-2004).
Hold window: 7–14 days (primary drift window; effect plateaus ~day 9).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class EarningsBeatScanner(BaseScanner):
    """Scan for recent EPS beats to capture post-earnings drift (PEAD)."""

    name = "earnings_beat"
    pipeline = "events"
    strategy = "pead_drift"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lookback_days = self.scanner_config.get("lookback_days", 14)
        self.min_surprise_pct = self.scanner_config.get("min_surprise_pct", 5.0)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info(
            f"📈 Scanning earnings beats (past {self.lookback_days}d, "
            f">={self.min_surprise_pct}% surprise)..."
        )

        try:
            from tradingagents.dataflows.finnhub_api import get_earnings_calendar

            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")

            earnings = get_earnings_calendar(
                from_date=from_date,
                to_date=to_date,
                return_structured=True,
            )

            if not earnings:
                logger.info("No recent earnings data found")
                return []

            today = datetime.now().date()
            candidates = []

            for event in earnings:
                ticker = event.get("symbol", "").upper().strip()
                if not ticker:
                    continue

                eps_actual = event.get("epsActual")
                eps_estimate = event.get("epsEstimate")
                earnings_date_str = event.get("date", "")

                # Need both actual and estimate to compute surprise
                if eps_actual is None or eps_estimate is None:
                    continue

                # Avoid division by zero; skip stub/loss estimates near zero
                if eps_estimate == 0:
                    continue

                surprise_pct = ((eps_actual - eps_estimate) / abs(eps_estimate)) * 100

                if surprise_pct < self.min_surprise_pct:
                    continue

                # Days since announcement
                try:
                    earnings_date = datetime.strptime(earnings_date_str, "%Y-%m-%d").date()
                    days_ago = (today - earnings_date).days
                except (ValueError, TypeError):
                    days_ago = None

                # Priority by surprise magnitude
                if surprise_pct >= 20:
                    priority = Priority.CRITICAL.value
                elif surprise_pct >= 10:
                    priority = Priority.HIGH.value
                else:
                    priority = Priority.MEDIUM.value

                days_ago_str = f"{days_ago}d ago" if days_ago is not None else "recently"
                context = (
                    f"Earnings beat {days_ago_str}: actual ${eps_actual:.2f} vs "
                    f"est ${eps_estimate:.2f} (+{surprise_pct:.1f}% surprise) "
                    f"— PEAD drift window open"
                )

                candidates.append(
                    {
                        "ticker": ticker,
                        "source": self.name,
                        "context": context,
                        "priority": priority,
                        "strategy": self.strategy,
                        "eps_surprise_pct": surprise_pct,
                        "eps_actual": eps_actual,
                        "eps_estimate": eps_estimate,
                        "days_since_earnings": days_ago,
                    }
                )

            # Sort by surprise magnitude (largest beats first)
            candidates.sort(key=lambda x: x.get("eps_surprise_pct", 0), reverse=True)
            candidates = candidates[: self.limit]

            logger.info(f"Earnings beats (PEAD): {len(candidates)} candidates")
            return candidates

        except Exception as e:
            logger.warning(f"⚠️  Earnings beat scanner failed: {e}")
            return []


SCANNER_REGISTRY.register(EarningsBeatScanner)
