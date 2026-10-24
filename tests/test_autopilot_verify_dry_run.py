"""Cross-platform immutable source audit: no market network or paper account."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tradingagents.paper.autopilot import live_dry_run, verify_dry_run
from tradingagents.paper.autopilot.decision import AIExecutionProposal, policy_intent
from tradingagents.paper.conditional import evidence_hash

SESSION = "2026-10-23"
NY = ZoneInfo("America/New_York")


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 10, 23, hour, minute, tzinfo=NY)


def snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "observer"
    (root / "market").mkdir(parents=True)
    (root / "calendar" / SESSION).mkdir(parents=True)
    d = {
        "schema": "koral-observation-v1", "mode": "OBSERVE_ONLY",
        "session": SESSION, "phase": "close", "orders": [],
        "source": "YAHOO_SECONDARY_NOT_EXCHANGE_CERTIFIED",
        "capture_started_utc": at(17,40).astimezone(timezone.utc).isoformat(),
        "capture_completed_utc": at(17,41).astimezone(timezone.utc).isoformat(),
        "ohlc_usd": {ticker: {"open":o,"high":h,"low":l,"close":c} for ticker,o,h,l,c in [
            ("AAPL",200,204,199,202),("SPY",600,605,598,601),
        ]},
        "fx_gbp_per_usd_open":.74,"fx_gbp_per_usd_close":.741,
        "corporate_actions":"QUERIED_NO_UNMODELLED_EVENTS_REPORTED",
    }
    c = {
        "session":SESSION,"phase":"preclose",
        "observed_utc":at(17,10).astimezone(timezone.utc).isoformat(),
        "source_policy":"TWO_SECONDARY_FEEDS_MUST_AGREE_OR_BLOCK",
        "earnings":{"AAPL":{
            "asof_date":SESSION,"next_earnings_date":"2026-11-02",
            "last_earnings_date":"2026-07-30",
            "source":"YAHOO+NASDAQ_CONSENSUS_SECONDARY",
            "verified":True,
            "observed_at_utc":at(17,10).astimezone(timezone.utc).isoformat(),
        }},
    }
    (root/"market"/(SESSION+".json")).write_bytes((json.dumps(d)+"\n").encode())
    (root/"calendar"/SESSION/"preclose.json").write_bytes((json.dumps(c)+"\n").encode())
    return root


def research_output(tmp_path: Path, *, model: bool=False) -> Path:
    observer = snapshot(tmp_path)
    out = tmp_path/"dry_run"
    def fake_ai(_graph, *, ticker, session, bar, root, state):
        report = ('{"stock":"AAPL","evidence":"TWO consecutive closes above $205; '
                  'firm stop-loss at $190"}\n')
        dest = root/"reports"/session/ticker
        dest.mkdir(parents=True)
        source = dest/"source.json"
        source.write_bytes(report.encode())
        pm = ("Rating: Overweight. Buy after TWO consecutive closes above $205.00. "
              "Use a firm stop-loss at $190.00.")
        trader = "**Stop Loss**: $190.00"
        proposal = AIExecutionProposal(action="CONDITIONAL_LONG",rating="Overweight",
            entry_quote="TWO consecutive closes above $205.00",stop_quote=trader,
            trigger_usd=205., stop_usd=190.,required_closes=2,
            expiry_days=14,holding_sessions=20,allocation_fraction=.05,rationale="audit mock")
        plan = policy_intent(proposal,ticker=ticker,session=session,final_pm=pm,
            trader_plan=trader,report=report,close_usd=bar.close,sector="Technology")
        return ({"source_file":str(source.relative_to(root)),
                 "source_sha256":evidence_hash(report), "decision":"CONDITIONAL_LONG"},plan,report)
    live_dry_run.run_dry_run(out,observer,SESSION,["AAPL"],
        now=at(18,5),ai_count=1 if model else 0,
        graph_factory=lambda _:object(),research_fn=fake_ai)
    return out


def modify_manifest(root: Path, func):
    path = root/"DRY_RUN_MANIFEST.json"
    data=json.loads(path.read_text())
    func(data)
    path.write_text(json.dumps(data))


def test_accepts_untouched_retrospective_source_audit(tmp_path):
    out=research_output(tmp_path)
    result=verify_dry_run.audit(out)
    assert result["status"]=="SOURCE_INTEGRITY_AUDIT_PASSED"
    assert result["files_verified"]==2
    assert result["model_receipts_verified"]==0
    assert result["paper_orders"]==0


def test_accepts_unapproved_diagnostic_plan_and_exact_source(tmp_path):
    out=research_output(tmp_path,model=True)
    result=verify_dry_run.audit(out)
    assert result["model_receipts_verified"]==1
    assert result["diagnostic_plans_verified"]==1
    assert result["paper_orders"]==0


def test_rejects_modified_observation_after_report(tmp_path):
    out=research_output(tmp_path)
    p=out/"original_sources"/"market.json"
    p.write_bytes(p.read_bytes().replace(b"202",b"203"))
    with pytest.raises(ValueError,match="hash mismatch"):
        verify_dry_run.audit(out)


def test_rejects_added_file_not_in_original_inventory(tmp_path):
    out=research_output(tmp_path)
    (out/"invented_fill.csv").write_text("winning trade")
    with pytest.raises(ValueError,match="inventory"):
        verify_dry_run.audit(out)


def test_rejects_missing_file(tmp_path):
    out=research_output(tmp_path)
    (out/"original_sources"/"preclose.json").unlink()
    with pytest.raises(ValueError,match="inventory"):
        verify_dry_run.audit(out)


def test_rejects_fake_order_or_enabled_broker_claim(tmp_path):
    out=research_output(tmp_path)
    modify_manifest(out,lambda m:m.__setitem__("paper_orders_created",1))
    with pytest.raises(ValueError,match="account access"):
        verify_dry_run.audit(out)


def test_rejects_forged_approval_status_even_with_updated_manifest(tmp_path):
    out=research_output(tmp_path,model=True)
    modify_manifest(out,lambda m:m["research"]["AAPL"]["conditional_plan"].__setitem__("approved",True))
    with pytest.raises(ValueError,match="incorrectly reports"):
        verify_dry_run.audit(out)


def test_rejects_forged_plan_report_digest(tmp_path):
    out=research_output(tmp_path,model=True)
    modify_manifest(out,lambda m:m["research"]["AAPL"]["conditional_plan"].__setitem__("report_sha256","a"*64))
    with pytest.raises(ValueError,match="does not match"):
        verify_dry_run.audit(out)


def test_rejects_symlink_archives(tmp_path, monkeypatch):
    out=research_output(tmp_path)
    alias=out/"source_alias.json"
    try:
        alias.symlink_to(out/"original_sources"/"market.json")
    except OSError:
        # Non-elevated Windows users may not have permission to create a
        # real symlink. Exercise the same fail-closed branch without admin.
        alias.write_bytes(b"NOT_AUTHORISED")
        old_is_symlink=Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: (
            path == alias or old_is_symlink(path)
        ))
    with pytest.raises(ValueError,match="Symlink"):
        verify_dry_run.audit(out)


def test_prevents_path_traversal_claim(tmp_path):
    out=research_output(tmp_path)
    modify_manifest(out,lambda m:m["audit_files_sha256"].__setitem__("../bad.json","0"*64))
    with pytest.raises(ValueError,match="inventory|unsafe"):
        verify_dry_run.audit(out)


def test_cli_exit_code_validated(tmp_path,capsys):
    out=research_output(tmp_path)
    assert verify_dry_run.main(["--folder",str(out)])==0
    assert "SOURCE_INTEGRITY_AUDIT_PASSED" in capsys.readouterr().out


def test_rejects_model_receipt_claiming_another_ticker_or_session(tmp_path):
    out = research_output(tmp_path, model=True)
    modify_manifest(out, lambda m: m["research"]["AAPL"]["ai_receipt"].__setitem__(
        "source_file", "reports/2026-10-22/MSFT/source.json"))
    with pytest.raises(ValueError, match="another ticker/session"):
        verify_dry_run.audit(out)


def test_rejects_false_ai_classification(tmp_path):
    out = research_output(tmp_path)
    modify_manifest(out, lambda m: m.__setitem__(
        "classification", "SAME_SESSION_REAL_AI_DRY_RUN_NOT_FORWARD_TRADE"))
    with pytest.raises(ValueError, match="AI attempt contradicts"):
        verify_dry_run.audit(out)


def test_rejects_forged_ai_attempt_field(tmp_path):
    out = research_output(tmp_path, model=True)
    modify_manifest(out, lambda m: m.__setitem__("real_ai_attempted", False))
    with pytest.raises(ValueError, match="AI attempt contradicts"):
        verify_dry_run.audit(out)
