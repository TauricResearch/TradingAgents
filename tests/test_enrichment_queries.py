"""Tests for market-aware enrichment query generation."""

import pytest

from tradingagents.dataflows.evidence import _build_enrichment_queries


class TestBuildEnrichmentQueries:
    def test_a_share_uses_chinese_templates(self):
        profile = {
            "ticker": "002396.SZ",
            "name": "星网锐捷",
            "full_name": "福建星网锐捷通讯股份有限公司",
            "industry": "通信设备",
        }
        queries = _build_enrichment_queries(profile)

        assert len(queries) == 3
        # First query: Chinese news/announcement terms
        assert "公告" in queries[0]["query"]
        assert "舆情" in queries[0]["query"]
        # Second query: A-share official domains
        assert "巨潮资讯" in queries[1]["query"]
        assert "cninfo.com.cn" in queries[1]["include_domains"]
        assert "szse.cn" in queries[1]["include_domains"]
        # Third query: Chinese industry terms
        assert "行业" in queries[2]["query"]

    def test_us_stock_uses_english_templates(self):
        profile = {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "full_name": "Apple Inc.",
            "industry": "Consumer Electronics",
        }
        queries = _build_enrichment_queries(profile)

        assert len(queries) == 3
        # First query: English news terms
        assert "earnings" in queries[0]["query"]
        assert "press release" in queries[0]["query"]
        assert queries[0]["include_domains"] == []
        # Second query: SEC/IR domains
        assert "sec.gov" in queries[1]["include_domains"]
        assert "prnewswire.com" in queries[1]["include_domains"]
        # Third query: English industry terms
        assert "industry" in queries[2]["query"]
        assert "市场" not in queries[2]["query"]

    def test_hk_stock_uses_english_templates(self):
        profile = {
            "ticker": "0700.HK",
            "name": "Tencent Holdings",
            "full_name": "Tencent Holdings Limited",
            "industry": "Internet Services",
        }
        queries = _build_enrichment_queries(profile)

        # HK stocks are not A-share → English templates
        assert "earnings" in queries[0]["query"]
        assert "sec.gov" in queries[1]["include_domains"] or "prnewswire.com" in queries[1]["include_domains"]

    def test_empty_ticker_returns_queries(self):
        profile = {"name": "Some Company", "industry": "Tech"}
        queries = _build_enrichment_queries(profile)
        assert len(queries) == 3

    def test_queries_respect_profile_fields(self):
        profile = {
            "ticker": "MSFT",
            "name": "Microsoft",
            "full_name": "Microsoft Corporation",
            "industry": "Software",
        }
        queries = _build_enrichment_queries(profile)

        assert "MSFT" in queries[0]["query"]
        assert "Microsoft Corporation" in queries[1]["query"]
        assert "Software" in queries[2]["query"]
