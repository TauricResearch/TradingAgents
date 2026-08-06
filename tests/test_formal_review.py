"""Final-gate publication is automated, immutable, and access-labeled."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from tradingagents import formal_review
from tradingagents.formal_readout import FormalReadoutIntegrityError
from tradingagents.outcome_semantics import (
    OutcomeSemanticsResolutionError,
    outcome_semantics_id,
)
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)

VERIFICATION = {
    "verification_manifest_id": "formal_verification_" + "1" * 24,
    "verification_manifest_artifact_id": "artifact_" + "2" * 24,
}
OUTCOME_SEMANTICS_ID = outcome_semantics_id()


class _Store:
    def __init__(self, intervals=252):
        self.config = {"outcome_semantics_id": OUTCOME_SEMANTICS_ID}
        self.registration = {
            "label": "confirmatory-trial",
            "created_utc": 1.0,
            "details": {"outcome_semantics_id": OUTCOME_SEMANTICS_ID},
        }
        self.counts = {
            "completed_intervals": intervals,
            "assignment_indices_contiguous": True,
            "assignment_dates_contiguous": True,
        }
        self.artifacts = {}
        self.labels = {}
        self.events = []

    def run_config(self, run_id):
        assert run_id == "run-1"
        return deepcopy(self.config)

    def confirmatory_registration(self, run_id):
        assert run_id == "run-1"
        return deepcopy(self.registration)

    def formal_trial_counts(self, run_id):
        assert run_id == "run-1"
        return dict(self.counts)

    def price_capture_operational_manifest(self, run_id):
        assert run_id == "run-1"
        return {"attempt_events": [], "batches": [], "terminal_failures": []}

    def record_artifact(self, artifact_type, content, created_utc):
        artifact_id = content_id(
            {"artifact_type": artifact_type, "content": content},
            prefix="artifact_",
        )
        if artifact_id in self.artifacts:
            return artifact_id
        self.events.append(("artifact", artifact_type))
        self.artifacts[artifact_id] = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "content_json": canonical_json(content),
            "created_utc": created_utc,
        }
        return artifact_id

    def label_run(self, run_id, label, created_utc, details):
        assert run_id == "run-1"
        self.events.append(("label", label))
        encoded = canonical_json(details)
        if label in self.labels:
            if self.labels[label] != encoded:
                raise ValueError("different label")
            return False
        self.labels[label] = encoded
        return True

    def _rows(self, sql, params):
        if "FROM paper_run_labels" in sql:
            if "label=:label" in sql:
                encoded = self.labels.get(params["label"])
                return [{"details_json": encoded}] if encoded is not None else []
            return [
                {"label": label, "details_json": details}
                for label, details in sorted(self.labels.items())
            ]
        if "FROM paper_artifacts" in sql:
            if "artifact_id=:artifact_id" in sql:
                row = self.artifacts.get(params["artifact_id"])
                return [dict(row)] if row is not None else []
            return [dict(row) for row in self.artifacts.values()]
        raise AssertionError(sql)


class _OutcomeSemanticsGuardStore(_Store):
    def __init__(self, mutation: str):
        super().__init__()
        self.outcome_reads = 0
        if mutation == "missing":
            self.config.pop("outcome_semantics_id")
        elif mutation == "installed_drift":
            drifted = "outcome_semantics_" + "0" * 64
            self.config["outcome_semantics_id"] = drifted
            self.registration["details"]["outcome_semantics_id"] = drifted
        else:
            raise AssertionError(mutation)

    def formal_trial_counts(self, run_id):
        self.outcome_reads += 1
        return super().formal_trial_counts(run_id)

    def price_capture_operational_manifest(self, run_id):
        self.outcome_reads += 1
        return super().price_capture_operational_manifest(run_id)

    def _rows(self, sql, params):
        self.outcome_reads += 1
        return super()._rows(sql, params)


@pytest.mark.unit
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda store: formal_review.materialize_final_formal_review(
                store,
                "run-1",
                100.0,
            ),
            id="materialize",
        ),
        pytest.param(
            lambda store: formal_review.load_final_formal_report(
                store,
                "run-1",
                100.0,
            ),
            id="load",
        ),
    ],
)
@pytest.mark.parametrize(
    ("mutation", "error", "message"),
    [
        ("missing", FormalReadoutIntegrityError, "disagree on outcome semantics"),
        (
            "installed_drift",
            OutcomeSemanticsResolutionError,
            "differ from preregistration",
        ),
    ],
)
def test_public_review_paths_reject_outcome_semantics_before_outcome_reads(
    operation,
    mutation,
    error,
    message,
):
    store = _OutcomeSemanticsGuardStore(mutation)

    with pytest.raises(error, match=message):
        operation(store)

    assert store.outcome_reads == 0
    assert store.events == []


def _result():
    outcome = {
        "schema_version": 1,
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": "run-1",
        "strategy_returns": {"champion": [0.01]},
        **VERIFICATION,
    }
    outcome_id = content_id(outcome, prefix="outcome_bundle_")
    report_base = {
        "schema_version": 1,
        "report_type": "global-event-v2-sole-confirmatory-readout",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "run_id": "run-1",
        "registration_id": "registration_1",
        "review_gate": 252,
        "interim": False,
        "outcome_bundle_id": outcome_id,
        **VERIFICATION,
        "readout": {
            "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
            "paired_intervals": 252,
            "machine_statistical_candidate": False,
            "live_capital_approved": False,
        },
    }
    return {
        **report_base,
        "report_id": content_id(report_base, prefix="formal_report_"),
        "outcome_bundle": outcome,
    }


@pytest.fixture(autouse=True)
def _verified_manifest(monkeypatch):
    monkeypatch.setattr(
        formal_review,
        "materialize_final_verification_manifest",
        lambda *_args: dict(VERIFICATION),
    )
    monkeypatch.setattr(
        formal_review,
        "require_final_verification_manifest",
        lambda *_args: dict(VERIFICATION),
    )


@pytest.mark.unit
def test_final_review_refuses_early_access_without_writing(monkeypatch):
    store = _Store(intervals=251)
    monkeypatch.setattr(
        formal_review,
        "build_formal_readout",
        lambda *_args: pytest.fail("early review reached outcomes"),
    )

    with pytest.raises(ValueError, match="exactly 252"):
        formal_review.materialize_final_formal_review(store, "run-1", 100.0)

    assert store.events == []


@pytest.mark.unit
def test_materialization_labels_access_before_read_and_is_idempotent(monkeypatch):
    store = _Store()

    def build(_store, run_id):
        assert run_id == "run-1"
        assert store.events == [("artifact", "formal_outcome_access")]
        return _result()

    monkeypatch.setattr(formal_review, "build_formal_readout", build)
    first = formal_review.materialize_final_formal_review(store, "run-1", 100.0)

    assert first["already_materialized"] is False
    assert store.events == [
        ("artifact", "formal_outcome_access"),
        ("artifact", "formal_outcome_bundle"),
        ("artifact", "formal_confirmatory_report"),
        ("label", formal_review.FINAL_REVIEW_LABEL),
    ]
    second = formal_review.materialize_final_formal_review(store, "run-1", 101.0)
    assert second["already_materialized"] is True
    assert len(store.events) == 4


@pytest.mark.unit
def test_explicit_report_view_gets_a_separate_access_receipt(monkeypatch):
    store = _Store()
    monkeypatch.setattr(formal_review, "build_formal_readout", lambda *_: _result())
    formal_review.materialize_final_formal_review(store, "run-1", 100.0)

    report = formal_review.load_final_formal_report(store, "run-1", 200.0)

    assert report["review_gate"] == 252
    assert report["interim"] is False
    assert report["readout"]["live_capital_approved"] is False
    assert store.events[-1] == ("artifact", "formal_outcome_access")
    access_rows = [
        json.loads(row["content_json"])
        for row in store.artifacts.values()
        if row["artifact_type"] == "formal_outcome_access"
    ]
    assert {row["access_kind"] for row in access_rows} == {
        "automatic_final_report_materialization",
        "explicit_final_report_view",
    }


@pytest.mark.unit
def test_report_artifact_tampering_fails_closed(monkeypatch):
    store = _Store()
    monkeypatch.setattr(formal_review, "build_formal_readout", lambda *_: _result())
    details = formal_review.materialize_final_formal_review(store, "run-1", 100.0)
    store.artifacts[details["report_artifact_id"]]["content_json"] = json.dumps({
        "report_id": details["report_id"],
        "readout": {"live_capital_approved": True},
    })

    with pytest.raises(ValueError, match="content validation"):
        formal_review.load_final_formal_report(store, "run-1", 200.0)


@pytest.mark.unit
def test_offline_verification_completes_before_outcome_access_and_build(monkeypatch):
    store = _Store()

    def verify_manifest(*_args):
        store.events.append(("verification", "complete"))
        return dict(VERIFICATION)

    def build(*_args):
        assert store.events == [
            ("verification", "complete"),
            ("artifact", "formal_outcome_access"),
        ]
        return _result()

    monkeypatch.setattr(
        formal_review, "materialize_final_verification_manifest", verify_manifest
    )
    monkeypatch.setattr(formal_review, "build_formal_readout", build)

    result = formal_review.materialize_final_formal_review(
        store, "run-1", 100.0
    )

    assert result["verification_manifest_id"] == VERIFICATION[
        "verification_manifest_id"
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "breach", ["gate126_access", "old_report", "custom_content", "label"]
)
def test_unauthorized_early_efficacy_evidence_blocks_final_materialization(
    monkeypatch, breach
):
    store = _Store()
    if breach == "gate126_access":
        store.record_artifact(
            "formal_outcome_access",
            {
                "schema_version": 1,
                "run_id": "run-1",
                "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
                "review_gate": 126,
                "access_kind": "automatic_interim_126_materialization",
                "accessed_utc": 90.0,
                "outcomes_may_be_read_after_this_receipt": True,
            },
            90.0,
        )
    elif breach == "old_report":
        store.record_artifact(
            "formal_interim_descriptive_report",
            {
                "schema_version": 1,
                "run_id": "run-1",
                "strategy_descriptives": [{"strategy_id": "champion", "return": 1.0}],
            },
            90.0,
        )
    elif breach == "custom_content":
        store.record_artifact(
            "research_note",
            {
                "run_id": "run-1",
                "strategy_returns": {"champion": [0.1]},
            },
            90.0,
        )
    else:
        store.labels["formal-review-100-efficacy"] = canonical_json({
            "run_id": "run-1"
        })
    monkeypatch.setattr(
        formal_review,
        "build_formal_readout",
        lambda *_args: pytest.fail("governance breach reached outcomes"),
    )

    with pytest.raises(ValueError, match="unauthorized early"):
        formal_review.materialize_final_formal_review(store, "run-1", 100.0)
