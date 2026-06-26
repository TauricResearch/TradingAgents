"""Twitter search fetcher for ticker-specific discussion posts."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

def fetch_twitter_posts(
    ticker: str,
    limit: int = 15,
    timeout: float = 30.0,
) -> str:
    """Fetch recent Twitter posts mentioning ``ticker`` and return them as a formatted plaintext block."""
    cmd = [
        "opencli", "twitter", "search", ticker,
        "--limit", str(limit),
        "-f", "json"
    ]
    try:
        # Using shell=True on Windows because opencli is a .cmd script from npm
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            try:
                posts = json.loads(res.stdout)
            except json.JSONDecodeError:
                logger.warning("opencli twitter search returned invalid JSON: %s", res.stdout)
                return f"<no Twitter posts found mentioning {ticker.upper()} (invalid JSON)>"
                
            if not posts:
                return f"<no Twitter posts found mentioning {ticker.upper()}>"
            
            blocks = []
            blocks.append(f"Twitter — {len(posts)} recent posts mentioning {ticker.upper()}:")
            for p in posts:
                text = (p.get("text") or "").replace("\n", " ").strip()
                score = p.get("likes") or 0
                retweets = p.get("retweets") or 0
                views = p.get("views") or 0
                created = p.get("created_at")
                
                meta = str(created)
                if score is not None:
                    meta += f" · {score:>4}♥"
                if retweets:
                    meta += f" · {retweets:>3}RT"
                if views:
                    meta += f" · {views}👁"
                    
                if len(text) > 240:
                    text = text[:240] + "…"
                author = p.get("author") or "user"
                blocks.append(f"  [{meta}] {author}: {text}")
                
            return "\n".join(blocks)
        else:
            logger.warning("opencli twitter search failed: %s", res.stderr)
            return f"<no Twitter posts found mentioning {ticker.upper()} (opencli failed)>"
    except Exception as e:
        logger.warning("opencli twitter search failed: %s", e)
        return f"<no Twitter posts found mentioning {ticker.upper()} (opencli error)>"
