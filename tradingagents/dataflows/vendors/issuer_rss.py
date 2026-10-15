"""Configured official issuer RSS/Atom feeds for ticker-specific news."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.net import get_scrubbed

REQUEST_TIMEOUT = 20
MAX_FEED_BYTES = 5_000_000


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, *names: str) -> str:
    names = {name.lower() for name in names}
    for child in element.iter():
        if child is element:
            continue
        if _local_name(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _link(element: ET.Element) -> str:
    for child in element.iter():
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def _published_date(value: str) -> date | None:
    if not value:
        return None
    try:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_feed(xml_text: str) -> tuple[list[dict], int]:
    """Parse RSS 2.x, RDF/RSS 1.0, or Atom; return items and undated count."""
    if len(xml_text.encode("utf-8")) > MAX_FEED_BYTES:
        raise ValueError("feed exceeds the 5 MB safety limit")
    root = ET.fromstring(xml_text)
    items = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    parsed, undated = [], 0
    for node in items:
        title = _child_text(node, "title")
        link = _link(node)
        raw_date = _child_text(node, "pubdate", "published", "updated", "date")
        published = _published_date(raw_date)
        if not published:
            undated += 1
            continue
        description = _child_text(node, "description", "summary", "content")
        description = re.sub(r"\s+", " ", description).strip()
        if len(description) > 800:
            description = description[:797].rstrip() + "..."
        parsed.append({
            "title": title or "(untitled issuer release)",
            "link": link,
            "date": published.isoformat(),
            "description": description,
        })
    return parsed, undated


def _load_instrument(ticker: str) -> dict:
    path = Path(get_config().get("issuer_registry_path", "~/.tradingagents/german_equities.json")).expanduser()
    if not path.is_file():
        raise VendorNotConfiguredError(f"issuer registry not found: {path}")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VendorUnavailableError(f"could not read issuer registry {path}: {exc}") from None
    instruments = registry.get("instruments", {}) if isinstance(registry, dict) else {}
    if not isinstance(instruments, dict):
        raise VendorUnavailableError("issuer registry 'instruments' must be a JSON object")
    wanted = ticker.strip().upper()
    for key, record in instruments.items():
        if not isinstance(record, dict):
            continue
        aliases = record.get("aliases", [])
        candidates = [
            key,
            record.get("ticker"),
            record.get("isin"),
            record.get("wkn"),
            record.get("yahoo_symbol"),
            record.get("alpha_vantage_symbol"),
            *(aliases if isinstance(aliases, list) else []),
        ]
        if any(str(candidate).strip().upper() == wanted for candidate in candidates):
            feed_url = record.get("news_feed_url")
            if feed_url and (urlparse(feed_url).scheme != "https" or not urlparse(feed_url).hostname):
                raise VendorNotConfiguredError(f"issuer feed URL for {ticker} must use HTTPS")
            return {**record, "ticker": key, "news_feed_url": feed_url}
    raise VendorNotConfiguredError(f"no issuer identity/feed configured for {ticker}")


def get_news_issuer_rss(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve date-bounded headlines from a configured issuer-controlled feed.

    An empty result is explicitly described as no matches in this one configured
    feed, never as evidence that the issuer published no news elsewhere.
    """
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    instrument = _load_instrument(ticker)
    if not instrument.get("news_feed_url"):
        raise VendorNotConfiguredError(f"no official RSS/Atom URL configured for {ticker}")
    try:
        response = get_scrubbed(
            instrument["news_feed_url"],
            params={},
            timeout=REQUEST_TIMEOUT,
            secret="",
        )
        items, undated = parse_feed(response.text)
    except VendorUnavailableError:
        raise
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"official feed request failed: {exc}") from None
    except (ET.ParseError, ValueError, TypeError) as exc:
        raise VendorUnavailableError(f"official feed is invalid: {exc}") from None

    matched = [item for item in items if start.isoformat() <= item["date"] <= end.isoformat()]
    matched.sort(key=lambda item: (item["date"], item["title"]), reverse=True)
    limit = max(1, int(get_config().get("news_article_limit", 20)))
    identity = " | ".join(
        f"{label}: {instrument[key]}"
        for key, label in (("isin", "ISIN"), ("mic", "Listing MIC"), ("currency", "Currency"))
        if instrument.get(key)
    )
    header = [
        f"## Official issuer feed: {instrument.get('issuer', ticker)} ({ticker})",
        f"- Source: issuer-configured RSS/Atom feed — {instrument['news_feed_url']}",
        f"- Instrument identity: {identity or 'not recorded'}",
        f"- Feed item window: {start} to {end}",
    ]
    if not matched:
        header.append("- Result: no dated items matched in this configured feed; this is not proof that no issuer news exists elsewhere.")
    if undated:
        header.append(f"- Omitted {undated} feed item(s) without a parseable publication date.")
    lines = header + [""]
    for item in matched[:limit]:
        lines.append(f"### {item['date']} — {item['title']}")
        if item["link"]:
            lines.append(f"- URL: {item['link']}")
        if item["description"]:
            lines.append(item["description"])
        lines.append("")
    if len(matched) > limit:
        lines.append(f"_(showing {limit} of {len(matched)} matching feed items)_")
    return "\n".join(lines).strip()
