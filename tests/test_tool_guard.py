"""Tests for the cross-ticker tool guard."""

from typing import Annotated
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool

from tradingagents.agents.utils.tool_guard import guard_target_ticker
from tradingagents.dataflows.target_context import (
    clear_target_ticker,
    get_target_ticker,
    set_target_ticker,
)
from tradingagents.observability.context import ObservationContext


@pytest.fixture(autouse=True)
def _clean_target():
    clear_target_ticker()
    yield
    clear_target_ticker()


def _make_fetch(param_name: str = "ticker"):
    @guard_target_ticker(param_name)
    def fetch(ticker=None, symbol=None):
        return f"DATA for {ticker or symbol}"

    return fetch


def test_target_ticker_passes_through():
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    assert fetch("AAPL") == "DATA for AAPL"


def test_cross_ticker_injects_notice():
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    result = fetch("MSFT")
    assert "COMPARISON_TICKER_NOTICE" in result
    assert "MSFT" in result
    assert "AAPL" in result
    assert "DATA for MSFT" in result


def test_no_target_passthrough():
    """Without a contextvar set (bare states, tests) the guard is a no-op."""
    fetch = _make_fetch("ticker")
    assert fetch("MSFT") == "DATA for MSFT"


def test_a_share_suffix_normalization_matches():
    """600519.SH / .SS / bare 600519 all refer to the same instrument."""
    set_target_ticker("600519.SH")
    fetch = _make_fetch("ticker")
    assert fetch("600519.SS") == "DATA for 600519.SS"
    assert fetch("600519") == "DATA for 600519"
    assert fetch("600519.SH") == "DATA for 600519.SH"


def test_us_ticker_case_insensitive_match():
    set_target_ticker("aapl")
    fetch = _make_fetch("ticker")
    assert fetch("AAPL") == "DATA for AAPL"


def test_symbol_param_name():
    set_target_ticker("AAPL")

    @guard_target_ticker("symbol")
    def fetch(symbol=None):
        return f"DATA for {symbol}"

    result = fetch("MSFT")
    assert "COMPARISON_TICKER_NOTICE" in result
    assert "DATA for MSFT" in result


def test_keyword_arg_extracted():
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    result = fetch(ticker="MSFT")
    assert "COMPARISON_TICKER_NOTICE" in result


def _patch_observer(monkeypatch, *, has_context=True, run_id="run-1"):
    """Patch the guard to use a fake observer/context capturing emitted drafts."""
    emitted: list = []
    observer = MagicMock()
    observer.run_id = run_id
    observer.emit = lambda draft: emitted.append(draft)
    monkeypatch.setattr(
        "tradingagents.agents.utils.tool_guard.current_provenance_observer",
        lambda: observer,
    )
    context = (
        ObservationContext(
            run_id=run_id,
            actor_id="actor-1",
            node_id="node-1",
            role_instance_id="role-1",
            turn_id="turn-1",
            graph_task_id="task-1",
            graph_step=1,
            tool_call_id="call-1",
        )
        if has_context
        else None
    )
    monkeypatch.setattr(
        "tradingagents.agents.utils.tool_guard.current_observation_context",
        lambda: context,
    )
    return emitted


def test_cross_ticker_emits_formal_event(monkeypatch):
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    emitted = _patch_observer(monkeypatch)

    fetch("MSFT")

    assert len(emitted) == 1
    draft = emitted[0]
    assert draft.type == "tool.cross_ticker_query"
    assert draft.run_id == "run-1"
    assert draft.payload["requested_ticker"] == "MSFT"
    assert draft.payload["target_ticker"] == "AAPL"
    assert draft.payload["tool_name"] == "fetch"
    assert draft.payload["tool_call_id"] == "call-1"
    assert draft.payload["turn_id"] == "turn-1"
    assert draft.payload["graph_task_id"] == "task-1"


def test_cross_ticker_cli_fallback_no_observer(monkeypatch):
    """Without an observer (CLI), the guard still injects a notice and logs."""
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    monkeypatch.setattr(
        "tradingagents.agents.utils.tool_guard.current_provenance_observer",
        lambda: None,
    )
    monkeypatch.setattr(
        "tradingagents.agents.utils.tool_guard.current_observation_context",
        lambda: None,
    )

    result = fetch("MSFT")

    assert "COMPARISON_TICKER_NOTICE" in result


def test_cross_ticker_no_context_no_formal_event(monkeypatch):
    """Observer present but no observation context: no formal event, still notice."""
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    emitted = _patch_observer(monkeypatch, has_context=False)

    result = fetch("MSFT")

    assert emitted == []
    assert "COMPARISON_TICKER_NOTICE" in result


def test_no_audit_when_target_matches(monkeypatch):
    set_target_ticker("AAPL")
    fetch = _make_fetch("ticker")
    emitted = _patch_observer(monkeypatch)

    fetch("AAPL")

    assert emitted == []


def test_tool_signature_preserved():
    """LangChain @tool must still see annotated params through the guard."""

    @tool
    @guard_target_ticker("ticker")
    def my_tool(
        ticker: Annotated[str, "ticker"],
        date: Annotated[str, "date"],
    ) -> str:
        """Return ticker and date for signature-preservation test."""
        return f"{ticker} {date}"

    assert "ticker" in my_tool.args
    assert "date" in my_tool.args


def test_target_context_set_get_clear():
    set_target_ticker("AAPL", company_name="Apple Inc.")
    target = get_target_ticker()
    assert target is not None
    assert target.ticker == "AAPL"
    assert target.company_name == "Apple Inc."
    clear_target_ticker()
    assert get_target_ticker() is None
