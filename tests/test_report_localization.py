import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import save_report_bundle


class ReportLocalizationTests(unittest.TestCase):
    def test_save_report_bundle_uses_korean_labels(self):
        final_state = {
            "market_report": "시장 보고서 본문",
            "sentiment_report": "소셜 보고서 본문",
            "news_report": "뉴스 보고서 본문",
            "fundamentals_report": "펀더멘털 보고서 본문",
            "investment_debate_state": {
                "bull_history": "강세 의견",
                "bear_history": "약세 의견",
                "judge_decision": "리서치 매니저 판단",
            },
            "trader_investment_plan": "트레이딩 계획",
            "risk_debate_state": {
                "aggressive_history": "공격적 의견",
                "conservative_history": "보수적 의견",
                "neutral_history": "중립 의견",
                "judge_decision": "포트폴리오 최종 판단",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = save_report_bundle(
                final_state,
                "GOOGL",
                Path(tmpdir),
                language="Korean",
            )
            report_text = report_path.read_text(encoding="utf-8")

        self.assertIn("트레이딩 분석 리포트", report_text)
        self.assertIn("생성 시각", report_text)
        self.assertIn("애널리스트 팀 리포트", report_text)
        self.assertIn("포트폴리오 매니저 최종 판단", report_text)
        self.assertIn("시장 애널리스트", report_text)

    def test_localize_final_state_rewrites_user_facing_fields(self):
        graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
        graph.quick_thinking_llm = object()
        final_state = {
            "market_report": "market",
            "sentiment_report": "social",
            "news_report": "news",
            "fundamentals_report": "fundamentals",
            "investment_plan": "investment plan",
            "trader_investment_plan": "trader plan",
            "final_trade_decision": "final decision",
            "investment_debate_state": {
                "bull_history": "bull",
                "bear_history": "bear",
                "history": "debate history",
                "current_response": "latest debate",
                "judge_decision": "manager decision",
            },
            "risk_debate_state": {
                "aggressive_history": "aggressive",
                "conservative_history": "conservative",
                "neutral_history": "neutral",
                "history": "risk history",
                "current_aggressive_response": "aggr latest",
                "current_conservative_response": "cons latest",
                "current_neutral_response": "neutral latest",
                "judge_decision": "portfolio decision",
            },
        }

        with (
            patch("tradingagents.graph.trading_graph.get_output_language", return_value="Korean"),
            patch(
                "tradingagents.graph.trading_graph.rewrite_in_output_language",
                side_effect=lambda llm, content, content_type="report": f"KO::{content_type}::{content}",
            ),
        ):
            localized = graph._localize_final_state(final_state)

        self.assertEqual(localized["market_report"], "KO::market analyst report::market")
        self.assertEqual(localized["investment_plan"], "KO::research manager investment plan::investment plan")
        self.assertEqual(
            localized["investment_debate_state"]["judge_decision"],
            "KO::research manager decision::manager decision",
        )
        self.assertEqual(
            localized["risk_debate_state"]["current_neutral_response"],
            "KO::neutral risk analyst latest response::neutral latest",
        )


if __name__ == "__main__":
    unittest.main()
