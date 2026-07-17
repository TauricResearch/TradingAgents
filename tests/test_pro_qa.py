"""Grounded evidence Q&A prompt assembly (A1)."""

from datetime import datetime, timezone

from tradingagents.contracts import (
    AgentEvidence,
    AgentTeam,
    DataRef,
    Direction,
    SourceAttribution,
    SourceType,
    Timeframe,
)
from tradingagents.pro.pipeline.qa import MAX_QUESTION_CHARS, build_qa_prompt


def _ev(agent_id: str, claim: str) -> AgentEvidence:
    return AgentEvidence(
        agent_id=agent_id,
        team=AgentTeam.TECHNICAL,
        claim=claim,
        direction=Direction.BEARISH,
        confidence=70,
        timeframe=Timeframe.H1,
        data_refs=[DataRef(name="X", value=1.0, source="indicator_engine")],
        sources=[SourceAttribution(id="indicator_engine",
                                   type=SourceType.INDICATOR, name="e")],
        timestamp=datetime.now(timezone.utc),
    )


def test_prompt_embeds_record_and_wraps_untrusted_question():
    prompt = build_qa_prompt(
        "Why short here?",
        symbol="XAUUSD",
        recommendation=None,
        supporting=[_ev("wyckoff", "distribution into 4080")],
        counterarguments=[_ev("macro_bull", "real yields easing")],
        debate_block="(debate)",
        invalidation="close above 4024",
    )
    assert "wyckoff" in prompt and "macro_bull" in prompt
    assert "close above 4024" in prompt
    assert "only from the record" in prompt.lower() or "ONLY the record" in prompt
    # the question is fenced as untrusted data, not spliced as an instruction
    assert "QUESTION" in prompt
    assert "Why short here?" in prompt


def test_long_question_is_truncated():
    prompt = build_qa_prompt(
        "x" * (MAX_QUESTION_CHARS + 200),
        symbol="XAUUSD",
        recommendation=None,
        supporting=[],
        counterarguments=[],
        debate_block="",
        invalidation=None,
    )
    assert "x" * MAX_QUESTION_CHARS in prompt
    assert "x" * (MAX_QUESTION_CHARS + 1) not in prompt


def test_empty_evidence_renders_placeholder():
    prompt = build_qa_prompt(
        "anything?", symbol="BTC-USD", recommendation=None,
        supporting=[], counterarguments=[], debate_block="", invalidation=None,
    )
    assert "(no evidence in this run)" in prompt
