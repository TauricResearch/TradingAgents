"""End-to-end final-state connection to the isolated, fail-closed paper gate."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree
from tradingagents.trade_guard import MarketSnapshot, PortfolioSnapshot, TradeIntent
from tradingagents.trade_guard.review import (
    agent_decision_review,
    attach_decision_review,
    read_trader_action,
    validate_paper_decision,
)

NOW = datetime(2026, 10, 9, 16, 0, tzinfo=UTC)


def crypto_state(**overrides):
    state = {
        "asset_type": "crypto",
        "company_of_interest": "BTC-USD",
        "trade_date": "2026-10-09",
        "trader_investment_plan": "**Action**: Sell\n\n**Entry Price**: 84500",
        "final_trade_decision": "**Rating**: Sell\n\n**Investment Thesis**: Bearish.",
    }
    state.update(overrides)
    return state


def paper_objects(**changes):
    fields = {
        "symbol": "BTC-USD",
        "market": "PERPETUAL",
        "action": "SHORT_OPEN",
        "order_type": "LIMIT",
        "quantity_base": "0.025",
        "limit_price": "84500",
        "stop_loss": "87800",
        "take_profit": "80000",
        "idempotency_key": "review-demo-01",
    }
    fields.update(changes)
    return (
        TradeIntent(**fields),
        MarketSnapshot(symbol="BTC-USD", price="82403", observed_at=NOW, source="test-feed"),
        PortfolioSnapshot(equity_quote="100000", free_quote="10000", free_base="0"),
    )


@pytest.mark.unit
def test_an_agent_sell_is_always_blocked_without_explicit_order_and_snapshots():
    review = agent_decision_review(crypto_state())
    assert review["status"] == "BLOCKED"
    assert review["approved"] is False
    assert review["execution_mode"] == "NONE"
    assert review["portfolio_rating"] == "Sell"
    assert "SELL_DOES_NOT_IDENTIFY_SPOT_EXIT_OR_SHORT" in review["reasons"]
    assert "NO_EXPLICIT_TRADE_INTENT" in review["reasons"]


@pytest.mark.unit
def test_prior_report_fields_cannot_inject_paper_approval():
    state = crypto_state(approved=True, execution_mode="LIVE", trade_guard_review={"approved": True})
    attach_decision_review(state)
    assert state["trade_guard_review"]["approved"] is False
    assert "BLOCKED" in state["trade_guard_report"]


@pytest.mark.unit
def test_hold_and_unreadable_outputs_are_not_autotrades():
    for state in (
        crypto_state(final_trade_decision="**Rating**: Hold"),
        crypto_state(final_trade_decision="unclear"),
        crypto_state(trader_investment_plan="I lean Sell but might Hold"),
    ):
        review = agent_decision_review(state)
        assert review["approved"] is False
        assert review["status"] == "BLOCKED"


@pytest.mark.unit
def test_trader_parser_does_not_infer_order_from_prose():
    assert read_trader_action("SELL around 84500") is None
    assert read_trader_action("**Action**: Sell\n**Reasoning**: bearish") == "Sell"
    assert read_trader_action("**Action**: Hold") == "Hold"


@pytest.mark.unit
def test_stock_analyses_are_unmodified():
    state = crypto_state(asset_type="stock")
    attach_decision_review(state)
    assert "trade_guard_review" not in state
    assert "trade_guard_report" not in state


@pytest.mark.unit
def test_record_decision_annotates_crypto_before_logging():
    graph = object.__new__(TradingAgentsGraph)
    recorded = []
    graph._log_state = lambda date, state: recorded.append(("log", state["trade_guard_review"]))
    graph.memory_log = SimpleNamespace(
        store_decision=lambda **kw: recorded.append(("memory", kw["rating"]))
    )
    state = crypto_state()
    graph.record_decision("BTC-USD", "2026-10-09", state)
    assert recorded[0][0] == "log" and recorded[0][1]["approved"] is False
    assert recorded[1] == ("memory", "Sell")


@pytest.mark.unit
def test_saved_report_includes_guard_in_md_html_and_own_file(tmp_path):
    state = crypto_state()
    attach_decision_review(state)
    full = write_report_tree(state, "BTC-USD", tmp_path, html=True).read_text()
    assert "VI. Paper Trade Guard" in full
    assert "BLOCKED" in full
    assert (tmp_path / "6_trade_guard" / "review.md").exists()
    page = (tmp_path / "complete_report.html").read_text()
    assert "Paper Trade Guard" in page
    assert "BLOCKED" in page


@pytest.mark.unit
def test_explicit_paper_intent_reaches_numeric_guard_with_agent_agreement():
    trade, quote, portfolio = paper_objects()
    verdict = validate_paper_decision(crypto_state(), trade, quote, portfolio, now=NOW)
    assert verdict.approved
    assert verdict.reasons == ()


@pytest.mark.unit
def test_numeric_guard_rejection_is_preserved():
    trade, quote, portfolio = paper_objects(stop_loss="80000")
    verdict = validate_paper_decision(crypto_state(), trade, quote, portfolio, now=NOW)
    assert not verdict.approved
    assert "SHORT_PRICE_LEVELS_INVALID" in verdict.reasons


@pytest.mark.unit
def test_conflicting_agent_action_blocks_even_good_math():
    trade, quote, portfolio = paper_objects()
    state = crypto_state(trader_investment_plan="**Action**: Buy")
    verdict = validate_paper_decision(state, trade, quote, portfolio, now=NOW)
    assert not verdict.approved
    assert "TRADER_PORTFOLIO_DIRECTION_CONFLICT" in verdict.reasons


@pytest.mark.unit
def test_missing_direction_does_not_become_approval():
    trade, quote, portfolio = paper_objects()
    verdict = validate_paper_decision(
        crypto_state(final_trade_decision="**Rating**: Hold"),
        trade, quote, portfolio, now=NOW,
    )
    assert "NO_CONSISTENT_ACTIONABLE_AGENT_DIRECTION" in verdict.reasons
    assert not verdict.approved


@pytest.mark.unit
def test_unrelated_symbol_is_rejected_even_with_valid_quote_for_order():
    trade, quote, portfolio = paper_objects()
    verdict = validate_paper_decision(
        crypto_state(company_of_interest="ETH-USD"), trade, quote, portfolio, now=NOW,
    )
    assert not verdict.approved
    assert "ORDER_SYMBOL_DIFFERS_FROM_ANALYSIS" in verdict.reasons


@pytest.mark.unit
def test_stock_signal_cannot_use_crypto_gate():
    trade, quote, portfolio = paper_objects()
    verdict = validate_paper_decision(
        crypto_state(asset_type="stock"), trade, quote, portfolio, now=NOW,
    )
    assert not verdict.approved
    assert "NOT_A_CRYPTO_ANALYSIS" in verdict.reasons
