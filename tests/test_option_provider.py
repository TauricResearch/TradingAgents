"""Unit tests for the Sina ETF option provider."""

from __future__ import annotations

import pytest

from tradingagents.dataflows import option_provider
from tradingagents.dataflows.china_data import ChinaDataUnavailableError


def _tquote_vals():
    v = [""] * 45
    v[1] = "0.12"
    v[2] = "0.13"
    v[3] = "0.14"
    v[5] = "5000"
    v[7] = "2.50"
    v[37] = "50ETF购2月2500"
    v[41] = "1000"
    return v


def test_option_tquote_parses(monkeypatch):
    monkeypatch.setattr(option_provider, "_sina_opt_list", lambda param: _tquote_vals())

    report = option_provider.get_a_share_option_tquote("10000001")

    assert "Source: sina" in report
    assert "50ETF购2月2500" in report
    assert "Strike" in report  # column header (CSV formats 2.50 float as 2.5)


def test_option_tquote_raises_on_empty(monkeypatch):
    monkeypatch.setattr(option_provider, "_sina_opt_list", lambda param: [])
    with pytest.raises(ChinaDataUnavailableError, match="no T-quote"):
        option_provider.get_a_share_option_tquote("10000001")


def test_option_greeks_parses(monkeypatch):
    # raw[1:4] are empty strings that must be skipped by the parser
    raw = ["50ETF购2月2500", "", "", "", "1000", "0.5", "0.01", "-0.02", "0.17", "0.1735", "0.15", "0.12", "10006", "2.50", "0.13", "0.128"]
    monkeypatch.setattr(option_provider, "_sina_opt_list", lambda param: raw)

    report = option_provider.get_a_share_option_greeks("10000001")

    assert "Source: sina" in report
    assert "Delta" in report
    assert "0.1735" in report  # IV


def test_option_greeks_raises_on_empty(monkeypatch):
    monkeypatch.setattr(option_provider, "_sina_opt_list", lambda param: [])
    with pytest.raises(ChinaDataUnavailableError, match="no Greeks"):
        option_provider.get_a_share_option_greeks("10000001")
