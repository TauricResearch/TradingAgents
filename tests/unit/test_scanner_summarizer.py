from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.scanners.scanner_summarizer import (
    _build_scanner_summary_prompt,
    create_scanner_summarizer,
)
from tradingagents.agents.utils.scanner_idempotency import save_node_report
from tradingagents.observability import RunLogger, set_run_logger


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


def test_scanner_summarizer_loads_raw_report_from_disk_when_state_missing(tmp_path, monkeypatch):
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="- NVDA | Technology | gatekeeper")
    run_dir = tmp_path / "daily" / "2026-04-24" / "RUN1" / "market"
    run_dir.mkdir(parents=True)
    (run_dir / "gatekeeper_universe_report.md").write_text(
        "[QUALITY: ok | evidence=8 | tools=get_gatekeeper_universe]\nNVDA AAPL MSFT",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tradingagents.agents.utils.scanner_idempotency.get_market_dir",
        lambda scan_date, run_id: tmp_path / "daily" / scan_date / run_id / "market",
    )
    node = create_scanner_summarizer(llm, "gatekeeper_universe_report", "gatekeeper_summary")

    result = node({"scan_date": "2026-04-24", "run_id": "RUN1"})

    assert result["gatekeeper_summary"] == "- NVDA | Technology | gatekeeper"
    assert llm.invoke.call_count == 1


def test_scanner_summarizer_uses_active_run_logger_when_run_id_missing(tmp_path, monkeypatch):
    llm = MagicMock()
    llm.invoke.return_value = SimpleNamespace(content="- NVDA | Technology | gatekeeper")
    run_dir = tmp_path / "daily" / "2026-04-24" / "RUN_FROM_LOGGER" / "market"
    run_dir.mkdir(parents=True)
    (run_dir / "gatekeeper_universe_report.md").write_text(
        "[QUALITY: ok | evidence=8 | tools=get_gatekeeper_universe]\nNVDA AAPL MSFT",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tradingagents.agents.utils.scanner_idempotency.get_market_dir",
        lambda scan_date, run_id: tmp_path / "daily" / scan_date / run_id / "market",
    )
    node = create_scanner_summarizer(llm, "gatekeeper_universe_report", "gatekeeper_summary")
    set_run_logger(RunLogger(run_id="RUN_FROM_LOGGER"))
    try:
        result = node({"scan_date": "2026-04-24"})
    finally:
        set_run_logger(None)

    assert result["gatekeeper_summary"] == "- NVDA | Technology | gatekeeper"
    assert llm.invoke.call_count == 1


def test_scanner_report_save_uses_active_run_logger_when_run_id_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.utils.scanner_idempotency.get_market_dir",
        lambda scan_date, run_id: tmp_path / "daily" / scan_date / run_id / "market",
    )
    set_run_logger(RunLogger(run_id="RUN_FROM_LOGGER"))
    try:
        save_node_report(
            {"scan_date": "2026-04-24"},
            "gatekeeper_universe_report",
            "[QUALITY: ok | evidence=8 | tools=get_gatekeeper_universe]\nNVDA AAPL MSFT",
        )
    finally:
        set_run_logger(None)

    report_path = (
        tmp_path
        / "daily"
        / "2026-04-24"
        / "RUN_FROM_LOGGER"
        / "market"
        / "gatekeeper_universe_report.md"
    )
    assert report_path.exists()


def test_scanner_summarizer_timeout_raises_runtime_error(monkeypatch):
    llm = MagicMock()
    node = create_scanner_summarizer(llm, "smart_money_report", "smart_money_summary")

    def _timeout(**kwargs):
        return None, TimeoutError("timed out")

    monkeypatch.setattr(
        "tradingagents.agents.scanners.scanner_summarizer.invoke_with_timeout",
        _timeout,
    )

    with pytest.raises(RuntimeError) as exc:
        node({"smart_money_report": "RIG insider buying at $45.20 on 2026-04-02"})

    assert "Summarizer invoke failed" in str(exc.value)
