"""Semantic news scanner for early catalyst detection."""

from typing import Any, Dict, List

from tradingagents.dataflows.discovery.scanner_registry import SCANNER_REGISTRY, BaseScanner
from tradingagents.dataflows.discovery.utils import Priority
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

# Catalyst keywords for priority classification
CATALYST_KEYWORDS = {
    Priority.CRITICAL.value: [
        "fda approval",
        "acquisition",
        "merger",
        "buyout",
        "takeover",
        "breakthrough",
        "approved",
    ],
    Priority.HIGH.value: [
        "upgrade",
        "initiated",
        "beat",
        "surprise",
        "contract win",
        "patent",
        "revenue growth",
        "guidance raise",
        "price target",
    ],
    Priority.MEDIUM.value: [
        "downgrade",
        "miss",
        "lawsuit",
        "investigation",
        "recall",
        "warning",
        "delayed",
    ],
}


class SemanticNewsScanner(BaseScanner):
    """Scan news for early catalysts using semantic analysis."""

    name = "semantic_news"
    pipeline = "news"
    strategy = "news_catalyst"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.sources = self.scanner_config.get("sources", ["google_news"])
        self.lookback_hours = self.scanner_config.get("lookback_hours", 6)
        self.min_importance = self.scanner_config.get("min_news_importance", 5)
        self.min_similarity = self.scanner_config.get("min_similarity", 0.5)

    def scan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        logger.info("📰 Scanning news catalysts...")

        try:
            from datetime import datetime

            from tradingagents.tools.executor import execute_tool

            # Get recent global news
            date_str = datetime.now().strftime("%Y-%m-%d")
            result = execute_tool("get_global_news", date=date_str)

            if not result or not isinstance(result, str):
                return []

            # Split into individual news items (lines or paragraphs)
            import re

            # Each news item typically starts with a headline or bullet point
            news_lines = [line.strip() for line in result.split("\n") if line.strip()]

            stop_words = {
                "NYSE",
                "NASDAQ",
                "CEO",
                "CFO",
                "IPO",
                "ETF",
                "USA",
                "SEC",
                "NEWS",
                "STOCK",
                "MARKET",
                "GDP",
                "CPI",
                "FED",
                "THE",
                "FOR",
                "AND",
                "ARE",
                "NOT",
                "BUT",
                "HAS",
                "WAS",
                "INC",
                "LTD",
                "LLC",
                "EST",
                "PDT",
            }

            # Extract tickers from each line along with the headline context
            ticker_headlines: dict = {}  # ticker -> best headline
            ticker_pattern = r"\$([A-Z]{2,5})\b|\b([A-Z]{2,5})\b"

            for line in news_lines:
                matches = re.findall(ticker_pattern, line)
                for match in matches:
                    ticker = (match[0] or match[1]).upper()
                    if ticker in stop_words or len(ticker) < 2:
                        continue
                    # Keep the first (most relevant) headline per ticker
                    if ticker not in ticker_headlines:
                        # Clean headline: strip markdown/bullets
                        headline = re.sub(r"^[-*•]\s*", "", line).strip()[:150]
                        ticker_headlines[ticker] = headline

            candidates = []
            for ticker, headline in list(ticker_headlines.items())[: self.limit]:
                priority = self._classify_catalyst(headline)

                # Only emit candidates with CRITICAL catalysts (FDA approval,
                # acquisition, merger, etc.). HIGH and MEDIUM candidates include
                # negative events (downgrades, lawsuits) that produce false positives
                # and dragged news_catalyst to -17.5% avg 30d return (0% 7d win rate).
                if priority != Priority.CRITICAL.value:
                    continue

                context = f"News catalyst: {headline}"

                candidates.append(
                    {
                        "ticker": ticker,
                        "source": self.name,
                        "context": context,
                        "priority": priority,
                        "strategy": self.strategy,
                        "news_headline": headline,
                    }
                )

            logger.info(f"Found {len(candidates)} news mentions")
            return candidates

        except Exception as e:
            logger.warning(f"⚠️  News scan failed: {e}")
            return []

    def _classify_catalyst(self, headline: str) -> str:
        """Classify news headline by catalyst type and return priority."""
        headline_lower = headline.lower()
        for priority, keywords in CATALYST_KEYWORDS.items():
            if any(kw in headline_lower for kw in keywords):
                return priority
        return Priority.MEDIUM.value


SCANNER_REGISTRY.register(SemanticNewsScanner)
