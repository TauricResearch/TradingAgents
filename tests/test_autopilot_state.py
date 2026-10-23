import copy
import json
from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from tradingagents.paper.conditional import TradeIntent, evidence_hash
from tradingagents.paper.autopilot.state import V3State, atomic_write, create_new, read, checked_path, normalize_tickers


def draft(session="2026-10-21", **overrides):
    raw=dict(intent_id="KEI-V3_AAAAAAAA",ticker="NVDA",decision_date=session,
        expiry_date="2026-11-01",rating="Overweight",side="ENTER_LONG",
        entry_rule="CLOSES_ABOVE",trigger_usd=226.87,required_closes=2,
        stop_loss_usd=212.16,stop_is_executable=True,initial_allocation_fraction=.08,
        max_holding_sessions=20,max_entry_gap_fraction=.025,
        sector="Technology",report_sha256=evidence_hash("report"))
    return TradeIntent(**(raw|overrides))


def initialized(tmp_path):
    path=tmp_path/"v3"/"portfolio.json"
    state=create_new(path,"2026-10-21",["NVDA","MSFT"])
    return path,state


def test_isolated_start_is_paper_only_and_no_reset(tmp_path):
    path,state=initialized(tmp_path)
    assert state.portfolio.book.equity()==10000
    assert read(path).to_dict()==state.to_dict()
    with pytest.raises(ValueError,match="already exists"):
        create_new(path,"2026-10-21",["NVDA"])
    assert read(path).portfolio.book.equity()==10000


def test_only_explicit_enable_and_no_real_mode(tmp_path):
    path,st=initialized(tmp_path)
    assert st.can_buy() is False
    st.set_running(True)
    assert st.can_buy() is True
    st.pause(True)
    assert st.can_buy() is False
    st.pause(False)
    assert st.can_buy() is True
    st.set_running(False)
    assert st.can_buy() is False
    atomic_write(path,st)
    assert read(path).auto_paper_enabled is False
    assert all("BROKER" not in e["kind"] for e in st.audit)


def test_provenance_and_policy_gate_no_direct_overweight(tmp_path):
    path,st=initialized(tmp_path)
    st.portfolio=st.portfolio.advance("2026-10-21",{},.75,.75,600,{}, {})
    with pytest.raises(ValueError,match="permission"):
        st.machine_accept(draft(),"report","2026-10-21","POLICY_VERIFIED")
    st.set_running(True)
    with pytest.raises(ValueError,match="provenance"):
        st.machine_accept(draft(),"wrong","2026-10-21","POLICY_VERIFIED")
    with pytest.raises(ValueError,match="permission"):
        st.machine_accept(draft(),"report","2026-10-21","RATING_ONLY")
    st.machine_accept(draft(),"report","2026-10-21","POLICY_VERIFIED")
    assert not st.portfolio.book.orders
    assert not st.portfolio.book.positions
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="WATCHING"
    assert any(e["kind"]=="V3_POLICY_ACCEPTED" for e in st.audit)
    with pytest.raises(ValueError,match="Intent replay"):
        st.machine_accept(draft(),"report","2026-10-21","POLICY_VERIFIED")


def test_worst_case_operator_pause_cancels_pending_without_removing_history(tmp_path):
    path,st=initialized(tmp_path)
    st.portfolio=st.portfolio.advance("2026-10-21",{},.75,.75,600,{}, {})
    st.set_running(True)
    st.machine_accept(draft(),"report","2026-10-21","POLICY_VERIFIED")
    old=len(st.audit)
    st.pause(True)
    assert len(st.audit)>old
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="CANCELLED"
    assert st.portfolio.book.orders==[]
    assert st.portfolio.book.equity()==10000
    atomic_write(path,st)
    assert read(path).paused is True


def test_corrupt_hash_chain_is_rejected(tmp_path):
    path,st=initialized(tmp_path)
    data=st.to_dict()
    data["audit"][0]["details"]["watchlist"][0]="TSLA"
    with pytest.raises(ValueError,match="hash"):
        V3State.from_dict(data)
    data=st.to_dict()
    data["paper_only"]=False
    with pytest.raises(ValueError,match="non-paper"):
        V3State.from_dict(data)


def test_invalid_tickers_and_cross_version_state_blocked(tmp_path,monkeypatch):
    with pytest.raises(ValueError):normalize_tickers(["NVDA","nvda"])
    with pytest.raises(ValueError):normalize_tickers(["NVDA","NVDA"])
    with pytest.raises(ValueError):normalize_tickers(["../../x"])
    from tradingagents.paper.autopilot import state
    legacy=tmp_path/"old"/"portfolio.json"
    monkeypatch.setattr(state,"LEGACIES",(legacy,))
    with pytest.raises(ValueError,match="immutable"):
        checked_path(legacy)


def test_ledger_fails_closed_after_version_or_risk_tamper(tmp_path):
    path,st=initialized(tmp_path)
    data=st.to_dict()
    data["portfolio"]["book"]["rules"]["risk_fraction"]=.9
    with pytest.raises(ValueError): V3State.from_dict(data)
    data=st.to_dict()
    data["schema"]="v4-rewrite"
    with pytest.raises(ValueError): V3State.from_dict(data)


def test_disabled_autopaper_stops_buying_but_does_not_evict_open_positions(tmp_path):
    path,st=initialized(tmp_path)
    st.portfolio=st.portfolio.advance("2026-10-21",{},.75,.75,600,{}, {})
    st.set_running(True)
    st.machine_accept(draft(),"report","2026-10-21","POLICY_VERIFIED")
    st.set_running(False)
    assert not st.portfolio.intents or st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="CANCELLED"
    assert st.can_buy() is False
