from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class DiscoveryStatus(Enum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Sector(Enum):
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    ENERGY = "energy"
    CONSUMER_GOODS = "consumer_goods"
    INDUSTRIALS = "industrials"
    OTHER = "other"


class EventCategory(Enum):
    EARNINGS = "earnings"
    MERGER_ACQUISITION = "merger_acquisition"
    REGULATORY = "regulatory"
    PRODUCT_LAUNCH = "product_launch"
    EXECUTIVE_CHANGE = "executive_change"
    OTHER = "other"


@dataclass
class NewsArticle:
    title: str
    source: str
    url: str
    published_at: datetime
    content_snippet: str
    ticker_mentions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "content_snippet": self.content_snippet,
            "ticker_mentions": self.ticker_mentions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NewsArticle":
        return cls(
            title=data["title"],
            source=data["source"],
            url=data["url"],
            published_at=datetime.fromisoformat(data["published_at"]),
            content_snippet=data["content_snippet"],
            ticker_mentions=data["ticker_mentions"],
        )


@dataclass
class TrendingStock:
    ticker: str
    company_name: str
    score: float
    mention_count: int
    sentiment: float
    sector: Sector
    event_type: EventCategory
    news_summary: str
    source_articles: List[NewsArticle]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "score": self.score,
            "mention_count": self.mention_count,
            "sentiment": self.sentiment,
            "sector": self.sector.value,
            "event_type": self.event_type.value,
            "news_summary": self.news_summary,
            "source_articles": [article.to_dict() for article in self.source_articles],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrendingStock":
        return cls(
            ticker=data["ticker"],
            company_name=data["company_name"],
            score=data["score"],
            mention_count=data["mention_count"],
            sentiment=data["sentiment"],
            sector=Sector(data["sector"]),
            event_type=EventCategory(data["event_type"]),
            news_summary=data["news_summary"],
            source_articles=[
                NewsArticle.from_dict(article) for article in data["source_articles"]
            ],
        )


@dataclass
class DiscoveryRequest:
    lookback_period: str
    sector_filter: Optional[List[Sector]] = None
    event_filter: Optional[List[EventCategory]] = None
    max_results: int = 20
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lookback_period": self.lookback_period,
            "sector_filter": (
                [s.value for s in self.sector_filter] if self.sector_filter else None
            ),
            "event_filter": (
                [e.value for e in self.event_filter] if self.event_filter else None
            ),
            "max_results": self.max_results,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryRequest":
        return cls(
            lookback_period=data["lookback_period"],
            sector_filter=(
                [Sector(s) for s in data["sector_filter"]]
                if data.get("sector_filter")
                else None
            ),
            event_filter=(
                [EventCategory(e) for e in data["event_filter"]]
                if data.get("event_filter")
                else None
            ),
            max_results=data.get("max_results", 20),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class DiscoveryResult:
    request: DiscoveryRequest
    trending_stocks: List[TrendingStock]
    status: DiscoveryStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "trending_stocks": [stock.to_dict() for stock in self.trending_stocks],
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveryResult":
        return cls(
            request=DiscoveryRequest.from_dict(data["request"]),
            trending_stocks=[
                TrendingStock.from_dict(stock) for stock in data["trending_stocks"]
            ],
            status=DiscoveryStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            error_message=data.get("error_message"),
        )
