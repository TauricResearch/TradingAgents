"""
Dagster assets for TradingAgents news collection workflow.
Replaces the op-based approach with declarative assets.
"""

import asyncio
import logging
from datetime import date, datetime, timezone

import pandas as pd
from dagster import (
    AssetExecutionContext,
    DailyPartitionsDefinition,
    MetadataValue,
    asset,
)

from tradingagents.config import TradingAgentsConfig
from tradingagents.domains.news.news_repository import NewsArticle
from tradingagents.domains.news.news_service import (
    ArticleData,
    NewsService,
)

logger = logging.getLogger(__name__)

# Daily partitions for time-series data
DAILY_PARTITIONS = DailyPartitionsDefinition(start_date="2024-01-01")


@asset(partitions_def=DAILY_PARTITIONS)
def raw_google_news_feeds(context: AssetExecutionContext) -> pd.DataFrame:
    """
    Raw RSS feeds from Google News by ticker and date.

    This asset fetches raw article metadata from Google News RSS feeds
    for all tracked tickers on the given partition date.
    """
    partition_date = context.partition_key
    context.log.info(f"Fetching raw Google News feeds for {partition_date}")

    # Initialize NewsService
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)
    google_client = news_service.google_client

    # Get tracked tickers
    tickers = ["AAPL", "GOOGL", "MSFT", "TSLA"]  # TODO: Make configurable

    # Collect all articles
    all_articles = []

    for ticker in tickers:
        try:
            context.log.info(f"Fetching articles for {ticker}")
            google_articles = google_client.get_company_news(ticker)

            if not google_articles:
                context.log.warning(f"No articles found for {ticker}")
                continue

            # Convert to DataFrame format
            for article in google_articles:
                all_articles.append(
                    {
                        "ticker": ticker,
                        "title": article.title,
                        "url": article.link,
                        "source": article.source,
                        "published_date": article.published,
                        "summary": article.summary,
                        "fetch_date": partition_date,
                        "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

        except Exception as e:
            context.log.error(f"Error fetching articles for {ticker}: {e}")
            continue

    # Create DataFrame
    df = pd.DataFrame(all_articles)

    if df.empty:
        context.log.warning("No articles found for any tickers")
        return df

    # Log metadata
    context.add_output_metadata(
        {
            "total_articles": len(df),
            "tickers": df["ticker"].unique().tolist(),
            "sources": df["source"].unique().tolist(),
            "fetch_date": partition_date,
            "preview": MetadataValue.md(
                df.head().to_markdown() if not df.empty else "No data"
            ),
        }
    )

    context.log.info(f"Fetched {len(df)} raw articles for {partition_date}")
    return df


@asset(partitions_def=DAILY_PARTITIONS)
def scraped_article_content(
    context: AssetExecutionContext, raw_google_news_feeds: pd.DataFrame
) -> pd.DataFrame:
    """
    Full article content extracted via newspaper4k.

    This asset takes the raw RSS feeds and scrapes the full article content
    from each URL, handling paywalls and extraction failures gracefully.
    """
    partition_date = context.partition_key
    context.log.info(f"Scraping article content for {partition_date}")

    if raw_google_news_feeds.empty:
        context.log.warning("No raw articles to scrape")
        return pd.DataFrame()

    # Initialize scraper
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)
    scraper = news_service.article_scraper

    # Process each article
    scraped_articles = []

    for idx, row in raw_google_news_feeds.iterrows():
        url = str(row["url"])
        ticker = str(row["ticker"])
        title = str(row["title"])

        try:
            context.log.info(
                f"Scraping article {idx + 1}/{len(raw_google_news_feeds)}: {title[:50]}..."
            )

            # Scrape content
            scrape_result = scraper.scrape_article(url)

            if scrape_result.status in ["SUCCESS", "ARCHIVE_SUCCESS"]:
                content = scrape_result.content or ""
                author = scrape_result.author or ""
                publish_date = scrape_result.publish_date or ""
                scrape_status = scrape_result.status
            else:
                # Fallback to RSS data
                content = str(row.get("summary", ""))
                author = ""
                publish_date = str(row.get("published_date", ""))
                scrape_status = "rss_fallback"
                context.log.warning(
                    f"Scraping failed for {url}, using RSS summary: {scrape_result.status}"
                )

            # Create enhanced article record
            scraped_articles.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "url": url,
                    "source": str(row["source"]),
                    "published_date": publish_date,
                    "author": author,
                    "content": content,
                    "summary": str(row["summary"]),  # Keep original summary
                    "scrape_status": scrape_status,
                    "content_length": len(content) if content else 0,
                    "fetch_date": partition_date,
                    "scraped_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception as e:
            context.log.error(f"Error scraping article {url}: {e}")
            # Add failed record
            scraped_articles.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "url": url,
                    "source": str(row["source"]),
                    "published_date": str(row.get("published_date", "")),
                    "author": "",
                    "content": str(row.get("summary", "")),
                    "summary": str(row["summary"]),
                    "scrape_status": "error",
                    "content_length": 0,
                    "fetch_date": partition_date,
                    "scraped_timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }
            )

    # Create DataFrame
    df = pd.DataFrame(scraped_articles)

    # Log metadata
    successful_scrapes = df["scrape_status"].isin(["SUCCESS", "ARCHIVE_SUCCESS"]).sum()
    context.add_output_metadata(
        {
            "total_articles": len(df),
            "successful_scrapes": int(successful_scrapes),
            "failed_scrapes": int(len(df) - successful_scrapes),
            "avg_content_length": float(df["content_length"].mean())
            if len(df) > 0
            else 0,
            "scrape_statuses": df["scrape_status"].value_counts().to_dict(),
            "preview": MetadataValue.md(
                df.head().to_markdown() if not df.empty else "No data"
            ),
        }
    )

    context.log.info(
        f"Scraped content for {len(df)} articles ({int(successful_scrapes)} successful)"
    )
    return df


@asset(partitions_def=DAILY_PARTITIONS)
def article_sentiment_analysis(
    context: AssetExecutionContext, scraped_article_content: pd.DataFrame
) -> pd.DataFrame:
    """
    LLM sentiment analysis via OpenRouter.

    This asset analyzes the sentiment of each scraped article using
    OpenRouter's LLM models with keyword fallback.
    """
    partition_date = context.partition_key
    context.log.info(f"Analyzing sentiment for {partition_date}")

    if scraped_article_content.empty:
        context.log.warning("No scraped articles to analyze")
        return pd.DataFrame()

    # Initialize NewsService with OpenRouter
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)

    # Process sentiment for each article
    analyzed_articles = []

    for idx, row in scraped_article_content.iterrows():
        content = str(row["content"])
        title = str(row["title"])
        url = str(row["url"])
        ticker = str(row["ticker"])

        try:
            context.log.info(
                f"Analyzing sentiment for article {idx + 1}/{len(scraped_article_content)}: {title[:50]}..."
            )

            # Create ArticleData for sentiment analysis
            article_data = ArticleData(
                title=title,
                content=content,
                author=str(row["author"]),
                source=str(row["source"]),
                date=str(row["fetch_date"]),
                url=url,
            )

            # Calculate sentiment using NewsService
            sentiment_score = asyncio.run(
                news_service._calculate_sentiment_summary([article_data])
            )

            analyzed_articles.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "url": url,
                    "source": str(row["source"]),
                    "published_date": str(row["published_date"]),
                    "author": str(row["author"]),
                    "content": content,
                    "summary": str(row["summary"]),
                    "scrape_status": str(row["scrape_status"]),
                    "content_length": int(row["content_length"]),
                    "fetch_date": partition_date,
                    "sentiment_score": sentiment_score.score,
                    "sentiment_confidence": sentiment_score.confidence,
                    "sentiment_label": sentiment_score.label,
                    "analyzed_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception as e:
            context.log.error(f"Error analyzing sentiment for {url}: {e}")
            # Add record with neutral sentiment
            analyzed_articles.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "url": url,
                    "source": str(row["source"]),
                    "published_date": str(row["published_date"]),
                    "author": str(row["author"]),
                    "content": content,
                    "summary": str(row["summary"]),
                    "scrape_status": str(row["scrape_status"]),
                    "content_length": int(row["content_length"]),
                    "fetch_date": partition_date,
                    "sentiment_score": 0.0,
                    "sentiment_confidence": 0.0,
                    "sentiment_label": "neutral",
                    "analyzed_timestamp": datetime.now(timezone.utc).isoformat(),
                    "sentiment_error": str(e),
                }
            )

    # Create DataFrame
    df = pd.DataFrame(analyzed_articles)

    # Log metadata
    sentiment_counts = df["sentiment_label"].value_counts().to_dict()
    avg_confidence = float(df["sentiment_confidence"].mean()) if len(df) > 0 else 0.0

    context.add_output_metadata(
        {
            "total_articles": len(df),
            "sentiment_distribution": sentiment_counts,
            "avg_confidence": avg_confidence,
            "avg_sentiment_score": float(df["sentiment_score"].mean())
            if len(df) > 0
            else 0.0,
            "preview": MetadataValue.md(
                df.head().to_markdown() if not df.empty else "No data"
            ),
        }
    )

    context.log.info(f"Analyzed sentiment for {len(df)} articles")
    return df


@asset(partitions_def=DAILY_PARTITIONS)
def article_vector_embeddings(
    context: AssetExecutionContext, article_sentiment_analysis: pd.DataFrame
) -> pd.DataFrame:
    """
    Vector embeddings for RAG using OpenRouter.

    This asset generates 1536-dimension vector embeddings for each article
    to enable semantic search and RAG-powered agent context.
    """
    partition_date = context.partition_key
    context.log.info(f"Generating embeddings for {partition_date}")

    if article_sentiment_analysis.empty:
        context.log.warning("No analyzed articles to embed")
        return pd.DataFrame()

    # Initialize OpenRouter client for embeddings
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)

    if not news_service.openrouter_client:
        context.log.warning(
            "OpenRouter client not available, using placeholder embeddings"
        )
        # Create placeholder embeddings
        df = article_sentiment_analysis.copy()
        df["title_embedding"] = [[0.0] * 1536] * len(df)
        df["content_embedding"] = [[0.0] * 1536] * len(df)
        df["embedding_model"] = "placeholder"
        df["embedding_dimensions"] = 1536
        df["embedded_timestamp"] = datetime.now(timezone.utc).isoformat()

        context.add_output_metadata(
            {
                "total_articles": len(df),
                "embedding_model": "placeholder",
                "embedding_dimensions": 1536,
                "preview": MetadataValue.md(
                    df.head().to_markdown() if not df.empty else "No data"
                ),
            }
        )

        return df

    # Process embeddings for each article
    embedded_articles = []

    for idx, row in article_sentiment_analysis.iterrows():
        title = str(row["title"])
        content = str(row["content"])
        url = str(row["url"])
        ticker = str(row["ticker"])

        try:
            context.log.info(
                f"Generating embeddings for article {idx + 1}/{len(article_sentiment_analysis)}: {title[:50]}..."
            )

            # Generate real embeddings using NewsService
            try:
                title_embedding, content_embedding = (
                    news_service.generate_article_embeddings(title, content)
                )
            except Exception as e:
                context.log.warning(f"Failed to generate embeddings for {url}: {e}")
                # Fallback to placeholder embeddings
                title_embedding = [0.0] * 1536
                content_embedding = [0.0] * 1536

            embedded_articles.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "url": url,
                    "source": str(row["source"]),
                    "published_date": str(row["published_date"]),
                    "author": str(row["author"]),
                    "content": content,
                    "summary": str(row["summary"]),
                    "scrape_status": str(row["scrape_status"]),
                    "content_length": int(row["content_length"]),
                    "fetch_date": partition_date,
                    "sentiment_score": float(row["sentiment_score"]),
                    "sentiment_confidence": float(row["sentiment_confidence"]),
                    "sentiment_label": str(row["sentiment_label"]),
                    "title_embedding": title_embedding,
                    "content_embedding": content_embedding,
                    "embedding_model": config.news_embedding_llm,
                    "embedding_dimensions": 1536,
                    "embedded_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        except Exception as e:
            context.log.error(f"Error generating embeddings for {url}: {e}")
            # Add record with placeholder embeddings
            embedded_articles.append(
                {
                    "ticker": ticker,
                    "title": title,
                    "url": url,
                    "source": str(row["source"]),
                    "published_date": str(row["published_date"]),
                    "author": str(row["author"]),
                    "content": content,
                    "summary": str(row["summary"]),
                    "scrape_status": str(row["scrape_status"]),
                    "content_length": int(row["content_length"]),
                    "fetch_date": partition_date,
                    "sentiment_score": float(row["sentiment_score"]),
                    "sentiment_confidence": float(row["sentiment_confidence"]),
                    "sentiment_label": str(row["sentiment_label"]),
                    "title_embedding": [0.0] * 1536,
                    "content_embedding": [0.0] * 1536,
                    "embedding_model": "error-placeholder",
                    "embedding_dimensions": 1536,
                    "embedded_timestamp": datetime.now(timezone.utc).isoformat(),
                    "embedding_error": str(e),
                }
            )

    # Create DataFrame
    df = pd.DataFrame(embedded_articles)

    # Log metadata
    context.add_output_metadata(
        {
            "total_articles": len(df),
            "embedding_model": str(df["embedding_model"].iloc[0])
            if not df.empty
            else "none",
            "embedding_dimensions": 1536,
            "preview": MetadataValue.md(
                df.head().to_markdown() if not df.empty else "No data"
            ),
        }
    )

    context.log.info(f"Generated embeddings for {len(df)} articles")
    return df


@asset(partitions_def=DAILY_PARTITIONS)
def news_articles_table(
    context: AssetExecutionContext, article_vector_embeddings: pd.DataFrame
) -> None:
    """
    Final storage in PostgreSQL with TimescaleDB hypertable.

    This asset stores the fully processed articles with embeddings
    in the PostgreSQL database for use by trading agents.
    """
    partition_date = context.partition_key
    context.log.info(f"Storing articles in database for {partition_date}")

    if article_vector_embeddings.empty:
        context.log.warning("No embedded articles to store")
        return

    # Initialize NewsService and repository
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)
    repository = news_service.repository

    if not repository:
        context.log.error("No repository available for storage")
        return

    # Convert DataFrame rows to NewsArticle objects
    stored_count = 0
    failed_count = 0

    for _idx, row in article_vector_embeddings.iterrows():
        try:
            # Create NewsArticle object
            news_article = NewsArticle(
                headline=str(row["title"]),
                url=str(row["url"]),
                source=str(row["source"]),
                published_date=date.fromisoformat(str(row["published_date"])[:10])
                if str(row["published_date"])
                else date.today(),
                summary=str(row["content"]),  # Use full content as summary
                author=str(row["author"]),
                # TODO: Add embedding fields to NewsArticle model
            )

            # Store in database (async operation)
            asyncio.run(repository.upsert_batch([news_article], str(row["ticker"])))
            stored_count += 1

        except Exception as e:
            context.log.error(f"Error storing article {row['url']}: {e}")
            failed_count += 1

    # Log metadata
    context.add_output_metadata(
        {
            "total_articles": len(article_vector_embeddings),
            "stored_successfully": stored_count,
            "failed_to_store": failed_count,
            "storage_rate": stored_count / len(article_vector_embeddings)
            if len(article_vector_embeddings) > 0
            else 0,
            "tickers": article_vector_embeddings["ticker"].unique().tolist(),
        }
    )

    context.log.info(
        f"Stored {stored_count} articles in database ({failed_count} failed)"
    )


@asset(partitions_def=DAILY_PARTITIONS)
def daily_sentiment_summary(
    context: AssetExecutionContext, _news_articles_table
) -> pd.DataFrame:
    """
    Aggregated sentiment by ticker/date for trading agents.

    This asset creates daily sentiment summaries that can be used
    by trading agents for market context and decision making.
    """
    partition_date = context.partition_key
    context.log.info(f"Creating daily sentiment summary for {partition_date}")

    # Initialize NewsService and repository
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)
    repository = news_service.repository

    if not repository:
        context.log.error("No repository available for sentiment summary")
        return pd.DataFrame()

    # Get tracked tickers
    tickers = ["AAPL", "GOOGL", "MSFT", "TSLA"]  # TODO: Make configurable

    summary_data = []

    try:
        # Query articles for each ticker on this date
        for ticker in tickers:
            try:
                # Convert partition date to date object
                start_date = date.fromisoformat(partition_date)
                end_date = start_date  # Same day for daily summary

                # Get articles from repository (following test pattern)
                news_articles = asyncio.run(
                    repository.list_by_date_range(
                        symbol=ticker,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )

                if not news_articles:
                    context.log.debug(
                        f"No articles found for {ticker} on {partition_date}"
                    )
                    continue

                # Convert NewsArticle objects to ArticleData objects (following test pattern)
                articles = []
                for article in news_articles:
                    articles.append(
                        ArticleData(
                            title=article.headline,
                            content=article.summary or "",
                            author=article.author or "",
                            source=article.source,
                            date=article.published_date.isoformat(),
                            url=article.url,
                        )
                    )

                # Calculate sentiment summary using NewsService (following test pattern)
                sentiment_summary = asyncio.run(
                    news_service._calculate_sentiment_summary(articles)
                )

                # Create summary record
                summary_data.append(
                    {
                        "date": partition_date,
                        "ticker": ticker,
                        "total_articles": len(articles),
                        "positive_articles": sum(
                            1
                            for a in articles
                            if hasattr(a, "sentiment")
                            and a.sentiment
                            and a.sentiment.label == "positive"
                        ),
                        "negative_articles": sum(
                            1
                            for a in articles
                            if hasattr(a, "sentiment")
                            and a.sentiment
                            and a.sentiment.label == "negative"
                        ),
                        "neutral_articles": sum(
                            1
                            for a in articles
                            if hasattr(a, "sentiment")
                            and a.sentiment
                            and a.sentiment.label == "neutral"
                        ),
                        "avg_sentiment_score": sentiment_summary.score,
                        "avg_confidence": sentiment_summary.confidence,
                        "dominant_sentiment": sentiment_summary.label,
                    }
                )

                context.log.debug(
                    f"Created sentiment summary for {ticker}: {len(articles)} articles"
                )

            except Exception as e:
                context.log.error(f"Error creating sentiment summary for {ticker}: {e}")
                continue

    except Exception as e:
        context.log.error(f"Error in daily sentiment summary: {e}")

    # Create DataFrame with proper columns
    summary_df = pd.DataFrame(summary_data)

    context.add_output_metadata(
        {
            "summary_date": partition_date,
            "total_tickers": len(summary_df),
            "total_articles": summary_df["total_articles"].sum()
            if not summary_df.empty
            else 0,
            "preview": MetadataValue.md(summary_df.head().to_markdown())
            if not summary_df.empty
            else "No data",
        }
    )

    context.log.info(f"Created sentiment summary for {len(summary_df)} tickers")
    return summary_df


@asset(partitions_def=DAILY_PARTITIONS)
def trending_topics_analysis(
    context: AssetExecutionContext, _news_articles_table
) -> pd.DataFrame:
    """
    Extracted trending topics for market context.

    This asset analyzes article titles and content to identify
    trending topics that may impact market conditions.
    """
    partition_date = context.partition_key
    context.log.info(f"Analyzing trending topics for {partition_date}")

    # Initialize NewsService and repository
    config = TradingAgentsConfig.from_env()
    news_service = NewsService.build(None, config)
    repository = news_service.repository

    if not repository:
        context.log.error("No repository available for trending topics analysis")
        return pd.DataFrame()

    # Get tracked tickers
    tickers = ["AAPL", "GOOGL", "MSFT", "TSLA"]  # TODO: Make configurable

    topics_data = []

    try:
        # Collect all articles for topic analysis
        all_articles = []

        for ticker in tickers:
            try:
                # Convert partition date to date object
                start_date = date.fromisoformat(partition_date)
                end_date = start_date  # Same day for daily analysis

                # Get articles from repository
                news_articles = asyncio.run(
                    repository.list_by_date_range(
                        symbol=ticker,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )

                if not news_articles:
                    continue

                # Convert NewsArticle objects to ArticleData objects
                for article in news_articles:
                    all_articles.append(
                        ArticleData(
                            title=article.headline,
                            content=article.summary or "",
                            author=article.author or "",
                            source=article.source,
                            date=article.published_date.isoformat(),
                            url=article.url,
                        )
                    )

            except Exception as e:
                context.log.error(f"Error fetching articles for {ticker}: {e}")
                continue

        if all_articles:
            # Extract trending topics using NewsService (following test pattern)
            trending_topics = news_service._extract_trending_topics(all_articles)

            # Create topic records with frequency analysis
            for topic in trending_topics:
                # Count articles containing this topic
                topic_articles = [
                    article
                    for article in all_articles
                    if topic.lower() in article.title.lower()
                    or topic.lower() in article.content.lower()
                ]

                # Calculate average sentiment for articles with this topic
                if topic_articles:
                    sentiment_summary = asyncio.run(
                        news_service._calculate_sentiment_summary(topic_articles)
                    )
                    avg_sentiment = sentiment_summary.score
                else:
                    avg_sentiment = 0.0

                # Get related tickers for this topic
                related_tickers = []
                for ticker in tickers:
                    ticker_articles = [
                        article
                        for article in topic_articles
                        if ticker.lower() in article.title.lower()
                        or ticker.lower() in article.content.lower()
                    ]
                    if ticker_articles:
                        related_tickers.append(ticker)

                topics_data.append(
                    {
                        "date": partition_date,
                        "topic": topic,
                        "frequency": len(topic_articles),
                        "sentiment_score": avg_sentiment,
                        "related_tickers": ",".join(related_tickers)
                        if related_tickers
                        else "",
                        "sample_articles": ",".join(
                            [article.url for article in topic_articles[:3]]
                        ),
                    }
                )

        context.log.debug(
            f"Identified {len(trending_topics)} trending topics from {len(all_articles)} articles"
        )

    except Exception as e:
        context.log.error(f"Error in trending topics analysis: {e}")

    # Create DataFrame
    topics_df = pd.DataFrame(topics_data)

    context.add_output_metadata(
        {
            "analysis_date": partition_date,
            "total_topics": len(topics_df),
            "preview": MetadataValue.md(topics_df.head().to_markdown())
            if not topics_df.empty
            else "No data",
        }
    )

    context.log.info(f"Identified {len(topics_df)} trending topics")
    return topics_df
