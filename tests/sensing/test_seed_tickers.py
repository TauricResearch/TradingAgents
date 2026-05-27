import pytest
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_seed_crypto_universe(conn):
    from tradingagents.sensing.seed_tickers import seed_crypto
    n = seed_crypto(conn)
    assert n == 20
    btc = conn.execute("SELECT * FROM tickers WHERE ticker='BTC-USD'").fetchone()
    assert btc["exchange"] == "CRYPTO"
    assert btc["active"] == 1
    import json as _j
    assert "BTC" in _j.loads(btc["aliases"])


@pytest.mark.unit
def test_seed_polygon_paginated(conn, monkeypatch):
    from tradingagents.sensing import seed_tickers
    pages = [
        {"results": [
            {"ticker": "AAPL", "name": "Apple Inc.", "primary_exchange": "XNAS",
             "active": True}],
         "next_url": "https://api.polygon.io/v3/reference/tickers?cursor=2"},
        {"results": [
            {"ticker": "TSLA", "name": "Tesla Inc.", "primary_exchange": "XNAS",
             "active": True}],
         "next_url": None},
    ]
    calls = {"n": 0}
    def fake_get(url, **_):
        idx = calls["n"]
        calls["n"] += 1
        m = MagicMock(); m.json.return_value = pages[idx]; m.status_code = 200
        m.raise_for_status = lambda: None
        return m
    monkeypatch.setattr(seed_tickers.requests, "get", fake_get)
    monkeypatch.setenv("POLYGON_API_KEY", "fake")

    n = seed_tickers.seed_polygon(conn)
    assert n == 2
    rows = {r["ticker"] for r in conn.execute(
        "SELECT ticker FROM tickers WHERE exchange != 'CRYPTO'"
    )}
    assert rows == {"AAPL", "TSLA"}


@pytest.mark.unit
def test_seed_polygon_missing_key_raises(conn, monkeypatch):
    from tradingagents.sensing.seed_tickers import seed_polygon
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="POLYGON_API_KEY"):
        seed_polygon(conn)
