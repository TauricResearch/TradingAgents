from datetime import date, datetime, timezone
from time import sleep

from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    NewsItem,
    PriceBar,
)
from tradingagents.research_platform.multi_agent_research import (
    LLMResearchConfig,
    MultiAgentResearchProvider,
)
from tradingagents.research_platform.research_jobs import (
    LocalResearchJobRunner,
    ManualSignalRequest,
    ResearchDataProvider,
    ResearchJobRequest,
    ResearchJobStatus,
    resolve_data_provider,
)
from tradingagents.research_platform.run_archive import JsonResearchRunArchive


class FixtureProvider:
    name = "fixture"

    def get_price_bars(self, identity, start, end, *, as_of_date=None):
        return [
            PriceBar(
                symbol=identity.symbol,
                date=date(2026, 1, 2),
                open=100,
                high=104,
                low=99,
                close=103,
                volume=100,
                currency="USD",
                provenance=_provenance(),
            )
        ]

    def get_fundamentals(self, identity, *, as_of_date=None):
        return [
            FundamentalSnapshot(
                symbol=identity.symbol,
                period_end=date(2026, 1, 2),
                metrics={"market_cap": 1_000_000},
                provenance=_provenance(),
            )
        ]

    def get_news(self, identity, start, end, *, as_of_date=None):
        return [
            NewsItem(
                symbol=identity.symbol,
                title="Fixture headline",
                published_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 2),
                provider="fixture-news",
                source_id="fixture-news-1",
            )
        ]


def _provenance() -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=date(2026, 1, 2),
        retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_local_job_runner_executes_workflow_archives_and_reports(tmp_path):
    runner = LocalResearchJobRunner(tmp_path, provider_factory=lambda request: FixtureProvider())

    queued = runner.submit(ResearchJobRequest(symbol=" nvda ", as_of_date=date(2026, 1, 2)))
    completed = runner.wait(queued.job_id, timeout=2)

    assert completed.status == ResearchJobStatus.SUCCEEDED
    assert completed.report_path is not None
    assert completed.report_path.exists()
    assert completed.run_id is not None
    assert runner.list_jobs() == [completed]
    runner.shutdown()


def test_local_job_runner_exposes_provider_failures_as_job_state(tmp_path):
    def failing_provider(request):
        raise RuntimeError("fixture provider unavailable")

    runner = LocalResearchJobRunner(tmp_path, provider_factory=failing_provider)

    queued = runner.submit(ResearchJobRequest(symbol="NVDA"))
    completed = runner.wait(queued.job_id, timeout=2)

    assert completed.status == ResearchJobStatus.FAILED
    assert completed.error == "fixture provider unavailable"
    runner.shutdown()


def test_local_job_runner_routes_manual_signal_through_risk_and_backtest(tmp_path):
    runner = LocalResearchJobRunner(tmp_path, provider_factory=lambda request: FixtureProvider())
    request = ResearchJobRequest(
        symbol="NVDA",
        as_of_date=date(2026, 1, 2),
        manual_signal=ManualSignalRequest(
            direction="buy",
            confidence=0.8,
            proposed_position_pct=0.20,
            rationale="Fixture manual decision.",
        ),
    )

    completed = runner.wait(runner.submit(request).job_id, timeout=2)

    assert completed.status == ResearchJobStatus.SUCCEEDED
    assert completed.run_id is not None

    bundle = JsonResearchRunArchive(tmp_path).load_latest_bundle("NVDA")
    assert bundle is not None
    assert bundle.signal is not None
    assert bundle.risk_review is not None
    assert bundle.risk_review.approved_position_pct == 0.10
    assert bundle.backtest_result is not None
    runner.shutdown()


class FixtureNarrativeProvider:
    def generate(self, context):
        from tradingagents.research_platform.agent_contracts import (
            AgentOutputEnvelope,
            AgentOutputType,
        )

        return [
            AgentOutputEnvelope(
                symbol=context.symbol,
                as_of_date=context.as_of_date,
                agent_id="fixture-narrative",
                agent_role="Fixture Narrative",
                output_type=AgentOutputType.COCKPIT_PANEL,
                headline="Fixture narrative",
                summary="Fixture narrative output.",
                evidence=context.evidence,
            )
        ]


def test_local_job_runner_persists_selected_narrative_mode(tmp_path):
    runner = LocalResearchJobRunner(
        tmp_path,
        provider_factory=lambda request: FixtureProvider(),
        narrative_provider_factory=lambda request: FixtureNarrativeProvider(),
    )
    completed = runner.wait(
        runner.submit(
            ResearchJobRequest(
                symbol="NVDA",
                as_of_date=date(2026, 1, 2),
                narrative_mode="openai_narrative",
            )
        ).job_id,
        timeout=2,
    )

    assert completed.status == ResearchJobStatus.SUCCEEDED
    bundle = JsonResearchRunArchive(tmp_path).load_latest_bundle("NVDA")
    assert bundle is not None
    assert any(output.agent_id == "fixture-narrative" for output in bundle.agent_outputs)
    runner.shutdown()


def test_local_job_runner_reports_missing_openai_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_OPENAI_MODEL", raising=False)
    runner = LocalResearchJobRunner(tmp_path, provider_factory=lambda request: FixtureProvider())

    completed = runner.wait(
        runner.submit(
            ResearchJobRequest(
                symbol="NVDA",
                as_of_date=date(2026, 1, 2),
                narrative_mode="openai_narrative",
            )
        ).job_id,
        timeout=2,
    )

    assert completed.status == ResearchJobStatus.FAILED
    assert completed.error is not None
    assert "OPENAI_API_KEY" in completed.error
    runner.shutdown()


def test_research_job_auto_selects_tushare_only_for_supported_china_hong_kong_symbols():
    assert (
        resolve_data_provider(ResearchJobRequest(symbol="600519")) == ResearchDataProvider.TUSHARE
    )
    assert (
        resolve_data_provider(ResearchJobRequest(symbol="700.HK")) == ResearchDataProvider.TUSHARE
    )
    assert resolve_data_provider(ResearchJobRequest(symbol="NVDA")) == ResearchDataProvider.YFINANCE
    assert (
        resolve_data_provider(
            ResearchJobRequest(symbol="600519", data_provider=ResearchDataProvider.YFINANCE)
        )
        == ResearchDataProvider.YFINANCE
    )


def test_local_job_runner_persists_multi_agent_mode_with_fake_provider(tmp_path):
    runner = LocalResearchJobRunner(
        tmp_path,
        provider_factory=lambda request: FixtureProvider(),
        narrative_provider_factory=lambda request: FixtureNarrativeProvider(),
    )
    completed = runner.wait(
        runner.submit(
            ResearchJobRequest(
                symbol="002624",
                as_of_date=date(2026, 1, 2),
                narrative_mode="multi_agent_research",
            )
        ).job_id,
        timeout=2,
    )
    assert completed.status == ResearchJobStatus.SUCCEEDED
    assert completed.phase == "completed"
    bundle = JsonResearchRunArchive(tmp_path).load_latest_bundle("002624")
    assert bundle is not None
    assert any(output.agent_id == "fixture-narrative" for output in bundle.agent_outputs)
    runner.shutdown()


class HangingResearchLLM:
    def __init__(self):
        self.calls = 0

    def with_structured_output(self, schema, **kwargs):
        owner = self

        class Runner:
            def invoke(self, prompt):
                owner.calls += 1
                sleep(0.25)
                raise AssertionError("late fixture result")

        return Runner()


def test_timed_out_multi_agent_job_releases_single_worker_for_next_job(tmp_path):
    llm = HangingResearchLLM()
    narrative = MultiAgentResearchProvider(
        config=LLMResearchConfig(
            provider="deepseek",
            model="fixture-model",
            call_timeout_seconds=0.02,
            max_retries=0,
            total_timeout_seconds=1,
        ),
        llm=llm,
    )
    runner = LocalResearchJobRunner(
        tmp_path,
        provider_factory=lambda request: FixtureProvider(),
        narrative_provider_factory=lambda request: narrative,
    )

    first = runner.submit(
        ResearchJobRequest(
            symbol="002624",
            as_of_date=date(2026, 1, 2),
            narrative_mode="multi_agent_research",
        )
    )
    second = runner.submit(ResearchJobRequest(symbol="002602", as_of_date=date(2026, 1, 2)))

    first_result = runner.wait(first.job_id, timeout=1)
    second_result = runner.wait(second.job_id, timeout=1)

    assert first_result.status == ResearchJobStatus.SUCCEEDED
    assert second_result.status == ResearchJobStatus.SUCCEEDED
    assert llm.calls == 1
    first_bundle = JsonResearchRunArchive(tmp_path).load_latest_bundle("002624")
    assert first_bundle is not None
    assert first_bundle.run_audit is not None
    assert first_bundle.run_audit.degraded_model_stages == 7
    runner.shutdown()
