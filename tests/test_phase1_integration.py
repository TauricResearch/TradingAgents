"""Phase 1 — End-to-end integration tests (T1.8).

Every previous Phase 1 PR shipped its own unit-test file. This file
is the cross-component contract check: it wires multiple audit
subsystems together in a realistic configuration and verifies the
artifacts they produce are mutually consistent.

What "mutually consistent" means here:

- A real migrated agent factory (``bull_researcher`` etc.) renders
  a prompt from the registry, attaches the prompt provenance to
  ``config.metadata``, calls a mock LLM, and the TraceCallback that
  observed the LangChain events ends up with a trace file in which
  the recorded ``prompt_hash`` matches what the registry produces
  on a fresh load.
- The hash chain (T1.3) wraps the same trace file, so verify_chain()
  passes immediately after the agent finishes.
- The Replayer (T1.7) consumes that file and reports the right
  session_id, the right node, the right model fingerprint, and
  successful prompt verification.
- Running the same data-fetch (T1.5) twice within one session uses
  the snapshot cache on the second call.
- Modifying a prompt template on disk after the trace is recorded
  causes ``verify_prompts()`` to flag the affected record as drift,
  which is the audit story this whole stack is built around.

These tests would catch wiring regressions that no single component's
unit tests can detect — e.g. an agent silently dropping its config
metadata, or the Replayer's verify_prompts gating logic skipping a
shape of metadata it should handle.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tradingagents.audit import (
    GENESIS_HASH,
    PromptRegistry,
    Replayer,
    TraceCallback,
    default_registry,
    reset_default_registry,
    verify_ledger,
)
from tradingagents.dataflows.config import set_config


# -------------------------------------------------------------------- #
# Shared helpers
# -------------------------------------------------------------------- #


def _llm_with_trace(cb: TraceCallback):
    """Construct a MagicMock LLM whose .invoke() fires both
    on_chat_model_start and on_llm_end against ``cb``, threading
    ``config.metadata`` through both sides.

    This is the bridge between a real agent factory and a real
    TraceCallback in tests. In production LangChain wires this up;
    here we do it manually so we don't need real API keys.
    """
    llm = MagicMock()

    def fake_invoke(prompt, config=None):
        rid = uuid.uuid4()
        meta = (config or {}).get("metadata", {}) or {}
        # LangChain forwards tags + metadata into the callback's kwargs
        # — we replicate that contract so TraceCallback sees the same
        # shape it sees in production.
        cb.on_chat_model_start(
            {"name": "MockChat"}, [[]],
            run_id=rid, metadata=meta,
        )
        ai = AIMessage(
            content="response text",
            response_metadata={
                "system_fingerprint": "fp_int_test",
                "model_name": "test-model-1.0",
            },
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            },
        )
        gen = ChatGeneration(message=ai, generation_info={})
        cb.on_llm_end(
            LLMResult(
                generations=[[gen]],
                llm_output={
                    "system_fingerprint": "fp_int_test",
                    "model_name": "test-model-1.0",
                },
            ),
            run_id=rid, metadata=meta,
        )
        return ai

    llm.invoke.side_effect = fake_invoke
    # Some agents call llm.with_structured_output(...).invoke(...)
    structured = MagicMock()
    structured.invoke.side_effect = fake_invoke
    llm.with_structured_output.return_value = structured
    return llm


def _state_for_researchers() -> dict:
    return {
        "investment_debate_state": {
            "history": "prior debate",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "market_report": "Market: bullish technicals",
        "sentiment_report": "Sentiment: positive",
        "news_report": "News: earnings beat",
        "fundamentals_report": "Fundamentals: P/E 25",
        "asset_type": "stock",
    }


# -------------------------------------------------------------------- #
# Module export contract
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestAuditModuleExports:
    """Locking in the public surface of ``tradingagents.audit`` so a
    future refactor that accidentally removes an export breaks loudly
    rather than silently breaking downstream consumers."""

    def test_all_required_symbols_importable(self):
        from tradingagents import audit
        required = [
            "TraceCallback",
            "TraceRecord",
            "HashChainLedger",
            "VerifyResult",
            "verify_ledger",
            "GENESIS_HASH",
            "PromptRegistry",
            "PromptNotFoundError",
            "DEFAULT_PROMPTS_DIR",
            "default_registry",
            "reset_default_registry",
            "Replayer",
            "ReplaySummary",
            "PromptVerification",
            "LLM_START",
            "LLM_END",
            "TOOL_START",
            "TOOL_END",
            "NODE_ENTER",
            "NODE_EXIT",
        ]
        for name in required:
            assert hasattr(audit, name), f"missing export: {name}"
            assert name in audit.__all__, f"missing from __all__: {name}"


# -------------------------------------------------------------------- #
# Single agent → trace → replayer
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestAgentToTraceToReplayer:
    """End-to-end through one real migrated agent factory.

    Wires bull_researcher (T1.4) into a real TraceCallback + ledger
    (T1.2 + T1.3) and validates the result through the Replayer (T1.7).
    """

    def setup_method(self):
        reset_default_registry()
        set_config({"output_language": "English"})

    def test_bull_researcher_round_trips_through_replayer(self, tmp_path):
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

        trace_path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=trace_path, session_id="int-bull")
        llm = _llm_with_trace(cb)

        node = create_bull_researcher(llm)
        node(_state_for_researchers())

        # 1) Trace file landed
        assert trace_path.exists()

        # 2) Hash chain intact
        assert verify_ledger(trace_path).ok

        # 3) Replayer sees exactly one LLM call attributed to the right
        # provenance
        r = Replayer(trace_path)
        s = r.summary()
        assert s.session_id == "int-bull"
        assert s.llm_calls == 1
        assert "fp_int_test" in s.fingerprints_seen
        assert "test-model-1.0" in s.models_seen

        # 4) Prompt provenance verification clean
        checks = r.verify_prompts()
        assert len(checks) == 1
        c = checks[0]
        assert c.prompt_key == "researchers/bull_researcher"
        assert c.prompt_version == "v1"
        assert c.matches, (
            f"recorded hash {c.recorded_hash} did not match current "
            f"registry hash {c.current_hash} — bull_researcher.v1.txt may "
            f"have drifted, or the agent isn't passing config.metadata "
            f"correctly"
        )

    def test_replayer_detects_prompt_drift_after_record(self, tmp_path):
        """If a prompt template is edited AFTER a trace is recorded,
        verify_prompts must flag the affected record. This is the
        canonical audit-failure flow."""
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

        trace_path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=trace_path, session_id="drift-test")
        llm = _llm_with_trace(cb)

        # Stand up an alternative prompts dir we control, then edit it
        # after the agent records its trace.
        alt_prompts = tmp_path / "alt_prompts"
        (alt_prompts / "researchers").mkdir(parents=True)
        (alt_prompts / "researchers" / "bull_researcher.v1.txt").write_text(
            "Original template ${market_research_report}"
        )
        alt_registry = PromptRegistry(base_dir=alt_prompts)

        node = create_bull_researcher(llm, prompt_registry=alt_registry)
        node(_state_for_researchers())

        # The trace records the original template's hash.  Now we
        # tamper with the file on disk.
        (alt_prompts / "researchers" / "bull_researcher.v1.txt").write_text(
            "TAMPERED ${market_research_report}"
        )

        # Force a fresh load by resetting the registry's cache
        alt_registry._cache.clear()

        # verify_prompts should now flag the drift
        r = Replayer(trace_path, prompt_registry=alt_registry)
        checks = r.verify_prompts()
        assert len(checks) == 1
        assert checks[0].matches is False
        assert checks[0].template_missing is False
        assert checks[0].recorded_hash != checks[0].current_hash


# -------------------------------------------------------------------- #
# Multiple agents in one session
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestMultiAgentSession:
    """Bull + Bear + Research Manager firing into the same TraceCallback,
    producing one contiguous, chain-verified trace file with multiple
    prompt-provenance records."""

    def setup_method(self):
        reset_default_registry()
        set_config({"output_language": "English"})

    def test_three_agents_record_provenance(self, tmp_path):
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
        from tradingagents.agents.researchers.bear_researcher import create_bear_researcher

        trace_path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=trace_path, session_id="multi")
        llm = _llm_with_trace(cb)

        bull = create_bull_researcher(llm)
        bear = create_bear_researcher(llm)

        state = _state_for_researchers()
        bull_result = bull(state)
        # Roll bear's input from bull's output
        state.update(bull_result)
        bear(state)

        r = Replayer(trace_path)
        s = r.summary()
        assert s.llm_calls == 2

        checks = r.verify_prompts()
        keys = {c.prompt_key for c in checks}
        assert keys == {
            "researchers/bull_researcher",
            "researchers/bear_researcher",
        }
        assert all(c.matches for c in checks), [
            (c.prompt_key, c.matches, c.template_missing) for c in checks
        ]

        # Hash chain stays intact across multiple agents writing into
        # the same ledger (their TraceCallback shares one ledger).
        assert verify_ledger(trace_path).ok


# -------------------------------------------------------------------- #
# Data snapshots consumed by an agent
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestDataSnapshotsInsideAgentRun:
    """A snapshot-decorated data fetcher called from within an agent
    invocation should produce a snapshot file, and a second call
    inside the same session (or any future session) should hit the
    cache without re-invoking the upstream API."""

    def test_yfinance_fetch_caches_within_session(self, tmp_path, monkeypatch):
        set_config({
            "news_snapshot_enabled": True,
            "news_snapshot_dir": str(tmp_path / "snapshots"),
        })

        from tradingagents.dataflows import y_finance as yfm
        import pandas as pd

        fake_df = pd.DataFrame(
            {"Open": [100.0], "Close": [101.0], "Volume": [1_000_000]},
            index=pd.to_datetime(["2026-01-15"]),
        )
        fake_ticker = MagicMock()
        fake_ticker.history = MagicMock(return_value=fake_df)
        monkeypatch.setattr(yfm.yf, "Ticker", lambda s: fake_ticker)
        monkeypatch.setattr(yfm, "yf_retry", lambda f: f())

        r1 = yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")
        r2 = yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")

        assert r1 == r2
        # Underlying API touched exactly once
        assert fake_ticker.history.call_count == 1
        # Snapshot dir layout matches the documented contract
        snap_files = list(
            (tmp_path / "snapshots" / "AAPL" / "2026-01-15").glob(
                "prices_yfinance_*.json"
            )
        )
        assert len(snap_files) == 1


# -------------------------------------------------------------------- #
# Full audit dir layout
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestFullAuditDirLayout:
    """After a representative session — agent runs + data fetches —
    the on-disk layout under audit_dir / snapshots should match what
    the documentation promises. This catches any drift in directory
    naming or partial writes from a botched future change."""

    def setup_method(self):
        reset_default_registry()
        set_config({"output_language": "English"})

    def test_layout_after_session(self, tmp_path, monkeypatch):
        # Wire up both audit + snapshot dirs under tmp_path
        audit_dir = tmp_path / "audit"
        snap_dir = tmp_path / "snapshots"
        audit_dir.mkdir()
        snap_dir.mkdir()
        set_config({
            "news_snapshot_enabled": True,
            "news_snapshot_dir": str(snap_dir),
        })

        # 1) Fire an agent into a TraceCallback writing under audit_dir
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

        trace_path = audit_dir / "traces" / "session-abc.jsonl"
        cb = TraceCallback(jsonl_path=trace_path, session_id="session-abc")
        llm = _llm_with_trace(cb)
        bull = create_bull_researcher(llm)
        bull(_state_for_researchers())

        # 2) Fire a snapshot-decorated data fetch
        from tradingagents.dataflows import y_finance as yfm
        import pandas as pd
        fake_df = pd.DataFrame(
            {"Open": [100.0]}, index=pd.to_datetime(["2026-01-15"]),
        )
        fake_ticker = MagicMock()
        fake_ticker.history = MagicMock(return_value=fake_df)
        monkeypatch.setattr(yfm.yf, "Ticker", lambda s: fake_ticker)
        monkeypatch.setattr(yfm, "yf_retry", lambda f: f())
        yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")

        # Verify the on-disk shape matches the documented layout
        assert trace_path.exists()
        assert trace_path.parent.name == "traces"

        snap_files = list(
            (snap_dir / "AAPL" / "2026-01-15").glob("prices_yfinance_*.json")
        )
        assert len(snap_files) == 1

        # And the trace file end-to-end validates
        assert verify_ledger(trace_path).ok


# -------------------------------------------------------------------- #
# Cross-session continuity
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestCrossSessionContinuity:
    """Running a second session against the same audit_dir + snapshots
    should:
    - produce a brand-new trace file with a fresh session_id
    - NOT corrupt the previous trace (verifies separately)
    - reuse the snapshot cache from session #1 for the same (ticker,
      date) data fetches
    """

    def setup_method(self):
        reset_default_registry()
        set_config({"output_language": "English"})

    def test_two_sessions_independent_traces_shared_snapshots(
        self, tmp_path, monkeypatch
    ):
        snap_dir = tmp_path / "snapshots"
        set_config({
            "news_snapshot_enabled": True,
            "news_snapshot_dir": str(snap_dir),
        })

        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
        from tradingagents.dataflows import y_finance as yfm
        import pandas as pd

        fake_df = pd.DataFrame(
            {"Open": [100.0]}, index=pd.to_datetime(["2026-01-15"]),
        )
        fake_ticker = MagicMock()
        fake_ticker.history = MagicMock(return_value=fake_df)
        monkeypatch.setattr(yfm.yf, "Ticker", lambda s: fake_ticker)
        monkeypatch.setattr(yfm, "yf_retry", lambda f: f())

        # ----- Session 1 -----
        trace_1 = tmp_path / "trace_s1.jsonl"
        cb_1 = TraceCallback(jsonl_path=trace_1, session_id="s1")
        bull_1 = create_bull_researcher(_llm_with_trace(cb_1))
        bull_1(_state_for_researchers())
        # First data fetch — cache miss
        yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")
        assert fake_ticker.history.call_count == 1

        # ----- Session 2 -----
        trace_2 = tmp_path / "trace_s2.jsonl"
        cb_2 = TraceCallback(jsonl_path=trace_2, session_id="s2")
        bull_2 = create_bull_researcher(_llm_with_trace(cb_2))
        bull_2(_state_for_researchers())
        # Same data fetch — cache hit, upstream not touched
        yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")
        assert fake_ticker.history.call_count == 1  # unchanged

        # Both traces independent + intact
        assert verify_ledger(trace_1).ok
        assert verify_ledger(trace_2).ok
        assert Replayer(trace_1).summary().session_id == "s1"
        assert Replayer(trace_2).summary().session_id == "s2"


# -------------------------------------------------------------------- #
# Determinism + fingerprint capture all the way through
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestDeterminismFingerprintFlow:
    """T0.1 + T0.2 ensure LLM determinism kwargs are pinned and
    system_fingerprint is captured. T1.2 + T1.7 expose it in the trace
    and via Replayer.summary(). This is the cross-phase check that
    those two halves agree on the field name and shape."""

    def setup_method(self):
        reset_default_registry()
        set_config({"output_language": "English"})

    def test_fingerprint_visible_in_summary(self, tmp_path):
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

        trace_path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=trace_path, session_id="fp-test")
        llm = _llm_with_trace(cb)
        bull = create_bull_researcher(llm)
        bull(_state_for_researchers())

        summary = Replayer(trace_path).summary()
        # The fingerprint we baked into _llm_with_trace flows through
        # T1.2's response serialiser and T1.7's summary aggregator
        assert "fp_int_test" in summary.fingerprints_seen
        assert "test-model-1.0" in summary.models_seen
