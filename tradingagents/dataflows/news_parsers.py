import re
from typing import List, Dict, Any


def _extract_urls(text: str) -> List[str]:
    url_pattern = re.compile(r"https?://[^\s)]+")
    return url_pattern.findall(text or "")


def _strip_md(s: str) -> str:
    if not s:
        return s
    # Remove simple markdown bold/italics markers
    return re.sub(r"[*_`]+", "", s).strip()


def parse_global_news(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses global news text produced by get_global_news_openai into a list of items.
    Expected patterns include enumerated bold headings like:
      1. **October 25, 2025: "Headline"**
         - Trading Relevance: ...
         (source links)
    Returns a list of dicts with keys: date, headline, relevance, sources, raw.
    """
    if not raw_text or not isinstance(raw_text, str):
        return []

    items: List[Dict[str, Any]] = []

    # Find each enumerated bold heading and take content until next heading
    header_iter = list(
        re.finditer(r"(?m)^\s*\d+\.\s+\*\*(.+?)\*\*\s*$", raw_text)
    )
    if not header_iter:
        # Fallback: try to split by lines that start with a date-like pattern in bold
        header_iter = list(
            re.finditer(r"(?m)^\s*\*\*([A-Za-z]+\s+\d{1,2},\s+\d{4}.*)\*\*\s*$", raw_text)
        )

    boundaries = []
    for m in header_iter:
        boundaries.append((m.start(), m.end(), m.group(1)))
    # Add sentinel end
    text_len = len(raw_text)
    for i, (s, e, header_text) in enumerate(boundaries):
        next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else text_len
        block = raw_text[e:next_start].strip()

        header = header_text.strip()
        # Extract date and headline from header
        date_match = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", header)
        quoted_headline = re.search(r"\"([^\"]+)\"", header)
        headline_after_colon = None
        if ":" in header:
            parts = header.split(":", 1)
            headline_after_colon = parts[1].strip()
            # Remove surrounding quotes if present
            headline_after_colon = headline_after_colon.strip("\"“”")

        date_str = date_match.group(1) if date_match else None
        headline = (
            quoted_headline.group(1)
            if quoted_headline
            else (headline_after_colon or _strip_md(header))
        )

        # Extract trading relevance line(s)
        rel_match = re.search(
            r"(?i)Trading\s+Relevance:\s*(.+)", block
        )
        relevance = rel_match.group(1).strip() if rel_match else ""

        sources = _extract_urls(block + " " + header)

        items.append(
            {
                "date": date_str,
                "headline": headline,
                "relevance": relevance,
                "sources": list(dict.fromkeys(sources)),
                "raw": header + "\n" + block,
            }
        )
    return items


def parse_stock_news(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parses company-specific news text from get_stock_news_openai into a list of items.
    Expected patterns include bold enumerated sections like:
      **1. Topic**
      Description ... (url)
    Returns a list of dicts with keys: title, summary, sources, raw.
    """
    if not raw_text or not isinstance(raw_text, str):
        return []

    items: List[Dict[str, Any]] = []

    # Find headings like **1. Something** or **1. Something** on its own line
    header_iter = list(
        re.finditer(r"(?m)^\s*\*\*\s*\d+\.\s*(.+?)\s*\*\*\s*$", raw_text)
    )

    if not header_iter:
        # Fallback: split by numbered lines even without bold
        header_iter = list(
            re.finditer(r"(?m)^\s*\d+\.\s+(.+?)\s*$", raw_text)
        )

    if header_iter:
        boundaries = []
        for m in header_iter:
            boundaries.append((m.start(), m.end(), m.group(1)))
        text_len = len(raw_text)
        for i, (s, e, header_text) in enumerate(boundaries):
            next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else text_len
            block = raw_text[e:next_start].strip()
            title = _strip_md(header_text)
            sources = _extract_urls(block + " " + title)
            summary = block.strip()
            items.append(
                {
                    "title": title,
                    "summary": summary,
                    "sources": list(dict.fromkeys(sources)),
                    "raw": f"{title}\n{summary}",
                }
            )
    else:
        # Last resort: try to split paragraphs; each paragraph with a URL is an item
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]
        for p in paragraphs:
            urls = _extract_urls(p)
            if urls or len(p) > 120:
                items.append(
                    {
                        "title": p.split("\n", 1)[0][:80],
                        "summary": p,
                        "sources": list(dict.fromkeys(urls)),
                        "raw": p,
                    }
                )

    return items


