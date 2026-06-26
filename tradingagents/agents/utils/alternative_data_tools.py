import logging
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.youtube import fetch_youtube_sentiment

logger = logging.getLogger(__name__)

@tool
def get_youtube_sentiment(
    ticker: Annotated[str, "ticker symbol"],
    limit: Annotated[int, "number of videos to fetch"] = 5
) -> str:
    """
    Search YouTube for recent videos about the ticker to gauge retail influencer sentiment,
    hype, and long-form analysis. Returns titles, views, and descriptions.
    """
    return fetch_youtube_sentiment(ticker, limit)
