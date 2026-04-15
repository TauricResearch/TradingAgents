"""Notion publisher for TradingAgents analysis reports.

Publishes a completed analysis as a structured Notion page.
Requires NOTION_API_KEY and NOTION_PARENT_PAGE_ID in the environment.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

_NOTION_API_VERSION = "2022-06-28"
_NOTION_BASE = "https://api.notion.com/v1"
_MAX_BLOCK_TEXT = 1900  # Notion rich_text limit is 2000; stay under it


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _NOTION_API_VERSION,
        "Content-Type": "application/json",
    }


def _chunks(text: str, size: int = _MAX_BLOCK_TEXT) -> list[str]:
    """Split text into chunks that fit within Notion's rich_text size limit."""
    return [text[i : i + size] for i in range(0, len(text), size)]


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _heading2(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _heading3(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _divider() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _text_to_blocks(text: str) -> list[dict[str, Any]]:
    """Convert a potentially long text string into a list of paragraph blocks."""
    blocks: list[dict[str, Any]] = []
    for chunk in _chunks(text.strip()):
        if chunk.strip():
            blocks.append(_paragraph(chunk))
    return blocks


# ---------------------------------------------------------------------------
# Report → blocks
# ---------------------------------------------------------------------------

def _build_blocks(final_state: dict, ticker: str, analysis_date: str) -> list[dict[str, Any]]:
    """Convert the full agent state into a flat list of Notion blocks."""
    blocks: list[dict[str, Any]] = []

    def section(title: str, parts: list[tuple[str, str]]) -> None:
        if not parts:
            return
        blocks.append(_heading2(title))
        for agent_name, content in parts:
            if content and content.strip():
                blocks.append(_heading3(agent_name))
                blocks.extend(_text_to_blocks(content))
        blocks.append(_divider())

    # I. Analyst Team
    analysts: list[tuple[str, str]] = []
    if final_state.get("market_report"):
        analysts.append(("Market Analyst", final_state["market_report"]))
    if final_state.get("sentiment_report"):
        analysts.append(("Social Analyst", final_state["sentiment_report"]))
    if final_state.get("news_report"):
        analysts.append(("News Analyst", final_state["news_report"]))
    if final_state.get("fundamentals_report"):
        analysts.append(("Fundamentals Analyst", final_state["fundamentals_report"]))
    section("I. Analyst Team Reports", analysts)

    # II. Research Team
    research: list[tuple[str, str]] = []
    debate = final_state.get("investment_debate_state", {})
    if debate.get("bull_history"):
        research.append(("Bull Researcher", debate["bull_history"]))
    if debate.get("bear_history"):
        research.append(("Bear Researcher", debate["bear_history"]))
    if debate.get("judge_decision"):
        research.append(("Research Manager", debate["judge_decision"]))
    section("II. Research Team Decision", research)

    # III. Trading Team
    if final_state.get("trader_investment_plan"):
        section("III. Trading Team Plan", [("Trader", final_state["trader_investment_plan"])])

    # IV. Risk Management
    risk_parts: list[tuple[str, str]] = []
    risk = final_state.get("risk_debate_state", {})
    if risk.get("aggressive_history"):
        risk_parts.append(("Aggressive Analyst", risk["aggressive_history"]))
    if risk.get("conservative_history"):
        risk_parts.append(("Conservative Analyst", risk["conservative_history"]))
    if risk.get("neutral_history"):
        risk_parts.append(("Neutral Analyst", risk["neutral_history"]))
    section("IV. Risk Management Team", risk_parts)

    # V. Portfolio Manager
    if risk.get("judge_decision"):
        section("V. Portfolio Manager Decision", [("Portfolio Manager", risk["judge_decision"])])

    # VI. Investment Plan (consolidated plan produced by the trader after risk review)
    if final_state.get("investment_plan"):
        section("VI. Investment Plan", [("Investment Plan", final_state["investment_plan"])])

    # VII. Final Trade Decision
    if final_state.get("final_trade_decision"):
        section(
            "VII. Final Trade Decision",
            [("Final Decision", final_state["final_trade_decision"])],
        )

    return blocks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _append_blocks(page_id: str, blocks: list[dict], api_key: str) -> None:
    """Append blocks to a Notion page, sending at most 100 per request."""
    url = f"{_NOTION_BASE}/blocks/{page_id}/children"
    # Notion accepts max 100 blocks per PATCH request
    for i in range(0, len(blocks), 100):
        batch = blocks[i : i + 100]
        resp = requests.patch(url, json={"children": batch}, headers=_headers(api_key), timeout=30)
        if not resp.ok:
            raise RuntimeError(f"Notion API error {resp.status_code}: {resp.text}")


def publish_to_notion(
    final_state: dict,
    ticker: str,
    analysis_date: str,
) -> str:
    """Create a Notion page with all analysis reports and return its URL.

    Reads NOTION_API_KEY and NOTION_PARENT_PAGE_ID from the environment.

    Raises:
        EnvironmentError: If the required environment variables are not set.
        RuntimeError: If the Notion API returns an error.
    """
    api_key = os.environ.get("NOTION_API_KEY", "").strip()
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID", "").strip()

    if not api_key:
        raise EnvironmentError(
            "NOTION_API_KEY is not set. Add it to your .env file."
        )
    if not parent_page_id:
        raise EnvironmentError(
            "NOTION_PARENT_PAGE_ID is not set. Add it to your .env file.\n"
            "Open the target Notion page, click Share → Copy link, and paste the 32-char ID."
        )

    title = f"Trading Analysis: {ticker.upper()} — {analysis_date}"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create the page (empty body first — blocks appended separately to avoid 100-block limit)
    create_payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title}}]
            }
        },
        "children": [
            _paragraph(f"Generated: {generated_at}"),
            _divider(),
        ],
    }

    resp = requests.post(
        f"{_NOTION_BASE}/pages",
        json=create_payload,
        headers=_headers(api_key),
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Failed to create Notion page {resp.status_code}: {resp.text}")

    page = resp.json()
    page_id = page["id"]
    page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

    # Append all report blocks
    blocks = _build_blocks(final_state, ticker, analysis_date)
    if blocks:
        _append_blocks(page_id, blocks, api_key)

    logger.info("Published to Notion: %s", page_url)
    return page_url
