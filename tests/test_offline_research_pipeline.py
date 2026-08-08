"""Focused guarantees for the capability-separated offline pipeline."""

from __future__ import annotations

import ast
import errno
import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tradingagents import poller
from tradingagents.domain.contracts import canonical_json
from tradingagents.evidence_lineage import evidence_id, raw_content_id
from tradingagents.global_research import (
    FORMAL_GLOBALNEWS_QUERY_SLOTS,
    build_forecast_prompt,
    evidence_selection_manifest,
    formal_globalnews_selection_coverage,
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
from tradingagents.research.errors import ForecastUnavailableError, OutcomeUnavailableError
from tradingagents.research.evaluate import evaluate, evaluate_from_artifacts
from tradingagents.research.label import attach_labels, label_from_artifact
from tradingagents.research.outcomes import YFinanceAdjustedOpenOutcomeProvider
from tradingagents.research.snapshot import (
    build_media_snapshot,
    build_snapshot,
    commit_snapshot,
)
from tradingagents.research.timeline import outcome_sessions
from tradingagents.research.x_availability import (
    _accepted_cycles,
    _cycle_summary,
    bind_x_availability_to_selection,
    project_x_cycle_availability,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_BROAD_NEWS_QUERIES,
    GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
    GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
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


def _x_cycle_store(rows, cutoff):
    policy, period_key, accepted_cycles = _accepted_cycles(
        datetime.fromtimestamp(float(cutoff), timezone.utc)
    )
    del policy
    spec = accepted_cycles[0]["spec"]
    period_start = datetime.fromisoformat(period_key).replace(
        tzinfo=timezone.utc
    ).timestamp()
    started, terminal = period_start + 3600.0, period_start + 7200.0
    max_topics = int(
        GLOBAL_EVENT_V2_PROTOCOL["evidence"]["max_x_search_requests_per_utc_day"]
    )
    headline = {
        "external_id": "discovery-headline",
        "title": "Bordeaux Wildfires Force Evacuations - Reuters",
        "created_utc": started - 60.0,
        "publisher": "Reuters",
        "category": "world",
        "region": "US",
        "rank": 0,
        "metadata": {"publisher_domain": "reuters.com"},
    }
    topics = poller._formally_grounded_discovery_topics(
        poller.discover_x_topics(
            max_topics=max_topics, headlines=[headline], trends=[]
        ),
        started,
    )
    requests = poller._group_x_search_topics(topics)
    decision = poller._x_discovery_decision_manifest(
        collection_cycle_id=spec["collection_cycle_id"],
        captured_utc=started,
        max_topics=max_topics,
        headlines=[headline],
        trends=[],
        topics=topics,
        search_requests=requests,
    )
    decision_row = poller.x_discovery_decision_row(decision)
    decision_fetch_id = "00000000-0000-4000-8000-000000000010"
    x_fetch_id = "00000000-0000-4000-8000-000000000020"
    x_row = next(row for row in rows if row.get("source") == "x")
    x_raw_id = raw_content_id(x_row)
    static_receipts = []
    for index, slot in enumerate(spec["identity"]["expected_static_slots"]):
        fetch_id = f"00000000-0000-4000-8000-{index + 1:012x}"
        is_decision = slot["provider"] == "trendnews"
        static_receipts.append({
            "slot_kind": "static",
            **slot,
            "fetch_run_id": decision_fetch_id if is_decision else fetch_id,
            "status": "success",
            "item_count": 1,
            "raw_content_ids": (
                [raw_content_id(decision_row)]
                if is_decision else [f"raw_{index + 1:024x}"]
            ),
        })
    dynamic_slots = [
        {"provider": "x", "query_key": request["query_key"]}
        for request in requests
    ]
    slot_receipts = static_receipts + [{
        "slot_kind": "dynamic",
        **dynamic_slots[0],
        "fetch_run_id": x_fetch_id,
        "status": "success",
        "item_count": 1,
        "raw_content_ids": [x_raw_id],
    }]
    manifest = {
        "schema_version": 2,
        "collection_cycle_id": spec["collection_cycle_id"],
        "cycle_kind": spec["identity"]["cycle_kind"],
        "period_key": spec["identity"]["period_key"],
        "protocol_id": spec["identity"]["protocol_id"],
        "collector_semantics_id": spec["identity"]["collector_semantics_id"],
        "started_utc": started,
        "completed_utc": terminal,
        "status": "complete",
        "expected_static_slots": spec["identity"]["expected_static_slots"],
        "expected_dynamic_slots": dynamic_slots,
        "slot_receipts": slot_receipts,
        "server_started_utc": started,
        "server_terminal_utc": terminal,
        "collector_build_id": "build_" + "b" * 24,
    }
    cycle = {
        **spec["identity"],
        "collection_cycle_id": spec["collection_cycle_id"],
        "identity": spec["identity"],
        "identity_valid": True,
        "started_utc": started,
        "completed_utc": terminal,
        "status": "complete",
        "manifest_valid": True,
        "manifest": manifest,
        "manifest_id": content_id(manifest, prefix="cycle_manifest_"),
        "collector_build_id": "build_" + "b" * 24,
        "server_started_utc": started,
        "server_terminal_utc": terminal,
    }

    class Store:
        def collection_cycle(self, cycle_id):
            return cycle if cycle_id == spec["collection_cycle_id"] else None

        def collection_cycle_formal_lineage(self, cycle_id, *, provider):
            assert cycle_id == spec["collection_cycle_id"] and provider == "x"
            return [{
                "fetch_run_id": x_fetch_id,
                "evidence_id": evidence_id(x_row),
                "raw_content_id": x_raw_id,
            }]

        def collection_cycle_item_rows(self, cycle_id, *, provider, query_key):
            assert cycle_id == spec["collection_cycle_id"]
            if provider == "trendnews":
                return [{
                    "fetch_run_id": decision_fetch_id,
                    "raw_content_id": raw_content_id(decision_row),
                    "row": decision_row,
                }]
            assert provider == "x" and query_key == dynamic_slots[0]["query_key"]
            return [{
                "fetch_run_id": x_fetch_id,
                "raw_content_id": x_raw_id,
                "row": {
                    **x_row,
                    "metadata": {
                        **x_row["metadata"],
                        "receipt_labels": requests[0]["labels"],
                    },
                    "latest_observed_utc": terminal,
                    "latest_observed_utc_source": "server_terminal_utc",
                },
            }]

    return Store()


def _selection(rows, cutoff):
    if any(row.get("source") == "x" for row in rows):
        availability, selected_rows = project_x_cycle_availability(
            _x_cycle_store(rows, cutoff),
            cutoff=datetime.fromtimestamp(float(cutoff), timezone.utc),
            candidate_rows=rows,
        )
    else:
        policy, period_key, accepted_cycles = _accepted_cycles(
            datetime.fromtimestamp(float(cutoff), timezone.utc)
        )
        primary = _cycle_summary(accepted_cycles[0])
        payload = {
            "schema_version": 2,
            "policy": policy,
            "period_key": period_key,
            "expected_collection_cycle_id": primary["collection_cycle_id"],
            "primary_collection_cycle_id": primary["collection_cycle_id"],
            "accepted_collection_cycles": [
                _cycle_summary(candidate) for candidate in accepted_cycles
            ],
            "selected_collection_cycle": None,
            "state": "missing",
            "collection_cycle_id": None,
            "manifest_id": None,
            "cycle_manifest": None,
            "collector_semantics_id": primary["collector_semantics_id"],
            "collector_build_id": None,
            "server_started_utc": None,
            "server_terminal_utc": None,
            "discovery_decision": None,
            "eligible_lineage": [],
        }
        availability = {
            "availability_id": content_id(payload, prefix="xavail_"),
            **payload,
        }
        selected_rows = rows
    selection = evidence_selection_manifest(selected_rows, as_of_utc=cutoff)
    return bind_x_availability_to_selection(selection, availability)


def _coverage(_selection_manifest):
    return formal_globalnews_selection_coverage(_selection_manifest)


def _receipt_coverage(_decision_date, _cutoff, selection):
    lineage_by_slot = {
        slot: sorted(
            (
                {
                    "evidence_id": candidate["evidence_id"],
                    "raw_content_id": candidate["raw_content_id"],
                }
                for candidate in selection["candidates"]
                if candidate.get("source") == "globalnews"
                and candidate.get("eligible") is True
                and candidate.get("query_slot") == slot
            ),
            key=lambda item: (item["evidence_id"], item["raw_content_id"]),
        )
        for slot in FORMAL_GLOBALNEWS_QUERY_SLOTS
    }
    receipt_metadata = json.dumps(
        {
            "protocol_id": GLOBAL_EVENT_V2_COLLECTION_PROTOCOL_ID,
            "collector_semantics_id": GLOBAL_EVENT_V2_COLLECTOR_SEMANTICS_ID,
        },
        separators=(",", ":"),
    )
    cutoff = _cutoff.timestamp()
    cycle = GLOBAL_EVENT_V2_PROTOCOL["evidence"]["query_cycle"]
    interval = int(cycle["collector_interval_seconds"])
    grace = int(cycle["cycle_start_grace_seconds"])
    lower_bound = cutoff - interval - grace
    runs = []
    for index, slot in enumerate(FORMAL_GLOBALNEWS_QUERY_SLOTS, start=1):
        lineage = lineage_by_slot[slot]
        evidence_ids = [item["evidence_id"] for item in lineage]
        started = lower_bound + index * 10.0
        item_count = max(1, len(evidence_ids))
        runs.append({
            "fetch_run_id": f"00000000-0000-4000-8000-{index:012x}",
            "provider": "globalnews",
            "query_key": slot,
            "started_utc": started,
            "received_utc": started + 1.0,
            "completed_utc": started + 2.0,
            "status": "success",
            "item_count": item_count,
            "inserted_count": item_count,
            "error": None,
            "formal_eligible_item_count": len(evidence_ids),
            "formal_eligible_evidence_ids_json": json.dumps(
                evidence_ids, separators=(",", ":")
            ),
            "formal_eligible_lineage_json": json.dumps(
                lineage, separators=(",", ":")
            ),
            "cost_units": 1.0,
            "cursor_before": None,
            "cursor_after": None,
            "metadata_json": receipt_metadata,
            "collection_cycle_id": None,
            "server_started_utc": started,
            "server_terminal_utc": started + 3.0,
            "collector_build_id": "build_" + "0" * 24,
            "formal_eligible_evidence_ids": evidence_ids,
            "formal_eligible_lineage": lineage,
        })
    return {
        "complete": True,
        "sources": {"globalnews": runs[-1]},
        "missing_source_groups": [],
        "missing_query_slots": [],
        "query_slots": [
            {
                "provider": "globalnews",
                "query_key": run["query_key"],
                "run": run,
                "allow_empty": False,
                "require_eligible": False,
                "require_lineage": True,
                "healthy": True,
                "reason": None,
            }
            for run in runs
        ],
        "cutoff_utc": cutoff,
        "collector_interval_seconds": interval,
        "cycle_start_grace_seconds": grace,
        "cycle_lower_bound_utc": lower_bound,
    }


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
        "created_utc": datetime(2026, 1, 7, 1, tzinfo=timezone.utc).timestamp(),
        "fetched_utc": datetime(2026, 1, 7, 1, 30, tzinfo=timezone.utc).timestamp(),
        "author": "public-user",
        "title": None,
        "body": "Public reaction to the global event.",
        "labels": ["@TREND_WORLD"],
        "latest_observed_utc": datetime(
            2026, 1, 7, 2, tzinfo=timezone.utc
        ).timestamp(),
        "latest_observed_utc_source": "server_terminal_utc",
        "metadata": {
            "evidence_role": "unverified_public_reaction",
            "author_id": "123456789",
            "account_created_utc": 1.0,
            "automation_signals_complete": True,
            "profile_screening_complete": True,
            "organization_signals": [],
            "verified_type": "none",
            "receipt_labels": ["@TREND_WORLD"],
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
        receipt_coverage_loader=_receipt_coverage,
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
    provider_name = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
        "exploratory_history_adapter"
    ]["provider_id"]

    def __init__(self):
        self.calls = []

    def observe(self, *, decision_date, universe, benchmark):
        self.calls.append((decision_date, tuple(universe), benchmark))
        entry_date, exit_date = outcome_sessions(decision_date)
        endpoint_dates = (entry_date.isoformat(), exit_date.isoformat())
        returns = {
            symbol: 0.02 if symbol == "AAPL" else -0.01 if symbol == "MSFT" else 0.0
            for symbol in universe
        }
        returns[benchmark] = 0.005
        endpoints = {
            symbol: [
                {"date": endpoint_dates[0], "adjusted_open": 100.0},
                {"date": endpoint_dates[1], "adjusted_open": 100.0 * (1.0 + value)},
            ]
            for symbol, value in returns.items()
        }
        observed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
        raw_hash = hashlib.sha256(canonical_json(endpoints).encode()).hexdigest()
        policy = GLOBAL_EVENT_V2_PROTOCOL["portfolio"]["price_capture"][
            "exploratory_history_adapter"
        ]
        return OutcomeObservation(
            provider=self.provider_name,
            observed_at=observed_at,
            vintage_id=f"yfinance:{observed_at.isoformat()}:{raw_hash[:16]}",
            raw_payload_sha256=raw_hash,
            entry_date=entry_date,
            exit_date=exit_date,
            asset_returns={
                symbol: returns[symbol]
                for symbol in universe
            },
            benchmark_return=returns[benchmark],
            cash_return=0.0,
            provenance={
                "schema_version": policy["provenance_schema_version"],
                "provider": self.provider_name,
                "price_semantics": policy["price_semantics"],
                "endpoints": endpoints,
            },
        )


class MissingMiddleOutcomeProvider(FakeOutcomeProvider):
    def observe(self, *, decision_date, universe, benchmark):
        observation = super().observe(
            decision_date=decision_date,
            universe=universe,
            benchmark=benchmark,
        )
        if decision_date == date(2026, 1, 8):
            endpoints = {
                **observation.provenance["endpoints"],
                "AAPL": None,
            }
            raw_hash = hashlib.sha256(canonical_json(endpoints).encode()).hexdigest()
            return observation.model_copy(
                update={
                    "asset_returns": {**observation.asset_returns, "AAPL": None},
                    "raw_payload_sha256": raw_hash,
                    "vintage_id": (
                        f"yfinance:{observation.observed_at.isoformat()}:{raw_hash[:16]}"
                    ),
                    "provenance": {**observation.provenance, "endpoints": endpoints},
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


class UnavailableForecastModel(FakeForecastModel):
    def forecast(self, **kwargs):
        self.calls.append(kwargs["decision_date"])
        raise ForecastUnavailableError("fixed provider failure")


class UnavailableOutcomeProvider(FakeOutcomeProvider):
    def observe(self, **_kwargs):
        raise OutcomeUnavailableError("fixed provider failure")


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
def test_application_fails_hard_when_adapter_bypasses_grounding(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())

    with pytest.raises(ValueError, match="grounded"):
        decide_from_artifact(
            artifact_store=store,
            snapshot_artifact_id=snapshot_ref.artifact_id,
            checkpoint=_checkpoint(),
            model=UngroundedForecastModel(),
        )


@pytest.mark.unit
def test_typed_forecast_unavailability_is_recorded_without_hiding_contract_bugs(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=UnavailableForecastModel(),
    )
    decisions = parse_contract(
        DecisionBatch, store.load("decisions", decision_ref.artifact_id)
    )

    assert [row.status for row in decisions.decisions] == ["failed", "failed"]
    assert all(row.error_type == "ForecastUnavailableError" for row in decisions.decisions)


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
def test_invalid_outcome_horizon_fails_hard_as_a_contract_violation(tmp_path):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    with pytest.raises(ValueError, match="does not replay"):
        label_from_artifact(
            artifact_store=store,
            decision_artifact_id=decision_ref.artifact_id,
            provider=InvalidHorizonOutcomeProvider(),
        )


@pytest.mark.unit
def test_typed_outcome_unavailability_becomes_an_explicit_missing_label(tmp_path):
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
        provider=UnavailableOutcomeProvider(),
    )
    labels = parse_contract(OutcomeBatch, store.load("labels", label_ref.artifact_id))

    assert [row.status for row in labels.outcomes] == ["missing", "missing"]
    assert all(row.error_type == "OutcomeUnavailableError" for row in labels.outcomes)


@pytest.mark.unit
def test_yfinance_outcome_adapter_normalizes_transport_failures(monkeypatch):
    from yfinance.exceptions import YFException

    secret = "https://prices.invalid/?token=must-not-escape"

    class FailedTicker:
        def history(self, **_kwargs):
            raise YFException(secret)

    monkeypatch.setattr("yfinance.Ticker", lambda _symbol: FailedTicker())

    with pytest.raises(OutcomeUnavailableError) as captured:
        YFinanceAdjustedOpenOutcomeProvider._endpoints("AAPL", date(2026, 1, 7))

    assert secret not in str(captured.value)


@pytest.mark.unit
def test_yfinance_outcome_adapter_does_not_hide_programming_errors(monkeypatch):
    class BuggyTicker:
        def history(self, **_kwargs):
            raise TypeError("adapter bug")

    monkeypatch.setattr("yfinance.Ticker", lambda _symbol: BuggyTicker())

    with pytest.raises(TypeError, match="adapter bug"):
        YFinanceAdjustedOpenOutcomeProvider._endpoints(
            "AAPL", date(2026, 1, 7)
        )


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
@pytest.mark.parametrize("coverage_variant", ["complete_only", "missing_binding"])
def test_decision_rejects_unbound_formal_coverage_before_model_call(
    tmp_path, coverage_variant
):
    snapshot = _snapshot_for_dates((date(2026, 1, 7),))
    valid_coverage = snapshot.slices[0].coverage
    coverage = (
        {"complete": True}
        if coverage_variant == "complete_only"
        else {
            key: value
            for key, value in valid_coverage.items()
            if key != "receipt_selection_binding"
        }
    )
    altered_slice = snapshot.slices[0].model_copy(update={"coverage": coverage})
    altered_snapshot = snapshot.model_copy(update={"slices": (altered_slice,)})
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, altered_snapshot)
    model = FakeForecastModel()

    with pytest.raises(ValueError):
        decide_from_artifact(
            artifact_store=store,
            snapshot_artifact_id=snapshot_ref.artifact_id,
            checkpoint=_checkpoint(),
            model=model,
        )

    assert model.calls == []
    assert not (tmp_path / "decisions").exists()


def _corrupt_receipt_coverage(coverage, variant):
    receipt = coverage["receipt_coverage"]
    if variant == "fake_healthy":
        receipt["query_slots"][-1]["run"].update(
            status="empty", item_count=0, inserted_count=0
        )
    elif variant == "missing_provenance":
        run = receipt["query_slots"][0]["run"]
        receipt["query_slots"][0]["run"] = {
            key: run[key]
            for key in (
                "formal_eligible_evidence_ids",
                "formal_eligible_lineage",
                "metadata_json",
            )
        }
    elif variant == "stale":
        run = receipt["sources"]["globalnews"]
        run["server_started_utc"] = receipt["cycle_lower_bound_utc"] - 2.0
        run["server_terminal_utc"] = receipt["cycle_lower_bound_utc"] - 1.0
    elif variant == "cutoff":
        receipt["query_slots"][0]["run"]["server_terminal_utc"] = receipt[
            "cutoff_utc"
        ]
    elif variant == "lower_bound":
        receipt["query_slots"][0]["run"]["server_started_utc"] = (
            receipt["cycle_lower_bound_utc"] - 1.0
        )
    elif variant == "wrapper":
        receipt["query_slots"][0]["provider"] = "x"
    elif variant == "flag":
        receipt["query_slots"][0]["allow_empty"] = True
    elif variant == "derived_summary":
        receipt["complete"] = False
    elif variant == "missing_summary":
        receipt["missing_query_slots"] = [{
            "provider": "globalnews",
            "query_key": receipt["query_slots"][0]["query_key"],
            "reason": "failed",
        }]
    elif variant == "counts":
        receipt["query_slots"][0]["run"]["inserted_count"] = 2
    elif variant == "client_time":
        run = receipt["query_slots"][0]["run"]
        run["received_utc"] = run["started_utc"] - 1.0
    elif variant == "build":
        receipt["query_slots"][0]["run"]["collector_build_id"] = "unknown"
    elif variant == "policy_decoration":
        receipt["collector_interval_seconds"] += 1
    elif variant == "lower_decoration":
        receipt["cycle_lower_bound_utc"] -= 1.0
    elif variant == "missing_core":
        receipt.pop("sources")
    else:  # pragma: no cover - local test helper guard
        raise AssertionError(f"unknown corruption: {variant}")


@pytest.mark.unit
@pytest.mark.parametrize(
    "variant",
    [
        "fake_healthy",
        "missing_provenance",
        "stale",
        "cutoff",
        "lower_bound",
        "wrapper",
        "flag",
        "derived_summary",
        "missing_summary",
        "counts",
        "client_time",
        "build",
        "policy_decoration",
        "lower_decoration",
        "missing_core",
    ],
)
def test_decision_replays_receipts_before_any_model_call(tmp_path, variant):
    snapshot = _snapshot_for_dates((date(2026, 1, 7),))
    coverage = deepcopy(snapshot.slices[0].coverage)
    _corrupt_receipt_coverage(coverage, variant)
    altered_slice = snapshot.slices[0].model_copy(update={"coverage": coverage})
    altered_snapshot = snapshot.model_copy(update={"slices": (altered_slice,)})
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, altered_snapshot)
    model = FakeForecastModel()

    with pytest.raises(ValueError, match="coverage|receipt"):
        decide_from_artifact(
            artifact_store=store,
            snapshot_artifact_id=snapshot_ref.artifact_id,
            checkpoint=_checkpoint(),
            model=model,
        )

    assert model.calls == []
    assert not (tmp_path / "decisions").exists()


@pytest.mark.unit
def test_snapshot_rejects_evidence_observed_at_the_cutoff():
    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp()

    with pytest.raises(ValueError, match="strictly before cutoff"):
        build_snapshot(
            run_id="future-row",
            decision_dates=(date(2026, 1, 9),),
            universe=("AAPL",),
            sectors={"AAPL": "technology"},
            evidence_loader=lambda _date: [_row(fetched_utc=cutoff)],
            selection_builder=_selection,
            coverage_builder=_coverage,
        )


@pytest.mark.unit
def test_snapshot_rejects_latest_receipt_observed_at_the_cutoff():
    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp()
    row = {**_row(), "latest_observed_utc": cutoff}

    with pytest.raises(ValueError, match="latest observation.*strictly before cutoff"):
        build_snapshot(
            run_id="future-latest-observation",
            decision_dates=(date(2026, 1, 9),),
            universe=("AAPL",),
            sectors={"AAPL": "technology"},
            evidence_loader=lambda _date: [row],
            selection_builder=_selection,
            coverage_builder=_coverage,
        )


@pytest.mark.unit
def test_snapshot_rejects_evidence_published_at_the_cutoff():
    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp()
    row = {**_row(), "created_utc": cutoff}

    with pytest.raises(ValueError, match="published strictly before cutoff"):
        build_snapshot(
            run_id="future-published-row",
            decision_dates=(date(2026, 1, 9),),
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
        decision_dates=(date(2026, 1, 9),),
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
def test_shifted_snapshot_cutoff_is_rejected_before_model_invocation(tmp_path):
    snapshot = _snapshot_for_dates((date(2026, 1, 7),))
    snapshot_slice = snapshot.slices[0]
    shifted = snapshot_slice.model_copy(
        update={"decision_cutoff": snapshot_slice.decision_cutoff + timedelta(seconds=1)}
    )
    altered = snapshot.model_copy(update={"slices": (shifted,)})
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, altered)
    model = FakeForecastModel()

    with pytest.raises(ValueError, match="cutoff differs"):
        decide_from_artifact(
            artifact_store=store,
            snapshot_artifact_id=snapshot_ref.artifact_id,
            checkpoint=_checkpoint(),
            model=model,
        )

    assert model.calls == []


@pytest.mark.unit
def test_skipped_decision_session_is_rejected_before_model_invocation(tmp_path):
    snapshot = _snapshot_for_dates(
        (date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9))
    )
    altered = snapshot.model_copy(
        update={"slices": (snapshot.slices[0], snapshot.slices[2])}
    )
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, altered)
    model = FakeForecastModel()

    with pytest.raises(ValueError, match="contiguous"):
        decide_from_artifact(
            artifact_store=store,
            snapshot_artifact_id=snapshot_ref.artifact_id,
            checkpoint=_checkpoint(),
            model=model,
        )

    assert model.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("corruption", ["weight", "allocator"])
def test_labeling_replays_decisions_before_requesting_prices(tmp_path, corruption):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    decisions = parse_contract(
        DecisionBatch, store.load("decisions", decision_ref.artifact_id)
    )
    if corruption == "weight":
        first = decisions.decisions[0]
        weights = dict(first.target_weights)
        delta = weights["AAPL"] / 2.0
        weights["AAPL"] -= delta
        forged_first = first.model_copy(
            update={
                "target_weights": weights,
                "cash_weight": first.cash_weight + delta,
            }
        )
        forged = decisions.model_copy(
            update={"decisions": (forged_first, *decisions.decisions[1:])}
        )
    else:
        forged = decisions.model_copy(
            update={
                "allocator": {
                    **decisions.allocator,
                    "max_weight": decisions.allocator["max_weight"] / 2.0,
                }
            }
        )
    forged_ref = store.commit("decisions", forged.model_dump(mode="json"))
    provider = FakeOutcomeProvider()

    with pytest.raises(ValueError, match="replay|allocator"):
        label_from_artifact(
            artifact_store=store,
            decision_artifact_id=forged_ref.artifact_id,
            provider=provider,
        )

    assert provider.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("corruption", ["return", "schema", "error_type"])
def test_evaluation_replays_outcome_provenance(tmp_path, corruption):
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot())
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )
    provider = (
        UnavailableOutcomeProvider()
        if corruption == "error_type"
        else FakeOutcomeProvider()
    )
    label_ref = label_from_artifact(
        artifact_store=store,
        decision_artifact_id=decision_ref.artifact_id,
        provider=provider,
    )
    payload = store.load("labels", label_ref.artifact_id)
    if corruption == "return":
        payload["outcomes"][0]["observation"]["asset_returns"]["AAPL"] += 0.01
    elif corruption == "schema":
        payload["outcomes"][0]["observation"]["provenance"]["schema_version"] = True
    else:
        payload["outcomes"][0]["error_type"] = "RuntimeError"
    forged_ref = store.commit("labels", payload)

    with pytest.raises(ValueError):
        evaluate_from_artifacts(
            artifact_store=store,
            decision_artifact_id=decision_ref.artifact_id,
            label_artifact_id=forged_ref.artifact_id,
        )


@pytest.mark.unit
def test_typed_price_failure_cannot_create_a_premature_missing_label(
    tmp_path, monkeypatch,
):
    class EarlyClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 8, 1, tzinfo=timezone.utc)

    monkeypatch.setattr("tradingagents.research.label.datetime", EarlyClock)
    store = FilesystemArtifactStore(tmp_path)
    snapshot_ref = commit_snapshot(store, _snapshot_for_dates((date(2026, 1, 7),)))
    decision_ref = decide_from_artifact(
        artifact_store=store,
        snapshot_artifact_id=snapshot_ref.artifact_id,
        checkpoint=_checkpoint(),
        model=FakeForecastModel(),
    )

    with pytest.raises(ValueError, match="before its scheduled mark"):
        label_from_artifact(
            artifact_store=store,
            decision_artifact_id=decision_ref.artifact_id,
            provider=UnavailableOutcomeProvider(),
        )


@pytest.mark.unit
def test_yfinance_adapter_never_shifts_across_a_missing_expected_session(monkeypatch):
    import pandas as pd

    class ShiftedHistoryTicker:
        def history(self, **_kwargs):
            return pd.DataFrame(
                {"Open": [101.0, 102.0]},
                index=pd.to_datetime(["2026-01-09", "2026-01-12"], utc=True),
            )

    monkeypatch.setattr("yfinance.Ticker", lambda _symbol: ShiftedHistoryTicker())

    assert YFinanceAdjustedOpenOutcomeProvider._endpoints(
        "AAPL", date(2026, 1, 7)
    ) is None


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
        receipt_coverage_loader=_receipt_coverage,
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
def test_artifact_commit_accepts_the_platform_existing_directory_race(
    tmp_path, monkeypatch,
):
    store = FilesystemArtifactStore(tmp_path)
    payload = {"schema_version": 1, "value": "shared"}
    reference = store.commit("snapshot", payload)
    final = tmp_path / "snapshot" / reference.artifact_id
    original_exists = Path.exists
    original_rename = Path.rename
    first_probe = True

    def raced_exists(path):
        nonlocal first_probe
        if path == final and first_probe:
            first_probe = False
            return False
        return original_exists(path)

    def raced_rename(path, target):
        if target == final:
            raise OSError(errno.ENOTEMPTY, "destination already committed")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "exists", raced_exists)
    monkeypatch.setattr(Path, "rename", raced_rename)

    assert store.commit("snapshot", payload) == reference
    assert not list((tmp_path / "snapshot").glob(".staging-*"))


@pytest.mark.unit
def test_artifact_commit_does_not_mask_unrelated_rename_failures(
    tmp_path, monkeypatch,
):
    store = FilesystemArtifactStore(tmp_path)
    payload = {"schema_version": 1, "value": "shared"}
    reference = store.commit("snapshot", payload)
    final = tmp_path / "snapshot" / reference.artifact_id
    original_exists = Path.exists
    first_probe = True

    def raced_exists(path):
        nonlocal first_probe
        if path == final and first_probe:
            first_probe = False
            return False
        return original_exists(path)

    def failed_rename(_path, _target):
        raise OSError(errno.EIO, "storage failure")

    monkeypatch.setattr(Path, "exists", raced_exists)
    monkeypatch.setattr(Path, "rename", failed_rename)

    with pytest.raises(OSError) as captured:
        store.commit("snapshot", payload)

    assert captured.value.errno == errno.EIO


@pytest.mark.unit
def test_artifact_load_returns_the_payload_from_its_single_validated_read(
    tmp_path, monkeypatch
):
    store = FilesystemArtifactStore(tmp_path)
    reference = store.commit("snapshot", {"schema_version": 1, "value": "original"})
    payload_path = tmp_path / "snapshot" / reference.artifact_id / "payload.json"
    original_read = Path.read_bytes
    reads = 0

    def counted_read(path):
        nonlocal reads
        if path == payload_path:
            reads += 1
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read)

    loaded_ref, payload = store.load_with_ref("snapshot", reference.artifact_id)

    assert loaded_ref == reference
    assert payload == {"schema_version": 1, "value": "original"}
    assert reads == 1


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
