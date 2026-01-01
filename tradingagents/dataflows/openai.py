from openai import OpenAI
from tradingagents.config import settings

_client = None

def get_openai_client():
    """Get or create OpenAI client with lazy initialization."""
    global _client
    if _client is None:
        try:
            base_url = settings.BACKEND_URL
            if not base_url:
                raise ValueError("backend_url not found in configuration")
            _client = OpenAI(base_url=base_url)
        except Exception as e:
            print(f"ERROR: Failed to initialize OpenAI client: {e}")
            raise
    
    return _client

def get_stock_news_openai(query, start_date, end_date):
    client = get_openai_client()

    response = client.responses.create(
        model=settings.QUICK_THINK_LLM,
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
        tool_choice={"type": "web_search_preview"},
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text

def get_crypto_news_openai(query, start_date, end_date):
    client = get_openai_client()

    response = client.responses.create(
        model=settings.QUICK_THINK_LLM,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Can you search News for {query} from {start_date} to {end_date}? Make sure you only get the data posted during that period.",
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
        tool_choice={"type": "web_search_preview"},
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text

def get_global_news_openai(curr_date, look_back_days=7, limit=5):
    client = get_openai_client()

    response = client.responses.create(
        model=settings.QUICK_THINK_LLM,
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
        tool_choice={"type": "web_search_preview"},
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text


def get_fundamentals_openai(ticker, curr_date):
    client = get_openai_client()

    response = client.responses.create(
        model=settings.QUICK_THINK_LLM,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        # "text": f"Can you search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc",
                        "text": f"Can you search Fundamental data on {ticker} crypto-currency coin before {curr_date} to {curr_date}. Make sure you only get the data posted during that period. The data includes purpose, use case, technology, token utility, tokenomics, team & organization, development activity, ecosystem & adoption, and governance & community.",
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
        tool_choice={"type": "web_search_preview"},
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text

def get_whitepaper_openai(symbol):
    client = get_openai_client()

    response = client.responses.create(
        model=settings.QUICK_THINK_LLM,
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Give me the summary of {symbol} crypto coin white paper.",
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
        tool_choice={"type": "web_search_preview"},
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return response.output[1].content[0].text
