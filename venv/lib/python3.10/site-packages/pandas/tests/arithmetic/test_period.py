# Arithmetic tests for DataFrame/Series/Index/Array classes that should
# behave identically.
# Specifically for Period dtype
import operator

import numpy as np
import pytest

from pandas._libs.tslibs import (
    IncompatibleFrequency,
    Period,
    Timestamp,
    to_offset,
)
from pandas.errors import PerformanceWarning

import pandas as pd
from pandas import (
    PeriodIndex,
    Series,
    Timedelta,
    TimedeltaIndex,
    period_range,
)
import pandas._testing as tm
from pandas.core import ops
from pandas.core.arrays import TimedeltaArray
from pandas.tests.arithmetic.common import (
    assert_invalid_addsub_type,
    assert_invalid_comparison,
    get_upcast_box,
)

_common_mismatch = [
    pd.offsets.YearBegin(2),
    pd.offsets.MonthBegin(1),
    pd.offsets.Minute(),
]


@pytest.fixture(
    params=[
        Timedelta(minutes=30).to_pytimedelta(),
        np.timedelta64(30, "s"),
        Timedelta(seconds=30),
    ]
    + _common_mismatch
)
def not_hourly(request):
    """
    Several timedelta-like and DateOffset instances that are _not_
    compatible with Hourly frequencies.
    """
    return request.param


@pytest.fixture(
    params=[
        np.timedelta64(365, "D"),
        Timedelta(days=365).to_pytimedelta(),
        Timedelta(days=365),
    ]
    + _common_mismatch
)
def mismatched_freq(request):
    """
    Several timedelta-like and DateOffset instances that are _not_
    compatible with Monthly or Annual frequencies.
    """
    return request.param


# ------------------------------------------------------------------
# Comparisons


class TestPeriodArrayLikeComparisons:
    # Comparison tests for PeriodDtype vectors fully parametrized over
    #  DataFrame/Series/PeriodIndex/PeriodArray.  Ideally all comparison
    #  tests will eventually end up here.

    @pytest.mark.parametrize("other", ["2017", Period("2017", freq="D")])
    def test_eq_scalar(self, other, box_with_array):
        idx = PeriodIndex(["2017", "2017", "2018"], freq="D")
        idx = tm.box_expected(idx, box_with_array)
        xbox = get_upcast_box(idx, other, True)

        expected = np.array([True, True, False])
        expected = tm.box_expected(expected, xbox)

        result = idx == other

        tm.assert_equal(result, expected)

    def test_compare_zerodim(self, box_with_array):
        # GH#26689 make sure we unbox zero-dimensional arrays

        pi = period_range("2000", periods=4)
        other = np.array(pi.to_numpy()[0])

        pi = tm.box_expected(pi, box_with_array)
        xbox = get_upcast_box(pi, other, True)

        result = pi <= other
        expected = np.array([True, False, False, False])
        expected = tm.box_expected(expected, xbox)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize(
        "scalar",
        [
            "foo",
            Timestamp("2021-01-01"),
            Timedelta(days=4),
            9,
            9.5,
            2000,  # specifically don't consider 2000 to match Period("2000", "D")
            False,
            None,
        ],
    )
    def test_compare_invalid_scalar(self, box_with_array, scalar):
        # GH#28980
        # comparison with scalar that cannot be interpreted as a Period
        pi = period_range("2000", periods=4)
        parr = tm.box_expected(pi, box_with_array)
        assert_invalid_comparison(parr, scalar, box_with_array)

    @pytest.mark.parametrize(
        "other",
        [
            pd.date_range("2000", periods=4).array,
            pd.timedelta_range("1D", periods=4).array,
            np.arange(4),
            np.arange(4).astype(np.float64),
            list(range(4)),
            # match Period semantics by not treating integers as Periods
            [2000, 2001, 2002, 2003],
            np.arange(2000, 2004),
            np.arange(2000, 2004).astype(object),
            pd.Index([2000, 2001, 2002, 2003]),
        ],
    )
    def test_compare_invalid_listlike(self, box_with_array, other):
        pi = period_range("2000", periods=4)
        parr = tm.box_expected(pi, box_with_array)
        assert_invalid_comparison(parr, other, box_with_array)

    @pytest.mark.parametrize("other_box", [list, np.array, lambda x: x.astype(object)])
    def test_compare_object_dtype(self, box_with_array, other_box):
        pi = period_range("2000", periods=5)
        parr = tm.box_expected(pi, box_with_array)

        other = other_box(pi)
        xbox = get_upcast_box(parr, other, True)

        expected = np.array([True, True, True, True, True])
        expected = tm.box_expected(expected, xbox)

        result = parr == other
        tm.assert_equal(result, expected)
        result = parr <= other
        tm.assert_equal(result, expected)
        result = parr >= other
        tm.assert_equal(result, expected)

        result = parr != other
        tm.assert_equal(result, ~expected)
        result = parr < other
        tm.assert_equal(result, ~expected)
        result = parr > other
        tm.assert_equal(result, ~expected)

        other = other_box(pi[::-1])

        expected = np.array([False, False, True, False, False])
        expected = tm.box_expected(expected, xbox)
        result = parr == other
        tm.assert_equal(result, expected)

        expected = np.array([True, True, True, False, False])
        expected = tm.box_expected(expected, xbox)
        result = parr <= other
        tm.assert_equal(result, expected)

        expected = np.array([False, False, True, True, True])
        expected = tm.box_expected(expected, xbox)
        result = parr >= other
        tm.assert_equal(result, expected)

        expected = np.array([True, True, False, True, True])
        expected = tm.box_expected(expected, xbox)
        result = parr != other
        tm.assert_equal(result, expected)

        expected = np.array([True, True, False, False, False])
        expected = tm.box_expected(expected, xbox)
        result = parr < other
        tm.assert_equal(result, expected)

        expected = np.array([False, False, False, True, True])
        expected = tm.box_expected(expected, xbox)
        result = parr > other
        tm.assert_equal(result, expected)


class TestPeriodIndexComparisons:
    # TODO: parameterize over boxes

    def test_pi_cmp_period(self):
        idx = period_range("2007-01", periods=20, freq="M")
        per = idx[10]

        result = idx < per
        exp = idx.values < idx.values[10]
        tm.assert_numpy_array_equal(result, exp)

        # Tests Period.__richcmp__ against ndarray[object, ndim=2]
        result = idx.values.reshape(10, 2) < per
        tm.assert_numpy_array_equal(result, exp.reshape(10, 2))

        # Tests Period.__richcmp__ against ndarray[object, ndim=0]
        result = idx < np.array(per)
        tm.assert_numpy_array_equal(result, exp)

    # TODO: moved from test_datetime64; de-duplicate with version below
    def test_parr_cmp_period_scalar2(self, box_with_array):
        pi = period_range("2000-01-01", periods=10, freq="D")

        val = pi[3]
        expected = [x > val for x in pi]

        ser = tm.box_expected(pi, box_with_array)
        xbox = get_upcast_box(ser, val, True)

        expected = tm.box_expected(expected, xbox)
        result = ser > val
        tm.assert_equal(result, expected)

        val = pi[5]
        result = ser > val
        expected = [x > val for x in pi]
        expected = tm.box_expected(expected, xbox)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("freq", ["M", "2M", "3M"])
    def test_parr_cmp_period_scalar(self, freq, box_with_array):
        # GH#13200
        base = PeriodIndex(["2011-01", "2011-02", "2011-03", "2011-04"], freq=freq)
        base = tm.box_expected(base, box_with_array)
        per = Period("2011-02", freq=freq)
        xbox = get_upcast_box(base, per, True)

        exp = np.array([False, True, False, False])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base == per, exp)
        tm.assert_equal(per == base, exp)

        exp = np.array([True, False, True, True])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base != per, exp)
        tm.assert_equal(per != base, exp)

        exp = np.array([False, False, True, True])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base > per, exp)
        tm.assert_equal(per < base, exp)

        exp = np.array([True, False, False, False])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base < per, exp)
        tm.assert_equal(per > base, exp)

        exp = np.array([False, True, True, True])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base >= per, exp)
        tm.assert_equal(per <= base, exp)

        exp = np.array([True, True, False, False])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base <= per, exp)
        tm.assert_equal(per >= base, exp)

    @pytest.mark.parametrize("freq", ["M", "2M", "3M"])
    def test_parr_cmp_pi(self, freq, box_with_array):
        # GH#13200
        base = PeriodIndex(["2011-01", "2011-02", "2011-03", "2011-04"], freq=freq)
        base = tm.box_expected(base, box_with_array)

        # TODO: could also box idx?
        idx = PeriodIndex(["2011-02", "2011-01", "2011-03", "2011-05"], freq=freq)

        xbox = get_upcast_box(base, idx, True)

        exp = np.array([False, False, True, False])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base == idx, exp)

        exp = np.array([True, True, False, True])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base != idx, exp)

        exp = np.array([False, True, False, False])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base > idx, exp)

        exp = np.array([True, False, False, True])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base < idx, exp)

        exp = np.array([False, True, True, False])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base >= idx, exp)

        exp = np.array([True, False, True, True])
        exp = tm.box_expected(exp, xbox)
        tm.assert_equal(base <= idx, exp)

    @pytest.mark.parametrize("freq", ["M", "2M", "3M"])
    def test_parr_cmp_pi_mismatched_freq(self, freq, box_with_array):
        # GH#13200
        # different base freq
        base = PeriodIndex(["2011-01", "2011-02", "2011-03", "2011-04"], freq=freq)
        base = tm.box_expected(base, box_with_array)

        msg = rf"Invalid comparison between dtype=period\[{freq}\] and Period"
        with pytest.raises(TypeError, match=msg):
            base <= Period("2011", freq="Y")

        with pytest.raises(TypeError, match=msg):
            Period("2011", freq="Y") >= base

        # TODO: Could parametrize over boxes for idx?
        idx = PeriodIndex(["2011", "2012", "2013", "2014"], freq="Y")
        rev_msg = r"Invalid comparison between dtype=period\[Y-DEC\] and PeriodArray"
        idx_msg = rev_msg if box_with_array in [tm.to_array, pd.array] else msg
        with pytest.raises(TypeError, match=idx_msg):
            base <= idx

        # Different frequency
        msg = rf"Invalid comparison between dtype=period\[{freq}\] and Period"
        with pytest.raises(TypeError, match=msg):
            base <= Period("2011", freq="4M")

        with pytest.raises(TypeError, match=msg):
            Period("2011", freq="4M") >= base

        idx = PeriodIndex(["2011", "2012", "2013", "2014"], freq="4M")
        rev_msg = r"Invalid comparison between dtype=period\[4M\] and PeriodArray"
        idx_msg = rev_msg if box_with_array in [tm.to_array, pd.array] else msg
        with pytest.raises(TypeError, match=idx_msg):
            base <= idx

    @pytest.mark.parametrize("freq", ["M", "2M", "3M"])
    def test_pi_cmp_nat(self, freq):
        idx1 = PeriodIndex(["2011-01", "2011-02", "NaT", "2011-05"], freq=freq)
        per = idx1[1]

        result = idx1 > per
        exp = np.array([False, False, False, True])
        tm.assert_numpy_array_equal(result, exp)
        result = per < idx1
        tm.assert_numpy_array_equal(result, exp)

        result = idx1 == pd.NaT
        exp = np.array([False, False, False, False])
        tm.assert_numpy_array_equal(result, exp)
        result = pd.NaT == idx1
        tm.assert_numpy_array_equal(result, exp)

        result = idx1 != pd.NaT
        exp = np.array([True, True, True, True])
        tm.assert_numpy_array_equal(result, exp)
        result = pd.NaT != idx1
        tm.assert_numpy_array_equal(result, exp)

        idx2 = PeriodIndex(["2011-02", "2011-01", "2011-04", "NaT"], freq=freq)
        result = idx1 < idx2
        exp = np.array([True, False, False, False])
        tm.assert_numpy_array_equal(result, exp)

        result = idx1 == idx2
        exp = np.array([False, False, False, False])
        tm.assert_numpy_array_equal(result, exp)

        result = idx1 != idx2
        exp = np.array([True, True, True, True])
        tm.assert_numpy_array_equal(result, exp)

        result = idx1 == idx1
        exp = np.array([True, True, False, True])
        tm.assert_numpy_array_equal(result, exp)

        result = idx1 != idx1
        exp = np.array([False, False, True, False])
        tm.assert_numpy_array_equal(result, exp)

    @pytest.mark.parametrize("freq", ["M", "2M", "3M"])
    def test_pi_cmp_nat_mismatched_freq_raises(self, freq):
        idx1 = PeriodIndex(["2011-01", "2011-02", "NaT", "2011-05"], freq=freq)

        diff = PeriodIndex(["2011-02", "2011-01", "2011-04", "NaT"], freq="4M")
        msg = rf"Invalid comparison between dtype=period\[{freq}\] and PeriodArray"
        with pytest.raises(TypeError, match=msg):
            idx1 > diff

        result = idx1 == diff
        expected = np.array([False, False, False, False], dtype=bool)
        tm.assert_numpy_array_equal(result, expected)

    # TODO: De-duplicate with test_pi_cmp_nat
    @pytest.mark.parametrize("dtype", [object, None])
    def test_comp_nat(self, dtype):
        left = PeriodIndex([Period("2011-01-01"), pd.NaT, Period("2011-01-03")])
        right = PeriodIndex([pd.NaT, pd.NaT, Period("2011-01-03")])

        if dtype is not None:
            left = left.astype(dtype)
            right = right.astype(dtype)

        result = left == right
        expected = np.array([False, False, True])
        tm.assert_numpy_array_equal(result, expected)

        result = left != right
        expected = np.array([True, True, False])
        tm.assert_numpy_array_equal(result, expected)

        expected = np.array([False, False, False])
        tm.assert_numpy_array_equal(left == pd.NaT, expected)
        tm.assert_numpy_array_equal(pd.NaT == right, expected)

        expected = np.array([True, True, True])
        tm.assert_numpy_array_equal(left != pd.NaT, expected)
        tm.assert_numpy_array_equal(pd.NaT != left, expected)

        expected = np.array([False, False, False])
        tm.assert_numpy_array_equal(left < pd.NaT, expected)
        tm.assert_numpy_array_equal(pd.NaT > left, expected)


class TestPeriodSeriesComparisons:
    def test_cmp_series_period_series_mixed_freq(self):
        # GH#13200
        base = Series(
            [
                Period("2011", freq="Y"),
                Period("2011-02", freq="M"),
                Period("2013", freq="Y"),
                Period("2011-04", freq="M"),
            ]
        )

        ser = Series(
            [
                Period("2012", freq="Y"),
                Period("2011-01", freq="M"),
                Period("2013", freq="Y"),
                Period("2011-05", freq="M"),
            ]
        )

        exp = Series([False, False, True, False])
        tm.assert_series_equal(base == ser, exp)

        exp = Series([True, True, False, True])
        tm.assert_series_equal(base != ser, exp)

        exp = Series([False, True, False, False])
        tm.assert_series_equal(base > ser, exp)

        exp = Series([True, False, False, True])
        tm.assert_series_equal(base < ser, exp)

        exp = Series([False, True, True, False])
        tm.assert_series_equal(base >= ser, exp)

        exp = Series([True, False, True, True])
        tm.assert_series_equal(base <= ser, exp)


class TestPeriodIndexSeriesComparisonConsistency:
    """Test PeriodIndex and Period Series Ops consistency"""

    # TODO: needs parametrization+de-duplication

    def _check(self, values, func, expected):
        # Test PeriodIndex and Period Series Ops consistency

        idx = PeriodIndex(values)
        result = func(idx)

        # check that we don't pass an unwanted type to tm.assert_equal
        assert isinstance(expected, (pd.Index, np.ndarray))
        tm.assert_equal(result, expected)

        s = Series(values)
        result = func(s)

        exp = Series(expected, name=values.name)
        tm.assert_series_equal(result, exp)

    def test_pi_comp_period(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "2011-03", "2011-04"], freq="M", name="idx"
        )
        per = idx[2]

        f = lambda x: x == per
        exp = np.array([False, False, True, False], dtype=np.bool_)
        self._check(idx, f, exp)
        f = lambda x: per == x
        self._check(idx, f, exp)

        f = lambda x: x != per
        exp = np.array([True, True, False, True], dtype=np.bool_)
        self._check(idx, f, exp)
        f = lambda x: per != x
        self._check(idx, f, exp)

        f = lambda x: per >= x
        exp = np.array([True, True, True, False], dtype=np.bool_)
        self._check(idx, f, exp)

        f = lambda x: x > per
        exp = np.array([False, False, False, True], dtype=np.bool_)
        self._check(idx, f, exp)

        f = lambda x: per >= x
        exp = np.array([True, True, True, False], dtype=np.bool_)
        self._check(idx, f, exp)

    def test_pi_comp_period_nat(self):
        idx = PeriodIndex(
            ["2011-01", "NaT", "2011-03", "2011-04"], freq="M", name="idx"
        )
        per = idx[2]

        f = lambda x: x == per
        exp = np.array([False, False, True, False], dtype=np.bool_)
        self._check(idx, f, exp)
        f = lambda x: per == x
        self._check(idx, f, exp)

        f = lambda x: x == pd.NaT
        exp = np.array([False, False, False, False], dtype=np.bool_)
        self._check(idx, f, exp)
        f = lambda x: pd.NaT == x
        self._check(idx, f, exp)

        f = lambda x: x != per
        exp = np.array([True, True, False, True], dtype=np.bool_)
        self._check(idx, f, exp)
        f = lambda x: per != x
        self._check(idx, f, exp)

        f = lambda x: x != pd.NaT
        exp = np.array([True, True, True, True], dtype=np.bool_)
        self._check(idx, f, exp)
        f = lambda x: pd.NaT != x
        self._check(idx, f, exp)

        f = lambda x: per >= x
        exp = np.array([True, False, True, False], dtype=np.bool_)
        self._check(idx, f, exp)

        f = lambda x: x < per
        exp = np.array([True, False, False, False], dtype=np.bool_)
        self._check(idx, f, exp)

        f = lambda x: x > pd.NaT
        exp = np.array([False, False, False, False], dtype=np.bool_)
        self._check(idx, f, exp)

        f = lambda x: pd.NaT >= x
        exp = np.array([False, False, False, False], dtype=np.bool_)
        self._check(idx, f, exp)


# ------------------------------------------------------------------
# Arithmetic


class TestPeriodFrameArithmetic:
    def test_ops_frame_period(self):
        # GH#13043
        df = pd.DataFrame(
            {
                "A": [Period("2015-01", freq="M"), Period("2015-02", freq="M")],
                "B": [Period("2014-01", freq="M"), Period("2014-02", freq="M")],
            }
        )
        assert df["A"].dtype == "Period[M]"
        assert df["B"].dtype == "Period[M]"

        p = Period("2015-03", freq="M")
        off = p.freq
        # dtype will be object because of original dtype
        exp = pd.DataFrame(
            {
                "A": np.array([2 * off, 1 * off], dtype=object),
                "B": np.array([14 * off, 13 * off], dtype=object),
            }
        )
        tm.assert_frame_equal(p - df, exp)
        tm.assert_frame_equal(df - p, -1 * exp)

        df2 = pd.DataFrame(
            {
                "A": [Period("2015-05", freq="M"), Period("2015-06", freq="M")],
                "B": [Period("2015-05", freq="M"), Period("2015-06", freq="M")],
            }
        )
        assert df2["A"].dtype == "Period[M]"
        assert df2["B"].dtype == "Period[M]"

        exp = pd.DataFrame(
            {
                "A": np.array([4 * off, 4 * off], dtype=object),
                "B": np.array([16 * off, 16 * off], dtype=object),
            }
        )
        tm.assert_frame_equal(df2 - df, exp)
        tm.assert_frame_equal(df - df2, -1 * exp)


class TestPeriodIndexArithmetic:
    # ---------------------------------------------------------------
    # __add__/__sub__ with PeriodIndex
    # PeriodIndex + other is defined for integers and timedelta-like others
    # PeriodIndex - other is defined for integers, timedelta-like others,
    #   and PeriodIndex (with matching freq)

    def test_parr_add_iadd_parr_raises(self, box_with_array):
        rng = period_range("1/1/2000", freq="D", periods=5)
        other = period_range("1/6/2000", freq="D", periods=5)
        # TODO: parametrize over boxes for other?

        rng = tm.box_expected(rng, box_with_array)
        # An earlier implementation of PeriodIndex addition performed
        # a set operation (union).  This has since been changed to
        # raise a TypeError. See GH#14164 and GH#13077 for historical
        # reference.
        msg = r"unsupported operand type\(s\) for \+: .* and .*"
        with pytest.raises(TypeError, match=msg):
            rng + other

        with pytest.raises(TypeError, match=msg):
            rng += other

    def test_pi_sub_isub_pi(self):
        # GH#20049
        # For historical reference see GH#14164, GH#13077.
        # PeriodIndex subtraction originally performed set difference,
        # then changed to raise TypeError before being implemented in GH#20049
        rng = period_range("1/1/2000", freq="D", periods=5)
        other = period_range("1/6/2000", freq="D", periods=5)

        off = rng.freq
        expected = pd.Index([-5 * off] * 5)
        result = rng - other
        tm.assert_index_equal(result, expected)

        rng -= other
        tm.assert_index_equal(rng, expected)

    def test_pi_sub_pi_with_nat(self):
        rng = period_range("1/1/2000", freq="D", periods=5)
        other = rng[1:].insert(0, pd.NaT)
        assert other[1:].equals(rng[1:])

        result = rng - other
        off = rng.freq
        expected = pd.Index([pd.NaT, 0 * off, 0 * off, 0 * off, 0 * off])
        tm.assert_index_equal(result, expected)

    def test_parr_sub_pi_mismatched_freq(self, box_with_array, box_with_array2):
        rng = period_range("1/1/2000", freq="D", periods=5)
        other = period_range("1/6/2000", freq="h", periods=5)

        rng = tm.box_expected(rng, box_with_array)
        other = tm.box_expected(other, box_with_array2)
        msg = r"Input has different freq=[hD] from PeriodArray\(freq=[Dh]\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng - other

    @pytest.mark.parametrize("n", [1, 2, 3, 4])
    def test_sub_n_gt_1_ticks(self, tick_classes, n):
        # GH 23878
        p1_d = "19910905"
        p2_d = "19920406"
        p1 = PeriodIndex([p1_d], freq=tick_classes(n))
        p2 = PeriodIndex([p2_d], freq=tick_classes(n))

        expected = PeriodIndex([p2_d], freq=p2.freq.base) - PeriodIndex(
            [p1_d], freq=p1.freq.base
        )

        tm.assert_index_equal((p2 - p1), expected)

    @pytest.mark.parametrize("n", [1, 2, 3, 4])
    @pytest.mark.parametrize(
        "offset, kwd_name",
        [
            (pd.offsets.YearEnd, "month"),
            (pd.offsets.QuarterEnd, "startingMonth"),
            (pd.offsets.MonthEnd, None),
            (pd.offsets.Week, "weekday"),
        ],
    )
    def test_sub_n_gt_1_offsets(self, offset, kwd_name, n):
        # GH 23878
        kwds = {kwd_name: 3} if kwd_name is not None else {}
        p1_d = "19910905"
        p2_d = "19920406"
        freq = offset(n, normalize=False, **kwds)
        p1 = PeriodIndex([p1_d], freq=freq)
        p2 = PeriodIndex([p2_d], freq=freq)

        result = p2 - p1
        expected = PeriodIndex([p2_d], freq=freq.base) - PeriodIndex(
            [p1_d], freq=freq.base
        )

        tm.assert_index_equal(result, expected)

    # -------------------------------------------------------------
    # Invalid Operations

    @pytest.mark.parametrize(
        "other",
        [
            # datetime scalars
            Timestamp("2016-01-01"),
            Timestamp("2016-01-01").to_pydatetime(),
            Timestamp("2016-01-01").to_datetime64(),
            # datetime-like arrays
            pd.date_range("2016-01-01", periods=3, freq="h"),
            pd.date_range("2016-01-01", periods=3, tz="Europe/Brussels"),
            pd.date_range("2016-01-01", periods=3, freq="s")._data,
            pd.date_range("2016-01-01", periods=3, tz="Asia/Tokyo")._data,
            # Miscellaneous invalid types
            3.14,
            np.array([2.0, 3.0, 4.0]),
        ],
    )
    def test_parr_add_sub_invalid(self, other, box_with_array):
        # GH#23215
        rng = period_range("1/1/2000", freq="D", periods=3)
        rng = tm.box_expected(rng, box_with_array)

        msg = "|".join(
            [
                r"(:?cannot add PeriodArray and .*)",
                r"(:?cannot subtract .* from (:?a\s)?.*)",
                r"(:?unsupported operand type\(s\) for \+: .* and .*)",
                r"unsupported operand type\(s\) for [+-]: .* and .*",
            ]
        )
        assert_invalid_addsub_type(rng, other, msg)
        with pytest.raises(TypeError, match=msg):
            rng + other
        with pytest.raises(TypeError, match=msg):
            other + rng
        with pytest.raises(TypeError, match=msg):
            rng - other
        with pytest.raises(TypeError, match=msg):
            other - rng

    # -----------------------------------------------------------------
    # __add__/__sub__ with ndarray[datetime64] and ndarray[timedelta64]

    def test_pi_add_sub_td64_array_non_tick_raises(self):
        rng = period_range("1/1/2000", freq="Q", periods=3)
        tdi = TimedeltaIndex(["-1 Day", "-1 Day", "-1 Day"])
        tdarr = tdi.values

        msg = r"Cannot add or subtract timedelta64\[ns\] dtype from period\[Q-DEC\]"
        with pytest.raises(TypeError, match=msg):
            rng + tdarr
        with pytest.raises(TypeError, match=msg):
            tdarr + rng

        with pytest.raises(TypeError, match=msg):
            rng - tdarr
        msg = r"cannot subtract PeriodArray from TimedeltaArray"
        with pytest.raises(TypeError, match=msg):
            tdarr - rng

    def test_pi_add_sub_td64_array_tick(self):
        # PeriodIndex + Timedelta-like is allowed only with
        #   tick-like frequencies
        rng = period_range("1/1/2000", freq="90D", periods=3)
        tdi = TimedeltaIndex(["-1 Day", "-1 Day", "-1 Day"])
        tdarr = tdi.values

        expected = period_range("12/31/1999", freq="90D", periods=3)
        result = rng + tdi
        tm.assert_index_equal(result, expected)
        result = rng + tdarr
        tm.assert_index_equal(result, expected)
        result = tdi + rng
        tm.assert_index_equal(result, expected)
        result = tdarr + rng
        tm.assert_index_equal(result, expected)

        expected = period_range("1/2/2000", freq="90D", periods=3)

        result = rng - tdi
        tm.assert_index_equal(result, expected)
        result = rng - tdarr
        tm.assert_index_equal(result, expected)

        msg = r"cannot subtract .* from .*"
        with pytest.raises(TypeError, match=msg):
            tdarr - rng

        with pytest.raises(TypeError, match=msg):
            tdi - rng

    @pytest.mark.parametrize("pi_freq", ["D", "W", "Q", "h"])
    @pytest.mark.parametrize("tdi_freq", [None, "h"])
    def test_parr_sub_td64array(self, box_with_array, tdi_freq, pi_freq):
        box = box_with_array
        xbox = box if box not in [pd.array, tm.to_array] else pd.Index

        tdi = TimedeltaIndex(["1 hours", "2 hours"], freq=tdi_freq)
        dti = Timestamp("2018-03-07 17:16:40") + tdi
        pi = dti.to_period(pi_freq)

        # TODO: parametrize over box for pi?
        td64obj = tm.box_expected(tdi, box)

        if pi_freq == "h":
            result = pi - td64obj
            expected = (pi.to_timestamp("s") - tdi).to_period(pi_freq)
            expected = tm.box_expected(expected, xbox)
            tm.assert_equal(result, expected)

            # Subtract from scalar
            result = pi[0] - td64obj
            expected = (pi[0].to_timestamp("s") - tdi).to_period(pi_freq)
            expected = tm.box_expected(expected, box)
            tm.assert_equal(result, expected)

        elif pi_freq == "D":
            # Tick, but non-compatible
            msg = (
                "Cannot add/subtract timedelta-like from PeriodArray that is "
                "not an integer multiple of the PeriodArray's freq."
            )
            with pytest.raises(IncompatibleFrequency, match=msg):
                pi - td64obj

            with pytest.raises(IncompatibleFrequency, match=msg):
                pi[0] - td64obj

        else:
            # With non-Tick freq, we could not add timedelta64 array regardless
            #  of what its resolution is
            msg = "Cannot add or subtract timedelta64"
            with pytest.raises(TypeError, match=msg):
                pi - td64obj
            with pytest.raises(TypeError, match=msg):
                pi[0] - td64obj

    # -----------------------------------------------------------------
    # operations with array/Index of DateOffset objects

    @pytest.mark.parametrize("box", [np.array, pd.Index])
    def test_pi_add_offset_array(self, box):
        # GH#18849
        pi = PeriodIndex([Period("2015Q1"), Period("2016Q2")])
        offs = box(
            [
                pd.offsets.QuarterEnd(n=1, startingMonth=12),
                pd.offsets.QuarterEnd(n=-2, startingMonth=12),
            ]
        )
        expected = PeriodIndex([Period("2015Q2"), Period("2015Q4")]).astype(object)

        with tm.assert_produces_warning(PerformanceWarning):
            res = pi + offs
        tm.assert_index_equal(res, expected)

        with tm.assert_produces_warning(PerformanceWarning):
            res2 = offs + pi
        tm.assert_index_equal(res2, expected)

        unanchored = np.array([pd.offsets.Hour(n=1), pd.offsets.Minute(n=-2)])
        # addition/subtraction ops with incompatible offsets should issue
        # a PerformanceWarning and _then_ raise a TypeError.
        msg = r"Input cannot be converted to Period\(freq=Q-DEC\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            with tm.assert_produces_warning(PerformanceWarning):
                pi + unanchored
        with pytest.raises(IncompatibleFrequency, match=msg):
            with tm.assert_produces_warning(PerformanceWarning):
                unanchored + pi

    @pytest.mark.parametrize("box", [np.array, pd.Index])
    def test_pi_sub_offset_array(self, box):
        # GH#18824
        pi = PeriodIndex([Period("2015Q1"), Period("2016Q2")])
        other = box(
            [
                pd.offsets.QuarterEnd(n=1, startingMonth=12),
                pd.offsets.QuarterEnd(n=-2, startingMonth=12),
            ]
        )

        expected = PeriodIndex([pi[n] - other[n] for n in range(len(pi))])
        expected = expected.astype(object)

        with tm.assert_produces_warning(PerformanceWarning):
            res = pi - other
        tm.assert_index_equal(res, expected)

        anchored = box([pd.offsets.MonthEnd(), pd.offsets.Day(n=2)])

        # addition/subtraction ops with anchored offsets should issue
        # a PerformanceWarning and _then_ raise a TypeError.
        msg = r"Input has different freq=-1M from Period\(freq=Q-DEC\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            with tm.assert_produces_warning(PerformanceWarning):
                pi - anchored
        with pytest.raises(IncompatibleFrequency, match=msg):
            with tm.assert_produces_warning(PerformanceWarning):
                anchored - pi

    def test_pi_add_iadd_int(self, one):
        # Variants of `one` for #19012
        rng = period_range("2000-01-01 09:00", freq="h", periods=10)
        result = rng + one
        expected = period_range("2000-01-01 10:00", freq="h", periods=10)
        tm.assert_index_equal(result, expected)
        rng += one
        tm.assert_index_equal(rng, expected)

    def test_pi_sub_isub_int(self, one):
        """
        PeriodIndex.__sub__ and __isub__ with several representations of
        the integer 1, e.g. int, np.int64, np.uint8, ...
        """
        rng = period_range("2000-01-01 09:00", freq="h", periods=10)
        result = rng - one
        expected = period_range("2000-01-01 08:00", freq="h", periods=10)
        tm.assert_index_equal(result, expected)
        rng -= one
        tm.assert_index_equal(rng, expected)

    @pytest.mark.parametrize("five", [5, np.array(5, dtype=np.int64)])
    def test_pi_sub_intlike(self, five):
        rng = period_range("2007-01", periods=50)

        result = rng - five
        exp = rng + (-five)
        tm.assert_index_equal(result, exp)

    def test_pi_add_sub_int_array_freqn_gt1(self):
        # GH#47209 test adding array of ints when freq.n > 1 matches
        #  scalar behavior
        pi = period_range("2016-01-01", periods=10, freq="2D")
        arr = np.arange(10)
        result = pi + arr
        expected = pd.Index([x + y for x, y in zip(pi, arr)])
        tm.assert_index_equal(result, expected)

        result = pi - arr
        expected = pd.Index([x - y for x, y in zip(pi, arr)])
        tm.assert_index_equal(result, expected)

    def test_pi_sub_isub_offset(self):
        # offset
        # DateOffset
        rng = period_range("2014", "2024", freq="Y")
        result = rng - pd.offsets.YearEnd(5)
        expected = period_range("2009", "2019", freq="Y")
        tm.assert_index_equal(result, expected)
        rng -= pd.offsets.YearEnd(5)
        tm.assert_index_equal(rng, expected)

        rng = period_range("2014-01", "2016-12", freq="M")
        result = rng - pd.offsets.MonthEnd(5)
        expected = period_range("2013-08", "2016-07", freq="M")
        tm.assert_index_equal(result, expected)

        rng -= pd.offsets.MonthEnd(5)
        tm.assert_index_equal(rng, expected)

    @pytest.mark.parametrize("transpose", [True, False])
    def test_pi_add_offset_n_gt1(self, box_with_array, transpose):
        # GH#23215
        # add offset to PeriodIndex with freq.n > 1

        per = Period("2016-01", freq="2M")
        pi = PeriodIndex([per])

        expected = PeriodIndex(["2016-03"], freq="2M")

        pi = tm.box_expected(pi, box_with_array, transpose=transpose)
        expected = tm.box_expected(expected, box_with_array, transpose=transpose)

        result = pi + per.freq
        tm.assert_equal(result, expected)

        result = per.freq + pi
        tm.assert_equal(result, expected)

    def test_pi_add_offset_n_gt1_not_divisible(self, box_with_array):
        # GH#23215
        # PeriodIndex with freq.n > 1 add offset with offset.n % freq.n != 0
        pi = PeriodIndex(["2016-01"], freq="2M")
        expected = PeriodIndex(["2016-04"], freq="2M")

        pi = tm.box_expected(pi, box_with_array)
        expected = tm.box_expected(expected, box_with_array)

        result = pi + to_offset("3ME")
        tm.assert_equal(result, expected)

        result = to_offset("3ME") + pi
        tm.assert_equal(result, expected)

    # ---------------------------------------------------------------
    # __add__/__sub__ with integer arrays

    @pytest.mark.parametrize("int_holder", [np.array, pd.Index])
    @pytest.mark.parametrize("op", [operator.add, ops.radd])
    def test_pi_add_intarray(self, int_holder, op):
        # GH#19959
        pi = PeriodIndex([Period("2015Q1"), Period("NaT")])
        other = int_holder([4, -1])

        result = op(pi, other)
        expected = PeriodIndex([Period("2016Q1"), Period("NaT")])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("int_holder", [np.array, pd.Index])
    def test_pi_sub_intarray(self, int_holder):
        # GH#19959
        pi = PeriodIndex([Period("2015Q1"), Period("NaT")])
        other = int_holder([4, -1])

        result = pi - other
        expected = PeriodIndex([Period("2014Q1"), Period("NaT")])
        tm.assert_index_equal(result, expected)

        msg = r"bad operand type for unary -: 'PeriodArray'"
        with pytest.raises(TypeError, match=msg):
            other - pi

    # ---------------------------------------------------------------
    # Timedelta-like (timedelta, timedelta64, Timedelta, Tick)
    # TODO: Some of these are misnomers because of non-Tick DateOffsets

    def test_parr_add_timedeltalike_minute_gt1(self, three_days, box_with_array):
        # GH#23031 adding a time-delta-like offset to a PeriodArray that has
        # minute frequency with n != 1.  A more general case is tested below
        # in test_pi_add_timedeltalike_tick_gt1, but here we write out the
        # expected result more explicitly.
        other = three_days
        rng = period_range("2014-05-01", periods=3, freq="2D")
        rng = tm.box_expected(rng, box_with_array)

        expected = PeriodIndex(["2014-05-04", "2014-05-06", "2014-05-08"], freq="2D")
        expected = tm.box_expected(expected, box_with_array)

        result = rng + other
        tm.assert_equal(result, expected)

        result = other + rng
        tm.assert_equal(result, expected)

        # subtraction
        expected = PeriodIndex(["2014-04-28", "2014-04-30", "2014-05-02"], freq="2D")
        expected = tm.box_expected(expected, box_with_array)
        result = rng - other
        tm.assert_equal(result, expected)

        msg = "|".join(
            [
                r"bad operand type for unary -: 'PeriodArray'",
                r"cannot subtract PeriodArray from timedelta64\[[hD]\]",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            other - rng

    @pytest.mark.parametrize("freqstr", ["5ns", "5us", "5ms", "5s", "5min", "5h", "5d"])
    def test_parr_add_timedeltalike_tick_gt1(self, three_days, freqstr, box_with_array):
        # GH#23031 adding a time-delta-like offset to a PeriodArray that has
        # tick-like frequency with n != 1
        other = three_days
        rng = period_range("2014-05-01", periods=6, freq=freqstr)
        first = rng[0]
        rng = tm.box_expected(rng, box_with_array)

        expected = period_range(first + other, periods=6, freq=freqstr)
        expected = tm.box_expected(expected, box_with_array)

        result = rng + other
        tm.assert_equal(result, expected)

        result = other + rng
        tm.assert_equal(result, expected)

        # subtraction
        expected = period_range(first - other, periods=6, freq=freqstr)
        expected = tm.box_expected(expected, box_with_array)
        result = rng - other
        tm.assert_equal(result, expected)
        msg = "|".join(
            [
                r"bad operand type for unary -: 'PeriodArray'",
                r"cannot subtract PeriodArray from timedelta64\[[hD]\]",
            ]
        )
        with pytest.raises(TypeError, match=msg):
            other - rng

    def test_pi_add_iadd_timedeltalike_daily(self, three_days):
        # Tick
        other = three_days
        rng = period_range("2014-05-01", "2014-05-15", freq="D")
        expected = period_range("2014-05-04", "2014-05-18", freq="D")

        result = rng + other
        tm.assert_index_equal(result, expected)

        rng += other
        tm.assert_index_equal(rng, expected)

    def test_pi_sub_isub_timedeltalike_daily(self, three_days):
        # Tick-like 3 Days
        other = three_days
        rng = period_range("2014-05-01", "2014-05-15", freq="D")
        expected = period_range("2014-04-28", "2014-05-12", freq="D")

        result = rng - other
        tm.assert_index_equal(result, expected)

        rng -= other
        tm.assert_index_equal(rng, expected)

    def test_parr_add_sub_timedeltalike_freq_mismatch_daily(
        self, not_daily, box_with_array
    ):
        other = not_daily
        rng = period_range("2014-05-01", "2014-05-15", freq="D")
        rng = tm.box_expected(rng, box_with_array)

        msg = "|".join(
            [
                # non-timedelta-like DateOffset
                "Input has different freq(=.+)? from Period.*?\\(freq=D\\)",
                # timedelta/td64/Timedelta but not a multiple of 24H
                "Cannot add/subtract timedelta-like from PeriodArray that is "
                "not an integer multiple of the PeriodArray's freq.",
            ]
        )
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng + other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng += other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng - other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng -= other

    def test_pi_add_iadd_timedeltalike_hourly(self, two_hours):
        other = two_hours
        rng = period_range("2014-01-01 10:00", "2014-01-05 10:00", freq="h")
        expected = period_range("2014-01-01 12:00", "2014-01-05 12:00", freq="h")

        result = rng + other
        tm.assert_index_equal(result, expected)

        rng += other
        tm.assert_index_equal(rng, expected)

    def test_parr_add_timedeltalike_mismatched_freq_hourly(
        self, not_hourly, box_with_array
    ):
        other = not_hourly
        rng = period_range("2014-01-01 10:00", "2014-01-05 10:00", freq="h")
        rng = tm.box_expected(rng, box_with_array)
        msg = "|".join(
            [
                # non-timedelta-like DateOffset
                "Input has different freq(=.+)? from Period.*?\\(freq=h\\)",
                # timedelta/td64/Timedelta but not a multiple of 24H
                "Cannot add/subtract timedelta-like from PeriodArray that is "
                "not an integer multiple of the PeriodArray's freq.",
            ]
        )

        with pytest.raises(IncompatibleFrequency, match=msg):
            rng + other

        with pytest.raises(IncompatibleFrequency, match=msg):
            rng += other

    def test_pi_sub_isub_timedeltalike_hourly(self, two_hours):
        other = two_hours
        rng = period_range("2014-01-01 10:00", "2014-01-05 10:00", freq="h")
        expected = period_range("2014-01-01 08:00", "2014-01-05 08:00", freq="h")

        result = rng - other
        tm.assert_index_equal(result, expected)

        rng -= other
        tm.assert_index_equal(rng, expected)

    def test_add_iadd_timedeltalike_annual(self):
        # offset
        # DateOffset
        rng = period_range("2014", "2024", freq="Y")
        result = rng + pd.offsets.YearEnd(5)
        expected = period_range("2019", "2029", freq="Y")
        tm.assert_index_equal(result, expected)
        rng += pd.offsets.YearEnd(5)
        tm.assert_index_equal(rng, expected)

    def test_pi_add_sub_timedeltalike_freq_mismatch_annual(self, mismatched_freq):
        other = mismatched_freq
        rng = period_range("2014", "2024", freq="Y")
        msg = "Input has different freq(=.+)? from Period.*?\\(freq=Y-DEC\\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng + other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng += other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng - other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng -= other

    def test_pi_add_iadd_timedeltalike_M(self):
        rng = period_range("2014-01", "2016-12", freq="M")
        expected = period_range("2014-06", "2017-05", freq="M")

        result = rng + pd.offsets.MonthEnd(5)
        tm.assert_index_equal(result, expected)

        rng += pd.offsets.MonthEnd(5)
        tm.assert_index_equal(rng, expected)

    def test_pi_add_sub_timedeltalike_freq_mismatch_monthly(self, mismatched_freq):
        other = mismatched_freq
        rng = period_range("2014-01", "2016-12", freq="M")
        msg = "Input has different freq(=.+)? from Period.*?\\(freq=M\\)"
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng + other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng += other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng - other
        with pytest.raises(IncompatibleFrequency, match=msg):
            rng -= other

    @pytest.mark.parametrize("transpose", [True, False])
    def test_parr_add_sub_td64_nat(self, box_with_array, transpose):
        # GH#23320 special handling for timedelta64("NaT")
        pi = period_range("1994-04-01", periods=9, freq="19D")
        other = np.timedelta64("NaT")
        expected = PeriodIndex(["NaT"] * 9, freq="19D")

        obj = tm.box_expected(pi, box_with_array, transpose=transpose)
        expected = tm.box_expected(expected, box_with_array, transpose=transpose)

        result = obj + other
        tm.assert_equal(result, expected)
        result = other + obj
        tm.assert_equal(result, expected)
        result = obj - other
        tm.assert_equal(result, expected)
        msg = r"cannot subtract .* from .*"
        with pytest.raises(TypeError, match=msg):
            other - obj

    @pytest.mark.parametrize(
        "other",
        [
            np.array(["NaT"] * 9, dtype="m8[ns]"),
            TimedeltaArray._from_sequence(["NaT"] * 9, dtype="m8[ns]"),
        ],
    )
    def test_parr_add_sub_tdt64_nat_array(self, box_with_array, other):
        pi = period_range("1994-04-01", periods=9, freq="19D")
        expected = PeriodIndex(["NaT"] * 9, freq="19D")

        obj = tm.box_expected(pi, box_with_array)
        expected = tm.box_expected(expected, box_with_array)

        result = obj + other
        tm.assert_equal(result, expected)
        result = other + obj
        tm.assert_equal(result, expected)
        result = obj - other
        tm.assert_equal(result, expected)
        msg = r"cannot subtract .* from .*"
        with pytest.raises(TypeError, match=msg):
            other - obj

        # some but not *all* NaT
        other = other.copy()
        other[0] = np.timedelta64(0, "ns")
        expected = PeriodIndex([pi[0]] + ["NaT"] * 8, freq="19D")
        expected = tm.box_expected(expected, box_with_array)

        result = obj + other
        tm.assert_equal(result, expected)
        result = other + obj
        tm.assert_equal(result, expected)
        result = obj - other
        tm.assert_equal(result, expected)
        with pytest.raises(TypeError, match=msg):
            other - obj

    # ---------------------------------------------------------------
    # Unsorted

    def test_parr_add_sub_index(self):
        # Check that PeriodArray defers to Index on arithmetic ops
        pi = period_range("2000-12-31", periods=3)
        parr = pi.array

        result = parr - pi
        expected = pi - pi
        tm.assert_index_equal(result, expected)

    def test_parr_add_sub_object_array(self):
        pi = period_range("2000-12-31", periods=3, freq="D")
        parr = pi.array

        other = np.array([Timedelta(days=1), pd.offsets.Day(2), 3])

        with tm.assert_produces_warning(PerformanceWarning):
            result = parr + other

        expected = PeriodIndex(
            ["2001-01-01", "2001-01-03", "2001-01-05"], freq="D"
        )._data.astype(object)
        tm.assert_equal(result, expected)

        with tm.assert_produces_warning(PerformanceWarning):
            result = parr - other

        expected = PeriodIndex(["2000-12-30"] * 3, freq="D")._data.astype(object)
        tm.assert_equal(result, expected)

    def test_period_add_timestamp_raises(self, box_with_array):
        # GH#17983
        ts = Timestamp("2017")
        per = Period("2017", freq="M")

        arr = pd.Index([per], dtype="Period[M]")
        arr = tm.box_expected(arr, box_with_array)

        msg = "cannot add PeriodArray and Timestamp"
        with pytest.raises(TypeError, match=msg):
            arr + ts
        with pytest.raises(TypeError, match=msg):
            ts + arr
        msg = "cannot add PeriodArray and DatetimeArray"
        with pytest.raises(TypeError, match=msg):
            arr + Series([ts])
        with pytest.raises(TypeError, match=msg):
            Series([ts]) + arr
        with pytest.raises(TypeError, match=msg):
            arr + pd.Index([ts])
        with pytest.raises(TypeError, match=msg):
            pd.Index([ts]) + arr

        if box_with_array is pd.DataFrame:
            msg = "cannot add PeriodArray and DatetimeArray"
        else:
            msg = r"unsupported operand type\(s\) for \+: 'Period' and 'DatetimeArray"
        with pytest.raises(TypeError, match=msg):
            arr + pd.DataFrame([ts])
        if box_with_array is pd.DataFrame:
            msg = "cannot add PeriodArray and DatetimeArray"
        else:
            msg = r"unsupported operand type\(s\) for \+: 'DatetimeArray' and 'Period'"
        with pytest.raises(TypeError, match=msg):
            pd.DataFrame([ts]) + arr


class TestPeriodSeriesArithmetic:
    def test_parr_add_timedeltalike_scalar(self, three_days, box_with_array):
        # GH#13043
        ser = Series(
            [Period("2015-01-01", freq="D"), Period("2015-01-02", freq="D")],
            name="xxx",
        )
        assert ser.dtype == "Period[D]"

        expected = Series(
            [Period("2015-01-04", freq="D"), Period("2015-01-05", freq="D")],
            name="xxx",
        )

        obj = tm.box_expected(ser, box_with_array)
        if box_with_array is pd.DataFrame:
            assert (obj.dtypes == "Period[D]").all()

        expected = tm.box_expected(expected, box_with_array)

        result = obj + three_days
        tm.assert_equal(result, expected)

        result = three_days + obj
        tm.assert_equal(result, expected)

    def test_ops_series_period(self):
        # GH#13043
        ser = Series(
            [Period("2015-01-01", freq="D"), Period("2015-01-02", freq="D")],
            name="xxx",
        )
        assert ser.dtype == "Period[D]"

        per = Period("2015-01-10", freq="D")
        off = per.freq
        # dtype will be object because of original dtype
        expected = Series([9 * off, 8 * off], name="xxx", dtype=object)
        tm.assert_series_equal(per - ser, expected)
        tm.assert_series_equal(ser - per, -1 * expected)

        s2 = Series(
            [Period("2015-01-05", freq="D"), Period("2015-01-04", freq="D")],
            name="xxx",
        )
        assert s2.dtype == "Period[D]"

        expected = Series([4 * off, 2 * off], name="xxx", dtype=object)
        tm.assert_series_equal(s2 - ser, expected)
        tm.assert_series_equal(ser - s2, -1 * expected)


class TestPeriodIndexSeriesMethods:
    """Test PeriodIndex and Period Series Ops consistency"""

    def _check(self, values, func, expected):
        idx = PeriodIndex(values)
        result = func(idx)
        tm.assert_equal(result, expected)

        ser = Series(values)
        result = func(ser)

        exp = Series(expected, name=values.name)
        tm.assert_series_equal(result, exp)

    def test_pi_ops(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "2011-03", "2011-04"], freq="M", name="idx"
        )

        expected = PeriodIndex(
            ["2011-03", "2011-04", "2011-05", "2011-06"], freq="M", name="idx"
        )

        self._check(idx, lambda x: x + 2, expected)
        self._check(idx, lambda x: 2 + x, expected)

        self._check(idx + 2, lambda x: x - 2, idx)

        result = idx - Period("2011-01", freq="M")
        off = idx.freq
        exp = pd.Index([0 * off, 1 * off, 2 * off, 3 * off], name="idx")
        tm.assert_index_equal(result, exp)

        result = Period("2011-01", freq="M") - idx
        exp = pd.Index([0 * off, -1 * off, -2 * off, -3 * off], name="idx")
        tm.assert_index_equal(result, exp)

    @pytest.mark.parametrize("ng", ["str", 1.5])
    @pytest.mark.parametrize(
        "func",
        [
            lambda obj, ng: obj + ng,
            lambda obj, ng: ng + obj,
            lambda obj, ng: obj - ng,
            lambda obj, ng: ng - obj,
            lambda obj, ng: np.add(obj, ng),
            lambda obj, ng: np.add(ng, obj),
            lambda obj, ng: np.subtract(obj, ng),
            lambda obj, ng: np.subtract(ng, obj),
        ],
    )
    def test_parr_ops_errors(self, ng, func, box_with_array):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "2011-03", "2011-04"], freq="M", name="idx"
        )
        obj = tm.box_expected(idx, box_with_array)
        msg = "|".join(
            [
                r"unsupported operand type\(s\)",
                "can only concatenate",
                r"must be str",
                "object to str implicitly",
            ]
        )

        with pytest.raises(TypeError, match=msg):
            func(obj, ng)

    def test_pi_ops_nat(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2011-04"], freq="M", name="idx"
        )
        expected = PeriodIndex(
            ["2011-03", "2011-04", "NaT", "2011-06"], freq="M", name="idx"
        )

        self._check(idx, lambda x: x + 2, expected)
        self._check(idx, lambda x: 2 + x, expected)
        self._check(idx, lambda x: np.add(x, 2), expected)

        self._check(idx + 2, lambda x: x - 2, idx)
        self._check(idx + 2, lambda x: np.subtract(x, 2), idx)

        # freq with mult
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2011-04"], freq="2M", name="idx"
        )
        expected = PeriodIndex(
            ["2011-07", "2011-08", "NaT", "2011-10"], freq="2M", name="idx"
        )

        self._check(idx, lambda x: x + 3, expected)
        self._check(idx, lambda x: 3 + x, expected)
        self._check(idx, lambda x: np.add(x, 3), expected)

        self._check(idx + 3, lambda x: x - 3, idx)
        self._check(idx + 3, lambda x: np.subtract(x, 3), idx)

    def test_pi_ops_array_int(self):
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2011-04"], freq="M", name="idx"
        )
        f = lambda x: x + np.array([1, 2, 3, 4])
        exp = PeriodIndex(
            ["2011-02", "2011-04", "NaT", "2011-08"], freq="M", name="idx"
        )
        self._check(idx, f, exp)

        f = lambda x: np.add(x, np.array([4, -1, 1, 2]))
        exp = PeriodIndex(
            ["2011-05", "2011-01", "NaT", "2011-06"], freq="M", name="idx"
        )
        self._check(idx, f, exp)

        f = lambda x: x - np.array([1, 2, 3, 4])
        exp = PeriodIndex(
            ["2010-12", "2010-12", "NaT", "2010-12"], freq="M", name="idx"
        )
        self._check(idx, f, exp)

        f = lambda x: np.subtract(x, np.array([3, 2, 3, -2]))
        exp = PeriodIndex(
            ["2010-10", "2010-12", "NaT", "2011-06"], freq="M", name="idx"
        )
        self._check(idx, f, exp)

    def test_pi_ops_offset(self):
        idx = PeriodIndex(
            ["2011-01-01", "2011-02-01", "2011-03-01", "2011-04-01"],
            freq="D",
            name="idx",
        )
        f = lambda x: x + pd.offsets.Day()
        exp = PeriodIndex(
            ["2011-01-02", "2011-02-02", "2011-03-02", "2011-04-02"],
            freq="D",
            name="idx",
        )
        self._check(idx, f, exp)

        f = lambda x: x + pd.offsets.Day(2)
        exp = PeriodIndex(
            ["2011-01-03", "2011-02-03", "2011-03-03", "2011-04-03"],
            freq="D",
            name="idx",
        )
        self._check(idx, f, exp)

        f = lambda x: x - pd.offsets.Day(2)
        exp = PeriodIndex(
            ["2010-12-30", "2011-01-30", "2011-02-27", "2011-03-30"],
            freq="D",
            name="idx",
        )
        self._check(idx, f, exp)

    def test_pi_offset_errors(self):
        idx = PeriodIndex(
            ["2011-01-01", "2011-02-01", "2011-03-01", "2011-04-01"],
            freq="D",
            name="idx",
        )
        ser = Series(idx)

        msg = (
            "Cannot add/subtract timedelta-like from PeriodArray that is not "
            "an integer multiple of the PeriodArray's freq"
        )
        for obj in [idx, ser]:
            with pytest.raises(IncompatibleFrequency, match=msg):
                obj + pd.offsets.Hour(2)

            with pytest.raises(IncompatibleFrequency, match=msg):
                pd.offsets.Hour(2) + obj

            with pytest.raises(IncompatibleFrequency, match=msg):
                obj - pd.offsets.Hour(2)

    def test_pi_sub_period(self):
        # GH#13071
        idx = PeriodIndex(
            ["2011-01", "2011-02", "2011-03", "2011-04"], freq="M", name="idx"
        )

        result = idx - Period("2012-01", freq="M")
        off = idx.freq
        exp = pd.Index([-12 * off, -11 * off, -10 * off, -9 * off], name="idx")
        tm.assert_index_equal(result, exp)

        result = np.subtract(idx, Period("2012-01", freq="M"))
        tm.assert_index_equal(result, exp)

        result = Period("2012-01", freq="M") - idx
        exp = pd.Index([12 * off, 11 * off, 10 * off, 9 * off], name="idx")
        tm.assert_index_equal(result, exp)

        result = np.subtract(Period("2012-01", freq="M"), idx)
        tm.assert_index_equal(result, exp)

        exp = TimedeltaIndex([np.nan, np.nan, np.nan, np.nan], name="idx")
        result = idx - Period("NaT", freq="M")
        tm.assert_index_equal(result, exp)
        assert result.freq == exp.freq

        result = Period("NaT", freq="M") - idx
        tm.assert_index_equal(result, exp)
        assert result.freq == exp.freq

    def test_pi_sub_pdnat(self):
        # GH#13071, GH#19389
        idx = PeriodIndex(
            ["2011-01", "2011-02", "NaT", "2011-04"], freq="M", name="idx"
        )
        exp = TimedeltaIndex([pd.NaT] * 4, name="idx")
        tm.assert_index_equal(pd.NaT - idx, exp)
        tm.assert_index_equal(idx - pd.NaT, exp)

    def test_pi_sub_period_nat(self):
        # GH#13071
        idx = PeriodIndex(
            ["2011-01", "NaT", "2011-03", "2011-04"], freq="M", name="idx"
        )

        result = idx - Period("2012-01", freq="M")
        off = idx.freq
        exp = pd.Index([-12 * off, pd.NaT, -10 * off, -9 * off], name="idx")
        tm.assert_index_equal(result, exp)

        result = Period("2012-01", freq="M") - idx
        exp = pd.Index([12 * off, pd.NaT, 10 * off, 9 * off], name="idx")
        tm.assert_index_equal(result, exp)

        exp = TimedeltaIndex([np.nan, np.nan, np.nan, np.nan], name="idx")
        tm.assert_index_equal(idx - Period("NaT", freq="M"), exp)
        tm.assert_index_equal(Period("NaT", freq="M") - idx, exp)
