"""Phase 7 — walk-forward validation tests (contract sections 9 and 11).

No look-ahead: a fold's train window ends strictly before its test window,
and the memory-log ``as_of`` guard is the enforcement point for lessons.
Honest scoring: pending cells are excluded from averages, never counted as
zero; small samples are labelled insufficient. Pure logic, frozen dates.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.walk_forward import (
    DEFAULT_MIN_SAMPLES,
    SettledCell,
    WalkForwardFold,
    make_walk_forward_folds,
    score_cells,
    summarize_walk_forward,
)

# ---------------------------------------------------------------------------
# Fold construction — the no-leakage geometry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_folds_tile_the_range_without_overlap():
    folds = make_walk_forward_folds(
        "2026-01-01", "2026-01-31", train_days=10, test_days=5
    )
    assert len(folds) >= 4
    seen = []
    for fold in folds:
        # Test windows never overlap: each starts after the previous ends.
        for other in seen:
            assert not (fold.test_start <= other.test_end
                        and other.test_start <= fold.test_end), \
                f"overlapping test windows: {fold} vs {other}"
        seen.append(fold)


@pytest.mark.unit
def test_train_window_ends_strictly_before_test_window():
    """The no-leakage boundary: train_end < test_start, always."""
    folds = make_walk_forward_folds(
        "2026-01-01", "2026-03-31", train_days=20, test_days=10
    )
    for fold in folds:
        assert fold.train_end < fold.test_start
        fold.validate()  # the fold's own invariant agrees


@pytest.mark.unit
def test_context_as_of_is_the_train_end():
    """The memory log must be filtered to lessons resolved by train_end (#1251)."""
    folds = make_walk_forward_folds(
        "2026-01-01", "2026-01-31", train_days=10, test_days=5
    )
    for fold in folds:
        assert fold.context_as_of() == fold.train_end


@pytest.mark.unit
def test_last_fold_is_truncated_not_dropped():
    """A range shorter than one test window still yields a truncated fold.

    With a 10-day range and 7-day test windows, the first fold covers
    01-01..01-07 and the second (stepped 7 days) is truncated at 01-10.
    """
    folds = make_walk_forward_folds(
        "2026-01-01", "2026-01-10", train_days=5, test_days=7
    )
    assert len(folds) == 2
    assert folds[0].test_end == "2026-01-07"
    assert folds[-1].test_end == "2026-01-10"  # truncated at the range end
    # Every fold still respects the no-leakage boundary.
    for fold in folds:
        fold.validate()


@pytest.mark.unit
def test_overlapping_windows_are_rejected():
    with pytest.raises(ValueError, match="overlap or are unordered"):
        WalkForwardFold(0, "2026-01-10", "2026-01-20", "2026-01-15", "2026-01-25").validate()


@pytest.mark.unit
def test_invalid_day_counts_are_rejected():
    with pytest.raises(ValueError):
        make_walk_forward_folds("2026-01-01", "2026-01-31", train_days=0, test_days=5)
    with pytest.raises(ValueError):
        make_walk_forward_folds("2026-01-01", "2026-01-31", train_days=5, test_days=0)


@pytest.mark.unit
def test_non_canonical_dates_are_rejected():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        make_walk_forward_folds("2026-1-1", "2026-01-31", train_days=5, test_days=5)


# ---------------------------------------------------------------------------
# Honest scoring — pending excluded, small samples labelled
# ---------------------------------------------------------------------------


def _cell(rating, holding, benchmark, ticker="X", day="2026-01-15"):
    return SettledCell(
        ticker=ticker, analysis_date=day, entry_date=day, rating=rating,
        holding_return=holding, benchmark_return=benchmark, holding_days=5,
    )


@pytest.mark.unit
def test_alpha_is_return_over_benchmark():
    cell = _cell("Buy", 0.05, 0.01)
    assert cell.alpha == pytest.approx(0.04)


@pytest.mark.unit
def test_unsettled_cell_has_no_alpha():
    cell = SettledCell("X", "2026-01-15", "2026-01-16", "Buy",
                       None, None, 5)
    assert cell.alpha is None


@pytest.mark.unit
def test_direction_map_covers_the_five_tier_scale():
    assert _cell("Buy", 0, 0).direction == 1
    assert _cell("Overweight", 0, 0).direction == 1
    assert _cell("Hold", 0, 0).direction == 0
    assert _cell("Underweight", 0, 0).direction == -1
    assert _cell("Sell", 0, 0).direction == -1


@pytest.mark.unit
def test_hit_rate_counts_matching_directions_only():
    cells = [
        _cell("Buy", 0.05, 0.01),   # alpha +4% vs +1: hit
        _cell("Buy", -0.03, 0.01),  # alpha -4% vs +1: miss
        _cell("Buy", 0.02, 0.00),   # alpha +2% vs 0: hit
        _cell("Buy", 0.04, 0.01),   # alpha +3% vs +1: hit
        _cell("Buy", 0.06, 0.01),   # alpha +5% vs +1: hit
    ]
    score = score_cells(cells)["Buy"]
    assert score.directional_calls == 5
    assert score.hits == 4
    assert not score.insufficient  # exactly at the minimum sample count


@pytest.mark.unit
def test_hold_claims_no_direction_so_nothing_proves_it():
    cells = [_cell("Hold", 0.05, 0.01), _cell("Hold", -0.02, 0.01)]
    score = score_cells(cells)["Hold"]
    assert score.directional_calls == 0
    assert score.hits == 0
    assert score.mean_alpha == pytest.approx((0.04 - 0.03) / 2)


@pytest.mark.unit
def test_small_samples_are_labelled_insufficient():
    """A 1-of-2 hit rate is noise: labelled, not reported as evidence."""
    cells = [_cell("Sell", -0.05, 0.01), _cell("Sell", -0.02, 0.01)]
    score = score_cells(cells)["Sell"]
    assert score.count == 2
    assert score.insufficient
    assert f"min {DEFAULT_MIN_SAMPLES}" in score.render()


@pytest.mark.unit
def test_enough_samples_are_scored():
    cells = [_cell("Buy", 0.05, 0.01) for _ in range(DEFAULT_MIN_SAMPLES)]
    score = score_cells(cells)["Buy"]
    assert not score.insufficient
    assert "called the direction 5/5" in score.render()


@pytest.mark.unit
def test_cells_with_missing_outcomes_are_excluded_from_the_mean():
    """A cell without an outcome is not a zero-alpha cell."""
    cells = [_cell("Buy", 0.10, 0.00), _cell("Buy", None, None)]
    score = score_cells(cells)["Buy"]
    assert score.count == 2
    assert score.mean_alpha == pytest.approx(0.10)  # only the settled one


# ---------------------------------------------------------------------------
# The honest summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_summary_counts_pending_separately():
    folds = make_walk_forward_folds("2026-01-01", "2026-01-31",
                                    train_days=10, test_days=5)
    settled = [_cell("Buy", 0.05, 0.01) for _ in range(6)]
    summary = summarize_walk_forward(folds, settled, cells_total=10,
                                     holding_window="5 trading days",
                                     benchmark="SPY")
    assert summary.folds == len(folds)
    assert summary.cells_total == 10
    assert summary.cells_settled == 6
    assert summary.cells_pending == 4
    assert not summary.all_scored
    text = summary.render()
    assert "4 pending" in text
    assert "excluded from the averages, not counted as zero" in text
    assert "indicative rather than repeatable" in text


@pytest.mark.unit
def test_summary_with_everything_settled():
    folds = make_walk_forward_folds("2026-01-01", "2026-01-15",
                                    train_days=5, test_days=5)
    settled = [_cell("Overweight", 0.03, 0.01) for _ in range(DEFAULT_MIN_SAMPLES)]
    summary = summarize_walk_forward(folds, settled, cells_total=5)
    assert summary.all_scored
    assert summary.cells_pending == 0


@pytest.mark.unit
def test_summary_declares_its_measurement_basis():
    """The reader must know what alpha was measured over (contract §11)."""
    folds = make_walk_forward_folds("2026-01-01", "2026-01-15",
                                    train_days=5, test_days=5)
    summary = summarize_walk_forward(folds, [], holding_window="10 trading days",
                                     benchmark="the ticker's regional benchmark")
    text = summary.render()
    assert "10 trading days" in text
    assert "regional benchmark" in text
