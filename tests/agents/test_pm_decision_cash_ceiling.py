"""Tests for PM decision cash ceiling injection (PR-B2.1)."""
import json


def test_context_includes_resolved_cash_ceiling():
    """_build_pm_context resolves max_total_buy_notional from cash and NAV."""
    from tradingagents.agents.portfolio.pm_decision_agent import _build_pm_context

    state = {
        "portfolio_data": json.dumps({
            "portfolio": {"cash": 25000.0, "total_value": 100000.0},
            "holdings": [],
        }),
        "macro_brief": "RISK-ON",
        "micro_brief": "ok",
        "prioritized_candidates": "[]",
    }
    cfg = {"min_cash_pct": 0.10}
    ctx = _build_pm_context(state, cfg)

    # max_total_buy_notional = 25000 - 0.10 * 100000 = 15000
    assert "max_total_buy_notional" in ctx
    assert "15000" in ctx


def test_context_cash_ceiling_zero_when_below_floor():
    """max_total_buy_notional clamps to 0 when cash is below the required floor."""
    from tradingagents.agents.portfolio.pm_decision_agent import _build_pm_context

    state = {
        "portfolio_data": json.dumps({
            "portfolio": {"cash": 5000.0, "total_value": 100000.0},
            "holdings": [],
        }),
        "macro_brief": "",
        "micro_brief": "",
        "prioritized_candidates": "[]",
    }
    cfg = {"min_cash_pct": 0.10}
    ctx = _build_pm_context(state, cfg)

    # cash 5000, floor 10000 → budget -5000 → clamp to 0
    assert "max_total_buy_notional" in ctx
    # Should show 0 or $0
    assert "$0" in ctx or "0.00" in ctx


def test_context_includes_standard_constraint_fields():
    """_build_pm_context includes standard portfolio constraint fields."""
    from tradingagents.agents.portfolio.pm_decision_agent import _build_pm_context

    state = {
        "portfolio_data": json.dumps({
            "portfolio": {"cash": 50000.0, "total_value": 200000.0},
            "holdings": [],
        }),
        "macro_brief": "neutral",
        "micro_brief": "micro",
        "prioritized_candidates": "[]",
    }
    cfg = {"min_cash_pct": 0.05, "max_position_pct": 0.15}
    ctx = _build_pm_context(state, cfg)

    assert "Portfolio Constraints" in ctx
    assert "Portfolio Summary" in ctx
    assert "Macro Context" in ctx
