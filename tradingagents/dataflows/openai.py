import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .config import get_config


def _extract_response_text(response) -> Optional[str]:
    if not hasattr(response, 'output') or not response.output:
        return None

    for output_item in response.output:
        if not hasattr(output_item, 'content') or not output_item.content:
            continue

        text_pieces = []
        for content_item in output_item.content:
            if hasattr(content_item, 'text') and content_item.text:
                text_pieces.append(content_item.text)

        if text_pieces:
            return "\n".join(text_pieces)

    return None


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

    return _extract_response_text(response) or ""


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

    return _extract_response_text(response) or ""


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

    return _extract_response_text(response) or ""


def get_bulk_news_openai(lookback_hours: int) -> List[Dict[str, Any]]:
    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    end_date = datetime.now()
    start_date = end_date - timedelta(hours=lookback_hours)

    start_str = start_date.strftime("%Y-%m-%d %H:%M")
    end_str = end_date.strftime("%Y-%m-%d %H:%M")

    prompt = f"""Search for recent stock market news, trading news, and earnings announcements from {start_str} to {end_str}.

Return the results as a JSON array with the following structure:
[
  {{
    "title": "Article title",
    "source": "Source name",
    "url": "https://...",
    "published_at": "YYYY-MM-DDTHH:MM:SS",
    "content_snippet": "Brief summary of the article..."
  }}
]

Focus on:
- Stock market movements and trends
- Company earnings reports
- Mergers and acquisitions
- Significant trading activity
- Economic news affecting markets

Return ONLY the JSON array, no additional text."""

    response = client.responses.create(
        model=config["quick_think_llm"],
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
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
                "search_context_size": "medium",
            }
        ],
        temperature=0.5,
        max_output_tokens=8192,
        top_p=1,
        store=True,
    )

    try:
        response_text = _extract_response_text(response)
        if not response_text:
            return []

        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            articles = json.loads(json_match.group())
        else:
            articles = json.loads(response_text)

        result = []
        for item in articles:
            if isinstance(item, dict):
                article = {
                    "title": item.get("title", ""),
                    "source": item.get("source", "Web Search"),
                    "url": item.get("url", ""),
                    "published_at": item.get("published_at", datetime.now().isoformat()),
                    "content_snippet": item.get("content_snippet", "")[:500],
                }
                result.append(article)

        return result

    except (json.JSONDecodeError, AttributeError):
        return []
