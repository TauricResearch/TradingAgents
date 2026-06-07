"""India macro context placeholders with explicit data-quality notes."""

from __future__ import annotations

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.india.quality import DataQuality


def get_india_macro_context(curr_date: str, look_back_days: int | None = None) -> str:
    config = get_config()
    queries = config.get("india_news_queries", [])
    quality = DataQuality.unavailable(
        "India macro configured queries",
        "Official RBI/MOSPI/DBIE macro APIs are not wired in this offline-safe path.",
    )
    query_block = "\n".join(f"- {query}" for query in queries)
    return (
        f"# India Macro Context\n\nDate: {curr_date}\n"
        f"Look-back days: {look_back_days or config.get('global_news_lookback_days', 7)}\n\n"
        "Official macro datapoints are unavailable in this run. Use these configured query topics "
        "for news/macro retrieval when a permitted source is available:\n\n"
        f"{query_block}\n\n"
        "Data quality:\n"
        f"{quality.to_markdown()}"
    )
