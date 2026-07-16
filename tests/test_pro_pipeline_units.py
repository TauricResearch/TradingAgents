"""Pipeline units: deterministic vote accounting and the risk gate."""

import pytest

from tests.test_pro_agents_base import make_snapshot  # noqa: F401 (fixture reuse)
from tradingagents.contracts import (
    AgentEvidence,
    AgentTeam,
    AgentVote,
    AssetClass,
    DataRef,
    Direction,
    MetricReading,
    ProConfig,
    SourceAttribution,
    SourceType,
    Timeframe,
    TradeAction,
)
from tradingagents.pro.pipeline import (
    build_vote_breakdown,
    confidence_weighted_consensus,
    event_gate,
    risk_gate,
    votes_from_evidence,
)


def make_evidence(agent_id: str, direction: Direction, confidence: int) -> AgentEvidence:
    return AgentEvidence(
        agent_id=agent_id,
        team=AgentTeam.TECHNICAL,
        claim=f"{agent_id} claim",
        direction=direction,
        confidence=confidence,
        timeframe=Timeframe.D1,
        data_refs=[DataRef(name="X", value=1.0, source="indicator_engine")],
        sources=[SourceAttribution(id="indicator_engine", type=SourceType.INDICATOR,
                                   name="engine")],
    )


class TestVotes:
    def test_direction_maps_to_action(self):
        votes = votes_from_evidence([
            make_evidence("a", Direction.BULLISH, 70),
            make_evidence("b", Direction.BEARISH, 60),
            make_evidence("c", Direction.NEUTRAL, 50),
        ])
        assert [v.vote for v in votes] == [TradeAction.BUY, TradeAction.SELL, TradeAction.HOLD]
        assert [v.confidence for v in votes] == [70, 60, 50]

    def test_confidence_weighted_consensus(self):
        votes = [
            AgentVote(agent_id="a", vote=TradeAction.BUY, confidence=80),
            AgentVote(agent_id="b", vote=TradeAction.BUY, confidence=40),
            AgentVote(agent_id="c", vote=TradeAction.SELL, confidence=50),
        ]
        action, share = confidence_weighted_consensus(votes)
        assert action is TradeAction.BUY
        assert share == pytest.approx(120 / 170)

    def test_tie_resolves_to_hold(self):
        votes = [
            AgentVote(agent_id="a", vote=TradeAction.BUY, confidence=50),
            AgentVote(agent_id="b", vote=TradeAction.SELL, confidence=50),
        ]
        action, _ = confidence_weighted_consensus(votes)
        assert action is TradeAction.HOLD

    def test_breakdown_includes_judge_vote(self):
        evidence = [make_evidence("a", Direction.BULLISH, 70)]
        judge = AgentVote(agent_id="judge", vote=TradeAction.BUY, confidence=65)
        breakdown = build_vote_breakdown(evidence, judge)
        assert [v.agent_id for v in breakdown.votes] == ["a", "judge"]
        assert breakdown.tally()[TradeAction.BUY] == 2

    def test_empty_votes_rejected(self):
        with pytest.raises(ValueError, match="no votes"):
            confidence_weighted_consensus([])


class TestEventGate:
    from datetime import datetime, timezone
    NOW = datetime(2026, 7, 16, 16, 0, tzinfo=timezone.utc)

    def event(self, at: str | None, release="FOMC Press Release"):
        return {"release": release, "date": "2026-07-16", "major": True,
                "at": at}

    def test_blocks_inside_the_window(self):
        # FOMC at 18:00Z, now 16:00Z, window 4h -> blocked
        result = event_gate(self.event("2026-07-16T18:00:00+00:00"),
                            self.NOW, 4.0)
        assert not result.passed
        assert "FOMC Press Release in 2.0h" in result.reasons[0]

    def test_passes_outside_the_window(self):
        result = event_gate(self.event("2026-07-16T22:30:00+00:00"),
                            self.NOW, 4.0)
        assert result.passed

    def test_past_events_do_not_block(self):
        result = event_gate(self.event("2026-07-16T12:30:00+00:00"),
                            self.NOW, 4.0)
        assert result.passed

    def test_disabled_or_missing_calendar_passes_open(self):
        assert event_gate(self.event("2026-07-16T18:00:00+00:00"),
                          self.NOW, 0).passed
        assert event_gate(None, self.NOW, 4.0).passed

    def test_date_only_event_passes_open(self):
        # blocking whole days on time-less events would be worse than
        # the disease; honesty over paralysis
        assert event_gate(self.event(None), self.NOW, 4.0).passed


class TestRiskGate:
    CONFIG = ProConfig(asset=AssetClass.GOLD)  # max_daily_loss 3%

    def metric(self, name, value):
        return MetricReading(name=name, value=value, source="risk_engine")

    def test_passes_within_limits(self):
        result = risk_gate({"VAR_95": self.metric("VAR_95", 0.01)}, self.CONFIG)
        assert result.passed
        assert result.checks == {"var_available": True, "var_within_limit": True}

    def test_fails_on_var_breach(self):
        result = risk_gate({"VAR_95": self.metric("VAR_95", 0.05)}, self.CONFIG)
        assert not result.passed
        assert "exceeds max daily loss" in result.reasons[0]

    def test_fails_on_cvar_tail_breach(self):
        metrics = {
            "VAR_95": self.metric("VAR_95", 0.01),
            "CVAR_95": self.metric("CVAR_95", 0.09),
        }
        result = risk_gate(metrics, self.CONFIG)
        assert not result.passed
        assert any("CVaR95" in r for r in result.reasons)

    def test_fails_when_var_unavailable(self):
        result = risk_gate({}, self.CONFIG)
        assert not result.passed
        assert result.checks["var_available"] is False

    def test_directional_action_requires_levels(self):
        metrics = {"VAR_95": self.metric("VAR_95", 0.01)}
        result = risk_gate(metrics, self.CONFIG, proposed_action=TradeAction.BUY)
        assert not result.passed
        assert result.checks["levels_available"] is False

    def test_directional_action_with_levels_passes(self):
        metrics = {
            "VAR_95": self.metric("VAR_95", 0.01),
            "ENTRY_REF_PRICE": self.metric("ENTRY_REF_PRICE", 2400.0),
            "ATR_STOP": self.metric("ATR_STOP", 2380.0),
        }
        result = risk_gate(metrics, self.CONFIG, proposed_action=TradeAction.BUY)
        assert result.passed
