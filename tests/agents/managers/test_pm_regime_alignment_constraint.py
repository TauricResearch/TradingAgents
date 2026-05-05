import inspect

import tradingagents.agents.portfolio.pm_decision_agent as pm_module


def test_pm_prompt_constrains_regime_alignment_field():
    src = inspect.getsource(pm_module)
    assert "macro-aligned" in src
    assert "regime-divergent" in src
    assert "uncorrelated" in src
    assert "Do NOT generate descriptive phrases" in src


def test_pm_forensic_report_regime_alignment_is_literal():
    """ForensicReport must reject hallucinated composite regime_alignment strings."""
    from tradingagents.agents.portfolio.pm_decision_agent import ForensicReport

    valid = ForensicReport(
        regime_alignment="macro-aligned",
        key_risks=["low"],
        decision_confidence="high",
        position_sizing_rationale="10%",
    )
    assert valid.regime_alignment == "macro-aligned"

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ForensicReport(
            regime_alignment="nostalgic-interference: US CDS -6.08",
            key_risks=[],
            decision_confidence="low",
            position_sizing_rationale="5%",
        )
