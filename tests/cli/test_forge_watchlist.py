import json
import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "iic.db"
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(p))
    return str(p)


@pytest.mark.unit
def test_forge_watchlist_add_then_list(runner, db_path):
    from cli.forge import app
    r = runner.invoke(app, ["watchlist", "add", "AAPL"])
    assert r.exit_code == 0, r.output
    r2 = runner.invoke(app, ["watchlist", "list"])
    assert r2.exit_code == 0
    assert "AAPL" in r2.output


@pytest.mark.unit
def test_forge_watchlist_remove(runner, db_path):
    from cli.forge import app
    runner.invoke(app, ["watchlist", "add", "TSLA"])
    r = runner.invoke(app, ["watchlist", "remove", "TSLA"])
    assert r.exit_code == 0
    out = runner.invoke(app, ["watchlist", "list"]).output
    assert "TSLA" not in out


@pytest.mark.unit
def test_forge_watchlist_list_empty(runner, db_path):
    from cli.forge import app
    r = runner.invoke(app, ["watchlist", "list"])
    assert r.exit_code == 0
    assert "watchlist is empty" in r.output.lower() or r.output.strip() == ""
