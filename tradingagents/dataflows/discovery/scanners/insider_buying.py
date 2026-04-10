"""SEC Form 4 insider buying scanner."""

from typing import Any, Dict, List

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class InsiderBuyingScanner(BaseScanner):
    """Scan SEC Form 4 for insider purchases."""

    name = "insider_buying"
    pipeline = "edge"
    strategy = "insider_buying"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.lookback_days = self.scanner_config.get("lookback_days", 7)
        self.min_transaction_value = self.scanner_config.get("min_transaction_value", 100000)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("Scanning insider buying (OpenInsider)...")

        try:
            from tradingagents.dataflows.finviz_scraper import get_finviz_insider_buying

            transactions = get_finviz_insider_buying(
                lookback_days=self.lookback_days,
                min_value=self.min_transaction_value,
                return_structured=True,
                deduplicate=False,
            )

            if not transactions:
                logger.info("No insider buying transactions found")
                return []

            logger.info(f"Found {len(transactions)} insider transactions")

            # Group by ticker for cluster detection
            by_ticker: Dict[str, list] = {}
            for txn in transactions:
                ticker = txn.get("ticker", "").upper().strip()
                if not ticker:
                    continue
                by_ticker.setdefault(ticker, []).append(txn)

            candidates = []
            for ticker, txns in by_ticker.items():
                # Use the largest transaction as primary
                txns.sort(key=lambda t: t.get("value_num", 0), reverse=True)
                primary = txns[0]

                insider_name = primary.get("insider", "Unknown")
                title = primary.get("title", "")
                value = primary.get("value_num", 0)
                value_str = primary.get("value_str", f"${value:,.0f}")
                num_insiders = len(set(t.get("insider", "") for t in txns))

                # Priority by significance
                title_lower = title.lower()
                is_c_suite = any(
                    t in title_lower for t in ["ceo", "cfo", "coo", "cto", "president", "chairman"]
                )
                is_director = "director" in title_lower

                if num_insiders >= 2:
                    priority = Priority.CRITICAL.value
                elif is_c_suite and value >= 100_000:
                    priority = Priority.CRITICAL.value
                elif is_c_suite or (is_director and value >= 50_000):
                    priority = Priority.HIGH.value
                elif value >= 50_000:
                    priority = Priority.HIGH.value
                else:
                    priority = Priority.MEDIUM.value

                # Build context
                if num_insiders > 1:
                    context = (
                        f"Cluster: {num_insiders} insiders buying {ticker}. "
                        f"Largest: {title} {insider_name} purchased {value_str}"
                    )
                else:
                    context = f"{title} {insider_name} purchased {value_str} of {ticker}"

                # Scoring: cluster buys > C-suite > dollar value
                insider_score = value + (num_insiders * 500_000) + (1_000_000 if is_c_suite else 0)

                candidates.append(
                    {
                        "ticker": ticker,
                        "source": self.name,
                        "context": context,
                        "priority": priority,
                        "strategy": self.strategy,
                        "insider_name": insider_name,
                        "insider_title": title,
                        "transaction_value": value,
                        "num_insiders_buying": num_insiders,
                        "insider_score": insider_score,
                    }
                )

            # Sort by signal quality, then limit
            candidates.sort(key=lambda c: c.get("insider_score", 0), reverse=True)
            candidates = candidates[: self.limit]

            logger.info(f"Insider buying: {len(candidates)} candidates")
            return candidates

        except Exception as e:
            logger.error(f"Insider buying scan failed: {e}", exc_info=True)
            return []


SCANNER_REGISTRY.register(InsiderBuyingScanner)
