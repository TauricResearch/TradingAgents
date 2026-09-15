"""Tests for the append-only backtest decision store."""

import json

import pytest

from tradingagents.backtest.store import (
    SCHEMA_VERSION,
    DecisionRecord,
    DecisionStore,
)

SIG = "analysts=market|debate=1|risk=1"
OTHER_SIG = "analysts=market,news|debate=2|risk=1"


def make_record(ticker="NVDA", date="2026-01-05", signature=SIG, **kwargs):
    defaults = {"rating": "Buy", "decision": "Rating: Buy"}
    defaults.update(kwargs)
    return DecisionRecord(ticker=ticker, date=date, signature=signature, **defaults)


def test_append_and_read_back(tmp_path):
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record())

    records = store.records()
    assert len(records) == 1
    assert records[0].ticker == "NVDA"
    assert records[0].rating == "Buy"
    assert records[0].schema_version == SCHEMA_VERSION


def test_has_reports_only_successful_points(tmp_path):
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record(date="2026-01-05"))
    store.append(make_record(date="2026-01-12", rating=None, error="boom"))

    assert store.has("NVDA", "2026-01-05", SIG)
    # A failed point must not count as done, so a resume retries it (#1249-style
    # resumability at the decision level rather than the node level).
    assert not store.has("NVDA", "2026-01-12", SIG)


def test_index_survives_reopening(tmp_path):
    path = tmp_path / "decisions.jsonl"
    DecisionStore(path).append(make_record())

    reopened = DecisionStore(path)
    assert reopened.has("NVDA", "2026-01-05", SIG)


def test_signature_partitions_records(tmp_path):
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record(signature=SIG))
    store.append(make_record(signature=OTHER_SIG))

    assert len(store.records(SIG)) == 1
    assert len(store.records(OTHER_SIG)) == 1
    assert len(store.records()) == 2
    # A config change must not be mistaken for work already done.
    assert not store.has("NVDA", "2026-01-05", "analysts=news|debate=9|risk=9")


def test_torn_final_line_is_skipped_not_fatal(tmp_path):
    """A crash mid-write leaves a partial line; earlier records stay readable."""
    path = tmp_path / "decisions.jsonl"
    store = DecisionStore(path)
    store.append(make_record(date="2026-01-05"))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"ticker": "NVDA", "date": "2026-01-12", "sig')  # truncated

    records = DecisionStore(path).records()
    assert len(records) == 1
    assert records[0].date == "2026-01-05"


def test_records_from_another_schema_version_are_ignored(tmp_path):
    path = tmp_path / "decisions.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ticker": "NVDA", "date": "2026-01-05", "signature": SIG,
            "rating": "Buy", "schema_version": SCHEMA_VERSION + 1,
        }) + "\n")

    assert DecisionStore(path).records() == []


def test_decisions_are_sorted_and_exclude_failures(tmp_path):
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record(ticker="TSLA", date="2026-01-12"))
    store.append(make_record(ticker="NVDA", date="2026-01-12"))
    store.append(make_record(ticker="NVDA", date="2026-01-05"))
    store.append(make_record(ticker="NVDA", date="2026-01-20", rating=None, error="timeout"))

    keys = [(r.ticker, r.date) for r in store.decisions()]
    assert keys == [("NVDA", "2026-01-05"), ("NVDA", "2026-01-12"), ("TSLA", "2026-01-12")]
    assert [r.date for r in store.failures()] == ["2026-01-20"]


def test_review_sentinel_counts_as_a_usable_decision(tmp_path):
    """REVIEW is a real outcome to record, not an error to retry (#1170)."""
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record(rating="REVIEW", decision="No parseable rating"))

    assert store.has("NVDA", "2026-01-05", SIG)
    assert store.decisions()[0].rating == "REVIEW"


def test_tickers_lists_distinct_successful_tickers(tmp_path):
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record(ticker="NVDA"))
    store.append(make_record(ticker="AAPL", date="2026-01-06"))
    store.append(make_record(ticker="AAPL", date="2026-01-07"))

    assert store.tickers() == ["AAPL", "NVDA"]


def test_missing_file_reads_as_empty(tmp_path):
    store = DecisionStore(tmp_path / "nested" / "decisions.jsonl")
    assert store.records() == []
    assert store.decisions() == []


def test_cost_is_none_when_model_is_unpriced(tmp_path):
    """An unpriced model reports tokens without inventing a dollar figure."""
    store = DecisionStore(tmp_path / "decisions.jsonl")
    store.append(make_record(tokens_in=1000, tokens_out=500, cost_usd=None))

    record = store.decisions()[0]
    assert record.tokens_in == 1000
    assert record.cost_usd is None


@pytest.mark.parametrize("rating,error,expected", [
    ("Buy", None, True),
    ("REVIEW", None, True),
    (None, "boom", False),
    (None, None, False),
])
def test_ok_property(rating, error, expected):
    assert make_record(rating=rating, error=error).ok is expected
