from web_app import _format_reports, _web_config


def test_web_config_uses_low_cost_defaults(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_MAX_TOKENS", raising=False)
    config = _web_config()
    assert config["max_tool_rounds"] == 3
    assert config["max_tokens"] == 2048


def test_format_reports_omits_empty_sections():
    output = _format_reports({"market_report": "Market text", "news_report": ""})
    assert "Market report" in output
    assert "Market text" in output
    assert "News report" not in output
