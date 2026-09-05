from datetime import datetime, timezone

import pytest

from tradingagents.research_platform.agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputType,
)
from tradingagents.research_platform.report_workspace import (
    build_report_workspace,
    render_archived_report,
)
from tradingagents.research_platform.research_report import ResearchReportBundle


def test_report_workspace_marks_core_and_optional_layers():
    bundle = ResearchReportBundle(
        symbol="NVDA",
        as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        agent_outputs=[
            AgentOutputEnvelope(
                symbol="NVDA",
                as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc).date(),
                agent_id="openai-research-narrative",
                agent_role="OpenAI Research Narrative",
                output_type=AgentOutputType.COCKPIT_PANEL,
                headline="Fixture narrative",
                summary="Fixture narrative output.",
                metadata={"mode": "openai_narrative"},
            )
        ],
    )

    workspace = build_report_workspace(bundle)

    assert workspace["available"] is True
    assert workspace["core_available"] == 0
    assert workspace["core_total"] == 3
    narrative = next(item for item in workspace["items"] if item["key"] == "narrative")
    assert narrative["available"] is True
    assert narrative["optional"] is True


def test_render_archived_report_requires_bundle():
    with pytest.raises(ValueError, match="archived research run"):
        render_archived_report(None)
