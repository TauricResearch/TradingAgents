"""Preflight validation maps selected analysts -> data categories -> required
keys and reports missing sources at startup, before a run begins."""

from __future__ import annotations

import copy

import pytest

import tradingagents.default_config as default_config
from tradingagents.config_validation import (
    enforce_preflight,
    validate_config,
)


def _config(**vendor_overrides):
    cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
    cfg["data_vendors"].update(vendor_overrides)
    return cfg


@pytest.mark.unit
def test_macro_missing_fred_key_is_optional_warning():
    """News analyst without FRED_API_KEY: warned, not fatal (macro is optional)."""
    env = {}  # no FRED_API_KEY
    res = validate_config(["news"], _config(), env=env)
    assert res.ok is True
    assert "macro_data" in res.missing_optional
    assert any("macro_data" in w and "skipped" in w for w in res.warnings)


@pytest.mark.unit
def test_keyless_defaults_produce_no_warnings():
    """Default vendors are keyless (yfinance/polymarket) except macro; market +
    fundamentals + social need no keys."""
    env = {}
    res = validate_config(["market", "social", "fundamentals"], _config(), env=env)
    assert res.ok is True
    assert res.warnings == []


@pytest.mark.unit
def test_alpha_vantage_only_without_key_is_required_error():
    """Forcing a core category onto alpha_vantage with no key is a hard miss."""
    env = {}  # no ALPHA_VANTAGE_API_KEY
    cfg = _config(core_stock_apis="alpha_vantage", technical_indicators="alpha_vantage")
    res = validate_config(["market"], cfg, env=env)
    assert res.ok is False
    assert "core_stock_apis" in res.missing_required
    assert any("ALPHA_VANTAGE_API_KEY" in w for w in res.warnings)


@pytest.mark.unit
def test_alpha_vantage_with_key_present_is_ok():
    env = {"ALPHA_VANTAGE_API_KEY": "present"}
    cfg = _config(core_stock_apis="alpha_vantage")
    res = validate_config(["market"], cfg, env=env)
    assert res.ok is True


@pytest.mark.unit
def test_disabled_category_is_skipped_not_flagged():
    """An explicitly 'off' category isn't a missing source."""
    env = {}
    cfg = _config(macro_data="off", prediction_markets="off")
    res = validate_config(["news"], cfg, env=env)
    assert res.ok is True
    assert res.missing_optional == []


@pytest.mark.unit
def test_enforce_strict_raises_on_required_miss():
    env_cfg = _config(core_stock_apis="alpha_vantage")
    # enforce_preflight reads os.environ; clear the key for this check.
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {}, clear=True), \
            pytest.raises(ValueError, match="missing required data sources"):
        enforce_preflight(["market"], env_cfg, strict=True)


@pytest.mark.unit
def test_enforce_non_strict_returns_result_without_raising():
    import os
    from unittest.mock import patch

    cfg = _config(core_stock_apis="alpha_vantage")
    with patch.dict(os.environ, {}, clear=True):
        res = enforce_preflight(["market"], cfg, strict=False)
    assert res.ok is False
    assert "core_stock_apis" in res.missing_required
