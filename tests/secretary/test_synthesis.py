import pytest
from unittest.mock import MagicMock


@pytest.fixture
def sample_persona_runs():
    return [
        {"persona_id": "macro", "decision": "SELL", "final_trade_decision":
            "SELL — rates rising squeeze tech multiples"},
        {"persona_id": "value", "decision": "BUY", "final_trade_decision":
            "BUY — cashflow yield 6%, stock undervalued"},
        {"persona_id": "momentum", "decision": "BUY", "final_trade_decision":
            "BUY — uptrend intact, call OI building"},
    ]


@pytest.mark.unit
def test_synthesis_calls_llm_and_returns_three_sections(sample_persona_runs):
    from tradingagents.secretary.synthesis import synthesize_brief
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="""
## Consensus
- Cashflow yield is attractive at current price.

## Divergence
- Macro persona says SELL on rate path; value and momentum say BUY.

## Recommendation
Low-confidence call: macro disagreement is material. Hold.
""")
    result = synthesize_brief(
        llm=fake_llm,
        ticker="AAPL",
        persona_runs=sample_persona_runs,
    )
    assert "consensus" in result
    assert "divergence" in result
    assert "recommendation" in result
    assert "Hold" in result["recommendation"] or "HOLD" in result["recommendation"]


@pytest.mark.unit
def test_synthesis_prompt_includes_divergence_directive(sample_persona_runs):
    """The synthesis prompt MUST instruct the LLM to preserve disagreement
    explicitly. This is R3 mitigation in the program design."""
    from tradingagents.secretary.synthesis import build_synthesis_prompt
    prompt = build_synthesis_prompt(ticker="AAPL", persona_runs=sample_persona_runs)
    assert "divergence" in prompt.lower() or "disagree" in prompt.lower()
    assert "AAPL" in prompt
    assert "macro" in prompt and "value" in prompt and "momentum" in prompt
