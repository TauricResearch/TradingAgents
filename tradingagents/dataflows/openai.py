import os
import warnings

from openai import OpenAI

from tradingagents.config import config
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)

# Suppress Pydantic serialization warnings from OpenAI web search
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.main")

_OPENAI_CLIENT = None


def _get_openai_client() -> OpenAI:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAI(api_key=config.validate_key("openai_api_key", "OpenAI"))
    return _OPENAI_CLIENT


def get_stock_news_openai(query=None, ticker=None, start_date=None, end_date=None):
    """Get stock news from OpenAI web search.

    Args:
        query: Search query or ticker symbol
        ticker: Ticker symbol (alias for query)
        start_date: Start date yyyy-mm-dd
        end_date: End date yyyy-mm-dd
    """
    # Handle parameter aliasing
    if query:
        search_query = query
    elif ticker:
        # Format ticker as a natural language query for better results
        search_query = f"latest news and market analysis on {ticker} stock"
    else:
        raise ValueError("Must provide either 'query' or 'ticker' parameter")

    client = _get_openai_client()

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=f"Search Social Media and news sources for {search_query} from {start_date} to {end_date}. Make sure you only get the data posted during that period.",
        )
        return response.output_text
    except Exception as e:
        return f"Error fetching news from OpenAI: {str(e)}"


def get_global_news_openai(date, look_back_days=7, limit=5):
    client = _get_openai_client()

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=f"Search global or macroeconomics news from {look_back_days} days before {date} that would be informative for trading purposes. Make sure you only get the data posted during that period. Limit the results to {limit} articles.",
        )
        return response.output_text
    except Exception as e:
        return f"Error fetching global news from OpenAI: {str(e)}"


def get_fundamentals_openai(ticker, curr_date):
    client = _get_openai_client()

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=f"Search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc",
        )
        return response.output_text
    except Exception as e:
        return f"Error fetching fundamentals from OpenAI: {str(e)}"


def get_batch_stock_news_openai(
    tickers: list[str],
    start_date: str,
    end_date: str,
    batch_size: int = 10,
) -> dict[str, str]:
    """Fetch news for multiple tickers in batched OpenAI calls.

    Instead of making one API call per ticker, this batches tickers together
    to significantly reduce API costs (~90% savings for 50 tickers).

    Args:
        tickers: List of ticker symbols
        start_date: Start date yyyy-mm-dd
        end_date: End date yyyy-mm-dd
        batch_size: Max tickers per API call (default 10 to avoid output truncation)

    Returns:
        dict: {ticker: "news summary text", ...}
    """
    from typing import List

    from pydantic import BaseModel

    # Define structured output schema (matching working snippet)
    class TickerNews(BaseModel):
        ticker: str
        news_summary: str
        date: str

    class PortfolioUpdate(BaseModel):
        items: List[TickerNews]

    client = _get_openai_client()
    results = {}
    total_batches = (len(tickers) + batch_size - 1) // batch_size

    # Process in batches to avoid output token limits
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"📰 OpenAI news batch {batch_num}/{total_batches}: {batch}")

        # Request comprehensive news summaries for better ranker LLM context
        prompt = f"""Find the most significant news stories for {batch} from {start_date} to {end_date}.

Focus on business catalysts: earnings, product launches, partnerships, analyst changes, regulatory news.

For each ticker, provide a comprehensive summary (5-8 sentences) covering:
- What happened (the catalyst/event)
- Key numbers/metrics if applicable (revenue, earnings, deal size, etc.)
- Why it matters for investors
- Market reaction or implications
- Any forward-looking statements or guidance"""

        try:
            completion = client.responses.parse(
                model="gpt-5-nano",
                tools=[{"type": "web_search"}],
                input=prompt,
                text_format=PortfolioUpdate,
            )

            # Extract structured output
            if completion.output_parsed:
                for item in completion.output_parsed.items:
                    results[item.ticker.upper()] = item.news_summary
            else:
                # Fallback if parsing failed
                logger.warning(f"Structured parsing returned None for batch: {batch}")
                for ticker in batch:
                    results[ticker.upper()] = ""

        except Exception as e:
            logger.error(f"Error fetching batch news for {batch}: {e}")
            # On error, set empty string for all tickers in batch
            for ticker in batch:
                results[ticker.upper()] = ""

    return results


def get_batch_stock_news_google(
    tickers: list[str],
    start_date: str,
    end_date: str,
    batch_size: int = 10,
    model: str = "gemini-3-flash-preview",
) -> dict[str, str]:
    """Fetch news for multiple tickers using Google Search (Gemini).

    Two-step approach:
    1. Use Gemini with google_search tool to gather grounded news
    2. Use structured output to format into JSON

    Args:
        tickers: List of ticker symbols
        start_date: Start date yyyy-mm-dd
        end_date: End date yyyy-mm-dd
        batch_size: Max tickers per API call (default 10)
        model: Gemini model name (default: gemini-3-flash-preview)

    Returns:
        dict: {ticker: "news summary text", ...}
    """
    # Create LLMs with specified model (don't use cached version)
    from typing import List

    from langchain_google_genai import ChatGoogleGenerativeAI
    from pydantic import BaseModel

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY not set in environment")

    # Define schema for structured output
    class TickerNews(BaseModel):
        ticker: str
        news_summary: str
        date: str

    class PortfolioUpdate(BaseModel):
        items: List[TickerNews]

    # Searcher: Enable web search tool
    search_llm = ChatGoogleGenerativeAI(
        model=model, api_key=google_api_key, temperature=1.0
    ).bind_tools([{"google_search": {}}])

    # Formatter: Native JSON mode
    structured_llm = ChatGoogleGenerativeAI(
        model=model, api_key=google_api_key
    ).with_structured_output(PortfolioUpdate, method="json_schema")
    results = {}

    total_batches = (len(tickers) + batch_size - 1) // batch_size

    # Process in batches
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"📰 Google news batch {batch_num}/{total_batches}: {batch}")

        # Request comprehensive news summaries for better ranker LLM context
        prompt = f"""Find the most significant news stories for {batch} from {start_date} to {end_date}.

Focus on business catalysts: earnings, product launches, partnerships, analyst changes, regulatory news.

For each ticker, provide a comprehensive summary (5-8 sentences) covering:
- What happened (the catalyst/event)
- Key numbers/metrics if applicable (revenue, earnings, deal size, etc.)
- Why it matters for investors
- Market reaction or implications
- Any forward-looking statements or guidance"""

        try:
            # Step 1: Perform Google search (grounded response)
            raw_news = search_llm.invoke(prompt)

            # Step 2: Structure the grounded results
            structured_result = structured_llm.invoke(
                f"Using this verified news data: {raw_news.content}\n\n"
                f"Format the news for these tickers into the JSON structure: {batch}\n"
                f"Include all tickers from the list, even if no news was found."
            )

            # Extract results
            if structured_result and hasattr(structured_result, "items"):
                for item in structured_result.items:
                    results[item.ticker.upper()] = item.news_summary
            else:
                logger.warning(f"Structured output invalid for batch: {batch}")
                for ticker in batch:
                    results[ticker.upper()] = ""

        except Exception as e:
            logger.error(f"Error fetching Google batch news for {batch}: {e}")
            # On error, set empty string for all tickers in batch
            for ticker in batch:
                results[ticker.upper()] = ""

    return results
