from datetime import datetime, timedelta

from openai import OpenAI
from .config import get_config


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

    return response.output[1].content[0].text


def get_global_news_openai(curr_date, look_back_days=7, limit=5):

    def _extract_text(resp):
        # 1) Preferred field for the Responses API
        if hasattr(resp, "output_text") and resp.output_text:
            return resp.output_text

        # 2) Structured outputs (some SDK builds)
        try:
            if resp.output and len(resp.output) > 0:
                parts = resp.output[0].content or []
                texts = []
                for p in parts:
                    # p may be a plain object with .text, or a dict
                    t = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
                    if t:
                        texts.append(t)
                if texts:
                    return "\n".join(texts)
        except Exception:
            pass

        # 3) Chat Completions style fallback (just in case)
        try:
            return resp.choices[0].message["content"]
        except Exception:
            pass

        # 4) Last resort: stringify the whole object
        return str(resp)

    config = get_config()
    client = OpenAI(base_url=config["backend_url"])

    # Build a clean date window
    end = datetime.strptime(curr_date, "%Y-%m-%d").date()
    start = end - timedelta(days=look_back_days)

    prompt = (
        f"List {limit} global or macroeconomic news items helpful for trading, "
        f"strictly published between {start.isoformat()} and {end.isoformat()} (inclusive). "
        "For each item, give: date, headline, 1-2 sentence trading relevance. "
        "Do not include articles outside the window."
    )

    resp = client.responses.create(
        model=config["quick_think_llm"],
        input=prompt,
        reasoning={},
        tools=[{"type": "web_search_preview"}],
        max_output_tokens=4096,
        store=False,
    )

    return _extract_text(resp)


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

    return response.output[1].content[0].text