import os
import tweepy
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
DATA_DIR = Path("data")
CACHE_FILE = DATA_DIR / ".twitter_cache.json"
USAGE_FILE = DATA_DIR / ".twitter_usage.json"
MONTHLY_LIMIT = 200
CACHE_DURATION_HOURS = 4

def _ensure_data_dir():
    """Ensure the data directory exists."""
    DATA_DIR.mkdir(exist_ok=True)

def _load_json(file_path: Path) -> dict:
    """Load JSON data from a file, returning empty dict if not found."""
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def _save_json(file_path: Path, data: dict):
    """Save dictionary to a JSON file."""
    _ensure_data_dir()
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save to {file_path}: {e}")

def _get_cache_key(prefix: str, identifier: str) -> str:
    """Generate a cache key."""
    return f"{prefix}:{identifier}"

def _is_cache_valid(timestamp: float) -> bool:
    """Check if the cached entry is still valid."""
    age_hours = (time.time() - timestamp) / 3600
    return age_hours < CACHE_DURATION_HOURS

def _check_usage_limit() -> bool:
    """Check if the monthly usage limit has been reached."""
    usage_data = _load_json(USAGE_FILE)
    current_month = datetime.now().strftime("%Y-%m")
    
    # Reset usage if it's a new month
    if usage_data.get("month") != current_month:
        usage_data = {"month": current_month, "count": 0}
        _save_json(USAGE_FILE, usage_data)
        return True
        
    return usage_data.get("count", 0) < MONTHLY_LIMIT

def _increment_usage():
    """Increment the usage counter."""
    usage_data = _load_json(USAGE_FILE)
    current_month = datetime.now().strftime("%Y-%m")
    
    if usage_data.get("month") != current_month:
        usage_data = {"month": current_month, "count": 0}
    
    usage_data["count"] = usage_data.get("count", 0) + 1
    _save_json(USAGE_FILE, usage_data)

def get_tweets(query: str, count: int = 10) -> str:
    """
    Fetches recent tweets matching the query using Twitter API v2.
    Includes caching and rate limiting.
    
    Args:
        query (str): The search query (e.g., "AAPL", "Bitcoin").
        count (int): Number of tweets to retrieve (default 10).
        
    Returns:
        str: A formatted string containing the tweets or an error message.
    """
    # 1. Check Cache
    cache_key = _get_cache_key("search", query)
    cache = _load_json(CACHE_FILE)
    
    if cache_key in cache:
        entry = cache[cache_key]
        if _is_cache_valid(entry["timestamp"]):
            return entry["data"] + "\n\n(Source: Local Cache)"

    # 2. Check Rate Limit
    if not _check_usage_limit():
        return "Error: Monthly Twitter API usage limit (200 calls) reached."

    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    
    if not bearer_token:
        return "Error: TWITTER_BEARER_TOKEN not found in environment variables."

    try:
        client = tweepy.Client(bearer_token=bearer_token)
        
        # Search for recent tweets
        safe_count = max(10, min(count, 100))
        
        response = client.search_recent_tweets(
            query=query, 
            max_results=safe_count,
            tweet_fields=['created_at', 'author_id', 'public_metrics']
        )
        
        # 3. Increment Usage
        _increment_usage()
        
        if not response.data:
            result = f"No tweets found for query: {query}"
        else:
            formatted_tweets = f"## Recent Tweets for '{query}'\n\n"
            for tweet in response.data:
                metrics = tweet.public_metrics
                formatted_tweets += f"- **{tweet.created_at}**: {tweet.text}\n"
                if metrics:
                    formatted_tweets += f"  (Likes: {metrics.get('like_count', 0)}, Retweets: {metrics.get('retweet_count', 0)})\n"
                formatted_tweets += "\n"
            result = formatted_tweets

        # 4. Save to Cache
        cache[cache_key] = {
            "timestamp": time.time(),
            "data": result
        }
        _save_json(CACHE_FILE, cache)
        
        return result

    except Exception as e:
        return f"Error fetching tweets: {str(e)}"

def get_tweets_from_user(username: str, count: int = 10) -> str:
    """
    Fetches recent tweets from a specific user using Twitter API v2.
    Includes caching and rate limiting.
    
    Args:
        username (str): The Twitter username (without @).
        count (int): Number of tweets to retrieve (default 10).
        
    Returns:
        str: A formatted string containing the tweets or an error message.
    """
    # 1. Check Cache
    cache_key = _get_cache_key("user", username)
    cache = _load_json(CACHE_FILE)
    
    if cache_key in cache:
        entry = cache[cache_key]
        if _is_cache_valid(entry["timestamp"]):
            return entry["data"] + "\n\n(Source: Local Cache)"

    # 2. Check Rate Limit
    if not _check_usage_limit():
        return "Error: Monthly Twitter API usage limit (200 calls) reached."

    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    
    if not bearer_token:
        return "Error: TWITTER_BEARER_TOKEN not found in environment variables."

    try:
        client = tweepy.Client(bearer_token=bearer_token)
        
        # First, get the user ID
        user = client.get_user(username=username)
        if not user.data:
            return f"Error: User '@{username}' not found."
            
        user_id = user.data.id
        
        # max_results must be between 5 and 100 for get_users_tweets
        safe_count = max(5, min(count, 100))
        
        response = client.get_users_tweets(
            id=user_id,
            max_results=safe_count,
            tweet_fields=['created_at', 'public_metrics']
        )
        
        # 3. Increment Usage
        _increment_usage()
        
        if not response.data:
            result = f"No recent tweets found for user: @{username}"
        else:
            formatted_tweets = f"## Recent Tweets from @{username}\n\n"
            for tweet in response.data:
                metrics = tweet.public_metrics
                formatted_tweets += f"- **{tweet.created_at}**: {tweet.text}\n"
                if metrics:
                    formatted_tweets += f"  (Likes: {metrics.get('like_count', 0)}, Retweets: {metrics.get('retweet_count', 0)})\n"
                formatted_tweets += "\n"
            result = formatted_tweets
            
        # 4. Save to Cache
        cache[cache_key] = {
            "timestamp": time.time(),
            "data": result
        }
        _save_json(CACHE_FILE, cache)
        
        return result

    except Exception as e:
        return f"Error fetching tweets from user @{username}: {str(e)}"

