"""Phase 3 — execution layer unit tests.

Covers:
- ``safety.resolve_mode`` — three-gate live/paper resolution.
- ``sizing.plan_stake`` — full-Kelly math + confidence discounting + caps.
- ``runner.parse_market_decision`` — round-trip from rendered markdown.
"""

from __future__ import annotations

import pytest

from tradingagents.agents.schemas import (
    Confidence,
    MarketDecision,
    MarketSide,
    render_market_decision,
)
from tradingagents.execution import safety, sizing
from tradingagents.execution.runner import parse_market_decision


# ---------------------------------------------------------------------------
# Safety gates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveMode:
    def test_paper_when_caller_did_not_request_live(self, monkeypatch):
        monkeypatch.delenv(safety.KILL_SWITCH_ENV, raising=False)
        config = {"kalshi": {"paper_mode": False}}
        assert safety.resolve_mode(requested_live=False, config=config) == "paper"

    def test_paper_when_kill_switch_set(self, monkeypatch):
        monkeypatch.setenv(safety.KILL_SWITCH_ENV, "1")
        config = {"kalshi": {"paper_mode": False}}
        assert safety.resolve_mode(requested_live=True, config=config) == "paper"

    def test_paper_when_config_paper_mode_true(self, monkeypatch):
        monkeypatch.delenv(safety.KILL_SWITCH_ENV, raising=False)
        config = {"kalshi": {"paper_mode": True}}
        assert safety.resolve_mode(requested_live=True, config=config) == "paper"

    def test_live_only_when_all_three_gates_aligned(self, monkeypatch):
        monkeypatch.delenv(safety.KILL_SWITCH_ENV, raising=False)
        config = {"kalshi": {"paper_mode": False}}
        assert safety.resolve_mode(requested_live=True, config=config) == "live"


# ---------------------------------------------------------------------------
# Stake sizing
# ---------------------------------------------------------------------------


def _decision(side, p_yes=0.6, market_p_yes=0.5, conf=Confidence.MEDIUM,
              kelly=0.25):
    return MarketDecision(
        p_yes=p_yes, market_p_yes=market_p_yes,
        edge_bps=(p_yes - market_p_yes) * 10000,
        recommended_side=side, confidence=conf,
        kelly_fraction=kelly,
        executive_summary="—",
        investment_thesis="—",
        key_risks="—",
    )


@pytest.mark.unit
class TestPlanStake:
    def test_pass_returns_zero_stake(self):
        plan = sizing.plan_stake(
            _decision(MarketSide.PASS),
            bankroll_usd=1000.0,
            max_stake_usd=100.0,
        )
        assert plan.side == MarketSide.PASS
        assert plan.contract_count == 0
        assert plan.stake_usd == 0.0

    def test_yes_with_edge_produces_positive_stake(self):
        plan = sizing.plan_stake(
            _decision(MarketSide.YES, p_yes=0.65, market_p_yes=0.50),
            bankroll_usd=1000.0,
            max_stake_usd=100.0,
        )
        assert plan.side == MarketSide.YES
        assert plan.contract_count > 0
        assert 0 < plan.stake_usd <= 100.0
        assert plan.price_cents == 50

    def test_no_with_edge_produces_positive_stake(self):
        plan = sizing.plan_stake(
            _decision(MarketSide.NO, p_yes=0.35, market_p_yes=0.50),
            bankroll_usd=1000.0,
            max_stake_usd=100.0,
        )
        assert plan.side == MarketSide.NO
        assert plan.contract_count > 0
        # NO at p_market 0.50 means buying NO at 1 - 0.50 = 0.50.
        assert plan.price_cents == 50

    def test_low_confidence_zeroes_the_stake(self):
        plan = sizing.plan_stake(
            _decision(MarketSide.YES, conf=Confidence.LOW),
            bankroll_usd=1000.0,
            max_stake_usd=100.0,
        )
        assert plan.side == MarketSide.PASS

    def test_max_stake_cap_respected(self):
        plan = sizing.plan_stake(
            _decision(MarketSide.YES, p_yes=0.95, market_p_yes=0.10, conf=Confidence.HIGH, kelly=1.0),
            bankroll_usd=10_000.0,
            max_stake_usd=50.0,
        )
        assert plan.stake_usd <= 50.0

    def test_no_edge_downgrades_to_pass(self):
        plan = sizing.plan_stake(
            _decision(MarketSide.YES, p_yes=0.40, market_p_yes=0.55),
            bankroll_usd=1000.0,
            max_stake_usd=100.0,
        )
        assert plan.side == MarketSide.PASS


# ---------------------------------------------------------------------------
# Markdown round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseMarketDecision:
    def test_roundtrip_yes_high_confidence(self):
        original = MarketDecision(
            p_yes=0.72,
            market_p_yes=0.55,
            edge_bps=1700.0,
            recommended_side=MarketSide.YES,
            confidence=Confidence.HIGH,
            kelly_fraction=0.04,
            executive_summary="Build YES exposure into close.",
            investment_thesis="Technicals + on-chain + sentiment all converge.",
            key_risks="Surprise SEC enforcement could collapse the YES side.",
        )
        markdown = render_market_decision(original)
        parsed = parse_market_decision(markdown)
        assert parsed is not None
        assert parsed.recommended_side == MarketSide.YES
        assert parsed.confidence == Confidence.HIGH
        assert abs(parsed.p_yes - 0.72) < 1e-6
        assert abs(parsed.market_p_yes - 0.55) < 1e-6
        assert abs(parsed.kelly_fraction - 0.04) < 1e-6

    def test_pass_is_recovered(self):
        original = MarketDecision(
            p_yes=0.50, market_p_yes=0.50, edge_bps=0.0,
            recommended_side=MarketSide.PASS,
            confidence=Confidence.LOW,
            kelly_fraction=0.0,
            executive_summary="—", investment_thesis="—", key_risks="—",
        )
        parsed = parse_market_decision(render_market_decision(original))
        assert parsed is not None
        assert parsed.recommended_side == MarketSide.PASS
