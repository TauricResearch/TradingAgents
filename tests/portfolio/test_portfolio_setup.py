import json
from unittest.mock import patch

import pytest

from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_PORTFOLIO = {
    "portfolio_id": "p1",
    "name": "Main",
    "cash": 450000.0,
    "initial_cash": 500000.0,
    "total_value": 500000.0,
}

_AAPL_HOLDING = {
    "holding_id": "h1",
    "portfolio_id": "p1",
    "ticker": "AAPL",
    "shares": 250.0,
    "avg_cost": 180.0,
    "sector": "Technology",
    "current_value": 50000.0,  # 10% of total_value=500000 — within 15% position cap
    "current_price": 200.0,
}

_BASE_CONFIG = {
    "min_cash_pct": 0.05,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "max_positions": 15,
}


def _make_portfolio_data(portfolio=None, holdings=None) -> str:
    return json.dumps(
        {
            "portfolio": portfolio if portfolio is not None else dict(_BASE_PORTFOLIO),
            "holdings": holdings if holdings is not None else [dict(_AAPL_HOLDING)],
        }
    )


def _make_decision(**kwargs) -> str:
    base = {
        "macro_regime": "risk-on",
        "regime_alignment_note": "test",
        "sells": [],
        "buys": [],
        "holds": [],
        "cash_reserve_pct": 50.0,
        "portfolio_thesis": "test",
        "risk_summary": "test",
        "forensic_report": {
            "regime_alignment": "risk-on",
            "key_risks": [],
            "decision_confidence": "high",
            "position_sizing_rationale": "test",
        },
    }
    base.update(kwargs)
    return json.dumps(base)


def _make_prioritized_candidates(*tickers: str) -> str:
    return json.dumps(
        [
            {
                "ticker": ticker,
                "candidate_final_trade_decision_summary": f"Completed deep-dive supports {ticker}",
            }
            for ticker in tickers
        ]
    )


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


def test_prioritize_candidates_only_uses_completed_ticker_analyses():
    setup = PortfolioGraphSetup(agents={}, config={})
    node = setup._make_prioritize_candidates_node()

    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {
                    "portfolio_id": "p1",
                    "name": "Main",
                    "cash": 100000.0,
                    "initial_cash": 100000.0,
                },
                "holdings": [],
            }
        ),
        "scan_summary": {
            "stocks_to_investigate": [
                {
                    "ticker": "AAPL",
                    "conviction": "high",
                    "thesis_angle": "growth",
                    "sector": "Technology",
                },
                {
                    "ticker": "NVDA",
                    "conviction": "high",
                    "thesis_angle": "momentum",
                    "sector": "Technology",
                },
            ]
        },
        "ticker_analyses": {
            "equity:AAPL": {"final_trade_decision": "Rating: Buy"},
            "equity:NVDA": {"analysis_status": "incomplete", "investment_plan": "partial"},
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    prioritized = json.loads(result["prioritized_candidates"])
    assert [candidate["ticker"] for candidate in prioritized] == ["AAPL"]
    assert prioritized[0]["candidate_final_trade_decision_summary"] == "Rating: Buy"


def test_prioritize_candidates_ignores_running_analyses_even_with_stray_decisions():
    setup = PortfolioGraphSetup(agents={}, config={})
    node = setup._make_prioritize_candidates_node()

    state = {
        "portfolio_data": json.dumps(
            {
                "portfolio": {
                    "portfolio_id": "p1",
                    "name": "Main",
                    "cash": 100000.0,
                    "initial_cash": 100000.0,
                },
                "holdings": [],
            }
        ),
        "scan_summary": {
            "stocks_to_investigate": [
                {"ticker": "AAPL"},
                {"ticker": "NVDA"},
            ]
        },
        "ticker_analyses": {
            "equity:AAPL": {"analysis_status": "completed", "final_trade_decision": "Rating: Buy"},
            "equity:NVDA": {
                "analysis_status": "running",
                "final_trade_decision": "Stray partial output should not count.",
            },
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    prioritized = json.loads(result["prioritized_candidates"])
    assert [candidate["ticker"] for candidate in prioritized] == ["AAPL"]


# ---------------------------------------------------------------------------
# portfolio_integrity_guard — happy path
# ---------------------------------------------------------------------------


def test_integrity_guard_passes_valid_portfolio():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    result = node({"portfolio_data": _make_portfolio_data(), "prices": {}})
    assert result["sender"] == "portfolio_integrity_guard"


def test_integrity_guard_passes_without_enriched_holdings():
    """Guard should pass when holdings have no current_value (skips conservation check)."""
    holding_no_price = {
        "holding_id": "h1",
        "portfolio_id": "p1",
        "ticker": "AAPL",
        "shares": 250.0,
        "avg_cost": 180.0,
        "sector": "Technology",
        # no current_value — not enriched
    }
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    state = {"portfolio_data": _make_portfolio_data(holdings=[holding_no_price]), "prices": {}}
    result = node(state)
    assert result["sender"] == "portfolio_integrity_guard"


# ---------------------------------------------------------------------------
# portfolio_integrity_guard — check 1: total_value is None
# ---------------------------------------------------------------------------


def test_integrity_guard_raises_when_total_value_is_none():
    portfolio = dict(_BASE_PORTFOLIO)
    portfolio["total_value"] = None
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    with pytest.raises(RuntimeError, match="total_value is None"):
        node({"portfolio_data": _make_portfolio_data(portfolio=portfolio), "prices": {}})


def test_integrity_guard_raises_on_empty_portfolio_data():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    with pytest.raises(RuntimeError, match="total_value is None"):
        node({"portfolio_data": json.dumps({"portfolio": {}, "holdings": []}), "prices": {}})


# ---------------------------------------------------------------------------
# portfolio_integrity_guard — check 2: type sanity
# ---------------------------------------------------------------------------


def test_integrity_guard_raises_on_negative_cash():
    portfolio = dict(_BASE_PORTFOLIO)
    portfolio["cash"] = -100.0
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    with pytest.raises(RuntimeError, match="cash must be a non-negative number"):
        node({"portfolio_data": _make_portfolio_data(portfolio=portfolio), "prices": {}})


def test_integrity_guard_raises_when_holdings_not_list():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    bad_data = json.dumps({"portfolio": dict(_BASE_PORTFOLIO), "holdings": "not-a-list"})
    with pytest.raises(RuntimeError, match="holdings must be a list"):
        node({"portfolio_data": bad_data, "prices": {}})


# ---------------------------------------------------------------------------
# portfolio_integrity_guard — check 3: non-degenerate
# ---------------------------------------------------------------------------


def test_integrity_guard_raises_on_empty_portfolio():
    portfolio = dict(_BASE_PORTFOLIO)
    portfolio["cash"] = 0.0
    portfolio["total_value"] = 0.0
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    with pytest.raises(RuntimeError, match="empty portfolio"):
        node(
            {"portfolio_data": _make_portfolio_data(portfolio=portfolio, holdings=[]), "prices": {}}
        )


# ---------------------------------------------------------------------------
# portfolio_integrity_guard — check 4: conservation
# ---------------------------------------------------------------------------


def test_integrity_guard_raises_on_conservation_failure():
    portfolio = dict(_BASE_PORTFOLIO)
    portfolio["total_value"] = 600000.0  # far off from cash=450000 + equity=50000 = 500000
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    with pytest.raises(RuntimeError, match="conservation check failed"):
        node({"portfolio_data": _make_portfolio_data(portfolio=portfolio), "prices": {}})


def test_integrity_guard_passes_conservation_within_tolerance():
    """A tiny float rounding delta (< $1) should not raise."""
    portfolio = dict(_BASE_PORTFOLIO)
    portfolio["total_value"] = 500000.49  # within $1 of 450000 + 50000
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    result = node({"portfolio_data": _make_portfolio_data(portfolio=portfolio), "prices": {}})
    assert result["sender"] == "portfolio_integrity_guard"


# ---------------------------------------------------------------------------
# portfolio_integrity_guard — check 5: currency
# ---------------------------------------------------------------------------


def test_integrity_guard_raises_on_currency_mismatch():
    holding = dict(_AAPL_HOLDING)
    holding["currency"] = "EUR"
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    with pytest.raises(RuntimeError, match="currency mismatch"):
        node({"portfolio_data": _make_portfolio_data(holdings=[holding]), "prices": {}})


def test_integrity_guard_passes_matching_currency():
    holding = dict(_AAPL_HOLDING)
    holding["currency"] = "USD"  # same as default portfolio currency
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_portfolio_integrity_guard_node()

    result = node({"portfolio_data": _make_portfolio_data(holdings=[holding]), "prices": {}})
    assert result["sender"] == "portfolio_integrity_guard"


# ---------------------------------------------------------------------------
# pm_decision_postcheck — happy path
# ---------------------------------------------------------------------------


def test_postcheck_passes_valid_decision_no_trades():
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    result = node(
        {
            "pm_decision": _make_decision(),
            "portfolio_data": _make_portfolio_data(),
            "prices": {"AAPL": 200.0},
        }
    )
    assert result["sender"] == "pm_decision_postcheck"


def test_postcheck_passes_valid_buy_within_caps():
    """A buy that stays within all caps should pass."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    # Portfolio: cash=450000, AAPL=50000 (total=500000)
    # Buy 500 MSFT @ $100 = $50,000 → MSFT/total ≈ 9.1% < 15%; Tech sector ≈ 18.2% < 35%
    buy = {"ticker": "MSFT", "shares": 500.0, "price_target": 100.0, "sector": "Technology"}
    result = node(
        {
            "pm_decision": _make_decision(buys=[buy]),
            "portfolio_data": _make_portfolio_data(),
            "prices": {"AAPL": 200.0, "MSFT": 100.0},
            "prioritized_candidates": _make_prioritized_candidates("MSFT"),
        }
    )
    assert result["sender"] == "pm_decision_postcheck"


def test_postcheck_raises_on_ungrounded_buy():
    """Every non-cash-sweep buy must have a completed candidate deep-dive."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    buy = {"ticker": "MSFT", "shares": 500.0, "price_target": 100.0, "sector": "Technology"}
    with pytest.raises(RuntimeError, match="buy grounding violated.*MSFT"):
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0, "MSFT": 100.0},
                "prioritized_candidates": _make_prioritized_candidates("NVDA"),
            }
        )


def test_postcheck_raises_when_buy_candidate_summary_blank():
    """A matching candidate ticker without a completed summary is not grounded."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    buy = {"ticker": "MSFT", "shares": 500.0, "price_target": 100.0, "sector": "Technology"}
    with pytest.raises(RuntimeError, match="buy grounding violated.*MSFT"):
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0, "MSFT": 100.0},
                "prioritized_candidates": json.dumps(
                    [{"ticker": "MSFT", "candidate_final_trade_decision_summary": "   "}]
                ),
            }
        )


def test_postcheck_allows_sgov_cash_equivalent_sweep_without_deep_dive():
    """Cash-equivalent SGOV sweep buys do not require candidate deep-dive grounding."""
    setup = PortfolioGraphSetup(agents={}, config={**_BASE_CONFIG, "max_position_pct": 1.0})
    node = setup._make_pm_decision_postcheck_node()

    buy = {"ticker": "SGOV", "shares": 100.0, "price_target": 100.0, "sector": "Cash Equivalent"}
    result = node(
        {
            "pm_decision": _make_decision(buys=[buy]),
            "portfolio_data": _make_portfolio_data(),
            "prices": {"AAPL": 200.0, "SGOV": 100.0},
            "prioritized_candidates": "[]",
        }
    )

    assert result["sender"] == "pm_decision_postcheck"


# ---------------------------------------------------------------------------
# pm_decision_postcheck — check 1: cash adequacy
# ---------------------------------------------------------------------------


def test_postcheck_raises_on_cash_adequacy_violation():
    """Buying more than allowed leaves projected_cash below min_cash_pct."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    # Portfolio: cash=450000, AAPL=50000, total=500000
    # Buy 4800 shares of MSFT @ $100 = $480,000 from $450,000 cash → projected_cash=-30,000 < 5%
    # projected_total_value = -30000 + 50000 + 480000 = 500000
    # required_min_cash = 500000 * 0.05 = 25000; actual = -30000 → violation
    buy = {"ticker": "MSFT", "shares": 4800.0, "price_target": 100.0, "sector": "Technology"}
    with pytest.raises(RuntimeError, match="cash adequacy violated") as exc_info:
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0, "MSFT": 100.0},
                "prioritized_candidates": _make_prioritized_candidates("MSFT"),
            }
        )
    assert "projected_cash=-30000.00" in str(exc_info.value)


# ---------------------------------------------------------------------------
# pm_decision_postcheck — check 2: position-cap
# ---------------------------------------------------------------------------


def test_postcheck_raises_on_position_cap_violation():
    """Buying a large block that pushes a ticker above max_position_pct should raise."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    # Buy 900 shares of MSFT @ $100 = $90,000 → MSFT/total ≈ 16.4% > 15% (max_position_pct)
    buy = {"ticker": "MSFT", "shares": 900.0, "price_target": 100.0, "sector": "Technology"}
    with pytest.raises(RuntimeError, match="position cap violated"):
        node(
            {
                "pm_decision": _make_decision(buys=[buy]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0, "MSFT": 100.0},
                "prioritized_candidates": _make_prioritized_candidates("MSFT"),
            }
        )


# ---------------------------------------------------------------------------
# pm_decision_postcheck — check 3: sector-cap
# ---------------------------------------------------------------------------


def test_postcheck_raises_on_sector_cap_violation():
    """Total sector exposure above max_sector_pct should raise even when each position is fine."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    # Three Technology holdings at 12% each = 36% sector total > 35% sector cap.
    # Each individual position is 12% < 15% (position cap passes; sector cap fires).
    aapl_h = {
        "holding_id": "h1",
        "portfolio_id": "p1",
        "ticker": "AAPL",
        "shares": 60.0,
        "avg_cost": 200.0,
        "sector": "Technology",
        "current_value": 12000.0,
        "current_price": 200.0,
    }
    msft_h = {
        "holding_id": "h2",
        "portfolio_id": "p1",
        "ticker": "MSFT",
        "shares": 60.0,
        "avg_cost": 200.0,
        "sector": "Technology",
        "current_value": 12000.0,
        "current_price": 200.0,
    }
    nvda_h = {
        "holding_id": "h3",
        "portfolio_id": "p1",
        "ticker": "NVDA",
        "shares": 60.0,
        "avg_cost": 200.0,
        "sector": "Technology",
        "current_value": 12000.0,
        "current_price": 200.0,
    }
    portfolio = {
        "portfolio_id": "p1",
        "name": "Main",
        "cash": 64000.0,
        "initial_cash": 100000.0,
        "total_value": 100000.0,
    }

    with pytest.raises(RuntimeError, match="sector cap violated"):
        node(
            {
                "pm_decision": _make_decision(),
                "portfolio_data": _make_portfolio_data(
                    portfolio=portfolio, holdings=[aapl_h, msft_h, nvda_h]
                ),
                "prices": {"AAPL": 200.0, "MSFT": 200.0, "NVDA": 200.0},
            }
        )


# ---------------------------------------------------------------------------
# pm_decision_postcheck — check 4: cash-reserve floor
# ---------------------------------------------------------------------------


def test_postcheck_raises_on_cash_reserve_floor_violation():
    """A PM decision with cash_reserve_pct below min_cash_pct should raise."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    # min_cash_pct = 5% → cash_reserve_pct = 1.0 (1%) is too low
    with pytest.raises(RuntimeError, match="cash_reserve_pct floor violated"):
        node(
            {
                "pm_decision": _make_decision(cash_reserve_pct=1.0),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0},
            }
        )


# ---------------------------------------------------------------------------
# pm_decision_postcheck — check 5: sells reference real holdings
# ---------------------------------------------------------------------------


def test_postcheck_raises_on_sell_unknown_ticker():
    """Selling a ticker not in current holdings must raise."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    sell = {"ticker": "NVDA", "shares": 10.0, "rationale": "exit", "macro_driven": False}
    with pytest.raises(RuntimeError, match="sell references ticker 'NVDA'"):
        node(
            {
                "pm_decision": _make_decision(sells=[sell]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0},
            }
        )


def test_postcheck_passes_on_sell_known_ticker():
    """Selling a held ticker (AAPL) must pass."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    sell = {"ticker": "AAPL", "shares": 10.0, "rationale": "trim", "macro_driven": False}
    result = node(
        {
            "pm_decision": _make_decision(sells=[sell]),
            "portfolio_data": _make_portfolio_data(),
            "prices": {"AAPL": 200.0},
        }
    )
    assert result["sender"] == "pm_decision_postcheck"


# ---------------------------------------------------------------------------
# pm_decision_postcheck — check 6: no orphan holds
# ---------------------------------------------------------------------------


def test_postcheck_raises_on_orphan_hold():
    """A hold referencing a ticker not in current holdings must raise."""
    setup = PortfolioGraphSetup(agents={}, config=_BASE_CONFIG)
    node = setup._make_pm_decision_postcheck_node()

    hold = {"ticker": "GOOG", "rationale": "hold for recovery"}
    with pytest.raises(RuntimeError, match="hold references ticker 'GOOG'"):
        node(
            {
                "pm_decision": _make_decision(holds=[hold]),
                "portfolio_data": _make_portfolio_data(),
                "prices": {"AAPL": 200.0},
            }
        )
