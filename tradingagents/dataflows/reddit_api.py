import os
import praw
from datetime import datetime, timedelta
from typing import Annotated

def get_reddit_client():
    """Initialize and return a PRAW Reddit instance."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "trading_agents_bot/1.0")

    if not client_id or not client_secret:
        raise ValueError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set in environment variables.")

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent
    )

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
            for submission in subreddit.search(q, sort='relevance', time_filter='all', limit=50):
                if submission.id in seen_ids:
                    continue
                    
                post_date = datetime.fromtimestamp(submission.created_utc)
                
                if start_dt <= post_date <= end_dt:
                    seen_ids.add(submission.id)
                    
                    # Fetch top comments for this post
                    submission.comment_sort = 'top'
                    submission.comments.replace_more(limit=0)
                    
                    top_comments = []
                    for comment in submission.comments[:5]:  # Top 5 comments
                        if hasattr(comment, 'body') and hasattr(comment, 'score'):
                            top_comments.append({
                                'body': comment.body[:300] + "..." if len(comment.body) > 300 else comment.body,
                                'score': comment.score,
                                'author': str(comment.author) if comment.author else '[deleted]'
                            })
                    
                    posts.append({
                        "title": submission.title,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "date": post_date.strftime("%Y-%m-%d"),
                        "url": submission.url,
                        "text": submission.selftext[:500] + "..." if len(submission.selftext) > 500 else submission.selftext,
                        "subreddit": submission.subreddit.display_name,
                        "top_comments": top_comments
                    })
            
            # Strategy 2: Search by new (for recent posts)
            for submission in subreddit.search(q, sort='new', time_filter='week', limit=50):
                if submission.id in seen_ids:
                    continue
                    
                post_date = datetime.fromtimestamp(submission.created_utc)
                
                if start_dt <= post_date <= end_dt:
                    seen_ids.add(submission.id)
                    
                    submission.comment_sort = 'top'
                    submission.comments.replace_more(limit=0)
                    
                    top_comments = []
                    for comment in submission.comments[:5]:
                        if hasattr(comment, 'body') and hasattr(comment, 'score'):
                            top_comments.append({
                                'body': comment.body[:300] + "..." if len(comment.body) > 300 else comment.body,
                                'score': comment.score,
                                'author': str(comment.author) if comment.author else '[deleted]'
                            })
                    
                    posts.append({
                        "title": submission.title,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "date": post_date.strftime("%Y-%m-%d"),
                        "url": submission.url,
                        "text": submission.selftext[:500] + "..." if len(submission.selftext) > 500 else submission.selftext,
                        "subreddit": submission.subreddit.display_name,
                        "top_comments": top_comments
                    })
                
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
            
            if post['text']:
                report += f"**Post Content:**\n{post['text']}\n\n"
            
            if post['top_comments']:
                report += f"**Top Community Reactions ({len(post['top_comments'])} comments):**\n"
                for j, comment in enumerate(post['top_comments'], 1):
                    report += f"{j}. *[{comment['score']} upvotes]* u/{comment['author']}: {comment['body']}\n"
                report += "\n"
            
            report += f"**Link:** {post['url']}\n\n"
            report += "---\n\n"
        
        # Summary statistics
        total_engagement = sum(p['score'] + p['num_comments'] for p in posts)
        avg_score = sum(p['score'] for p in posts) / len(posts) if posts else 0
        
        report += "### Summary Statistics\n"
        report += f"- **Total Posts:** {len(posts)}\n"
        report += f"- **Average Score:** {avg_score:.1f}\n"
        report += f"- **Total Engagement:** {total_engagement:,} (upvotes + comments)\n"
        report += f"- **Most Active Subreddit:** {max(posts, key=lambda x: x['score'])['subreddit']}\n"
            
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
        subreddits = "worldnews+economics+finance"
        
        posts = []
        subreddit = reddit.subreddit(subreddits)
        
        # For global news, we just want top posts from the period
        # We can use 'top' with time_filter, but 'week' is a fixed window.
        # Better to iterate top of 'week' and filter by date.
        
        for submission in subreddit.top(time_filter='week', limit=50):
            post_date = datetime.fromtimestamp(submission.created_utc)
            
            if start_dt <= post_date <= curr_dt + timedelta(days=1):
                posts.append({
                    "title": submission.title,
                    "score": submission.score,
                    "date": post_date.strftime("%Y-%m-%d"),
                    "subreddit": submission.subreddit.display_name
                })
                
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
        for submission in subreddit.hot(limit=limit * 2): # Fetch more to filter by date
            # Check date
            post_date = datetime.fromtimestamp(submission.created_utc)
            if (datetime.now() - post_date).days > look_back_days:
                continue
                
            # Fetch top comments
            submission.comment_sort = 'top'
            submission.comments.replace_more(limit=0)
            
            top_comments = []
            for comment in submission.comments[:3]:
                if hasattr(comment, 'body'):
                    top_comments.append(f"- {comment.body[:200]}...")
            
            posts.append({
                "title": submission.title,
                "score": submission.score,
                "subreddit": submission.subreddit.display_name,
                "text": submission.selftext[:500] + "..." if len(submission.selftext) > 500 else submission.selftext,
                "comments": top_comments
            })
            
            if len(posts) >= limit:
                break
        
        if not posts:
            return "No trending discussions found."
            
        # Format report for LLM
        report = "## Trending Reddit Discussions\n\n"
        for i, post in enumerate(posts, 1):
            report += f"### {i}. [{post['subreddit']}] {post['title']} (Score: {post['score']})\n"
            if post['text']:
                report += f"**Content:** {post['text']}\n"
            if post['comments']:
                report += "**Top Comments:**\n" + "\n".join(post['comments']) + "\n"
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
