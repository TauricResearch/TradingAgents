"""Tests for backtest decision-point scheduling."""

import pytest

from tradingagents.backtest.schedule import decision_dates


def test_every_weekday_skips_the_weekend():
    # Fri 2026-01-09 .. Mon 2026-01-12.
    dates = decision_dates("2026-01-09", "2026-01-12", every_n_days=1)

    assert dates == ["2026-01-09", "2026-01-12"]


def test_stride_is_in_business_days():
    dates = decision_dates("2026-01-05", "2026-01-30", every_n_days=5)

    # Mondays: a 5-business-day stride from a Monday lands on Mondays.
    assert dates == ["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-26"]


def test_range_is_inclusive_of_both_ends():
    dates = decision_dates("2026-01-05", "2026-01-07", every_n_days=1)

    assert dates[0] == "2026-01-05"
    assert dates[-1] == "2026-01-07"


def test_single_day_range():
    assert decision_dates("2026-01-05", "2026-01-05") == ["2026-01-05"]


def test_weekend_only_range_is_empty():
    # Sat 2026-01-10 .. Sun 2026-01-11 — no weekdays at all.
    assert decision_dates("2026-01-10", "2026-01-11") == []


def test_reversed_range_raises():
    with pytest.raises(ValueError, match="precedes start"):
        decision_dates("2026-06-01", "2026-01-01")


@pytest.mark.parametrize("stride", [0, -1])
def test_non_positive_stride_raises(stride):
    with pytest.raises(ValueError, match="every_n_days must be >= 1"):
        decision_dates("2026-01-05", "2026-01-30", every_n_days=stride)


def test_unparseable_date_raises():
    with pytest.raises(ValueError, match="Invalid backtest date range"):
        decision_dates("not-a-date", "2026-01-30")


def test_large_stride_yields_the_first_date_only():
    dates = decision_dates("2026-01-05", "2026-01-09", every_n_days=500)

    assert dates == ["2026-01-05"]


def test_dates_are_strictly_increasing():
    dates = decision_dates("2026-01-01", "2026-12-31", every_n_days=5)

    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)
