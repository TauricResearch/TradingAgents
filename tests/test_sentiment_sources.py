"""Unit tests for the expanded sentiment analyst: Bluesky + Mastodon fetchers
and verification that all six data sources are wired into the prompt."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

import tradingagents.dataflows.bluesky as bluesky_mod
import tradingagents.dataflows.mastodon as mastodon_mod
from tradingagents.agents.analysts.sentiment_analyst import (
    _build_system_message,
    create_sentiment_analyst,
)


def _mock_urlopen(payload):
    """Return a context-manager mock whose read() yields json-encoded payload."""
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return cm


# ─── Bluesky fetcher ─────────────────────────────────────────────────────────


class TestBlueskyFetcher:
    @pytest.mark.unit
    def test_parses_posts(self):
        payload = {"posts": [{
            "author": {"handle": "trader.bsky.social"},
            "record": {"createdAt": "2026-05-28T10:00:00Z", "text": "Loading up on $NVDA"},
            "likeCount": 12, "repostCount": 3, "replyCount": 1,
        }]}
        with patch.object(bluesky_mod, "urlopen", return_value=_mock_urlopen(payload)):
            out = bluesky_mod.fetch_bluesky_posts("$NVDA")
        assert "trader.bsky.social" in out
        assert "Loading up on $NVDA" in out
        assert "12♥" in out

    @pytest.mark.unit
    def test_empty_results_placeholder(self):
        with patch.object(bluesky_mod, "urlopen", return_value=_mock_urlopen({"posts": []})):
            out = bluesky_mod.fetch_bluesky_posts("$ZZZZ")
        assert out.startswith("<no Bluesky posts found")

    @pytest.mark.unit
    def test_http_error_degrades_gracefully(self):
        err = HTTPError("url", 403, "Forbidden", {}, None)
        with patch.object(bluesky_mod, "urlopen", side_effect=err):
            out = bluesky_mod.fetch_bluesky_posts("$NVDA")
        assert out == "<bluesky unavailable: HTTPError>"


# ─── Mastodon fetcher ────────────────────────────────────────────────────────


class TestMastodonFetcher:
    @pytest.mark.unit
    def test_parses_posts_and_strips_html(self):
        payload = [{
            "account": {"acct": "fintwit@mastodon.social"},
            "created_at": "2026-05-28T10:00:00Z",
            "content": "<p>Bullish on <b>NVDA</b></p>",
            "favourites_count": 5, "reblogs_count": 2, "replies_count": 1,
        }]
        with patch.object(mastodon_mod, "urlopen", return_value=_mock_urlopen(payload)):
            out = mastodon_mod.fetch_mastodon_posts("NVDA")
        assert "fintwit@mastodon.social" in out
        assert "Bullish on NVDA" in out  # HTML tags stripped
        assert "<p>" not in out

    @pytest.mark.unit
    def test_empty_results_placeholder(self):
        with patch.object(mastodon_mod, "urlopen", return_value=_mock_urlopen([])):
            out = mastodon_mod.fetch_mastodon_posts("ZZZZ")
        assert out.startswith("<no Mastodon posts found")

    @pytest.mark.unit
    def test_invalid_tag_placeholder(self):
        out = mastodon_mod.fetch_mastodon_posts("$$$")
        assert out.startswith("<no Mastodon posts: invalid tag")

    @pytest.mark.unit
    def test_http_error_degrades_gracefully(self):
        err = HTTPError("url", 500, "err", {}, None)
        with patch.object(mastodon_mod, "urlopen", side_effect=err):
            out = mastodon_mod.fetch_mastodon_posts("NVDA")
        assert out == "<mastodon unavailable: HTTPError>"


# ─── Prompt wiring ───────────────────────────────────────────────────────────


class TestPromptWiring:
    @pytest.mark.unit
    def test_all_six_blocks_present(self):
        msg = _build_system_message(
            ticker="NVDA", start_date="2026-05-22", end_date="2026-05-29",
            news_block="NEWS_X", stocktwits_block="ST_X", reddit_block="RD_X",
            bluesky_block="BSKY_X", mastodon_block="MASTO_X", fear_greed_block="FG_X",
        )
        for tag in ("news", "stocktwits", "reddit", "bluesky", "mastodon", "fear_greed"):
            assert f"<start_of_{tag}>" in msg and f"<end_of_{tag}>" in msg
        for data in ("NEWS_X", "ST_X", "RD_X", "BSKY_X", "MASTO_X", "FG_X"):
            assert data in msg

    @pytest.mark.unit
    def test_breakdown_lists_new_sources(self):
        msg = _build_system_message(
            ticker="NVDA", start_date="2026-05-22", end_date="2026-05-29",
            news_block="", stocktwits_block="", reddit_block="",
        )
        assert "Bluesky" in msg and "Mastodon" in msg and "Fear & Greed" in msg


# ─── Node integration ────────────────────────────────────────────────────────


class TestSentimentNode:
    @pytest.mark.unit
    def test_node_injects_all_fetchers_into_prompt(self):
        from langchain_core.runnables import RunnableLambda

        captured = {}

        # A real Runnable so `prompt | llm` builds a valid sequence; it
        # records the fully-rendered prompt the LLM would receive.
        def _capture(prompt_value):
            captured["text"] = prompt_value.to_string()
            return MagicMock(content="report")

        fake_llm = RunnableLambda(_capture)

        with patch("tradingagents.agents.analysts.sentiment_analyst.get_news") as gn, \
             patch("tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages", return_value="ST_DATA"), \
             patch("tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts", return_value="RD_DATA"), \
             patch("tradingagents.agents.analysts.sentiment_analyst.fetch_bluesky_posts", return_value="BSKY_DATA") as fb, \
             patch("tradingagents.agents.analysts.sentiment_analyst.fetch_mastodon_posts", return_value="MASTO_DATA") as fm, \
             patch("tradingagents.agents.analysts.sentiment_analyst.get_fear_greed_index", return_value="FG_DATA") as fg:
            gn.func.return_value = "NEWS_DATA"

            node = create_sentiment_analyst(fake_llm)
            state = {
                "company_of_interest": "NVDA",
                "trade_date": "2026-05-29",
                "messages": [],
            }
            result = node(state)

        # Fetchers called with the expected ticker-derived args.
        fb.assert_called_once_with("$NVDA")
        fm.assert_called_once_with("NVDA")
        fg.assert_called_once()
        # Every source's data made it into the rendered prompt.
        for data in ("NEWS_DATA", "ST_DATA", "RD_DATA", "BSKY_DATA", "MASTO_DATA", "FG_DATA"):
            assert data in captured["text"]
        assert result["sentiment_report"] == "report"
