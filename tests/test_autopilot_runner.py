from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import pytest

from tradingagents.paper.conditional import EarningsSnapshot, evidence_hash
from tradingagents.paper.engine import Bar
from tradingagents.paper.autopilot import runner, feeds
from tradingagents.paper.autopilot.state import create_new, read, atomic_write
from test_autopilot_state import draft

NY=ZoneInfo("America/New_York")
D1="2026-10-21"
D2="2026-10-22"
D3="2026-10-23"
D4="2026-10-26"
D5="2026-10-27"


def when(d,h=18,m=12):
    return datetime.fromisoformat(f"{d}T{h:02d}:{m:02d}:00").replace(tzinfo=NY)


def bar(open_,close=None,low=None,high=None):
    close = open_ if close is None else close
    return Bar(open_,max(open_,close)+1 if high is None else high,
               min(open_,close)-1 if low is None else low,close)


def prices(**changes):
    b={D1:bar(221),D2:bar(228,close=229),D3:bar(230,close=232),
       D4:bar(233,close=234),D5:bar(234,close=233)}
    b.update(changes)
    return b


def loader(price=None):
    sample=price or prices()
    def impl(st,*,target):
        dates=[d for d in sample if d<=target and d>=st.portfolio.book.started]
        if not dates:
            raise ValueError("No completed quote")
        q={"SPY":{d:bar(610+i) for i,d in enumerate(dates)},
           "GBPUSD=X":{d:bar(1.33) for d in dates},
           "NVDA":{d:sample[d] for d in dates},
           "MSFT":{d:bar(420) for d in dates}}
        return q,sorted(dates),lambda x,d:(.75,.75)
    return impl


def create(tmp_path,tickers=None):
    path=tmp_path/"v3"/"portfolio.json"
    create_new(path,D1,tickers or ["NVDA"])
    return path


def source(ticker,session,now):
    return EarningsSnapshot(session,"2026-12-15","2026-07-21",
              "YAHOO+NASDAQ_CONSENSUS_SECONDARY",True,
              now.astimezone(timezone.utc).isoformat())


def capture(path,day,phase):
    now=when(day,9,15) if phase=="preopen" else when(day,17,10)
    return runner.snapshot_phase(path,phase=phase,now=now,fetcher=source)


def initial_plan(path):
    st=read(path)
    st.set_running(True)
    st.machine_accept(draft(),"report",D1,"POLICY_VERIFIED")
    atomic_write(path,st)


def test_last_session_and_spy_comparison_are_ledger_backed(tmp_path):
    path=create(tmp_path)
    r=runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    assert r["session"]==D1 and r["replayed"]==1
    st=read(path)
    assert st.portfolio.book.equity()==10000
    assert st.portfolio.book.equity_history[-1]["spy_benchmark_gbp"]==10000
    assert runner.mark_closed_sessions(path,now=when(D1),loader=loader())["status"]=="already_marked"


def test_strict_two_closes_and_true_next_open_fill(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    initial_plan(path)
    capture(path,D2,"preclose")
    runner.mark_closed_sessions(path,now=when(D2),loader=loader())
    assert read(path).portfolio.book.orders==[]
    capture(path,D3,"preclose")
    runner.mark_closed_sessions(path,now=when(D3),loader=loader())
    st=read(path)
    assert len(st.portfolio.book.orders)==1
    assert st.portfolio.book.positions=={}
    capture(path,D4,"preopen")
    runner.mark_closed_sessions(path,now=when(D4),loader=loader())
    st=read(path)
    assert st.portfolio.book.orders==[]
    assert st.portfolio.book.positions["NVDA"]["shares"]>=1
    assert st.portfolio.book.positions["NVDA"]["stop_usd"]==212.16
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="FILLED"
    assert any(e["type"]=="BUY_FILLED" for e in st.portfolio.book.events)
    assert not st.portfolio.book.halted


def test_missing_preopen_vetoes_new_entry_without_backdated_reconstruction(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    initial_plan(path)
    capture(path,D2,"preclose")
    runner.mark_closed_sessions(path,now=when(D2),loader=loader())
    capture(path,D3,"preclose")
    runner.mark_closed_sessions(path,now=when(D3),loader=loader())
    # Pre-open not captured; afterclose stock quote exists. Never buy anyway.
    runner.mark_closed_sessions(path,now=when(D4),loader=loader())
    st=read(path)
    assert st.portfolio.book.positions=={}
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="REJECTED"
    assert any(e["type"]=="V2_ORDER_VETO" for e in st.portfolio.book.events)
    assert st.portfolio.book.equity()==10000


def test_tampered_preopen_file_rejected_by_ledger_hash(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    initial_plan(path)
    capture(path,D2,"preclose")
    runner.mark_closed_sessions(path,now=when(D2),loader=loader())
    capture(path,D3,"preclose")
    runner.mark_closed_sessions(path,now=when(D3),loader=loader())
    snap=capture(path,D4,"preopen")
    f=Path(snap["path"])
    content=json.loads(f.read_text())
    content["earnings"]["NVDA"]["next_earnings_date"]="2027-03-01"
    f.write_text(json.dumps(content))
    runner.mark_closed_sessions(path,now=when(D4),loader=loader())
    st=read(path)
    assert not st.portfolio.book.positions
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="REJECTED"


def test_large_chase_gap_rejected(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    initial_plan(path)
    capture(path,D2,"preclose")
    runner.mark_closed_sessions(path,now=when(D2),loader=loader())
    capture(path,D3,"preclose")
    runner.mark_closed_sessions(path,now=when(D3),loader=loader())
    capture(path,D4,"preopen")
    runaway=prices(**{D4:bar(250,close=250)})
    runner.mark_closed_sessions(path,now=when(D4),loader=loader(runaway))
    assert not read(path).portfolio.book.positions
    assert read(path).portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="REJECTED"


def test_no_retroactive_buy_even_if_preopen_was_originally_available(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    initial_plan(path)
    capture(path,D2,"preclose")
    runner.mark_closed_sessions(path,now=when(D2),loader=loader())
    capture(path,D3,"preclose")
    runner.mark_closed_sessions(path,now=when(D3),loader=loader())
    capture(path,D4,"preopen")
    # Computer was shut down at D4 close, wakes after D5 close: D4 is backfill.
    runner.mark_closed_sessions(path,now=when(D5),loader=loader())
    st=read(path)
    assert st.portfolio.book.positions=={}
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="CANCELLED"
    assert any(e["kind"]=="BACKFILL_MODELED_STANDING_RISK" for e in st.audit)
    assert not any(e["type"]=="BUY_FILLED" for e in st.portfolio.book.events)


def test_missing_required_bar_keeps_entire_account_unchanged(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    initial_plan(path)
    before=path.read_bytes()
    base=prices()
    del base[D2]
    with pytest.raises((ValueError,KeyError)):
        runner.mark_closed_sessions(path,now=when(D2),loader=loader(base))
    assert path.read_bytes()==before


def test_new_ai_receipt_is_idempotent_and_no_rating_only_orders(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    st=read(path)
    st.set_running(True)
    atomic_write(path,st)
    calls=[]
    def research(graph,*,ticker,session,bar,root,state):
        calls.append(ticker)
        return {"decision":"NO_TRADE","session":session,"rating":"Overweight",
                "reason":"PM did not provide executable entry"},None,"research"
    res=runner.afterclose_research(path,now=when(D1),loader=loader(),
             graph_factory=lambda r:object(),research_fn=research)
    assert res["reviewed"]==1 and calls==["NVDA"]
    assert read(path).portfolio.book.orders==[]
    res=runner.afterclose_research(path,now=when(D1),loader=loader(),
             graph_factory=lambda r:object(),research_fn=research)
    assert res["reviewed"]==0 and calls==["NVDA"]
    assert len(read(path).ai_receipts)==1


def test_ai_valid_conditional_proposal_is_only_a_watching_intent(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    st=read(path)
    st.set_running(True)
    atomic_write(path,st)
    def research(graph,*,ticker,session,bar,root,state):
        return {"decision":"CONDITIONAL_LONG","session":session,"reason":"policy_valid"},draft(),"report"
    res=runner.afterclose_research(path,now=when(D1),loader=loader(),
             graph_factory=lambda r:object(),research_fn=research)
    st=read(path)
    assert res["reviewed"]==1
    assert st.portfolio.book.positions=={}
    assert st.portfolio.book.orders==[]
    assert st.portfolio.intents["KEI-V3_AAAAAAAA"]["status"]=="WATCHING"
    assert len([x for x in st.audit if x["kind"]=="V3_POLICY_ACCEPTED"])==1


def test_disabled_autopaper_still_marks_stop_book_safely(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    x=runner.afterclose_research(path,now=when(D1),loader=loader())
    assert x["status"]=="research_disabled"
    assert not read(path).ai_receipts


def test_end_to_end_llm_handoff_requires_verbatim_pm_and_trader_proof(monkeypatch,tmp_path):
    """Controlled fake model: typed contract, quoted evidence, real V3 policy gate."""
    import sys
    from types import ModuleType,SimpleNamespace
    from tradingagents.paper.autopilot.decision import AIExecutionProposal
    from test_autopilot_decision import proposal,PM,TRADER
    fake_portfolio=ModuleType("tradingagents.portfolio")
    class FakePosition:
        def __init__(self,**kwargs): self.data=kwargs
    class FakePortfolioContext:
        def __init__(self,**kwargs):
            assert "cash" not in kwargs   # NEVER equate GBP cash to USD buying power
            self.positions=kwargs.get("positions",[])
    fake_portfolio.PortfolioContext=FakePortfolioContext
    fake_portfolio.Position=FakePosition
    monkeypatch.setitem(sys.modules,"tradingagents.portfolio",fake_portfolio)
    package=ModuleType("tradingagents.agents")
    rating=ModuleType("tradingagents.agents.rating")
    rating.parse_rating=lambda text:"Overweight"
    monkeypatch.setitem(sys.modules,"tradingagents.agents",package)
    monkeypatch.setitem(sys.modules,"tradingagents.agents.rating",rating)
    class LLM:
        def with_structured_output(self,schema):
            assert schema is AIExecutionProposal
            return SimpleNamespace(invoke=lambda prompt:proposal())
    class Graph:
        deep_thinking_llm=LLM()
        def propagate(self,ticker,date,portfolio):
            assert ticker=="NVDA" and date==D1
            return {"final_trade_decision":PM,
                    "trader_investment_plan":TRADER},"Overweight"
        def save_reports(self,*args,**kw):return None
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    st=read(path)
    st.set_running(True)
    atomic_write(path,st)
    result=runner.afterclose_research(path,now=when(D1),loader=loader(),
                 graph_factory=lambda root:Graph(),
                 research_fn=lambda graph,**kw:runner._research_one(graph,**kw,
                     sector_info=lambda ticker:("Technology",{"currency":"USD","averageVolume":1_000_000})))
    assert result["reviewed"]==1
    st=read(path)
    assert len(st.portfolio.intents)==1
    assert not st.portfolio.book.orders
    intent=next(iter(st.portfolio.intents.values()))
    assert intent["status"]=="WATCHING"
    report_file=path.parent/st.ai_receipts[f"{D1}:NVDA"]["source_file"]
    assert report_file.exists()
    assert evidence_hash(report_file.read_text())==intent["plan"]["report_sha256"]


def test_bad_ai_report_cannot_claim_an_executable_stop(monkeypatch,tmp_path):
    import sys
    from types import ModuleType,SimpleNamespace
    from test_autopilot_decision import proposal,PM,TRADER
    mod=ModuleType("tradingagents.portfolio")
    mod.Position=lambda **kw:kw
    mod.PortfolioContext=lambda **kw:kw
    monkeypatch.setitem(sys.modules,"tradingagents.portfolio",mod)
    rating_mod=ModuleType("tradingagents.agents.rating")
    rating_mod.parse_rating=lambda text:"Overweight"
    monkeypatch.setitem(sys.modules,"tradingagents.agents",ModuleType("tradingagents.agents"))
    monkeypatch.setitem(sys.modules,"tradingagents.agents.rating",rating_mod)
    class Graph:
        deep_thinking_llm=SimpleNamespace(with_structured_output=lambda schema:
                  SimpleNamespace(invoke=lambda prompt:proposal()))
        def propagate(self,ticker,date,portfolio):
            return {"final_trade_decision":PM.replace(
                 "Use a firm stop-loss at $212.16 for the paper trade",
                 "Treat $212.16 as risk-review level, not a firm stop"),
                 "trader_investment_plan":TRADER},"Overweight"
        def save_reports(self,*a,**kw):pass
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    st=read(path);st.set_running(True);atomic_write(path,st)
    runner.afterclose_research(path,now=when(D1),loader=loader(),graph_factory=lambda r:Graph(),
                  research_fn=lambda graph,**kw:runner._research_one(graph,**kw,
                      sector_info=lambda ticker:("Technology",{"currency":"USD","averageVolume":1_000_000})))
    st=read(path)
    assert not st.portfolio.intents
    assert st.ai_receipts[f"{D1}:NVDA"]["decision"]=="NO_TRADE"
    assert st.portfolio.book.equity()==10000


def test_research_price_loader_refetches_completed_marked_session(monkeypatch):
    """Research must request the just-marked date, NOT day+1."""
    from types import ModuleType
    from tradingagents.paper.autopilot.state import V3State
    state = V3State.new("2026-10-22", ["NVDA"])
    state.portfolio.book.last_session = "2026-10-22"
    fake = ModuleType("tradingagents.paper.cli")
    asked = []
    def get_quotes(tickers, start, end, required):
        asked.append((tickers, start, end, required))
        return {"SPY":{"2026-10-22":Bar(600,601,599,600)},
                "NVDA":{"2026-10-22":Bar(210,218,205,215)}}
    fake.fetch_daily = get_quotes
    fake.forex_for_day = lambda *args: (.75,.75)
    import sys
    monkeypatch.setitem(sys.modules, "tradingagents.paper.cli", fake)
    monkeypatch.setattr(feeds, "reject_unmodelled_corporate_actions", lambda *args,**kwargs:None)
    quotes, sessions, conv = runner._research_prices(state, target="2026-10-22")
    assert asked[0][1:3] == ("2026-10-22", "2026-10-22")
    assert sessions == ["2026-10-22"]
    assert "NVDA" in quotes


def test_market_input_snapshot_is_immutable_and_tamper_checked(tmp_path):
    path=create(tmp_path)
    runner.mark_closed_sessions(path,now=when(D1),loader=loader())
    market=path.parent/"market_evidence"/(D1+".json")
    assert market.is_file()
    original=market.read_bytes()
    st=read(path)
    entry=next(e for e in st.audit if e["kind"]=="SESSION_MARKED")
    assert hashlib.sha256(original).hexdigest()==entry["details"]["market_input_sha256"]
    data=json.loads(original)
    data["spy_price_only_close_usd"] = 888.0
    market.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="Market evidence tampered"):
        read(path)
    market.write_bytes(original)
    assert read(path).portfolio.book.last_session==D1


def test_automated_runner_never_overwrites_the_existing_v3_staging_account(tmp_path,monkeypatch):
    from tradingagents.paper.autopilot import state as state_mod
    earlier=tmp_path/"v3"/"portfolio.json"
    earlier.parent.mkdir(parents=True)
    earlier.write_text("PREEXISTING STAGING LEDGER")
    monkeypatch.setattr(state_mod,"LEGACIES", state_mod.LEGACIES+(earlier,))
    with pytest.raises(ValueError,match="immutable"):
        state_mod.create_new(earlier,D1,["NVDA"])
    assert earlier.read_text()=="PREEXISTING STAGING LEDGER"
