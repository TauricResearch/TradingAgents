"""
Google Custom Search client with daily quota guard.

Prevents exceeding the free tier (100 queries/day) with:
- Hard block when limit is reached
- Warning threshold when approaching limit
- Automatic daily reset
"""

import logging
from dataclasses import dataclass, field
from datetime import date

import httpx

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when the daily search quota is exhausted."""

    def __init__(self, usage: int, limit: int):
        self.usage = usage
        self.limit = limit
        super().__init__(
            f"Google Search daily quota exceeded: {usage}/{limit} queries used. "
            "Resets at midnight UTC. Check GOOGLE_SEARCH_DAILY_LIMIT to increase."
        )


@dataclass
class QuotaManager:
    """Tracks daily API usage and enforces the quota limit."""

    daily_limit: int
    warn_threshold: float = 0.8
    usage_today: int = 0
    last_reset: date = field(default_factory=date.today)

    def _maybe_reset(self) -> None:
        """Reset counter if we're on a new day."""
        today = date.today()
        if self.last_reset < today:
            logger.info(
                "Google Search quota reset. Previous usage: %d/%d",
                self.usage_today,
                self.daily_limit,
            )
            self.usage_today = 0
            self.last_reset = today

    def check_and_increment(self) -> None:
        """Check quota, increment counter, or raise QuotaExceededError."""
        self._maybe_reset()
        if self.usage_today >= self.daily_limit:
            raise QuotaExceededError(self.usage_today, self.daily_limit)
        self.usage_today += 1
        remaining = self.daily_limit - self.usage_today
        if self.is_near_limit():
            logger.warning(
                "Google Search quota warning: %d/%d queries used (%d remaining).",
                self.usage_today,
                self.daily_limit,
                remaining,
            )

    def is_near_limit(self) -> bool:
        return self.usage_today / self.daily_limit >= self.warn_threshold

    @property
    def remaining(self) -> int:
        self._maybe_reset()
        return max(0, self.daily_limit - self.usage_today)


@dataclass
class SearchResult:
    title: str
    link: str
    snippet: str


class GoogleSearchClient:
    """
    Async Google Custom Search client with quota protection.

    Args:
        api_key: GOOGLE_SEARCH_API_KEY env value
        cx: GOOGLE_SEARCH_ENGINE_ID (Custom Search Engine ID)
        daily_limit: Hard cap on queries per day (default 95 to be safe below 100)
        warn_threshold: Fraction of limit at which to emit a warning (default 0.8)
    """

    BASE_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(
        self,
        api_key: str,
        cx: str,
        daily_limit: int = 95,
        warn_threshold: float = 0.8,
    ) -> None:
        self.api_key = api_key
        self.cx = cx
        self.quota_manager = QuotaManager(
            daily_limit=daily_limit,
            warn_threshold=warn_threshold,
        )

    async def search(
        self,
        query: str,
        num: int = 5,
        **extra_params,
    ) -> list[SearchResult]:
        """
        Search using the Custom Search Engine.

        Args:
            query: Search query string
            num: Number of results (1-10, API limit)
            **extra_params: Extra parameters passed to the API (e.g. dateRestrict)

        Returns:
            List of SearchResult objects

        Raises:
            QuotaExceededError: If the daily limit has been reached
        """
        # Hard quota check BEFORE making any network call
        self.quota_manager.check_and_increment()

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": min(num, 10),
            **extra_params,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        items = data.get("items", [])
        return [
            SearchResult(
                title=item.get("title", ""),
                link=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in items
        ]

    @property
    def quota_status(self) -> dict:
        """Returns current quota status for logging/monitoring."""
        return {
            "usage_today": self.quota_manager.usage_today,
            "daily_limit": self.quota_manager.daily_limit,
            "remaining": self.quota_manager.remaining,
            "is_near_limit": self.quota_manager.is_near_limit(),
        }
