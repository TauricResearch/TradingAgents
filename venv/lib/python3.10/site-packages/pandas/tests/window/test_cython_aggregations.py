from functools import partial
import sys

import numpy as np
import pytest

import pandas._libs.window.aggregations as window_aggregations

from pandas import Series
import pandas._testing as tm


def _get_rolling_aggregations():
    # list pairs of name and function
    # each function has this signature:
    # (const float64_t[:] values, ndarray[int64_t] start,
    #  ndarray[int64_t] end, int64_t minp) -> np.ndarray
    named_roll_aggs = (
        [
            ("roll_sum", window_aggregations.roll_sum),
            ("roll_mean", window_aggregations.roll_mean),
        ]
        + [
            (f"roll_var({ddof})", partial(window_aggregations.roll_var, ddof=ddof))
            for ddof in [0, 1]
        ]
        + [
            ("roll_skew", window_aggregations.roll_skew),
            ("roll_kurt", window_aggregations.roll_kurt),
            ("roll_median_c", window_aggregations.roll_median_c),
            ("roll_max", window_aggregations.roll_max),
            ("roll_min", window_aggregations.roll_min),
        ]
        + [
            (
                f"roll_quantile({quantile},{interpolation})",
                partial(
                    window_aggregations.roll_quantile,
                    quantile=quantile,
                    interpolation=interpolation,
                ),
            )
            for quantile in [0.0001, 0.5, 0.9999]
            for interpolation in window_aggregations.interpolation_types
        ]
        + [
            (
                f"roll_rank({percentile},{method},{ascending})",
                partial(
                    window_aggregations.roll_rank,
                    percentile=percentile,
                    method=method,
                    ascending=ascending,
                ),
            )
            for percentile in [True, False]
            for method in window_aggregations.rolling_rank_tiebreakers.keys()
            for ascending in [True, False]
        ]
    )
    # unzip to a list of 2 tuples, names and functions
    unzipped = list(zip(*named_roll_aggs))
    return {"ids": unzipped[0], "params": unzipped[1]}


_rolling_aggregations = _get_rolling_aggregations()


@pytest.fixture(
    params=_rolling_aggregations["params"], ids=_rolling_aggregations["ids"]
)
def rolling_aggregation(request):
    """Make a rolling aggregation function as fixture."""
    return request.param


def test_rolling_aggregation_boundary_consistency(rolling_aggregation):
    # GH-45647
    minp, step, width, size, selection = 0, 1, 3, 11, [2, 7]
    values = np.arange(1, 1 + size, dtype=np.float64)
    end = np.arange(width, size, step, dtype=np.int64)
    start = end - width
    selarr = np.array(selection, dtype=np.int32)
    result = Series(rolling_aggregation(values, start[selarr], end[selarr], minp))
    expected = Series(rolling_aggregation(values, start, end, minp)[selarr])
    tm.assert_equal(expected, result)


def test_rolling_aggregation_with_unused_elements(rolling_aggregation):
    # GH-45647
    minp, width = 0, 5  # width at least 4 for kurt
    size = 2 * width + 5
    values = np.arange(1, size + 1, dtype=np.float64)
    values[width : width + 2] = sys.float_info.min
    values[width + 2] = np.nan
    values[width + 3 : width + 5] = sys.float_info.max
    start = np.array([0, size - width], dtype=np.int64)
    end = np.array([width, size], dtype=np.int64)
    loc = np.array(
        [j for i in range(len(start)) for j in range(start[i], end[i])],
        dtype=np.int32,
    )
    result = Series(rolling_aggregation(values, start, end, minp))
    compact_values = np.array(values[loc], dtype=np.float64)
    compact_start = np.arange(0, len(start) * width, width, dtype=np.int64)
    compact_end = compact_start + width
    expected = Series(
        rolling_aggregation(compact_values, compact_start, compact_end, minp)
    )
    assert np.isfinite(expected.values).all(), "Not all expected values are finite"
    tm.assert_equal(expected, result)
