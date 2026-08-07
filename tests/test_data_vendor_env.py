"""Tests for the TRADINGAGENTS_DATA_VENDOR env-var overlay.

Unlike the other TRADINGAGENTS_* knobs, this one targets the nested
``data_vendors`` dict and is applied to BOTH the ``core_stock_apis`` and
``technical_indicators`` categories at once (users chose to keep prices and
indicators on one source). Opt-in: unset leaves the yfinance defaults intact.
"""

from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config_module


def _reload_with_env(monkeypatch, value=None):
    """Set/clear TRADINGAGENTS_DATA_VENDOR then reload to re-evaluate DEFAULT_CONFIG."""
    monkeypatch.delenv("TRADINGAGENTS_DATA_VENDOR", raising=False)
    if value is not None:
        monkeypatch.setenv("TRADINGAGENTS_DATA_VENDOR", value)
    return importlib.reload(default_config_module)


@pytest.mark.unit
def test_unset_keeps_yfinance_defaults(monkeypatch):
    """Opt-in: no env var leaves both categories on the yfinance default."""
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "yfinance"


@pytest.mark.unit
def test_empty_value_is_passthrough(monkeypatch):
    """An empty value must not clobber the built-in defaults."""
    dc = _reload_with_env(monkeypatch, value="")
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "yfinance"


@pytest.mark.unit
def test_schwab_chain_applies_to_both_categories(monkeypatch):
    dc = _reload_with_env(monkeypatch, value="schwab,yfinance")
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "schwab,yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "schwab,yfinance"


@pytest.mark.unit
def test_single_vendor_applies_to_both_categories(monkeypatch):
    dc = _reload_with_env(monkeypatch, value="alpha_vantage")
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "alpha_vantage"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "alpha_vantage"


@pytest.mark.unit
def test_whitespace_is_trimmed(monkeypatch):
    dc = _reload_with_env(monkeypatch, value=" schwab , yfinance ")
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "schwab,yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "schwab,yfinance"


@pytest.mark.unit
def test_other_categories_are_untouched(monkeypatch):
    """The single value must not bleed into fundamentals/news/macro categories."""
    dc = _reload_with_env(monkeypatch, value="schwab,yfinance")
    assert dc.DEFAULT_CONFIG["data_vendors"]["fundamental_data"] == "yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["news_data"] == "yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["macro_data"] == "fred"


@pytest.mark.unit
def test_unknown_vendor_raises(monkeypatch):
    """A typo'd vendor must fail loudly at import, not silently misconfigure."""
    monkeypatch.setenv("TRADINGAGENTS_DATA_VENDOR", "yfinance,bogus")
    with pytest.raises(ValueError, match="TRADINGAGENTS_DATA_VENDOR"):
        importlib.reload(default_config_module)
    # Restore module state for subsequent tests in this process.
    monkeypatch.delenv("TRADINGAGENTS_DATA_VENDOR", raising=False)
    importlib.reload(default_config_module)


@pytest.mark.unit
def test_empty_list_entry_raises(monkeypatch):
    """A trailing/blank comma entry (e.g. 'schwab,') is rejected."""
    monkeypatch.setenv("TRADINGAGENTS_DATA_VENDOR", "schwab,")
    with pytest.raises(ValueError, match="TRADINGAGENTS_DATA_VENDOR"):
        importlib.reload(default_config_module)
    monkeypatch.delenv("TRADINGAGENTS_DATA_VENDOR", raising=False)
    importlib.reload(default_config_module)


@pytest.mark.unit
def test_get_config_reflects_env(monkeypatch):
    """End-to-end: get_config() carries the env-selected vendor into both categories."""
    dc = _reload_with_env(monkeypatch, value="schwab,yfinance")
    # Reload the config module so its cached DEFAULT_CONFIG picks up the reload.
    import tradingagents.dataflows.config as config_module

    importlib.reload(config_module)
    cfg = config_module.get_config()
    assert cfg["data_vendors"]["core_stock_apis"] == "schwab,yfinance"
    assert cfg["data_vendors"]["technical_indicators"] == "schwab,yfinance"
    # Reset for other tests.
    _reload_with_env(monkeypatch)
    importlib.reload(config_module)
    del dc
