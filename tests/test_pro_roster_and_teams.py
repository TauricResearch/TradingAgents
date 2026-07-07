"""Roster integrity + one integration pass per team with fake LLMs."""

from datetime import datetime, timezone

import pytest

from tests.pro_fakes import make_bars
from tests.test_pro_agents_base import FakeLLM, make_snapshot
from tradingagents.contracts import AgentTeam, RiskLimits, Timeframe
from tradingagents.pro.agents import (
    ROSTER,
    SPECS_BY_TEAM,
    build_team,
    compute_quant_metrics,
    compute_risk_metrics,
    load_team_template,
    run_agents,
    spec_by_id,
    specs_for_asset,
)

AS_OF = datetime(2026, 7, 6, 14, 30, tzinfo=timezone.utc)

APPENDIX_COUNTS = {
    AgentTeam.TECHNICAL: 24,
    AgentTeam.MACRO: 11,
    AgentTeam.NEWS_SENTIMENT: 7,
    AgentTeam.QUANT: 8,
    AgentTeam.RISK: 9,
}


class TestRosterIntegrity:
    def test_full_appendix_coverage(self):
        assert len(ROSTER) == sum(APPENDIX_COUNTS.values()) == 59
        for team, count in APPENDIX_COUNTS.items():
            assert len(SPECS_BY_TEAM[team]) == count, team

    def test_agent_ids_unique(self):
        ids = [s.agent_id for s in ROSTER]
        assert len(ids) == len(set(ids))

    def test_every_spec_selects_data(self):
        for spec in ROSTER:
            assert (
                spec.indicators or spec.metrics or spec.include_bars or spec.include_news
            ), spec.agent_id

    def test_technical_agents_never_select_news(self):
        # Constraint 2 hygiene: technical agents read indicators/bars only
        for spec in SPECS_BY_TEAM[AgentTeam.TECHNICAL]:
            assert spec.include_news == 0, spec.agent_id
            assert not spec.metrics, spec.agent_id

    def test_known_gaps_are_documented(self):
        for agent_id in ("vwap", "adx", "supertrend", "twitter_sentiment"):
            assert spec_by_id(agent_id).notes, f"{agent_id} gap must carry a note"

    def test_spec_lookup_and_timeframe_override(self):
        assert spec_by_id("rsi").team is AgentTeam.TECHNICAL
        with pytest.raises(KeyError):
            spec_by_id("nonexistent")
        h4 = specs_for_asset(Timeframe.H4)
        assert all(s.timeframe is Timeframe.H4 for s in h4)
        assert len(h4) == len(ROSTER)

    def test_all_team_templates_load_and_have_placeholders(self):
        for team in APPENDIX_COUNTS:
            template = load_team_template(team.value)
            for placeholder in ("{persona}", "{data_block}", "{missing_note}"):
                assert placeholder in template, (team, placeholder)


class TestTeamsEndToEnd:
    def _evidence_for_team(self, team: AgentTeam, extra=None):
        snapshot = make_snapshot()
        agents = build_team(SPECS_BY_TEAM[team], FakeLLM())
        return run_agents(agents, snapshot, extra_metrics=extra)

    def test_technical_team_emits_for_available_indicators_only(self):
        evidence = self._evidence_for_team(AgentTeam.TECHNICAL)
        ids = {e.agent_id for e in evidence}
        # snapshot carries RSI_14 + MACD + bars: indicator agents with data + pattern agents
        assert "rsi" in ids and "macd" in ids and "wyckoff" in ids
        # unavailable-indicator agents abstained
        assert {"vwap", "adx", "supertrend"}.isdisjoint(ids)
        for e in evidence:
            assert e.team is AgentTeam.TECHNICAL
            assert e.data_refs and e.sources

    def test_macro_team(self):
        snapshot = make_snapshot()
        agents = build_team(SPECS_BY_TEAM[AgentTeam.MACRO], FakeLLM())
        evidence = run_agents(agents, snapshot)
        ids = {e.agent_id for e in evidence}
        assert "dollar_index" in ids  # DXY present
        assert "geopolitical_risk" in ids  # news present
        assert "inflation" not in ids  # no CPI in this snapshot -> abstain

    def test_news_team_attribution(self):
        evidence = self._evidence_for_team(AgentTeam.NEWS_SENTIMENT)
        by_id = {e.agent_id: e for e in evidence}
        assert "general_news" in by_id
        news_evidence = by_id["general_news"]
        assert news_evidence.sources[0].id.startswith("news:")
        assert all(e.confidence <= 100 for e in evidence)

    def test_quant_team_with_computed_features(self):
        snapshot = make_snapshot()
        extra = compute_quant_metrics(snapshot.bars)
        evidence = self._evidence_for_team(AgentTeam.QUANT, extra=extra)
        ids = {e.agent_id for e in evidence}
        assert "regime_detection" in ids
        assert "volatility_forecast" in ids
        regime = next(e for e in evidence if e.agent_id == "regime_detection")
        assert {r.name for r in regime.data_refs} == {
            "REALIZED_VOL_ANN", "TREND_SLOPE_PCT", "TREND_R2"
        }
        assert regime.sources[0].id == "quant_engine"

    def test_risk_team_with_engine_outputs(self):
        from tradingagents.contracts import IndicatorReading

        snapshot = make_snapshot(
            indicators=[
                *make_snapshot().indicators,
                # give the risk engine an ATR to work with
                IndicatorReading(
                    name="ATR_14", timeframe=Timeframe.D1, value={"value": 12.5},
                    params={"period": 14},
                ),
            ]
        )
        extra = compute_risk_metrics(snapshot, RiskLimits(), equity=100_000.0)
        agents = build_team(SPECS_BY_TEAM[AgentTeam.RISK], FakeLLM())
        evidence = run_agents(agents, snapshot, extra_metrics=extra)
        ids = {e.agent_id for e in evidence}
        assert {"position_sizing", "var", "cvar", "dynamic_stop_loss",
                "dynamic_take_profit", "exposure"} <= ids
        # kelly abstains: no win statistics supplied
        assert "kelly_criterion" not in ids
        sizing = next(e for e in evidence if e.agent_id == "position_sizing")
        assert sizing.sources[0].id == "risk_engine"


class TestComputedMetricsHelpers:
    def test_quant_metrics_names_and_windows(self):
        metrics = compute_quant_metrics(make_bars(n=60))
        assert set(metrics) == {
            "REALIZED_VOL_ANN", "TREND_SLOPE_PCT", "TREND_R2", "CLOSE_ZSCORE_50"
        }
        short = compute_quant_metrics(make_bars(n=10))
        assert "CLOSE_ZSCORE_50" not in short

    def test_risk_metrics_without_atr_still_reports_limits(self):
        snapshot = make_snapshot()  # no ATR_14 indicator
        metrics = compute_risk_metrics(snapshot, RiskLimits(), equity=50_000.0)
        assert "MAX_RISK_PER_TRADE_PCT" in metrics
        assert "VAR_95" in metrics  # 60 bars of returns available
        assert "ATR_STOP" not in metrics
        assert "KELLY_FRACTION" not in metrics

    def test_risk_metrics_kelly_only_with_stats(self):
        snapshot = make_snapshot()
        metrics = compute_risk_metrics(
            snapshot, RiskLimits(), equity=50_000.0,
            win_rate=0.55, avg_win=150.0, avg_loss=100.0,
        )
        assert metrics["KELLY_FRACTION"].value > 0
