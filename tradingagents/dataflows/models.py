from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class NewsArticle:
    title: str
    source: str
    url: str
    published_at: datetime
    content_snippet: str
    ticker_mentions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "content_snippet": self.content_snippet,
            "ticker_mentions": self.ticker_mentions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsArticle":
        return cls(
            title=data["title"],
            source=data["source"],
            url=data["url"],
            published_at=datetime.fromisoformat(data["published_at"]),
            content_snippet=data["content_snippet"],
            ticker_mentions=data["ticker_mentions"],
        )
