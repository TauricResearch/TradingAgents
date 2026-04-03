import copy
import unittest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.agents.utils.agent_utils import (
    build_debate_brief,
    extract_feedback_snapshot,
    get_snapshot_template,
    strip_feedback_snapshot,
    truncate_for_prompt,
)
from tradingagents.agents.utils.memory import FinancialSituationMemory


class ContextMemoryOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())

    def tearDown(self):
        set_config(self.original_config)

    def test_truncate_for_prompt_uses_config_limit(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["report_context_char_limit"] = 10
        set_config(cfg)

        text = "abcdefghijklmnopqrstuvwxyz"
        truncated = truncate_for_prompt(text)

        self.assertIn("Content trimmed", truncated)
        self.assertTrue(truncated.endswith("qrstuvwxyz"))

    def test_memory_similarity_threshold_filters_irrelevant_matches(self):
        situations = [
            ("apple earnings beat with margin expansion", "prefer bullish setups"),
            ("oil demand collapse and weak refinery margins", "reduce cyclical exposure"),
        ]
        strict_memory = FinancialSituationMemory(
            "strict_memory",
            config={"memory_min_similarity": 0.99},
        )
        strict_memory.add_situations(situations)

        unrelated = strict_memory.get_memories("football world cup final highlights", n_matches=2)
        self.assertEqual(unrelated, [])

        related = strict_memory.get_memories("apple margin expansion after earnings", n_matches=2)
        self.assertEqual(related, [])

        relaxed_memory = FinancialSituationMemory(
            "relaxed_memory",
            config={"memory_min_similarity": 0.0},
        )
        relaxed_memory.add_situations(situations)
        related = relaxed_memory.get_memories("apple margin expansion after earnings", n_matches=2)
        self.assertGreaterEqual(len(related), 1)

    def test_feedback_snapshot_helpers(self):
        response = (
            "Argument body here.\n\n"
            "FEEDBACK SNAPSHOT:\n"
            "- Current thesis: Bull case improved.\n"
            "- What changed: Margin outlook improved.\n"
            "- Why it changed: Earnings beat.\n"
            "- Key rebuttal: Bear margin fears are weaker.\n"
            "- Lesson for next round: Track valuation risk."
        )

        snapshot = extract_feedback_snapshot(response)
        body = strip_feedback_snapshot(response)
        brief = build_debate_brief(
            {
                "Bull Analyst": snapshot,
                "Bear Analyst": "FEEDBACK SNAPSHOT:\n- Current thesis: Bear case unchanged.",
            },
            latest_speaker="Bull Analyst",
        )

        self.assertIn("Current thesis", snapshot)
        self.assertEqual(body, "Argument body here.")
        self.assertIn("Latest update came from: Bull Analyst", brief)
        self.assertIn("Bull Analyst latest snapshot", brief)

    def test_build_debate_brief_localizes_summary_phrases_for_chinese(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        brief = build_debate_brief(
            {
                "Bull Analyst": "反馈快照:\n- 当前观点: 多头增强。",
                "Bear Analyst": "反馈快照:\n- 当前观点: 空头不变。",
            },
            latest_speaker="Bull Analyst",
        )

        self.assertIn("最新更新来自: 多头分析师", brief)
        self.assertIn("多头分析师 最新快照", brief)

    def test_feedback_snapshot_helpers_support_chinese_template(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        self.assertIn("反馈快照", get_snapshot_template())

        response = (
            "论证正文。\n\n"
            "反馈快照:\n"
            "- 当前观点: 多头逻辑增强。\n"
            "- 发生了什么变化: 利润率预期改善。\n"
            "- 为什么变化: 财报超预期。\n"
            "- 关键反驳: 空头对利润率的担忧减弱。\n"
            "- 下一轮教训: 继续跟踪估值风险。"
        )

        snapshot = extract_feedback_snapshot(response)
        body = strip_feedback_snapshot(response)

        self.assertIn("当前观点", snapshot)
        self.assertEqual(body, "论证正文。")

    def test_feedback_snapshot_infers_substantive_chinese_content_when_placeholder_block_is_used(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。本轮新增了对库存风险的反驳，并强调需要继续跟踪金价与并购进度。\n\n"
            "反馈快照:\n"
            "- 当前观点: 暂无。\n"
            "- 发生了什么变化: 未明确说明。\n"
            "- 为什么变化: 未明确说明。\n"
            "- 关键反驳: 未明确说明。\n"
            "- 下一轮教训: 未明确说明。"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertNotIn("未明确说明", snapshot)
        self.assertNotIn("暂无", snapshot)
        self.assertIn("- 当前观点: 持有", snapshot)
        self.assertIn("库存风险", snapshot)
        self.assertIn("继续跟踪金价与并购进度", snapshot)

    def test_feedback_snapshot_fills_empty_fields_with_inferred_content(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。本轮转向更谨慎，核心原因是估值偏高且需要继续跟踪成交量是否萎缩。\n\n"
            "反馈快照:\n"
            "- 当前观点:\n"
            "- 发生了什么变化:\n"
            "- 为什么变化: 估值偏高。\n"
            "- 关键反驳:\n"
            "- 下一轮教训:"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- 当前观点: 持有", snapshot)
        self.assertIn("- 发生了什么变化:", snapshot)
        self.assertIn("- 为什么变化: 估值偏高。", snapshot)
        self.assertIn("- 关键反驳:", snapshot)
        self.assertIn("- 下一轮教训:", snapshot)
        self.assertNotIn("- 当前观点: \n", snapshot)
        self.assertNotIn("- 关键反驳: \n", snapshot)

    def test_feedback_snapshot_detects_explicit_chinese_rating_terms(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "我们维持减持观点，建议分批止盈，等待更好的风险收益比。\n\n"
            "反馈快照:\n"
            "- 当前观点:\n"
            "- 发生了什么变化:\n"
            "- 为什么变化:\n"
            "- 关键反驳:\n"
            "- 下一轮教训:"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- 当前观点: 减持", snapshot)


if __name__ == "__main__":
    unittest.main()
