from openai import OpenAI
from .config import get_config


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

    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=f"Search Social Media and news sources for {search_query} from {start_date} to {end_date}. Make sure you only get the data posted during that period."
        )
        return response.output_text
    except Exception as e:
        return f"Error fetching news from OpenAI: {str(e)}"


def get_global_news_openai(date, look_back_days=7, limit=5):
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=f"Search global or macroeconomics news from {look_back_days} days before {date} to {date} that would be informative for trading purposes. Make sure you only get the data posted during that period. Limit the results to {limit} articles."
        )
        return response.output_text
    except Exception as e:
        return f"Error fetching global news from OpenAI: {str(e)}"


def get_fundamentals_openai(ticker, curr_date):
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            tools=[{"type": "web_search_preview"}],
            input=f"Search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc"
        )
        return response.output_text
    except Exception as e:
        return f"Error fetching fundamentals from OpenAI: {str(e)}"