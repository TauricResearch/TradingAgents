"""R1 bounded-context compaction (RE.md 需求 1).

Covers the three ``history_compress`` modes — ``truncate`` (default),
``summarize`` and ``none`` (legacy) — plus the token estimator, the
per-side recent-turn retention, the hard character cap, the master
``debate_history_compact`` switch, and the state-structure guarantee that
compaction never mutates the stored debate history.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.graph.context_budget import (
    BEAR_PREFIX,
    BULL_PREFIX,
    build_bounded_history,
    compact_from_config,
    estimate_tokens,
)


def _history(rounds: int, *, pad: int = 200) -> str:
    """A realistic growing debate history: ``rounds`` bull+bear exchanges."""
    filler = "x" * pad
    parts = []
    for r in range(rounds):
        parts.append(f"{BULL_PREFIX} bull claim {r} {filler}")
        parts.append(f"{BEAR_PREFIX} bear claim {r} {filler}")
    return "\n".join(parts)


# --- estimator / metrics ----------------------------------------------------

@pytest.mark.unit
def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2   # ceil(5/4)
    assert estimate_tokens("x" * 4000) == 1000


@pytest.mark.unit
def test_metrics_populated_for_all_modes():
    history = _history(3)
    for mode in ("none", "truncate", "summarize"):
        out = build_bounded_history(history, mode=mode, max_chars=5000, max_turns=2)
        assert out.mode == mode
        assert out.original_chars == len(history)
        assert out.compacted_chars == len(out.text)
        assert out.token_estimate == estimate_tokens(out.text)


# --- mode: none (legacy, backwards-compatible) ------------------------------

@pytest.mark.unit
def test_none_returns_history_unchanged():
    history = _history(4)
    out = build_bounded_history(history, mode="none", max_chars=10)
    assert out.text == history
    assert out.saved_chars == 0
    assert out.saved_ratio == 0.0


@pytest.mark.unit
def test_master_switch_off_keeps_full_history():
    history = _history(4)
    cfg = {"debate_history_compact": False}
    out = compact_from_config(history, cfg)
    assert out.text == history
    assert out.mode == "none"


# --- mode: truncate (default) -----------------------------------------------

@pytest.mark.unit
def test_truncate_respects_max_chars():
    history = _history(10)
    out = build_bounded_history(history, mode="truncate", max_chars=800, max_turns=3)
    assert len(out.text) <= 800
    assert out.compacted_chars <= 800
    assert out.saved_chars > 0


@pytest.mark.unit
def test_truncate_keeps_opening_and_recent_turns_per_side():
    history = _history(5)
    out = build_bounded_history(
        history, mode="truncate", max_chars=100_000, max_turns=1
    )
    # Opening stance of each side is retained ...
    assert "bull claim 0" in out.text
    assert "bear claim 0" in out.text
    # ... alongside each side's most recent turn.
    assert "bull claim 4" in out.text
    assert "bear claim 4" in out.text
    # And a middle turn is dropped.
    assert "bull claim 2" not in out.text


@pytest.mark.unit
def test_truncate_zero_turns_keeps_only_openings():
    history = _history(4)
    out = build_bounded_history(
        history, mode="truncate", max_chars=100_000, max_turns=0
    )
    assert "bull claim 0" in out.text
    assert "bear claim 0" in out.text
    assert "bull claim 3" not in out.text


@pytest.mark.unit
def test_truncate_does_not_break_under_short_history():
    history = f"{BULL_PREFIX} only opening"
    out = build_bounded_history(history, mode="truncate", max_chars=6000, max_turns=4)
    assert "only opening" in out.text


@pytest.mark.unit
def test_empty_history_is_handled():
    out = build_bounded_history("", mode="truncate", max_chars=100)
    assert out.text == ""
    assert out.token_estimate == 0
    assert out.saved_ratio == 0.0


# --- mode: summarize --------------------------------------------------------

@pytest.mark.unit
def test_summarize_elides_middle_with_marker_and_caps():
    history = _history(10)
    out = build_bounded_history(history, mode="summarize", max_chars=700, max_turns=10)
    assert len(out.text) <= 700
    if out.original_chars > 700:
        assert "[... earlier debate elided ...]" in out.text


@pytest.mark.unit
def test_metrics_dict_is_serialisable_and_has_token_estimate():
    out = build_bounded_history(_history(4), mode="truncate", max_chars=600, max_turns=2)
    metrics = out.metrics()
    assert metrics["mode"] == "truncate"
    assert metrics["token_estimate"] == out.token_estimate
    assert metrics["compacted_chars"] <= 600
    assert 0.0 <= metrics["saved_ratio"] <= 1.0
    import json

    json.dumps(metrics)  # must not raise


@pytest.mark.unit
def test_researcher_returns_context_stats():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="arg")
    state = {
        "company_of_interest": "AAPL", "asset_type": "stock",
        "market_report": "m", "sentiment_report": "s",
        "news_report": "n", "fundamentals_report": "f",
        "investment_debate_state": {
            "history": _history(5), "bull_history": "", "bear_history": "",
            "current_response": "", "count": 0,
        },
    }
    result = create_bull_researcher(llm)(state)
    stats = result["debate_context_stats"]
    assert "token_estimate" in stats
    assert stats["mode"] in ("truncate", "summarize", "none")


@pytest.mark.unit
def test_report_header_shows_context_stats():
    from tradingagents.reporting import write_report_tree

    final_state = {
        "trade_date": "2024-05-10",
        "debate_context_stats": {
            "mode": "truncate", "token_estimate": 120, "saved_chars": 900,
            "saved_ratio": 0.6, "original_chars": 1500,
        },
    }
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = write_report_tree(final_state, "AAPL", tmp, settings=None, html=False)
        text = path.read_text(encoding="utf-8")
    assert "Debate context (truncate)" in text
    assert "~120 tokens" in text


# --- invalid / edge ---------------------------------------------------------

@pytest.mark.unit
def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        build_bounded_history(_history(1), mode="bogus")


@pytest.mark.unit
def test_config_drives_truncation():
    history = _history(8)
    cfg = {
        "debate_history_compact": True,
        "history_compress": "truncate",
        "history_max_chars": 600,
        "history_max_turns": 2,
    }
    out = compact_from_config(history, cfg)
    assert out.mode == "truncate"
    assert len(out.text) <= 600


# --- never mutates stored history (state-structure guarantee) ---------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "factory,module",
    [
        (create_bull_researcher, "tradingagents.agents.researchers.bull_researcher"),
        (create_bear_researcher, "tradingagents.agents.researchers.bear_researcher"),
    ],
)
def test_researcher_injects_compact_but_stores_full_history(monkeypatch, factory, module):
    import importlib

    mod = importlib.import_module(module)
    monkeypatch.setattr(
        mod,
        "get_config",
        lambda: {"debate_history_compact": True, "history_compress": "truncate",
                 "history_max_chars": 100_000, "history_max_turns": 1},
    )
    full_history = _history(6)
    captured = {}

    def _invoke(prompt):
        captured["prompt"] = prompt
        return MagicMock(content="a new argument")

    llm = MagicMock()
    llm.invoke.side_effect = _invoke
    state = {
        "company_of_interest": "AAPL", "asset_type": "stock",
        "market_report": "m", "sentiment_report": "s",
        "news_report": "n", "fundamentals_report": "f",
        "investment_debate_state": {
            "history": full_history, "bull_history": "", "bear_history": "",
            "current_response": "", "count": 0,
        },
    }
    result = factory(llm)(state)
    stored = result["investment_debate_state"]["history"]
    # The stored history keeps the full text plus the new argument.
    assert full_history in stored
    assert "a new argument" in stored
    # The prompt carries a bounded view: recent turns present, a dropped middle
    # turn absent (proving the injected section was compacted, not full).
    assert "bull claim 5" in captured["prompt"] or "bear claim 5" in captured["prompt"]
    assert "bull claim 2" not in captured["prompt"]
    assert "bear claim 2" not in captured["prompt"]
