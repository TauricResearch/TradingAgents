from datetime import date, datetime, timezone

from tradingagents.research_platform.agent_contracts import (
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.artifact_store import JsonArtifactStore
from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    InstrumentIdentity,
    NewsItem,
    PriceBar,
)
from tradingagents.research_platform.research_workflow import (
    ResearchWorkflowConfig,
    run_ticker_research,
)
from tradingagents.research_platform.risk_contracts import RiskDecision, RiskPolicy
from tradingagents.research_platform.run_archive import JsonResearchRunArchive


class FakeProvider:
    name = "fixture"

    def __init__(self):
        self.price_request = None
        self.fundamentals_request = None
        self.news_request = None

    def get_price_bars(self, identity, start, end, *, as_of_date=None):
        self.price_request = (identity, start, end, as_of_date)
        return [
            _bar(identity.symbol, date(2026, 1, 1), 100),
            _bar(identity.symbol, date(2026, 1, 2), 105),
            _bar(identity.symbol, date(2026, 1, 3), 110),
            _bar(identity.symbol, date(2026, 1, 5), 120),
        ]

    def get_fundamentals(self, identity, *, as_of_date=None):
        self.fundamentals_request = (identity, as_of_date)
        return [
            FundamentalSnapshot(
                symbol=identity.symbol,
                period_end=date(2026, 1, 5),
                fiscal_period="snapshot",
                currency="USD",
                metrics={"market_cap": 3000000000000, "pe_ratio_ttm": 42.5},
                provenance=_provenance(identity.symbol, date(2026, 1, 5)),
            )
        ]

    def get_news(self, identity, start, end, *, as_of_date=None):
        self.news_request = (identity, start, end, as_of_date)
        return [
            NewsItem(
                symbol=identity.symbol,
                title="Nvidia launches platform",
                published_at=datetime(2026, 1, 4, 15, 30, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 5),
                provider="Example News",
                url="https://example.com/nvda",
                summary="Summary.",
                source_id="news-1",
            )
        ]


class EmptyProvider:
    name = "empty"

    def get_price_bars(self, identity, start, end, *, as_of_date=None):
        return []

    def get_fundamentals(self, identity, *, as_of_date=None):
        return []

    def get_news(self, identity, start, end, *, as_of_date=None):
        return []


def _provenance(symbol: str, day: date) -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=day,
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        source="fixture",
        vendor_symbol=symbol,
    )


def _bar(symbol: str, day: date, close: float) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        adjusted_close=close,
        volume=1000,
        currency="USD",
        provenance=_provenance(symbol, day),
    )


def _signal() -> TradeSignal:
    return TradeSignal(
        symbol="NVDA",
        as_of_date=date(2026, 1, 2),
        direction=TradeDirection.BUY,
        horizon=TradeHorizon.MEDIUM,
        confidence=0.8,
        rationale="Fixture signal.",
        proposed_position_pct=0.20,
    )


def test_run_ticker_research_fetches_stores_reviews_backtests_and_writes_report(tmp_path):
    provider = FakeProvider()
    store = JsonArtifactStore(tmp_path / "cache")
    archive = JsonResearchRunArchive(tmp_path / "cache")

    result = run_ticker_research(
        config=ResearchWorkflowConfig(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            lookback_days=4,
            initial_cash=1000,
        ),
        provider=provider,
        store=store,
        signal=_signal(),
        risk_policy=RiskPolicy(max_single_position_pct=0.10),
        output_dir=tmp_path / "reports",
        archive=archive,
    )

    identity, start, end, as_of = provider.price_request
    assert isinstance(identity, InstrumentIdentity)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 1, 5)
    assert as_of == date(2026, 1, 5)
    assert result.report_path is not None
    assert result.report_path.exists()
    assert result.archived_run is not None
    assert archive.load_latest_bundle("NVDA") == result.bundle
    assert "## Market Snapshot" in result.markdown
    assert "## Risk Review" in result.markdown
    assert result.bundle.risk_review.decision == RiskDecision.REDUCE
    assert result.bundle.backtest_result.trades
    assert len(result.bundle.agent_outputs) == 5
    assert store.load_agent_outputs("NVDA", as_of_date=date(2026, 1, 5))
    assert store.load_price_bars("NVDA", date(2026, 1, 1), date(2026, 1, 5))


def test_run_ticker_research_without_signal_still_returns_data_report():
    result = run_ticker_research(
        config=ResearchWorkflowConfig(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            lookback_days=4,
        ),
        provider=FakeProvider(),
    )

    assert result.report_path is None
    assert result.bundle.signal is None
    assert result.bundle.risk_review is None
    assert result.bundle.backtest_result is None
    assert len(result.bundle.analyst_notes) == 3
    assert len(result.bundle.agent_outputs) == 4
    assert result.bundle.thesis is not None


def test_run_ticker_research_handles_empty_provider():
    result = run_ticker_research(
        config=ResearchWorkflowConfig(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            lookback_days=4,
        ),
        provider=EmptyProvider(),
    )

    assert result.bundle.price_bars == []
    assert result.bundle.analyst_notes == []
    assert result.bundle.agent_outputs == []
    assert result.bundle.thesis is None
    assert "No normalized price bars available." in result.markdown


class FixtureNarrativeProvider:
    def __init__(self):
        self.last_context = None
        self.config = type(
            "Config",
            (),
            {"base_url": "https://user:secret@example.com/v1?api_key=hidden"},
        )()

    def generate(self, context):
        self.last_context = context
        from tradingagents.research_platform.agent_contracts import (
            AgentOutputEnvelope,
            AgentOutputType,
            ConfidenceLevel,
        )

        return [
            AgentOutputEnvelope(
                symbol=context.symbol,
                as_of_date=context.as_of_date,
                agent_id="fixture-narrative",
                agent_role="Fixture Narrative",
                output_type=AgentOutputType.COCKPIT_PANEL,
                headline="Fixture narrative",
                summary="Validated fixture commentary.",
                evidence=context.evidence,
                confidence=ConfidenceLevel.MEDIUM,
                metadata={
                    "provider": "fixture",
                    "model": "fixture-model",
                    "prompt_version": "fixture-prompt-v1",
                    "latency_ms": 25,
                    "usage_input_tokens": 10,
                    "usage_output_tokens": 5,
                },
            )
        ]


def test_run_ticker_research_persists_optional_narrative_output(tmp_path):
    archive = JsonResearchRunArchive(tmp_path / "cache")
    narrative_provider = FixtureNarrativeProvider()
    result = run_ticker_research(
        config=ResearchWorkflowConfig(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            lookback_days=4,
            narrative_mode="multi_agent_research",
        ),
        provider=FakeProvider(),
        archive=archive,
        narrative_provider=narrative_provider,
    )

    narrative = next(
        output for output in result.bundle.agent_outputs if output.agent_id == "fixture-narrative"
    )
    assert narrative.evidence
    assert narrative_provider.last_context is not None
    assert len(narrative_provider.last_context.deterministic_outputs) == 4
    assert (
        "# Personal Research Report: NVDA"
        in narrative_provider.last_context.deterministic_report_markdown
    )
    assert "Investment Thesis" in narrative_provider.last_context.deterministic_report_markdown
    assert archive.load_latest_bundle("NVDA") == result.bundle
    audit = result.bundle.run_audit
    assert audit is not None
    assert audit.narrative_mode == "multi_agent_research"
    assert audit.data_provider == "fixture"
    assert audit.llm_provider == "fixture"
    assert audit.llm_model == "fixture-model"
    assert audit.llm_endpoint == "https://example.com/v1"
    assert "secret" not in result.bundle.model_dump_json()
    assert "hidden" not in result.bundle.model_dump_json()
    assert audit.prompt_versions == ["fixture-prompt-v1"]
    assert audit.price_basis == "forward_adjusted"
    assert audit.adjusted_price_bar_count == 4
    assert audit.successful_model_stages == 1
    assert audit.degraded_model_stages == 0
    assert audit.total_model_latency_ms == 25
    assert audit.usage == {"input_tokens": 10, "output_tokens": 5}


def test_workflow_passes_point_in_time_game_context_to_narrative_provider(tmp_path):
    narrative_provider = FixtureNarrativeProvider()
    result = run_ticker_research(
        config=ResearchWorkflowConfig(
            symbol="002602",
            as_of_date=date(2026, 7, 12),
            lookback_days=90,
        ),
        provider=FakeProvider(),
        store=JsonArtifactStore(tmp_path),
        narrative_provider=narrative_provider,
    )

    context = narrative_provider.last_context
    assert context is not None
    assert context.game_research is not None
    assert context.game_research.available is True
    assert {item.name for item in context.game_research.products} >= {
        "Whiteout Survival",
        "Kingshot",
    }
    assert context.game_approvals is not None
    assert context.game_opportunity is not None
    assert any(item.source_id.startswith("game:") for item in context.evidence)
    assert result.bundle.symbol == "002602"
