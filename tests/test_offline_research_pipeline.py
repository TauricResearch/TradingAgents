"""Focused guarantees for the capability-separated offline pipeline."""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradingagents.evidence_lineage import evidence_id, raw_content_id
from tradingagents.global_research import (
    build_forecast_prompt,
    evidence_selection_manifest,
    prepare_evidence,
)
from tradingagents.research.artifacts import ArtifactIntegrityError, FilesystemArtifactStore
from tradingagents.research.contracts import (
    DecisionBatch,
    EvaluationReport,
    ModelCheckpointSpec,
    OutcomeBatch,
    OutcomeObservation,
    parse_contract,
)
from tradingagents.research.decide import decide_from_artifact, generate_decisions
from tradingagents.research.evaluate import evaluate, evaluate_from_artifacts
from tradingagents.research.label import attach_labels, label_from_artifact
from tradingagents.research.snapshot import (
    build_media_snapshot,
    build_snapshot,
    commit_snapshot,
)
from tradingagents.research.x_availability import (
    _accepted_cycles,
    _cycle_summary,
    bind_x_availability_to_selection,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES,
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
    global_news_query_slot_label,
    model_identity,
)

UNIVERSE = tuple(GLOBAL_EVENT_V2_PROTOCOL["universe"]["symbols"])
SECTORS = dict(GLOBAL_EVENT_V2_PROTOCOL["universe"]["sectors"])
BENCHMARK = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["benchmark"]
FORECAST_POLICY = GLOBAL_EVENT_V2_PROTOCOL["forecast"]
_THEME, _QUERY = next(
    (theme, query)
    for theme, queries in GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES.items()
    for query in queries
)


def _selection(rows, cutoff):
    selection = evidence_selection_manifest(rows, as_of_utc=cutoff)
    lineage = [
        {
            "evidence_id": evidence_id(row),
            "raw_content_id": raw_content_id(row),
            "fetch_run_ids": ["fetch_" + "f" * 24],
        }
        for row in rows
        if row.get("source") == "x"
    ]
    policy, period_key, accepted_cycles = _accepted_cycles(
        datetime.fromtimestamp(float(cutoff), timezone.utc)
    )
    primary = _cycle_summary(accepted_cycles[0])
    selected = primary if lineage else None
    payload = {
        "schema_version": 2,
        "policy": policy,
        "period_key": period_key,
        "expected_collection_cycle_id": primary["collection_cycle_id"],
        "primary_collection_cycle_id": primary["collection_cycle_id"],
        "accepted_collection_cycles": [
            _cycle_summary(candidate) for candidate in accepted_cycles
        ],
        "selected_collection_cycle": selected,
        "state": "complete_with_eligible" if lineage else "missing",
        "collection_cycle_id": primary["collection_cycle_id"] if lineage else None,
        "manifest_id": "cycle_manifest_" + "c" * 24 if lineage else None,
        "cycle_manifest": {"schema_version": 2} if lineage else None,
        "collector_semantics_id": primary["collector_semantics_id"],
        "collector_build_id": "build_" + "b" * 24 if lineage else None,
        "server_started_utc": cutoff - 2 if lineage else None,
        "server_terminal_utc": cutoff - 1 if lineage else None,
        "eligible_lineage": lineage,
    }
    availability = {
        "availability_id": content_id(payload, prefix="xavail_"),
        **payload,
    }
    return bind_x_availability_to_selection(selection, availability)


def _coverage(_selection_manifest):
    return {"complete": True, "missing_query_slots": []}


def _row(*, fetched_utc: float = 100.0):
    if fetched_utc == 100.0:
        fetched_utc = datetime(2026, 1, 6, 13, tzinfo=timezone.utc).timestamp()
    return {
        "source": "globalnews",
        "external_id": "story-1",
        "ticker": "@WORLD",
        "created_utc": datetime(2026, 1, 6, 12, tzinfo=timezone.utc).timestamp(),
        "fetched_utc": fetched_utc,
        "author": "Reuters",
        "title": "A global event changes risk expectations",
        "body": "Independent editorial evidence.",
        "labels": ["@WORLD", global_news_query_slot_label(_THEME, _QUERY)],
        "metadata": {
            "article_url": "https://news.google.com/articles/story-1",
            "publisher_domain": "reuters.com",
        },
    }


def _x_row():
    return {
        "source": "x",
        "external_id": "reaction-1",
        "ticker": "@TREND_WORLD",
        "created_utc": datetime(2026, 1, 6, 14, tzinfo=timezone.utc).timestamp(),
        "fetched_utc": datetime(2026, 1, 6, 15, tzinfo=timezone.utc).timestamp(),
        "author": "public-user",
        "title": None,
        "body": "Public reaction to the global event.",
        "labels": ["@TREND_WORLD"],
        "metadata": {
            "evidence_role": "unverified_public_reaction",
            "author_id": "123456789",
            "account_created_utc": 1.0,
            "automation_signals_complete": True,
            "verified_type": "none",
            "automation_risk": 0.0,
            "engagement": {
                "like_count": 1,
                "reply_count": 0,
                "retweet_count": 0,
                "quote_count": 0,
            },
            "author_metrics": {
                "followers_count": 100,
                "following_count": 50,
                "tweet_count": 500,
            },
        },
    }


def _snapshot_for_dates(decision_dates):
    return build_snapshot(
        run_id="offline-run-1",
        decision_dates=decision_dates,
        universe=UNIVERSE,
        sectors=SECTORS,
        evidence_loader=lambda _decision_date: [_row()],
        selection_builder=_selection,
        coverage_builder=_coverage,
    )


def _snapshot():
    return _snapshot_for_dates((date(2026, 1, 7), date(2026, 1, 8)))


def _checkpoint(**overrides):
    values = {
        "checkpoint_id": "openai:gpt-5.4-mini-frozen-declaration",
        "provider": FORECAST_POLICY["provider"],
        "requested_model": FORECAST_POLICY["requested_model"],
        "available_at": datetime(2025, 12, 1, tzinfo=timezone.utc),
        "knowledge_cutoff": datetime(2025, 11, 1, tzinfo=timezone.utc),
        "accepted_returned_models": (FORECAST_POLICY["requested_model"],),
        "tools_enabled": False,
    }
    values.update(overrides)
    return ModelCheckpointSpec(**values)


class FakeForecastModel:
    def __init__(self):
        self.calls = []

    def forecast(self, *, checkpoint, decision_date, raw_evidence, universe):
        self.calls.append((decision_date, tuple(row["external_id"] for row in raw_evidence)))
        evidence = prepare_evidence(list(raw_evidence))
        prompt = build_forecast_prompt(
            decision_date=decision_date,
            evidence=evidence,
            universe=list(universe),
        )
        response_metadata = {"model_name": checkpoint.requested_model}
        cited = evidence[0]
        return {
            "input_bundle_id": content_id(
                {
                    "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                    "decision_date": decision_date,
                    "universe": list(universe),
                    "evidence": evidence,
                },
                prefix="input_",
            ),
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "model_id": model_identity(
                checkpoint.provider, checkpoint.requested_model, response_metadata
            ),
            "provider": checkpoint.provider,
            "requested_model": checkpoint.requested_model,
            "response_id": f"response-{decision_date}",
            "response_metadata": response_metadata,
            "usage_metadata": {"output_tokens": 100},
            "raw_response": {"id": f"response-{decision_date}"},
            "prompt": prompt,
            "evidence": evidence,
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_weights_sha256": checkpoint.weights_sha256,
            "forecast": {
                "horizon": "next-open-to-open",
                "market_regime": "fixture",
                "events": [
                    {
                        "event_id": "event_1",
                        "summary": "Fixture event",
                        "onset_utc": None,
                        "geographies": [],
                        "entities": [],
                        "transmission_mechanism": "Fixture transmission",
                        "novelty": 0.5,
                        "uncertainty": 0.5,
                        "evidence_ids": [cited["evidence_id"]],
                        "independent_source_count": 1,
                        "source_types": [cited["source"]],
                        "public_reaction": None,
                    }
                ],
                "forecasts": [
                    (
                        {
                            "ticker": symbol,
                            "expected_excess_return_bps": 100.0,
                            "probability_positive": 0.7,
                            "confidence": 1.0,
                            "abstain": False,
                            "event_ids": ["event_1"],
                            "rationale": "fixture edge",
                        }
                        if symbol == "AAPL"
                        else {
                            "ticker": symbol,
                            "expected_excess_return_bps": 0.0,
                            "probability_positive": 0.5,
                            "confidence": 0.0,
                            "abstain": True,
                            "event_ids": [],
                            "rationale": "fixture abstention",
                        }
                    )
                    for symbol in universe
                ],
            },
        }


class FakeOutcomeProvider:
    provider_name = "fixed-label-fixture"

    def __init__(self):
        self.calls = []

    def observe(self, *, decision_date, universe, benchmark):
        self.calls.append((decision_date, tuple(universe), benchmark))
        return OutcomeObservation(
            provider=self.provider_name,
            observed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            vintage_id="fixture-vintage-1",
            raw_payload_sha256="b" * 64,
            entry_date=decision_date + timedelta(days=1),
            exit_date=decision_date + timedelta(days=2),
            asset_returns={
                symbol: 0.02 if symbol == "AAPL" else -0.01 if symbol == "MSFT" else 0.0
                for symbol in universe
            },
            benchmark_return=0.005,
            cash_return=0.0,
            provenance={"provider": self.provider_name, "fixture": True},
        )


class MissingMiddleOutcomeProvider(FakeOutcomeProvider):
    def observe(self, *, decision_date, universe, benchmark):
        observation = super().observe(
            decision_date=decision_date,
            universe=universe,
            benchmark=benchmark,
        )
        if decision_date == date(2026, 1, 8):
            return observation.model_copy(
                update={
                    "asset_returns": {**observation.asset_returns, "AAPL": None}
                }
            )
        return observation


class InvalidHorizonOutcomeProvider(FakeOutcomeProvider):
    def observe(self, *, decision_date, universe, benchmark):
        observation = super().observe(
            decision_date=decision_date,
            universe=universe,
            benchmark=benchmark,
        )
        return observation.model_copy(
            update={
                "entry_date": decision_date,
                "exit_date": decision_date + timedelta(days=1),
            }
        )


class UngroundedForecastModel(FakeForecastModel):
    def forecast(self, **kwargs):
        bundle = super().forecast(**kwargs)
        bundle["forecast"]["forecasts"][0]["event_ids"] = []
        return bundle


@pytest.mark.unit
def test_complete_pipeline_commits_each_capability_boundary(tmp_path, monkeypatch):
    hac_inputs = []

    def capture_hac(values):
        hac_inputs.append(tuple(values))
        return {"observations": len(values), "captured": True}

    monkeypatch.setattr(
        "tradingagents.research.evaluate.newey_west_mean_test", capture_hac
    )
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    model = FakeForecastModel()

    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=model,
    )
    decisions = parse_contract(DecisionBatch, store.load("decisions", decision_ref.artifact_id))
    assert len(model.calls) == 2
    assert [row.status for row in decisions.decisions] == ["success", "success"]
    assert all(row.target_weights["AAPL"] > 0 for row in decisions.decisions)
    assert decisions.snapshot_payload_sha256 == snapshot_ref.payload_sha256

    provider = FakeOutcomeProvider()
    label_ref = label_from_artifact(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        provider=provider,
    )
    labels = parse_contract(OutcomeBatch, store.load("labels", label_ref.artifact_id))
    assert len(provider.calls) == 2
    assert labels.decision_payload_sha256 == decision_ref.payload_sha256
    assert [row.status for row in labels.outcomes] == ["complete", "complete"]

    evaluation_ref = evaluate_from_artifacts(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        label_artifact_id=label_ref.artifact_id,
    )
    report = parse_contract(
        EvaluationReport, store.load("evaluation", evaluation_ref.artifact_id)
    )
    assert report.intervals_completed == 2
    assert report.intervals_missing == 0
    assert report.total_return is not None
    assert report.total_turnover is not None
    assert report.decision_artifact_id == decision_ref.artifact_id
    assert report.outcome_artifact_id == label_ref.artifact_id
    first, second = report.interval_returns
    assert second["planned_target_turnover"] == pytest.approx(0.0)
    assert second["realized_entry_turnover"] > 0.0
    assert report.total_turnover == pytest.approx(
        first["realized_entry_turnover"] + second["realized_entry_turnover"]
    )
    assert hac_inputs == [
        tuple(row["excess_return"] for row in report.interval_returns)
    ]
    assert hac_inputs[0] != tuple(
        row["strategy_return"] for row in report.interval_returns
    )
    assert report.diagnostics["newey_west_excess_mean"]["captured"] is True


@pytest.mark.unit
def test_missing_label_blocks_the_remaining_path_and_all_total_metrics(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(
        store,
        _snapshot_for_dates(
            (date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9))
        ),
    )
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    label_ref = label_from_artifact(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        provider=MissingMiddleOutcomeProvider(),
    )

    evaluation_ref = evaluate_from_artifacts(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        label_artifact_id=label_ref.artifact_id,
    )
    report = parse_contract(
        EvaluationReport, store.load("evaluation", evaluation_ref.artifact_id)
    )

    assert report.intervals_completed == 1
    assert report.intervals_missing == 2
    assert [row["status"] for row in report.interval_returns] == [
        "complete",
        "missing_label",
        "blocked_by_missing_predecessor",
    ]
    assert report.total_return is None
    assert report.benchmark_return is None
    assert report.excess_return is None
    assert report.max_drawdown is None
    assert report.mean_interval_return is None
    assert report.total_turnover is None
    assert report.diagnostics["accounting_complete"] is False
    assert report.diagnostics["observed_prefix_intervals"] == 1
    assert report.diagnostics["newey_west_excess_mean"] is None


@pytest.mark.unit
def test_evaluation_rejects_a_different_benchmark(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    label_ref = label_from_artifact(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        provider=FakeOutcomeProvider(),
    )
    decisions = parse_contract(
        DecisionBatch, store.load("decisions", decision_ref.artifact_id)
    )
    labels = parse_contract(OutcomeBatch, store.load("labels", label_ref.artifact_id))

    altered = labels.model_copy(update={"benchmark": "QQQ"})
    altered_ref = store.commit("labels", altered.model_dump(mode="json"))
    with pytest.raises(ValueError, match="different experiments"):
        evaluate(
            decisions=decisions,
            decision_ref=decision_ref,
            labels=altered,
            label_ref=altered_ref,
        )


@pytest.mark.unit
def test_application_rejects_adapter_that_bypasses_grounding(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=UngroundedForecastModel(),
    )
    decisions = parse_contract(
        DecisionBatch, store.load("decisions", decision_ref.artifact_id)
    )

    assert [row.status for row in decisions.decisions] == ["failed", "failed"]
    assert all(row.error_type == "ValueError" for row in decisions.decisions)
    assert all(row.forecast_bundle is None for row in decisions.decisions)


@pytest.mark.unit
def test_public_phase_functions_reject_mismatched_objects_and_refs(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot = _snapshot()
    snapshot_ref = commit_snapshot(store, snapshot)
    altered_snapshot = snapshot.model_copy(update={"run_id": "different-run"})

    with pytest.raises(ArtifactIntegrityError, match="does not match"):
        generate_decisions(
            snapshot=altered_snapshot,
            snapshot_ref=snapshot_ref,
            checkpoint=_checkpoint(),
            model=FakeForecastModel(),
        )

    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    decisions = parse_contract(
        DecisionBatch, store.load("decisions", decision_ref.artifact_id)
    )
    altered_decisions = decisions.model_copy(update={"run_id": "different-run"})
    with pytest.raises(ArtifactIntegrityError, match="does not match"):
        attach_labels(
            decisions=altered_decisions,
            decision_ref=decision_ref,
            provider=FakeOutcomeProvider(),
        )


@pytest.mark.unit
def test_invalid_outcome_horizon_becomes_explicit_missing_label(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    label_ref = label_from_artifact(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        provider=InvalidHorizonOutcomeProvider(),
    )
    labels = parse_contract(OutcomeBatch, store.load("labels", label_ref.artifact_id))

    assert [row.status for row in labels.outcomes] == ["missing", "missing"]
    assert all(row.error_type == "ValueError" for row in labels.outcomes)
    assert all(row.observation.entry_date is None for row in labels.outcomes)


@pytest.mark.unit
def test_future_checkpoint_is_rejected_before_any_model_call(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    model = FakeForecastModel()
    future = _checkpoint(
        available_at=datetime(2026, 1, 11, tzinfo=timezone.utc),
        knowledge_cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="checkpoint must be available before"):
        decide_from_artifact(
            artifact_store=store,
            snapshot_artifact_id=snapshot_ref.artifact_id,
            checkpoint=future,
            model=model,
        )

    assert model.calls == []
    assert not (tmp_path / "decisions").exists()


@pytest.mark.unit
def test_snapshot_rejects_evidence_observed_at_the_cutoff():
    cutoff = datetime(2026, 1, 11, tzinfo=timezone.utc).timestamp()

    with pytest.raises(ValueError, match="strictly before cutoff"):
        build_snapshot(
            run_id="future-row",
            decision_dates=(date(2026, 1, 10),),
            universe=("AAPL",),
            sectors={"AAPL": "technology"},
            evidence_loader=lambda _date: [_row(fetched_utc=cutoff)],
            selection_builder=_selection,
            coverage_builder=_coverage,
        )


@pytest.mark.unit
def test_snapshot_rejects_evidence_published_at_the_cutoff():
    cutoff = datetime(2026, 1, 11, tzinfo=timezone.utc).timestamp()
    row = {**_row(), "created_utc": cutoff}

    with pytest.raises(ValueError, match="published strictly before cutoff"):
        build_snapshot(
            run_id="future-published-row",
            decision_dates=(date(2026, 1, 10),),
            universe=("AAPL",),
            sectors={"AAPL": "technology"},
            evidence_loader=lambda _date: [row],
            selection_builder=_selection,
            coverage_builder=_coverage,
        )


@pytest.mark.unit
def test_media_snapshot_rejects_non_xnys_decision_dates_before_database_access(
    monkeypatch,
):
    monkeypatch.setattr(
        "tradingagents.dataflows.media_store.open_store",
        lambda *_args, **_kwargs: pytest.fail("invalid dates must fail before DB access"),
    )

    with pytest.raises(ValueError, match="must be XNYS sessions"):
        build_media_snapshot(
            db_url="postgresql://unused",
            run_id="weekend",
            decision_dates=(date(2026, 1, 10),),
        )


@pytest.mark.unit
def test_receipt_coverage_cannot_be_masked_by_selection_coverage(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.research.snapshot.bind_receipt_coverage_to_selection",
        lambda receipt, _selection: {**receipt, "complete": receipt["complete"]},
    )
    snapshot = build_snapshot(
        run_id="partial-collection",
        decision_dates=(date(2026, 1, 10),),
        universe=("AAPL",),
        sectors={"AAPL": "technology"},
        evidence_loader=lambda _date: [_row()],
        selection_builder=_selection,
        coverage_builder=_coverage,
        receipt_coverage_loader=lambda _date, _cutoff, _selection: {
            "complete": False,
            "missing_query_slots": [{"provider": "globalnews", "query_key": "missing"}],
        },
    )

    assert snapshot.slices[0].coverage["selection_coverage"]["complete"] is True
    assert snapshot.slices[0].coverage["receipt_coverage"]["complete"] is False
    assert snapshot.slices[0].coverage["complete"] is False


@pytest.mark.unit
def test_x_ablation_reuses_snapshot_but_never_sends_x_to_model(tmp_path):
    snapshot = build_snapshot(
        run_id="ablation-run",
        decision_dates=(date(2026, 1, 7),),
        universe=UNIVERSE,
        sectors=SECTORS,
        evidence_loader=lambda _date: [_row(), _x_row()],
        selection_builder=_selection,
        coverage_builder=_coverage,
    )
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, snapshot)
    champion = FakeForecastModel()
    ablation = FakeForecastModel()

    champion_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=champion,
        arm="global_events",
    )
    ablation_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=ablation,
        arm="without_public_reaction",
    )

    assert champion_ref.artifact_id != ablation_ref.artifact_id
    assert champion.calls[0][1] == ("reaction-1", "story-1")
    assert ablation.calls[0][1] == ("story-1",)
    champion_batch = parse_contract(
        DecisionBatch, store.load("decisions", champion_ref.artifact_id)
    )
    ablation_batch = parse_contract(
        DecisionBatch, store.load("decisions", ablation_ref.artifact_id)
    )
    assert champion_batch.snapshot_artifact_id == ablation_batch.snapshot_artifact_id
    assert champion_batch.arm == "global_events"
    assert ablation_batch.arm == "without_public_reaction"


@pytest.mark.unit
def test_artifact_commit_is_idempotent_and_detects_tampering(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    first = store.commit("snapshot", {"schema_version": 1, "value": "original"})
    assert store.commit("snapshot", {"schema_version": 1, "value": "original"}) == first
    payload_path = tmp_path / "snapshot" / first.artifact_id / "payload.json"
    payload_path.write_text(
        json.dumps({"schema_version": 1, "value": "tampered"}, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ArtifactIntegrityError, match="modified"):
        store.load("snapshot", first.artifact_id)


@pytest.mark.unit
def test_label_refuses_an_uncommitted_decision_identifier(tmp_path):
    with pytest.raises(ArtifactIntegrityError, match="commit marker"):
        label_from_artifact(
            artifact_store=FilesystemArtifactStore(tmp_path),
            decision_artifact_id="decisions_" + "0" * 24,
            provider=FakeOutcomeProvider(),
        )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


@pytest.mark.unit
def test_decision_and_label_modules_have_disjoint_capabilities():
    package = Path(__file__).parents[1] / "tradingagents" / "research"
    decision_imports = _imported_modules(package / "decide.py")
    label_imports = _imported_modules(package / "label.py")

    assert "tradingagents.research.outcomes" not in decision_imports
    assert "tradingagents.research.model" not in label_imports
    assert all("yfinance" not in module for module in decision_imports)
    assert all("llm" not in module for module in label_imports)
