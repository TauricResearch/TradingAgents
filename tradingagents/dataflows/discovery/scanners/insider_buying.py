"""SEC Form 4 insider buying scanner."""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Set

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
        # Raised from $25K to $100K: P&L data (178 recs, -2.05% 30d avg) suggests
        # sub-$100K transactions add noise. Tests the insider_buying-min-txn-100k
        # hypothesis registered 2026-04-07.
        self.min_transaction_value = self.scanner_config.get("min_transaction_value", 100_000)

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

            # Staleness suppression: filter tickers already recommended as insider_buying
            # in the past 2 days (same Form 4 filing appears daily within lookback_days window)
            recently_seen = self._load_recent_insider_tickers(suppress_days=2)
            if recently_seen:
                before_tickers = {c["ticker"] for c in candidates}
                candidates = [c for c in candidates if c["ticker"] not in recently_seen]
                suppressed = before_tickers - {c["ticker"] for c in candidates}
                if suppressed:
                    logger.info(
                        f"Staleness filter: suppressed {len(suppressed)} ticker(s) already "
                        f"recommended as insider_buying in the past 2 days: {suppressed}"
                    )

            logger.info(f"Insider buying: {len(candidates)} candidates")
            return candidates

        except Exception as e:
            logger.error(f"Insider buying scan failed: {e}", exc_info=True)
            return []

    def _load_recent_insider_tickers(self, suppress_days: int = 2) -> Set[str]:
        """Return tickers recommended as insider_buying in the past N days.

        Used to suppress stale Form 4 filings that re-appear daily within the
        lookback_days window.  P&L review (Apr 3-9 2026) confirmed 3 tickers
        (PAGS, ZBIO, HMH) each repeated 3-4 consecutive days from the same filing.
        """
        seen: Set[str] = set()
        data_dir = Path(self.config.get("data_dir", "data"))
        recs_dir = data_dir / "recommendations"

        if not recs_dir.exists():
            return seen

        today = date.today()
        for i in range(1, suppress_days + 1):
            check_date = today - timedelta(days=i)
            rec_file = recs_dir / f"{check_date.isoformat()}.json"
            if not rec_file.exists():
                continue
            try:
                with open(rec_file) as f:
                    data = json.load(f)
                for rec in data.get("recommendations", []):
                    if rec.get("strategy_match") == "insider_buying":
                        ticker = rec.get("ticker", "").upper()
                        if ticker:
                            seen.add(ticker)
            except Exception:
                pass

        return seen


SCANNER_REGISTRY.register(InsiderBuyingScanner)
