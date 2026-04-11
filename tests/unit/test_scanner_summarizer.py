from types import SimpleNamespace
from unittest.mock import MagicMock

from tradingagents.agents.scanners.scanner_summarizer import (
    _build_scanner_summary_prompt,
    create_scanner_summarizer,
)


def test_build_scanner_summary_prompt_emphasizes_machine_reuse():
    prompt = _build_scanner_summary_prompt(
        "smart_money_report",
        "RIG unusual options flow on 2026-04-02 at $45.20.",
    )

    assert "Scanner source: smart money" in prompt
    assert "Write for downstream machine reuse" in prompt
    assert "Prefer `TICKER | sector | signal | exact evidence | implication` rows." in prompt
    assert "Preserve dates exactly as written." in prompt


def test_scanner_summarizer_returns_no_data_placeholder():
    llm = MagicMock()
    node = create_scanner_summarizer(llm, "smart_money_report", "smart_money_summary")

    result = node({"smart_money_report": ""})

    assert result == {
        "smart_money_summary": (
            "[NO_EVIDENCE] Source: smart money. "
            "Upstream scanner produced no usable data. Exclude from synthesis."
        ),
        "sender": "summarizer_smart_money_report",
    }
    llm.invoke.assert_not_called()


def test_scanner_summarizer_invokes_llm_with_tightened_prompt():
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="- RIG | Energy | insider buying")
    node = create_scanner_summarizer(llm, "smart_money_report", "smart_money_summary")

    result = node({"smart_money_report": "RIG insider buying at $45.20 on 2026-04-02"})

    assert result["smart_money_summary"] == "- RIG | Energy | insider buying"
    assert result["sender"] == "summarizer_smart_money_report"
    prompt = llm.invoke.call_args.args[0]
    assert "Scanner source: smart money" in prompt
    assert "Preserve dates exactly as written." in prompt
