from types import SimpleNamespace

from tradingagents.orchestrator.alert_evaluator import evaluate_alert_candidate


class FakeLLM:
    def __init__(self, content):
        self.content = content

    def invoke(self, prompt):
        self.prompt = prompt
        return SimpleNamespace(content=self.content)


def test_alert_evaluator_passes_material_direct_event():
    llm = FakeLLM(
        '{"decision":"pass","score":0.91,"materiality":"earnings surprise",'
        '"actionability":"watchlist thesis may change",'
        '"ticker_link_evidence":"NVDA named directly","novelty":"new filing",'
        '"disqualifiers":[],"reasons":["direct and material"]}'
    )
    result = evaluate_alert_candidate(
        llm=llm,
        event_text="NVDA raises guidance after earnings.",
        tickers=["NVDA"],
        min_score=0.80,
    )
    assert result.passed is True
    assert result.score == 0.91


def test_alert_evaluator_rejects_invalid_json():
    llm = FakeLLM("not json")
    result = evaluate_alert_candidate(
        llm=llm,
        event_text="generic market chatter",
        tickers=["AAPL"],
        min_score=0.80,
    )
    assert result.passed is False
    assert "invalid_json" in result.disqualifiers
