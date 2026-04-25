from unittest.mock import patch


def test_gold_price_tool_defaults_to_yfinance_vendor():
    from tradingagents.agents.utils.scanner_tools import get_gold_price
    from tradingagents.dataflows.interface import VENDOR_METHODS

    with patch.dict(
        VENDOR_METHODS["get_gold_price"],
        {"yfinance": lambda: "# Gold Price Snapshot\n"},
        clear=False,
    ):
        result = get_gold_price.invoke({})

    assert "Gold Price Snapshot" in result


def test_gold_price_tool_uses_alpha_vantage_when_explicitly_selected():
    from tradingagents.agents.utils.scanner_tools import get_gold_price
    from tradingagents.dataflows.config import get_config
    from tradingagents.dataflows.interface import VENDOR_METHODS

    original_config = get_config()
    patched_config = {
        **original_config,
        "tool_vendors": {
            **original_config.get("tool_vendors", {}),
            "get_gold_price": "alpha_vantage",
        },
    }

    with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
        with patch.dict(
            VENDOR_METHODS["get_gold_price"],
            {"alpha_vantage": lambda: "# Gold Price Snapshot\n"},
            clear=False,
        ):
            result = get_gold_price.invoke({})

    assert "Gold Price Snapshot" in result


def test_market_price_tools_inherit_scanner_data_vendor_when_no_tool_override():
    from tradingagents.agents.utils.scanner_tools import get_gold_price
    from tradingagents.dataflows.config import get_config
    from tradingagents.dataflows.interface import VENDOR_METHODS

    original_config = get_config()
    patched_config = {
        **original_config,
        "data_vendors": {
            **original_config.get("data_vendors", {}),
            "scanner_data": "alpha_vantage",
        },
        "tool_vendors": {
            k: v
            for k, v in original_config.get("tool_vendors", {}).items()
            if k not in {"get_gold_price", "get_oil_prices", "get_bitcoin_price"}
        },
    }

    with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
        with patch.dict(
            VENDOR_METHODS["get_gold_price"],
            {"alpha_vantage": lambda: "# Gold Price Snapshot\n"},
            clear=False,
        ):
            result = get_gold_price.invoke({})

    assert "Gold Price Snapshot" in result


def test_oil_and_bitcoin_price_tools_use_explicit_alpha_vantage_selection():
    from tradingagents.agents.utils.scanner_tools import get_bitcoin_price, get_oil_prices
    from tradingagents.dataflows.config import get_config
    from tradingagents.dataflows.interface import VENDOR_METHODS

    original_config = get_config()
    patched_config = {
        **original_config,
        "tool_vendors": {
            **original_config.get("tool_vendors", {}),
            "get_oil_prices": "alpha_vantage",
            "get_bitcoin_price": "alpha_vantage",
        },
    }

    with patch("tradingagents.dataflows.interface.get_config", return_value=patched_config):
        with (
            patch.dict(
                VENDOR_METHODS["get_oil_prices"],
                {"alpha_vantage": lambda: "# Oil Price Snapshot\n"},
                clear=False,
            ),
            patch.dict(
                VENDOR_METHODS["get_bitcoin_price"],
                {"alpha_vantage": lambda: "# Bitcoin Price Snapshot\n"},
                clear=False,
            ),
        ):
            oil_result = get_oil_prices.invoke({})
            btc_result = get_bitcoin_price.invoke({})

    assert "Oil Price Snapshot" in oil_result
    assert "Bitcoin Price Snapshot" in btc_result
