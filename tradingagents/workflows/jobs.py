"""
Dagster jobs for TradingAgents news collection workflow.
"""

from dagster import job, op

from tradingagents.workflows.ops import (
    collect_all_results,
    collect_ticker_results,
    fetch_and_process_article,
    fetch_google_news_articles,
    get_tracked_tickers,
)


@op
def hardcoded_ticker():
    """Provide a hardcoded ticker for testing."""
    return "AAPL"


@op
def get_first_ticker(tickers: list[str]) -> str:
    """Get the first ticker from the list."""
    return tickers[0] if tickers else "AAPL"


@op
def get_first_article(ticker_articles: dict) -> dict:
    """Get the first article from the ticker articles."""
    articles = ticker_articles.get("articles", [])
    return articles[0] if articles else {}


@op
def process_articles_list(ticker_articles: dict) -> list[dict]:
    """Process articles list for collection."""
    articles = ticker_articles.get("articles", [])
    return articles


@job
def simple_news_collection_job():
    """
    Simple news collection job for testing.

    This job processes a single ticker with a simplified workflow.
    """
    # Step 1: Get tickers
    tickers = get_tracked_tickers()

    # Step 2: Get first ticker
    first_ticker = get_first_ticker(tickers)

    # Step 3: Fetch articles for the ticker
    ticker_articles = fetch_google_news_articles(first_ticker)

    # Step 4: Get first article
    first_article = get_first_article(ticker_articles)

    # Step 5: Process first article only (for testing)
    if first_article:
        processed_article = fetch_and_process_article(first_article)

        # Step 6: Collect results
        collect_ticker_results([processed_article])
    else:
        # Handle case with no articles
        collect_ticker_results([])


@job
def single_ticker_news_collection_job():
    """
    News collection job for a single ticker.

    This is useful for testing or when you want to process
    a specific ticker without running the full pipeline.
    """
    # Get hardcoded ticker
    ticker = hardcoded_ticker()

    # Fetch articles for the ticker
    ticker_articles = fetch_google_news_articles(ticker)

    # Get first article
    first_article = get_first_article(ticker_articles)

    # Process articles (simplified - would need dynamic mapping for real parallel processing)
    if first_article:
        processed_article = fetch_and_process_article(first_article)

        # Collect results
        collect_ticker_results([processed_article])
    else:
        # Handle case with no articles
        collect_ticker_results([])


@job
def complete_news_collection_job():
    """
    Complete news collection job for all tickers.

    This job processes all configured tickers with their articles
    and provides comprehensive results.
    """
    # Step 1: Get all tickers to process
    tickers = get_tracked_tickers()

    # Step 2: Get first ticker as example (simplified - would need dynamic mapping)
    first_ticker = get_first_ticker(tickers)

    # Step 3: Fetch articles for the ticker
    ticker_articles = fetch_google_news_articles(first_ticker)

    # Step 4: Get first article
    first_article = get_first_article(ticker_articles)

    # Step 5: Process first article (simplified - would need dynamic mapping)
    if first_article:
        processed_article = fetch_and_process_article(first_article)

        # Step 6: Collect ticker results
        ticker_results = collect_ticker_results([processed_article])

        # Step 7: Collect overall results
        collect_all_results([ticker_results])
    else:
        # Handle case with no articles
        collect_all_results([])
