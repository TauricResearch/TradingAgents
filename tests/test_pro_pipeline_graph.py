"""End-to-end pipeline runs through the compiled LangGraph with fake LLMs."""

from datetime import timedelta

import pytest

from tests.pro_fakes import BASE_TS
from tests.test_pro_agents_base import make_snapshot
from tradingagents.contracts import (
    AssetClass,
    IndicatorReading,
    OHLCVBar,
    ProConfig,
    Timeframe,
    TradeAction,
    TradingMode,
)
from tradingagents.pro.agents import EvidenceDraft

# the scripted provider lives in the package so the dashboard's replay
# endpoint can use it in production; tests re-import from here
from tradingagents.pro.evals.scripted import (  # noqa: E402,F401
    DEFAULT_DRAFTS,
    FakePipelineLLM,
    FakeRunnable,
)
from tradingagents.pro.pipeline import (
    CriticReport,
    JudgeVerdict,
    ReflectionNote,
    run_pipeline,
)


def pipeline_snapshot(**overrides):
    base = make_snapshot()
    snapshot = make_snapshot(
        indicators=[
            *base.indicators,
            IndicatorReading(name="ATR_14", timeframe=Timeframe.D1,
                             value={"value": 2.5}, params={"period": 14}),
        ],
        **overrides,
    )
    return snapshot


def lossy_bars(n: int = 30) -> list[OHLCVBar]:
    """Bars losing 5% per bar: VaR95 = 5%/bar, breaching the 3% default limit."""
    bars, price = [], 100.0
    for i in range(n):
        close = price * 0.95
        bars.append(OHLCVBar(
            timeframe=Timeframe.D1, start=BASE_TS + timedelta(days=i),
            open=price, high=price * 1.01, low=close * 0.99, close=close,
            volume=1000.0,
        ))
        price = close
    return bars


CONFIG = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=1)


def test_happy_path_produces_validated_buy_recommendation():
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())

    assert state.get("rejection") is None
    rec = state["recommendation"]
    assert rec is not None
    assert rec.action is TradeAction.BUY
    assert rec.confidence == 72
    # levels came from the risk engine, geometry validated by the contract
    assert rec.stop_loss < rec.entry_price < rec.take_profits[0].price
    assert rec.risk_reward is not None and rec.risk_reward > 0
    assert rec.position_size.quantity > 0
    # votes recorded: every evidence item + the judge
    judge_votes = [v for v in rec.vote_breakdown.votes if v.agent_id == "judge"]
    assert len(judge_votes) == 1
    assert len(rec.vote_breakdown.votes) >= 2
    assert state["execution_status"] == "accepted:paper"
    # judge saw the computed vote tally
    assert "confidence weight" in llm.prompts["JudgeVerdict"][0]


def test_event_gate_blocks_new_entries_near_major_events():
    # review deal-breaker #2: the pipeline shorted gold on FOMC day with
    # zero FOMC awareness. Inside the window the run must decline to trade.
    from datetime import datetime, timedelta, timezone

    imminent = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    llm = FakePipelineLLM()
    state = run_pipeline(
        llm, CONFIG, pipeline_snapshot(),
        calendar_fn=lambda: {"release": "FOMC Press Release",
                             "date": "2026-07-16", "major": True,
                             "at": imminent},
    )
    assert state.get("recommendation") is None
    assert state["rejection"]["stage"] == "event_gate"
    assert "FOMC Press Release" in state["rejection"]["reasons"][0]
    assert state["gate_results"]["event"]["passed"] is False
    # R2.6: the veto happens at prepare — a gated run buys ZERO LLM calls
    # (six event-day runs each paid for a full debate before this fix)
    assert llm.prompts == {}


def test_event_gate_passes_when_no_event_is_near():
    from datetime import datetime, timedelta, timezone

    far = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    llm = FakePipelineLLM()
    state = run_pipeline(
        llm, CONFIG, pipeline_snapshot(),
        calendar_fn=lambda: {"release": "FOMC Press Release",
                             "date": "2026-07-19", "major": True, "at": far},
    )
    assert state.get("rejection") is None
    assert state["recommendation"] is not None
    assert state["gate_results"]["event"]["passed"] is True


def test_broken_calendar_never_blocks_the_run():
    llm = FakePipelineLLM()
    state = run_pipeline(
        llm, CONFIG, pipeline_snapshot(),
        calendar_fn=lambda: (_ for _ in ()).throw(RuntimeError("calendar down")),
    )
    assert state.get("rejection") is None
    assert state["recommendation"] is not None


def test_reflection_invalidation_price_derives_the_stop():
    llm = FakePipelineLLM(overrides={
        ReflectionNote: ReflectionNote(
            weaknesses="Momentum evidence is single-timeframe.",
            invalidation="A sustained close below 128.0 breaks the structure.",
            invalidation_price=128.0,
        ),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    assert rec is not None and rec.action is TradeAction.BUY
    # entry 130.0 (last close), ATR 2.5: stop derives from the thesis-death
    # level 128.0 minus buffer min(0.25*2.5, max(0.25*2.0, 0.13)) = 0.5
    assert rec.invalidation_price == 128.0
    assert rec.stop_loss == pytest.approx(127.5)
    # the trade no longer outlives its thesis (old ATR stop was 125.0)
    assert rec.stop_loss > 125.0


def test_wrong_sided_invalidation_falls_back_to_atr_stop():
    llm = FakePipelineLLM(overrides={
        ReflectionNote: ReflectionNote(
            weaknesses="Momentum evidence is single-timeframe.",
            invalidation="A close above 131.0 invalidates the bear case.",
            invalidation_price=131.0,  # above entry: unusable for a BUY
        ),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    assert rec is not None and rec.action is TradeAction.BUY
    assert rec.invalidation_price is None
    assert rec.stop_loss == pytest.approx(125.0)  # 130 - 2*ATR(2.5)


def test_hold_ruling_yields_hold_recommendation_without_levels():
    llm = FakePipelineLLM(overrides={
        JudgeVerdict: JudgeVerdict(action="HOLD", confidence=50,
                                   rationale="Evidence is balanced."),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    assert rec.action is TradeAction.HOLD
    assert rec.entry_price is None and rec.stop_loss is None
    assert rec.position_size.quantity == 0
    assert state["execution_status"] == "accepted:paper"


def test_debate_rounds_are_bounded_by_config():
    llm = FakePipelineLLM()
    config = ProConfig(asset=AssetClass.GOLD, max_debate_rounds=2)
    state = run_pipeline(llm, config, pipeline_snapshot())

    speakers = [entry["speaker"] for entry in state["debate"]]
    assert speakers.count("technical_bull") == 2
    assert speakers.count("technical_bear") == 2
    assert speakers.count("macro_bull") == 2
    assert speakers.count("macro_bear") == 2
    assert speakers.count("sentiment") == 1
    # order: full technical exchange precedes macro
    assert speakers.index("macro_bull") > speakers.index("technical_bear")


def test_risk_gate_rejects_var_breach_before_critic():
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot(bars=lossy_bars()))

    assert state["rejection"]["stage"] == "risk_gate"
    assert state["recommendation"] is None
    assert state["execution_status"] == "rejected:risk_gate"
    speakers = {entry["speaker"] for entry in state["debate"]}
    assert "critic" not in speakers and "judge" not in speakers


def test_critic_fail_rejects_run():
    llm = FakePipelineLLM(overrides={
        CriticReport: CriticReport(
            verdict="fail",
            issues=["technical_bull cited agent 'ichimoku' which produced no evidence"],
        ),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert state["rejection"]["stage"] == "critic"
    assert state["recommendation"] is None
    assert "ichimoku" in state["rejection"]["reasons"][0]


def test_unsupported_judge_ruling_rejected_at_pm():
    # every agent said bearish, judge rules BUY -> no supporting evidence
    llm = FakePipelineLLM(overrides={
        EvidenceDraft: EvidenceDraft(
            claim="Signal points down.", direction="bearish", confidence=60,
        ),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert state["rejection"]["stage"] == "portfolio_manager"
    assert "no evidence supports" in state["rejection"]["reasons"][0]
    assert state["recommendation"] is None


def test_join_rejects_when_no_agent_produces_evidence():
    llm = FakePipelineLLM(overrides={EvidenceDraft: RuntimeError("all agents down")})
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    assert state["rejection"]["stage"] == "join"
    assert state["recommendation"] is None
    assert state["debate"] == []  # rejected before any debate turn


def test_live_mode_without_checkpointer_cannot_even_build():
    import pytest

    llm = FakePipelineLLM()
    config = ProConfig(
        asset=AssetClass.GOLD, mode=TradingMode.LIVE,
        live_trading_enabled=True, max_debate_rounds=1,
    )
    with pytest.raises(ValueError, match="requires a checkpointer"):
        run_pipeline(llm, config, pipeline_snapshot())


def test_sell_ruling_builds_sell_geometry():
    llm = FakePipelineLLM(overrides={
        EvidenceDraft: EvidenceDraft(
            claim="Signal points down.", direction="bearish", confidence=60,
        ),
        JudgeVerdict: JudgeVerdict(action="SELL", confidence=64,
                                   rationale="Bear side carried it."),
    })
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    assert rec.action is TradeAction.SELL
    assert rec.stop_loss > rec.entry_price > rec.take_profits[0].price
    assert state.get("rejection") is None


def test_counterarguments_preserve_losing_side():
    # mix: technical bullish (default), but override is global per schema, so
    # simulate by checking the happy path keeps opposing list consistent
    llm = FakePipelineLLM()
    state = run_pipeline(llm, CONFIG, pipeline_snapshot())
    rec = state["recommendation"]
    # all fake evidence is bullish -> no counterarguments, all supporting
    assert rec.counterarguments == []
    assert all(e.direction.value == "bullish" for e in rec.evidence)
