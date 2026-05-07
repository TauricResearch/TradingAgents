"""Tests for tradingagents.graph.checkpointer module."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.graph.checkpointer import (
    _db_path,
    clear_all_checkpoints,
    thread_id,
)

# ---------------------------------------------------------------------------
# Property 8: Deterministic Thread ID
# ---------------------------------------------------------------------------


@given(
    ticker=st.text(
        min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))
    ),
    trade_date=st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True),
)
@settings(max_examples=200)
def test_thread_id_deterministic(ticker: str, trade_date: str) -> None:
    """Same inputs always produce the same thread_id."""
    assert thread_id(ticker, trade_date) == thread_id(ticker, trade_date)


@given(
    ticker1=st.text(
        min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))
    ),
    ticker2=st.text(
        min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))
    ),
    date1=st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True),
    date2=st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True),
)
@settings(max_examples=200)
def test_thread_id_different_inputs(ticker1: str, ticker2: str, date1: str, date2: str) -> None:
    """Different (normalized) inputs produce different thread_ids."""
    # Only assert difference when the normalized inputs actually differ
    if ticker1.upper() != ticker2.upper() or date1 != date2:
        assert thread_id(ticker1, date1) != thread_id(ticker2, date2)


def test_thread_id_case_insensitive() -> None:
    """Thread ID is case-insensitive on ticker."""
    assert thread_id("AAPL", "2024-01-15") == thread_id("aapl", "2024-01-15")


def test_thread_id_length() -> None:
    """Thread ID is always 16 hex characters."""
    tid = thread_id("TSLA", "2024-06-01")
    assert len(tid) == 16
    assert all(c in "0123456789abcdef" for c in tid)


# ---------------------------------------------------------------------------
# Unit: _db_path creates correct path
# ---------------------------------------------------------------------------


def test_db_path_creates_correct_path() -> None:
    """_db_path returns expected path structure and creates parent dirs."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _db_path(tmp, "aapl")
        assert path == Path(tmp) / "checkpoints" / "AAPL.db"
        assert path.parent.exists()


def test_db_path_case_normalization() -> None:
    """_db_path normalizes ticker to uppercase."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _db_path(tmp, "msft")
        assert path.name == "MSFT.db"


# ---------------------------------------------------------------------------
# Unit: clear_all_checkpoints removes files
# ---------------------------------------------------------------------------


def test_clear_all_checkpoints_removes_files() -> None:
    """clear_all_checkpoints removes all .db files and returns count."""
    with tempfile.TemporaryDirectory() as tmp:
        cp_dir = Path(tmp) / "checkpoints"
        cp_dir.mkdir(parents=True)
        # Create some fake db files
        (cp_dir / "AAPL.db").touch()
        (cp_dir / "TSLA.db").touch()
        (cp_dir / "MSFT.db").touch()

        count = clear_all_checkpoints(tmp)
        assert count == 3
        assert list(cp_dir.glob("*.db")) == []


def test_clear_all_checkpoints_empty_dir() -> None:
    """clear_all_checkpoints returns 0 when no checkpoints exist."""
    with tempfile.TemporaryDirectory() as tmp:
        count = clear_all_checkpoints(tmp)
        assert count == 0


# ---------------------------------------------------------------------------
# Unit: setup_graph returns StateGraph (not CompiledStateGraph)
# ---------------------------------------------------------------------------


def test_setup_graph_returns_state_graph() -> None:
    """setup_graph() returns an uncompiled StateGraph instance."""
    from unittest.mock import MagicMock

    from langgraph.graph import StateGraph

    from tradingagents.graph.setup import GraphSetup

    # Create a GraphSetup with mocked LLMs — we only need to verify the return type
    mock_llm = MagicMock()
    mock_memory = MagicMock()
    mock_conditional = MagicMock()
    mock_conditional.should_continue_debate = MagicMock(return_value="Research Manager")
    mock_conditional.should_continue_risk = MagicMock(return_value="Portfolio Manager")
    mock_news_store = MagicMock()

    gs = GraphSetup(
        quick_thinking_llm=mock_llm,
        mid_thinking_llm=mock_llm,
        deep_thinking_llm=mock_llm,
        bull_memory=mock_memory,
        bear_memory=mock_memory,
        trader_memory=mock_memory,
        invest_judge_memory=mock_memory,
        portfolio_manager_memory=mock_memory,
        conditional_logic=mock_conditional,
        news_evidence_store=mock_news_store,
    )

    result = gs.setup_graph(["market", "news", "fundamentals"])
    assert isinstance(result, StateGraph)
    # Verify it's NOT already compiled
    assert not hasattr(result, "invoke"), "setup_graph should return uncompiled StateGraph"
