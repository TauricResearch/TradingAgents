"""Tests for ``tradingagents.audit.replay`` (T1.7).

Four layers:

1. **Replayer API** — load / summary / tree / verify_chain.
2. **verify_prompts** — recorded hash vs current registry hash,
   detection of missing templates and drifted templates.
3. **CLI** — argparse entry point produces the right exit codes for
   automation (CI pipelines hooked into this for "did the prompts
   drift since this trace?" checks).
4. **End-to-end with real TraceCallback** — a callback-produced trace
   round-trips through the replayer cleanly.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tradingagents.audit import (
    GENESIS_HASH,
    HashChainLedger,
    PromptRegistry,
    Replayer,
    TraceCallback,
)
from tradingagents.audit.replay import main as cli_main
from tradingagents.audit.schemas import (
    LLM_END,
    LLM_START,
    NODE_ENTER,
    TOOL_START,
    TraceRecord,
    hash_payload,
)


# -------------------------------------------------------------------- #
# Fixture: write a minimal valid chained trace
# -------------------------------------------------------------------- #


def _build_chained_trace(
    path: Path,
    records: list,
) -> None:
    """Append `records` (list of TraceRecord) through a real HashChainLedger.

    Records are mutated in place so callers can inspect their
    ``prev_hash`` after writing.
    """
    ledger = HashChainLedger(path)
    for rec in records:
        ledger.append(rec)


def _mk(type_: str, *, payload=None, node=None, parent=None, session="s1") -> TraceRecord:
    payload = payload or {}
    return TraceRecord(
        record_id=str(uuid.uuid4()),
        session_id=session,
        parent_record_id=parent,
        ts=datetime.now(timezone.utc),
        type=type_,
        node=node,
        payload=payload,
        payload_hash=hash_payload(payload),
    )


@pytest.fixture
def trivial_trace(tmp_path):
    """Three-record chained trace: node_enter → llm_start → llm_end."""
    path = tmp_path / "trace.jsonl"
    node = _mk(NODE_ENTER, node="Bull Researcher")
    llm_s = _mk(LLM_START, node="Bull Researcher", parent=node.record_id,
                payload={
                    "messages": [{"role": "user", "content": "analyze AAPL"}],
                    "metadata": {
                        "prompt_key": "researchers/bull_researcher",
                        "prompt_version": "v1",
                        "prompt_hash": "DEADBEEF",  # will be overridden in tests
                    },
                })
    llm_e = _mk(LLM_END, node="Bull Researcher", parent=node.record_id,
                payload={
                    "response": {
                        "generations": [[{"message": {"content": "BUY"}}]],
                        "llm_output": {
                            "system_fingerprint": "fp_abc",
                            "model_name": "gpt-5.4-20260101",
                        },
                    },
                })
    _build_chained_trace(path, [node, llm_s, llm_e])
    return path


# -------------------------------------------------------------------- #
# Replayer.records() + summary() + tree()
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestReplayerBasics:
    def test_records_reads_all_lines(self, trivial_trace):
        r = Replayer(trivial_trace)
        recs = r.records()
        assert len(recs) == 3
        assert {r["type"] for r in recs} == {NODE_ENTER, LLM_START, LLM_END}

    def test_records_skips_blank_lines(self, tmp_path):
        path = tmp_path / "t.jsonl"
        ledger = HashChainLedger(path)
        ledger.append(_mk(LLM_START))
        # Manually append blank lines
        with open(path, "a") as f:
            f.write("\n\n   \n")
        ledger.append(_mk(LLM_END))
        recs = Replayer(path).records()
        assert len(recs) == 2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Replayer(tmp_path / "nope.jsonl").records()

    def test_summary_counts(self, trivial_trace):
        s = Replayer(trivial_trace).summary()
        assert s.session_id == "s1"
        assert s.total_records == 3
        assert s.llm_calls == 1
        assert s.tool_calls == 0
        assert s.nodes_visited == ["Bull Researcher"]
        assert "fp_abc" in s.fingerprints_seen
        assert "gpt-5.4-20260101" in s.models_seen

    def test_summary_wall_seconds(self, tmp_path):
        path = tmp_path / "t.jsonl"
        # Two records with explicit timestamps 5 seconds apart
        a = _mk(LLM_START)
        a.ts = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        b = _mk(LLM_END)
        b.ts = datetime(2026, 1, 15, 14, 0, 5, tzinfo=timezone.utc)
        _build_chained_trace(path, [a, b])
        s = Replayer(path).summary()
        assert s.wall_seconds == pytest.approx(5.0)

    def test_tree_links_parent_child(self, trivial_trace):
        roots = Replayer(trivial_trace).tree()
        # Three records: one root (NODE_ENTER), two children
        assert len(roots) == 1
        root = roots[0]
        assert root["type"] == NODE_ENTER
        # Two children: LLM_START and LLM_END both point at the node
        assert len(root["children"]) == 2
        child_types = {c["type"] for c in root["children"]}
        assert child_types == {LLM_START, LLM_END}

    def test_tree_orphan_becomes_root(self, tmp_path):
        """A record whose parent isn't in the file is reported as a root."""
        path = tmp_path / "t.jsonl"
        # parent_record_id points at something not in this file
        orphan = _mk(LLM_START, parent="ghost")
        _build_chained_trace(path, [orphan])
        roots = Replayer(path).tree()
        assert len(roots) == 1
        assert roots[0]["record_id"] == orphan.record_id


# -------------------------------------------------------------------- #
# verify_chain — wraps T1.3
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestReplayerVerifyChain:
    def test_intact_chain_verifies_clean(self, trivial_trace):
        result = Replayer(trivial_trace).verify_chain()
        assert result.ok is True
        assert result.format == "chained"

    def test_tampered_chain_reports_broken(self, trivial_trace):
        # Edit the middle record's payload
        lines = trivial_trace.read_text().splitlines()
        rec = json.loads(lines[1])
        rec["payload"]["messages"][0]["content"] = "TAMPERED"
        from tradingagents.audit.schemas import canonical_json
        lines[1] = canonical_json(rec)
        trivial_trace.write_text("\n".join(lines) + "\n")

        result = Replayer(trivial_trace).verify_chain()
        assert result.ok is False
        assert result.format == "corrupt"


# -------------------------------------------------------------------- #
# verify_prompts — the novel T1.7 check
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestVerifyPrompts:
    def _build_trace_with_recorded_hash(self, tmp_path, *, recorded_hash):
        """Build a trace whose single LLM_START claims this hash."""
        path = tmp_path / "trace.jsonl"
        node = _mk(NODE_ENTER, node="Bull")
        llm_s = _mk(LLM_START, node="Bull",
                    payload={
                        "metadata": {
                            "prompt_key": "researchers/bull_researcher",
                            "prompt_version": "v1",
                            "prompt_hash": recorded_hash,
                        },
                    })
        _build_chained_trace(path, [node, llm_s])
        return path

    def test_matching_hash_reports_ok(self, tmp_path):
        # First, find out what the current bull_researcher.v1 hash is
        from tradingagents.audit.prompt_registry import default_registry, reset_default_registry
        reset_default_registry()
        registry = default_registry()
        _, current_hash = registry.load("researchers/bull_researcher", "v1")

        # Build a trace claiming the same hash
        path = self._build_trace_with_recorded_hash(tmp_path, recorded_hash=current_hash)

        checks = Replayer(path).verify_prompts()
        assert len(checks) == 1
        assert checks[0].matches is True
        assert checks[0].template_missing is False

    def test_mismatched_hash_flagged(self, tmp_path):
        """A recorded hash that no longer matches the on-disk template
        flags as drift. This catches post-hoc prompt edits."""
        path = self._build_trace_with_recorded_hash(
            tmp_path, recorded_hash="0" * 64,  # definitely not the real one
        )
        checks = Replayer(path).verify_prompts()
        assert checks[0].matches is False
        assert checks[0].template_missing is False
        assert checks[0].recorded_hash == "0" * 64
        assert checks[0].current_hash is not None  # template still exists

    def test_missing_template_flagged(self, tmp_path):
        """Loading a key not in the registry surfaces as
        template_missing=True. This is the case where a prompt was
        deleted entirely rather than edited."""
        path = tmp_path / "trace.jsonl"
        rec = _mk(LLM_START, node="Mystery",
                  payload={
                      "metadata": {
                          "prompt_key": "totally/made_up_agent",
                          "prompt_version": "v1",
                          "prompt_hash": "abc",
                      },
                  })
        _build_chained_trace(path, [rec])
        checks = Replayer(path).verify_prompts()
        assert len(checks) == 1
        assert checks[0].matches is False
        assert checks[0].template_missing is True
        assert checks[0].current_hash is None

    def test_no_metadata_skipped(self, tmp_path):
        """LLM_START records without prompt metadata (e.g. pre-T1.4
        traces or analyst calls not yet migrated) don't appear in the
        result list — they aren't 'failures', they're 'no provenance
        recorded'."""
        path = tmp_path / "trace.jsonl"
        rec = _mk(LLM_START, node="X", payload={})
        _build_chained_trace(path, [rec])
        checks = Replayer(path).verify_prompts()
        assert checks == []

    def test_trader_two_template_records(self, tmp_path):
        """Trader records two hashes (system + user). Each should appear
        as its own PromptVerification row so a mismatch localises."""
        path = tmp_path / "trace.jsonl"
        from tradingagents.audit.prompt_registry import default_registry, reset_default_registry
        reset_default_registry()
        registry = default_registry()
        _, sys_hash = registry.load("trader/trader_system", "v1")
        _, usr_hash = registry.load("trader/trader_user", "v1")

        rec = _mk(LLM_START, node="Trader",
                  payload={
                      "metadata": {
                          "prompt_key": "trader/messages",
                          "prompt_version": "system=v1,user=v1",
                          "prompt_hash_system": sys_hash,
                          "prompt_hash_user": usr_hash,
                      },
                  })
        _build_chained_trace(path, [rec])
        checks = Replayer(path).verify_prompts()
        # The "trader/messages" key isn't loadable (it's a composite
        # name) — we'd expect 0 entries for that one. The trader_system
        # and trader_user entries should both be present and matching.
        keys = {c.prompt_key for c in checks}
        assert "trader/trader_system" in keys
        assert "trader/trader_user" in keys
        for c in checks:
            if c.prompt_key in ("trader/trader_system", "trader/trader_user"):
                assert c.matches, f"{c.prompt_key}: {c}"


# -------------------------------------------------------------------- #
# CLI
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestCLI:
    def test_verify_exits_0_for_intact(self, trivial_trace, capsys):
        rc = cli_main(["verify", str(trivial_trace)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out
        assert "chained" in out

    def test_verify_exits_1_for_tampered(self, trivial_trace, capsys):
        # Edit line 2's payload, then verify
        lines = trivial_trace.read_text().splitlines()
        rec = json.loads(lines[1])
        rec["payload"]["messages"][0]["content"] = "FORGED"
        from tradingagents.audit.schemas import canonical_json
        lines[1] = canonical_json(rec)
        trivial_trace.write_text("\n".join(lines) + "\n")

        rc = cli_main(["verify", str(trivial_trace)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "BROKEN" in out

    def test_summary_outputs_session(self, trivial_trace, capsys):
        rc = cli_main(["summary", str(trivial_trace)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "s1" in out
        assert "Bull Researcher" in out

    def test_summary_json_mode_parseable(self, trivial_trace, capsys):
        rc = cli_main(["summary", str(trivial_trace), "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["session_id"] == "s1"
        assert data["llm_calls"] == 1

    def test_prompts_exits_1_when_hash_drifts(self, tmp_path, capsys):
        # Trace claims a non-existent hash for bull_researcher.v1
        rec = _mk(LLM_START, node="Bull",
                  payload={
                      "metadata": {
                          "prompt_key": "researchers/bull_researcher",
                          "prompt_version": "v1",
                          "prompt_hash": "0" * 64,  # not the real hash
                      },
                  })
        path = tmp_path / "t.jsonl"
        _build_chained_trace(path, [rec])

        rc = cli_main(["prompts", str(path)])
        assert rc == 1  # non-zero because at least one mismatch
        out = capsys.readouterr().out
        assert "MISMATCH" in out

    def test_tree_command_runs(self, trivial_trace, capsys):
        rc = cli_main(["tree", str(trivial_trace)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Bull Researcher" in out


# -------------------------------------------------------------------- #
# End-to-end with real TraceCallback
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestEndToEnd:
    """A trace produced by the real TraceCallback (T1.2 + T1.3) should
    round-trip through the replayer cleanly: chain verifies, summary
    populates, tree reconstructs."""

    def test_callback_trace_verifies_and_summarises(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=path, session_id="real-session")

        # Simulate a sequence of events
        rid1 = uuid.uuid4()
        cb.on_chain_start(
            {"name": "Bull Researcher"},
            {"market_report": "..."},
            run_id=rid1,
            metadata={"langgraph_node": "Bull Researcher"},
        )
        rid2 = uuid.uuid4()
        cb.on_chat_model_start(
            {}, [[]],
            run_id=rid2, parent_run_id=rid1,
            metadata={
                "langgraph_node": "Bull Researcher",
                "prompt_key": "researchers/bull_researcher",
                "prompt_version": "v1",
                "prompt_hash": "fake_hash_for_test",
            },
        )
        msg = AIMessage(
            content="BUY",
            response_metadata={"system_fingerprint": "fp_test", "model_name": "test-model"},
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
        gen = ChatGeneration(message=msg, generation_info={})
        cb.on_llm_end(
            LLMResult(generations=[[gen]], llm_output={"system_fingerprint": "fp_test", "model_name": "test-model"}),
            run_id=rid2, parent_run_id=rid1,
            metadata={"langgraph_node": "Bull Researcher"},
        )
        cb.on_chain_end({"bull_history": "..."}, run_id=rid1)

        # Now feed through the replayer
        r = Replayer(path)
        assert r.verify_chain().ok
        s = r.summary()
        assert s.session_id == "real-session"
        assert s.llm_calls == 1
        assert "Bull Researcher" in s.nodes_visited
        assert "fp_test" in s.fingerprints_seen
        # Prompts: recorded hash is fake, registry has real one — mismatch
        checks = r.verify_prompts()
        assert len(checks) == 1
        assert checks[0].matches is False
