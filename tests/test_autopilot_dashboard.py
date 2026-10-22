"""Read-only V3.1 web status must not touch V1/V2/V3 book files."""
import json
from datetime import datetime, timezone

from tradingagents.paper.autopilot.state import create_new
from tradingagents.paper.dashboard import autopilot_paper_snapshot


def test_missing_autopilot_ledger_is_never_auto_initialised(tmp_path):
    path=tmp_path/"v3_autopilot"/"portfolio.json"
    state=autopilot_paper_snapshot(path)
    assert state["status"]=="not_initialized"
    assert state["broker_connected"] is False
    assert not path.exists()


def test_read_only_status_is_ledger_backed_and_never_mutates(tmp_path):
    path=tmp_path/"v3_autopilot"/"portfolio.json"
    create_new(path,"2026-10-22",["AAPL","NVDA"])
    before=path.read_bytes()
    result=autopilot_paper_snapshot(path)
    assert result["status"]=="paper_ready"
    assert result["equity_gbp"]==10000.0
    assert result["positions"]==0 and result["queued"]==0
    assert result["ai_receipts"]==0
    assert result["heartbeat_recent"] is False
    assert result["watchlist"]==["AAPL","NVDA"]
    assert result["broker_connected"] is False
    assert path.read_bytes()==before


def test_journal_tampering_is_shown_as_safe_halt(tmp_path):
    path=tmp_path/"v3_autopilot"/"portfolio.json"
    create_new(path,"2026-10-22",["AAPL"])
    raw=json.loads(path.read_text())
    raw["audit"][0]["details"]["date"]="2026-10-23"
    path.write_text(json.dumps(raw))
    result=autopilot_paper_snapshot(path)
    assert result["status"]=="invalid_state"
    assert result["broker_connected"] is False


def test_stale_heartbeat_cannot_claim_running_service(tmp_path):
    path=tmp_path/"v3_autopilot"/"portfolio.json"
    create_new(path,"2026-10-22",["AAPL"])
    heartbeat=path.parent/"service_heartbeat.json"
    heartbeat.write_text(json.dumps({"last_pulse_utc":"2025-01-01T12:00:00+00:00","mode":"PAPER_ONLY"}))
    assert autopilot_paper_snapshot(path)["heartbeat_recent"] is False
    heartbeat.write_text(json.dumps({"last_pulse_utc":datetime.now(timezone.utc).isoformat(),
                                     "mode":"PAPER_ONLY"}))
    assert autopilot_paper_snapshot(path)["heartbeat_recent"] is True
