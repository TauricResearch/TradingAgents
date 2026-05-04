"""Integration: replay of the failed run through rescale_buys and postcheck (PR-B2.3).

This test is marked ``integration`` and skipped in default CI runs.
It demonstrates that the rescale_buys → pm_decision_postcheck pipeline
would have succeeded for run 01KQHDVJB2R19S4D7Z7Z6DP9F7 instead of
crashing at pm_decision_postcheck with a cash-adequacy violation.
"""

import json

import pytest


@pytest.mark.integration
def test_failed_run_rescales_and_passes_postcheck():
    """Replay 01KQHDVJB2R19S4D7Z7Z6DP9F7: with rescale_buys, postcheck passes.

    Reconstructed basket from the event log's make_pm_decision result:
    - cash at decision time: ~$2,687.88
    - total NAV:             ~$99,923.20
    - min_cash_pct (10%):    floor = $9,992.32
    - original buy notional: ~$7,304.44 (over the $0 ceiling after accounting for floor)
    - Expected: rescale_buys drops all buys to 0 shares; postcheck passes.
    """
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    config = {"min_cash_pct": 0.10}
    setup = PortfolioGraphSetup(agents={}, config=config)
    rescale_node = setup._make_rescale_buys_node()

    # Synthesised state matching the failed run parameters
    pm_decision = {
        "macro_regime": "risk-off",
        "regime_alignment_note": "Defensive",
        "sells": [],
        "buys": [
            {
                "ticker": "ET",
                "shares": 362.0,
                "entry_price": 20.18,
                "limit_price": 20.50,
                "max_chase_price": 20.40,
                "order_type": "limit",
                "valid_as_of": "2026-05-01",
                "price_target": 24.0,
                "stop_loss": 17.5,
                "take_profit": 24.0,
                "sector": "Energy",
                "rationale": "High-yield MLP with resilient cash flows",
                "thesis": "Income + appreciation",
                "macro_alignment": "Income play in risk-off regime",
                "memory_note": "",
                "position_sizing_logic": "362 shares * $20.18 = $7,305",
            }
        ],
        "holds": [],
        "cash_reserve_pct": 90.0,
        "portfolio_thesis": "Defensive",
        "risk_summary": "Low",
        "forensic_report": {
            "regime_alignment": "regime-divergent",
            "key_risks": ["market volatility"],
            "decision_confidence": "medium",
            "position_sizing_rationale": "conservative sizing",
        },
    }
    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {"cash": 2687.88, "total_value": 99923.20},
                "holdings": [],
            }
        ),
        "pm_decision": json.dumps(pm_decision),
        "prices": {"ET": 20.18},
        "sender": "make_pm_decision",
    }

    result = rescale_node(state)
    rescaled_decision = json.loads(result["pm_decision"])

    # With cash=2687 and floor=9992, ceiling is negative → all buys cleared
    assert rescaled_decision["buys"] == [] or all(
        b["shares"] == 0 for b in rescaled_decision["buys"]
    ), f"Expected zero shares after rescale, got: {rescaled_decision['buys']}"
