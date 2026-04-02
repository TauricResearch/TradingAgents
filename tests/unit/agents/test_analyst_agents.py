from unittest.mock import MagicMock, patch
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.memory.news_evidence import NewsEvidenceRecord


class MockRunnable(Runnable):
    def __init__(self, invoke_responses):
        self.invoke_responses = invoke_responses
        self.call_count = 0

    def invoke(self, input, config=None, **kwargs):
        response = self.invoke_responses[self.call_count]
        self.call_count += 1
        return response


class MockLLM(Runnable):
    def __init__(self, invoke_responses):
        self.runnable = MockRunnable(invoke_responses)
        self.tools_bound = None

    def invoke(self, input, config=None, **kwargs):
        return self.runnable.invoke(input, config=config, **kwargs)

    def bind_tools(self, tools):
        self.tools_bound = tools
        return self.runnable


class FakeNewsEvidenceStore:
    def ingest_prefetched_sections(self, *, run_id, ticker, trade_date, prefetched):
        return [
            NewsEvidenceRecord(
                run_id=run_id,
                evidence_id=f"art_{ticker.lower()}_001",
                ticker=ticker,
                trade_date=trade_date,
                section_label="Company-Specific News (Last 7 Days)",
                ordinal=1,
                source="Sahm",
                published_at=trade_date,
                title=f"{ticker} sample article",
                url="https://example.com/article",
                summary="Sample summary",
                raw_json="{}",
            )
        ]

    def build_prompt_context(self, records):
        return (
            "## Evidence Records\n\n"
            "These are SQLite-backed evidence records persisted for this run.\n\n"
            f"- [Evidence ID: {records[0].evidence_id}] Source: {records[0].source}"
        )


@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="Analyze AAPL.")],
        "run_id": "run-001",
        "trade_date": "2024-05-15",
        "company_of_interest": "AAPL",
    }


@pytest.fixture
def mock_llm_with_tool_call():
    """LLM that makes one tool call then writes the final report (iterative loop)."""
    # 1. First call: The LLM decides to use a tool
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "mock_tool", "args": {"query": "test"}, "id": "call_123"}
        ]
    )
    # 2. Second call: The LLM receives the tool output and writes the report
    final_report_msg = AIMessage(
        content="This is the final report after running the tool."
    )
    return MockLLM([tool_call_msg, final_report_msg])


@pytest.fixture
def mock_llm_direct_report():
    """LLM that returns the final report directly (no tool calls — full pre-fetch path)."""
    final_report_msg = AIMessage(
        content="This is the final report after running the tool."
    )
    return MockLLM([final_report_msg])


@pytest.fixture
def valid_news_report():
    return AIMessage(
        content="""
        AAPL News Analysis - 2024-05-15
        - Reuters reported on 2024-05-15 that AAPL supplier demand improved by 8%.
        - AAPL shares closed at $189.00 on 2024-05-15, and AAPL services revenue expectations rose 4%.
        - Bloomberg reported AAPL iPhone demand stabilized on 2024-05-14, supporting AAPL gross margin forecasts.
        - AAPL remained the focus of analyst revisions, and AAPL now trades with 22% operating margin expectations.
        """
    )


def test_fundamentals_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    """Fundamentals analyst: pre-fetches 4 tools, runs iterative loop for raw statements."""
    node = create_fundamentals_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["fundamentals_report"]


def test_market_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    """Market analyst: pre-fetches macro + stock data, keeps indicator selection iterative."""
    node = create_market_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["market_report"]


def test_social_media_analyst_direct_invoke(mock_state, mock_llm_direct_report):
    """Social analyst: full pre-fetch, direct LLM invoke (no tool loop)."""
    node = create_social_media_analyst(mock_llm_direct_report)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["sentiment_report"]


def test_news_analyst_direct_invoke(mock_state, valid_news_report):
    """News analyst: full pre-fetch, direct LLM invoke (no tool loop)."""
    with patch(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        return_value={},
    ):
        node = create_news_analyst(
            MockLLM([valid_news_report]),
            evidence_store=FakeNewsEvidenceStore(),
        )
        result = node(mock_state)
    assert "AAPL News Analysis" in result["news_report"]


def test_market_analyst_macro_regime_from_prefetch(mock_state, mock_llm_with_tool_call):
    """Market analyst populates macro_regime_report from pre-fetched data when available."""
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        return_value={
            "Macro Regime Classification": "## Risk-On\nMarket is RISK-ON.",
            "Stock Price Data": "Date,Close\n2024-05-14,189.0",
        },
    ):
        node = create_market_analyst(mock_llm_with_tool_call)
        result = node(mock_state)
    assert result["macro_regime_report"] == "## Risk-On\nMarket is RISK-ON."


def test_social_media_analyst_no_bind_tools(mock_state, mock_llm_direct_report):
    """Social analyst must not call bind_tools since there are no tools."""
    node = create_social_media_analyst(mock_llm_direct_report)
    node(mock_state)
    # bind_tools should never have been called (no tools in the list)
    assert mock_llm_direct_report.tools_bound is None


def test_prefetched_context_injected_into_prompt(mock_state, mock_llm_with_tool_call):
    """Market analyst injects pre-fetched context into the prompt sent to the LLM."""
    captured_inputs = []

    class CapturingRunnable(Runnable):
        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            # Return final report directly to end the loop early
            return AIMessage(content="This is the final report after running the tool.")

    class CapturingLLM(Runnable):
        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            return AIMessage(content="This is the final report after running the tool.")

        def bind_tools(self, tools):
            return CapturingRunnable()

    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        return_value={
            "Macro Regime Classification": "**RISK-ON** regime detected.",
            "Stock Price Data": "Date,Close\n2024-05-14,189.0",
        },
    ):
        node = create_market_analyst(CapturingLLM())
        node(mock_state)

    # The prompt was captured; find the system message and verify injected context
    assert captured_inputs, "LLM was never called"
    # The input to the runnable is a list of messages; find the system message text
    messages = captured_inputs[0]
    full_text = " ".join(
        m.content if hasattr(m, "content") else str(m)
        for m in messages
    )
    assert "RISK-ON" in full_text
    assert "Pre-loaded Context" in full_text


def test_news_analyst_no_bind_tools(mock_state, valid_news_report):
    """News analyst must not call bind_tools since there are no tools."""
    mock_llm = MockLLM([valid_news_report])
    with patch(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        return_value={},
    ):
        node = create_news_analyst(mock_llm, evidence_store=FakeNewsEvidenceStore())
        node(mock_state)
    assert mock_llm.tools_bound is None


def test_news_analyst_retries_once_then_passes(mock_state, valid_news_report):
    invalid = AIMessage(content="AAPL generic commentary without dates or sources.")
    mock_llm = MockLLM([invalid, valid_news_report])

    with patch(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        return_value={},
    ):
        node = create_news_analyst(mock_llm, evidence_store=FakeNewsEvidenceStore())
        result = node(mock_state)

    assert mock_llm.runnable.call_count == 2
    assert "[CRITICAL ABORT]" not in result["news_report"]
    assert "AAPL News Analysis" in result["news_report"]


def test_news_analyst_aborts_after_two_invalid_attempts(mock_state):
    invalid = AIMessage(content="AAPL generic commentary without dates or sources.")
    mock_llm = MockLLM([invalid, invalid])

    with patch(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        return_value={},
    ):
        node = create_news_analyst(mock_llm, evidence_store=FakeNewsEvidenceStore())
        result = node(mock_state)

    assert mock_llm.runnable.call_count == 2
    assert result["news_report"].startswith("[CRITICAL ABORT]")


def test_news_analyst_prompt_forbids_internal_headers_as_sources():
    captured_inputs = []

    class CapturingLLM(Runnable):
        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            return AIMessage(
                content="""
                CSTM News Analysis - 2026-04-02
                - Reuters reported on 2026-04-02 that CSTM remained sensitive to aluminum demand.
                - CSTM traded with materials support and CSTM maintained $48.02 valuation discussion.
                - Bloomberg noted on 2026-04-01 that CSTM demand trends remained stable.
                - CSTM remained active in coverage while CSTM sentiment stayed tied to sector data.
                """
            )

    state = {
        "messages": [HumanMessage(content="Continue")],
        "run_id": "run-cstm-001",
        "trade_date": "2026-04-02",
        "company_of_interest": "CSTM",
        "macro_regime_report": "# Macro Regime Classification\n## Regime: TRANSITION",
        "scanner_context_packet": "# SCANNER CONTEXT PACKET: CSTM\nDate: 2026-04-02",
    }

    with patch(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        return_value={
            "Company-Specific News (Last 7 Days)": '{"feed":[{"source":"Sahm"}]}',
            "Global Macroeconomic News (Last 7 Days)": '{"feed":[{"source":"StoneX"}]}',
        },
    ):
        node = create_news_analyst(
            CapturingLLM(),
            evidence_store=FakeNewsEvidenceStore(),
        )
        node(state)

    assert captured_inputs, "LLM was never called"
    messages = captured_inputs[0]
    full_text = " ".join(
        m.content if hasattr(m, "content") else str(m)
        for m in messages
    )
    assert "Never cite labels such as \"Macro Regime Classification\"" in full_text
    assert "Internal prompt labels and section headers are NOT sources." in full_text
    assert "[Evidence ID: art_cstm_001]" in full_text


def test_news_analyst_retry_instruction_restates_internal_header_rule():
    captured_inputs = []

    class RetryCapturingLLM(Runnable):
        def __init__(self):
            self.call_count = 0

        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            self.call_count += 1
            if self.call_count == 1:
                return AIMessage(content="CSTM generic commentary without dates or sources.")
            return AIMessage(
                content="""
                CSTM News Analysis - 2026-04-02
                - Reuters reported on 2026-04-02 that CSTM demand improved 8%.
                - CSTM traded near $48.02 and CSTM sentiment remained tied to materials strength.
                - Bloomberg noted on 2026-04-01 that CSTM remained exposed to automotive demand.
                - CSTM coverage stayed active while CSTM retained event-driven sensitivity.
                """
            )

    state = {
        "messages": [HumanMessage(content="Continue")],
        "run_id": "run-cstm-002",
        "trade_date": "2026-04-02",
        "company_of_interest": "CSTM",
        "scanner_context_packet": "# SCANNER CONTEXT PACKET: CSTM\nDate: 2026-04-02",
    }

    with patch(
        "tradingagents.agents.analysts.news_analyst.prefetch_tools_parallel",
        return_value={
            "Company-Specific News (Last 7 Days)": '{"feed":[{"source":"Sahm"}]}',
            "Global Macroeconomic News (Last 7 Days)": '{"feed":[{"source":"StoneX"}]}',
        },
    ):
        node = create_news_analyst(
            RetryCapturingLLM(),
            evidence_store=FakeNewsEvidenceStore(),
        )
        node(state)

    assert len(captured_inputs) == 2
    retry_messages = captured_inputs[1]
    retry_text = " ".join(
        m.content if hasattr(m, "content") else str(m)
        for m in retry_messages
    )
    assert "The same full scanner context, pre-loaded news feeds, and persisted evidence records remain available on this retry." in retry_text
    assert "Do not cite internal prompt labels or section headers like" in retry_text
    assert "\"Macro Regime Classification\", \"Scanner Context\", or \"Pre-loaded Context\"" in retry_text
