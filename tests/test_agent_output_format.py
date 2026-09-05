from datetime import date, datetime, timezone

import pytest

from tradingagents.research_platform.agent_artifacts import (
    agent_output_from_analyst_note,
    agent_output_from_investment_thesis,
    agent_output_from_trade_signal,
    render_agent_output,
)
from tradingagents.research_platform.agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputType,
    AnalystNote,
    ConfidenceLevel,
    EvidenceRef,
    InvestmentThesis,
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.artifact_store import JsonArtifactStore
from tradingagents.research_platform.research_report import (
    ResearchReportBundle,
    render_research_report,
)


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        source_id="price:NVDA:2026-01-05",
        description="Daily close and volume snapshot",
        as_of_date=date(2026, 1, 5),
        confidence=0.95,
    )


def _note() -> AnalystNote:
    return AnalystNote(
        symbol="NVDA",
        analyst_role="Market Analyst",
        as_of_date=date(2026, 1, 5),
        summary="Trend is constructive.",
        evidence=[_evidence()],
        risks=["Gap risk into earnings."],
        confidence=ConfidenceLevel.HIGH,
    )


def _thesis() -> InvestmentThesis:
    return InvestmentThesis(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        base_case="Base case remains constructive.",
        bull_case="Bull case.",
        bear_case="Bear case.",
        catalysts=["Estimate revisions."],
        disconfirming_evidence=["Margin pressure."],
        evidence=[_evidence()],
        confidence=0.7,
    )


def _signal() -> TradeSignal:
    return TradeSignal(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        direction=TradeDirection.BUY,
        horizon=TradeHorizon.MEDIUM,
        confidence=0.8,
        rationale="Risk/reward is favorable.",
        proposed_position_pct=0.05,
        expected_return_pct=0.12,
        stop_loss_pct=0.08,
        evidence=[_evidence()],
        invalidation_triggers=["Breaks below support."],
    )


def test_agent_output_envelope_validates_payload_identity():
    note = _note().model_copy(update={"symbol": "AAPL"})

    with pytest.raises(ValueError, match="payload symbol"):
        AgentOutputEnvelope(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            agent_id="market-analyst",
            agent_role="Market Analyst",
            output_type=AgentOutputType.ANALYST_NOTE,
            headline="Market note",
            summary="Summary.",
            payload=note,
        )


def test_agent_output_wrappers_render_cockpit_markdown():
    output = agent_output_from_analyst_note(_note())

    markdown = render_agent_output(output)

    assert output.agent_id == "market-analyst"
    assert output.output_type == AgentOutputType.ANALYST_NOTE
    assert output.payload == _note()
    assert "### Market Analyst: Market Analyst note for NVDA" in markdown
    assert "**Type:** analyst_note" in markdown
    assert "price:NVDA:2026-01-05" in markdown
    assert "- Gap risk into earnings." in markdown


def test_thesis_and_signal_outputs_preserve_machine_fields():
    thesis_output = agent_output_from_investment_thesis(_thesis())
    signal_output = agent_output_from_trade_signal(_signal())

    assert thesis_output.output_type == AgentOutputType.INVESTMENT_THESIS
    assert thesis_output.metadata["confidence_score"] == 0.7
    assert signal_output.output_type == AgentOutputType.TRADE_SIGNAL
    assert "Proposed position: 5.0%" in signal_output.sections[0].bullets
    assert "Breaks below support." in signal_output.risks


def test_json_artifact_store_round_trips_agent_outputs(tmp_path):
    store = JsonArtifactStore(tmp_path)
    output = agent_output_from_analyst_note(_note())

    store.save_agent_outputs([output])
    loaded = store.load_agent_outputs("NVDA", as_of_date=date(2026, 1, 5))

    assert loaded == [output]
    assert isinstance(loaded[0].payload, AnalystNote)
    assert (tmp_path / "agent_outputs" / "NVDA.jsonl").exists()


def test_research_report_renders_agent_outputs():
    output = agent_output_from_trade_signal(_signal())
    manager = agent_output_from_investment_thesis(_thesis()).model_copy(
        update={"metadata": {"provider": "deepseek", "stage": "manager"}}
    )
    bundle = ResearchReportBundle(
        symbol="NVDA",
        as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        agent_outputs=[manager, output],
    )

    report = render_research_report(bundle)

    assert "## Agent Outputs" in report
    assert "### 研究经理综合" in report
    assert "### 确定性研究基线" in report
    assert "### Portfolio Manager: Buy signal for NVDA" in report
    assert "**Type:** trade_signal" in report
