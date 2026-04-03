import unittest

from tradingagents.graph.conditional_logic import ConditionalLogic


class ConditionalLogicLocalizationTests(unittest.TestCase):
    def test_should_continue_debate_uses_latest_speaker_not_localized_response_prefix(self):
        logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        state = {
            "investment_debate_state": {
                "count": 1,
                "latest_speaker": "Bull Analyst",
                "current_response": "多头分析师: 这是中文前缀，不应影响路由",
            }
        }

        self.assertEqual(logic.should_continue_debate(state), "Bear Researcher")

    def test_should_continue_debate_still_returns_research_manager_when_rounds_complete(self):
        logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
        state = {
            "investment_debate_state": {
                "count": 2,
                "latest_speaker": "Bull Analyst",
                "current_response": "多头分析师: 已完成一轮",
            }
        }

        self.assertEqual(logic.should_continue_debate(state), "Research Manager")


if __name__ == "__main__":
    unittest.main()
