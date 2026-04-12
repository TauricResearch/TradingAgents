"""Reddit social media data provider.

Supports two modes:
- Live API (default): uses PRAW with REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET env vars
- Cache mode: reads pre-downloaded JSONL files from a local reddit_data/ directory
"""

import json
import os
import re
from datetime import datetime, timezone

TICKER_TO_COMPANY = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
    "NVDA": "Nvidia",
    "TSM": "Taiwan Semiconductor Manufacturing Company OR TSMC",
    "JPM": "JPMorgan Chase OR JP Morgan",
    "JNJ": "Johnson & Johnson OR JNJ",
    "V": "Visa",
    "WMT": "Walmart",
    "META": "Meta OR Facebook",
    "AMD": "AMD",
    "INTC": "Intel",
    "QCOM": "Qualcomm",
    "BABA": "Alibaba",
    "ADBE": "Adobe",
    "NFLX": "Netflix",
    "CRM": "Salesforce",
    "PYPL": "PayPal",
    "PLTR": "Palantir",
    "MU": "Micron",
    "SQ": "Block OR Square",
    "ZM": "Zoom",
    "CSCO": "Cisco",
    "SHOP": "Shopify",
    "ORCL": "Oracle",
    "X": "Twitter OR X",
    "SPOT": "Spotify",
    "AVGO": "Broadcom",
    "ASML": "ASML",
    "TWLO": "Twilio",
    "SNAP": "Snap Inc.",
    "TEAM": "Atlassian",
    "SQSP": "Squarespace",
    "UBER": "Uber",
    "ROKU": "Roku",
    "PINS": "Pinterest",
}

SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "SecurityAnalysis",
    "options",
    "StockMarket",
]


def _format_posts(ticker: str, start_date: str, end_date: str, posts: list) -> str:
    if not posts:
        return f"No Reddit posts found for {ticker} between {start_date} and {end_date}."

    posts.sort(key=lambda x: x["upvotes"], reverse=True)
    lines = [f"## Reddit Posts for {ticker} ({start_date} to {end_date})\n"]
    for post in posts[:20]:
        lines.append(f"**[r/{post['subreddit']}] {post['title']}** (↑{post['upvotes']})")
        if post.get("content"):
            snippet = post["content"][:300]
            if len(post["content"]) > 300:
                snippet += "..."
            lines.append(snippet)
        lines.append(f"Date: {post['date']} | URL: {post['url']}\n")
    return "\n".join(lines)


def get_reddit_posts(ticker: str, start_date: str, end_date: str) -> str:
    """Fetch Reddit posts about a ticker via PRAW (live Reddit API).

    Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.
    Register an app at https://www.reddit.com/prefs/apps (script type).
    """
    import praw

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        return (
            "Reddit API credentials not configured. "
            "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables. "
            "Register a script app at https://www.reddit.com/prefs/apps to get credentials."
        )

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="TradingAgents:social-media-analyst:v1.0",
        read_only=True,
    )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    company = TICKER_TO_COMPANY.get(ticker.upper(), ticker)
    query = f"{ticker} OR {company}" if company != ticker else ticker

    posts = []
    for subreddit_name in SUBREDDITS:
        subreddit = reddit.subreddit(subreddit_name)
        for submission in subreddit.search(query, sort="new", limit=30):
            post_dt = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).replace(tzinfo=None)
            if not (start_dt <= post_dt <= end_dt):
                continue
            posts.append({
                "subreddit": subreddit_name,
                "title": submission.title,
                "content": submission.selftext,
                "upvotes": submission.score,
                "url": f"https://reddit.com{submission.permalink}",
                "date": post_dt.strftime("%Y-%m-%d"),
            })

    return _format_posts(ticker, start_date, end_date, posts)


def get_reddit_posts_from_cache(
    ticker: str,
    start_date: str,
    end_date: str,
    data_path: str = "reddit_data",
) -> str:
    """Fetch Reddit posts from pre-downloaded local JSONL files.

    Expects files at: {data_path}/{category}/{subreddit}.jsonl
    Each JSONL line must have: created_utc, title, selftext, url, ups.
    """
    if not os.path.isdir(data_path):
        return (
            f"Reddit cache directory '{data_path}' not found. "
            "Download Reddit data first or use the live API mode."
        )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    company_name = TICKER_TO_COMPANY.get(ticker.upper(), ticker)

    search_terms = [ticker]
    if " OR " in company_name:
        search_terms.extend(company_name.split(" OR "))
    elif company_name != ticker:
        search_terms.append(company_name)

    posts = []
    for category in os.listdir(data_path):
        category_path = os.path.join(data_path, category)
        if not os.path.isdir(category_path):
            continue
        for data_file in os.listdir(category_path):
            if not data_file.endswith(".jsonl"):
                continue
            subreddit_name = data_file.replace(".jsonl", "")
            with open(os.path.join(category_path, data_file), "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    parsed = json.loads(line)
                    post_dt = datetime.fromtimestamp(parsed["created_utc"], tz=timezone.utc).replace(tzinfo=None)
                    if not (start_dt <= post_dt <= end_dt):
                        continue
                    # Filter by company/ticker if it's a company category
                    if "company" in category:
                        found = any(
                            re.search(term, parsed["title"], re.IGNORECASE)
                            or re.search(term, parsed.get("selftext", ""), re.IGNORECASE)
                            for term in search_terms
                        )
                        if not found:
                            continue
                    posts.append({
                        "subreddit": subreddit_name,
                        "title": parsed["title"],
                        "content": parsed.get("selftext", ""),
                        "upvotes": parsed["ups"],
                        "url": parsed.get("url", ""),
                        "date": post_dt.strftime("%Y-%m-%d"),
                    })

    return _format_posts(ticker, start_date, end_date, posts)
