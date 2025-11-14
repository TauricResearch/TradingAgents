from openai import OpenAI
from .config import get_config


def get_stock_news_openai(query, start_date, end_date):
    """
    Retrieve stock news using LLM provider configured in backend_url.
    Compatible with OpenAI, Gemini (via OpenAI-compatible API), and OpenRouter.

    Args:
        query: Stock ticker or search query
        start_date: Start date for news search
        end_date: End date for news search

    Returns:
        str: News content as text
    """
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    # Use standard chat completions API for compatibility with all providers
    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": "You are a financial news analyst. Search and summarize relevant news from social media and news sources."
            },
            {
                "role": "user",
                "content": f"Can you search Social Media for {query} from {start_date} to {end_date}? Make sure you only get the data posted during that period."
            }
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
    )

    return response.choices[0].message.content


def get_global_news_openai(curr_date, look_back_days=7, limit=5):
    """
    Retrieve global news using LLM provider configured in backend_url.
    Compatible with OpenAI, Gemini (via OpenAI-compatible API), and OpenRouter.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back (default 7)
        limit: Maximum number of articles to return (default 5)

    Returns:
        str: Global news content as text
    """
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    # Use standard chat completions API for compatibility with all providers
    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": "You are a financial news analyst. Search and summarize relevant global and macroeconomic news for trading purposes."
            },
            {
                "role": "user",
                "content": f"Can you search global or macroeconomics news from {look_back_days} days before {curr_date} to {curr_date} that would be informative for trading purposes? Make sure you only get the data posted during that period. Limit the results to {limit} articles."
            }
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
    )

    return response.choices[0].message.content


def get_fundamentals_openai(ticker, curr_date):
    """
    Retrieve fundamental data using LLM provider configured in backend_url.
    Compatible with OpenAI, Gemini (via OpenAI-compatible API), and OpenRouter.

    Args:
        ticker: Stock ticker symbol
        curr_date: Current date in yyyy-mm-dd format

    Returns:
        str: Fundamental data as text (table format with PE/PS/Cash flow etc)
    """
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    # Use standard chat completions API for compatibility with all providers
    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": "You are a financial analyst. Search and provide fundamental data for stocks in a structured table format."
            },
            {
                "role": "user",
                "content": f"Can you search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc"
            }
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
    )

    return response.choices[0].message.content