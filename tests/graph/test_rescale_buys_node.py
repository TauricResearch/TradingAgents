"""Tests for rescale_buys node (PR-B2.2).

The rescale_buys node deterministically scales down aggregate buy notional
to fit within max_total_buy_notional (cash – min_cash_pct * NAV).
"""
import json

import pytest


def _make_state(
    cash: float = 50_000.0,
    total_value: float = 200_000.0,
    buys: list | None = None,
    sells: list | None = None,
    min_cash_pct: float = 0.05,
) -> dict:
    return {
        "portfolio_data": json.dumps({
            "portfolio": {"cash": cash, "total_value": total_value},
            "holdings": [],
        }),
        "pm_decision": json.dumps({
            "buys": buys or [],
            "sells": sells or [],
            "holds": [],
            "macro_regime": "neutral",
            "regime_alignment_note": "test",
            "cash_reserve_pct": 5.0,
            "portfolio_thesis": "test",
            "risk_summary": "ok",
            "forensic_report": {
                "regime_alignment": "test",
                "key_risks": [],
                "decision_confidence": "low",
                "position_sizing_logic": "test",
                "position_sizing_rationale": "test",
            },
        }),
        "prices": {"AAPL": 150.0, "MSFT": 300.0},
        "sender": "make_pm_decision",
    }


def test_rescale_buys_noop_when_within_ceiling():
    """Node does not modify buys when total notional is within ceiling."""
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    # cash=50k, NAV=200k, min_cash_pct=5% → ceiling = 50000 - 0.05*200000 = 40000
    # buy: AAPL 100 shares @ 150 = 15000 < 40000 → no scaling
    state = _make_state(
        cash=50_000.0, total_value=200_000.0,
        buys=[{
            "ticker": "AAPL", "shares": 100.0,
            "entry_price": 150.0, "limit_price": 155.0, "max_chase_price": 153.0,
            "order_type": "limit", "valid_as_of": "2025-01-01",
            "price_target": 200.0, "stop_loss": 130.0, "take_profit": 195.0,
            "sector": "Technology", "rationale": "r", "thesis": "t",
            "macro_alignment": "m", "memory_note": "", "position_sizing_logic": "p",
        }],
    )
    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05})
    node = setup._make_rescale_buys_node()
    result = node(state)

    decision = json.loads(result["pm_decision"])
    assert decision["buys"][0]["shares"] == pytest.approx(100.0, rel=0.01)


def test_rescale_buys_scales_down_proportionally():
    """Node scales ALL buy shares proportionally when aggregate notional exceeds ceiling."""
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    # cash=10k, NAV=100k, min_cash_pct=5% → ceiling = 10000 - 5000 = 5000
    # buy: AAPL 100 shares @ 150 = 15000 > 5000 → scale factor = 5000/15000 = 0.333
    state = _make_state(
        cash=10_000.0, total_value=100_000.0,
        buys=[{
            "ticker": "AAPL", "shares": 100.0,
            "entry_price": 150.0, "limit_price": 155.0, "max_chase_price": 153.0,
            "order_type": "limit", "valid_as_of": "2025-01-01",
            "price_target": 200.0, "stop_loss": 130.0, "take_profit": 195.0,
            "sector": "Technology", "rationale": "r", "thesis": "t",
            "macro_alignment": "m", "memory_note": "", "position_sizing_logic": "p",
        }],
    )
    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05})
    node = setup._make_rescale_buys_node()
    result = node(state)

    decision = json.loads(result["pm_decision"])
    scaled_shares = decision["buys"][0]["shares"]
    # Expected: 100 * (5000/15000) ≈ 33.33
    assert scaled_shares == pytest.approx(33.33, rel=0.01)
    assert result["sender"] == "rescale_buys"


def test_rescale_buys_zero_ceiling_clears_all_buys():
    """When ceiling is 0 or negative, all buys are dropped."""
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    # cash=5k, NAV=100k, min_cash_pct=10% → ceiling = 5000 - 10000 = -5000 → clamp 0
    state = _make_state(
        cash=5_000.0, total_value=100_000.0,
        min_cash_pct=0.10,
        buys=[{
            "ticker": "AAPL", "shares": 10.0,
            "entry_price": 150.0, "limit_price": 155.0, "max_chase_price": 153.0,
            "order_type": "limit", "valid_as_of": "2025-01-01",
            "price_target": 200.0, "stop_loss": 130.0, "take_profit": 195.0,
            "sector": "Technology", "rationale": "r", "thesis": "t",
            "macro_alignment": "m", "memory_note": "", "position_sizing_logic": "p",
        }],
    )
    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.10})
    node = setup._make_rescale_buys_node()
    result = node(state)

    decision = json.loads(result["pm_decision"])
    assert decision["buys"] == []


def test_rescale_buys_node_registered_in_graph():
    """rescale_buys appears as a node in the compiled portfolio graph."""
    import inspect
    from pathlib import Path

    setup_src = Path(__file__).parent.parent.parent / "tradingagents/graph/portfolio_setup.py"
    source = setup_src.read_text()

    # Check node method exists and is wired
    assert "_make_rescale_buys_node" in source
    assert "\"rescale_buys\"" in source
    # Edge: make_pm_decision → rescale_buys → cash_sweep
    assert "make_pm_decision\", \"rescale_buys" in source or '"make_pm_decision", "rescale_buys"' in source
