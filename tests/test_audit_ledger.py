"""Tests for ``tradingagents.audit.ledger`` (T1.3).

The ledger has three jobs:
1. Append records with a SHA-256 chain linking each to the previous.
2. Resume the chain when an existing file is reopened (so a CLI run #2
   continues from run #1's last hash, not from genesis).
3. Detect any post-hoc mutation (edit / delete / reorder / insert).

Plus the TraceCallback integration: traces produced under T1.3 must
verify clean, and a tampered trace must verify dirty.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradingagents.audit.ledger import (
    GENESIS_HASH,
    HashChainLedger,
    VerifyResult,
    _hash_line,
    verify_ledger,
)
from tradingagents.audit.schemas import (
    LLM_END,
    LLM_START,
    TraceRecord,
    canonical_json,
    hash_payload,
)
from tradingagents.audit.trace_callback import TraceCallback


# -------------------------------------------------------------------- #
# Helpers
# -------------------------------------------------------------------- #


def _make_record(seq: int, prev_hash: str = "") -> TraceRecord:
    """Build a minimal valid TraceRecord with deterministic content."""
    payload = {"seq": seq, "data": f"record-{seq}"}
    # Wrap seq into a valid minute slot so tests can use seq=99 etc.
    return TraceRecord(
        record_id=f"rec-{seq:04d}",
        session_id="sess-test",
        ts=datetime(2026, 1, 15, 14, seq % 60, 0, tzinfo=timezone.utc),
        type=LLM_START,
        payload=payload,
        payload_hash=hash_payload(payload),
        prev_hash=prev_hash,
    )


# -------------------------------------------------------------------- #
# Append + chain linkage
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestAppendBasics:
    def test_first_record_uses_genesis_prev_hash(self, tmp_path):
        ledger = HashChainLedger(tmp_path / "trace.jsonl")
        rec = _make_record(1)
        ledger.append(rec)
        assert rec.prev_hash == GENESIS_HASH

    def test_subsequent_record_links_to_previous(self, tmp_path):
        ledger = HashChainLedger(tmp_path / "trace.jsonl")
        r1 = _make_record(1)
        r2 = _make_record(2)
        hash1 = ledger.append(r1)
        ledger.append(r2)
        assert r2.prev_hash == hash1

    def test_returned_hash_matches_disk_line(self, tmp_path):
        ledger = HashChainLedger(tmp_path / "trace.jsonl")
        rec = _make_record(1)
        returned_hash = ledger.append(rec)
        # The disk line, stripped, should hash to the returned value
        disk_line = (tmp_path / "trace.jsonl").read_text().splitlines()[0]
        assert returned_hash == _hash_line(disk_line)

    def test_append_only_open_mode(self, tmp_path, monkeypatch):
        """The ledger must NEVER open the file in write/truncate mode.

        We can't fully assert this without ptrace; the next best is to
        intercept ``open`` and check the mode the ledger requests.
        """
        ledger = HashChainLedger(tmp_path / "trace.jsonl")
        opens = []
        import builtins
        orig_open = builtins.open

        def _spy_open(path, mode="r", *a, **kw):
            opens.append((str(path), mode))
            return orig_open(path, mode, *a, **kw)

        monkeypatch.setattr(builtins, "open", _spy_open)
        ledger.append(_make_record(1))
        ledger.append(_make_record(2))
        # Every write opened with 'a', never 'w' or 'r+'
        write_modes = [m for p, m in opens if str(tmp_path) in p]
        assert all("w" not in mode and "+" not in mode for mode in write_modes), \
            f"non-append open detected: {write_modes}"

    def test_record_in_memory_reflects_prev_hash(self, tmp_path):
        """ledger.append mutates the record in place — the in-memory
        copy that downstream code holds must show the same prev_hash
        that landed on disk."""
        ledger = HashChainLedger(tmp_path / "trace.jsonl")
        r1 = _make_record(1)
        r2 = _make_record(2)
        ledger.append(r1)
        ledger.append(r2)
        assert r1.prev_hash == GENESIS_HASH
        # r2's prev_hash mutated to match the on-disk r1 line hash
        assert r2.prev_hash != GENESIS_HASH
        assert r2.prev_hash != ""


# -------------------------------------------------------------------- #
# Resume across ledger instances
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestResume:
    def test_second_ledger_continues_chain(self, tmp_path):
        """A fresh HashChainLedger over an existing file picks up the
        chain. Simulates a CLI session #2 appending to a file from #1."""
        path = tmp_path / "trace.jsonl"
        l1 = HashChainLedger(path)
        l1.append(_make_record(1))
        hash1 = l1.append(_make_record(2))

        # Drop l1, open a fresh ledger over the same file
        l2 = HashChainLedger(path)
        r3 = _make_record(3)
        l2.append(r3)

        # r3.prev_hash equals the hash l1 returned for record 2
        assert r3.prev_hash == hash1
        # And the verify of the resulting file is clean
        result = verify_ledger(path)
        assert result.ok
        assert result.format == "chained"

    def test_empty_file_resumes_to_genesis(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        path.write_text("")
        ledger = HashChainLedger(path)
        rec = _make_record(1)
        ledger.append(rec)
        assert rec.prev_hash == GENESIS_HASH

    def test_missing_file_resumes_to_genesis(self, tmp_path):
        path = tmp_path / "deep" / "trace.jsonl"  # doesn't exist
        ledger = HashChainLedger(path)
        rec = _make_record(1)
        ledger.append(rec)
        assert rec.prev_hash == GENESIS_HASH


# -------------------------------------------------------------------- #
# Verify — detect tampering
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestVerify:
    def test_empty_file_is_ok(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        result = verify_ledger(path)
        assert result.ok
        assert result.format == "empty"
        assert result.total_records == 0

    def test_intact_chain_verifies_clean(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)
        for i in range(10):
            ledger.append(_make_record(i))
        result = verify_ledger(path)
        assert result.ok is True
        assert result.format == "chained"
        assert result.total_records == 10
        assert result.broken_lines == []

    def test_edited_record_breaks_chain_from_next_line(self, tmp_path):
        """Editing the payload of record N should be detected at N+1
        (because N's hash changes, but N+1's prev_hash is unchanged)."""
        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)
        for i in range(5):
            ledger.append(_make_record(i))

        # Maliciously edit record at line 3 (1-indexed)
        lines = path.read_text().splitlines()
        rec = json.loads(lines[2])
        rec["payload"]["data"] = "TAMPERED"
        # Keep the line canonically formatted so a casual ls -la
        # doesn't show length change
        from tradingagents.audit.schemas import canonical_json as cj
        lines[2] = cj(rec)
        path.write_text("\n".join(lines) + "\n")

        result = verify_ledger(path)
        assert result.ok is False
        assert result.format == "corrupt"
        # Line 3 itself verifies against the original prev_hash (we
        # didn't touch its prev_hash field), but every line FROM 4
        # ONWARD is broken because line 3's hash changed.
        assert 3 not in result.broken_lines  # its own prev_hash still matches
        assert result.broken_lines == [4, 5]

    def test_deleted_record_breaks_next_line(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)
        for i in range(5):
            ledger.append(_make_record(i))

        # Delete line 3
        lines = path.read_text().splitlines()
        del lines[2]
        path.write_text("\n".join(lines) + "\n")

        result = verify_ledger(path)
        assert result.ok is False
        # Line 4 (which is now at line 3 after deletion) is the first
        # to disagree, since its prev_hash points to the old line 2's
        # successor (the deleted line 3), not to line 2 directly.
        assert result.broken_lines == [3, 4]

    def test_reordered_records_break(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)
        for i in range(5):
            ledger.append(_make_record(i))

        # Swap lines 3 and 4
        lines = path.read_text().splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        path.write_text("\n".join(lines) + "\n")

        result = verify_ledger(path)
        assert result.ok is False
        assert len(result.broken_lines) > 0

    def test_inserted_record_breaks(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)
        for i in range(3):
            ledger.append(_make_record(i))

        # Forge a record and stuff it at position 2 with a made-up prev_hash
        fake = _make_record(99, prev_hash="0" * 64)  # not the actual prev
        fake_line = fake.canonical()
        lines = path.read_text().splitlines()
        lines.insert(1, fake_line)
        path.write_text("\n".join(lines) + "\n")

        result = verify_ledger(path)
        assert result.ok is False
        # The forged line itself disagrees with the real prev_hash (line 1's)
        assert 2 in result.broken_lines

    def test_unparseable_json_flagged(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)
        ledger.append(_make_record(1))
        # Append garbage manually
        with open(path, "a") as f:
            f.write("{not json\n")
        ledger.append(_make_record(2))  # this will get a valid chain link

        result = verify_ledger(path)
        assert result.ok is False
        # Garbage at line 2 is flagged
        assert 2 in result.broken_lines


@pytest.mark.unit
class TestVerifyPreT13Format:
    """Files written by T1.2 (before this PR) have prev_hash="" on every
    line — they aren't chained. The verifier should not claim them
    "corrupt", it should report the pre-T1.3 format honestly."""

    def test_all_empty_prev_hash_reported_as_pre_t13(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        # Emulate the T1.2 era: records written with prev_hash=""
        recs = [_make_record(i, prev_hash="") for i in range(5)]
        with open(path, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(r.canonical() + "\n")

        result = verify_ledger(path)
        assert result.format == "unchained_pre_t1_3"
        assert result.ok is False  # not strictly broken, but not chained
        assert result.total_records == 5


# -------------------------------------------------------------------- #
# TraceCallback integration: produced traces are chained + verify clean
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestTraceCallbackProducesChainedLedger:
    def test_callback_produced_trace_verifies_clean(self, tmp_path):
        path = tmp_path / "traces" / "session.jsonl"
        cb = TraceCallback(jsonl_path=path, session_id="s1")

        # Fire a small sequence of events
        rid1 = uuid.uuid4()
        cb.on_chat_model_start({}, [[]], run_id=rid1)
        cb.on_llm_end(
            __import__("langchain_core.outputs", fromlist=["LLMResult"]).LLMResult(
                generations=[[]], llm_output={},
            ),
            run_id=rid1,
        )
        cb.on_tool_start({"name": "x"}, "input", run_id=uuid.uuid4())

        result = verify_ledger(path)
        assert result.ok is True
        assert result.format == "chained"
        assert result.total_records == 3

    def test_callback_records_match_disk_chain(self, tmp_path):
        """In-memory records must have the same prev_hash as their disk
        counterparts so callers reading ``cb.records`` see the chain."""
        path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=path, session_id="s1")
        for _ in range(5):
            cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())

        in_mem_prev = [r.prev_hash for r in cb.get_records()]
        disk_prev = [json.loads(l)["prev_hash"] for l in path.read_text().splitlines()]
        assert in_mem_prev == disk_prev
        # First is genesis
        assert in_mem_prev[0] == GENESIS_HASH
        # Rest are non-empty, non-genesis
        for h in in_mem_prev[1:]:
            assert h != ""
            assert h != GENESIS_HASH

    def test_tampered_callback_trace_detected(self, tmp_path):
        """A user who edits the trace file post-hoc should be caught."""
        path = tmp_path / "trace.jsonl"
        cb = TraceCallback(jsonl_path=path, session_id="s1")
        for _ in range(4):
            cb.on_chat_model_start({}, [[]], run_id=uuid.uuid4())

        # Edit a record on disk (the in-memory cb.records is unchanged,
        # which is itself notable — the on-disk file is the source of
        # truth for audit purposes)
        lines = path.read_text().splitlines()
        rec = json.loads(lines[1])
        rec["payload"]["messages"] = [{"role": "user", "content": "FORGED"}]
        lines[1] = canonical_json(rec)
        path.write_text("\n".join(lines) + "\n")

        result = verify_ledger(path)
        assert not result.ok
        assert 3 in result.broken_lines or 4 in result.broken_lines


# -------------------------------------------------------------------- #
# Thread safety smoke test
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestConcurrency:
    def test_concurrent_appends_produce_valid_chain(self, tmp_path):
        """Hammering the ledger from multiple threads must still produce
        a verifiable chain — the ledger's internal lock is what makes
        this safe even when callers don't synchronise externally."""
        import threading

        path = tmp_path / "trace.jsonl"
        ledger = HashChainLedger(path)

        def worker(start_seq):
            for i in range(20):
                ledger.append(_make_record(start_seq + i))

        threads = [threading.Thread(target=worker, args=(t * 100,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        result = verify_ledger(path)
        assert result.ok is True
        assert result.total_records == 80
