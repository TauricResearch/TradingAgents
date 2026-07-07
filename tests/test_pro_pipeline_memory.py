"""Pipeline + memory integration: analogs in debate, Kelly wakes up, writeback."""

from tests.test_pro_memory_facade import make_recommendation
from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot
from tradingagents.pro.memory import MemoryKind, ProMemory
from tradingagents.pro.pipeline import CriticReport, run_pipeline


def seeded_memory(n_closed: int = 5) -> ProMemory:
    memory = ProMemory()
    pnls = [2.0, 2.0, 2.0, -1.0, -1.0][:n_closed]
    for pnl in pnls:
        trade = memory.record_trade(make_recommendation())
        memory.close_trade(trade.id, pnl=pnl)
    return memory


def test_analogs_flow_into_debate_and_recommendation():
    memory = seeded_memory()
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot(), memory=memory)

    rec = state["recommendation"]
    assert rec is not None
    assert rec.historical_analogs, "closed trades should surface as analogs"
    assert all(0 <= a.similarity <= 1 for a in rec.historical_analogs)
    # debaters saw the memory context
    debate_prompt = llm.prompts["DebateTurn"][0]
    assert "Historical analogs" in debate_prompt
    assert "Known market relationships" in debate_prompt
    # judge saw it too
    assert "Historical analogs" in llm.prompts["JudgeVerdict"][0]


def test_win_stats_wake_the_kelly_agent():
    memory = seeded_memory()
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot(), memory=memory)

    assert "KELLY_FRACTION" in state["risk_metrics"]
    risk_evidence = state["evidence_by_team"]["risk"]
    assert any(e.agent_id == "kelly_criterion" for e in risk_evidence)


def test_without_memory_kelly_stays_dormant():
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert "KELLY_FRACTION" not in state["risk_metrics"]
    assert not any(
        e.agent_id == "kelly_criterion" for e in state["evidence_by_team"]["risk"]
    )
    assert state["recommendation"].historical_analogs == []


def test_accepted_run_writes_trade_and_reflection_back():
    memory = seeded_memory()
    before_trades = len([r for r in memory._records.values()
                         if r.kind is MemoryKind.TRADE])
    llm = FakePipelineLLM()
    run_pipeline(llm, CONFIG, pipeline_snapshot(), memory=memory)

    trades = [r for r in memory._records.values() if r.kind is MemoryKind.TRADE]
    reflections = [r for r in memory._records.values()
                   if r.kind is MemoryKind.REFLECTION]
    assert len(trades) == before_trades + 1
    assert len(reflections) == 1
    assert "Invalidation" in reflections[0].text


def test_rejected_run_writes_no_trade():
    memory = seeded_memory()
    llm = FakePipelineLLM(overrides={
        CriticReport: CriticReport(verdict="fail", issues=["fabricated citation"]),
    })
    before = len([r for r in memory._records.values() if r.kind is MemoryKind.TRADE])
    state = run_pipeline(llm, CONFIG, pipeline_snapshot(), memory=memory)
    after = len([r for r in memory._records.values() if r.kind is MemoryKind.TRADE])
    assert state["recommendation"] is None
    assert after == before
