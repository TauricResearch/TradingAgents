from tradingagents.graph.context_compaction import compact_debate_history


def _history() -> str:
    return "\n".join(
        [
            "Bull Analyst: Revenue grew 20% and backlog remains strong. " + "x" * 140,
            "Bear Analyst: Operating cash flow declined and valuation is elevated. " + "y" * 140,
            "Bull Analyst: New order data supports the growth thesis. " + "z" * 140,
            "Bear Analyst: Margin pressure could invalidate the thesis. " + "a" * 140,
            "Bull Analyst: Recent catalyst is a verified contract award. " + "b" * 140,
        ]
    )


def test_compaction_preserves_last_three_turns_and_public_fact_extracts():
    result = compact_debate_history(_history(), max_characters=900, recent_turns=3)

    assert result.compacted is True
    assert result.preserved_turns == 3
    assert "Recent catalyst is a verified contract award" in result.history
    assert "Operating cash flow declined" in result.history
    assert result.flushed_facts
    assert result.method == "deterministic_extract"


def test_compaction_accepts_an_explicit_public_summary_callback():
    result = compact_debate_history(
        _history(),
        max_characters=900,
        summarize=lambda _old: "- Verified prior claim: cash flow risk remains unresolved.",
    )

    assert result.method == "llm_public_summary"
    assert "cash flow risk remains unresolved" in result.history


def test_short_history_is_not_changed():
    result = compact_debate_history("Bull Analyst: concise evidence.", max_characters=512)

    assert result.compacted is False
    assert result.history == "Bull Analyst: concise evidence."
