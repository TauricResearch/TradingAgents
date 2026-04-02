from tradingagents.instruments import (
    is_equity_pipeline_supported,
    normalize_symbol,
    resolve_instrument,
)
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup


def test_normalize_symbol_preserves_exchange_suffix():
    assert normalize_symbol(" cnc.to ") == "CNC.TO"


def test_resolve_common_stock():
    instrument = resolve_instrument("AAPL", source_context="test")
    assert instrument.instrument_key == "equity:AAPL"
    assert instrument.asset_class == "equity"
    assert instrument.instrument_type == "common_stock"
    assert is_equity_pipeline_supported(instrument) is True


def test_resolve_broad_market_etf():
    instrument = resolve_instrument("SPY")
    assert instrument.instrument_key == "etf:SPY"
    assert instrument.asset_class == "etf"
    assert instrument.instrument_type == "broad_market_etf"
    assert instrument.is_etf is True
    assert is_equity_pipeline_supported(instrument) is False


def test_resolve_inverse_and_leveraged_etf():
    instrument = resolve_instrument("SQQQ")
    assert instrument.instrument_key == "etf:SQQQ"
    assert instrument.instrument_type == "leveraged_etf"
    assert instrument.is_inverse is True
    assert instrument.is_leveraged is True


def test_resolve_treasury_etf():
    instrument = resolve_instrument("SGOV")
    assert instrument.instrument_key == "etf:SGOV"
    assert instrument.instrument_type == "treasury_etf"


def test_resolve_crypto_coin():
    instrument = resolve_instrument("BTC")
    assert instrument.instrument_key == "crypto:BTC"
    assert instrument.asset_class == "crypto"
    assert instrument.instrument_type == "coin"
    assert is_equity_pipeline_supported(instrument) is False


def test_resolve_index():
    instrument = resolve_instrument("^GSPC")
    assert instrument.instrument_key == "index:^GSPC"
    assert instrument.asset_class == "index"
    assert instrument.instrument_type == "index"


def test_propagator_initial_state_includes_instrument_metadata():
    state = Propagator().create_initial_state("SPY", "2026-01-01", run_id="run-001")
    assert state["run_id"] == "run-001"
    assert state["instrument_key"] == "etf:SPY"
    assert state["asset_class"] == "etf"
    assert state["instrument_type"] == "broad_market_etf"
    assert state["analysis_status"] == "pending"
    assert state["research_packet_summary"] == ""
    assert state["investment_debate_state"]["summary"] == ""
    assert state["risk_debate_state"]["summary"] == ""


def test_instrument_preflight_aborts_non_stock():
    node = GraphSetup._make_instrument_preflight_node()
    result = node({"company_of_interest": "SPY"})
    assert result["analysis_status"] == "aborted"
    assert result["terminal_action"] == "UNSUPPORTED_INSTRUMENT_TYPE"
    assert "[CRITICAL ABORT]" in result["market_report"]


def test_instrument_preflight_allows_common_stock():
    node = GraphSetup._make_instrument_preflight_node()
    result = node({"company_of_interest": "AAPL"})
    assert result["instrument_key"] == "equity:AAPL"
    assert "analysis_status" not in result


def test_route_after_preflight_sends_aborted_runs_to_end():
    assert GraphSetup._route_after_preflight({"analysis_status": "aborted"}, "Market Analyst") == "END"
    assert GraphSetup._route_after_preflight({"analysis_status": "pending"}, "Market Analyst") == "Market Analyst"
