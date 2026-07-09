"""Tests for the LLM-based news coverage advisor."""

import json

import pytest

from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.news_advisor import (
    NewsAdvisorResult,
    _analyze_via_rules,
    _parse_advisor_response,
    analyze_news_coverage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeAdvisorLLM:
    """Mock LLM that returns a pre-configured advisor response."""

    def __init__(self, result: dict):
        self._result = result
        self.last_prompt: str | None = None

    def invoke(self, prompt: str):
        self.last_prompt = prompt
        return type("Resp", (), {"content": json.dumps(self._result)})()


def _profile(**overrides) -> dict:
    base = {
        "ticker": "AAPL",
        "name": "Apple",
        "full_name": "Apple Inc.",
        "industry": "Consumer Electronics",
    }
    base.update(overrides)
    return base


def _items(*titles: str) -> list[dict]:
    return [{"title": t, "source": "tavily", "url": f"https://example.com/{i}"}
            for i, t in enumerate(titles)]


# ---------------------------------------------------------------------------
# LLM-based analysis
# ---------------------------------------------------------------------------


class TestAnalyzeViaLLM:
    def test_should_enrich_when_gaps_identified(self):
        items = _items("Apple launches new iPhone model")
        llm = FakeAdvisorLLM({
            "should_enrich": True,
            "gaps": ["missing earnings/financial news"],
            "reasoning": "No earnings coverage for a company that just reported.",
            "queries": [
                {"query": "AAPL Apple earnings Q1 2026", "include_domains": [], "include_raw_content": False}
            ],
        })

        result = analyze_news_coverage(items, _profile(), llm)

        assert result.should_enrich is True
        assert len(result.queries) == 1
        assert "earnings" in result.queries[0]["query"]
        assert "earnings" in result.gaps[0]

    def test_no_enrichment_when_coverage_adequate(self):
        items = _items(
            "Apple Q1 earnings beat expectations",
            "Apple revenue grows 10%",
            "Apple announces new product",
        )
        llm = FakeAdvisorLLM({
            "should_enrich": False,
            "gaps": [],
            "reasoning": "Coverage is adequate across all dimensions.",
            "queries": [],
        })

        result = analyze_news_coverage(items, _profile(), llm)

        assert result.should_enrich is False
        assert result.queries == []

    def test_queries_limited_to_three(self):
        items = _items("Some news")
        llm = FakeAdvisorLLM({
            "should_enrich": True,
            "gaps": ["gap1", "gap2", "gap3", "gap4"],
            "reasoning": "Multiple gaps.",
            "queries": [
                {"query": f"query {i}", "include_domains": [], "include_raw_content": False}
                for i in range(5)
            ],
        })

        result = analyze_news_coverage(items, _profile(), llm)

        assert len(result.queries) <= 3

    def test_llm_receives_company_info_in_prompt(self):
        items = _items("Some headline")
        llm = FakeAdvisorLLM({
            "should_enrich": False, "gaps": [], "reasoning": "ok", "queries": [],
        })

        analyze_news_coverage(items, _profile(ticker="MSFT", name="Microsoft"), llm)

        assert "MSFT" in llm.last_prompt
        assert "Microsoft" in llm.last_prompt


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------


class TestParseAdvisorResponse:
    def test_valid_json(self):
        text = json.dumps({
            "should_enrich": True,
            "gaps": ["missing earnings"],
            "reasoning": "Need more data.",
            "queries": [{"query": "AAPL earnings", "include_domains": [], "include_raw_content": False}],
        })
        result = _parse_advisor_response(text)

        assert result.should_enrich is True
        assert len(result.queries) == 1

    def test_json_in_markdown_fences(self):
        inner = json.dumps({
            "should_enrich": False, "gaps": [], "reasoning": "ok", "queries": [],
        })
        text = f"```json\n{inner}\n```"
        result = _parse_advisor_response(text)

        assert result.should_enrich is False

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="No JSON"):
            _parse_advisor_response("not json at all")

    def test_empty_queries_filtered(self):
        text = json.dumps({
            "should_enrich": True,
            "gaps": ["gap"],
            "reasoning": "reason",
            "queries": [
                {"query": "", "include_domains": []},
                {"query": "valid query", "include_domains": ["sec.gov"]},
                {"query": "x" * 400, "include_domains": []},  # truncated to 380
            ],
        })
        result = _parse_advisor_response(text)

        assert len(result.queries) == 2
        assert result.queries[0]["query"] == "valid query"
        assert len(result.queries[1]["query"]) <= 380


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------


class TestAnalyzeViaRules:
    def test_empty_items_should_enrich(self):
        result = _analyze_via_rules([], _profile())

        assert result.should_enrich is True
        assert "no news" in result.reasoning.lower()

    def test_adequate_coverage_no_enrichment(self):
        items = _items(
            "Apple earnings beat expectations Q1 revenue growth",
            "Apple filing disclosure announcement SEC",
            "Apple industry market competition outlook",
        )
        result = _analyze_via_rules(items, _profile())

        assert result.should_enrich is False

    def test_missing_earnings_triggers_enrichment(self):
        items = _items(
            "Apple launches new iPhone accessories",
            "Apple market share grows in Europe",
        )
        result = _analyze_via_rules(items, _profile())

        assert result.should_enrich is True
        assert any("earnings" in g for g in result.gaps)

    def test_a_share_queries_use_chinese(self):
        items = _items("星网锐捷发布新产品")
        result = _analyze_via_rules(items, _profile(ticker="002396.SZ", name="星网锐捷"))

        if result.should_enrich:
            assert any("公告" in q["query"] for q in result.queries)


# ---------------------------------------------------------------------------
# Integration: analyze_news_coverage
# ---------------------------------------------------------------------------


class TestAnalyzeNewsCoverage:
    def teardown_method(self):
        set_config({"news_advisor_enabled": True})

    def test_disabled_by_config(self):
        set_config({"news_advisor_enabled": False})
        result = analyze_news_coverage([], _profile(), llm=None)

        assert result.should_enrich is False
        assert "disabled" in result.reasoning.lower()

    def test_falls_back_to_rules_when_no_llm(self):
        items = _items("Some random news without earnings")
        result = analyze_news_coverage(items, _profile(), llm=None)

        # Should fall back to rule-based analysis
        assert isinstance(result, NewsAdvisorResult)
