from tradingagents.dataflows.config import get_config, reset_config, use_config


def test_config_context_isolation():
    base = get_config()
    token = use_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})
    try:
        assert get_config()["data_vendors"]["core_stock_apis"] == "alpha_vantage"
    finally:
        reset_config(token)

    assert (
        get_config()["data_vendors"].get("core_stock_apis")
        == base["data_vendors"]["core_stock_apis"]
    )


def test_nested_config_context_restores_outer():
    outer = use_config({"output_language": "Spanish"})
    try:
        inner = use_config({"output_language": "Japanese"})
        try:
            assert get_config()["output_language"] == "Japanese"
        finally:
            reset_config(inner)
        assert get_config()["output_language"] == "Spanish"
    finally:
        reset_config(outer)
