import pytest
from tradingagents.persistence.db import connect
from tradingagents.persistence.store import upsert_ticker


@pytest.fixture
def conn(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    upsert_ticker(conn, ticker="AAPL", exchange="NASDAQ",
                  name="Apple Inc.", aliases=[], active=True)
    upsert_ticker(conn, ticker="TSLA", exchange="NASDAQ",
                  name="Tesla Inc.", aliases=[], active=True)
    upsert_ticker(conn, ticker="DEAD", exchange="NYSE",
                  name="Defunct", aliases=[], active=False)
    return conn


@pytest.mark.unit
def test_validator_keeps_known_drops_unknown(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    kept = v.filter(["AAPL", "NOTREAL", "TSLA"])
    assert kept == ["AAPL", "TSLA"]


@pytest.mark.unit
def test_validator_drops_inactive(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    kept = v.filter(["AAPL", "DEAD"])
    assert kept == ["AAPL"]


@pytest.mark.unit
def test_validator_caches_set(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    _ = v.filter(["AAPL"])
    # Mutate underlying table; validator should not re-query within ttl.
    conn.execute("DELETE FROM tickers WHERE ticker = 'AAPL'")
    conn.commit()
    assert v.filter(["AAPL"]) == ["AAPL"]  # cache still has it


@pytest.mark.unit
def test_validator_refresh_re_reads(conn):
    from tradingagents.sensing.ticker_validator import TickerValidator
    v = TickerValidator(conn=conn)
    _ = v.filter(["AAPL"])
    conn.execute("DELETE FROM tickers WHERE ticker = 'AAPL'"); conn.commit()
    v.refresh()
    assert v.filter(["AAPL"]) == []
