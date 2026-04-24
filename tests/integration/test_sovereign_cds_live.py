"""Live integration tests for the standalone sovereign CDS tool."""

from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from tradingagents.agents.scanners.geopolitical_scanner import create_geopolitical_scanner
from tradingagents.agents.utils.scanner_tools import get_todays_sovereign_cds
from tradingagents.dataflows.sovereign_cds import WorldGovernmentBondsCDSClient

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket()]


class _MockRunnable(Runnable):
    def __init__(self, invoke_responses):
        self.invoke_responses = invoke_responses
        self.call_count = 0

    def invoke(self, input, config=None, **kwargs):
        response = self.invoke_responses[self.call_count]
        self.call_count += 1
        return response


class _MockLLM(Runnable):
    def __init__(self, invoke_responses):
        self.runnable = _MockRunnable(invoke_responses)
        self.tools_bound = None

    def invoke(self, input, config=None, **kwargs):
        return self.runnable.invoke(input, config=config, **kwargs)

    def bind_tools(self, tools):
        self.tools_bound = tools
        return self.runnable


def test_world_government_bonds_cds_client_live():
    client = WorldGovernmentBondsCDSClient()
    snapshot = client.fetch_snapshot()

    if not client.is_current_snapshot(snapshot):
        pytest.skip(
            f"World Government Bonds CDS snapshot is stale: {snapshot.last_update.strftime('%Y-%m-%d %H:%M UTC')}"
        )

    assert snapshot.rows
    us_row = next((row for row in snapshot.rows if row.country == "United States"), None)
    assert us_row is not None
    assert us_row.cds_5y > 0
    assert snapshot.last_update.date() == datetime.now(UTC).date()


def test_get_todays_sovereign_cds_tool_live():
    result = get_todays_sovereign_cds.invoke({})

    if "Skipped:" in result:
        pytest.skip(result)

    assert result.startswith("# Sovereign CDS Snapshot")
    assert "United States" in result
    assert "Germany" in result


def test_geopolitical_node_can_call_todays_sovereign_cds_live():
    llm = _MockLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_todays_sovereign_cds", "args": {}, "id": "tc1"},
                    {"name": "get_gold_price", "args": {}, "id": "tc2"},
                    {"name": "get_oil_prices", "args": {}, "id": "tc3"},
                    {"name": "get_bitcoin_price", "args": {}, "id": "tc4"},
                ],
            ),
            AIMessage(content="Geopolitical report with live sovereign CDS validation."),
        ]
    )

    node = create_geopolitical_scanner(llm)
    result = node(
        {
            "messages": [HumanMessage(content="Run the geopolitical scan.")],
            "scan_date": datetime.now(UTC).date().isoformat(),
        }
    )

    assert "Geopolitical report with live sovereign CDS validation." in result["geopolitical_report"]
    assert result["sender"] == "geopolitical_scanner"
    # Use subset check so future tool additions don't break this assertion.
    # The geopolitical scanner currently binds 8 tools including FX-rate tools.
    REQUIRED_TOOLS = {
        "get_topic_news",
        "get_todays_sovereign_cds",
        "get_gold_price",
        "get_oil_prices",
        "get_bitcoin_price",
        "get_eur_usd_rate",
        "get_jpy_usd_rate",
        "get_cny_usd_rate",
    }
    assert REQUIRED_TOOLS.issubset({t.name for t in llm.tools_bound})
