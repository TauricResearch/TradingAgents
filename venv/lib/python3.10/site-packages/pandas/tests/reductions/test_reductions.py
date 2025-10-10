from datetime import (
    datetime,
    timedelta,
)
from decimal import Decimal

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    DatetimeIndex,
    Index,
    NaT,
    Period,
    PeriodIndex,
    RangeIndex,
    Series,
    Timedelta,
    TimedeltaIndex,
    Timestamp,
    date_range,
    isna,
    period_range,
    timedelta_range,
    to_timedelta,
)
import pandas._testing as tm
from pandas.core import nanops
from pandas.core.arrays.string_arrow import ArrowStringArrayNumpySemantics


def get_objs():
    indexes = [
        Index([True, False] * 5, name="a"),
        Index(np.arange(10), dtype=np.int64, name="a"),
        Index(np.arange(10), dtype=np.float64, name="a"),
        DatetimeIndex(date_range("2020-01-01", periods=10), name="a"),
        DatetimeIndex(date_range("2020-01-01", periods=10), name="a").tz_localize(
            tz="US/Eastern"
        ),
        PeriodIndex(period_range("2020-01-01", periods=10, freq="D"), name="a"),
        Index([str(i) for i in range(10)], name="a"),
    ]

    arr = np.random.default_rng(2).standard_normal(10)
    series = [Series(arr, index=idx, name="a") for idx in indexes]

    objs = indexes + series
    return objs


class TestReductions:
    @pytest.mark.filterwarnings(
        "ignore:Period with BDay freq is deprecated:FutureWarning"
    )
    @pytest.mark.parametrize("opname", ["max", "min"])
    @pytest.mark.parametrize("obj", get_objs())
    def test_ops(self, opname, obj):
        result = getattr(obj, opname)()
        if not isinstance(obj, PeriodIndex):
            if isinstance(obj.values, ArrowStringArrayNumpySemantics):
                # max not on the interface
                expected = getattr(np.array(obj.values), opname)()
            else:
                expected = getattr(obj.values, opname)()
        else:
            expected = Period(ordinal=getattr(obj.asi8, opname)(), freq=obj.freq)

        if getattr(obj, "tz", None) is not None:
            # We need to de-localize before comparing to the numpy-produced result
            expected = expected.astype("M8[ns]").astype("int64")
            assert result._value == expected
        else:
            assert result == expected

    @pytest.mark.parametrize("opname", ["max", "min"])
    @pytest.mark.parametrize(
        "dtype, val",
        [
            ("object", 2.0),
            ("float64", 2.0),
            ("datetime64[ns]", datetime(2011, 11, 1)),
            ("Int64", 2),
            ("boolean", True),
        ],
    )
    def test_nanminmax(self, opname, dtype, val, index_or_series):
        # GH#7261
        klass = index_or_series

        def check_missing(res):
            if dtype == "datetime64[ns]":
                return res is NaT
            elif dtype in ["Int64", "boolean"]:
                return res is pd.NA
            else:
                return isna(res)

        obj = klass([None], dtype=dtype)
        assert check_missing(getattr(obj, opname)())
        assert check_missing(getattr(obj, opname)(skipna=False))

        obj = klass([], dtype=dtype)
        assert check_missing(getattr(obj, opname)())
        assert check_missing(getattr(obj, opname)(skipna=False))

        if dtype == "object":
            # generic test with object only works for empty / all NaN
            return

        obj = klass([None, val], dtype=dtype)
        assert getattr(obj, opname)() == val
        assert check_missing(getattr(obj, opname)(skipna=False))

        obj = klass([None, val, None], dtype=dtype)
        assert getattr(obj, opname)() == val
        assert check_missing(getattr(obj, opname)(skipna=False))

    @pytest.mark.parametrize("opname", ["max", "min"])
    def test_nanargminmax(self, opname, index_or_series):
        # GH#7261
        klass = index_or_series
        arg_op = "arg" + opname if klass is Index else "idx" + opname

        obj = klass([NaT, datetime(2011, 11, 1)])
        assert getattr(obj, arg_op)() == 1

        msg = (
            "The behavior of (DatetimeIndex|Series).argmax/argmin with "
            "skipna=False and NAs"
        )
        if klass is Series:
            msg = "The behavior of Series.(idxmax|idxmin) with all-NA"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = getattr(obj, arg_op)(skipna=False)
        if klass is Series:
            assert np.isnan(result)
        else:
            assert result == -1

        obj = klass([NaT, datetime(2011, 11, 1), NaT])
        # check DatetimeIndex non-monotonic path
        assert getattr(obj, arg_op)() == 1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = getattr(obj, arg_op)(skipna=False)
        if klass is Series:
            assert np.isnan(result)
        else:
            assert result == -1

    @pytest.mark.parametrize("opname", ["max", "min"])
    @pytest.mark.parametrize("dtype", ["M8[ns]", "datetime64[ns, UTC]"])
    def test_nanops_empty_object(self, opname, index_or_series, dtype):
        klass = index_or_series
        arg_op = "arg" + opname if klass is Index else "idx" + opname

        obj = klass([], dtype=dtype)

        assert getattr(obj, opname)() is NaT
        assert getattr(obj, opname)(skipna=False) is NaT

        with pytest.raises(ValueError, match="empty sequence"):
            getattr(obj, arg_op)()
        with pytest.raises(ValueError, match="empty sequence"):
            getattr(obj, arg_op)(skipna=False)

    def test_argminmax(self):
        obj = Index(np.arange(5, dtype="int64"))
        assert obj.argmin() == 0
        assert obj.argmax() == 4

        obj = Index([np.nan, 1, np.nan, 2])
        assert obj.argmin() == 1
        assert obj.argmax() == 3
        msg = "The behavior of Index.argmax/argmin with skipna=False and NAs"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmin(skipna=False) == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmax(skipna=False) == -1

        obj = Index([np.nan])
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmin() == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmax() == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmin(skipna=False) == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmax(skipna=False) == -1

        msg = "The behavior of DatetimeIndex.argmax/argmin with skipna=False and NAs"
        obj = Index([NaT, datetime(2011, 11, 1), datetime(2011, 11, 2), NaT])
        assert obj.argmin() == 1
        assert obj.argmax() == 2
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmin(skipna=False) == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmax(skipna=False) == -1

        obj = Index([NaT])
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmin() == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmax() == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmin(skipna=False) == -1
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert obj.argmax(skipna=False) == -1

    @pytest.mark.parametrize("op, expected_col", [["max", "a"], ["min", "b"]])
    def test_same_tz_min_max_axis_1(self, op, expected_col):
        # GH 10390
        df = DataFrame(
            date_range("2016-01-01 00:00:00", periods=3, tz="UTC"), columns=["a"]
        )
        df["b"] = df.a.subtract(Timedelta(seconds=3600))
        result = getattr(df, op)(axis=1)
        expected = df[expected_col].rename(None)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("func", ["maximum", "minimum"])
    def test_numpy_reduction_with_tz_aware_dtype(self, tz_aware_fixture, func):
        # GH 15552
        tz = tz_aware_fixture
        arg = pd.to_datetime(["2019"]).tz_localize(tz)
        expected = Series(arg)
        result = getattr(np, func)(expected, expected)
        tm.assert_series_equal(result, expected)

    def test_nan_int_timedelta_sum(self):
        # GH 27185
        df = DataFrame(
            {
                "A": Series([1, 2, NaT], dtype="timedelta64[ns]"),
                "B": Series([1, 2, np.nan], dtype="Int64"),
            }
        )
        expected = Series({"A": Timedelta(3), "B": 3})
        result = df.sum()
        tm.assert_series_equal(result, expected)


class TestIndexReductions:
    # Note: the name TestIndexReductions indicates these tests
    #  were moved from a Index-specific test file, _not_ that these tests are
    #  intended long-term to be Index-specific

    @pytest.mark.parametrize(
        "start,stop,step",
        [
            (0, 400, 3),
            (500, 0, -6),
            (-(10**6), 10**6, 4),
            (10**6, -(10**6), -4),
            (0, 10, 20),
        ],
    )
    def test_max_min_range(self, start, stop, step):
        # GH#17607
        idx = RangeIndex(start, stop, step)
        expected = idx._values.max()
        result = idx.max()
        assert result == expected

        # skipna should be irrelevant since RangeIndex should never have NAs
        result2 = idx.max(skipna=False)
        assert result2 == expected

        expected = idx._values.min()
        result = idx.min()
        assert result == expected

        # skipna should be irrelevant since RangeIndex should never have NAs
        result2 = idx.min(skipna=False)
        assert result2 == expected

        # empty
        idx = RangeIndex(start, stop, -step)
        assert isna(idx.max())
        assert isna(idx.min())

    def test_minmax_timedelta64(self):
        # monotonic
        idx1 = TimedeltaIndex(["1 days", "2 days", "3 days"])
        assert idx1.is_monotonic_increasing

        # non-monotonic
        idx2 = TimedeltaIndex(["1 days", np.nan, "3 days", "NaT"])
        assert not idx2.is_monotonic_increasing

        for idx in [idx1, idx2]:
            assert idx.min() == Timedelta("1 days")
            assert idx.max() == Timedelta("3 days")
            assert idx.argmin() == 0
            assert idx.argmax() == 2

    @pytest.mark.parametrize("op", ["min", "max"])
    def test_minmax_timedelta_empty_or_na(self, op):
        # Return NaT
        obj = TimedeltaIndex([])
        assert getattr(obj, op)() is NaT

        obj = TimedeltaIndex([NaT])
        assert getattr(obj, op)() is NaT

        obj = TimedeltaIndex([NaT, NaT, NaT])
        assert getattr(obj, op)() is NaT

    def test_numpy_minmax_timedelta64(self):
        td = timedelta_range("16815 days", "16820 days", freq="D")

        assert np.min(td) == Timedelta("16815 days")
        assert np.max(td) == Timedelta("16820 days")

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.min(td, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.max(td, out=0)

        assert np.argmin(td) == 0
        assert np.argmax(td) == 5

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.argmin(td, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.argmax(td, out=0)

    def test_timedelta_ops(self):
        # GH#4984
        # make sure ops return Timedelta
        s = Series(
            [Timestamp("20130101") + timedelta(seconds=i * i) for i in range(10)]
        )
        td = s.diff()

        result = td.mean()
        expected = to_timedelta(timedelta(seconds=9))
        assert result == expected

        result = td.to_frame().mean()
        assert result[0] == expected

        result = td.quantile(0.1)
        expected = Timedelta(np.timedelta64(2600, "ms"))
        assert result == expected

        result = td.median()
        expected = to_timedelta("00:00:09")
        assert result == expected

        result = td.to_frame().median()
        assert result[0] == expected

        # GH#6462
        # consistency in returned values for sum
        result = td.sum()
        expected = to_timedelta("00:01:21")
        assert result == expected

        result = td.to_frame().sum()
        assert result[0] == expected

        # std
        result = td.std()
        expected = to_timedelta(Series(td.dropna().values).std())
        assert result == expected

        result = td.to_frame().std()
        assert result[0] == expected

        # GH#10040
        # make sure NaT is properly handled by median()
        s = Series([Timestamp("2015-02-03"), Timestamp("2015-02-07")])
        assert s.diff().median() == timedelta(days=4)

        s = Series(
            [Timestamp("2015-02-03"), Timestamp("2015-02-07"), Timestamp("2015-02-15")]
        )
        assert s.diff().median() == timedelta(days=6)

    @pytest.mark.parametrize("opname", ["skew", "kurt", "sem", "prod", "var"])
    def test_invalid_td64_reductions(self, opname):
        s = Series(
            [Timestamp("20130101") + timedelta(seconds=i * i) for i in range(10)]
        )
        td = s.diff()

        msg = "|".join(
            [
                f"reduction operation '{opname}' not allowed for this dtype",
                rf"cannot perform {opname} with type timedelta64\[ns\]",
                f"does not support reduction '{opname}'",
            ]
        )

        with pytest.raises(TypeError, match=msg):
            getattr(td, opname)()

        with pytest.raises(TypeError, match=msg):
            getattr(td.to_frame(), opname)(numeric_only=False)

    def test_minmax_tz(self, tz_naive_fixture):
        tz = tz_naive_fixture
        # monotonic
        idx1 = DatetimeIndex(["2011-01-01", "2011-01-02", "2011-01-03"], tz=tz)
        assert idx1.is_monotonic_increasing

        # non-monotonic
        idx2 = DatetimeIndex(
            ["2011-01-01", NaT, "2011-01-03", "2011-01-02", NaT], tz=tz
        )
        assert not idx2.is_monotonic_increasing

        for idx in [idx1, idx2]:
            assert idx.min() == Timestamp("2011-01-01", tz=tz)
            assert idx.max() == Timestamp("2011-01-03", tz=tz)
            assert idx.argmin() == 0
            assert idx.argmax() == 2

    @pytest.mark.parametrize("op", ["min", "max"])
    def test_minmax_nat_datetime64(self, op):
        # Return NaT
        obj = DatetimeIndex([])
        assert isna(getattr(obj, op)())

        obj = DatetimeIndex([NaT])
        assert isna(getattr(obj, op)())

        obj = DatetimeIndex([NaT, NaT, NaT])
        assert isna(getattr(obj, op)())

    def test_numpy_minmax_integer(self):
        # GH#26125
        idx = Index([1, 2, 3])

        expected = idx.values.max()
        result = np.max(idx)
        assert result == expected

        expected = idx.values.min()
        result = np.min(idx)
        assert result == expected

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.min(idx, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.max(idx, out=0)

        expected = idx.values.argmax()
        result = np.argmax(idx)
        assert result == expected

        expected = idx.values.argmin()
        result = np.argmin(idx)
        assert result == expected

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.argmin(idx, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.argmax(idx, out=0)

    def test_numpy_minmax_range(self):
        # GH#26125
        idx = RangeIndex(0, 10, 3)

        result = np.max(idx)
        assert result == 9

        result = np.min(idx)
        assert result == 0

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.min(idx, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.max(idx, out=0)

        # No need to test again argmax/argmin compat since the implementation
        # is the same as basic integer index

    def test_numpy_minmax_datetime64(self):
        dr = date_range(start="2016-01-15", end="2016-01-20")

        assert np.min(dr) == Timestamp("2016-01-15 00:00:00")
        assert np.max(dr) == Timestamp("2016-01-20 00:00:00")

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.min(dr, out=0)

        with pytest.raises(ValueError, match=errmsg):
            np.max(dr, out=0)

        assert np.argmin(dr) == 0
        assert np.argmax(dr) == 5

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.argmin(dr, out=0)

        with pytest.raises(ValueError, match=errmsg):
            np.argmax(dr, out=0)

    def test_minmax_period(self):
        # monotonic
        idx1 = PeriodIndex([NaT, "2011-01-01", "2011-01-02", "2011-01-03"], freq="D")
        assert not idx1.is_monotonic_increasing
        assert idx1[1:].is_monotonic_increasing

        # non-monotonic
        idx2 = PeriodIndex(
            ["2011-01-01", NaT, "2011-01-03", "2011-01-02", NaT], freq="D"
        )
        assert not idx2.is_monotonic_increasing

        for idx in [idx1, idx2]:
            assert idx.min() == Period("2011-01-01", freq="D")
            assert idx.max() == Period("2011-01-03", freq="D")
        assert idx1.argmin() == 1
        assert idx2.argmin() == 0
        assert idx1.argmax() == 3
        assert idx2.argmax() == 2

    @pytest.mark.parametrize("op", ["min", "max"])
    @pytest.mark.parametrize("data", [[], [NaT], [NaT, NaT, NaT]])
    def test_minmax_period_empty_nat(self, op, data):
        # Return NaT
        obj = PeriodIndex(data, freq="M")
        result = getattr(obj, op)()
        assert result is NaT

    def test_numpy_minmax_period(self):
        pr = period_range(start="2016-01-15", end="2016-01-20")

        assert np.min(pr) == Period("2016-01-15", freq="D")
        assert np.max(pr) == Period("2016-01-20", freq="D")

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.min(pr, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.max(pr, out=0)

        assert np.argmin(pr) == 0
        assert np.argmax(pr) == 5

        errmsg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=errmsg):
            np.argmin(pr, out=0)
        with pytest.raises(ValueError, match=errmsg):
            np.argmax(pr, out=0)

    def test_min_max_categorical(self):
        ci = pd.CategoricalIndex(list("aabbca"), categories=list("cab"), ordered=False)
        msg = (
            r"Categorical is not ordered for operation min\n"
            r"you can use .as_ordered\(\) to change the Categorical to an ordered one\n"
        )
        with pytest.raises(TypeError, match=msg):
            ci.min()
        msg = (
            r"Categorical is not ordered for operation max\n"
            r"you can use .as_ordered\(\) to change the Categorical to an ordered one\n"
        )
        with pytest.raises(TypeError, match=msg):
            ci.max()

        ci = pd.CategoricalIndex(list("aabbca"), categories=list("cab"), ordered=True)
        assert ci.min() == "c"
        assert ci.max() == "b"


class TestSeriesReductions:
    # Note: the name TestSeriesReductions indicates these tests
    #  were moved from a series-specific test file, _not_ that these tests are
    #  intended long-term to be series-specific

    def test_sum_inf(self):
        s = Series(np.random.default_rng(2).standard_normal(10))
        s2 = s.copy()

        s[5:8] = np.inf
        s2[5:8] = np.nan

        assert np.isinf(s.sum())

        arr = np.random.default_rng(2).standard_normal((100, 100)).astype("f4")
        arr[:, 2] = np.inf

        msg = "use_inf_as_na option is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            with pd.option_context("mode.use_inf_as_na", True):
                tm.assert_almost_equal(s.sum(), s2.sum())

        res = nanops.nansum(arr, axis=1)
        assert np.isinf(res).all()

    @pytest.mark.parametrize(
        "dtype", ["float64", "Float32", "Int64", "boolean", "object"]
    )
    @pytest.mark.parametrize("use_bottleneck", [True, False])
    @pytest.mark.parametrize("method, unit", [("sum", 0.0), ("prod", 1.0)])
    def test_empty(self, method, unit, use_bottleneck, dtype):
        with pd.option_context("use_bottleneck", use_bottleneck):
            # GH#9422 / GH#18921
            # Entirely empty
            s = Series([], dtype=dtype)
            # NA by default
            result = getattr(s, method)()
            assert result == unit

            # Explicit
            result = getattr(s, method)(min_count=0)
            assert result == unit

            result = getattr(s, method)(min_count=1)
            assert isna(result)

            # Skipna, default
            result = getattr(s, method)(skipna=True)
            result == unit

            # Skipna, explicit
            result = getattr(s, method)(skipna=True, min_count=0)
            assert result == unit

            result = getattr(s, method)(skipna=True, min_count=1)
            assert isna(result)

            result = getattr(s, method)(skipna=False, min_count=0)
            assert result == unit

            result = getattr(s, method)(skipna=False, min_count=1)
            assert isna(result)

            # All-NA
            s = Series([np.nan], dtype=dtype)
            # NA by default
            result = getattr(s, method)()
            assert result == unit

            # Explicit
            result = getattr(s, method)(min_count=0)
            assert result == unit

            result = getattr(s, method)(min_count=1)
            assert isna(result)

            # Skipna, default
            result = getattr(s, method)(skipna=True)
            result == unit

            # skipna, explicit
            result = getattr(s, method)(skipna=True, min_count=0)
            assert result == unit

            result = getattr(s, method)(skipna=True, min_count=1)
            assert isna(result)

            # Mix of valid, empty
            s = Series([np.nan, 1], dtype=dtype)
            # Default
            result = getattr(s, method)()
            assert result == 1.0

            # Explicit
            result = getattr(s, method)(min_count=0)
            assert result == 1.0

            result = getattr(s, method)(min_count=1)
            assert result == 1.0

            # Skipna
            result = getattr(s, method)(skipna=True)
            assert result == 1.0

            result = getattr(s, method)(skipna=True, min_count=0)
            assert result == 1.0

            # GH#844 (changed in GH#9422)
            df = DataFrame(np.empty((10, 0)), dtype=dtype)
            assert (getattr(df, method)(1) == unit).all()

            s = Series([1], dtype=dtype)
            result = getattr(s, method)(min_count=2)
            assert isna(result)

            result = getattr(s, method)(skipna=False, min_count=2)
            assert isna(result)

            s = Series([np.nan], dtype=dtype)
            result = getattr(s, method)(min_count=2)
            assert isna(result)

            s = Series([np.nan, 1], dtype=dtype)
            result = getattr(s, method)(min_count=2)
            assert isna(result)

    @pytest.mark.parametrize("method", ["mean", "var"])
    @pytest.mark.parametrize("dtype", ["Float64", "Int64", "boolean"])
    def test_ops_consistency_on_empty_nullable(self, method, dtype):
        # GH#34814
        # consistency for nullable dtypes on empty or ALL-NA mean

        # empty series
        eser = Series([], dtype=dtype)
        result = getattr(eser, method)()
        assert result is pd.NA

        # ALL-NA series
        nser = Series([np.nan], dtype=dtype)
        result = getattr(nser, method)()
        assert result is pd.NA

    @pytest.mark.parametrize("method", ["mean", "median", "std", "var"])
    def test_ops_consistency_on_empty(self, method):
        # GH#7869
        # consistency on empty

        # float
        result = getattr(Series(dtype=float), method)()
        assert isna(result)

        # timedelta64[ns]
        tdser = Series([], dtype="m8[ns]")
        if method == "var":
            msg = "|".join(
                [
                    "operation 'var' not allowed",
                    r"cannot perform var with type timedelta64\[ns\]",
                    "does not support reduction 'var'",
                ]
            )
            with pytest.raises(TypeError, match=msg):
                getattr(tdser, method)()
        else:
            result = getattr(tdser, method)()
            assert result is NaT

    def test_nansum_buglet(self):
        ser = Series([1.0, np.nan], index=[0, 1])
        result = np.nansum(ser)
        tm.assert_almost_equal(result, 1)

    @pytest.mark.parametrize("use_bottleneck", [True, False])
    @pytest.mark.parametrize("dtype", ["int32", "int64"])
    def test_sum_overflow_int(self, use_bottleneck, dtype):
        with pd.option_context("use_bottleneck", use_bottleneck):
            # GH#6915
            # overflowing on the smaller int dtypes
            v = np.arange(5000000, dtype=dtype)
            s = Series(v)

            result = s.sum(skipna=False)
            assert int(result) == v.sum(dtype="int64")
            result = s.min(skipna=False)
            assert int(result) == 0
            result = s.max(skipna=False)
            assert int(result) == v[-1]

    @pytest.mark.parametrize("use_bottleneck", [True, False])
    @pytest.mark.parametrize("dtype", ["float32", "float64"])
    def test_sum_overflow_float(self, use_bottleneck, dtype):
        with pd.option_context("use_bottleneck", use_bottleneck):
            v = np.arange(5000000, dtype=dtype)
            s = Series(v)

            result = s.sum(skipna=False)
            assert result == v.sum(dtype=dtype)
            result = s.min(skipna=False)
            assert np.allclose(float(result), 0.0)
            result = s.max(skipna=False)
            assert np.allclose(float(result), v[-1])

    def test_mean_masked_overflow(self):
        # GH#48378
        val = 100_000_000_000_000_000
        n_elements = 100
        na = np.array([val] * n_elements)
        ser = Series([val] * n_elements, dtype="Int64")

        result_numpy = np.mean(na)
        result_masked = ser.mean()
        assert result_masked - result_numpy == 0
        assert result_masked == 1e17

    @pytest.mark.parametrize("ddof, exp", [(1, 2.5), (0, 2.0)])
    def test_var_masked_array(self, ddof, exp):
        # GH#48379
        ser = Series([1, 2, 3, 4, 5], dtype="Int64")
        ser_numpy_dtype = Series([1, 2, 3, 4, 5], dtype="int64")
        result = ser.var(ddof=ddof)
        result_numpy_dtype = ser_numpy_dtype.var(ddof=ddof)
        assert result == result_numpy_dtype
        assert result == exp

    @pytest.mark.parametrize("dtype", ("m8[ns]", "m8[ns]", "M8[ns]", "M8[ns, UTC]"))
    @pytest.mark.parametrize("skipna", [True, False])
    def test_empty_timeseries_reductions_return_nat(self, dtype, skipna):
        # covers GH#11245
        assert Series([], dtype=dtype).min(skipna=skipna) is NaT
        assert Series([], dtype=dtype).max(skipna=skipna) is NaT

    def test_numpy_argmin(self):
        # See GH#16830
        data = np.arange(1, 11)

        s = Series(data, index=data)
        result = np.argmin(s)

        expected = np.argmin(data)
        assert result == expected

        result = s.argmin()

        assert result == expected

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            np.argmin(s, out=data)

    def test_numpy_argmax(self):
        # See GH#16830
        data = np.arange(1, 11)

        ser = Series(data, index=data)
        result = np.argmax(ser)
        expected = np.argmax(data)
        assert result == expected

        result = ser.argmax()

        assert result == expected

        msg = "the 'out' parameter is not supported"
        with pytest.raises(ValueError, match=msg):
            np.argmax(ser, out=data)

    def test_idxmin_dt64index(self, unit):
        # GH#43587 should have NaT instead of NaN
        dti = DatetimeIndex(["NaT", "2015-02-08", "NaT"]).as_unit(unit)
        ser = Series([1.0, 2.0, np.nan], index=dti)
        msg = "The behavior of Series.idxmin with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.idxmin(skipna=False)
        assert res is NaT
        msg = "The behavior of Series.idxmax with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = ser.idxmax(skipna=False)
        assert res is NaT

        df = ser.to_frame()
        msg = "The behavior of DataFrame.idxmin with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = df.idxmin(skipna=False)
        assert res.dtype == f"M8[{unit}]"
        assert res.isna().all()
        msg = "The behavior of DataFrame.idxmax with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            res = df.idxmax(skipna=False)
        assert res.dtype == f"M8[{unit}]"
        assert res.isna().all()

    def test_idxmin(self):
        # test idxmin
        # _check_stat_op approach can not be used here because of isna check.
        string_series = Series(range(20), dtype=np.float64, name="series")

        # add some NaNs
        string_series[5:15] = np.nan

        # skipna or no
        assert string_series[string_series.idxmin()] == string_series.min()
        msg = "The behavior of Series.idxmin"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert isna(string_series.idxmin(skipna=False))

        # no NaNs
        nona = string_series.dropna()
        assert nona[nona.idxmin()] == nona.min()
        assert nona.index.values.tolist().index(nona.idxmin()) == nona.values.argmin()

        # all NaNs
        allna = string_series * np.nan
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert isna(allna.idxmin())

        # datetime64[ns]
        s = Series(date_range("20130102", periods=6))
        result = s.idxmin()
        assert result == 0

        s[0] = np.nan
        result = s.idxmin()
        assert result == 1

    def test_idxmax(self):
        # test idxmax
        # _check_stat_op approach can not be used here because of isna check.
        string_series = Series(range(20), dtype=np.float64, name="series")

        # add some NaNs
        string_series[5:15] = np.nan

        # skipna or no
        assert string_series[string_series.idxmax()] == string_series.max()
        msg = "The behavior of Series.idxmax with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert isna(string_series.idxmax(skipna=False))

        # no NaNs
        nona = string_series.dropna()
        assert nona[nona.idxmax()] == nona.max()
        assert nona.index.values.tolist().index(nona.idxmax()) == nona.values.argmax()

        # all NaNs
        allna = string_series * np.nan
        msg = "The behavior of Series.idxmax with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert isna(allna.idxmax())

        s = Series(date_range("20130102", periods=6))
        result = s.idxmax()
        assert result == 5

        s[5] = np.nan
        result = s.idxmax()
        assert result == 4

        # Index with float64 dtype
        # GH#5914
        s = Series([1, 2, 3], [1.1, 2.1, 3.1])
        result = s.idxmax()
        assert result == 3.1
        result = s.idxmin()
        assert result == 1.1

        s = Series(s.index, s.index)
        result = s.idxmax()
        assert result == 3.1
        result = s.idxmin()
        assert result == 1.1

    def test_all_any(self):
        ts = Series(
            np.arange(10, dtype=np.float64),
            index=date_range("2020-01-01", periods=10),
            name="ts",
        )
        bool_series = ts > 0
        assert not bool_series.all()
        assert bool_series.any()

        # Alternative types, with implicit 'object' dtype.
        s = Series(["abc", True])
        assert s.any()

    def test_numpy_all_any(self, index_or_series):
        # GH#40180
        idx = index_or_series([0, 1, 2])
        assert not np.all(idx)
        assert np.any(idx)
        idx = Index([1, 2, 3])
        assert np.all(idx)

    def test_all_any_skipna(self):
        # Check skipna, with implicit 'object' dtype.
        s1 = Series([np.nan, True])
        s2 = Series([np.nan, False])
        assert s1.all(skipna=False)  # nan && True => True
        assert s1.all(skipna=True)
        assert s2.any(skipna=False)
        assert not s2.any(skipna=True)

    def test_all_any_bool_only(self):
        s = Series([False, False, True, True, False, True], index=[0, 0, 1, 1, 2, 2])

        # GH#47500 - test bool_only works
        assert s.any(bool_only=True)
        assert not s.all(bool_only=True)

    @pytest.mark.parametrize("bool_agg_func", ["any", "all"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_any_all_object_dtype(self, bool_agg_func, skipna):
        # GH#12863
        ser = Series(["a", "b", "c", "d", "e"], dtype=object)
        result = getattr(ser, bool_agg_func)(skipna=skipna)
        expected = True

        assert result == expected

    @pytest.mark.parametrize("bool_agg_func", ["any", "all"])
    @pytest.mark.parametrize(
        "data", [[False, None], [None, False], [False, np.nan], [np.nan, False]]
    )
    def test_any_all_object_dtype_missing(self, data, bool_agg_func):
        # GH#27709
        ser = Series(data)
        result = getattr(ser, bool_agg_func)(skipna=False)

        # None is treated is False, but np.nan is treated as True
        expected = bool_agg_func == "any" and None not in data
        assert result == expected

    @pytest.mark.parametrize("dtype", ["boolean", "Int64", "UInt64", "Float64"])
    @pytest.mark.parametrize("bool_agg_func", ["any", "all"])
    @pytest.mark.parametrize("skipna", [True, False])
    @pytest.mark.parametrize(
        # expected_data indexed as [[skipna=False/any, skipna=False/all],
        #                           [skipna=True/any, skipna=True/all]]
        "data,expected_data",
        [
            ([0, 0, 0], [[False, False], [False, False]]),
            ([1, 1, 1], [[True, True], [True, True]]),
            ([pd.NA, pd.NA, pd.NA], [[pd.NA, pd.NA], [False, True]]),
            ([0, pd.NA, 0], [[pd.NA, False], [False, False]]),
            ([1, pd.NA, 1], [[True, pd.NA], [True, True]]),
            ([1, pd.NA, 0], [[True, False], [True, False]]),
        ],
    )
    def test_any_all_nullable_kleene_logic(
        self, bool_agg_func, skipna, data, dtype, expected_data
    ):
        # GH-37506, GH-41967
        ser = Series(data, dtype=dtype)
        expected = expected_data[skipna][bool_agg_func == "all"]

        result = getattr(ser, bool_agg_func)(skipna=skipna)
        assert (result is pd.NA and expected is pd.NA) or result == expected

    def test_any_axis1_bool_only(self):
        # GH#32432
        df = DataFrame({"A": [True, False], "B": [1, 2]})
        result = df.any(axis=1, bool_only=True)
        expected = Series([True, False])
        tm.assert_series_equal(result, expected)

    def test_any_all_datetimelike(self):
        # GH#38723 these may not be the desired long-term behavior (GH#34479)
        #  but in the interim should be internally consistent
        dta = date_range("1995-01-02", periods=3)._data
        ser = Series(dta)
        df = DataFrame(ser)

        msg = "'(any|all)' with datetime64 dtypes is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            # GH#34479
            assert dta.all()
            assert dta.any()

            assert ser.all()
            assert ser.any()

            assert df.any().all()
            assert df.all().all()

        dta = dta.tz_localize("UTC")
        ser = Series(dta)
        df = DataFrame(ser)

        with tm.assert_produces_warning(FutureWarning, match=msg):
            # GH#34479
            assert dta.all()
            assert dta.any()

            assert ser.all()
            assert ser.any()

            assert df.any().all()
            assert df.all().all()

        tda = dta - dta[0]
        ser = Series(tda)
        df = DataFrame(ser)

        assert tda.any()
        assert not tda.all()

        assert ser.any()
        assert not ser.all()

        assert df.any().all()
        assert not df.all().any()

    def test_any_all_string_dtype(self, any_string_dtype):
        # GH#54591
        if (
            isinstance(any_string_dtype, pd.StringDtype)
            and any_string_dtype.na_value is pd.NA
        ):
            # the nullable string dtype currently still raise an error
            # https://github.com/pandas-dev/pandas/issues/51939
            ser = Series(["a", "b"], dtype=any_string_dtype)
            with pytest.raises(TypeError):
                ser.any()
            with pytest.raises(TypeError):
                ser.all()
            return

        ser = Series(["", "a"], dtype=any_string_dtype)
        assert ser.any()
        assert not ser.all()
        assert ser.any(skipna=False)
        assert not ser.all(skipna=False)

        ser = Series([np.nan, "a"], dtype=any_string_dtype)
        assert ser.any()
        assert ser.all()
        assert ser.any(skipna=False)
        assert ser.all(skipna=False)  # NaN is considered truthy

        ser = Series([np.nan, ""], dtype=any_string_dtype)
        assert not ser.any()
        assert not ser.all()
        assert ser.any(skipna=False)  # NaN is considered truthy
        assert not ser.all(skipna=False)

        ser = Series(["a", "b"], dtype=any_string_dtype)
        assert ser.any()
        assert ser.all()
        assert ser.any(skipna=False)
        assert ser.all(skipna=False)

        ser = Series([], dtype=any_string_dtype)
        assert not ser.any()
        assert ser.all()
        assert not ser.any(skipna=False)
        assert ser.all(skipna=False)

        ser = Series([""], dtype=any_string_dtype)
        assert not ser.any()
        assert not ser.all()
        assert not ser.any(skipna=False)
        assert not ser.all(skipna=False)

        ser = Series([np.nan], dtype=any_string_dtype)
        assert not ser.any()
        assert ser.all()
        assert ser.any(skipna=False)  # NaN is considered truthy
        assert ser.all(skipna=False)  # NaN is considered truthy

    def test_timedelta64_analytics(self):
        # index min/max
        dti = date_range("2012-1-1", periods=3, freq="D")
        td = Series(dti) - Timestamp("20120101")

        result = td.idxmin()
        assert result == 0

        result = td.idxmax()
        assert result == 2

        # GH#2982
        # with NaT
        td[0] = np.nan

        result = td.idxmin()
        assert result == 1

        result = td.idxmax()
        assert result == 2

        # abs
        s1 = Series(date_range("20120101", periods=3))
        s2 = Series(date_range("20120102", periods=3))
        expected = Series(s2 - s1)

        result = np.abs(s1 - s2)
        tm.assert_series_equal(result, expected)

        result = (s1 - s2).abs()
        tm.assert_series_equal(result, expected)

        # max/min
        result = td.max()
        expected = Timedelta("2 days")
        assert result == expected

        result = td.min()
        expected = Timedelta("1 days")
        assert result == expected

    @pytest.mark.parametrize(
        "test_input,error_type",
        [
            (Series([], dtype="float64"), ValueError),
            # For strings, or any Series with dtype 'O'
            (Series(["foo", "bar", "baz"]), TypeError),
            (Series([(1,), (2,)]), TypeError),
            # For mixed data types
            (Series(["foo", "foo", "bar", "bar", None, np.nan, "baz"]), TypeError),
        ],
    )
    def test_assert_idxminmax_empty_raises(self, test_input, error_type):
        """
        Cases where ``Series.argmax`` and related should raise an exception
        """
        test_input = Series([], dtype="float64")
        msg = "attempt to get argmin of an empty sequence"
        with pytest.raises(ValueError, match=msg):
            test_input.idxmin()
        with pytest.raises(ValueError, match=msg):
            test_input.idxmin(skipna=False)
        msg = "attempt to get argmax of an empty sequence"
        with pytest.raises(ValueError, match=msg):
            test_input.idxmax()
        with pytest.raises(ValueError, match=msg):
            test_input.idxmax(skipna=False)

    def test_idxminmax_object_dtype(self, using_infer_string):
        # pre-2.1 object-dtype was disallowed for argmin/max
        ser = Series(["foo", "bar", "baz"])
        assert ser.idxmax() == 0
        assert ser.idxmax(skipna=False) == 0
        assert ser.idxmin() == 1
        assert ser.idxmin(skipna=False) == 1

        ser2 = Series([(1,), (2,)])
        assert ser2.idxmax() == 1
        assert ser2.idxmax(skipna=False) == 1
        assert ser2.idxmin() == 0
        assert ser2.idxmin(skipna=False) == 0

        if not using_infer_string:
            # attempting to compare np.nan with string raises
            ser3 = Series(["foo", "foo", "bar", "bar", None, np.nan, "baz"])
            msg = "'>' not supported between instances of 'float' and 'str'"
            with pytest.raises(TypeError, match=msg):
                ser3.idxmax()
            with pytest.raises(TypeError, match=msg):
                ser3.idxmax(skipna=False)
            msg = "'<' not supported between instances of 'float' and 'str'"
            with pytest.raises(TypeError, match=msg):
                ser3.idxmin()
            with pytest.raises(TypeError, match=msg):
                ser3.idxmin(skipna=False)

    def test_idxminmax_object_frame(self):
        # GH#4279
        df = DataFrame([["zimm", 2.5], ["biff", 1.0], ["bid", 12.0]])
        res = df.idxmax()
        exp = Series([0, 2])
        tm.assert_series_equal(res, exp)

    def test_idxminmax_object_tuples(self):
        # GH#43697
        ser = Series([(1, 3), (2, 2), (3, 1)])
        assert ser.idxmax() == 2
        assert ser.idxmin() == 0
        assert ser.idxmax(skipna=False) == 2
        assert ser.idxmin(skipna=False) == 0

    def test_idxminmax_object_decimals(self):
        # GH#40685
        df = DataFrame(
            {
                "idx": [0, 1],
                "x": [Decimal("8.68"), Decimal("42.23")],
                "y": [Decimal("7.11"), Decimal("79.61")],
            }
        )
        res = df.idxmax()
        exp = Series({"idx": 1, "x": 1, "y": 1})
        tm.assert_series_equal(res, exp)

        res2 = df.idxmin()
        exp2 = exp - 1
        tm.assert_series_equal(res2, exp2)

    def test_argminmax_object_ints(self):
        # GH#18021
        ser = Series([0, 1], dtype="object")
        assert ser.argmax() == 1
        assert ser.argmin() == 0
        assert ser.argmax(skipna=False) == 1
        assert ser.argmin(skipna=False) == 0

    def test_idxminmax_with_inf(self):
        # For numeric data with NA and Inf (GH #13595)
        s = Series([0, -np.inf, np.inf, np.nan])

        assert s.idxmin() == 1
        msg = "The behavior of Series.idxmin with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert np.isnan(s.idxmin(skipna=False))

        assert s.idxmax() == 2
        msg = "The behavior of Series.idxmax with all-NA values"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            assert np.isnan(s.idxmax(skipna=False))

        msg = "use_inf_as_na option is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            # Using old-style behavior that treats floating point nan, -inf, and
            # +inf as missing
            with pd.option_context("mode.use_inf_as_na", True):
                assert s.idxmin() == 0
                assert np.isnan(s.idxmin(skipna=False))
                assert s.idxmax() == 0
                np.isnan(s.idxmax(skipna=False))

    def test_sum_uint64(self):
        # GH 53401
        s = Series([10000000000000000000], dtype="uint64")
        result = s.sum()
        expected = np.uint64(10000000000000000000)
        tm.assert_almost_equal(result, expected)


class TestDatetime64SeriesReductions:
    # Note: the name TestDatetime64SeriesReductions indicates these tests
    #  were moved from a series-specific test file, _not_ that these tests are
    #  intended long-term to be series-specific

    @pytest.mark.parametrize(
        "nat_ser",
        [
            Series([NaT, NaT]),
            Series([NaT, Timedelta("nat")]),
            Series([Timedelta("nat"), Timedelta("nat")]),
        ],
    )
    def test_minmax_nat_series(self, nat_ser):
        # GH#23282
        assert nat_ser.min() is NaT
        assert nat_ser.max() is NaT
        assert nat_ser.min(skipna=False) is NaT
        assert nat_ser.max(skipna=False) is NaT

    @pytest.mark.parametrize(
        "nat_df",
        [
            DataFrame([NaT, NaT]),
            DataFrame([NaT, Timedelta("nat")]),
            DataFrame([Timedelta("nat"), Timedelta("nat")]),
        ],
    )
    def test_minmax_nat_dataframe(self, nat_df):
        # GH#23282
        assert nat_df.min()[0] is NaT
        assert nat_df.max()[0] is NaT
        assert nat_df.min(skipna=False)[0] is NaT
        assert nat_df.max(skipna=False)[0] is NaT

    def test_min_max(self):
        rng = date_range("1/1/2000", "12/31/2000")
        rng2 = rng.take(np.random.default_rng(2).permutation(len(rng)))

        the_min = rng2.min()
        the_max = rng2.max()
        assert isinstance(the_min, Timestamp)
        assert isinstance(the_max, Timestamp)
        assert the_min == rng[0]
        assert the_max == rng[-1]

        assert rng.min() == rng[0]
        assert rng.max() == rng[-1]

    def test_min_max_series(self):
        rng = date_range("1/1/2000", periods=10, freq="4h")
        lvls = ["A", "A", "A", "B", "B", "B", "C", "C", "C", "C"]
        df = DataFrame(
            {
                "TS": rng,
                "V": np.random.default_rng(2).standard_normal(len(rng)),
                "L": lvls,
            }
        )

        result = df.TS.max()
        exp = Timestamp(df.TS.iat[-1])
        assert isinstance(result, Timestamp)
        assert result == exp

        result = df.TS.min()
        exp = Timestamp(df.TS.iat[0])
        assert isinstance(result, Timestamp)
        assert result == exp


class TestCategoricalSeriesReductions:
    # Note: the name TestCategoricalSeriesReductions indicates these tests
    #  were moved from a series-specific test file, _not_ that these tests are
    #  intended long-term to be series-specific

    @pytest.mark.parametrize("function", ["min", "max"])
    def test_min_max_unordered_raises(self, function):
        # unordered cats have no min/max
        cat = Series(Categorical(["a", "b", "c", "d"], ordered=False))
        msg = f"Categorical is not ordered for operation {function}"
        with pytest.raises(TypeError, match=msg):
            getattr(cat, function)()

    @pytest.mark.parametrize(
        "values, categories",
        [
            (list("abc"), list("abc")),
            (list("abc"), list("cba")),
            (list("abc") + [np.nan], list("cba")),
            ([1, 2, 3], [3, 2, 1]),
            ([1, 2, 3, np.nan], [3, 2, 1]),
        ],
    )
    @pytest.mark.parametrize("function", ["min", "max"])
    def test_min_max_ordered(self, values, categories, function):
        # GH 25303
        cat = Series(Categorical(values, categories=categories, ordered=True))
        result = getattr(cat, function)(skipna=True)
        expected = categories[0] if function == "min" else categories[2]
        assert result == expected

    @pytest.mark.parametrize("function", ["min", "max"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_min_max_ordered_with_nan_only(self, function, skipna):
        # https://github.com/pandas-dev/pandas/issues/33450
        cat = Series(Categorical([np.nan], categories=[1, 2], ordered=True))
        result = getattr(cat, function)(skipna=skipna)
        assert result is np.nan

    @pytest.mark.parametrize("function", ["min", "max"])
    @pytest.mark.parametrize("skipna", [True, False])
    def test_min_max_skipna(self, function, skipna):
        cat = Series(
            Categorical(["a", "b", np.nan, "a"], categories=["b", "a"], ordered=True)
        )
        result = getattr(cat, function)(skipna=skipna)

        if skipna is True:
            expected = "b" if function == "min" else "a"
            assert result == expected
        else:
            assert result is np.nan


class TestSeriesMode:
    # Note: the name TestSeriesMode indicates these tests
    #  were moved from a series-specific test file, _not_ that these tests are
    #  intended long-term to be series-specific

    @pytest.mark.parametrize(
        "dropna, expected",
        [(True, Series([], dtype=np.float64)), (False, Series([], dtype=np.float64))],
    )
    def test_mode_empty(self, dropna, expected):
        s = Series([], dtype=np.float64)
        result = s.mode(dropna)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "dropna, data, expected",
        [
            (True, [1, 1, 1, 2], [1]),
            (True, [1, 1, 1, 2, 3, 3, 3], [1, 3]),
            (False, [1, 1, 1, 2], [1]),
            (False, [1, 1, 1, 2, 3, 3, 3], [1, 3]),
        ],
    )
    @pytest.mark.parametrize(
        "dt", list(np.typecodes["AllInteger"] + np.typecodes["Float"])
    )
    def test_mode_numerical(self, dropna, data, expected, dt):
        s = Series(data, dtype=dt)
        result = s.mode(dropna)
        expected = Series(expected, dtype=dt)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("dropna, expected", [(True, [1.0]), (False, [1, np.nan])])
    def test_mode_numerical_nan(self, dropna, expected):
        s = Series([1, 1, 2, np.nan, np.nan])
        result = s.mode(dropna)
        expected = Series(expected)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2",
        [
            (True, ["b"], ["bar"]),
            (False, ["b"], [np.nan]),
        ],
    )
    def test_mode_object(self, dropna, expected1, expected2):
        # Test string and object types.
        data = ["a"] * 2 + ["b"] * 3

        s = Series(data, dtype="c")
        result = s.mode(dropna)
        expected1 = Series(expected1, dtype="c")
        tm.assert_series_equal(result, expected1)

        data = ["foo", "bar", "bar", np.nan, np.nan, np.nan]

        s = Series(data, dtype=object)
        result = s.mode(dropna)
        expected2 = Series(expected2, dtype=object)
        tm.assert_series_equal(result, expected2)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2",
        [
            (True, ["b"], ["bar"]),
            (False, ["b"], [np.nan]),
        ],
    )
    def test_mode_string(self, dropna, expected1, expected2, any_string_dtype):
        # Test string and object types.
        data = ["a"] * 2 + ["b"] * 3

        s = Series(data, dtype=any_string_dtype)
        result = s.mode(dropna)
        expected1 = Series(expected1, dtype=any_string_dtype)
        tm.assert_series_equal(result, expected1)

        data = ["foo", "bar", "bar", np.nan, np.nan, np.nan]

        s = Series(data, dtype=any_string_dtype)
        result = s.mode(dropna)
        expected2 = Series(expected2, dtype=any_string_dtype)
        tm.assert_series_equal(result, expected2)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2",
        [(True, ["foo"], ["foo"]), (False, ["foo"], [np.nan])],
    )
    def test_mode_mixeddtype(self, dropna, expected1, expected2):
        s = Series([1, "foo", "foo"])
        result = s.mode(dropna)
        expected = Series(expected1, dtype=object)
        tm.assert_series_equal(result, expected)

        s = Series([1, "foo", "foo", np.nan, np.nan, np.nan])
        result = s.mode(dropna)
        expected = Series(expected2, dtype=object)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2",
        [
            (
                True,
                ["1900-05-03", "2011-01-03", "2013-01-02"],
                ["2011-01-03", "2013-01-02"],
            ),
            (False, [np.nan], [np.nan, "2011-01-03", "2013-01-02"]),
        ],
    )
    def test_mode_datetime(self, dropna, expected1, expected2):
        s = Series(
            ["2011-01-03", "2013-01-02", "1900-05-03", "nan", "nan"], dtype="M8[ns]"
        )
        result = s.mode(dropna)
        expected1 = Series(expected1, dtype="M8[ns]")
        tm.assert_series_equal(result, expected1)

        s = Series(
            [
                "2011-01-03",
                "2013-01-02",
                "1900-05-03",
                "2011-01-03",
                "2013-01-02",
                "nan",
                "nan",
            ],
            dtype="M8[ns]",
        )
        result = s.mode(dropna)
        expected2 = Series(expected2, dtype="M8[ns]")
        tm.assert_series_equal(result, expected2)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2",
        [
            (True, ["-1 days", "0 days", "1 days"], ["2 min", "1 day"]),
            (False, [np.nan], [np.nan, "2 min", "1 day"]),
        ],
    )
    def test_mode_timedelta(self, dropna, expected1, expected2):
        # gh-5986: Test timedelta types.

        s = Series(
            ["1 days", "-1 days", "0 days", "nan", "nan"], dtype="timedelta64[ns]"
        )
        result = s.mode(dropna)
        expected1 = Series(expected1, dtype="timedelta64[ns]")
        tm.assert_series_equal(result, expected1)

        s = Series(
            [
                "1 day",
                "1 day",
                "-1 day",
                "-1 day 2 min",
                "2 min",
                "2 min",
                "nan",
                "nan",
            ],
            dtype="timedelta64[ns]",
        )
        result = s.mode(dropna)
        expected2 = Series(expected2, dtype="timedelta64[ns]")
        tm.assert_series_equal(result, expected2)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2, expected3",
        [
            (
                True,
                Categorical([1, 2], categories=[1, 2]),
                Categorical(["a"], categories=[1, "a"]),
                Categorical([3, 1], categories=[3, 2, 1], ordered=True),
            ),
            (
                False,
                Categorical([np.nan], categories=[1, 2]),
                Categorical([np.nan, "a"], categories=[1, "a"]),
                Categorical([np.nan, 3, 1], categories=[3, 2, 1], ordered=True),
            ),
        ],
    )
    def test_mode_category(self, dropna, expected1, expected2, expected3):
        s = Series(Categorical([1, 2, np.nan, np.nan]))
        result = s.mode(dropna)
        expected1 = Series(expected1, dtype="category")
        tm.assert_series_equal(result, expected1)

        s = Series(Categorical([1, "a", "a", np.nan, np.nan]))
        result = s.mode(dropna)
        expected2 = Series(expected2, dtype="category")
        tm.assert_series_equal(result, expected2)

        s = Series(
            Categorical(
                [1, 1, 2, 3, 3, np.nan, np.nan], categories=[3, 2, 1], ordered=True
            )
        )
        result = s.mode(dropna)
        expected3 = Series(expected3, dtype="category")
        tm.assert_series_equal(result, expected3)

    @pytest.mark.parametrize(
        "dropna, expected1, expected2",
        [(True, [2**63], [1, 2**63]), (False, [2**63], [1, 2**63])],
    )
    def test_mode_intoverflow(self, dropna, expected1, expected2):
        # Test for uint64 overflow.
        s = Series([1, 2**63, 2**63], dtype=np.uint64)
        result = s.mode(dropna)
        expected1 = Series(expected1, dtype=np.uint64)
        tm.assert_series_equal(result, expected1)

        s = Series([1, 2**63], dtype=np.uint64)
        result = s.mode(dropna)
        expected2 = Series(expected2, dtype=np.uint64)
        tm.assert_series_equal(result, expected2)

    def test_mode_sort_with_na(self):
        s = Series([1, "foo", "foo", np.nan, np.nan])
        expected = Series(["foo", np.nan], dtype=object)
        result = s.mode(dropna=False)
        tm.assert_series_equal(result, expected)

    def test_mode_boolean_with_na(self):
        # GH#42107
        ser = Series([True, False, True, pd.NA], dtype="boolean")
        result = ser.mode()
        expected = Series({0: True}, dtype="boolean")
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "array,expected,dtype",
        [
            (
                [0, 1j, 1, 1, 1 + 1j, 1 + 2j],
                Series([1], dtype=np.complex128),
                np.complex128,
            ),
            (
                [0, 1j, 1, 1, 1 + 1j, 1 + 2j],
                Series([1], dtype=np.complex64),
                np.complex64,
            ),
            (
                [1 + 1j, 2j, 1 + 1j],
                Series([1 + 1j], dtype=np.complex128),
                np.complex128,
            ),
        ],
    )
    def test_single_mode_value_complex(self, array, expected, dtype):
        result = Series(array, dtype=dtype).mode()
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "array,expected,dtype",
        [
            (
                # no modes
                [0, 1j, 1, 1 + 1j, 1 + 2j],
                Series([0j, 1j, 1 + 0j, 1 + 1j, 1 + 2j], dtype=np.complex128),
                np.complex128,
            ),
            (
                [1 + 1j, 2j, 1 + 1j, 2j, 3],
                Series([2j, 1 + 1j], dtype=np.complex64),
                np.complex64,
            ),
        ],
    )
    def test_multimode_complex(self, array, expected, dtype):
        # GH 17927
        # mode tries to sort multimodal series.
        # Complex numbers are sorted by their magnitude
        result = Series(array, dtype=dtype).mode()
        tm.assert_series_equal(result, expected)
