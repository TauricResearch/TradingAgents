import unittest

from cli.main import format_research_team_history, format_risk_management_history
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.default_config import DEFAULT_CONFIG


class CliRoundFormattingTests(unittest.TestCase):
    def setUp(self):
        self.original_config = get_config().copy()
        cfg = DEFAULT_CONFIG.copy()
        cfg["output_language"] = "Chinese"
        set_config(cfg)

    def tearDown(self):
        set_config(self.original_config)

    def test_research_team_history_is_grouped_by_round(self):
        debate_state = {
            "bull_history": (
                "多头分析师: 第一轮多头观点\n"
                "反馈快照:\n"
                "- 当前观点: 买入\n"
                "- 发生了什么变化: 强化多头\n"
                "- 为什么变化: 金价走强\n"
                "- 关键反驳: 估值担忧可控\n"
                "- 下一轮教训: 跟踪量价\n"
                "多头分析师: 第二轮多头补充\n"
                "反馈快照:\n"
                "- 当前观点: 强烈买入\n"
                "- 发生了什么变化: 更激进\n"
                "- 为什么变化: 避险升级\n"
                "- 关键反驳: 回撤是买点\n"
                "- 下一轮教训: 盯并购兑现"
            ),
            "bear_history": (
                "空头分析师: 第一轮空头观点\n"
                "反馈快照:\n"
                "- 当前观点: 持有\n"
                "- 发生了什么变化: 维持谨慎\n"
                "- 为什么变化: 估值偏高\n"
                "- 关键反驳: 上涨已透支\n"
                "- 下一轮教训: 看现金流\n"
                "空头分析师: 第二轮空头反驳\n"
                "反馈快照:\n"
                "- 当前观点: 减持\n"
                "- 发生了什么变化: 转向更谨慎\n"
                "- 为什么变化: 风险升高\n"
                "- 关键反驳: 高位放量\n"
                "- 下一轮教训: 盯库存"
            ),
            "judge_decision": "研究经理: 最终结论",
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("### 第 1 轮", formatted)
        self.assertIn("#### 多头分析师\n\n多头分析师: 第一轮多头观点", formatted)
        self.assertIn("##### 本轮复盘\n反馈快照:\n- 当前观点: 买入", formatted)
        self.assertIn("- 发生了什么变化: 强化多头", formatted)
        self.assertIn("- 下一轮教训: 跟踪量价", formatted)
        self.assertIn("#### 空头分析师\n\n空头分析师: 第一轮空头观点", formatted)
        self.assertIn("### 第 2 轮", formatted)
        self.assertIn("#### 多头分析师\n\n多头分析师: 第二轮多头补充", formatted)
        self.assertIn("- 发生了什么变化: 更激进", formatted)
        self.assertIn("- 下一轮教训: 盯并购兑现", formatted)
        self.assertIn("#### 空头分析师\n\n空头分析师: 第二轮空头反驳", formatted)
        self.assertIn("- 发生了什么变化: 转向更谨慎", formatted)
        self.assertIn("- 下一轮教训: 盯库存", formatted)
        self.assertTrue(formatted.endswith("### 研究经理结论\n研究经理: 最终结论"))

    def test_risk_management_history_supports_english_prefixes(self):
        risk_state = {
            "aggressive_history": (
                "Aggressive Analyst: Round 1 aggressive case\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Current thesis: Sell\n"
                "- What changed: More defensive\n"
                "- Why it changed: Momentum broke\n"
                "- Key rebuttal: Upside is capped\n"
                "- Lesson for next round: Watch liquidity\n"
                "Aggressive Analyst: Round 2 aggressive follow-up"
            ),
            "conservative_history": (
                "Conservative Analyst: Round 1 conservative case\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Current thesis: Hold\n"
                "- What changed: Stayed cautious\n"
                "- Why it changed: Valuation rich\n"
                "- Key rebuttal: Do not chase\n"
                "- Lesson for next round: Check earnings"
            ),
            "neutral_history": (
                "Neutral Analyst: Round 1 neutral case\n"
                "FEEDBACK SNAPSHOT:\n"
                "- Current thesis: Hold\n"
                "- What changed: Balanced both sides\n"
                "- Why it changed: Conflicting signals\n"
                "- Key rebuttal: Need confirmation\n"
                "- Lesson for next round: Wait for breakout"
            ),
            "judge_decision": "Portfolio Manager: Final allocation",
        }

        formatted = format_risk_management_history(risk_state)

        self.assertIn("### 第 1 轮", formatted)
        self.assertIn("#### 激进分析师\n\nAggressive Analyst: Round 1 aggressive case", formatted)
        self.assertIn("##### 本轮复盘\nFEEDBACK SNAPSHOT:\n- Current thesis: Sell", formatted)
        self.assertIn("- What changed: More defensive", formatted)
        self.assertIn("- Lesson for next round: Watch liquidity", formatted)
        self.assertIn("#### 保守分析师\n\nConservative Analyst: Round 1 conservative case", formatted)
        self.assertIn("#### 中性分析师\n\nNeutral Analyst: Round 1 neutral case", formatted)
        self.assertIn("### 第 2 轮", formatted)
        self.assertIn("#### 激进分析师\n\nAggressive Analyst: Round 2 aggressive follow-up", formatted)
        self.assertIn("### 投资组合经理结论\nPortfolio Manager: Final allocation", formatted)

    def test_inferred_snapshot_uses_auto_review_title(self):
        debate_state = {
            "bull_history": (
                "多头分析师: 本轮新增了对库存风险的反驳，并强调需要继续跟踪金价与并购进度。\n"
                "反馈快照:\n"
                "- 当前观点: 暂无。\n"
                "- 发生了什么变化: 未明确说明。\n"
                "- 为什么变化: 未明确说明。\n"
                "- 关键反驳: 未明确说明。\n"
                "- 下一轮教训: 未明确说明。"
            ),
            "bear_history": "",
            "judge_decision": "",
        }

        formatted = format_research_team_history(debate_state)

        self.assertIn("##### 自动复盘", formatted)
        self.assertNotIn("##### 本轮复盘", formatted)


if __name__ == "__main__":
    unittest.main()
