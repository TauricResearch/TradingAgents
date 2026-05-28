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
            self.assertEqual(build_agentkey_social_section("Apple", "Technology", "Consumer Electronics"), "")

    def test_configured_consumer_includes_all_four_blocks(self):
        with patch.object(agentkey_social, "is_configured", return_value=True), patch.object(
            agentkey_social, "dispatch", side_effect=AgentKeyError("upstream down")
        ):
            section = build_agentkey_social_section("Apple", "Technology", "Consumer Electronics")
        for channel in ("weibo", "zhihu", "xiaohongshu", "douyin"):
            self.assertIn(f"<start_of_{channel}>", section)
            self.assertIn(f"<end_of_{channel}>", section)

    def test_configured_non_consumer_only_base_blocks(self):
        with patch.object(agentkey_social, "is_configured", return_value=True), patch.object(
            agentkey_social, "dispatch", side_effect=AgentKeyError("upstream down")
        ):
            section = build_agentkey_social_section("Boeing", "Industrials", "Aerospace & Defense")
        self.assertIn("<start_of_weibo>", section)
        self.assertIn("<start_of_zhihu>", section)
        self.assertNotIn("<start_of_xiaohongshu>", section)
        self.assertNotIn("<start_of_douyin>", section)


class ClientConfigTests(unittest.TestCase):
    def test_dispatch_without_key_raises(self):
        with patch.object(agentkey_client, "get_api_key", return_value=""):
            with self.assertRaises(AgentKeyError):
                agentkey_client.dispatch("weibo/app/fetch_search_all", {"query": "x"})


if __name__ == "__main__":
    unittest.main()
