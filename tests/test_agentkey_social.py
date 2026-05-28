"""Tests for AgentKey-backed social channels in the sentiment analyst.

Parsing fixtures mirror the real (observed) upstream response shapes:
  * Weibo: data.items[] mixing card containers and status dicts (text + user)
  * Zhihu: data.data[] of {object: {type, title, excerpt(html), author, counts}}

Network is never hit: dispatch is monkeypatched. Behavioral contracts under test
are the same as the existing fetchers — a formatted string always, a placeholder
on failure, and zero output when AgentKey is unconfigured.
"""

import unittest
from unittest.mock import patch

from tradingagents.dataflows import agentkey_client, agentkey_social
from tradingagents.dataflows.agentkey_client import AgentKeyError
from tradingagents.dataflows.agentkey_social import (
    build_agentkey_social_section,
    fetch_weibo_posts,
    fetch_zhihu_discussions,
    is_consumer_brand,
    normalize_search_name,
    select_channels,
)

_WEIBO_PAYLOAD = {
    "code": 1,
    "data": {
        "items": [
            {"category": "feed", "type": "card", "items": [], "itemId": "x", "style": 1},
            {
                "category": "status",
                "data": {
                    "text": "贵州茅台，腾讯控股两大老登今日继续新低 ​",
                    "user": {"screen_name": "股海老王"},
                    "created_at": "Wed May 28 09:00:00 +0800 2026",
                    "region_name": "发布于 北京",
                    "attitudes_count": 42,
                    "comments_count": 7,
                    "reposts_count": 3,
                },
            },
        ]
    },
}

_ZHIHU_PAYLOAD = {
    "code": 0,
    "data": {
        "data": [
            {"object": {"type": "hot_timing", "title": "热榜"}},  # non-content card, skipped
            {
                "object": {
                    "type": "answer",
                    "title": "茅台一季度营收增长 6.5%，为何明星基金减仓？",
                    "excerpt": "<p>单看一季度营收增长6.5%</p>",
                    "author": {"name": "jian mi"},
                    "voteup_count": 27,
                    "comment_count": 28,
                    "created_time": 1777356615,
                }
            },
        ]
    },
}


class ChannelSelectionTests(unittest.TestCase):
    def test_base_channels_always_present(self):
        self.assertEqual(select_channels("Technology", "Software—Infrastructure"), ["weibo", "zhihu"])

    def test_consumer_sector_adds_consumer_channels(self):
        channels = select_channels("Consumer Defensive", "Beverages—Wineries & Distilleries")
        self.assertEqual(channels, ["weibo", "zhihu", "xiaohongshu", "douyin"])

    def test_consumer_electronics_detected_despite_tech_sector(self):
        # Apple: sector "Technology" but industry "Consumer Electronics" → consumer brand.
        self.assertTrue(is_consumer_brand("Technology", "Consumer Electronics"))

    def test_industrial_is_not_consumer(self):
        self.assertFalse(is_consumer_brand("Industrials", "Aerospace & Defense"))

    def test_missing_sector_industry_is_not_consumer(self):
        self.assertFalse(is_consumer_brand("", ""))


class SearchNameTests(unittest.TestCase):
    def test_strips_common_corporate_suffixes(self):
        self.assertEqual(normalize_search_name("Tencent Holdings Limited"), "Tencent")
        self.assertEqual(normalize_search_name("NVIDIA Corporation"), "NVIDIA")
        self.assertEqual(normalize_search_name("Apple Inc."), "Apple")
        self.assertEqual(normalize_search_name("Kweichow Moutai Co., Ltd."), "Kweichow Moutai")

    def test_strips_trailing_share_class(self):
        self.assertEqual(normalize_search_name("Alphabet Inc. Class C"), "Alphabet")

    def test_preserves_multiword_core_name(self):
        self.assertEqual(normalize_search_name("China Petroleum & Chemical Corporation"), "China Petroleum & Chemical")

    def test_never_collapses_to_empty(self):
        # The loop keeps the last token, so an all-suffix name never empties.
        self.assertTrue(normalize_search_name("Holdings Group"))

    def test_handles_empty(self):
        self.assertEqual(normalize_search_name(""), "")


class HelperTests(unittest.TestCase):
    def test_unix_to_date_seconds(self):
        self.assertEqual(agentkey_social._unix_to_date(1777356615), "2026-04-28")

    def test_unix_to_date_milliseconds(self):
        # 13-digit ms timestamp normalizes to the same date as its seconds form.
        self.assertEqual(agentkey_social._unix_to_date(1777356615000), "2026-04-28")

    def test_unix_to_date_passthrough_on_garbage(self):
        self.assertEqual(agentkey_social._unix_to_date("not-a-ts"), "not-a-ts")


class WeiboParsingTests(unittest.TestCase):
    def test_extracts_status_skips_containers(self):
        with patch.object(agentkey_social, "dispatch", return_value=_WEIBO_PAYLOAD):
            out = fetch_weibo_posts("贵州茅台")
        self.assertIn("股海老王", out)
        self.assertIn("两大老登", out)
        self.assertIn("like 42", out)
        self.assertIn("comment 7", out)
        self.assertTrue(out.startswith("1 most-relevant Weibo posts"))

    def test_empty_results_placeholder(self):
        with patch.object(agentkey_social, "dispatch", return_value={"data": {"items": []}}):
            out = fetch_weibo_posts("NoSuchCo")
        self.assertEqual(out, "<no Weibo posts found for 'NoSuchCo'>")

    def test_failure_degrades_to_placeholder(self):
        with patch.object(agentkey_social, "dispatch", side_effect=AgentKeyError("HTTP 500 for weibo")):
            out = fetch_weibo_posts("贵州茅台")
        self.assertEqual(out, "<weibo unavailable: HTTP 500 for weibo>")


class ZhihuParsingTests(unittest.TestCase):
    def test_extracts_answers_strips_html_and_skips_cards(self):
        with patch.object(agentkey_social, "dispatch", return_value=_ZHIHU_PAYLOAD):
            out = fetch_zhihu_discussions("贵州茅台")
        self.assertIn("jian mi", out)
        self.assertIn("营收增长 6.5%", out)
        self.assertNotIn("<p>", out)  # html stripped
        self.assertIn("upvote 27", out)
        self.assertIn("2026-04", out)  # created_time rendered as date
        self.assertNotIn("热榜", out)  # hot_timing card skipped

    def test_failure_degrades_to_placeholder(self):
        with patch.object(agentkey_social, "dispatch", side_effect=AgentKeyError("network error")):
            out = fetch_zhihu_discussions("贵州茅台")
        self.assertEqual(out, "<zhihu unavailable: network error>")


class SectionAssemblyTests(unittest.TestCase):
    def test_unconfigured_returns_empty(self):
        with patch.object(agentkey_social, "is_configured", return_value=False):
            self.assertEqual(
                build_agentkey_social_section("AAPL", "Apple Inc.", "Technology", "Consumer Electronics"), ""
            )

    def test_fetcher_exception_does_not_crash_section(self):
        # An unexpected (non-AgentKeyError) failure in one channel must degrade to
        # a placeholder, not propagate and crash the sentiment node.
        def boom(_query):
            raise TypeError("upstream shape changed")

        with patch.object(agentkey_social, "is_configured", return_value=True), patch.dict(
            agentkey_social._FETCHERS, {"weibo": boom, "zhihu": lambda q: "ok"}
        ):
            section = build_agentkey_social_section("AAPL", "Apple Inc.", "Technology", "Software")
        self.assertIn("<weibo unavailable: unexpected error>", section)
        self.assertIn("<start_of_zhihu>\nok", section)

    def test_unconfigured_makes_no_network_call(self):
        # AgentKey is opt-in: with no key, the section must short-circuit BEFORE
        # touching the network, so an unconfigured install runs fully unaffected.
        with patch.object(agentkey_social, "is_configured", return_value=False), patch.object(
            agentkey_social, "dispatch", side_effect=AssertionError("dispatch must not be called")
        ), patch.object(
            agentkey_social, "search", side_effect=AssertionError("search must not be called")
        ):
            self.assertEqual(build_agentkey_social_section("0700.HK", "Tencent Holdings Limited"), "")

    def test_configured_consumer_includes_all_four_blocks(self):
        with patch.object(agentkey_social, "is_configured", return_value=True), patch.object(
            agentkey_social, "dispatch", side_effect=AgentKeyError("upstream down")
        ):
            section = build_agentkey_social_section("AAPL", "Apple Inc.", "Technology", "Consumer Electronics")
        for channel in ("weibo", "zhihu", "xiaohongshu", "douyin"):
            self.assertIn(f"<start_of_{channel}>", section)
            self.assertIn(f"<end_of_{channel}>", section)

    def test_configured_non_consumer_only_base_blocks(self):
        with patch.object(agentkey_social, "is_configured", return_value=True), patch.object(
            agentkey_social, "dispatch", side_effect=AgentKeyError("upstream down")
        ):
            section = build_agentkey_social_section("BA", "Boeing Company", "Industrials", "Aerospace & Defense")
        self.assertIn("<start_of_weibo>", section)
        self.assertIn("<start_of_zhihu>", section)
        self.assertNotIn("<start_of_xiaohongshu>", section)
        self.assertNotIn("<start_of_douyin>", section)


class CnNameResolutionTests(unittest.TestCase):
    def setUp(self):
        agentkey_social._cn_name_cache.clear()

    def test_detects_cn_market_tickers(self):
        self.assertTrue(agentkey_social.is_cn_market_ticker("0700.HK"))
        self.assertTrue(agentkey_social.is_cn_market_ticker("600519.SS"))
        self.assertTrue(agentkey_social.is_cn_market_ticker("000001.SZ"))
        self.assertFalse(agentkey_social.is_cn_market_ticker("AAPL"))
        self.assertFalse(agentkey_social.is_cn_market_ticker("BTC-USD"))

    def test_numeric_code_extraction(self):
        self.assertEqual(agentkey_social._ticker_numeric_code("0700.HK"), "0700")
        self.assertEqual(agentkey_social._ticker_numeric_code("600519.SS"), "600519")

    def test_extracts_chinese_name_before_padded_code(self):
        # "0700" → matched as zero-padded 00700, name captured before the paren.
        self.assertEqual(agentkey_social._extract_cn_name("腾讯控股(00700)股价分析", "0700"), "腾讯控股")
        self.assertEqual(agentkey_social._extract_cn_name("贵州茅台（600519）一季报", "600519"), "贵州茅台")

    def test_rejects_stopword_only_match(self):
        self.assertIsNone(agentkey_social._extract_cn_name("港股(00700)", "0700"))

    def test_resolve_picks_most_frequent_and_caches(self):
        payload = {
            "results": [
                {"title": "腾讯控股(00700)财报", "snippet": ""},
                {"title": "港股 00700", "snippet": "腾讯控股（00700）回购"},
            ]
        }
        with patch.object(agentkey_social, "search", return_value=payload) as mock_search:
            first = agentkey_social.resolve_cn_name("0700.HK", "Tencent")
            second = agentkey_social.resolve_cn_name("0700.HK", "Tencent")  # cached
        self.assertEqual(first, "腾讯控股")
        self.assertEqual(second, "腾讯控股")
        mock_search.assert_called_once()  # second call served from cache

    def test_resolve_falls_back_on_search_error(self):
        with patch.object(agentkey_social, "search", side_effect=AgentKeyError("down")):
            self.assertEqual(agentkey_social.resolve_cn_name("0700.HK", "Tencent"), "Tencent")

    def test_resolve_tolerates_malformed_results(self):
        # results not a list / items not dicts must not raise — fall back to brand.
        for payload in ({"results": "oops"}, {"results": ["str", 123, None]}, {}):
            agentkey_social._cn_name_cache.clear()
            with patch.object(agentkey_social, "search", return_value=payload):
                self.assertEqual(agentkey_social.resolve_cn_name("0700.HK", "Tencent"), "Tencent")

    def test_resolve_search_query_non_cn_uses_brand(self):
        self.assertEqual(agentkey_social.resolve_search_query("AAPL", "Apple Inc."), "Apple")


class ClientConfigTests(unittest.TestCase):
    def test_dispatch_without_key_raises(self):
        with patch.object(agentkey_client, "get_api_key", return_value=""):
            with self.assertRaises(AgentKeyError):
                agentkey_client.dispatch("weibo/app/fetch_search_all", {"query": "x"})


if __name__ == "__main__":
    unittest.main()
