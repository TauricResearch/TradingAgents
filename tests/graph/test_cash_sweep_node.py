"""Tests for cash_sweep node — P1 regression coverage.

The cash_sweep node parks excess cash into SGOV (cash-equivalent ETF). It
runs AFTER rescale_buys, so when computing "excess" it must subtract
already-approved BUY notional from portfolio cash. Otherwise the combined
basket (PM buys + SGOV) over-allocates cash and pm_decision_postcheck
fails the cash floor.
"""

import json

import pytest


def _make_state(
    cash: float,
    total_value: float,
    buys: list | None = None,
    prices: dict | None = None,
) -> dict:
    return {
        "portfolio_data": json.dumps(
            {
                "portfolio": {
                    "portfolio_id": "test-portfolio",
                    "name": "Test Portfolio",
                    "cash": cash,
                    "initial_cash": cash,
                    "total_value": total_value,
                },
                "holdings": [],
            }
        ),
        "pm_decision": json.dumps(
            {
                "buys": buys or [],
                "sells": [],
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
            }
        ),
        "prices": prices or {},
        "sender": "rescale_buys",
    }


def _buy(ticker: str, shares: float, entry: float) -> dict:
    return {
        "ticker": ticker,
        "shares": shares,
        "entry_price": entry,
        "limit_price": entry * 1.05,
        "max_chase_price": entry * 1.03,
        "order_type": "limit",
        "valid_as_of": "2025-01-01",
        "price_target": entry * 1.20,
        "stop_loss": entry * 0.90,
        "take_profit": entry * 1.15,
        "sector": "Technology",
        "rationale": "r",
        "thesis": "t",
        "macro_alignment": "m",
        "memory_note": "",
        "position_sizing_logic": "p",
    }


def test_cash_sweep_subtracts_approved_buy_notional_from_excess():
    """P1 regression: cash_sweep must size SGOV from cash *after* PM buys,
    not from pre-buy portfolio cash.

    Setup: cash=$50K, NAV=$200K, target=5% (so target reserve $10K).
    PM has approved a $20K AAPL buy. Sweep should park (50K - 20K - 10K)=$20K
    in SGOV, NOT (50K - 10K)=$40K.
    """
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    state = _make_state(
        cash=50_000.0,
        total_value=200_000.0,
        buys=[_buy("AAPL", 100.0, 200.0)],  # 100 * 200 = $20K
        prices={"AAPL": 200.0, "SGOV": 100.0},
    )

    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05})
    node = setup._make_cash_sweep_node()
    result = node(state)
    decision = json.loads(result["pm_decision"])

    sgov_buys = [b for b in decision["buys"] if b["ticker"] == "SGOV"]
    assert len(sgov_buys) == 1, f"Expected 1 SGOV sweep, got {sgov_buys}"

    # SGOV at $100/share. Available after buys+target: 50K - 20K - 10K = 20K.
    # int(20000 / 100) = 200 shares.
    assert sgov_buys[0]["shares"] == pytest.approx(200.0, rel=0.001), (
        f"SGOV shares={sgov_buys[0]['shares']}; expected 200. "
        "Sweep must subtract approved BUY notional from excess cash."
    )

    # Combined basket must respect the cash floor:
    #   PM buys + SGOV ≤ cash - min_cash_pct * NAV
    pm_total = 100.0 * 200.0  # AAPL
    sgov_total = sgov_buys[0]["shares"] * 100.0
    combined = pm_total + sgov_total
    floor = 50_000.0 - 0.05 * 200_000.0  # = 40K
    assert combined <= floor + 1e-6, (
        f"combined={combined} > floor={floor} — cash_sweep over-allocated"
    )


def test_cash_sweep_uses_live_price_for_buy_notional():
    """When live price differs from entry, sweep must use live price (same
    source as postcheck). With live > entry, the buy notional is larger and
    less cash should be swept.
    """
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    state = _make_state(
        cash=50_000.0,
        total_value=200_000.0,
        buys=[_buy("AAPL", 100.0, 150.0)],  # entry=150 but live=200
        prices={"AAPL": 200.0, "SGOV": 100.0},
    )

    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05})
    node = setup._make_cash_sweep_node()
    result = node(state)
    decision = json.loads(result["pm_decision"])
    sgov_buys = [b for b in decision["buys"] if b["ticker"] == "SGOV"]

    # Available = 50K - 100*200 (live) - 0.05*200K = 50K - 20K - 10K = 20K
    # → 200 shares of SGOV at $100. (Using entry=150 would give 250 shares,
    # which would over-allocate.)
    assert sgov_buys[0]["shares"] == pytest.approx(200.0, rel=0.001)


def test_cash_sweep_no_op_when_buys_consume_target_cash():
    """When PM buys consume cash down to (or below) the target reserve,
    no sweep should happen.
    """
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    state = _make_state(
        cash=50_000.0,
        total_value=200_000.0,
        buys=[_buy("AAPL", 200.0, 200.0)],  # 200*200 = $40K → cash_after = $10K = target
        prices={"AAPL": 200.0, "SGOV": 100.0},
    )

    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05})
    node = setup._make_cash_sweep_node()
    result = node(state)
    decision = json.loads(result["pm_decision"])
    sgov_buys = [b for b in decision["buys"] if b["ticker"] == "SGOV"]
    assert sgov_buys == [], f"Expected no sweep when PM buys hit target reserve; got {sgov_buys}"


def test_cash_sweep_target_defaults_to_min_cash_pct():
    """When target_cash_pct is unset, the sweep target follows min_cash_pct.

    Without this defaulting, a deployment that raises min_cash_pct above 0.05
    would still see SGOV pushing cash down to 5% — silently violating the
    operator's reserve. Audit finding (Important).
    """
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    # cash=$50K, NAV=$200K, min_cash_pct=0.10 → target reserve is 0.10*200K=$20K.
    # No PM buys. Excess = 50K - 20K = $30K → 300 SGOV shares (not 400 from 0.05).
    state = _make_state(
        cash=50_000.0,
        total_value=200_000.0,
        buys=[],
        prices={"SGOV": 100.0},
    )

    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.10})
    node = setup._make_cash_sweep_node()
    result = node(state)
    sgov_buys = [b for b in json.loads(result["pm_decision"])["buys"] if b["ticker"] == "SGOV"]
    assert sgov_buys, "expected sweep to fire"
    assert sgov_buys[0]["shares"] == pytest.approx(300.0, rel=0.001), (
        f"target_cash_pct should follow min_cash_pct; got {sgov_buys[0]['shares']} shares "
        "(would be 400 if hardcoded to 0.05)"
    )


def test_cash_sweep_explicit_target_cash_pct_wins():
    """Operators can still set target_cash_pct above min_cash_pct for a buffer."""
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    # cash=$50K, NAV=$200K, min=5% but target=15% → reserve $30K → excess $20K → 200 shares
    state = _make_state(
        cash=50_000.0,
        total_value=200_000.0,
        buys=[],
        prices={"SGOV": 100.0},
    )

    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05, "target_cash_pct": 0.15})
    node = setup._make_cash_sweep_node()
    result = node(state)
    sgov_buys = [b for b in json.loads(result["pm_decision"])["buys"] if b["ticker"] == "SGOV"]
    assert sgov_buys[0]["shares"] == pytest.approx(200.0, rel=0.001)


def test_cash_sweep_skips_when_buys_exceed_cash():
    """Defensive: if (post-rescale) buy notional exceeds cash, no sweep —
    rescale should have prevented this; sweep must not 'rescue' by going
    negative or sizing off pre-buy cash.
    """
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    state = _make_state(
        cash=10_000.0,
        total_value=200_000.0,
        buys=[_buy("AAPL", 100.0, 200.0)],  # $20K buy on $10K cash
        prices={"AAPL": 200.0, "SGOV": 100.0},
    )

    setup = PortfolioGraphSetup(agents={}, config={"min_cash_pct": 0.05})
    node = setup._make_cash_sweep_node()
    result = node(state)
    decision = json.loads(result["pm_decision"])
    sgov_buys = [b for b in decision["buys"] if b["ticker"] == "SGOV"]
    assert sgov_buys == []
