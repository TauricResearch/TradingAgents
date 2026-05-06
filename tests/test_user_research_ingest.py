from pathlib import Path
from unittest.mock import MagicMock


def _fake_llm():
    """Minimal langchain-style LLM with .invoke() returning a fixed string."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="**Bottom line**\n- it goes up")
    return llm


def test_ingest_research_happy_path(tmp_path: Path):
    from tradingagents.dataflows.user_research import ingest_research
    out = ingest_research(
        file_bytes=b"# AAPL beats earnings\n\nGreat quarter.",
        filename="aapl_q4.md",
        ticker="AAPL",
        user_root=tmp_path / "user42",
        summarize_fn=_fake_llm(),
        run_id=None,
    )
    assert out["filename"] == "aapl_q4.md"
    assert "Bottom line" in out["summary"]
    assert Path(out["path"]).exists()


def test_ingest_research_truncates_large_input_before_llm(tmp_path: Path):
    from tradingagents.dataflows.user_research import (
        ingest_research,
        MAX_SUMMARY_INPUT_CHARS,
    )
    big_text = "x" * (MAX_SUMMARY_INPUT_CHARS * 2)
    llm = _fake_llm()
    ingest_research(
        file_bytes=big_text.encode(),
        filename="huge.md",
        ticker="AAPL",
        user_root=tmp_path / "u",
        summarize_fn=llm,
        run_id=None,
    )
    # llm.invoke called with a prompt — verify it carries truncated content
    invoked_prompt = llm.invoke.call_args.args[0]
    assert len(invoked_prompt) < MAX_SUMMARY_INPUT_CHARS + 5_000


def test_ingest_research_falls_back_when_summary_fails(tmp_path: Path):
    from tradingagents.dataflows.user_research import ingest_research
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("LLM down")
    out = ingest_research(
        file_bytes=b"# important note about TSLA",
        filename="tsla.md",
        ticker="TSLA",
        user_root=tmp_path / "u",
        summarize_fn=llm,
        run_id=None,
    )
    assert "summary failed" in out["summary"].lower()
    assert "important note about TSLA" in out["summary"]
