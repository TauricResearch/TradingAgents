import pytest
from web.server import storage


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Per-test data dir under tmp_path. Sets env vars + inits storage."""
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(data))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(cache))
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


@pytest.fixture
def client(data_root):
    """FastAPI TestClient with the file-backed storage configured."""
    from fastapi.testclient import TestClient
    from web.server.app import app
    with TestClient(app) as c:
        yield c