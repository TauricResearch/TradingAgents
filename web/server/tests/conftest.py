import pytest
from web.server import storage


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Per-test data dir under tmp_path. Sets env vars + inits storage."""
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(data))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(cache))
    # Keep the lifespan's background PriceFeed (yfinance poll loop) off
    # during tests — the feed is unit-tested in test_price_feed.py and
    # would otherwise hit the network / make tests non-deterministic.
    # ``PriceState`` is still created so /api/prices is reachable and
    # testable in isolation.
    monkeypatch.setenv("TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED", "1")
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


@pytest.fixture
def client(data_root):
    """FastAPI TestClient with the file-backed storage configured."""
    from fastapi.testclient import TestClient
    from web.server.app import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def fake_propagate(monkeypatch):
    """Replace ``background_runs._call_propagate`` with a recording fake.

    Tests that need the fake add ``fake_propagate`` to their parameter list.
    The setattr is best-effort: if ``background_runs`` is not yet importing
    cleanly or doesn't have ``_call_propagate`` (e.g. earlier in the plan),
    the fixture still yields the fake so the test can inspect it.
    """
    from web.server.tests.fixtures.fake_propagate import FakePropagate
    fake = FakePropagate()
    try:
        from web.server import background_runs
        monkeypatch.setattr(background_runs, "_call_propagate", fake)
    except (ImportError, AttributeError):
        # background_runs module or _call_propagate not yet defined.
        pass
    yield fake