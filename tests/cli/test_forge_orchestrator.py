import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from typer.testing import CliRunner

from tradingagents.persistence.db import connect
from tradingagents.persistence import store
from tradingagents.orchestrator import queue_store


runner = CliRunner()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "iic.db")
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", p)
    return p


@pytest.mark.unit
def test_orchestrator_status_shows_counts(db):
    from cli.forge import app
    conn = connect(db)
    store.insert_event(conn, event_id="ev1", source="rss",
                       ingested_ts=_now(), salience=0.9, raw_path=None,
                       status="triaged", deduped_of=None)
    queue_store.insert_queue_job(conn, job_type="event_alert",
                                  payload="{}", trigger_event_id="ev1")
    result = runner.invoke(app, ["orchestrator", "status"])
    assert result.exit_code == 0, result.output
    assert "queued" in result.output.lower()
    assert "1" in result.output    # pending count


@pytest.mark.unit
def test_orchestrator_promoter_command_exists():
    from cli.forge import app
    # `--help` is the cheapest way to assert wiring without launching the loop.
    result = runner.invoke(app, ["orchestrator", "promoter", "--help"])
    assert result.exit_code == 0
    assert "promoter" in result.output.lower()


@pytest.mark.unit
def test_orchestrator_worker_command_exists():
    from cli.forge import app
    result = runner.invoke(app, ["orchestrator", "worker", "--help"])
    assert result.exit_code == 0
    assert "worker" in result.output.lower()
