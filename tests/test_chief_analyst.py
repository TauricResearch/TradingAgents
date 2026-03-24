import pytest
from pydantic import ValidationError


def test_chief_analyst_report_valid_buy():
    from tradingagents.agents.utils.agent_states import ChiefAnalystReport
    r = ChiefAnalystReport(verdict="BUY", catalyst="Strong Q4", execution="Enter at market", tail_risk="Rate hike")
    assert r.verdict == "BUY"
    assert r.model_dump() == {
        "verdict": "BUY",
        "catalyst": "Strong Q4",
        "execution": "Enter at market",
        "tail_risk": "Rate hike",
    }


def test_chief_analyst_report_valid_sell():
    from tradingagents.agents.utils.agent_states import ChiefAnalystReport
    r = ChiefAnalystReport(verdict="SELL", catalyst="Weak guidance", execution="Exit position", tail_risk="Liquidity crunch")
    assert r.verdict == "SELL"


def test_chief_analyst_report_valid_hold():
    from tradingagents.agents.utils.agent_states import ChiefAnalystReport
    r = ChiefAnalystReport(verdict="HOLD", catalyst="Mixed signals", execution="No change", tail_risk="FX exposure")
    assert r.verdict == "HOLD"


def test_chief_analyst_report_rejects_invalid_verdict():
    from tradingagents.agents.utils.agent_states import ChiefAnalystReport
    with pytest.raises(ValidationError):
        ChiefAnalystReport(verdict="MAYBE", catalyst="x", execution="x", tail_risk="x")


def test_agent_state_does_not_require_chief_analyst_report():
    """AgentState can be constructed without chief_analyst_report (NotRequired field)."""
    from tradingagents.agents.utils.agent_states import AgentState
    from typing_extensions import get_type_hints, NotRequired
    hints = get_type_hints(AgentState, include_extras=True)
    assert "chief_analyst_report" in hints


# --- Task 2: Chief Analyst agent factory ---

from unittest.mock import MagicMock


def _make_mock_llm(verdict="BUY", catalyst="Strong earnings", execution="Enter at market", tail_risk="Rate risk"):
    """Return a mock LLM that produces a structured ChiefAnalystReport."""
    from tradingagents.agents.utils.agent_states import ChiefAnalystReport
    structured_llm = MagicMock()
    structured_llm.invoke.return_value = ChiefAnalystReport(
        verdict=verdict, catalyst=catalyst, execution=execution, tail_risk=tail_risk
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = structured_llm
    return mock_llm, structured_llm


def _make_state():
    """Minimal AgentState dict for testing the Chief Analyst node."""
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2024-01-15",
        "market_report": "Bullish technicals.",
        "sentiment_report": "Positive social sentiment.",
        "news_report": "No major negative news.",
        "fundamentals_report": "Strong balance sheet.",
        "investment_plan": "Bull case: enter long.",
        "trader_investment_plan": "Buy at market, SL at 180.",
        "final_trade_decision": "BUY. Rationale: strong Q4 earnings.",
    }


def test_create_chief_analyst_returns_callable():
    from tradingagents.agents.managers.chief_analyst import create_chief_analyst
    mock_llm, _ = _make_mock_llm()
    node = create_chief_analyst(mock_llm)
    assert callable(node)


def test_chief_analyst_node_calls_structured_llm():
    from tradingagents.agents.managers.chief_analyst import create_chief_analyst
    from tradingagents.agents.utils.agent_states import ChiefAnalystReport
    mock_llm, structured_llm = _make_mock_llm()
    node = create_chief_analyst(mock_llm)
    mock_llm.with_structured_output.assert_called_once_with(ChiefAnalystReport)


def test_chief_analyst_node_returns_report_dict():
    from tradingagents.agents.managers.chief_analyst import create_chief_analyst
    mock_llm, _ = _make_mock_llm(verdict="BUY", catalyst="Strong earnings", execution="Enter at market", tail_risk="Rate risk")
    node = create_chief_analyst(mock_llm)
    result = node(_make_state())
    assert "chief_analyst_report" in result
    assert result["chief_analyst_report"]["verdict"] == "BUY"
    assert result["chief_analyst_report"]["catalyst"] == "Strong earnings"
    assert result["chief_analyst_report"]["execution"] == "Enter at market"
    assert result["chief_analyst_report"]["tail_risk"] == "Rate risk"


def test_chief_analyst_node_result_is_json_serializable():
    """The returned dict must be serializable so SqliteSaver can checkpoint it."""
    import json
    from tradingagents.agents.managers.chief_analyst import create_chief_analyst
    mock_llm, _ = _make_mock_llm()
    node = create_chief_analyst(mock_llm)
    result = node(_make_state())
    serialized = json.dumps(result["chief_analyst_report"])
    assert isinstance(serialized, str)


def test_chief_analyst_node_prompt_includes_company_name():
    """The LLM must be called with a prompt referencing the company."""
    from tradingagents.agents.managers.chief_analyst import create_chief_analyst
    mock_llm, structured_llm = _make_mock_llm()
    node = create_chief_analyst(mock_llm)
    state = _make_state()
    node(state)
    call_args = structured_llm.invoke.call_args
    prompt_text = call_args[0][0]
    assert "AAPL" in prompt_text


# --- Task 4: trading_graph.py changes ---

def test_extract_report_chief_analyst_serializes_dict():
    """_extract_report for chief_analyst must JSON-serialize the dict from state."""
    import json
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    report_dict = {"verdict": "BUY", "catalyst": "x", "execution": "y", "tail_risk": "z"}
    update = {"chief_analyst_report": report_dict}
    result = TradingAgentsGraph._extract_report("chief_analyst", update)
    assert json.loads(result) == report_dict


def test_extract_report_chief_analyst_handles_missing():
    """_extract_report for chief_analyst returns empty JSON object when key absent."""
    import json
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    result = TradingAgentsGraph._extract_report("chief_analyst", {})
    assert json.loads(result) == {}


def test_node_to_step_includes_chief_analyst():
    from tradingagents.graph.trading_graph import _NODE_TO_STEP
    assert "Chief Analyst" in _NODE_TO_STEP
    assert _NODE_TO_STEP["Chief Analyst"] == "chief_analyst"
