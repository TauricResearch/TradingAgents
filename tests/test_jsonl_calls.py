"""Tests for Phase 0 — JSONL call log (T0.5).

When ``StatsCallbackHandler`` is given a ``jsonl_path``, every LLM call
that fires ``on_llm_end`` writes one structured line to that file. This
validates the file path resolution, schema, session/sequence tracking,
latency computation, and the disabled-by-default behavior.
"""

from __future__ import annotations

import json
import uuid
import time
from pathlib import Path

import pytest

from cli.stats_handler import StatsCallbackHandler


# -------------------------------------------------------------------- #
# Helpers
# -------------------------------------------------------------------- #


def _make_llm_result(
    *,
    fingerprint: str = None,
    model: str = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
):
    """Minimal LLMResult-like object with the fields the handler reads."""
    from langchain_core.outputs import ChatGeneration, LLMResult
    from langchain_core.messages import AIMessage

    msg = AIMessage(
        content="hello",
        response_metadata={"model_name": model} if model else {},
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    )
    gen = ChatGeneration(message=msg, generation_info={})
    llm_output = {}
    if model is not None:
        llm_output["model_name"] = model
    if fingerprint is not None:
        llm_output["system_fingerprint"] = fingerprint
    return LLMResult(generations=[[gen]], llm_output=llm_output)


def _fire_call(handler, *, fingerprint, model, tokens_in=10, tokens_out=20,
               tags=None, metadata=None, call_id=None):
    """Fire one paired start→end against the handler."""
    rid = call_id or uuid.uuid4()
    handler.on_chat_model_start({}, [[]], run_id=rid)
    handler.on_llm_end(
        _make_llm_result(
            fingerprint=fingerprint, model=model,
            tokens_in=tokens_in, tokens_out=tokens_out,
        ),
        run_id=rid, tags=tags, metadata=metadata,
    )
    return rid


# -------------------------------------------------------------------- #
# Disabled path (default constructor) — bit-identical to pre-T0.5
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestDisabledByDefault:
    def test_no_jsonl_path_means_no_file(self, tmp_path):
        h = StatsCallbackHandler()  # jsonl_path defaults to None
        _fire_call(h, fingerprint="fp_a", model="m1")
        # Nothing landed anywhere in tmp_path (or in cwd for that matter)
        assert not list(tmp_path.glob("*.jsonl"))
        # Stats handler still works for in-memory data
        stats = h.get_stats()
        assert stats["llm_calls"] == 1
        assert stats["jsonl_path"] is None
        assert stats["session_id"]  # always present

    def test_session_id_is_uuid_string(self):
        h = StatsCallbackHandler()
        # Validates the default-generated session_id is parseable as UUID
        uuid.UUID(h.session_id)  # raises if malformed


# -------------------------------------------------------------------- #
# Enabled path — file is written, schema is right
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestJsonlPersistence:
    def test_writes_one_line_per_call(self, tmp_path):
        jsonl = tmp_path / "calls" / "session.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl, session_id="s1")
        _fire_call(h, fingerprint="fp_a", model="m1")
        _fire_call(h, fingerprint="fp_b", model="m2")
        _fire_call(h, fingerprint="fp_c", model="m3")

        assert jsonl.exists()
        lines = jsonl.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # all valid JSON

    def test_record_schema(self, tmp_path):
        """Every required field is present and typed correctly."""
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl, session_id="abc")
        _fire_call(
            h, fingerprint="fp_x", model="gpt-5.4-20260101",
            tokens_in=100, tokens_out=50,
            tags=["seq:1", "langgraph"],
            metadata={"langgraph_node": "Bull Researcher", "langgraph_step": 3},
        )
        record = json.loads(jsonl.read_text().splitlines()[0])

        # Required keys present
        for key in ("ts", "type", "session_id", "call_seq", "call_id",
                    "model", "fingerprint", "tokens_in", "tokens_out",
                    "latency_ms", "tags", "metadata"):
            assert key in record, f"missing: {key}"

        # Type + value checks
        assert record["type"] == "llm_end"
        assert record["session_id"] == "abc"
        assert record["call_seq"] == 1
        assert record["model"] == "gpt-5.4-20260101"
        assert record["fingerprint"] == "fp_x"
        assert record["tokens_in"] == 100
        assert record["tokens_out"] == 50
        assert record["tags"] == ["seq:1", "langgraph"]
        assert record["metadata"]["langgraph_node"] == "Bull Researcher"
        # ISO 8601 with Z suffix
        assert record["ts"].endswith("Z")

    def test_call_seq_monotonic(self, tmp_path):
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        for i in range(5):
            _fire_call(h, fingerprint=f"fp_{i}", model="m")
        records = [json.loads(l) for l in jsonl.read_text().splitlines()]
        assert [r["call_seq"] for r in records] == [1, 2, 3, 4, 5]

    def test_session_id_constant_across_calls(self, tmp_path):
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl, session_id="my-session")
        for i in range(3):
            _fire_call(h, fingerprint=f"fp_{i}", model="m")
        records = [json.loads(l) for l in jsonl.read_text().splitlines()]
        assert {r["session_id"] for r in records} == {"my-session"}

    def test_latency_ms_populated(self, tmp_path):
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        rid = uuid.uuid4()
        h.on_chat_model_start({}, [[]], run_id=rid)
        time.sleep(0.02)  # ~20ms
        h.on_llm_end(_make_llm_result(fingerprint="fp", model="m"), run_id=rid)
        record = json.loads(jsonl.read_text().splitlines()[0])
        assert record["latency_ms"] is not None
        assert record["latency_ms"] >= 15  # generous lower bound, real-world wall time

    def test_latency_is_none_if_start_was_missed(self, tmp_path):
        """If on_llm_start never fired (some edge case in async impls),
        latency_ms should be None rather than crash or a misleading 0."""
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        # Fire end without start; provider id is captured anyway
        h.on_llm_end(
            _make_llm_result(fingerprint="fp", model="m"),
            run_id=uuid.uuid4(),
        )
        record = json.loads(jsonl.read_text().splitlines()[0])
        assert record["latency_ms"] is None
        assert record["model"] == "m"

    def test_call_id_correlates_with_start(self, tmp_path):
        """The run_id passed to LangChain shows up as call_id in the record."""
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        rid = uuid.uuid4()
        _fire_call(h, fingerprint="fp", model="m", call_id=rid)
        record = json.loads(jsonl.read_text().splitlines()[0])
        assert record["call_id"] == str(rid)

    def test_parent_directory_auto_created(self, tmp_path):
        """jsonl_path may be deep — mkdir parents=True at construction."""
        jsonl = tmp_path / "a" / "b" / "c" / "calls.jsonl"
        assert not jsonl.parent.exists()
        StatsCallbackHandler(jsonl_path=jsonl)
        assert jsonl.parent.exists()

    def test_appends_across_handler_lifetime(self, tmp_path):
        """A second batch of calls APPENDS to existing file (doesn't truncate)."""
        jsonl = tmp_path / "calls.jsonl"
        h1 = StatsCallbackHandler(jsonl_path=jsonl, session_id="s1")
        _fire_call(h1, fingerprint="fp_a", model="m1")
        # New handler, same jsonl path. Realistic flow: CLI run #2 against
        # the same audit directory should not stomp run #1's data.
        h2 = StatsCallbackHandler(jsonl_path=jsonl, session_id="s2")
        _fire_call(h2, fingerprint="fp_b", model="m2")
        lines = jsonl.read_text().splitlines()
        assert len(lines) == 2
        sessions = [json.loads(l)["session_id"] for l in lines]
        assert sessions == ["s1", "s2"]

    def test_metadata_and_tags_default_to_empty(self, tmp_path):
        """Missing tags/metadata kwargs land as empty list / dict, not None."""
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        rid = uuid.uuid4()
        h.on_chat_model_start({}, [[]], run_id=rid)
        h.on_llm_end(_make_llm_result(fingerprint="fp", model="m"), run_id=rid)
        record = json.loads(jsonl.read_text().splitlines()[0])
        assert record["tags"] == []
        assert record["metadata"] == {}


# -------------------------------------------------------------------- #
# In-memory state still works (T0.2 contract preserved)
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestInMemoryContractStillHolds:
    def test_fingerprints_list_still_populated_when_jsonl_enabled(self, tmp_path):
        """T0.2's fingerprints list must remain the in-memory truth even
        when JSONL is on, so CLI display code doesn't break."""
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        _fire_call(h, fingerprint="fp_a", model="m1")
        _fire_call(h, fingerprint="fp_b", model="m2")

        stats = h.get_stats()
        assert len(stats["fingerprints"]) == 2
        assert stats["fingerprints"][0]["fingerprint"] == "fp_a"
        assert stats["fingerprints"][1]["fingerprint"] == "fp_b"
        assert stats["llm_calls"] == 2
        assert stats["tokens_in"] == 20  # 10 per call * 2
        assert stats["tokens_out"] == 40

    def test_get_stats_reports_jsonl_path_when_enabled(self, tmp_path):
        jsonl = tmp_path / "calls.jsonl"
        h = StatsCallbackHandler(jsonl_path=jsonl)
        stats = h.get_stats()
        assert stats["jsonl_path"] == str(jsonl)
