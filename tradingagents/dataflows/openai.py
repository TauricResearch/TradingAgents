import warnings
from openai import OpenAI
from .config import get_config


def _warn_hallucination_risk(data_type="news", category="news_data", alternatives=None):
    """
    Emit a warning about potential hallucination when using OpenAI for data retrieval.

    Args:
        data_type: Type of data being retrieved (e.g., "news", "fundamental data")
        category: Config category for vendor selection (e.g., "news_data", "fundamental_data")
        alternatives: List of alternative vendor names (default: ["alpha_vantage", "google", "local"])
    """
    if alternatives is None:
        alternatives = ["alpha_vantage", "google", "local"]

    alternatives_str = "', '".join(alternatives)
    warnings.warn(
        f"OpenAI {data_type} vendor may hallucinate or provide outdated {data_type}. "
        f"For reliable {data_type}, use alternative vendors: '{alternatives_str}'. "
        f"Configure in config['data_vendors']['{category}'].",
        UserWarning,
        stacklevel=3
    )


def get_stock_news_openai(query, start_date, end_date):
    """
    Retrieve stock news using OpenAI's LLM.

    WARNING: This function may hallucinate or provide outdated news because it relies on
    the LLM's training data rather than real-time web search. For reliable, up-to-date news,
    consider using alternative vendors such as 'alpha_vantage', 'google', or 'local'.

    Configure alternative vendors in your config:
        config["data_vendors"]["news_data"] = "alpha_vantage"  # or "google" or "local"

    Args:
        query: Stock ticker or search query
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        str: News content (may be hallucinated or outdated)
    """
    _warn_hallucination_risk(data_type="news", category="news_data")
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    response = client.responses.create(
        model=config["quick_think_llm"],
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Can you search Social Media for {query} from {start_date} to {end_date}? Make sure you only get the data posted during that period.",
                    }
                ],
            }
        ],
        text={"format": {"type": "text"}},
        reasoning={},
        tools=[
            {
                "type": "web_search_preview",
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text


def get_global_news_openai(curr_date, look_back_days=7, limit=5):
    """
    Retrieve global news using OpenAI's LLM.

    WARNING: This function may hallucinate or provide outdated news because it relies on
    the LLM's training data rather than real-time web search. For reliable, up-to-date news,
    consider using alternative vendors such as 'alpha_vantage', 'google', or 'local'.

    Configure alternative vendors in your config:
        config["data_vendors"]["news_data"] = "alpha_vantage"  # or "google" or "local"

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back (default: 7)
        limit: Maximum number of articles to return (default: 5)

    Returns:
        str: News content (may be hallucinated or outdated)
    """
    _warn_hallucination_risk(data_type="news", category="news_data")

    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    response = client.responses.create(
        model=config["quick_think_llm"],
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Can you search global or macroeconomics news from {look_back_days} days before {curr_date} to {curr_date} that would be informative for trading purposes? Make sure you only get the data posted during that period. Limit the results to {limit} articles.",
                    }
                ],
            }
        ],
        text={"format": {"type": "text"}},
        reasoning={},
        tools=[
            {
                "type": "web_search_preview",
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text


def get_fundamentals_openai(ticker, curr_date):
    """
    Retrieve fundamental data using OpenAI's LLM.

    WARNING: This function may hallucinate or provide outdated data because it relies on
    the LLM's training data rather than real-time data sources. For reliable, up-to-date
    fundamental data, consider using alternative vendors such as 'alpha_vantage', 'yfinance', or 'local'.

    Configure alternative vendors in your config:
        config["data_vendors"]["fundamental_data"] = "alpha_vantage"  # or "yfinance" or "local"

    Args:
        ticker: Stock ticker symbol
        curr_date: Current date in yyyy-mm-dd format

    Returns:
        str: Fundamental data (may be hallucinated or outdated)
    """
    _warn_hallucination_risk(
        data_type="fundamental data",
        category="fundamental_data",
        alternatives=["alpha_vantage", "yfinance", "local"]
    )

    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    response = client.responses.create(
        model=config["quick_think_llm"],
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Can you search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc",
                    }
                ],
            }
        ],
        text={"format": {"type": "text"}},
        reasoning={},
        tools=[
            {
                "type": "web_search_preview",
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text