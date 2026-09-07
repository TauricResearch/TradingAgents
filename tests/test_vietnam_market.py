"""Unit tests for Vietnam market regulations, tax model, symbol utilities, and data adapters."""

from __future__ import annotations

import pytest

from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.dataflows.vn_data import (
    calculate_vn_trade_friction,
    get_vietnam_macro_data,
    get_vietnam_regulatory_prompt,
    is_vietnam_symbol,
    normalize_vn_symbol,
)
from tradingagents.default_config import DEFAULT_CONFIG


def test_is_vietnam_symbol():
    assert is_vietnam_symbol("VNM.VN") is True
    assert is_vietnam_symbol("hpg.vn") is True
    assert is_vietnam_symbol("SSI:VN") is True
    assert is_vietnam_symbol("^VNINDEX") is True
    assert is_vietnam_symbol("VN30") is True
    assert is_vietnam_symbol("AAPL") is False
    assert is_vietnam_symbol("SPY") is False
    assert is_vietnam_symbol(None) is False


def test_normalize_vn_symbol():
    assert normalize_vn_symbol("HPG:VN") == "HPG.VN"
    assert normalize_vn_symbol("vnm.vn") == "VNM.VN"
    assert normalize_vn_symbol("VCB") == "VCB.VN"
    assert normalize_vn_symbol("FPT") == "FPT.VN"
    assert normalize_vn_symbol("AAPL") == "AAPL"


def test_normalize_symbol_vietnam():
    # Broker colon format
    assert normalize_symbol("HPG:VN") == "HPG.VN"
    assert normalize_symbol("vcb:vn") == "VCB.VN"
    # Index aliases
    assert normalize_symbol("VNINDEX") == "E1VFVN30.VN"
    assert normalize_symbol("^VNINDEX") == "E1VFVN30.VN"
    assert normalize_symbol("VN30") == "E1VFVN30.VN"


def test_default_config_vietnam_settings():
    assert DEFAULT_CONFIG["benchmark_map"][".VN"] == "E1VFVN30.VN"
    assert DEFAULT_CONFIG["vn_tax_rate_sell"] == 0.001
    assert DEFAULT_CONFIG["vn_trading_fee_rate"] == 0.0015
    assert DEFAULT_CONFIG["vn_allow_short_selling"] is False
    assert DEFAULT_CONFIG["vn_price_limit_hose"] == 0.07
    assert DEFAULT_CONFIG["vn_settlement_days"] == 2


def test_calculate_vn_trade_friction_profit():
    # Buy 100 shares at 60,000, sell at 66,000 (+10% gross gain)
    res = calculate_vn_trade_friction(
        entry_price=60_000,
        exit_price=66_000,
        shares=100,
        fee_rate=0.0015,
        tax_rate_sell=0.001,
    )
    assert res["buy_value"] == 6_000_000
    assert res["buy_fee"] == 9_000.0
    assert res["total_cost"] == 6_009_000.0

    assert res["sell_value"] == 6_600_000
    assert res["sell_fee"] == 9_900.0
    assert res["sell_tax"] == 6_600.0  # 0.1% on 6.6M
    assert res["net_proceeds"] == 6_600_000 - 9_900.0 - 6_600.0

    assert res["gross_profit"] == 600_000
    assert res["total_friction"] == 9_000.0 + 9_900.0 + 6_600.0
    assert res["net_profit"] == res["gross_profit"] - res["total_friction"]
    assert res["breakeven_gain_percent"] > 0.4


def test_calculate_vn_trade_friction_loss():
    # Buy 100 shares at 60,000, sell at 54,000 (-10% gross loss)
    res = calculate_vn_trade_friction(
        entry_price=60_000,
        exit_price=54_000,
        shares=100,
        fee_rate=0.0015,
        tax_rate_sell=0.001,
    )
    # Tax is still collected even on a loss!
    assert res["sell_tax"] == 54.0 * 100  # 0.1% of 5,400,000 = 5,400
    assert res["net_profit"] < res["gross_profit"]


def test_build_instrument_context_injects_vn_directives():
    context = build_instrument_context("VNM.VN")
    assert "VIETNAM MARKET REGULATORY & TAX DIRECTIVES" in context
    assert "BAN ON SHORT SELLING" in context
    assert "0.1% Personal Income Tax" in context
    assert "T+2" in context

    # US ticker should not have VN directives
    us_context = build_instrument_context("AAPL")
    assert "VIETNAM MARKET REGULATORY & TAX DIRECTIVES" not in us_context


def test_route_to_vendor_vn_macro():
    macro_report = route_to_vendor("get_macro_indicators", "vietnam_macro", "2026-09-07")
    assert "State Bank of Vietnam" in macro_report
    assert "Lãi suất tái cấp vốn" in macro_report
    assert "VN-Index" in macro_report


def test_paper_trading_engine(tmp_path):
    from tradingagents.dataflows.dnse_client import PaperTradingEngine

    storage = tmp_path / "paper_test.json"
    engine = PaperTradingEngine(storage_path=storage, initial_cash=10_000_000.0)

    # 1. Invalid lot size (not multiple of 100)
    res_bad_lot = engine.place_buy_order("HPG", 28000, 50)
    assert res_bad_lot["success"] is False
    assert "lô chẵn 100" in res_bad_lot["message"]

    # 2. Insufficient cash
    res_no_cash = engine.place_buy_order("HPG", 28000, 100000)
    assert res_no_cash["success"] is False
    assert "Số dư không đủ" in res_no_cash["message"]

    # 3. Valid Buy 200 shares HPG at 28,000 VND
    res_buy = engine.place_buy_order("HPG", 28000, 200)
    assert res_buy["success"] is True
    assert engine.state["portfolio"]["HPG.VN"]["quantity"] == 200
    assert engine.state["cash"] < 10_000_000.0

    # 4. Sell rejection on short selling (attempt to sell 300 when only having 200)
    res_short = engine.place_sell_order("HPG", 30000, 300)
    assert res_short["success"] is False
    assert "Cấm bán khống" in res_short["message"]

    # 5. Valid Sell 200 shares HPG at 30,000 VND
    res_sell = engine.place_sell_order("HPG", 30000, 200)
    assert res_sell["success"] is True
    assert "HPG.VN" not in engine.state["portfolio"]
    assert res_sell["order"]["tax"] == 30000 * 200 * 0.001  # 0.1% tax on sell
    assert engine.state["cash"] > 10_000_000.0  # Profitable trade

