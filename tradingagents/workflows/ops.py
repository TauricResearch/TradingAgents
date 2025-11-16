"""
Dagster operations for TradingAgents news collection workflow.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from dagster import (
    AssetMaterialization,
    OpExecutionContext,
    op,
)

from tradingagents.config import TradingAgentsConfig
from tradingagents.domains.news.news_service import NewsService

logger = logging.getLogger(__name__)


@op
def get_tracked_tickers(context: OpExecutionContext) -> list[str]:
    """
    Get list of tickers to process from configuration.

    Returns:
        List of ticker symbols to process
    """
    try:
        # Default ticker list - can be made configurable
        tickers = ["AAPL", "GOOGL", "MSFT", "TSLA"]

        context.log.info(f"Processing {len(tickers)} tickers: {tickers}")

        return tickers

    except Exception as e:
        context.log.error(f"Error getting tracked tickers: {e}")
        raise


@op
def fetch_google_news_articles(
    context: OpExecutionContext, ticker: str
) -> dict[str, Any]:
    """
    Fetch news articles for a single ticker from Google News.

    Args:
        context: Dagster operation context
        ticker: Stock ticker symbol

    Returns:
        Dictionary with ticker and article list
    """
    try:
        context.log.info(f"Fetching articles for ticker: {ticker}")

        # Initialize NewsService
        config = TradingAgentsConfig.from_env()
        news_service = NewsService.build(None, config)  # Will be replaced with resource

        # Get Google News articles
        google_client = news_service.google_client
        google_articles = google_client.get_company_news(ticker)

        if not google_articles:
            context.log.warning(f"No articles found for {ticker}")
            return {
                "ticker": ticker,
                "articles": [],
                "status": "no_articles",
                "total_found": 0,
            }

        # Convert to simple dict format
        article_list = []
        for i, article in enumerate(google_articles):
            article_list.append(
                {
                    "index": i,
                    "ticker": ticker,
                    "title": article.title,
                    "url": article.link,
                    "source": article.source,
                    "published_date": article.published,
                    "summary": article.summary,
                }
            )

        context.log.info(f"Found {len(article_list)} articles for {ticker}")

        # Log asset materialization
        context.log_event(
            AssetMaterialization(
                asset_key=f"google_news_articles_{ticker}",
                description=f"Fetched {len(article_list)} articles for {ticker}",
                metadata={
                    "ticker": ticker,
                    "total_articles": len(article_list),
                    "sources": {article["source"] for article in article_list},
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        )

        return {
            "ticker": ticker,
            "articles": article_list,
            "status": "success",
            "total_found": len(article_list),
        }

    except Exception as e:
        context.log.error(f"Error fetching articles for {ticker}: {e}")
        return {
            "ticker": ticker,
            "articles": [],
            "status": "error",
            "error": str(e),
            "total_found": 0,
        }


@op
def fetch_and_process_article(
    context: OpExecutionContext, article_data: dict[str, Any]
) -> dict[str, Any]:
    """
    Complete processing pipeline for a single article:
    - Scrape content
    - LLM sentiment analysis
    - Vector embeddings
    - Store in database

    Args:
        context: Dagster operation context
        article_data: Article information including URL

    Returns:
        Processed article data with all processing results
    """
    try:
        url = article_data["url"]
        title = article_data["title"]
        ticker = article_data["ticker"]

        context.log.info(f"Processing article: {title[:50]}...")

        # Initialize NewsService
        config = TradingAgentsConfig.from_env()
        news_service = NewsService.build(None, config)
        scraper = news_service.article_scraper

        # Step 1: Scrape content
        context.log.info("Step 1: Scraping content...")
        scrape_result = scraper.scrape_article(url)

        if scrape_result.status in ["SUCCESS", "ARCHIVE_SUCCESS"]:
            content = scrape_result.content
            author = scrape_result.author
            publish_date = scrape_result.publish_date
            context.log.info(f"Successfully scraped {len(content)} characters")
        else:
            content = article_data.get("summary", "")
            author = ""
            publish_date = article_data.get("published_date", "")
            context.log.warning(
                f"Scraping failed, using summary: {scrape_result.status}"
            )

        # Step 2: LLM Sentiment Analysis
        context.log.info("Step 2: Analyzing sentiment...")
        sentiment_result = {
            "sentiment": "positive",  # TODO: Implement OpenRouter LLM
            "confidence": 0.75,  # TODO: Implement OpenRouter LLM
            "reasoning": "LLM analysis placeholder",
        }
        context.log.info(
            f"Sentiment: {sentiment_result['sentiment']} (confidence: {sentiment_result['confidence']})"
        )

        # Step 3: Vector Embeddings
        context.log.info("Step 3: Generating embeddings...")
        vector_result = {
            "title_embedding": [0.0] * 1536,  # TODO: Implement OpenAI embeddings
            "content_embedding": [0.0] * 1536,  # TODO: Implement OpenAI embeddings
            "embedding_model": "text-embedding-3-small",
            "embedding_dimensions": 1536,
        }
        context.log.info(
            f"Generated {len(vector_result['title_embedding'])}-dim embeddings"
        )

        # Step 4: Store in database
        context.log.info("Step 4: Storing in database...")

        async def store_article():
            from datetime import date

            from tradingagents.domains.news.news_repository import NewsArticle

            news_article = NewsArticle(
                headline=title,
                url=url,
                source=article_data["source"],
                published_date=date.fromisoformat(
                    publish_date[:10] if publish_date else "2025-01-01"
                ),
                summary=content,
                author=author,
            )

            repository = news_service.repository
            await repository.upsert_batch([news_article], ticker)

        try:
            asyncio.run(store_article())
            storage_status = "success"
            context.log.info("Successfully stored article")
        except Exception as e:
            storage_status = "error"
            context.log.error(f"Error storing article: {e}")

        # Return complete processed article
        processed_article = {
            **article_data,
            "content": content,
            "author": author,
            "publish_date": publish_date,
            "scrape_status": scrape_result.status,
            "sentiment": sentiment_result,
            "vectors": vector_result,
            "storage_status": storage_status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Log asset materialization
        context.log_event(
            AssetMaterialization(
                asset_key=f"processed_article_{ticker}_{article_data['index']}",
                description=f"Completely processed article: {title[:50]}...",
                metadata={
                    "ticker": ticker,
                    "url": url,
                    "scrape_status": scrape_result.status,
                    "sentiment": sentiment_result["sentiment"],
                    "content_length": len(content),
                    "storage_status": storage_status,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        )

        return processed_article

    except Exception as e:
        context.log.error(f"Error processing article {article_data['url']}: {e}")
        return {
            **article_data,
            "content": "",
            "scrape_status": "error",
            "sentiment": {
                "sentiment": "neutral",
                "confidence": 0.0,
                "reasoning": f"Error: {str(e)}",
            },
            "vectors": {
                "title_embedding": [],
                "content_embedding": [],
                "error": str(e),
            },
            "storage_status": "error",
            "error": str(e),
        }


@op
def collect_ticker_results(
    context: OpExecutionContext, processed_articles: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Collect and summarize results for a ticker.

    Args:
        context: Dagster operation context
        processed_articles: List of fully processed articles

    Returns:
        Summary results for the ticker
    """
    try:
        if not processed_articles:
            return {"status": "no_articles", "total_processed": 0}

        ticker = processed_articles[0]["ticker"]

        # Calculate statistics
        total_processed = len(processed_articles)
        successful_scrapes = sum(
            1
            for a in processed_articles
            if a.get("scrape_status") in ["SUCCESS", "ARCHIVE_SUCCESS"]
        )
        successful_storage = sum(
            1 for a in processed_articles if a.get("storage_status") == "success"
        )

        # Sentiment analysis
        sentiments = [
            a.get("sentiment", {}).get("sentiment", "neutral")
            for a in processed_articles
        ]
        sentiment_counts = {
            "positive": sentiments.count("positive"),
            "negative": sentiments.count("negative"),
            "neutral": sentiments.count("neutral"),
        }

        results = {
            "ticker": ticker,
            "status": "completed",
            "total_processed": total_processed,
            "successful_scrapes": successful_scrapes,
            "successful_storage": successful_storage,
            "sentiment_summary": sentiment_counts,
            "completion_time": datetime.now(timezone.utc).isoformat(),
        }

        context.log.info(
            f"Completed {ticker}: {total_processed} articles, {successful_storage} stored"
        )

        # Log asset materialization
        context.log_event(
            AssetMaterialization(
                asset_key=f"ticker_results_{ticker}",
                description=f"Completed news processing for {ticker}",
                metadata=results,
            )
        )

        return results

    except Exception as e:
        context.log.error(f"Error collecting ticker results: {e}")
        return {"status": "error", "error": str(e)}


@op
def collect_all_results(
    context: OpExecutionContext, ticker_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Collect and summarize results for all tickers.

    Args:
        context: Dagster operation context
        ticker_results: List of ticker result summaries

    Returns:
        Overall summary results
    """
    try:
        if not ticker_results:
            return {"status": "no_results", "total_tickers": 0}

        # Calculate overall statistics
        total_tickers = len(ticker_results)
        successful_tickers = sum(
            1 for r in ticker_results if r.get("status") == "completed"
        )
        total_articles = sum(r.get("total_processed", 0) for r in ticker_results)
        total_stored = sum(r.get("successful_storage", 0) for r in ticker_results)

        # Aggregate sentiment data
        overall_sentiment = {
            "positive": sum(
                r.get("sentiment_summary", {}).get("positive", 0)
                for r in ticker_results
            ),
            "negative": sum(
                r.get("sentiment_summary", {}).get("negative", 0)
                for r in ticker_results
            ),
            "neutral": sum(
                r.get("sentiment_summary", {}).get("neutral", 0) for r in ticker_results
            ),
        }

        results = {
            "status": "completed",
            "total_tickers": total_tickers,
            "successful_tickers": successful_tickers,
            "total_articles": total_articles,
            "total_stored": total_stored,
            "overall_sentiment": overall_sentiment,
            "completion_time": datetime.now(timezone.utc).isoformat(),
            "ticker_results": ticker_results,
        }

        context.log.info(
            f"Completed all tickers: {total_tickers} tickers, {total_articles} articles, {total_stored} stored"
        )

        # Log asset materialization
        context.log_event(
            AssetMaterialization(
                asset_key="daily_news_collection_summary",
                description="Completed daily news collection for all tickers",
                metadata=results,
            )
        )

        return results

    except Exception as e:
        context.log.error(f"Error collecting all results: {e}")
        return {"status": "error", "error": str(e)}
