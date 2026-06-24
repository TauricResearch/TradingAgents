"""Tests for agent memory."""
from __future__ import annotations

from web.server.ticker_agent.memory import append_memory, read_memory


def test_append_and_read_memory(tmp_path):
    f = tmp_path / "agent_memory.jsonl"
    append_memory({"cycle": 1, "conclusions": ["test"]}, file_path=str(f))
    append_memory({"cycle": 2, "conclusions": ["test2"]}, file_path=str(f))
    entries = read_memory(limit=10, file_path=str(f))
    assert len(entries) == 2
    assert entries[0]["cycle"] == 2  # most recent first


def test_read_memory_respects_limit(tmp_path):
    f = tmp_path / "agent_memory.jsonl"
    for i in range(5):
        append_memory({"cycle": i + 1}, file_path=str(f))
    entries = read_memory(limit=3, file_path=str(f))
    assert len(entries) == 3
    assert entries[0]["cycle"] == 5  # most recent first


def test_read_memory_empty(tmp_path):
    assert read_memory(limit=10, file_path=str(tmp_path / "empty.jsonl")) == []
