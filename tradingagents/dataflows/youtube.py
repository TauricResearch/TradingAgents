import json
import logging
import subprocess

logger = logging.getLogger(__name__)

def fetch_youtube_sentiment(
    ticker: str,
    limit: int = 5,
    timeout: float = 45.0,
) -> str:
    """Fetch recent YouTube videos and sentiment mentioning ``ticker``."""
    cmd = [
        "opencli", "youtube", "search", ticker,
        "--limit", str(limit),
        "-f", "json"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=True, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            try:
                videos = json.loads(res.stdout)
            except json.JSONDecodeError:
                logger.warning("opencli youtube search returned invalid JSON: %s", res.stdout)
                return f"<no YouTube data found for {ticker.upper()} (invalid JSON)>"
                
            if not videos:
                return f"<no YouTube data found for {ticker.upper()}>"
            
            blocks = []
            blocks.append(f"YouTube — {len(videos)} recent videos mentioning {ticker.upper()}:")
            for v in videos:
                title = (v.get("title") or "").strip()
                desc = (v.get("description") or "").replace("\n", " ").strip()
                views = v.get("viewCount") or 0
                
                blocks.append(f"Title: {title}")
                blocks.append(f"Views: {views}")
                if desc:
                    # Truncate very long descriptions
                    blocks.append(f"Description: {desc[:300]}...")
                blocks.append("---")
            return "\n".join(blocks)
        else:
            return f"<failed to fetch YouTube data: {res.stderr.strip()}>"
    except subprocess.TimeoutExpired:
        return "<YouTube search timed out>"
    except Exception as e:
        return f"<YouTube search failed: {e}>"
