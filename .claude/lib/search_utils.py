"""Search utilities for researcher agent.

Provides utilities for:
- Web fetch caching
- Source quality scoring
- Pattern quality scoring
- Knowledge base freshness checking
"""

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class WebFetchCache:
    """Cache for web fetch results to reduce duplicate API calls.

    Caches fetched URLs with 7-day TTL to avoid re-fetching same content.
    Saves API costs and improves performance.

    Usage:
        cache = WebFetchCache()

        # Try cache first
        content = cache.get(url)
        if not content:
            content = fetch_from_web(url)
            cache.set(url, content)
    """

    def __init__(self, cache_dir: Optional[Path] = None, ttl_days: int = 7):
        """Initialize web fetch cache.

        Args:
            cache_dir: Directory to store cached files. Defaults to .claude/cache/web-fetch
            ttl_days: Time to live in days. Default 7 days.
        """
        if cache_dir is None:
            cache_dir = Path(".claude/cache/web-fetch")

        self.cache_dir = Path(cache_dir)
        self.ttl_days = ttl_days
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, url: str) -> Path:
        """Get cache file path for URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.md"

    def get(self, url: str) -> Optional[str]:
        """Get cached content if fresh.

        Args:
            url: URL to fetch from cache

        Returns:
            Cached content if exists and fresh, None otherwise
        """
        cache_file = self._get_cache_path(url)

        if not cache_file.exists():
            return None

        try:
            content = cache_file.read_text()

            # Extract expiry date
            if "**Expires**:" in content:
                for line in content.split("\n"):
                    if "**Expires**:" in line:
                        expires_str = line.split(":", 1)[1].strip()
                        expires = datetime.fromisoformat(expires_str)

                        # Check if expired
                        if datetime.now() > expires:
                            cache_file.unlink()
                            return None

                        break

            # Extract content (after separator)
            if "---" in content:
                parts = content.split("---", 1)
                if len(parts) == 2:
                    return parts[1].strip()

            return content

        except Exception:
            # If any error reading cache, treat as miss
            return None

    def set(self, url: str, content: str) -> None:
        """Cache content with TTL.

        Args:
            url: URL being cached
            content: Content to cache
        """
        cache_file = self._get_cache_path(url)

        expires = datetime.now() + timedelta(days=self.ttl_days)

        cached = f"""# Cached Web Fetch

**URL**: {url}
**Fetched**: {datetime.now().isoformat()}
**Expires**: {expires.isoformat()}

---

{content}"""

        cache_file.write_text(cached)

    def clear_expired(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of entries removed
        """
        removed = 0
        for cache_file in self.cache_dir.glob("*.md"):
            try:
                content = cache_file.read_text()

                if "**Expires**:" in content:
                    for line in content.split("\n"):
                        if "**Expires**:" in line:
                            expires_str = line.split(":", 1)[1].strip()
                            expires = datetime.fromisoformat(expires_str)

                            if datetime.now() > expires:
                                cache_file.unlink()
                                removed += 1
                            break
            except Exception:
                # If can't read, remove to be safe
                cache_file.unlink()
                removed += 1

        return removed


def score_source(url: str, title: str = "", snippet: str = "") -> float:
    """Score source quality for prioritization.

    Scores sources based on:
    - Authority (official docs, well-known sites)
    - Recency (2024-2025 content preferred)
    - Content indicators (tutorials, code examples)

    Args:
        url: Source URL
        title: Page title
        snippet: Text snippet from search result

    Returns:
        Quality score from 0.0 to 1.0
    """
    score = 0.0
    url_lower = url.lower()
    title_lower = title.lower()
    snippet_lower = snippet.lower()

    # Authority scoring (0.5 max)
    high_authority = [
        "python.org", "docs.python.org",
        "github.com", "anthropic.com", "docs.anthropic.com",
        "martinfowler.com", "realpython.com",
        "auth0.com", "owasp.org",
        "readthedocs.io", "readthedocs.org",
    ]

    medium_authority = [
        "stackoverflow.com", "medium.com",
        "dev.to", "hackernoon.com",
        "thoughtworks.com", "elastic.co",
    ]

    if any(auth in url_lower for auth in high_authority):
        score += 0.5
    elif any(auth in url_lower for auth in medium_authority):
        score += 0.3
    else:
        score += 0.1  # Base score for any source

    # Recency scoring (0.3 max)
    # Extract year from snippet or title
    year_pattern = r'\b(202[3-5]|2025)\b'
    year_match = re.search(year_pattern, snippet_lower + " " + title_lower)

    if year_match:
        year = int(year_match.group(1))
        current_year = datetime.now().year
        years_old = current_year - year

        if years_old == 0:
            score += 0.3  # Current year
        elif years_old == 1:
            score += 0.2  # Last year
        elif years_old == 2:
            score += 0.1  # 2 years old
        # Older than 2 years: no recency bonus

    # Content quality indicators (0.2 max)
    quality_indicators = {
        "tutorial": 0.05,
        "guide": 0.05,
        "best practices": 0.1,
        "example": 0.05,
        "code": 0.05,
        "documentation": 0.05,
        "official": 0.1,
    }

    combined_text = title_lower + " " + snippet_lower
    for indicator, points in quality_indicators.items():
        if indicator in combined_text:
            score += points

    # Cap at 1.0
    return min(1.0, score)


def score_pattern(
    file_path: str,
    content: str,
    keyword_relevance: float = 0.5,
    has_tests: bool = False,
    has_docstrings: bool = False,
    line_count: int = 0,
    last_modified_days: Optional[int] = None
) -> float:
    """Score codebase pattern quality.

    Scores patterns based on:
    - Keyword relevance (how well it matches search)
    - Has tests (indicates quality)
    - Has docstrings (indicates documentation)
    - Substantial code (>50 lines)
    - Recently modified (indicates maintenance)

    Args:
        file_path: Path to file containing pattern
        content: File content
        keyword_relevance: How relevant to search (0.0-1.0)
        has_tests: Whether tests exist for this pattern
        has_docstrings: Whether docstrings present
        line_count: Number of lines in file
        last_modified_days: Days since last modification

    Returns:
        Quality score from 0.0 to 1.0
    """
    score = 0.0

    # Keyword relevance (0.0-0.2)
    score += keyword_relevance * 0.2

    # Has tests (+0.3)
    if has_tests:
        score += 0.3

    # Has docstrings (+0.2)
    if has_docstrings:
        score += 0.2
    elif '"""' in content or "'''" in content:
        # Simple heuristic if not explicitly checked
        score += 0.2

    # Substantial code (+0.2)
    if line_count > 50:
        score += 0.2
    elif line_count > 20:
        score += 0.1

    # Recently modified (+0.1)
    if last_modified_days is not None:
        if last_modified_days < 30:
            score += 0.1
        elif last_modified_days < 90:
            score += 0.05

    return min(1.0, score)


def check_knowledge_freshness(knowledge_file: Path, max_age_days: int = 180) -> Tuple[bool, int, str]:
    """Check if knowledge base entry is fresh.

    Args:
        knowledge_file: Path to knowledge file
        max_age_days: Maximum age in days before considering stale

    Returns:
        Tuple of (is_fresh, age_in_days, status_message)
    """
    if not knowledge_file.exists():
        return False, -1, "File does not exist"

    try:
        content = knowledge_file.read_text()

        # Extract date from frontmatter
        date_pattern = r'\*\*Date(?:\s+Researched)?\*\*:\s*(\d{4}-\d{2}-\d{2})'
        match = re.search(date_pattern, content)

        if not match:
            return False, -1, "No date found in file"

        date_str = match.group(1)
        research_date = datetime.strptime(date_str, "%Y-%m-%d")
        age_days = (datetime.now() - research_date).days

        # Check freshness
        if age_days < 0:
            return False, age_days, "Future date (invalid)"
        elif age_days <= max_age_days:
            return True, age_days, f"Fresh ({age_days} days old)"
        else:
            return False, age_days, f"Stale ({age_days} days old, max {max_age_days})"

    except Exception as e:
        return False, -1, f"Error reading file: {str(e)}"


def extract_keywords(text: str, min_length: int = 3, max_keywords: int = 10) -> List[str]:
    """Extract keywords from user request for codebase search.

    Args:
        text: User request text
        min_length: Minimum keyword length
        max_keywords: Maximum keywords to return

    Returns:
        List of keywords sorted by relevance
    """
    # Common stop words to exclude
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all",
        "can", "her", "was", "one", "our", "out", "this", "that",
        "have", "has", "had", "with", "from", "what", "when", "where",
        "how", "why", "should", "would", "could", "implement", "create",
        "add", "make", "use", "using", "need", "want",
    }

    # Extract words
    words = re.findall(r'\b[a-z]+\b', text.lower())

    # Filter and count
    keyword_counts: Dict[str, int] = {}
    for word in words:
        if len(word) >= min_length and word not in stop_words:
            keyword_counts[word] = keyword_counts.get(word, 0) + 1

    # Sort by frequency, then alphabetically
    sorted_keywords = sorted(
        keyword_counts.items(),
        key=lambda x: (-x[1], x[0])
    )

    # Return top keywords
    return [k for k, _ in sorted_keywords[:max_keywords]]


def parse_index_entry(index_content: str, topic: str) -> Optional[Dict[str, str]]:
    """Parse INDEX.md to find knowledge about a topic.

    Args:
        index_content: Content of INDEX.md file
        topic: Topic to search for (e.g., "authentication")

    Returns:
        Dictionary with entry details if found, None otherwise
    """
    topic_lower = topic.lower()

    # Split into sections
    sections = index_content.split("## ")

    for section in sections:
        if not section.strip():
            continue

        # Check if topic mentioned in section
        if topic_lower not in section.lower():
            continue

        # Extract entry details
        entry = {}

        # Extract title (first line)
        lines = section.split("\n")
        if lines:
            entry["title"] = lines[0].strip()

        # Extract file path
        file_match = re.search(r'\*\*File\*\*:\s*`([^`]+)`', section)
        if file_match:
            entry["file"] = file_match.group(1)

        # Extract date
        date_match = re.search(r'\*\*Date\*\*:\s*(\d{4}-\d{2}-\d{2})', section)
        if date_match:
            entry["date"] = date_match.group(1)

        # Extract description
        desc_match = re.search(r'\*\*Description\*\*:\s*([^\n]+)', section)
        if desc_match:
            entry["description"] = desc_match.group(1)

        if "file" in entry:
            return entry

    return None


def bootstrap_knowledge_base(
    workspace_kb: Optional[Path] = None,
    template_kb: Optional[Path] = None
) -> Tuple[bool, str]:
    """Bootstrap knowledge base from plugin template if not exists.

    Creates .claude/knowledge/ by copying from plugin templates/knowledge/
    if the workspace knowledge base doesn't exist yet.

    Args:
        workspace_kb: Path to workspace knowledge base. Defaults to .claude/knowledge
        template_kb: Path to template knowledge base. Defaults to plugins/.../templates/knowledge

    Returns:
        Tuple of (success, message)
    """
    if workspace_kb is None:
        workspace_kb = Path(".claude/knowledge")

    if template_kb is None:
        template_kb = Path("plugins/autonomous-dev/templates/knowledge")

    # Check if workspace knowledge base already exists
    if workspace_kb.exists():
        # Already bootstrapped
        return True, "Knowledge base already exists"

    # Check if template exists
    if not template_kb.exists():
        # Create minimal structure without template
        try:
            workspace_kb.mkdir(parents=True, exist_ok=True)
            (workspace_kb / "best-practices").mkdir(exist_ok=True)
            (workspace_kb / "patterns").mkdir(exist_ok=True)
            (workspace_kb / "research").mkdir(exist_ok=True)

            # Create minimal INDEX.md
            index_content = """# Knowledge Base Index

**Last Updated**: {date}
**Purpose**: Persistent, organized knowledge for autonomous-dev plugin

## How to Use This Knowledge Base

### For Agents
Before researching a topic:
1. Read this INDEX to check if knowledge already exists
2. If found, read the specific file (avoids duplicate research)
3. If not found, research and save new findings here

### For Humans
- Browse by category below
- Each entry includes: topic, file path, date researched, brief description

---

## Best Practices

*(No entries yet)*

## Patterns

*(No entries yet)*

## Research

*(No entries yet)*
""".format(date=datetime.now().strftime("%Y-%m-%d"))

            (workspace_kb / "INDEX.md").write_text(index_content)

            return True, "Created minimal knowledge base structure (no template found)"

        except Exception as e:
            return False, f"Failed to create knowledge base: {str(e)}"

    # Copy template to workspace
    try:
        import shutil
        shutil.copytree(template_kb, workspace_kb)
        return True, f"Initialized knowledge base from template: {template_kb}"

    except Exception as e:
        return False, f"Failed to copy template: {str(e)}"


# Example usage and testing
if __name__ == "__main__":
    print("=== Search Utilities Tests ===\n")

    # Test WebFetchCache
    print("1. Web Fetch Cache")
    cache = WebFetchCache(Path("/tmp/test-cache"))
    test_url = "https://example.com/article"

    # Should be miss first time
    result = cache.get(test_url)
    print(f"   Cache miss: {result is None}")

    # Set cache
    cache.set(test_url, "Test content")

    # Should be hit second time
    result = cache.get(test_url)
    print(f"   Cache hit: {result == 'Test content'}")
    print()

    # Test source scoring
    print("2. Source Quality Scoring")
    scores = [
        ("https://docs.python.org/guide", "Python Guide 2025", "Tutorial", "High authority + recent"),
        ("https://github.com/user/repo", "Example code", "Code examples 2024", "High authority"),
        ("https://medium.com/article", "Tutorial", "How to do X", "Medium authority"),
        ("https://random.com/post", "Old post", "Post from 2020", "Low authority + old"),
    ]

    for url, title, snippet, description in scores:
        score = score_source(url, title, snippet)
        print(f"   {description}: {score:.2f}")
    print()

    # Test pattern scoring
    print("3. Pattern Quality Scoring")
    patterns = [
        ("High quality", 0.9, True, True, 200, 10),
        ("Medium quality", 0.6, False, True, 100, 60),
        ("Low quality", 0.3, False, False, 30, 365),
    ]

    for desc, relevance, tests, docs, lines, days in patterns:
        score = score_pattern("test.py", "content", relevance, tests, docs, lines, days)
        print(f"   {desc}: {score:.2f}")
    print()

    # Test keyword extraction
    print("4. Keyword Extraction")
    text = "implement user authentication with JWT tokens for secure API access"
    keywords = extract_keywords(text)
    print(f"   Keywords: {', '.join(keywords)}")
    print()

    print("✅ All tests complete!")
