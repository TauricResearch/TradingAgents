from langchain_core.tools import tool
from typing import Annotated
from tradingagents.tools.executor import execute_tool

@tool
def get_tweets(
    query: Annotated[str, "Search query for tweets (e.g. ticker symbol or topic)"],
    count: Annotated[int, "Number of tweets to retrieve"] = 10,
) -> str:
    """
    Retrieve recent tweets for a given query.
    Uses the configured news_data vendor (defaulting to twitter).
    Args:
        query (str): Search query
        count (int): Number of tweets to return (default 10)
    Returns:
        str: A formatted string containing recent tweets
    """
    return execute_tool("get_tweets", query=query, count=count)

@tool
def get_tweets_from_user(
    username: Annotated[str, "Twitter username (without @) to fetch tweets from"],
    count: Annotated[int, "Number of tweets to retrieve"] = 10,
) -> str:
    """
    Retrieve recent tweets from a specific Twitter user.
    Uses the configured news_data vendor (defaulting to twitter).
    Args:
        username (str): Twitter username
        count (int): Number of tweets to return (default 10)
    Returns:
        str: A formatted string containing the user's recent tweets
    """
    return execute_tool("get_tweets_from_user", username=username, count=count)
