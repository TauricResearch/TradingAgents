"""Tests for ticker_price alert functionality."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from web.server.indicators import (
    IndicatorDefinition,
    add_indicator,
    read_indicators,
    remove_indicator,
    reset_indicator,
    update_indicator,
    write_indicators,
)


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path, monkeypatch):
    """Point storage at a temp dir so tests never touch real data."""
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(tmp_path / "cache"))
    from web.server import storage
    storage.init_settings(data_dir=str(tmp_path / "data"), cache_dir=str(tmp_path / "cache"))


# --- data-model tests -------------------------------------------------------

def test_indicator_definition_with_ticker():
    ind = IndicatorDefinition(
        id="test-spy",
        kind="ticker_price",
        name="SPY Above 750",
        description="Alert when SPY reaches 750",
        threshold=750,
        comparator="above",
        unit="price",
        ticker="SPY",
        triggered=False,
    )
    assert ind.ticker == "SPY"
    assert ind.triggered is False
    assert ind.kind == "ticker_price"


def test_indicator_definition_triggered_default():
    ind = IndicatorDefinition(
        id="x",
        kind="vix",
        name="VIX",
        description="",
        threshold=30,
        comparator="above",
        unit="index",
    )
    assert ind.triggered is False
    assert ind.ticker is None


# --- add / remove / update / reset round-trip -------------------------------

def test_add_and_remove_ticker_price_alert():
    mock_ticker = MagicMock()
    mock_ticker.fast_info = {"lastPrice": 500.0}
    with patch("web.server.indicators.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        ind = add_indicator({
            "kind": "ticker_price",
            "ticker": "SPY",
            "name": "SPY Test",
            "threshold": 750,
            "comparator": "above",
        })
    assert ind.ticker == "SPY"
    assert ind.kind == "ticker_price"
    assert ind.triggered is False

    all_inds = read_indicators()
    assert any(i.id == ind.id for i in all_inds)

    removed = remove_indicator(ind.id)
    assert removed is True

    all_inds = read_indicators()
    assert not any(i.id == ind.id for i in all_inds)


def test_update_ticker_price_threshold():
    mock_ticker = MagicMock()
    mock_ticker.fast_info = {"lastPrice": 500.0}
    with patch("web.server.indicators.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        ind = add_indicator({
            "kind": "ticker_price",
            "ticker": "AAPL",
            "name": "AAPL Test",
            "threshold": 200,
            "comparator": "above",
        })

    updated = update_indicator(ind.id, {"threshold": 250})
    assert updated is not None
    assert updated.threshold == 250
    assert updated.ticker == "AAPL"


def test_reset_indicator():
    ind = IndicatorDefinition(
        id="test-reset",
        kind="ticker_price",
        name="SPY Above 750",
        description="Alert when SPY reaches 750",
        threshold=750,
        comparator="above",
        unit="price",
        ticker="SPY",
        triggered=True,
    )
    write_indicators([ind])

    result = reset_indicator("test-reset")
    assert result is not None
    assert result.triggered is False

    persisted = read_indicators()
    assert len(persisted) == 1
    assert persisted[0].triggered is False


def test_reset_already_inactive_indicator():
    ind = IndicatorDefinition(
        id="test-active",
        kind="ticker_price",
        name="SPY Alert",
        description="",
        threshold=750,
        comparator="above",
        unit="price",
        ticker="SPY",
        triggered=False,
    )
    write_indicators([ind])

    result = reset_indicator("test-active")
    assert result is not None
    assert result.triggered is False


def test_reset_nonexistent_indicator():
    result = reset_indicator("does-not-exist")
    assert result is None


# --- add_indicator validation ------------------------------------------------

def test_add_ticker_price_requires_ticker():
    with pytest.raises(ValueError, match="ticker is required"):
        add_indicator({"kind": "ticker_price"})


def test_add_ticker_price_rejects_invalid_ticker():
    mock_ticker = MagicMock()
    mock_ticker.fast_info.__getitem__ = MagicMock(side_effect=KeyError("no such key"))
    with patch("web.server.indicators.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        with pytest.raises(ValueError, match="not found"):
            add_indicator({"kind": "ticker_price", "ticker": "INVALID"})


def test_add_ticker_price_rejects_duplicate():
    mock_ticker = MagicMock()
    mock_ticker.fast_info = {"lastPrice": 100.0}
    with patch("web.server.indicators.yf") as mock_yf:
        mock_yf.Ticker.return_value = mock_ticker
        add_indicator({
            "kind": "ticker_price",
            "ticker": "SPY",
            "threshold": 750,
            "comparator": "above",
        })
        with pytest.raises(ValueError, match="already exists"):
            add_indicator({
                "kind": "ticker_price",
                "ticker": "SPY",
                "threshold": 750,
                "comparator": "above",
            })
