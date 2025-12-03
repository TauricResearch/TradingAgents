import math
from collections import defaultdict
from datetime import datetime
from typing import List, Dict

from tradingagents.agents.discovery.models import (
    TrendingStock,
    NewsArticle,
    Sector,
    EventCategory,
)
from tradingagents.agents.discovery.entity_extractor import EntityMention
from tradingagents.dataflows.trending.stock_resolver import resolve_ticker
from tradingagents.dataflows.trending.sector_classifier import classify_sector


DEFAULT_DECAY_RATE = 0.1
DEFAULT_MAX_RESULTS = 20
DEFAULT_MIN_MENTIONS = 2


def _aggregate_sentiment(mentions: List[EntityMention]) -> float:
    if not mentions:
        return 0.0

    total_weighted_sentiment = 0.0
    total_confidence = 0.0

    for mention in mentions:
        total_weighted_sentiment += mention.sentiment * mention.confidence
        total_confidence += mention.confidence

    if total_confidence == 0:
        return 0.0

    return total_weighted_sentiment / total_confidence


def _calculate_recency_weight(
    articles: List[NewsArticle],
    article_ids: set,
    decay_rate: float,
) -> float:
    if not articles:
        return 1.0

    now = datetime.now()
    weights = []

    for i, article in enumerate(articles):
        article_id = f"article_{i}"
        if article_id in article_ids:
            hours_old = (now - article.published_at).total_seconds() / 3600.0
            weight = math.exp(-decay_rate * hours_old)
            weights.append(weight)

    if not weights:
        return 1.0

    return sum(weights) / len(weights)


def _get_most_common_event_type(mentions: List[EntityMention]) -> EventCategory:
    if not mentions:
        return EventCategory.OTHER

    event_counts: Dict[EventCategory, int] = defaultdict(int)
    for mention in mentions:
        event_counts[mention.event_type] += 1

    return max(event_counts.keys(), key=lambda e: event_counts[e])


def _build_news_summary(mentions: List[EntityMention]) -> str:
    if not mentions:
        return ""

    snippets = [m.context_snippet for m in mentions[:3]]
    return " ".join(snippets)


def calculate_trending_scores(
    mentions: List[EntityMention],
    articles: List[NewsArticle],
    decay_rate: float = DEFAULT_DECAY_RATE,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_mentions: int = DEFAULT_MIN_MENTIONS,
) -> List[TrendingStock]:
    if not mentions:
        return []

    ticker_mentions: Dict[str, List[EntityMention]] = defaultdict(list)
    ticker_company_names: Dict[str, str] = {}

    for mention in mentions:
        ticker = resolve_ticker(mention.company_name)
        if ticker:
            ticker_mentions[ticker].append(mention)
            if ticker not in ticker_company_names:
                ticker_company_names[ticker] = mention.company_name

    article_index: Dict[str, int] = {}
    for i, article in enumerate(articles):
        article_index[f"article_{i}"] = i

    trending_stocks: List[TrendingStock] = []

    for ticker, ticker_mention_list in ticker_mentions.items():
        article_ids = {m.article_id for m in ticker_mention_list}
        frequency = len(article_ids)

        if frequency < min_mentions:
            continue

        sentiment = _aggregate_sentiment(ticker_mention_list)
        sentiment_factor = 1 + abs(sentiment)

        recency_weight = _calculate_recency_weight(articles, article_ids, decay_rate)

        score = frequency * sentiment_factor * recency_weight

        sector_str = classify_sector(ticker)
        try:
            sector = Sector(sector_str)
        except ValueError:
            sector = Sector.OTHER

        event_type = _get_most_common_event_type(ticker_mention_list)

        source_article_list: List[NewsArticle] = []
        for article_id in article_ids:
            idx = article_index.get(article_id)
            if idx is not None and idx < len(articles):
                source_article_list.append(articles[idx])

        news_summary = _build_news_summary(ticker_mention_list)

        trending_stock = TrendingStock(
            ticker=ticker,
            company_name=ticker_company_names.get(ticker, ticker),
            score=score,
            mention_count=frequency,
            sentiment=sentiment,
            sector=sector,
            event_type=event_type,
            news_summary=news_summary,
            source_articles=source_article_list,
        )
        trending_stocks.append(trending_stock)

    trending_stocks.sort(key=lambda s: s.score, reverse=True)

    return trending_stocks[:max_results]
