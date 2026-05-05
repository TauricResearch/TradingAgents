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
smoke_gate = pytest.mark.skipif(
    not (NETWORK and HAS_PYKRX),
    reason="set RUN_NETWORK_TESTS=1 and install pykrx to enable",
)


@smoke_gate
def test_get_stock_data_pykrx_samsung():
    """Samsung Electronics — known to have data on this date range."""
    from tradingagents.dataflows.pykrx_vendor import get_stock_data_pykrx

    out = get_stock_data_pykrx("005930", "2024-01-02", "2024-01-10")
    assert "Stock data for 005930" in out
    assert "Open,High,Low,Close,Volume" in out
    assert out.count("\n") >= 7
