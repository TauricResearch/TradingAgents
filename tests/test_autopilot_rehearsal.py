"""Full trade-cycle rehearsal: mock AI and prices, not an investable result."""
import hashlib

import pytest

from tradingagents.paper.autopilot import rehearsal
from tradingagents.paper.autopilot.state import read


def test_complete_source_backed_trade_and_adverse_gap_stop(tmp_path):
    dest=tmp_path/"mock_trade"
    evidence=rehearsal.run_rehearsal(dest)
    assert evidence["classification"]=="SYNTHETIC_CONTROLLED_NOT_FORWARD_PERFORMANCE"
    assert evidence["real_money_exposure_gbp"]==0
    assert evidence["real_llm_called"] is False
    assert evidence["live_prices_used"] is False
    assert evidence["ticker"]=="KXDEMO"
    assert evidence["entry"]["date"]=="2026-10-26"
    assert evidence["entry"]["shares"]==6
    assert evidence["entry"]["stop_usd"]==92.0
    assert evidence["exit"]["reason"]=="STOP"
    assert evidence["exit"]["exit_date"]=="2026-10-27"
    assert evidence["exit"]["exit_usd"] < evidence["entry"]["stop_usd"]
    assert evidence["pnl_gbp"] == -82.28
    assert evidence["equity_gbp"] == 9917.72
    assert evidence["open_positions"] == evidence["pending_orders"] == 0
    for filename,digest in evidence["files_sha256"].items():
        assert hashlib.sha256((dest/filename).read_bytes()).hexdigest()==digest
    book=read(dest/"portfolio.json")
    assert book.portfolio.book.last_session=="2026-10-27"
    assert len(book.portfolio.book.completed)==1
    assert len([x for x in book.audit if x["kind"]=="SESSION_MARKED"])==5
    assert any(x["kind"]=="AI_RESEARCH_RECEIPT"
               and x["details"]["receipt"]["ticker"]=="KXDEMO"
               for x in book.audit)


def test_market_evidence_tamper_blocks_rehearsal_state(tmp_path):
    folder=tmp_path/"mock_trade"
    rehearsal.run_rehearsal(folder)
    file=folder/"market_evidence"/"2026-10-23.json"
    file.write_text("{}")
    with pytest.raises(ValueError,match="Market evidence tampered"):
        read(folder/"portfolio.json")


def test_rehearsal_never_overwrites_existing_portfolio(tmp_path):
    folder=tmp_path/"existing"
    folder.mkdir()
    account=folder/"portfolio.json"
    account.write_bytes(b"DO_NOT_CHANGE")
    with pytest.raises(ValueError,match="already exists"):
        rehearsal.run_rehearsal(folder)
    assert account.read_bytes()==b"DO_NOT_CHANGE"


def test_rehearsal_does_not_modify_other_paper_account(tmp_path):
    account=tmp_path/"live_account"/"portfolio.json"
    account.parent.mkdir()
    account.write_bytes(b"V3_LIVE_PAPER_ACCOUNT")
    rehearsal.run_rehearsal(tmp_path/"separate_rehearsal")
    assert account.read_bytes()==b"V3_LIVE_PAPER_ACCOUNT"


def test_rehearsal_cli_is_explicitly_not_forward_performance(tmp_path,capsys):
    output=tmp_path/"from_cli"
    assert rehearsal.main(["--output",str(output)])==0
    assert '"real_forward_trade": false' in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        rehearsal.main(["--output",str(output)])
    assert error.value.code==2


def test_rehearsal_inside_real_paper_tree_is_forbidden(monkeypatch,tmp_path):
    monkeypatch.setattr(rehearsal.Path, "home", lambda:tmp_path)
    real=tmp_path/".tradingagents"/"paper"/"v3_autopilot"/"test"
    with pytest.raises(ValueError,match="must not access actual paper accounts"):
        rehearsal.safe_output(real)


def test_source_report_is_exact_canonical_utf8_on_every_platform(tmp_path):
    """Windows previously wrote CRLF, invalidating the SHA of the LLM report."""
    folder = tmp_path / "canonical_source"
    manifest = rehearsal.run_rehearsal(folder)
    source = folder / "reports" / "2026-10-21" / "KXDEMO" / "source.json"
    raw = source.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw
    assert hashlib.sha256(raw).hexdigest() == manifest["source_sha256"]
    state = read(folder / "portfolio.json")
    record = state.ai_receipts["2026-10-21:KXDEMO"]
    assert record["source_sha256"] == hashlib.sha256(raw).hexdigest()

