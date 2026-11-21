"""Offline contract tests for :mod:`egta.contracts.manifest` (B confirmations).

Strict negatives (no xfail/skip). Tests encoding not-yet-implemented decisions are
expected RED (test-first). Definitions: docs/req/contracts-summary.md §3.

B confirmed: four variants mandatory; metrics_rubric typed MetricDef;
quality_rubric independent field; code_hash/policy_hash in v1; manifest_hash
(with the spec hash function); MISSING_USAGE PENDING (D).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from egta.contracts.manifest import ExperimentManifest, compute_manifest_hash

pytestmark = pytest.mark.spec

VALID_HASH = "a" * 64
CODE_HASH = "c" * 40  # a Git commit SHA (40 hex)

ALL_VARIANTS = {
    "B0": {"mode": "baseline"},
    "B1": {"mode": "enhanced"},
    "B2": {"mode": "ablation-1"},
    "B3": {"mode": "ablation-2", "budget_opt": False},  # B3 disables budget opt
}

_METRIC_DEF = {
    "metric": "token_cost",
    "operator": "lte",
    "threshold": 2.0,
    "verification": "pytest",
    "source": "budget",
    "aggregation": "median",
    "unit": "USD",
}

_VALID_QUALITY = {
    "levels": ["gold", "silver", "bronze"],
    "double_blind": True,
    "third_party_adjudication": True,
    "llm_judge_assist": False,
}


def _utc() -> datetime:
    return datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _manifest(**overrides) -> ExperimentManifest:
    base = {
        "manifest_id": "m1",
        "created_at": _utc(),
        "target_snapshot_id": "snap1",
        "model_config_hash": VALID_HASH,
        "prompt_hash": VALID_HASH,
        "code_hash": CODE_HASH,
        "policy_hash": VALID_HASH,
        "manifest_hash": VALID_HASH,
        "variants": {k: dict(v) for k, v in ALL_VARIANTS.items()},
        "metrics_rubric": {"token_cost": dict(_METRIC_DEF)},
        "quality_rubric": dict(_VALID_QUALITY),
    }
    base.update(overrides)
    return ExperimentManifest(**base)


# --- positive ----------------------------------------------------------------


def test_manifest_with_all_four_variants_constructs():
    m = _manifest()
    assert set(m.variants) == {"B0", "B1", "B2", "B3"}


def test_non_empty_b1_b2_b3_positive():
    m = _manifest()
    for name in ("B1", "B2", "B3"):
        assert m.variants[name]


def test_code_and_policy_hash_present():
    m = _manifest()
    assert m.code_hash == CODE_HASH
    assert m.policy_hash == VALID_HASH


def test_manifest_hash_present():
    assert _manifest().manifest_hash == VALID_HASH


# --- negative: required variants --------------------------------------------


@pytest.mark.parametrize("missing", ["B0", "B1", "B2", "B3"])
def test_missing_any_variant_rejected(missing):
    v = {k: val for k, val in ALL_VARIANTS.items() if k != missing}
    with pytest.raises(ValidationError):
        _manifest(variants=v)


@pytest.mark.parametrize("empty", ["B1", "B2", "B3"])
def test_empty_enhanced_variant_rejected(empty):
    v = {k: dict(val) for k, val in ALL_VARIANTS.items()}
    v[empty] = {}
    with pytest.raises(ValidationError):
        _manifest(variants=v)


def test_unknown_variant_key_rejected():
    v = {k: dict(val) for k, val in ALL_VARIANTS.items()}
    v["B9"] = {"mode": "bogus"}
    with pytest.raises(ValidationError):
        _manifest(variants=v)


def test_empty_b0_rejected():
    v = {k: dict(val) for k, val in ALL_VARIANTS.items()}
    v["B0"] = {}
    with pytest.raises(ValidationError):
        _manifest(variants=v)


# --- negative: hashes --------------------------------------------------------


@pytest.mark.parametrize("field", ["model_config_hash", "prompt_hash", "policy_hash"])
@pytest.mark.parametrize("bad", ["XYZ", "A" * 64, "a" * 63, ""])
def test_bad_64_hex_hash_rejected(field, bad):
    with pytest.raises(ValidationError):
        _manifest(**{field: bad})


@pytest.mark.parametrize("bad", ["XYZ", "c" * 39, ""])
def test_bad_code_hash_rejected(bad):
    with pytest.raises(ValidationError):
        _manifest(code_hash=bad)


# --- negative: timezone ------------------------------------------------------


def test_naive_created_at_rejected():
    with pytest.raises(ValidationError):
        _manifest(created_at=datetime(2026, 1, 2, 3, 4, 5))


# --- metrics_rubric: typed MetricDef ----------------------------------------


def test_empty_metrics_rubric_rejected():
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric={})


def test_non_dict_metrics_rubric_rejected():
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric=["not", "a", "mapping"])


@pytest.mark.parametrize(
    "field", ["metric", "operator", "threshold", "verification", "source",
              "aggregation", "unit"]
)
def test_metric_def_missing_required_field_rejected(field):
    entry = dict(_METRIC_DEF)
    entry.pop(field)
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric={"token_cost": entry})


def test_metric_def_illegal_operator_rejected():
    entry = dict(_METRIC_DEF)
    entry["operator"] = "approximately"
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric={"token_cost": entry})


def test_metric_def_non_numeric_threshold_rejected():
    entry = dict(_METRIC_DEF)
    entry["threshold"] = "two"
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric={"token_cost": entry})


def test_metric_def_empty_unit_rejected():
    entry = dict(_METRIC_DEF)
    entry["unit"] = ""
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric={"token_cost": entry})


def test_metric_def_extra_field_rejected():
    entry = dict(_METRIC_DEF)
    entry["bogus"] = 1
    with pytest.raises(ValidationError):
        _manifest(metrics_rubric={"token_cost": entry})


# --- quality_rubric: independent field --------------------------------------


def test_quality_rubric_positive():
    m = _manifest()
    assert len(m.quality_rubric.levels) >= 3


@pytest.mark.parametrize(
    "field", ["levels", "double_blind", "third_party_adjudication",
              "llm_judge_assist"]
)
def test_quality_rubric_missing_field_rejected(field):
    q = dict(_VALID_QUALITY)
    q.pop(field)
    with pytest.raises(ValidationError):
        _manifest(quality_rubric=q)


def test_quality_rubric_requires_three_levels():
    q = dict(_VALID_QUALITY)
    q["levels"] = ["only-one"]
    with pytest.raises(ValidationError):
        _manifest(quality_rubric=q)


@pytest.mark.parametrize("field", ["double_blind", "third_party_adjudication",
                                   "llm_judge_assist"])
def test_quality_rubric_illegal_bool_rejected(field):
    q = dict(_VALID_QUALITY)
    q[field] = "yes-please"
    with pytest.raises(ValidationError):
        _manifest(quality_rubric=q)


def test_quality_rubric_extra_field_rejected():
    q = dict(_VALID_QUALITY)
    q["bogus"] = True
    with pytest.raises(ValidationError):
        _manifest(quality_rubric=q)


# --- manifest_hash normalization (D item 2) ---------------------------------


def _build_with_hash(**overrides):
    """Construct a manifest whose manifest_hash is its own computed hash."""
    base = {
        "manifest_id": "m1", "created_at": _utc(), "target_snapshot_id": "snap1",
        "model_config_hash": VALID_HASH, "prompt_hash": VALID_HASH,
        "code_hash": CODE_HASH, "policy_hash": VALID_HASH, "manifest_hash": VALID_HASH,
        "variants": {k: dict(v) for k, v in ALL_VARIANTS.items()},
        "metrics_rubric": {"token_cost": dict(_METRIC_DEF)},
        "quality_rubric": dict(_VALID_QUALITY),
    }
    base.update(overrides)
    draft = ExperimentManifest(**base)
    return draft.model_copy(update={"manifest_hash": compute_manifest_hash(draft)})


def test_manifest_hash_is_deterministic():
    a = _build_with_hash()
    b = _build_with_hash()
    assert compute_manifest_hash(a) == compute_manifest_hash(b)


@pytest.mark.parametrize(
    "field, value",
    [
        ("target_snapshot_id", "snap2"),
        ("model_config_hash", "b" * 64),
        ("prompt_hash", "b" * 64),
        ("policy_hash", "b" * 64),
        ("code_hash", "d" * 40),
    ],
)
def test_manifest_hash_changes_when_field_changes(field, value):
    base_hash = compute_manifest_hash(_build_with_hash())
    changed = compute_manifest_hash(_build_with_hash(**{field: value}))
    assert changed != base_hash


def test_manifest_hash_changes_when_variant_or_rubric_changes():
    base_hash = compute_manifest_hash(_build_with_hash())
    v = {k: dict(val) for k, val in ALL_VARIANTS.items()}
    v["B1"] = {"mode": "changed"}
    assert compute_manifest_hash(_build_with_hash(variants=v)) != base_hash
    q = dict(_VALID_QUALITY)
    q["double_blind"] = False
    assert compute_manifest_hash(_build_with_hash(quality_rubric=q)) != base_hash


def test_manifest_hash_absent_from_hash_input():
    """model_dump excludes manifest_hash so changing only it does not change the computed hash."""
    m = _build_with_hash()
    other = m.model_copy(update={"manifest_hash": "f" * 64})
    assert compute_manifest_hash(m) == compute_manifest_hash(other)


def test_manifest_recompute_hash_matches():
    m = _build_with_hash()
    assert m.recompute_hash() == compute_manifest_hash(m)


def test_manifest_is_frozen_assignment_rejected():
    m = _build_with_hash()
    with pytest.raises(ValidationError):
        m.manifest_id = "changed"  # type: ignore[misc]
