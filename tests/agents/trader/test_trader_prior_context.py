import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tradingagents.agents.trader.trader import create_trader


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_patches(tmp_path: Path, fake_invoke):
    """Common patches for trader tests: disable structured output and mock invoke."""
    return [
        patch("tradingagents.agents.trader.trader.invoke_with_timeout", side_effect=fake_invoke),
        patch(
            "tradingagents.agents.utils.historical_context.REPORTS_ROOT",
            str(tmp_path / "reports"),
        ),
        patch(
            "tradingagents.agents.trader.trader.build_trader_plan_structured",
            return_value={"status": "completed"},
        ),
        # Force legacy free-text path so these tests remain independent of
        # the structured output integration.
        patch.dict(
            "tradingagents.agents.trader.trader.DEFAULT_CONFIG",
            {"structured_output_enabled": False},
        ),
    ]


def test_trader_includes_prior_context_when_available(tmp_path: Path) -> None:
    base = tmp_path / "reports" / "daily"
    _write(
        base / "2026-04-28" / "RUN1" / "AAPL" / "report" / "00_complete_report.json",
        {"trader_investment_plan": "PRIOR PLAN: BUY $180 stop $170"},
    )

    fake_llm = MagicMock()
    response = MagicMock(content="• BUY at $182\n• Stop $172\n• Target $200")
    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return response, None

    patches = _base_patches(tmp_path, fake_invoke)
    with patches[0], patches[1], patches[2], patches[3]:
        node = create_trader(fake_llm, memory)
        state = {
            "company_of_interest": "AAPL",
            "investment_plan": "Manager says BUY",
            "investment_plan_structured": {"status": "completed"},
            "market_report": "tech setup positive",
            "sentiment_report": "neutral",
            "news_report": "earnings beat",
            "fundamentals_report": "PE 28",
            "trade_date": "2026-05-01",
            "scanner_graph_context_text": "",
        }
        node(state)

    system_msg = captured["messages"][0]["content"]
    assert "Prior Run Context" in system_msg
    assert "PRIOR PLAN" in system_msg
    assert "2026-04-28" in system_msg


def test_trader_system_msg_has_no_prior_context_when_absent(tmp_path: Path) -> None:
    fake_llm = MagicMock()
    response = MagicMock(content="• BUY at $182\n• Stop $172\n• Target $200")
    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return response, None

    patches = _base_patches(tmp_path, fake_invoke)
    with patches[0], patches[1], patches[2], patches[3]:
        node = create_trader(fake_llm, memory)
        state = {
            "company_of_interest": "AAPL",
            "investment_plan": "Manager says BUY",
            "investment_plan_structured": {"status": "completed"},
            "market_report": "tech setup positive",
            "sentiment_report": "neutral",
            "news_report": "earnings beat",
            "fundamentals_report": "PE 28",
            "trade_date": "2026-05-01",
            "scanner_graph_context_text": "",
        }
        node(state)

    system_msg = captured["messages"][0]["content"]
    assert "Prior Run Context" not in system_msg
    assert not system_msg.endswith("\n\n")


def test_trader_no_crash_when_trade_date_missing(tmp_path: Path) -> None:
    fake_llm = MagicMock()
    response = MagicMock(content="• BUY at $182\n• Stop $172\n• Target $200")
    memory = MagicMock()
    memory.get_memories.return_value = []
    captured: dict = {}

    def fake_invoke(llm, messages, **kwargs):
        captured["messages"] = messages
        return response, None

    patches = _base_patches(tmp_path, fake_invoke)
    with patches[0], patches[1], patches[2], patches[3]:
        node = create_trader(fake_llm, memory)
        state = {
            "company_of_interest": "AAPL",
            "investment_plan": "Manager says BUY",
            "investment_plan_structured": {"status": "completed"},
            "market_report": "tech setup positive",
            "sentiment_report": "neutral",
            "news_report": "earnings beat",
            "fundamentals_report": "PE 28",
            # trade_date intentionally absent
            "scanner_graph_context_text": "",
        }
        result = node(state)

    assert "trader_investment_plan" in result
    system_msg = captured["messages"][0]["content"]
    assert "Prior Run Context" not in system_msg
