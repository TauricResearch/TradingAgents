from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import _merge_with_default_config


def test_merge_with_default_config_keeps_required_defaults():
    merged = _merge_with_default_config({
        "llm_provider": "anthropic",
        "backend_url": "https://example.com/api",
    })

    assert merged["llm_provider"] == "anthropic"
    assert merged["backend_url"] == "https://example.com/api"
    assert merged["project_dir"] == DEFAULT_CONFIG["project_dir"]
    assert merged["results_dir"] == DEFAULT_CONFIG["results_dir"]


def test_merge_with_default_config_merges_nested_vendor_settings():
    merged = _merge_with_default_config({
        "data_vendors": {
            "news_data": "alpha_vantage",
        },
        "tool_vendors": {
            "get_stock_data": "alpha_vantage",
        },
    })

    assert merged["data_vendors"]["news_data"] == "alpha_vantage"
    assert merged["data_vendors"]["core_stock_apis"] == DEFAULT_CONFIG["data_vendors"]["core_stock_apis"]
    assert merged["tool_vendors"]["get_stock_data"] == "alpha_vantage"
