# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for pykrx_vendor.

Unit tests run unconditionally (no network).
Smoke tests are network-gated by RUN_NETWORK_TESTS=1 and require pykrx installed.
"""

import importlib.util
import os

import pytest

from tradingagents.dataflows.pykrx_vendor import _yyyymmdd


# ---------------------------------------------------------------------------
# Unit tests — no network, no pykrx required
# ---------------------------------------------------------------------------


def test_yyyymmdd_zero_padded():
    assert _yyyymmdd("2024-01-02") == "20240102"


def test_yyyymmdd_rejects_unpadded():
    with pytest.raises(ValueError):
        _yyyymmdd("2024-1-2")


def test_yyyymmdd_rejects_garbage():
    with pytest.raises(ValueError):
        _yyyymmdd("not-a-date")


# ---------------------------------------------------------------------------
# Smoke tests — network-gated and pykrx-gated
# ---------------------------------------------------------------------------

NETWORK = os.getenv("RUN_NETWORK_TESTS") == "1"
HAS_PYKRX = importlib.util.find_spec("pykrx") is not None
HAS_KRX_CREDS = bool(os.getenv("KRX_ID")) and bool(os.getenv("KRX_PW"))
smoke_gate = pytest.mark.skipif(
    not (NETWORK and HAS_PYKRX),
    reason="set RUN_NETWORK_TESTS=1 and install pykrx to enable",
)
# pykrx 1.2.8 requires KRX_ID / KRX_PW for ticker-list, investor-trading, and
# fundamental endpoints (KRX server-side change). OHLCV uses a different
# unauthenticated endpoint and remains usable without creds.
krx_login_gate = pytest.mark.skipif(
    not (NETWORK and HAS_PYKRX and HAS_KRX_CREDS),
    reason="set RUN_NETWORK_TESTS=1, install pykrx, and provide KRX_ID/KRX_PW to enable",
)


@smoke_gate
def test_get_stock_data_pykrx_samsung():
    """Samsung Electronics — known to have data on this date range."""
    from tradingagents.dataflows.pykrx_vendor import get_stock_data_pykrx

    out = get_stock_data_pykrx("005930", "2024-01-02", "2024-01-10")
    assert "Stock data for 005930" in out
    assert "Open,High,Low,Close,Volume" in out
    assert out.count("\n") >= 7


@krx_login_gate
def test_get_kr_universe_kospi_snapshot():
    from tradingagents.dataflows.pykrx_vendor import get_kr_universe

    out = get_kr_universe("2024-01-02", market="KOSPI")
    assert "ticker" in out
    # KOSPI has hundreds of names — header + many rows
    assert out.count("\n") > 100


@krx_login_gate
def test_get_kr_investor_trading_samsung():
    from tradingagents.dataflows.pykrx_vendor import get_kr_investor_trading

    out = get_kr_investor_trading("005930", "2024-01-02", "2024-01-10")
    assert "외국인" in out or "Foreign" in out
    assert out.count("\n") >= 5


@krx_login_gate
def test_get_kr_value_factors_samsung():
    from tradingagents.dataflows.pykrx_vendor import get_kr_value_factors

    out = get_kr_value_factors("005930", "2024-01-02", "2024-01-10")
    assert "PER" in out
    assert "PBR" in out
    assert out.count("\n") >= 5


# ---------------------------------------------------------------------------
# Integration tests — route_to_vendor dispatch
# ---------------------------------------------------------------------------


@smoke_gate
def test_route_to_vendor_dispatches_to_pykrx(monkeypatch):
    """tool_vendors override get_stock_data → pykrx must reach pykrx impl."""
    from tradingagents.dataflows import config as df_config
    from tradingagents.dataflows.interface import route_to_vendor

    monkeypatch.setitem(
        df_config._config,
        "tool_vendors",
        {"get_stock_data": "pykrx"},
    )

    out = route_to_vendor("get_stock_data", "005930", "2024-01-02", "2024-01-10")
    assert "Source: pykrx" in out


@krx_login_gate
def test_route_to_vendor_kr_universe():
    from tradingagents.dataflows.interface import route_to_vendor

    out = route_to_vendor("get_kr_universe", "2024-01-02", "KOSPI")
    assert "KR universe snapshot" in out
