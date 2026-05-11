import os

from cli.config import (
    DEFAULT_LOCAL_CONFIG_PATH,
    build_configured_selections,
    load_cli_config,
)


def test_load_cli_config_injects_api_keys_and_keeps_values(tmp_path, monkeypatch):
    config_path = tmp_path / "tradingagents.local.json"
    config_path.write_text(
        """
{
  "api_keys": {
    "MIMO_API_KEY": "json-mimo-key",
    "TAVILY_API_KEY": "",
    "TUSHARE_TOKEN": "json-tushare-token"
  },
  "llm": {
    "provider": "mimo",
    "backend_url": "https://token-plan-sgp.xiaomimimo.com/anthropic",
    "quick_think_llm": "mimo-v2.5",
    "deep_think_llm": "mimo-v2.5-pro"
  },
  "run": {
    "analysts": ["market", "news"],
    "research_depth": 1,
    "output_language": "Chinese",
    "checkpoint_enabled": false,
    "save_report": true,
    "display_report": false
  },
  "data_vendors": {
    "news_data": "tavily,yfinance,alpha_vantage"
  }
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("MIMO_API_KEY", "old-key")
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    config = load_cli_config(config_path)

    assert config["llm"]["provider"] == "mimo"
    assert config["run"]["output_language"] == "Chinese"
    assert config["data_vendors"]["news_data"].startswith("tavily")
    assert os.environ["MIMO_API_KEY"] == "json-mimo-key"
    assert os.environ["TUSHARE_TOKEN"] == "json-tushare-token"
    assert os.environ.get("TAVILY_API_KEY") != ""


def test_load_cli_config_returns_empty_when_default_file_is_absent(tmp_path):
    missing = tmp_path / DEFAULT_LOCAL_CONFIG_PATH.name

    assert load_cli_config(missing) == {}


def test_build_configured_selections_uses_config_without_prompting_for_llm():
    selections = build_configured_selections(
        {
            "llm": {
                "provider": "mimo",
                "backend_url": "https://token-plan-sgp.xiaomimimo.com/anthropic",
                "quick_think_llm": "mimo-v2.5",
                "deep_think_llm": "mimo-v2.5-pro",
            },
            "run": {
                "analysts": ["market", "social"],
                "research_depth": 1,
                "output_language": "Chinese",
                "checkpoint_enabled": True,
                "save_report": False,
                "display_report": False,
            },
        },
        ticker="002636",
        analysis_date="2026-05-01",
    )

    assert selections["ticker"] == "002636.SZ"
    assert [analyst.value for analyst in selections["analysts"]] == ["market", "social"]
    assert selections["llm_provider"] == "mimo"
    assert selections["shallow_thinker"] == "mimo-v2.5"
    assert selections["deep_thinker"] == "mimo-v2.5-pro"
    assert selections["output_language"] == "Chinese"
    assert selections["checkpoint_enabled"] is True
    assert selections["save_report"] is False
    assert selections["display_report"] is False
