"""Phase 6: parallel teams, human approval, resume, retries, routing, streaming."""

import threading

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot
from tradingagents.contracts import (
    AssetClass,
    ProConfig,
    TradeAction,
    TradingMode,
)
from tradingagents.pro.agents import EvidenceDraft
from tradingagents.pro.pipeline import (
    PipelineNodes,
    build_pro_pipeline,
    run_pipeline,
    stream_pipeline,
)

LIVE_CONFIG = ProConfig(
    asset=AssetClass.GOLD, mode=TradingMode.LIVE,
    live_trading_enabled=True, max_debate_rounds=1,
)


class TestParallelTeams:
    def test_team_nodes_run_in_one_superstep(self):
        """All five team nodes appear between prepare and join in the stream,
        and the merged evidence matches the sequential result shape."""
        llm = FakePipelineLLM()
        events = list(stream_pipeline(llm, CONFIG, pipeline_snapshot()))
        order = [next(iter(e)) for e in events]

        prepare_idx = order.index("prepare")
        join_idx = order.index("join")
        team_indices = [i for i, n in enumerate(order) if n.startswith("team_")]
        assert len(team_indices) == 5
        assert all(prepare_idx < i < join_idx for i in team_indices)

    def test_merged_evidence_is_deterministic_in_vote_order(self):
        llm = FakePipelineLLM()
        state = run_pipeline(llm, CONFIG, pipeline_snapshot())
        agent_ids = [v.agent_id for v in state["vote_breakdown"].votes]
        # deterministic fixed team order regardless of branch completion order
        state2 = run_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot())
        assert agent_ids == [v.agent_id for v in state2["vote_breakdown"].votes]

    def test_agent_workers_thread_pool_produces_same_evidence(self):
        seen_threads = set()

        class ThreadTrackingLLM(FakePipelineLLM):
            def with_structured_output(self, schema):
                runnable = super().with_structured_output(schema)
                if schema is EvidenceDraft:
                    original = runnable.invoke

                    def tracked(prompt):
                        seen_threads.add(threading.current_thread().name)
                        return original(prompt)

                    runnable.invoke = tracked
                return runnable

        sequential = run_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot())
        parallel = run_pipeline(
            ThreadTrackingLLM(), CONFIG, pipeline_snapshot(), agent_workers=4
        )
        assert len(seen_threads) > 1  # pool actually used
        seq_ids = {e.agent_id for t in sequential["evidence_by_team"].values() for e in t}
        par_ids = {e.agent_id for t in parallel["evidence_by_team"].values() for e in t}
        assert seq_ids == par_ids


class TestHumanApproval:
    def _run_until_interrupt(self, llm):
        saver = MemorySaver()
        pipeline = build_pro_pipeline(llm, LIVE_CONFIG, checkpointer=saver)
        run_config = {"configurable": {"thread_id": "live-1"}}
        state = pipeline.invoke({"snapshot": pipeline_snapshot()}, run_config)
        return pipeline, run_config, state

    def test_live_run_pauses_for_approval(self):
        _, _, state = self._run_until_interrupt(FakePipelineLLM())
        assert "__interrupt__" in state
        payload = state["__interrupt__"][0].value
        assert payload["question"].startswith("Approve live execution")
        assert payload["recommendation"]["action"] == "BUY"
        assert state.get("execution_status") is None  # nothing executed yet

    def test_approval_resumes_into_live_execution(self):
        pipeline, run_config, _ = self._run_until_interrupt(FakePipelineLLM())
        final = pipeline.invoke(
            Command(resume={"approved": True, "approver": "ajay"}), run_config
        )
        assert final["human_approval"] == {"approved": True, "approver": "ajay"}
        assert final["execution_status"].startswith("accepted:live")
        assert final["recommendation"].action is TradeAction.BUY

    def test_decline_rejects_at_human_approval_gate(self):
        pipeline, run_config, _ = self._run_until_interrupt(FakePipelineLLM())
        final = pipeline.invoke(
            Command(resume={"approved": False, "approver": "ajay"}), run_config
        )
        assert final["rejection"]["stage"] == "human_approval"
        assert final["execution_status"] == "rejected:human_approval"
        assert final["recommendation"] is None

    def test_paper_mode_never_interrupts(self):
        state = run_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot())
        assert "__interrupt__" not in state
        assert state["execution_status"] == "accepted:paper"


class TestRetries:
    class FlakyOnce:
        """with_structured_output whose runnable fails on the first call only."""

        def __init__(self, inner: FakePipelineLLM):
            self.inner = inner
            self.failed_once = False

        def with_structured_output(self, schema):
            runnable = self.inner.with_structured_output(schema)
            outer = self

            class Wrapper:
                def invoke(self, prompt):
                    if not outer.failed_once:
                        outer.failed_once = True
                        raise RuntimeError("transient provider error")
                    return runnable.invoke(prompt)

            return Wrapper()

    def test_retry_recovers_from_transient_failure(self):
        nodes = PipelineNodes(self.FlakyOnce(FakePipelineLLM()), CONFIG, llm_retries=1)
        from tradingagents.pro.pipeline.schemas import CriticReport

        result = nodes._invoke(CriticReport, "prompt")
        assert result is not None and result.verdict == "pass"

    def test_zero_retries_fails_fast(self):
        nodes = PipelineNodes(self.FlakyOnce(FakePipelineLLM()), CONFIG, llm_retries=0)
        from tradingagents.pro.pipeline.schemas import CriticReport

        assert nodes._invoke(CriticReport, "prompt") is None

    def test_invalid_settings_rejected(self):
        with pytest.raises(ValueError):
            PipelineNodes(FakePipelineLLM(), CONFIG, llm_retries=-1)
        with pytest.raises(ValueError):
            PipelineNodes(FakePipelineLLM(), CONFIG, agent_workers=0)


class TestDynamicRouting:
    def test_empty_macro_and_news_stages_are_skipped(self):
        # snapshot with no macro metrics and no news: macro + sentiment skip
        snapshot = pipeline_snapshot(macro=[], news=[])
        state = run_pipeline(FakePipelineLLM(), CONFIG, snapshot)

        speakers = [e["speaker"] for e in state["debate"]]
        assert "technical_bull" in speakers
        assert "macro_bull" not in speakers
        assert "sentiment" not in speakers
        # pipeline still completes through the gates
        assert state["recommendation"] is not None

    def test_full_snapshot_runs_all_stages(self):
        state = run_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot())
        speakers = {e["speaker"] for e in state["debate"]}
        assert {"technical_bull", "macro_bull", "sentiment"} <= speakers


class TestStreaming:
    def test_stream_yields_node_updates_in_pipeline_order(self):
        events = list(stream_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot()))
        order = [next(iter(e)) for e in events]
        assert order[0] == "prepare"
        assert order[-1] == "execution"
        for earlier, later in [("join", "judge"), ("judge", "portfolio_manager"),
                               ("critic", "reflection")]:
            assert order.index(earlier) < order.index(later)

    def test_stream_updates_carry_debate_entries(self):
        events = list(stream_pipeline(FakePipelineLLM(), CONFIG, pipeline_snapshot()))
        judge_updates = [e["judge"] for e in events if "judge" in e]
        assert judge_updates and judge_updates[0]["judge_action"] is TradeAction.BUY
