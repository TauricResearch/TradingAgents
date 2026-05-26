"""Tests for ``tradingagents.audit.trace_callback`` (T1.2).

End-to-end behavior of the full trace callback: full prompt + response
capture, parent/child correlation via LangChain run_id hierarchy,
LangGraph node attribution, tool I/O serialization, JSONL persistence.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from tradingagents.audit import (
    LLM_END,
    LLM_START,
    NODE_ENTER,
    NODE_EXIT,
    TOOL_END,
    TOOL_START,
    TraceCallback,
)


# -------------------------------------------------------------------- #
# Fixtures / helpers
# -------------------------------------------------------------------- #


@pytest.fixture
def cb(tmp_path):
    """Trace callback writing to a fresh tmp file."""
    path = tmp_path / "traces" / "session.jsonl"
    return TraceCallback(jsonl_path=path, session_id="sess-test")


def _make_llm_result(
    *,
    content: str = "hello",
    model: str = "gpt-5.4-20260101",
    fingerprint: str = "fp_abc",
    tokens_in: int = 10,
    tokens_out: int = 20,
) -> LLMResult:
    msg = AIMessage(
        content=content,
        response_metadata={"model_name": model, "system_fingerprint": fingerprint},
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    )
    gen = ChatGeneration(message=msg, generation_info={"model_name": model})
    return LLMResult(
        generations=[[gen]],
        llm_output={"model_name": model, "system_fingerprint": fingerprint},
    )


def _lines(path: Path) -> list:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


# -------------------------------------------------------------------- #
# Capture: full prompts and full responses
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestFullCapture:
    def test_chat_model_start_captures_full_messages(self, cb, tmp_path):
        rid = uuid.uuid4()
        messages = [[
            SystemMessage(content="You are a trader."),
            HumanMessage(content="Analyze NVDA earnings."),
        ]]
        cb.on_chat_model_start({"name": "ChatOpenAI"}, messages, run_id=rid)

        records = cb.get_records()
        assert len(records) == 1
        rec = records[0]
        assert rec.type == LLM_START
        # Full messages, not metadata
        assert len(rec.payload["messages"]) == 2
        # Content preserved, both messages flattened with batch index
        contents = [m["content"] for m in rec.payload["messages"]]
        assert "trader" in contents[0].lower()
        assert "NVDA" in contents[1]
        # Persisted to disk
        lines = _lines(cb.jsonl_path)
        assert lines[0]["payload"]["messages"] == rec.payload["messages"]

    def test_llm_end_captures_full_response(self, cb):
        rid = uuid.uuid4()
        cb.on_chat_model_start({}, [[]], run_id=rid)
        cb.on_llm_end(
            _make_llm_result(content="The thesis is BUY at $850 entry."),
            run_id=rid,
        )

        records = cb.get_records()
        end_rec = records[-1]
        assert end_rec.type == LLM_END
        # Response content is reachable
        gens = end_rec.payload["response"]["generations"]
        assert gens[0][0]["message"]["content"] == "The thesis is BUY at $850 entry."
        # Fingerprint and usage made it through
        assert end_rec.payload["response"]["llm_output"]["system_fingerprint"] == "fp_abc"

    def test_tool_io_captured(self, cb):
        rid = uuid.uuid4()
        cb.on_tool_start(
            {"name": "get_stock_data"},
            input_str='{"ticker": "NVDA", "start": "2026-01-01"}',
            run_id=rid,
        )
        cb.on_tool_end(
            "OHLCV: 800,810,795,805,1e9\n800.5,815,800,812,9e8",
            run_id=rid,
        )

        records = cb.get_records()
        assert records[0].type == TOOL_START
        assert records[1].type == TOOL_END
        assert "NVDA" in records[0].payload["input"]
        assert "OHLCV" in records[1].payload["output"]


# -------------------------------------------------------------------- #
# Parent / child correlation
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestParentChildCorrelation:
    """LangChain feeds run_id + parent_run_id pairs that we translate
    into record_id / parent_record_id so the trace tree is reconstructable
    without depending on file ordering."""

    def test_llm_inside_chain_carries_chain_id_as_parent(self, cb):
        chain_rid = uuid.uuid4()
        llm_rid = uuid.uuid4()
        cb.on_chain_start({}, {"input": "x"}, run_id=chain_rid)
        cb.on_chat_model_start(
            {}, [[]], run_id=llm_rid, parent_run_id=chain_rid,
        )

        records = cb.get_records()
        chain_rec = records[0]
        llm_rec = records[1]
        # The LLM record's parent_record_id is the CHAIN record's record_id
        # — not the langchain run_id directly.
        assert llm_rec.parent_record_id == chain_rec.record_id
        # Chain itself is top-level
        assert chain_rec.parent_record_id is None

    def test_unknown_parent_run_id_records_none(self, cb):
        """If the parent fired before TraceCallback attached (e.g. mid-run
        reconnect), we record None rather than fabricate a record_id."""
        cb.on_chat_model_start(
            {}, [[]],
            run_id=uuid.uuid4(),
            parent_run_id=uuid.uuid4(),  # never registered
        )
        recs = cb.get_records()
        assert recs[0].parent_record_id is None


# -------------------------------------------------------------------- #
# LangGraph node attribution
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestNodeAttribution:
    def test_node_extracted_from_metadata(self, cb):
        cb.on_chat_model_start(
            {}, [[]],
            run_id=uuid.uuid4(),
            metadata={"langgraph_node": "Bull Researcher", "langgraph_step": 3},
        )
        rec = cb.get_records()[0]
        assert rec.node == "Bull Researcher"

    def test_node_fallback_to_tag(self, cb):
        """Older LangGraph versions tag rather than annotate."""
        cb.on_chat_model_start(
            {}, [[]],
            run_id=uuid.uuid4(),
            tags=["langgraph:Trader", "seq:5"],
        )
        rec = cb.get_records()[0]
        assert rec.node == "Trader"

    def test_node_none_when_unavailable(self, cb):
        cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        rec = cb.get_records()[0]
        assert rec.node is None


# -------------------------------------------------------------------- #
# Persistence + disabled path
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestPersistence:
    def test_records_persist_in_order(self, cb):
        for i in range(5):
            cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        lines = _lines(cb.jsonl_path)
        assert len(lines) == 5
        assert all(l["type"] == LLM_START for l in lines)

    def test_each_record_has_unique_record_id(self, cb):
        for _ in range(10):
            cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        ids = [r.record_id for r in cb.get_records()]
        assert len(set(ids)) == 10

    def test_session_id_constant(self, cb):
        for _ in range(3):
            cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        for rec in cb.get_records():
            assert rec.session_id == "sess-test"

    def test_payload_hash_is_sha256_of_payload(self, cb):
        from tradingagents.audit.schemas import hash_payload
        cb.on_tool_start({"name": "x"}, "input", run_id=uuid.uuid4())
        rec = cb.get_records()[0]
        assert rec.payload_hash == hash_payload(rec.payload)

    def test_prev_hash_chained_under_t1_3(self, cb):
        """T1.3 onward: prev_hash is real. First record uses GENESIS_HASH,
        subsequent records carry the prior record's on-disk line hash."""
        from tradingagents.audit.ledger import GENESIS_HASH
        cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        records = cb.get_records()
        assert records[0].prev_hash == GENESIS_HASH
        # Second record's prev_hash is the hash of record 0's line — not
        # empty, not genesis.
        assert records[1].prev_hash != ""
        assert records[1].prev_hash != GENESIS_HASH

    def test_no_jsonl_path_keeps_in_memory_only(self, tmp_path):
        cb = TraceCallback(jsonl_path=None, session_id="s1")
        cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())
        recs = cb.get_records()
        assert len(recs) == 1
        # Nothing landed on disk
        assert not list(tmp_path.glob("*.jsonl"))

    def test_parent_dir_auto_created(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "session.jsonl"
        assert not deep.parent.exists()
        TraceCallback(jsonl_path=deep)
        assert deep.parent.exists()


# -------------------------------------------------------------------- #
# Chain (node) events
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestChainEvents:
    def test_chain_start_emits_node_enter(self, cb):
        cb.on_chain_start(
            {"name": "Bull Researcher"},
            {"market_report": "..."},
            run_id=uuid.uuid4(),
        )
        rec = cb.get_records()[0]
        assert rec.type == NODE_ENTER

    def test_chain_end_emits_node_exit(self, cb):
        cb.on_chain_end({"bull_history": "..."}, run_id=uuid.uuid4())
        rec = cb.get_records()[0]
        assert rec.type == NODE_EXIT

    def test_chain_payload_records_keys_not_values(self, cb):
        """Recording full state inputs would multiply storage by ~Nx where
        N is the graph depth — not worth it given each node's outputs
        are captured by the downstream LLM records anyway. We record
        the KEYS so the trace shows what flowed where, without bloating."""
        cb.on_chain_start(
            {},
            {"market_report": "long string", "sentiment_report": "another"},
            run_id=uuid.uuid4(),
        )
        rec = cb.get_records()[0]
        assert "long string" not in str(rec.payload)
        assert set(rec.payload["inputs_keys"]) == {"market_report", "sentiment_report"}


# -------------------------------------------------------------------- #
# Integration with TradingAgentsGraph wiring
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestTradingAgentsGraphWiring:
    """Verify that TradingAgentsGraph wires up a TraceCallback by default."""

    def test_default_config_registers_trace_callback(self, tmp_path, monkeypatch):
        """No real LLM calls; just verify the wiring."""
        from tradingagents.graph import trading_graph as tg
        from unittest.mock import MagicMock

        # Short-circuit the LLM construction so we don't need real keys
        monkeypatch.setattr(
            tg, "create_llm_client",
            lambda **kw: MagicMock(get_llm=lambda: MagicMock()),
        )
        monkeypatch.setattr(
            tg.GraphSetup, "setup_graph",
            lambda self, selected_analysts: MagicMock(),
        )

        cfg = dict(tg.DEFAULT_CONFIG)
        cfg["audit_dir"] = str(tmp_path)

        ta = tg.TradingAgentsGraph(config=cfg)
        assert ta.trace_callback is not None
        assert isinstance(ta.trace_callback, TraceCallback)
        # The trace callback is the FIRST callback so it observes events
        # before any user-provided side effects can mutate state.
        assert ta.callbacks[0] is ta.trace_callback
        # Path is under the configured audit_dir
        assert str(ta.trace_callback.jsonl_path).startswith(str(tmp_path))

    def test_disabled_flag_skips_trace_callback(self, tmp_path, monkeypatch):
        from tradingagents.graph import trading_graph as tg
        from unittest.mock import MagicMock

        monkeypatch.setattr(
            tg, "create_llm_client",
            lambda **kw: MagicMock(get_llm=lambda: MagicMock()),
        )
        monkeypatch.setattr(
            tg.GraphSetup, "setup_graph",
            lambda self, selected_analysts: MagicMock(),
        )

        cfg = dict(tg.DEFAULT_CONFIG)
        cfg["audit_full_trace_enabled"] = False

        ta = tg.TradingAgentsGraph(config=cfg)
        assert ta.trace_callback is None

    def test_user_callbacks_appended_after_trace(self, tmp_path, monkeypatch):
        """Caller-provided callbacks come AFTER the trace callback in the
        list — audit observes first, user callbacks can mutate state."""
        from tradingagents.graph import trading_graph as tg
        from unittest.mock import MagicMock
        from langchain_core.callbacks import BaseCallbackHandler

        monkeypatch.setattr(
            tg, "create_llm_client",
            lambda **kw: MagicMock(get_llm=lambda: MagicMock()),
        )
        monkeypatch.setattr(
            tg.GraphSetup, "setup_graph",
            lambda self, selected_analysts: MagicMock(),
        )

        user_cb = BaseCallbackHandler()
        cfg = dict(tg.DEFAULT_CONFIG)
        cfg["audit_dir"] = str(tmp_path)

        ta = tg.TradingAgentsGraph(config=cfg, callbacks=[user_cb])
        assert ta.callbacks[0] is ta.trace_callback
        assert ta.callbacks[1] is user_cb
