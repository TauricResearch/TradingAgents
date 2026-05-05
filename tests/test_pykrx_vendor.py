# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Smoke tests for pykrx_vendor — require network. Skipped if pykrx import fails."""

import os

import pytest

pykrx = pytest.importorskip("pykrx")
NETWORK = os.getenv("RUN_NETWORK_TESTS") == "1"
pytestmark = pytest.mark.skipif(not NETWORK, reason="set RUN_NETWORK_TESTS=1 to enable")

from tradingagents.dataflows.pykrx_vendor import get_stock_data_pykrx  # noqa: E402


def test_get_stock_data_pykrx_samsung():
    """Samsung Electronics — known to have data on this date range."""
    out = get_stock_data_pykrx("005930", "2024-01-02", "2024-01-10")
    assert "Stock data for 005930" in out
    assert "Open,High,Low,Close,Volume" in out  # csv columns we expose
    # at least 5 trading days
    assert out.count("\n") >= 7
