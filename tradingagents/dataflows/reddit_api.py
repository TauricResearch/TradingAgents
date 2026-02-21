from datetime import datetime, timedelta
from typing import Annotated

import praw

from tradingagents.config import config
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


def get_reddit_client():
    """Initialize and return a PRAW Reddit instance."""
    client_id = config.validate_key("reddit_client_id", "Reddit Client ID")
    client_secret = config.validate_key("reddit_client_secret", "Reddit Client Secret")
    user_agent = config.reddit_user_agent

    return praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)


def get_reddit_news(
    ticker: Annotated[str, "Ticker symbol"] = None,
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"] = None,
    end_date: Annotated[str, "End date in yyyy-mm-dd format"] = None,
    query: Annotated[str, "Search query or ticker symbol"] = None,
) -> str:
    """
    Fetch company news/discussion from Reddit with top comments.
    """
    target_query = query or ticker
    if not target_query:
        raise ValueError("Must provide query or ticker")

    try:
        reddit = get_reddit_client()

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        # Add one day to end_date to include the full day
        end_dt = end_dt + timedelta(days=1)

        # Subreddits to search
        subreddits = "stocks+investing+wallstreetbets+stockmarket"

        # Search queries - try multiple variations
        queries = [
            target_query,
            f"${target_query}",  # Common format on WSB
            target_query.lower(),
        ]

        posts = []
        seen_ids = set()  # Avoid duplicates
        subreddit = reddit.subreddit(subreddits)

        # Try multiple search strategies
        for q in queries:
            # Strategy 1: Search by relevance
            for submission in subreddit.search(q, sort="relevance", time_filter="all", limit=50):
                if submission.id in seen_ids:
                    continue

                post_date = datetime.fromtimestamp(submission.created_utc)

                if start_dt <= post_date <= end_dt:
                    seen_ids.add(submission.id)

                    # Fetch top comments for this post
                    submission.comment_sort = "top"
                    submission.comments.replace_more(limit=0)

                    top_comments = []
                    for comment in submission.comments[:5]:  # Top 5 comments
                        if hasattr(comment, "body") and hasattr(comment, "score"):
                            top_comments.append(
                                {
                                    "body": (
                                        comment.body[:300] + "..."
                                        if len(comment.body) > 300
                                        else comment.body
                                    ),
                                    "score": comment.score,
                                    "author": (
                                        str(comment.author) if comment.author else "[deleted]"
                                    ),
                                }
                            )

                    posts.append(
                        {
                            "title": submission.title,
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                            "date": post_date.strftime("%Y-%m-%d"),
                            "url": submission.url,
                            "text": (
                                submission.selftext[:500] + "..."
                                if len(submission.selftext) > 500
                                else submission.selftext
                            ),
                            "subreddit": submission.subreddit.display_name,
                            "top_comments": top_comments,
                        }
                    )

            # Strategy 2: Search by new (for recent posts)
            for submission in subreddit.search(q, sort="new", time_filter="week", limit=50):
                if submission.id in seen_ids:
                    continue

                post_date = datetime.fromtimestamp(submission.created_utc)

                if start_dt <= post_date <= end_dt:
                    seen_ids.add(submission.id)

                    submission.comment_sort = "top"
                    submission.comments.replace_more(limit=0)

                    top_comments = []
                    for comment in submission.comments[:5]:
                        if hasattr(comment, "body") and hasattr(comment, "score"):
                            top_comments.append(
                                {
                                    "body": (
                                        comment.body[:300] + "..."
                                        if len(comment.body) > 300
                                        else comment.body
                                    ),
                                    "score": comment.score,
                                    "author": (
                                        str(comment.author) if comment.author else "[deleted]"
                                    ),
                                }
                            )

                    posts.append(
                        {
                            "title": submission.title,
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                            "date": post_date.strftime("%Y-%m-%d"),
                            "url": submission.url,
                            "text": (
                                submission.selftext[:500] + "..."
                                if len(submission.selftext) > 500
                                else submission.selftext
                            ),
                            "subreddit": submission.subreddit.display_name,
                            "top_comments": top_comments,
                        }
                    )

        if not posts:
            return f"No Reddit posts found for {target_query} between {start_date} and {end_date}."

        # Format output
        report = f"## Reddit Discussions for {target_query} ({start_date} to {end_date})\n\n"
        report += f"**Total Posts Found:** {len(posts)}\n\n"

        # Sort by score (popularity)
        posts.sort(key=lambda x: x["score"], reverse=True)

        # Detailed view of top posts
        report += "### Top Posts with Community Reactions\n\n"
        for i, post in enumerate(posts[:10], 1):  # Top 10 posts
            report += f"#### {i}. [{post['subreddit']}] {post['title']}\n"
            report += f"**Score:** {post['score']} | **Comments:** {post['num_comments']} | **Date:** {post['date']}\n\n"

            if post["text"]:
                report += f"**Post Content:**\n{post['text']}\n\n"

            if post["top_comments"]:
                report += f"**Top Community Reactions ({len(post['top_comments'])} comments):**\n"
                for j, comment in enumerate(post["top_comments"], 1):
                    report += f"{j}. *[{comment['score']} upvotes]* u/{comment['author']}: {comment['body']}\n"
                report += "\n"

            report += f"**Link:** {post['url']}\n\n"
            report += "---\n\n"

        # Summary statistics
        total_engagement = sum(p["score"] + p["num_comments"] for p in posts)
        avg_score = sum(p["score"] for p in posts) / len(posts) if posts else 0

        report += "### Summary Statistics\n"
        report += f"- **Total Posts:** {len(posts)}\n"
        report += f"- **Average Score:** {avg_score:.1f}\n"
        report += f"- **Total Engagement:** {total_engagement:,} (upvotes + comments)\n"
        report += (
            f"- **Most Active Subreddit:** {max(posts, key=lambda x: x['score'])['subreddit']}\n"
        )

        return report

    except Exception as e:
        return f"Error fetching Reddit news: {str(e)}"


def get_reddit_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"] = None,
    date: Annotated[str, "Date in yyyy-mm-dd format"] = None,
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """
    Fetch global news from Reddit.
    """
    target_date = date or curr_date
    if not target_date:
        raise ValueError("Must provide date")

    try:
        reddit = get_reddit_client()

        curr_dt = datetime.strptime(target_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=look_back_days)

        # Subreddits for global news
        subreddits = "financenews+finance+economics+stockmarket"

        posts = []
        subreddit = reddit.subreddit(subreddits)

        # For global news, we just want top posts from the period
        # We can use 'top' with time_filter, but 'week' is a fixed window.
        # Better to iterate top of 'week' and filter by date.

        for submission in subreddit.top(time_filter="week", limit=50):
            post_date = datetime.fromtimestamp(submission.created_utc)

            if start_dt <= post_date <= curr_dt + timedelta(days=1):
                posts.append(
                    {
                        "title": submission.title,
                        "score": submission.score,
                        "date": post_date.strftime("%Y-%m-%d"),
                        "subreddit": submission.subreddit.display_name,
                    }
                )

        if not posts:
            return f"No global news found on Reddit for the past {look_back_days} days."

        # Format output
        report = f"## Global News from Reddit (Last {look_back_days} days)\n\n"

        posts.sort(key=lambda x: x["score"], reverse=True)

        for post in posts[:limit]:
            report += f"### [{post['subreddit']}] {post['title']} (Score: {post['score']})\n"
            report += f"**Date:** {post['date']}\n\n"

        return report

    except Exception as e:
        return f"Error fetching global Reddit news: {str(e)}"


def get_reddit_trending_tickers(
    limit: Annotated[int, "Number of posts to retrieve"] = 10,
    look_back_days: Annotated[int, "Number of days to look back"] = 3,
) -> str:
    """
    Fetch trending discussions from Reddit (r/wallstreetbets, r/stocks, r/investing)
    to be analyzed for trending tickers.
    """
    try:
        reddit = get_reddit_client()

        # Subreddits to scan
        subreddits = "wallstreetbets+stocks+investing+stockmarket"
        subreddit = reddit.subreddit(subreddits)

        posts = []

        # Scan hot posts
        for submission in subreddit.hot(limit=limit * 2):  # Fetch more to filter by date
            # Check date
            post_date = datetime.fromtimestamp(submission.created_utc)
            if (datetime.now() - post_date).days > look_back_days:
                continue

            # Fetch top comments
            submission.comment_sort = "top"
            submission.comments.replace_more(limit=0)

            top_comments = []
            for comment in submission.comments[:3]:
                if hasattr(comment, "body"):
                    top_comments.append(f"- {comment.body[:200]}...")

            posts.append(
                {
                    "title": submission.title,
                    "score": submission.score,
                    "subreddit": submission.subreddit.display_name,
                    "text": (
                        submission.selftext[:500] + "..."
                        if len(submission.selftext) > 500
                        else submission.selftext
                    ),
                    "comments": top_comments,
                }
            )

            if len(posts) >= limit:
                break

        if not posts:
            return "No trending discussions found."

        # Format report for LLM
        report = "## Trending Reddit Discussions\n\n"
        for i, post in enumerate(posts, 1):
            report += f"### {i}. [{post['subreddit']}] {post['title']} (Score: {post['score']})\n"
            if post["text"]:
                report += f"**Content:** {post['text']}\n"
            if post["comments"]:
                report += "**Top Comments:**\n" + "\n".join(post["comments"]) + "\n"
            report += "\n---\n"

        return report

    except Exception as e:
        return f"Error fetching trending tickers: {str(e)}"


def get_reddit_discussions(
    symbol: Annotated[str, "Ticker symbol"],
    from_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    to_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Wrapper for get_reddit_news to match get_reddit_discussions registry signature.
    """
    return get_reddit_news(ticker=symbol, start_date=from_date, end_date=to_date)


def get_reddit_undiscovered_dd(
    lookback_hours: Annotated[int, "Hours to look back"] = 72,
    scan_limit: Annotated[int, "Number of new posts to scan"] = 100,
    top_n: Annotated[int, "Number of top DD posts to return"] = 10,
    num_comments: Annotated[int, "Number of top comments to include"] = 10,
    llm_evaluator=None,  # Will be passed from discovery graph
    as_list: bool = False,
) -> str | list:
    """
    Find high-quality undiscovered DD using LLM evaluation.

    LEADING INDICATOR: Deep research before it goes viral.

    Strategy:
    1. Scan NEW posts (not hot) from quality subreddits
    2. Send ALL to LLM for quality evaluation (parallel)
    3. LLM filters for: quality analysis, sound thesis, novel insights
    4. Return top-scoring DD posts

    Args:
        lookback_hours: How far back to scan
        scan_limit: Number of posts to scan
        top_n: Number of top DD to return
        llm_evaluator: LLM instance for evaluation

    Returns:
        Report of high-quality undiscovered DD
    """
    try:
        reddit = get_reddit_client()

        subreddits = "stocks+investing+StockMarket+wallstreetbets+Superstonk+pennystocks"
        subreddit = reddit.subreddit(subreddits)
        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

        # Collect ALL recent posts (minimal filtering)
        candidate_posts = []

        for submission in subreddit.new(limit=scan_limit):
            post_date = datetime.fromtimestamp(submission.created_utc)

            if post_date < cutoff_time:
                continue

            # Only filter: has text content
            if not submission.selftext or len(submission.selftext) < 200:
                continue

            top_comments = []
            if llm_evaluator:
                # Get top comments for community validation
                submission.comment_sort = "top"
                submission.comments.replace_more(limit=0)
                for comment in submission.comments[:num_comments]:
                    if hasattr(comment, "body") and hasattr(comment, "score"):
                        top_comments.append(
                            {
                                "body": comment.body[:1000],  # Include more of each comment
                                "score": comment.score,
                            }
                        )

            candidate_posts.append(
                {
                    "title": submission.title,
                    "author": str(submission.author) if submission.author else "[deleted]",
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "subreddit": submission.subreddit.display_name,
                    "flair": submission.link_flair_text or "None",
                    "date": post_date.strftime("%Y-%m-%d %H:%M"),
                    "url": f"https://reddit.com{submission.permalink}",
                    "text": submission.selftext[:1500],  # First 1500 chars for LLM
                    "full_length": len(submission.selftext),
                    "hours_ago": int((datetime.now() - post_date).total_seconds() / 3600),
                    "top_comments": top_comments,
                }
            )

        if not candidate_posts:
            return f"# Undiscovered DD\n\nNo posts found in last {lookback_hours}h."

        logger.info(f"Scanning {len(candidate_posts)} Reddit posts with LLM...")

        # LLM evaluation (parallel)
        if llm_evaluator:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from typing import List

            from pydantic import BaseModel, Field

            # Define structured output schema
            class DDEvaluation(BaseModel):
                score: int = Field(description="Quality score 0-100")
                reason: str = Field(description="Brief reasoning for the score")
                tickers: List[str] = Field(
                    default_factory=list,
                    description="List of stock ticker symbols mentioned (empty list if none)",
                )

            # Configure LLM for Reddit content (adjust safety settings if using Gemini)
            try:
                # Check if using Google Gemini and configure safety settings
                if (
                    hasattr(llm_evaluator, "model_name")
                    and "gemini" in llm_evaluator.model_name.lower()
                ):
                    from langchain_google_genai import HarmBlockThreshold, HarmCategory

                    # More permissive safety settings for financial content analysis
                    llm_evaluator.safety_settings = {
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    }
                    logger.info(
                        "⚙️  Configured Gemini with permissive safety settings for financial content"
                    )
            except Exception as e:
                logger.warning(f"Could not configure safety settings: {e}")

            # Create structured LLM
            structured_llm = llm_evaluator.with_structured_output(DDEvaluation)

            def evaluate_post(post):
                try:
                    # Build prompt with comments if available
                    comments_section = ""
                    if post.get("top_comments") and len(post["top_comments"]) > 0:
                        comments_section = "\n\nTop Community Comments (for validation):\n"
                        for i, comment in enumerate(post["top_comments"], 1):
                            comments_section += (
                                f"{i}. [{comment['score']} upvotes] {comment['body']}\n"
                            )

                    prompt = f"""Evaluate this Reddit post for investment Due Diligence quality.

Title: {post['title']}
Subreddit: r/{post['subreddit']}
Upvotes: {post['score']} | Comments: {post['num_comments']}

Content:
{post['text']}{comments_section}

Score 0-100 based on:
- Quality analysis (financial data, metrics, industry research)
- Sound thesis (logical, not just hype/speculation)
- Novel insights (unique perspective vs rehashing news)
- Risk awareness (mentions downsides, realistic)
- Actionable (identifies specific ticker/opportunity)
- Community validation (do top comments support or debunk the thesis?)

Extract all stock ticker symbols mentioned in the post or comments."""

                    result = structured_llm.invoke(prompt)

                    # Handle None result (Gemini blocked content despite safety settings)
                    if result is None:
                        logger.warning(
                            f"⚠️  Content blocked for '{post['title'][:50]}...' - Skipping"
                        )
                        post["quality_score"] = 0
                        post["quality_reason"] = (
                            "Content blocked by LLM safety filter. "
                            "Consider using OpenAI/Anthropic for Reddit content."
                        )
                        post["tickers"] = []
                        return post

                    # Extract values from structured response
                    post["quality_score"] = result.score
                    post["quality_reason"] = result.reason
                    post["tickers"] = result.tickers  # Now a list

                except Exception as e:
                    logger.error(f"Error evaluating '{post['title'][:50]}': {str(e)}")
                    post["quality_score"] = 0
                    post["quality_reason"] = f"Error: {str(e)}"
                    post["tickers"] = []

                return post

            # Parallel evaluation
            logger.info(f"Scanning {len(candidate_posts)} Reddit posts with LLM...")
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(evaluate_post, post) for post in candidate_posts]
                evaluated = [f.result() for f in as_completed(futures)]

            # Filter quality threshold (55+ = decent DD)
            quality_dd = [p for p in evaluated if p["quality_score"] >= 55]
            quality_dd.sort(key=lambda x: x["quality_score"], reverse=True)

            # Debug: show score distribution
            all_scores = [p["quality_score"] for p in evaluated if p["quality_score"] > 0]
            if all_scores:
                avg_score = sum(all_scores) / len(all_scores)
                max_score = max(all_scores)
                logger.info(
                    f"Score distribution: avg={avg_score:.1f}, max={max_score}, quality_posts={len(quality_dd)}"
                )

            top_dd = quality_dd[:top_n]

        else:
            # No LLM - sort by length + engagement
            candidate_posts.sort(key=lambda x: x["full_length"] + (x["score"] * 10), reverse=True)
            top_dd = candidate_posts[:top_n]

        if as_list:
            if not llm_evaluator:
                import re

                ticker_pattern = r"\$([A-Z]{2,5})\b|^([A-Z]{2,5})\s"
                for post in top_dd:
                    matches = re.findall(ticker_pattern, post["title"] + " " + post["text"])
                    tickers = list(set([t[0] or t[1] for t in matches if t[0] or t[1]]))
                    post["ticker"] = tickers[0] if tickers else ""
                    post["quality_score"] = 75  # default to Medium priority
            return top_dd

        if not top_dd:
            return f"# Undiscovered DD\n\nNo high-quality DD found (scanned {len(candidate_posts)} posts)."

        # Build report
        report = "# 💎 Undiscovered DD (LLM-Filtered Quality)\n\n"
        report += f"**Scanned:** {len(candidate_posts)} posts\n"
        report += f"**High Quality:** {len(top_dd)} DD posts (score ≥60)\n\n"

        for i, post in enumerate(top_dd, 1):
            report += f"## {i}. {post['title']}\n\n"

            if "quality_score" in post:
                report += f"**Quality:** {post['quality_score']}/100 - {post['quality_reason']}\n"
                if post.get("tickers") and len(post["tickers"]) > 0:
                    tickers_str = ", ".join([f"${t}" for t in post["tickers"]])
                    report += f"**Tickers:** {tickers_str}\n"

            report += f"**r/{post['subreddit']}** | {post['hours_ago']}h ago | "
            report += f"{post['score']} ⬆ {post['num_comments']} 💬\n\n"

            report += f"{post['text'][:600]}...\n\n"
            report += f"[Read Full DD]({post['url']})\n\n---\n\n"

        return report

    except Exception as e:
        import traceback

        return f"# Undiscovered DD\n\nError: {str(e)}\n{traceback.format_exc()}"
