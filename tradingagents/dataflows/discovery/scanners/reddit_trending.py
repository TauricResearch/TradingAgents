"""Reddit trending scanner - migrated from legacy TraditionalScanner."""

from typing import Any, Dict, List

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class RedditTrendingScanner(BaseScanner):
    """Scan for trending tickers on Reddit."""

    name = "reddit_trending"
    pipeline = "social"
    strategy = "social_hype"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("📱 Scanning Reddit trending...")

        from tradingagents.tools.executor import execute_tool

        try:
            result = execute_tool("get_trending_tickers", limit=self.limit)

            if not result or not isinstance(result, str):
                return []

            if "Error" in result or "No trending" in result:
                logger.warning(f"⚠️  {result}")
                return []

            # Extract tickers using common utility
            from collections import Counter

            from tradingagents.dataflows.discovery.common_utils import extract_tickers_from_text

            tickers_found = extract_tickers_from_text(result)

            # Count ticker mentions in the raw text for priority scaling
            ticker_counts = Counter()
            for ticker in tickers_found:
                # Count occurrences in the original text
                count = result.upper().count(ticker)
                ticker_counts[ticker] = max(count, 1)

            # Deduplicate while preserving order
            seen = set()
            unique_tickers = []
            for t in tickers_found:
                if t not in seen:
                    seen.add(t)
                    unique_tickers.append(t)

            candidates = []
            for ticker in unique_tickers[: self.limit]:
                count = ticker_counts.get(ticker, 1)

                if count >= 50:
                    priority = Priority.HIGH.value
                else:
                    # Skip MEDIUM (20-49) and LOW (<20) priority candidates.
                    # P&L data showed social_hype at -10.64% avg 30d return across
                    # 22 recommendations — low-count mentions are noise, not signal.
                    # Only genuinely viral tickers (>=50 mentions) have a plausible
                    # momentum thesis worth surfacing.
                    continue

                context = f"Trending on Reddit: ~{count} mentions"

                candidates.append(
                    {
                        "ticker": ticker,
                        "source": self.name,
                        "context": context,
                        "priority": priority,
                        "strategy": self.strategy,
                        "mention_count": count,
                    }
                )

            logger.info(f"Found {len(candidates)} Reddit trending tickers")
            return candidates

        except Exception as e:
            logger.warning(f"⚠️  Reddit trending failed: {e}")
            return []


SCANNER_REGISTRY.register(RedditTrendingScanner)
