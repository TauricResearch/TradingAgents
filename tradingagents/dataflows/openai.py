import os

from openai import OpenAI
from .config import get_config


def _get_web_search_tool_type() -> str:
    """Return the appropriate web search tool type based on FETCH_LATEST setting.

    - FETCH_LATEST=true: Use 'web_search' (GA version, supports GPT-5)
    - FETCH_LATEST=false/unset: Use 'web_search_preview' (legacy, wider compatibility)
    """
    fetch_latest = os.getenv("FETCH_LATEST", "false").lower() in ("true", "1", "yes")
    return "web_search" if fetch_latest else "web_search_preview"


def _extract_text_from_response(response):
    """Safely extract text content from OpenAI Responses API output.

    The response.output array typically contains:
    - output[0]: ResponseFunctionWebSearch (the web search call)
    - output[1]: ResponseOutputMessage (the text response)

    This function handles edge cases where the structure may differ.
    """
    if not response.output:
        raise RuntimeError("OpenAI response has empty output")

    # Look for a message with text content
    for item in response.output:
        if hasattr(item, 'content') and item.content:
            for content_block in item.content:
                if hasattr(content_block, 'text') and content_block.text:
                    return content_block.text

    # If we get here, no text was found
    output_types = [type(item).__name__ for item in response.output]
    raise RuntimeError(
        f"No text content found in OpenAI response. "
        f"Output types: {output_types}"
    )


def get_stock_news_openai(query, start_date, end_date):
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
                "type": _get_web_search_tool_type(),
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return _extract_text_from_response(response)


def get_global_news_openai(curr_date, look_back_days=7, limit=5):
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
                "type": _get_web_search_tool_type(),
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return _extract_text_from_response(response)


def get_fundamentals_openai(ticker, curr_date):
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
                "type": _get_web_search_tool_type(),
                "user_location": {"type": "approximate"},
                "search_context_size": "low",
            }
        ],
        temperature=1,
        max_output_tokens=4096,
        top_p=1,
        store=True,
    )

    return _extract_text_from_response(response)