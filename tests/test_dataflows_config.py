"""Config isolation: get/set must not leak nested-dict references."""

import copy
import unittest
from unittest.mock import patch

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import get_config, set_config


def _base_default_config():
    cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
    cfg["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
    }
    cfg["tool_vendors"] = {}
    return cfg


@pytest.mark.unit
class DataflowsConfigIsolationTests(unittest.TestCase):
    def setUp(self):
        set_config(_base_default_config())

    def test_get_config_returns_deep_copy(self):
        cfg = get_config()
        cfg["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        cfg["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "yfinance")
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
        self.assertEqual(fresh["data_vendors"]["technical_indicators"], "yfinance")
        self.assertEqual(fresh["data_vendors"]["fundamental_data"], "yfinance")
        self.assertEqual(fresh["data_vendors"]["news_data"], "yfinance")

    def test_nested_dict_updates_merge_one_level_deep(self):
        set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})
        set_config({"tool_vendors": {"get_news": "alpha_vantage"}})

        fresh = get_config()
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_news"], "alpha_vantage")

    def test_data_vendor_env_override_applies_to_all_categories(self):
        with patch.dict(
            "os.environ",
            {"TRADINGAGENTS_DATA_VENDOR": "alpha_vantage"},
            clear=True,
        ):
            cfg = default_config._apply_env_overrides(_base_default_config())

        self.assertEqual(cfg["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(cfg["data_vendors"]["technical_indicators"], "alpha_vantage")
        self.assertEqual(cfg["data_vendors"]["fundamental_data"], "alpha_vantage")
        self.assertEqual(cfg["data_vendors"]["news_data"], "alpha_vantage")

    def test_category_data_vendor_env_override_wins_over_global_vendor(self):
        with patch.dict(
            "os.environ",
            {
                "TRADINGAGENTS_DATA_VENDOR": "alpha_vantage",
                "TRADINGAGENTS_NEWS_DATA_VENDOR": "yfinance",
            },
            clear=True,
        ):
            cfg = default_config._apply_env_overrides(_base_default_config())

        self.assertEqual(cfg["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(cfg["data_vendors"]["news_data"], "yfinance")

    def test_tool_vendor_env_override_uses_method_name_suffix(self):
        with patch.dict(
            "os.environ",
            {"TRADINGAGENTS_TOOL_VENDOR_GET_STOCK_DATA": "alpha_vantage"},
            clear=True,
        ):
            cfg = default_config._apply_env_overrides(_base_default_config())

        self.assertEqual(cfg["tool_vendors"]["get_stock_data"], "alpha_vantage")
