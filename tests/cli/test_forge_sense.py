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
def test_forge_sense_reseed_calls_seed_all(runner, db_path, monkeypatch):
    from cli import forge as fmod
    calls = {"n": 0}
    def fake(conn):
        calls["n"] += 1
        return {"crypto": 20, "polygon": 0}
    monkeypatch.setattr(fmod, "seed_all", fake)
    r = runner.invoke(fmod.app, ["sense", "reseed-tickers", "--no-polygon"])
    assert r.exit_code == 0, r.output
    assert calls["n"] == 0  # --no-polygon → seed_crypto only
    monkeypatch.setattr(fmod, "seed_all", fake)
    r2 = runner.invoke(fmod.app, ["sense", "reseed-tickers"])
    assert calls["n"] >= 1


@pytest.mark.unit
def test_forge_sense_sweep_watchlist(runner, db_path):
    from cli.forge import app
    r = runner.invoke(app, ["sense", "sweep-watchlist"])
    assert r.exit_code == 0
    assert "pruned" in r.output.lower()
