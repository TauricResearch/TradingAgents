"""Environment-based data vendor selection (#1628)."""

import json
import os
import subprocess
import sys

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.default_config import build_default_config


@pytest.fixture(autouse=True)
def _clear_vendor_env(monkeypatch):
    for name in os.environ:
        if name.startswith("TRADINGAGENTS_VENDOR_"):
            monkeypatch.delenv(name)


@pytest.mark.parametrize("category", [
    "core_stock_apis", "technical_indicators", "fundamental_data",
    "news_data", "macro_data", "prediction_markets",
])
def test_category_override(monkeypatch, category):
    defaults = build_default_config()["data_vendors"]
    monkeypatch.setenv(f"TRADINGAGENTS_VENDOR_{category.upper()}", "default")
    expected = {**defaults, category: "default"}
    assert build_default_config()["data_vendors"] == expected


@pytest.mark.parametrize("value", ["", "  \t "])
def test_blank_override_keeps_default(monkeypatch, value):
    defaults = build_default_config()["data_vendors"]
    monkeypatch.setenv("TRADINGAGENTS_VENDOR_NEWS_DATA", value)
    assert build_default_config()["data_vendors"] == defaults


def test_config_builds_have_independent_vendors(monkeypatch):
    first = build_default_config()
    monkeypatch.setenv("TRADINGAGENTS_VENDOR_NEWS_DATA", "alpha_vantage")
    second = build_default_config()
    assert second["data_vendors"]["news_data"] == "alpha_vantage"
    assert first["data_vendors"]["news_data"] == "yfinance"
    monkeypatch.delenv("TRADINGAGENTS_VENDOR_NEWS_DATA")
    assert build_default_config()["data_vendors"]["news_data"] == "yfinance"


def test_environment_chain_reaches_router_in_order(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_VENDOR_CORE_STOCK_APIS", " alpha_vantage, yfinance ")
    calls = []

    def primary(symbol):
        calls.append("alpha_vantage")
        raise NoMarketDataError(symbol, symbol, "no rows")

    def fallback(symbol):
        calls.append("yfinance")
        return "prices"

    monkeypatch.setitem(router.VENDOR_METHODS, "get_stock_data", {
        "yfinance": fallback, "alpha_vantage": primary,
    })
    with run_config(build_default_config()):
        assert router.route_to_vendor("get_stock_data", "AAPL") == "prices"
    assert calls == ["alpha_vantage", "yfinance"]


def test_tool_override_takes_precedence(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_VENDOR_NEWS_DATA", "alpha_vantage")
    config = build_default_config()
    config["tool_vendors"]["get_news"] = "yfinance"
    with run_config(config):
        assert router.get_vendor("news_data") == "alpha_vantage"
        assert router.get_vendor("news_data", "get_news") == "yfinance"


def test_unknown_vendor_uses_router_validation(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_VENDOR_CORE_STOCK_APIS", "misspelled_vendor")
    with run_config(build_default_config()), pytest.raises(ValueError, match="misspelled_vendor"):
        router.route_to_vendor("get_stock_data", "AAPL")


@pytest.mark.parametrize("shell_vendor", [None, "yfinance,alpha_vantage"])
def test_dotenv_vendor_reaches_cli_and_explicit_config_wins(tmp_path, shell_vendor):
    (tmp_path / ".env").write_text(
        "TRADINGAGENTS_VENDOR_NEWS_DATA=alpha_vantage\n", encoding="utf-8",
    )
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("TRADINGAGENTS_") and key != "PYTHON_DOTENV_DISABLED"}
    if shell_vendor is not None:
        env["TRADINGAGENTS_VENDOR_NEWS_DATA"] = shell_vendor
    script = """
import json
from cli.run import _build_run_config
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.router import get_vendor
from tradingagents.default_config import DEFAULT_CONFIG

selections = {key: DEFAULT_CONFIG[key] for key in (
    "quick_think_llm", "deep_think_llm", "backend_url", "llm_provider", "output_language"
)}
selections["research_depth"] = 1
config = _build_run_config(selections, checkpoint=None)
with run_config(config):
    cli_vendor = get_vendor("news_data", "get_news")
with run_config({"data_vendors": {"news_data": "yfinance"}}):
    explicit_vendor = get_vendor("news_data", "get_news")
print(json.dumps([cli_vendor, explicit_vendor]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True, check=True, timeout=30,
    )
    assert json.loads(result.stdout) == [shell_vendor or "alpha_vantage", "yfinance"]
