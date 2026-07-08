"""RL as advisory input to the Judge — and provably not an execution bypass."""

from tests.pro_fakes import make_bars
from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot
from tradingagents.contracts import TradeAction
from tradingagents.pro.pipeline import run_pipeline
from tradingagents.pro.pipeline.schemas import JudgeVerdict
from tradingagents.pro.rl import RLAdvisor, train_q_policy


def trained_advisor() -> RLAdvisor:
    policy, _ = train_q_policy(make_bars(n=300), eval_fraction=0, seed=3)
    return RLAdvisor(policy, min_visits=1)


def rl_snapshot():
    # pipeline snapshot bars must support an RL state (>= 60) — the default
    # test snapshot carries 60 rising bars, matching the trained state space
    return pipeline_snapshot()


def test_rl_agent_emits_evidence_when_advisor_attached():
    state = run_pipeline(
        FakePipelineLLM(), CONFIG, rl_snapshot(), advisor=trained_advisor()
    )
    quant_evidence = state["evidence_by_team"]["quant"]
    rl = [e for e in quant_evidence if e.agent_id == "reinforcement_learning"]
    assert rl, "trained advisor should wake the reinforcement_learning agent"
    ref_names = {r.name for r in rl[0].data_refs}
    assert {"RL_Q_BUY", "RL_POLICY_EDGE"} <= ref_names
    assert rl[0].sources[0].id == "rl_advisor"
    # the RL voice is one recorded vote among many
    assert any(v.agent_id == "reinforcement_learning"
               for v in state["vote_breakdown"].votes)


def test_rl_agent_abstains_without_advisor():
    state = run_pipeline(FakePipelineLLM(), CONFIG, rl_snapshot())
    quant_ids = {e.agent_id for e in state["evidence_by_team"]["quant"]}
    assert "reinforcement_learning" not in quant_ids


def test_rl_advice_cannot_bypass_the_judge():
    """Advisor says BUY loudly; judge rules HOLD; result is HOLD — the
    policy influences through evidence only, never through execution."""
    llm = FakePipelineLLM(overrides={
        JudgeVerdict: JudgeVerdict(action="HOLD", confidence=55,
                                   rationale="RL edge noted but macro conflicts."),
    })
    state = run_pipeline(llm, CONFIG, rl_snapshot(), advisor=trained_advisor())
    rec = state["recommendation"]
    assert rec.action is TradeAction.HOLD
    assert rec.position_size.quantity == 0
    assert state["execution_status"] == "accepted:paper"


def test_failing_advisor_degrades_gracefully():
    class ExplodingAdvisor:
        def advise(self, bars):
            raise RuntimeError("policy file corrupted")

    state = run_pipeline(
        FakePipelineLLM(), CONFIG, rl_snapshot(), advisor=ExplodingAdvisor()
    )
    assert state.get("rejection") is None
    assert state["recommendation"] is not None  # pipeline unaffected
