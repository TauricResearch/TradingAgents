"""Config isolation: get/set must not leak nested-dict references."""

import copy
import importlib
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import get_config, set_config


@pytest.mark.unit
class DataflowsConfigIsolationTests(unittest.TestCase):
    def setUp(self):
        set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))

    def test_get_config_returns_deep_copy(self):
        cfg = get_config()
        cfg["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        cfg["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        fresh = get_config()
        self.assertEqual(
            fresh["data_vendors"]["core_stock_apis"],
            "yfinance, akshare, futu, polygon",
        )
        self.assertNotIn("get_stock_data", fresh["tool_vendors"])

    def test_set_config_does_not_alias_caller_nested_dicts(self):
        custom = copy.deepcopy(default_config.DEFAULT_CONFIG)
        custom["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        custom["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        set_config(custom)

        custom["data_vendors"]["core_stock_apis"] = "yfinance"
        custom["tool_vendors"]["get_stock_data"] = "yfinance"

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")

    def test_partial_nested_update_preserves_existing_defaults(self):
        set_config(
            {
                "data_vendors": {
                    "core_stock_apis": "alpha_vantage",
                }
            }
        )

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(
            fresh["data_vendors"]["market_snapshot"],
            "yfinance, akshare, futu, polygon",
        )
        self.assertEqual(fresh["data_vendors"]["technical_indicators"], "yfinance")
        self.assertEqual(fresh["data_vendors"]["fundamental_data"], "yfinance")
        self.assertEqual(fresh["data_vendors"]["news_data"], "yfinance")

    def test_nested_dict_updates_merge_one_level_deep(self):
        set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})
        set_config({"tool_vendors": {"get_news": "alpha_vantage"}})

        fresh = get_config()
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_news"], "alpha_vantage")


def _load_interface_with_fake_optional_market_deps(monkeypatch):
    fake_yfinance = ModuleType("yfinance")
    fake_yfinance.Ticker = MagicMock()
    fake_yfinance.download = MagicMock()
    fake_yfinance.Search = MagicMock()

    fake_exceptions = ModuleType("yfinance.exceptions")
    fake_exceptions.YFRateLimitError = type("YFRateLimitError", (Exception,), {})

    fake_stockstats = ModuleType("stockstats")
    fake_stockstats.wrap = lambda data: data

    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)
    monkeypatch.setitem(sys.modules, "yfinance.exceptions", fake_exceptions)
    monkeypatch.setitem(sys.modules, "stockstats", fake_stockstats)
    sys.modules.pop("tradingagents.dataflows.stockstats_utils", None)
    sys.modules.pop("tradingagents.dataflows.y_finance", None)
    sys.modules.pop("tradingagents.dataflows.yfinance_news", None)
    sys.modules.pop("tradingagents.dataflows.yfinance_options", None)
    sys.modules.pop("tradingagents.dataflows.interface", None)
    return importlib.import_module("tradingagents.dataflows.interface")


def test_market_snapshot_default_vendor_order():
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))
    cfg = get_config()

    assert cfg["data_vendors"]["market_snapshot"] == "yfinance, akshare, futu, polygon"
    assert cfg["data_vendors"]["core_stock_apis"] == "yfinance, akshare, futu, polygon"
    assert cfg["market_data_stale_after_seconds"] == 900
    assert cfg["market_data_cache_ttl_seconds"] == 900


def test_stock_data_route_falls_back_to_akshare(monkeypatch):
    iface = _load_interface_with_fake_optional_market_deps(monkeypatch)

    calls = []

    def yfinance_fail(*args, **kwargs):
        calls.append("yfinance")
        raise iface.DataVendorError("no yfinance data")

    def akshare_ok(*args, **kwargs):
        calls.append("akshare")
        return "akshare snapshot"

    monkeypatch.setitem(
        iface.VENDOR_METHODS,
        "get_stock_data",
        {"yfinance": yfinance_fail, "akshare": akshare_ok},
    )
    monkeypatch.setattr(
        iface,
        "get_vendor",
        lambda category, method=None: "yfinance, akshare, futu, polygon",
    )

    assert iface.route_to_vendor("get_stock_data", "AAPL", "2026-06-01", "2026-06-03") == (
        "akshare snapshot"
    )
    assert calls == ["yfinance", "akshare"]


def test_market_snapshot_route_uses_fusion_provider_order(monkeypatch):
    import tradingagents.dataflows.interface as iface

    calls = []

    def fake_fused_snapshot(ticker, curr_date, **kwargs):
        calls.append((ticker, curr_date, kwargs))
        return "# Market snapshot for AAPL\n\n## Fused OHLCV Chart\n"

    monkeypatch.setattr(iface, "get_fused_market_snapshot", fake_fused_snapshot)
    cfg = get_config()
    cfg["data_vendors"]["market_snapshot"] = "yfinance, akshare, futu, polygon"
    set_config(cfg)

    out = iface.route_to_vendor("get_market_snapshot", "AAPL", "2026-06-05")

    assert "## Fused OHLCV Chart" in out
    assert calls == [
        (
            "AAPL",
            "2026-06-05",
            {"providers": ["yfinance", "akshare", "futu", "polygon"]},
        )
    ]
