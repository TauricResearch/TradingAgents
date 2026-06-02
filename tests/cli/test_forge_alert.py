import json
import pytest
from typer.testing import CliRunner

from tradingagents.persistence.db import connect
from tradingagents.persistence import store


def _seed(conn):
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id="lb1", mode="event_alert_light",
                       scope='["NVDA", "PANW"]',
                       generated_ts="2026-06-01T00:00:00+00:00",
                       content_path="briefs/lb1.md", run_ids=[],
                       trigger_event_id="ev1")
    for t in ("NVDA", "PANW"):
        store.insert_brief_action(conn, brief_id="lb1",
                                  action_type="run_full_study",
                                  action_params={"ticker": t},
                                  expires_at="2099-01-01T00:00:00+00:00")


@pytest.mark.unit
def test_forge_alert_list_and_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    _seed(conn)

    from cli.forge import app
    runner = CliRunner()

    res = runner.invoke(app, ["alert", "list"])
    assert res.exit_code == 0
    assert "lb1" in res.stdout and "NVDA" in res.stdout

    res = runner.invoke(app, ["alert", "approve", "lb1", "--ticker", "NVDA"])
    assert res.exit_code == 0

    conn2 = connect(str(tmp_path / "iic.db"))
    states = dict((json.loads(r["action_params"])["ticker"], r["state"])
                  for r in conn2.execute(
                      "SELECT action_params, state FROM brief_actions"))
    assert states["NVDA"] == "accepted"
    assert states["PANW"] == "pending"


@pytest.mark.unit
def test_forge_alert_approve_all(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    _seed(conn)
    from cli.forge import app
    runner = CliRunner()
    res = runner.invoke(app, ["alert", "approve", "lb1"])
    assert res.exit_code == 0
    conn2 = connect(str(tmp_path / "iic.db"))
    states = [r[0] for r in conn2.execute("SELECT state FROM brief_actions")]
    assert states == ["accepted", "accepted"]


def _seed_full_id(conn, brief_id="fc293809d37445dfaf54d174176c5a1a"):
    """Seed a light alert with a realistic 32-char brief_id (like production)."""
    store.insert_event(conn, event_id="evx", source="rss",
                       ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                       raw_path=None, status="triaged", deduped_of=None)
    store.insert_brief(conn, brief_id=brief_id, mode="event_alert_light",
                       scope='["NVDA"]', generated_ts="2026-06-01T00:00:00+00:00",
                       content_path=f"briefs/{brief_id}.md", run_ids=[],
                       trigger_event_id="evx")
    store.insert_brief_action(conn, brief_id=brief_id, action_type="run_full_study",
                              action_params={"ticker": "NVDA"},
                              expires_at="2099-01-01T00:00:00+00:00")
    return brief_id


@pytest.mark.unit
def test_forge_alert_approve_by_8char_prefix(tmp_path, monkeypatch):
    """The prefix shown by `list` (brief_id[:8]) must be approvable directly."""
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    full = _seed_full_id(conn)

    from cli.forge import app
    runner = CliRunner()
    # the displayed prefix is exactly the first 8 chars
    res = runner.invoke(app, ["alert", "approve", full[:8]])
    assert res.exit_code == 0, res.stdout
    conn2 = connect(str(tmp_path / "iic.db"))
    state = conn2.execute(
        "SELECT state FROM brief_actions WHERE brief_id=?", (full,)).fetchone()[0]
    assert state == "accepted"


@pytest.mark.unit
def test_forge_alert_unknown_prefix_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    _seed_full_id(conn)
    from cli.forge import app
    runner = CliRunner()
    res = runner.invoke(app, ["alert", "approve", "deadbeef"])
    assert res.exit_code != 0  # typer.BadParameter -> non-zero exit


@pytest.mark.unit
def test_forge_alert_ambiguous_prefix_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    conn = connect(str(tmp_path / "iic.db"))
    # two briefs sharing a common prefix 'abcd'
    for bid in ("abcd1111111111111111111111111111", "abcd2222222222222222222222222222"):
        store.insert_event(conn, event_id=f"e_{bid[:6]}", source="rss",
                           ingested_ts="2026-06-01T00:00:00+00:00", salience=0.9,
                           raw_path=None, status="triaged", deduped_of=None)
        store.insert_brief(conn, brief_id=bid, mode="event_alert_light",
                           scope='["NVDA"]', generated_ts="2026-06-01T00:00:00+00:00",
                           content_path=f"briefs/{bid}.md", run_ids=[],
                           trigger_event_id=f"e_{bid[:6]}")
        store.insert_brief_action(conn, brief_id=bid, action_type="run_full_study",
                                  action_params={"ticker": "NVDA"},
                                  expires_at="2099-01-01T00:00:00+00:00")
    from cli.forge import app
    runner = CliRunner()
    res = runner.invoke(app, ["alert", "approve", "abcd"])
    assert res.exit_code != 0  # ambiguous -> BadParameter
