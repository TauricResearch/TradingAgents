import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_build_run_config_translates_research_depth():
    from web.settings import build_run_config
    cfg = build_run_config({"research_depth": 3})
    assert cfg["max_debate_rounds"] == 3
    assert cfg["max_risk_discuss_rounds"] == 3


def test_build_run_config_removes_research_depth_key():
    from web.settings import build_run_config
    cfg = build_run_config({"research_depth": 1})
    assert "research_depth" not in cfg


def test_build_run_config_deep_merges_data_vendors():
    from web.settings import build_run_config
    cfg = build_run_config({"data_vendors": {"core_stock_apis": "alpha_vantage"}})
    assert cfg["data_vendors"]["core_stock_apis"] == "alpha_vantage"
    assert "technical_indicators" in cfg["data_vendors"]


def test_build_run_config_preserves_tool_vendors():
    from web.settings import build_run_config
    cfg = build_run_config({})
    assert "tool_vendors" in cfg


def test_save_and_load_settings(tmp_path):
    from web.settings import save_settings, load_settings
    settings_file = tmp_path / "web_config.json"
    data = {"llm_provider": "openai", "research_depth": 3}
    save_settings(data, path=settings_file)
    loaded = load_settings(path=settings_file)
    assert loaded["llm_provider"] == "openai"
    assert loaded["research_depth"] == 3


def test_load_settings_returns_defaults_when_file_missing(tmp_path):
    from web.settings import load_settings, DEFAULT_WEB_SETTINGS
    missing = tmp_path / "no_such_file.json"
    loaded = load_settings(path=missing)
    assert loaded == DEFAULT_WEB_SETTINGS
