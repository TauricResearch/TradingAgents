"""Property-based tests for ReflexionMemory as-of-date filtering.

Feature: remaining-graph-hardening, Property 3: ReflexionMemory as-of-date filtering

Validates: Requirements 2.1, 2.2, 2.3, 2.4

For any set of reflexion records and any as_of_date string,
ReflexionMemory.get_history(ticker, as_of_date=d) returns only records
whose decision_date is <= d, and returns them in descending date order.
"""

from __future__ import annotations

import json
import logging

from hypothesis import given, settings
from hypothesis import strategies as st

from tradingagents.memory.reflexion import ReflexionMemory


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate ISO date strings in a reasonable range
_iso_dates = st.dates(
    min_value=st.just(2020).flatmap(lambda _: None),  # type: ignore[arg-type]
).map(lambda d: d.isoformat())

# Simpler: generate YYYY-MM-DD strings directly
_year = st.integers(min_value=2020, max_value=2030)
_month = st.integers(min_value=1, max_value=12)
_day = st.integers(min_value=1, max_value=28)  # avoid invalid dates

_iso_date_str = st.builds(
    lambda y, m, d: f"{y:04d}-{m:02d}-{d:02d}",
    _year,
    _month,
    _day,
)

_decisions = st.sampled_from(["BUY", "SELL", "HOLD", "SKIP"])
_confidences = st.sampled_from(["high", "medium", "low"])
_rationales = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Z")))

_reflexion_record = st.fixed_dictionaries({
    "ticker": st.just("TEST"),
    "decision_date": _iso_date_str,
    "decision": _decisions,
    "rationale": _rationales,
    "confidence": _confidences,
    "source": st.just("pipeline"),
    "run_id": st.just("test_run"),
    "outcome": st.just(None),
    "created_at": st.just("2026-01-01T00:00:00+00:00"),
})


# ---------------------------------------------------------------------------
# Property 3: as-of-date filtering
# ---------------------------------------------------------------------------


@given(
    records=st.lists(_reflexion_record, min_size=1, max_size=20),
    as_of_date=_iso_date_str,
)
@settings(max_examples=100)
def test_property3_get_history_as_of_date_filtering(tmp_path_factory, records, as_of_date):
    """Property 3: get_history(as_of_date=d) returns only records with decision_date <= d
    in descending date order.

    Feature: remaining-graph-hardening, Property 3: ReflexionMemory as-of-date filtering
    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    # Use a unique tmp path for each example
    tmp_path = tmp_path_factory.mktemp("reflexion")
    fb_path = tmp_path / "reflexion.json"

    # Write records directly to the JSON file (bypass record_decision for speed)
    fb_path.write_text(json.dumps(records), encoding="utf-8")

    mem = ReflexionMemory(mongo_uri=None, fallback_path=fb_path)
    history = mem.get_history("TEST", limit=100, as_of_date=as_of_date)

    # Property assertion 1: All returned records have decision_date <= as_of_date
    for rec in history:
        assert rec["decision_date"][:10] <= as_of_date[:10], (
            f"Record with date {rec['decision_date']} should not appear "
            f"when as_of_date={as_of_date}"
        )

    # Property assertion 2: Results are in descending date order
    dates = [rec["decision_date"][:10] for rec in history]
    assert dates == sorted(dates, reverse=True), (
        f"Results not in descending order: {dates}"
    )

    # Property assertion 3: All records that SHOULD be included ARE included
    expected_count = sum(
        1 for r in records
        if r.get("ticker") == "TEST" and r["decision_date"][:10] <= as_of_date[:10]
    )
    assert len(history) == expected_count, (
        f"Expected {expected_count} records but got {len(history)}"
    )


@given(
    records=st.lists(_reflexion_record, min_size=0, max_size=15),
)
@settings(max_examples=100)
def test_property3_no_as_of_date_returns_all(tmp_path_factory, records):
    """When as_of_date is None, get_history returns all matching records (backward-compat).

    Feature: remaining-graph-hardening, Property 3: ReflexionMemory as-of-date filtering
    **Validates: Requirements 2.3**
    """
    tmp_path = tmp_path_factory.mktemp("reflexion")
    fb_path = tmp_path / "reflexion.json"
    fb_path.write_text(json.dumps(records), encoding="utf-8")

    mem = ReflexionMemory(mongo_uri=None, fallback_path=fb_path)
    history = mem.get_history("TEST", limit=100, as_of_date=None)

    # All records for ticker TEST should be returned
    expected_count = sum(1 for r in records if r.get("ticker") == "TEST")
    assert len(history) == expected_count

    # Still in descending order
    dates = [rec["decision_date"][:10] for rec in history]
    assert dates == sorted(dates, reverse=True)


@given(
    records=st.lists(_reflexion_record, min_size=1, max_size=15),
    as_of_date=_iso_date_str,
)
@settings(max_examples=100)
def test_property3_build_context_respects_as_of_date(tmp_path_factory, records, as_of_date):
    """build_context(as_of_date=d) must not mention decisions after d.

    Feature: remaining-graph-hardening, Property 3: ReflexionMemory as-of-date filtering
    **Validates: Requirements 2.2**
    """
    tmp_path = tmp_path_factory.mktemp("reflexion")
    fb_path = tmp_path / "reflexion.json"
    fb_path.write_text(json.dumps(records), encoding="utf-8")

    mem = ReflexionMemory(mongo_uri=None, fallback_path=fb_path)
    context = mem.build_context("TEST", limit=100, as_of_date=as_of_date)

    # No future dates should appear in the context string
    future_dates = [
        r["decision_date"][:10]
        for r in records
        if r.get("ticker") == "TEST" and r["decision_date"][:10] > as_of_date[:10]
    ]
    for future_date in future_dates:
        assert future_date not in context, (
            f"Future date {future_date} found in context when as_of_date={as_of_date}"
        )


# ---------------------------------------------------------------------------
# Unit tests: corrupt file handling
# ---------------------------------------------------------------------------


def test_corrupt_json_logs_warning_returns_empty(tmp_path, caplog):
    """Corrupt local JSON must log a warning and return empty list.

    Validates: Requirement 2.5
    """
    bad_path = tmp_path / "corrupt.json"
    bad_path.write_text("{{{invalid json", encoding="utf-8")

    mem = ReflexionMemory(mongo_uri=None, fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = mem.get_history("AAPL", as_of_date="2026-03-20")

    assert history == []
    assert any(
        "corrupt" in r.message.lower() or "malformed" in r.message.lower()
        for r in caplog.records
    )


def test_unreadable_file_logs_warning_returns_empty(tmp_path, caplog):
    """Unreadable local file must log a warning and return empty list.

    Validates: Requirement 2.5
    """
    import os

    bad_path = tmp_path / "unreadable.json"
    bad_path.write_text("[]", encoding="utf-8")
    os.chmod(bad_path, 0o000)

    mem = ReflexionMemory(mongo_uri=None, fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = mem.get_history("AAPL", as_of_date="2026-03-20")

    assert history == []
    # Restore permissions for cleanup
    os.chmod(bad_path, 0o644)


def test_non_list_json_logs_warning_returns_empty(tmp_path, caplog):
    """JSON that is not a list must log a warning and return empty list.

    Validates: Requirement 2.5
    """
    bad_path = tmp_path / "not_list.json"
    bad_path.write_text('{"key": "value"}', encoding="utf-8")

    mem = ReflexionMemory(mongo_uri=None, fallback_path=bad_path)
    with caplog.at_level(logging.WARNING, logger="tradingagents.memory.reflexion"):
        history = mem.get_history("AAPL", as_of_date="2026-03-20")

    assert history == []
    assert any(
        "corrupt" in r.message.lower() or "malformed" in r.message.lower()
        for r in caplog.records
    )
