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
        {
          "ticker": "AAPL",
          "report_title": "AAPL News Analysis",
          "claims": [
            {
              "claim": "AAPL supplier demand improved by 8% on 2024-05-15.",
              "source": "Sahm",
              "published_at": "2024-05-15",
              "evidence_id": "art_aapl_001"
            },
            {
              "claim": "AAPL services revenue expectations rose 4% on 2024-05-15.",
              "source": "Sahm",
              "published_at": "2024-05-15",
              "evidence_id": "art_aapl_001"
            },
            {
              "claim": "AAPL remained the focus of analyst revisions with 22% operating margin expectations.",
              "source": "Sahm",
              "published_at": "2024-05-15",
              "evidence_id": "art_aapl_001"
            }
          ],
          "summary_table": [
            {
              "date": "2024-05-15",
              "event": "Supplier demand",
              "metric": "Demand growth",
              "value": "8%",
              "source": "Sahm",
              "evidence_id": "art_aapl_001"
            }
          ]
        }
        """
    )


def test_fundamentals_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    """Fundamentals analyst: pre-fetches 4 tools, runs iterative loop for raw statements."""
    node = create_fundamentals_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["fundamentals_report"]


def test_market_analyst_direct_invoke(mock_state, mock_llm_direct_report):
    """Market analyst: pre-fetches macro + indicator context and invokes directly."""
    node = create_market_analyst(mock_llm_direct_report)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["market_report"]
    structured = result["market_report_structured"]
    assert structured["ticker"] == "AAPL"
    assert structured["as_of_date"] == "2024-05-15"
    assert structured["status"] == "completed"
    assert structured["contract_version"] == "market_summary_v1"


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
    assert result["news_report_structured"]["ticker"] == "AAPL"


def test_market_analyst_macro_regime_from_prefetch(mock_state, mock_llm_direct_report):
    """Market analyst populates macro_regime_report from pre-fetched data when available."""
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        side_effect=[
            {
                "Macro Regime Classification": "## Risk-On\nMarket is RISK-ON.",
                "Stock Price Data": "Date,Close\n2024-05-14,189.0",
            },
            {
                "Technical Indicator: macd": "MACD context",
                "Technical Indicator: rsi": "RSI context",
            },
        ],
    ):
        node = create_market_analyst(mock_llm_direct_report)
        result = node(mock_state)
    assert result["macro_regime_report"] == "## Risk-On\nMarket is RISK-ON."
    assert result["market_report_structured"]["macro_regime"] == "risk_on"


def test_market_analyst_macro_regime_empty_when_prefetch_missing(mock_state):
    """Macro regime should stay empty when prefetch has no macro section."""
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        side_effect=[
            {
                "Stock Price Data": "Date,Close\n2024-05-14,189.0",
            },
            {
                "Technical Indicator: macd": "MACD context",
            },
        ],
    ):
        node = create_market_analyst(
            MockLLM([AIMessage(content="Macro Regime Classification: RISK-ON but sourced from report text only.")])
        )
        result = node(mock_state)
    assert result["macro_regime_report"] == ""
    # Do not infer regime from report prose when prefetch is absent.
    assert result["market_report_structured"]["macro_regime"] == "unknown"


def test_market_analyst_macro_regime_empty_when_prefetch_errors(mock_state):
    """Macro regime should stay empty when macro prefetch returns an error marker."""
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        side_effect=[
            {
                "Macro Regime Classification": "[Error] upstream failure",
                "Stock Price Data": "Date,Close\n2024-05-14,189.0",
            },
            {
                "Technical Indicator: atr": "ATR context",
            },
        ],
    ):
        node = create_market_analyst(MockLLM([AIMessage(content="TRANSITION regime discussed in report body.")]))
        result = node(mock_state)
    assert result["macro_regime_report"] == ""
    assert result["market_report_structured"]["macro_regime"] == "unknown"


def test_market_analyst_structured_status_aborted_on_critical_abort(mock_state):
    """Structured market contract should mark critical abort reports as aborted."""
    abort_report = AIMessage(
        content="[CRITICAL ABORT] Reason: Trading halted pending delisting - SEC notice"
    )
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        side_effect=[
            {
                "Macro Regime Classification": "## Risk-Off\nMarket is RISK-OFF.",
                "Stock Price Data": "Date,Close\n2024-05-14,189.0",
            },
            {
                "Technical Indicator: atr": "ATR context",
            },
        ],
    ):
        node = create_market_analyst(MockLLM([abort_report]))
        result = node(mock_state)
    structured = result["market_report_structured"]
    assert structured["status"] == "aborted"
    assert structured["abort_reason"].startswith("Reason:")
    assert structured["macro_regime"] == "risk_off"


def test_market_analyst_timeout_fallback_returns_report(mock_state, mock_llm_direct_report):
    """Timeout in market LLM invoke should return deterministic fallback instead of stalling."""
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        side_effect=[
            {
                "Macro Regime Classification": "## Risk-Off\nMarket is RISK-OFF.",
                "Stock Price Data": "Date,Close\n2024-05-14,189.0",
            },
            {
                "Technical Indicator: atr": "ATR context",
            },
        ],
    ), patch(
        "tradingagents.agents.analysts.market_analyst._invoke_with_timeout",
        return_value=(None, TimeoutError("forced timeout")),
    ):
        node = create_market_analyst(mock_llm_direct_report)
        result = node(mock_state)

    assert "Timeout Fallback" in result["market_report"]
    assert result["market_report_structured"]["macro_regime"] == "risk_off"
    assert result["market_report_structured"]["status"] == "completed"


def test_social_media_analyst_no_bind_tools(mock_state, mock_llm_direct_report):
    """Social analyst must not call bind_tools since there are no tools."""
    node = create_social_media_analyst(mock_llm_direct_report)
    node(mock_state)
    # bind_tools should never have been called (no tools in the list)
    assert mock_llm_direct_report.tools_bound is None


def test_market_analyst_no_bind_tools(mock_state, mock_llm_direct_report):
    """Market analyst must not call bind_tools after indicator prefetch hardening."""
    node = create_market_analyst(mock_llm_direct_report)
    node(mock_state)
    assert mock_llm_direct_report.tools_bound is None


def test_prefetched_context_injected_into_prompt(mock_state):
    """Market analyst injects pre-fetched context into the prompt sent to the LLM."""
    captured_inputs = []

    class CapturingLLM(Runnable):
        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            return AIMessage(content="This is the final report after running the tool.")

    long_stock = "Date,Close\n" + "\n".join(
        [f"2024-04-{i:02d},{180 + i/10:.2f}" for i in range(1, 62)]
    )
    long_indicator = "Date,Value\n" + "\n".join(
        [f"2024-04-{i:02d},{50 + i/100:.2f}" for i in range(1, 28)]
    )

    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        side_effect=[
            {
                "Macro Regime Classification": "**RISK-ON** regime detected.",
                "Stock Price Data": long_stock,
            },
            {
                "Technical Indicator: macd": long_indicator,
                "Technical Indicator: rsi": "RSI context",
            },
        ],
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
    assert "Technical Indicator: macd" in full_text
    assert "stock data compacted" in full_text
    assert "indicator data compacted" in full_text


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
    invalid = AIMessage(content='{"ticker":"AAPL","claims":[],"summary_table":[]}')
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
    assert result["news_report_structured"]["ticker"] == "AAPL"


def test_news_analyst_aborts_after_two_invalid_attempts(mock_state):
    invalid = AIMessage(content='{"ticker":"AAPL","claims":[],"summary_table":[]}')
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
                {
                  "ticker": "CSTM",
                  "report_title": "CSTM News Analysis",
                  "claims": [
                    {
                      "claim": "CSTM remained sensitive to aluminum demand on 2026-04-02.",
                      "source": "Sahm",
                      "published_at": "2026-04-02",
                      "evidence_id": "art_cstm_001"
                    },
                    {
                      "claim": "CSTM maintained $48.02 valuation discussion in sector coverage.",
                      "source": "Sahm",
                      "published_at": "2026-04-02",
                      "evidence_id": "art_cstm_001"
                    },
                    {
                      "claim": "CSTM demand trends remained stable in the provided article context.",
                      "source": "Sahm",
                      "published_at": "2026-04-02",
                      "evidence_id": "art_cstm_001"
                    }
                  ],
                  "summary_table": []
                }
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
                return AIMessage(content='{"ticker":"CSTM","claims":[],"summary_table":[]}')
            return AIMessage(
                content="""
                {
                  "ticker": "CSTM",
                  "report_title": "CSTM News Analysis",
                  "claims": [
                    {
                      "claim": "CSTM demand improved 8% in the supplied article context.",
                      "source": "Sahm",
                      "published_at": "2026-04-02",
                      "evidence_id": "art_cstm_001"
                    },
                    {
                      "claim": "CSTM traded near $48.02 with materials strength in focus.",
                      "source": "Sahm",
                      "published_at": "2026-04-02",
                      "evidence_id": "art_cstm_001"
                    },
                    {
                      "claim": "CSTM retained event-driven sensitivity in coverage.",
                      "source": "Sahm",
                      "published_at": "2026-04-02",
                      "evidence_id": "art_cstm_001"
                    }
                  ],
                  "summary_table": []
                }
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
