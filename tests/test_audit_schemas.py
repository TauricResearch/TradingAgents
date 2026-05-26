"""Tests for ``tradingagents.audit.schemas`` (T1.1).

Validates the TraceRecord shape, canonical-JSON determinism (the
foundation T1.3's hash chain rests on), and the rules around which
fields are or aren't included in the hashed payload.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from tradingagents.audit.schemas import (
    LLM_END,
    LLM_START,
    NODE_ENTER,
    canonical_json,
    hash_payload,
    TraceRecord,
)


@pytest.mark.unit
class TestCanonicalJson:
    """``canonical_json`` must be deterministic — same input, same output bits.

    Without that, every downstream hash comparison breaks under trivial
    key reordering or whitespace differences.
    """

    def test_key_order_does_not_matter(self):
        a = canonical_json({"b": 1, "a": 2})
        b = canonical_json({"a": 2, "b": 1})
        assert a == b

    def test_no_extra_whitespace(self):
        s = canonical_json({"a": 1, "b": [1, 2, 3]})
        # No spaces after commas/colons; that's the contract for the hash
        assert " " not in s

    def test_nested_keys_sorted(self):
        s = canonical_json({"outer": {"z": 1, "a": 2}})
        # Verify order via parsing the underlying string positions
        assert s.index('"a"') < s.index('"z"')

    def test_datetime_falls_back_to_str(self):
        """Datetimes are not natively JSON-serializable; canonical_json
        must fall back to str() so hashing never crashes on real
        TraceRecord payloads that include timestamps."""
        ts = datetime(2026, 1, 15, 14, 23, 45, tzinfo=timezone.utc)
        s = canonical_json({"ts": ts})
        # Parseable and contains a string-encoded date
        data = json.loads(s)
        assert "2026" in data["ts"]

    def test_identical_inputs_produce_identical_bytes(self):
        """The hashing contract: byte-identical input → byte-identical output."""
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        for _ in range(5):
            assert canonical_json(payload) == canonical_json(payload)


@pytest.mark.unit
class TestHashPayload:
    def test_sha256_hex(self):
        h = hash_payload({"a": 1})
        # SHA-256 hex digest is 64 hex chars
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        p = {"messages": [{"role": "user", "content": "hi"}]}
        assert hash_payload(p) == hash_payload(p)

    def test_different_payloads_different_hashes(self):
        assert hash_payload({"a": 1}) != hash_payload({"a": 2})


def _make_record(**overrides):
    base = {
        "record_id": "rec-1",
        "session_id": "sess-1",
        "ts": datetime(2026, 1, 15, 14, 23, 45, tzinfo=timezone.utc),
        "type": LLM_START,
        "payload": {"foo": "bar"},
        "payload_hash": hash_payload({"foo": "bar"}),
    }
    base.update(overrides)
    return TraceRecord(**base)


@pytest.mark.unit
class TestTraceRecord:
    def test_minimal_construction(self):
        rec = _make_record()
        assert rec.type == LLM_START
        assert rec.payload_hash == hash_payload({"foo": "bar"})
        assert rec.prev_hash == ""  # Phase 1 default

    def test_parent_record_id_optional(self):
        rec = _make_record(parent_record_id="parent-123")
        assert rec.parent_record_id == "parent-123"

    def test_node_optional(self):
        rec_with = _make_record(node="Bull Researcher")
        rec_without = _make_record()
        assert rec_with.node == "Bull Researcher"
        assert rec_without.node is None

    def test_type_validates(self):
        """Pydantic Literal type rejects unknown event types."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _make_record(type="totally_made_up_event")

    def test_to_canonical_dict_excludes_prev_hash(self):
        """to_canonical_dict() is what's hashed FOR a record; including
        prev_hash there would create a chicken-and-egg: the hash would
        depend on the prev_hash which depends on the previous record's
        hash, but we'd be hashing the current record."""
        rec = _make_record(prev_hash="abcdef")
        d = rec.to_canonical_dict()
        assert "prev_hash" not in d
        # All other fields are present
        assert d["record_id"] == "rec-1"
        assert d["payload_hash"] == hash_payload({"foo": "bar"})

    def test_canonical_includes_prev_hash(self):
        """canonical() is what the NEXT record hashes — must include the
        full chain pointer."""
        rec = _make_record(prev_hash="abc")
        s = rec.canonical()
        data = json.loads(s)
        assert data["prev_hash"] == "abc"

    def test_canonical_deterministic_across_phases(self):
        """Two records with identical fields must canonicalize identically
        regardless of prev_hash value — prev_hash is just one more field,
        not a signal that changes the rest of the encoding. This
        guarantees that adding T1.3 won't invalidate T1.2 files."""
        rec_a = _make_record(prev_hash="")
        rec_b = _make_record(prev_hash="abcdef")
        # The two should differ only by prev_hash; everything else is bit
        # identical (compare to_canonical_dict).
        a = rec_a.to_canonical_dict()
        b = rec_b.to_canonical_dict()
        assert a == b
        assert canonical_json(a) == canonical_json(b)

    def test_ts_renders_as_iso_z(self):
        rec = _make_record()
        d = rec.to_canonical_dict()
        # UTC, "Z" suffix per RFC 3339
        assert d["ts"].endswith("Z") or d["ts"].endswith("+00:00")
