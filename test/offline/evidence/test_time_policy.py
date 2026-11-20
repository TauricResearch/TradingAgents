"""Tests for evidence time filtering, driven by the E-01..E-30 fixtures."""

from datetime import datetime, timezone

import pytest

from ._target import TimeVerdict, is_admissible  # noqa: F401


def _as_of_string(frozen_now) -> str:
    return frozen_now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_future_items_excluded(load_case, frozen_now, iter_items):
    as_of = _as_of_string(frozen_now)
    for case_id in ("E-13", "E-14", "E-15", "E-16", "E-28"):
        case = load_case(case_id)
        for item in iter_items(case):
            verdict = is_admissible(
                published_at=item["published_at"],
                time_granularity=item["time_granularity"],
                as_of=as_of,
            )
            expected = case["expected"]["excluded"][0]
            assert verdict.admissible is False, case_id
            assert verdict.availability == expected["availability"], case_id
            assert verdict.reason_code == expected["reason_code"], case_id


def test_boundary_before_cutoff_admitted(load_case, frozen_now, iter_items):
    case = load_case("E-27")
    item = iter_items(case)[0]
    verdict = is_admissible(
        published_at=item["published_at"],
        time_granularity=item["time_granularity"],
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is True
    assert verdict.availability == "available"
    assert verdict.reason_code is None


def test_offset_normalized_to_utc(load_case, frozen_now, iter_items):
    case = load_case("E-11")
    item = iter_items(case)[0]
    verdict = is_admissible(
        published_at=item["published_at"],
        time_granularity=item["time_granularity"],
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is True
    normalized = datetime.fromisoformat(verdict.normalized_at.replace("Z", "+00:00"))
    expected_instant = datetime(2026, 11, 10, 9, 0, 0, tzinfo=timezone.utc)
    assert normalized == expected_instant


def test_date_only_before_cutoff_admitted(load_case, frozen_now, iter_items):
    case = load_case("E-07")
    item = iter_items(case)[0]
    verdict = is_admissible(
        published_at=item["published_at"],
        time_granularity=item["time_granularity"],
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is True
    assert verdict.reason_code is None


def test_day_granularity_future_excluded(load_case, frozen_now, iter_items):
    case = load_case("E-16")
    item = iter_items(case)[0]
    verdict = is_admissible(
        published_at=item["published_at"],
        time_granularity=item["time_granularity"],
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is False
    assert verdict.reason_code == "FUTURE_DATA"


def test_missing_published_at_records_reason(load_case, frozen_now, iter_items):
    as_of = _as_of_string(frozen_now)
    # E-20's expected outcome is REVIEW, but that is a pack-level decision;
    # the time layer only reports EVIDENCE_MISSING.
    for case_id in ("E-17", "E-20"):
        case = load_case(case_id)
        item = iter_items(case)[0]
        verdict = is_admissible(
            published_at=item.get("published_at"),
            time_granularity=item["time_granularity"],
            as_of=as_of,
        )
        assert verdict.admissible is False, case_id
        assert verdict.availability == "unavailable", case_id
        assert verdict.reason_code == "EVIDENCE_MISSING", case_id


def test_malformed_time_is_invalid(load_case, frozen_now, iter_items):
    case = load_case("E-18")
    item = iter_items(case)[0]
    assert item["published_at"] == "2026-13-45 25:61"
    verdict = is_admissible(
        published_at=item["published_at"],
        time_granularity=item["time_granularity"],
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is False
    assert verdict.reason_code == "INVALID_TIME"


def test_naive_timestamp_not_assumed_utc(load_case, frozen_now, iter_items):
    case = load_case("E-19")
    item = iter_items(case)[0]
    assert item["published_at"] == "2026-11-10T09:00:00"
    verdict = is_admissible(
        published_at=item["published_at"],
        time_granularity=item["time_granularity"],
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is False
    assert (
        verdict.reason_code == "INVALID_TIME"
    ), "a timestamp without an offset must never be assumed to be UTC and admitted"


def test_epoch_input_supported(frozen_now):
    verdict = is_admissible(
        published_at=1794262200,
        time_granularity="second",
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is True


def test_naive_as_of_rejected(frozen_now):
    with pytest.raises(ValueError):
        is_admissible(
            published_at="2026-11-10T09:00:00Z",
            time_granularity="second",
            as_of=datetime(2026, 11, 11),
        )


def test_date_only_equal_to_as_of_date_excludes(frozen_now):
    """This choice is pending confirmation from B and D; the alternative is
    FUTURE_DATA; both exclude, only the reason code differs."""
    verdict = is_admissible(
        published_at="2026-11-11",
        time_granularity="date_only",
        as_of=_as_of_string(frozen_now),
    )
    assert verdict.admissible is False
    assert verdict.reason_code == "INVALID_TIME"
