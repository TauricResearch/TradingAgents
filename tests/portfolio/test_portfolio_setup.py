import json
import logging
from unittest.mock import Mock, patch

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
            "regime_alignment": "macro-aligned",
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


def _make_record_pm_decisions_state(pm_decision: dict | str) -> dict:
    if isinstance(pm_decision, str):
        pm_decision_str = pm_decision
    else:
        pm_decision_str = json.dumps(pm_decision)

    return {
        "portfolio_id": "port-1",
        "analysis_date": "2026-03-20",
        "run_id": "run-test-123",
        "pm_decision": pm_decision_str,
        "prices": {},
        "messages": [],
        "portfolio_data": "{}",
        "risk_metrics": "{}",
        "holding_reviews": "{}",
        "prioritized_candidates": "[]",
        "macro_brief": "",
        "micro_brief": "",
        "macro_memory_context": "",
        "micro_memory_context": "",
        "cash_sweep": "",
        "execution_result": "{}",
        "sender": "",
        "ticker_analyses": {},
    }


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
            "equity:AAPL": {
                "final_trade_decision": "Rating: Buy",
                "final_trade_decision_structured": {"status": "completed", "action": "BUY"},
            },
            "equity:NVDA": {
                "analysis_status": "incomplete",
                "investment_plan": "partial",
                "final_trade_decision_structured": {"status": "completed", "action": "BUY"},
            },
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
            "equity:AAPL": {
                "analysis_status": "completed",
                "final_trade_decision": "Rating: Buy",
                "final_trade_decision_structured": {"status": "completed", "action": "BUY"},
            },
            "equity:NVDA": {
                "analysis_status": "running",
                "final_trade_decision": "Stray partial output should not count.",
                "final_trade_decision_structured": {"status": "completed", "action": "BUY"},
            },
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    prioritized = json.loads(result["prioritized_candidates"])
    assert [candidate["ticker"] for candidate in prioritized] == ["AAPL"]


def test_prioritize_candidates_rejects_structured_sell_even_when_prose_says_buy():
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
        "scan_summary": {"stocks_to_investigate": [{"ticker": "RIG"}]},
        "ticker_analyses": {
            "equity:RIG": {
                "analysis_status": "completed",
                "final_trade_decision": "Rating: Buy after the selloff.",
                "final_trade_decision_structured": {
                    "status": "completed",
                    "action": "SELL",
                },
            }
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    assert json.loads(result["prioritized_candidates"]) == []


def test_prioritize_candidates_keeps_completed_structured_buy():
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
        "scan_summary": {"stocks_to_investigate": [{"ticker": "RMAX"}]},
        "ticker_analyses": {
            "equity:RMAX": {
                "analysis_status": "completed",
                "final_trade_decision": "Rating: Buy with strict entry discipline.",
                "final_trade_decision_structured": {
                    "status": "completed",
                    "action": "BUY",
                },
            }
        },
        "prices": {},
    }

    with patch("tradingagents.portfolio.memory_loader.build_selection_memory", return_value=None):
        result = node(state)

    prioritized = json.loads(result["prioritized_candidates"])
    assert [candidate["ticker"] for candidate in prioritized] == ["RMAX"]
    assert prioritized[0]["candidate_final_trade_decision_structured"]["action"] == "BUY"


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


class TestRecordPmDecisionsNode:
    def test_buy_order_records_high_confidence_portfolio_decision(self):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        result = node(
            _make_record_pm_decisions_state(
                {"buys": [{"ticker": " xom ", "rationale": "Energy play"}]}
            )
        )

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_called_once_with(
            "XOM",
            "2026-03-20",
            "BUY",
            rationale="Energy play",
            confidence="high",
            source="portfolio",
            run_id="run-test-123",
        )

    def test_sell_order_records_medium_confidence_portfolio_decision(self):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        result = node(
            _make_record_pm_decisions_state(
                {"sells": [{"ticker": "AAPL", "rationale": "Overvalued"}]}
            )
        )

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_called_once_with(
            "AAPL",
            "2026-03-20",
            "SELL",
            rationale="Overvalued",
            confidence="medium",
            source="portfolio",
            run_id="run-test-123",
        )

    def test_hold_records_medium_confidence_portfolio_decision(self):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        result = node(
            _make_record_pm_decisions_state(
                {"holds": [{"ticker": "MSFT", "rationale": "Thesis intact"}]}
            )
        )

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_called_once_with(
            "MSFT",
            "2026-03-20",
            "HOLD",
            rationale="Thesis intact",
            confidence="medium",
            source="portfolio",
            run_id="run-test-123",
        )

    def test_micro_memory_none_does_not_crash(self):
        setup = PortfolioGraphSetup(agents={}, micro_memory=None)
        node = setup._make_record_pm_decisions_node()

        result = node(
            _make_record_pm_decisions_state(
                {"buys": [{"ticker": "XOM", "rationale": "Energy play"}]}
            )
        )

        assert result == {"sender": "record_pm_decisions"}

    def test_record_decision_exception_does_not_crash(self):
        micro_memory = Mock()
        micro_memory.record_decision.side_effect = RuntimeError("memory unavailable")
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        result = node(
            _make_record_pm_decisions_state(
                {"buys": [{"ticker": "XOM", "rationale": "Energy play"}]}
            )
        )

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_called_once()

    def test_execution_error_skips_memory_write(self, caplog):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()
        state = _make_record_pm_decisions_state(
            {"buys": [{"ticker": "XOM", "rationale": "Energy play"}]}
        )
        state["execution_result"] = json.dumps(
            {"error": "trade executor failed", "executed_trades": []}
        )

        with caplog.at_level(logging.ERROR):
            result = node(state)

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_not_called()
        assert "execute_trades failed" in caplog.text

    def test_missing_analysis_date_skips_memory_write(self, caplog):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()
        state = _make_record_pm_decisions_state(
            {"buys": [{"ticker": "XOM", "rationale": "Energy play"}]}
        )
        state["analysis_date"] = ""

        with caplog.at_level(logging.ERROR):
            result = node(state)

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_not_called()
        assert "analysis_date is missing" in caplog.text

    def test_empty_decision_lists_do_not_record_memory(self):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        result = node(_make_record_pm_decisions_state({"buys": [], "sells": [], "holds": []}))

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_not_called()

    def test_record_decision_partial_failures_log_summary(self, caplog):
        micro_memory = Mock()
        micro_memory.record_decision.side_effect = [RuntimeError("first failed"), None]
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        with caplog.at_level(logging.ERROR):
            result = node(
                _make_record_pm_decisions_state(
                    {
                        "buys": [{"ticker": "XOM", "rationale": "Energy play"}],
                        "holds": [{"ticker": "MSFT", "rationale": "Keep holding"}],
                    }
                )
            )

        assert result == {"sender": "record_pm_decisions"}
        assert micro_memory.record_decision.call_count == 2
        assert "failed to record 1 PM decision" in caplog.text

    def test_malformed_pm_decision_json_does_not_crash(self):
        micro_memory = Mock()
        setup = PortfolioGraphSetup(agents={}, micro_memory=micro_memory)
        node = setup._make_record_pm_decisions_node()

        result = node(_make_record_pm_decisions_state("{not-json"))

        assert result == {"sender": "record_pm_decisions"}
        micro_memory.record_decision.assert_not_called()

    def test_graph_topology_records_pm_decisions_after_execute_trades(self):
        agents = {
            "review_holdings": lambda state: {"sender": "review_holdings"},
            "macro_summary": lambda state: {"sender": "macro_summary"},
            "micro_summary": lambda state: {"sender": "micro_summary"},
            "pm_decision": lambda state: {"sender": "pm_decision"},
        }
        graph = PortfolioGraphSetup(agents=agents, micro_memory=Mock()).setup_graph().get_graph()

        edges = {(edge.source, edge.target) for edge in graph.edges}

        assert ("execute_trades", "record_pm_decisions") in edges
        assert ("record_pm_decisions", "__end__") in edges
        assert ("execute_trades", "__end__") not in edges

    def test_graph_topology_matches_active_guarded_path(self):
        """Compiled graph must enforce current guarded portfolio execution path."""
        agents = {
            "review_holdings": lambda state: {"sender": "review_holdings"},
            "macro_summary": lambda state: {"sender": "macro_summary"},
            "micro_summary": lambda state: {"sender": "micro_summary"},
            "pm_decision": lambda state: {"sender": "pm_decision"},
        }
        graph = PortfolioGraphSetup(agents=agents, micro_memory=Mock()).setup_graph().get_graph()

        edges = {(edge.source, edge.target) for edge in graph.edges}

        # Active backbone before fan-out
        assert ("load_portfolio", "compute_risk") in edges
        assert ("compute_risk", "portfolio_integrity_guard") in edges
        assert ("portfolio_integrity_guard", "review_holdings") in edges
        assert ("review_holdings", "prioritize_candidates") in edges

        # Active tail after fan-in
        assert ("make_pm_decision", "rescale_buys") in edges
        assert ("rescale_buys", "cash_sweep") in edges
        assert ("cash_sweep", "pm_decision_postcheck") in edges
        assert ("pm_decision_postcheck", "execute_trades") in edges

        # Ensure stale direct edges are not reintroduced
        assert ("compute_risk", "review_holdings") not in edges
        assert ("make_pm_decision", "cash_sweep") not in edges
        assert ("cash_sweep", "execute_trades") not in edges

    def test_candidate_handoff_guard_is_wired_in_graph(self):
        """Verify candidate_handoff_guard node is wired between prioritize_candidates and summaries."""
        agents = {
            "review_holdings": lambda state: {"sender": "review_holdings"},
            "macro_summary": lambda state: {"sender": "macro_summary"},
            "micro_summary": lambda state: {"sender": "micro_summary"},
            "pm_decision": lambda state: {"sender": "pm_decision"},
        }
        graph = PortfolioGraphSetup(agents=agents, micro_memory=Mock()).setup_graph().get_graph()

        edges = {(edge.source, edge.target) for edge in graph.edges}

        # Guard is wired after prioritize_candidates
        assert ("prioritize_candidates", "candidate_handoff_guard") in edges

        # Guard fans out to both summary nodes
        assert ("candidate_handoff_guard", "macro_summary") in edges
        assert ("candidate_handoff_guard", "micro_summary") in edges

        # Ensure old direct edges from prioritize_candidates are removed
        assert ("prioritize_candidates", "macro_summary") not in edges
        assert ("prioritize_candidates", "micro_summary") not in edges
