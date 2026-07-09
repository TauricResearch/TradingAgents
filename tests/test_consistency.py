"""Tests for cross-source news consistency detection."""

import json

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.consistency import (
    attach_cross_source_info,
    cluster_news_by_event,
    cross_source_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeLLMResponse:
    """Mimics a LangChain LLM response with .content attribute."""

    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """A mock LLM that returns a pre-configured clustering result."""

    def __init__(self, clusters: list[list[int]]):
        self._clusters = clusters
        self.last_prompt: str | None = None

    def invoke(self, prompt: str):
        self.last_prompt = prompt
        return FakeLLMResponse(json.dumps(self._clusters))


def _items(*specs: tuple[str, str]) -> list[dict]:
    """Create minimal news items: (source, title)."""
    return [{"source": src, "title": title, "url": f"https://{src}.example.com/{i}"}
            for i, (src, title) in enumerate(specs)]


# ---------------------------------------------------------------------------
# LLM clustering
# ---------------------------------------------------------------------------


class TestClusterViaLLM:
    def test_same_event_clustered_together(self):
        items = _items(
            ("tavily", "Apple Q1 earnings beat expectations"),
            ("yfinance", "Apple Reports Strong Q1 Results"),
            ("alpha_vantage", "Fed holds rates steady"),
        )
        llm = FakeLLM([[0, 1], [2]])

        clusters = cluster_news_by_event(items, llm)

        assert clusters == [[0, 1], [2]]

    def test_all_different_events(self):
        items = _items(
            ("tavily", "Apple launches new iPhone"),
            ("yfinance", "Tesla stock drops 5%"),
            ("alpha_vantage", "Fed raises rates"),
        )
        llm = FakeLLM([[0], [1], [2]])

        clusters = cluster_news_by_event(items, llm)

        assert clusters == [[0], [1], [2]]

    def test_llm_returns_incomplete_clusters_missing_indices_added(self):
        items = _items(
            ("tavily", "Title A"),
            ("yfinance", "Title B"),
            ("alpha_vantage", "Title C"),
        )
        # LLM forgets index 2
        llm = FakeLLM([[0, 1]])

        clusters = cluster_news_by_event(items, llm)

        # Index 2 should be added as singleton
        assert [2] in clusters
        assert sorted(c for cluster in clusters for c in cluster) == [0, 1, 2]

    def test_llm_returns_invalid_json_falls_back_to_ngram(self):
        items = _items(
            ("tavily", "Apple earnings beat expectations"),
            ("yfinance", "Apple earnings beat expectations"),
        )

        class BrokenLLM:
            def invoke(self, prompt):
                return FakeLLMResponse("not valid json at all")

        clusters = cluster_news_by_event(items, BrokenLLM())

        # Should fall back to n-gram and cluster similar titles together
        assert len(clusters) == 1
        assert sorted(clusters[0]) == [0, 1]


# ---------------------------------------------------------------------------
# n-gram fallback
# ---------------------------------------------------------------------------


class TestClusterNgram:
    def test_identical_titles_clustered(self):
        items = _items(
            ("tavily", "Apple Q1 earnings beat expectations"),
            ("yfinance", "Apple Q1 earnings beat expectations"),
        )

        clusters = cluster_news_by_event(items, llm=None)

        assert len(clusters) == 1
        assert sorted(clusters[0]) == [0, 1]

    def test_very_different_titles_separate(self):
        items = _items(
            ("tavily", "Apple launches new iPhone model"),
            ("yfinance", "Federal Reserve raises interest rates"),
        )

        clusters = cluster_news_by_event(items, llm=None)

        assert len(clusters) == 2

    def test_chinese_titles_with_similarity(self):
        items = _items(
            ("tavily", "星网锐捷出售德明通讯股权进展公告"),
            ("yfinance", "星网锐捷出售德明通讯股权最新进展"),
        )

        clusters = cluster_news_by_event(items, llm=None)

        # Should cluster together due to shared n-grams
        assert len(clusters) == 1

    def test_single_item_returns_singleton(self):
        items = _items(("tavily", "Only one item"))

        clusters = cluster_news_by_event(items, llm=None)

        assert clusters == [[0]]

    def test_empty_list(self):
        clusters = cluster_news_by_event([], llm=None)

        assert clusters == []

    def test_same_source_items_not_force_clustered(self):
        """Items from the same source should still cluster if titles are similar,
        but we verify they aren't artificially merged."""
        items = _items(
            ("tavily", "Apple launches new iPhone"),
            ("tavily", "Fed raises interest rates"),
        )

        clusters = cluster_news_by_event(items, llm=None)

        # Very different titles, even from same source → separate clusters
        assert len(clusters) == 2


# ---------------------------------------------------------------------------
# attach_cross_source_info
# ---------------------------------------------------------------------------


class TestAttachCrossSourceInfo:
    def test_multi_source_items_marked_confirmed(self):
        items = _items(
            ("tavily", "Apple Q1 earnings beat expectations"),
            ("yfinance", "Apple Q1 earnings beat expectations"),
            ("alpha_vantage", "Fed holds rates steady"),
        )
        llm = FakeLLM([[0, 1], [2]])

        attach_cross_source_info(items, llm)

        assert items[0]["cross_source_tag"] == "confirmed"
        assert items[1]["cross_source_tag"] == "confirmed"
        assert items[2]["cross_source_tag"] == "single_source"
        assert items[0]["cross_source_count"] == 2
        assert items[2]["cross_source_count"] == 1

    def test_vendors_listed_correctly(self):
        items = _items(
            ("tavily", "Same event"),
            ("yfinance", "Same event"),
        )
        llm = FakeLLM([[0, 1]])

        attach_cross_source_info(items, llm)

        assert items[0]["cross_source_vendors"] == ["tavily", "yfinance"]
        assert items[1]["cross_source_vendors"] == ["tavily", "yfinance"]

    def test_empty_list(self):
        result = attach_cross_source_info([], llm=None)
        assert result == []

    def test_disabled_by_config(self):
        set_config({"consistency_enabled": False})
        items = _items(
            ("tavily", "Title A"),
            ("yfinance", "Title A"),
        )

        attach_cross_source_info(items, llm=None)

        assert "cross_source_tag" not in items[0]
        set_config({"consistency_enabled": True})

    def test_returns_same_list(self):
        items = _items(("tavily", "Only one"))
        result = attach_cross_source_info(items, llm=None)
        assert result is items


# ---------------------------------------------------------------------------
# cross_source_summary
# ---------------------------------------------------------------------------


class TestCrossSourceSummary:
    def test_counts_correctly(self):
        items = [
            {"cross_source_tag": "confirmed"},
            {"cross_source_tag": "confirmed"},
            {"cross_source_tag": "single_source"},
        ]
        summary = cross_source_summary(items)
        assert summary == {"confirmed": 2, "single_source": 1}

    def test_empty_list(self):
        assert cross_source_summary([]) == {"confirmed": 0, "single_source": 0}


# ---------------------------------------------------------------------------
# Integration: _format_curated_news includes cross-source markers
# ---------------------------------------------------------------------------


class TestFormatCuratedNewsIntegration:
    def test_format_includes_cross_source_when_multiple_sources(self, monkeypatch):
        from tradingagents.dataflows import interface

        monkeypatch.setattr(
            interface,
            "get_vendor",
            lambda category, method=None: "tavily,yfinance",
        )
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {
                "tavily": lambda *args, **kwargs: {
                    "source": "tavily",
                    "items": [
                        {
                            "title": "Apple Q1 earnings beat expectations",
                            "url": "https://reuters.com/apple-q1",
                            "content": "Tavily summary.",
                            "source": "tavily",
                        }
                    ],
                },
                "yfinance": lambda *args, **kwargs: (
                    "### Apple Q1 earnings beat expectations (source: Yahoo Finance)\n"
                    "Duplicate summary.\n"
                    "Link: https://finance.yahoo.com/apple-q1\n"
                ),
            },
        )
        # Mock LLM creation to avoid real API calls
        monkeypatch.setattr(
            "tradingagents.dataflows.consistency.create_llm_from_config",
            lambda: None,
        )
        set_config({"news_curator_max_items": 10, "consistency_enabled": True})

        result = interface.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-31")

        assert "Cross-source:" in result
        assert "confirmed" in result

    def test_format_skips_cross_source_when_single_source(self, monkeypatch):
        from tradingagents.dataflows import interface

        # Clear news cache to avoid stale results from previous test
        interface._news_result_cache.clear()

        monkeypatch.setattr(
            interface,
            "get_vendor",
            lambda category, method=None: "tavily",
        )
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {
                "tavily": lambda *args, **kwargs: {
                    "source": "tavily",
                    "items": [
                        {
                            "title": "Apple Q1 earnings",
                            "url": "https://reuters.com/apple-q1",
                            "content": "Summary.",
                            "source": "tavily",
                        }
                    ],
                },
            },
        )
        monkeypatch.setattr(
            "tradingagents.dataflows.consistency.create_llm_from_config",
            lambda: None,
        )
        set_config({"news_curator_max_items": 10, "consistency_enabled": True})

        result = interface.route_to_vendor("get_news", "AAPL", "2026-01-01", "2026-01-31")

        # With only 1 source, cross-source detection is skipped
        assert "Cross-source: 0 confirmed" in result
