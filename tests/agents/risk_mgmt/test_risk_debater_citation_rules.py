import inspect
import tradingagents.agents.risk_mgmt.aggressive_debator as agg
import tradingagents.agents.risk_mgmt.conservative_debator as con
import tradingagents.agents.risk_mgmt.neutral_debator as neu


def test_all_debaters_have_citation_rule():
    for module, name in [(agg, "aggressive"), (con, "conservative"), (neu, "neutral")]:
        src = inspect.getsource(module)
        assert "EVIDENCE CITATION RULES" in src, f"{name} debater missing citation rules"
        assert "Analyst estimate, unverified" in src, f"{name} debater missing unverified label"
