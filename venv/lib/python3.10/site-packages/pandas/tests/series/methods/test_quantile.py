import numpy as np
import pytest

from pandas.core.dtypes.common import is_integer

import pandas as pd
from pandas import (
    Index,
    Series,
)
import pandas._testing as tm
from pandas.core.indexes.datetimes import Timestamp


class TestSeriesQuantile:
    def test_quantile(self, datetime_series):
        q = datetime_series.quantile(0.1)
        assert q == np.percentile(datetime_series.dropna(), 10)

        q = datetime_series.quantile(0.9)
        assert q == np.percentile(datetime_series.dropna(), 90)

        # object dtype
        q = Series(datetime_series, dtype=object).quantile(0.9)
        assert q == np.percentile(datetime_series.dropna(), 90)

        # datetime64[ns] dtype
        dts = datetime_series.index.to_series()
        q = dts.quantile(0.2)
        assert q == Timestamp("2000-01-10 19:12:00")

        # timedelta64[ns] dtype
        tds = dts.diff()
        q = tds.quantile(0.25)
        assert q == pd.to_timedelta("24:00:00")

        # GH7661
        result = Series([np.timedelta64("NaT")]).sum()
        assert result == pd.Timedelta(0)

        msg = "percentiles should all be in the interval \\[0, 1\\]"
        for invalid in [-1, 2, [0.5, -1], [0.5, 2]]:
            with pytest.raises(ValueError, match=msg):
                datetime_series.quantile(invalid)

        s = Series(np.random.default_rng(2).standard_normal(100))
        percentile_array = [-0.5, 0.25, 1.5]
        with pytest.raises(ValueError, match=msg):
            s.quantile(percentile_array)

    def test_quantile_multi(self, datetime_series, unit):
        datetime_series.index = datetime_series.index.as_unit(unit)
        qs = [0.1, 0.9]
        result = datetime_series.quantile(qs)
        expected = Series(
            [
                np.percentile(datetime_series.dropna(), 10),
                np.percentile(datetime_series.dropna(), 90),
            ],
            index=qs,
            name=datetime_series.name,
        )
        tm.assert_series_equal(result, expected)

        dts = datetime_series.index.to_series()
        dts.name = "xxx"
        result = dts.quantile((0.2, 0.2))
        expected = Series(
            [Timestamp("2000-01-10 19:12:00"), Timestamp("2000-01-10 19:12:00")],
            index=[0.2, 0.2],
            name="xxx",
            dtype=f"M8[{unit}]",
        )
        tm.assert_series_equal(result, expected)

        result = datetime_series.quantile([])
        expected = Series(
            [], name=datetime_series.name, index=Index([], dtype=float), dtype="float64"
        )
        tm.assert_series_equal(result, expected)

    def test_quantile_interpolation(self, datetime_series):
        # see gh-10174

        # interpolation = linear (default case)
        q = datetime_series.quantile(0.1, interpolation="linear")
        assert q == np.percentile(datetime_series.dropna(), 10)
        q1 = datetime_series.quantile(0.1)
        assert q1 == np.percentile(datetime_series.dropna(), 10)

        # test with and without interpolation keyword
        assert q == q1

    def test_quantile_interpolation_dtype(self):
        # GH #10174

        # interpolation = linear (default case)
        q = Series([1, 3, 4]).quantile(0.5, interpolation="lower")
        assert q == np.percentile(np.array([1, 3, 4]), 50)
        assert is_integer(q)

        q = Series([1, 3, 4]).quantile(0.5, interpolation="higher")
        assert q == np.percentile(np.array([1, 3, 4]), 50)
        assert is_integer(q)

    def test_quantile_nan(self):
        # GH 13098
        ser = Series([1, 2, 3, 4, np.nan])
        result = ser.quantile(0.5)
        expected = 2.5
        assert result == expected

        # all nan/empty
        s1 = Series([], dtype=object)
        cases = [s1, Series([np.nan, np.nan])]

        for ser in cases:
            res = ser.quantile(0.5)
            assert np.isnan(res)

            res = ser.quantile([0.5])
            tm.assert_series_equal(res, Series([np.nan], index=[0.5]))

            res = ser.quantile([0.2, 0.3])
            tm.assert_series_equal(res, Series([np.nan, np.nan], index=[0.2, 0.3]))

    @pytest.mark.parametrize(
        "case",
        [
            [
                Timestamp("2011-01-01"),
                Timestamp("2011-01-02"),
                Timestamp("2011-01-03"),
            ],
            [
                Timestamp("2011-01-01", tz="US/Eastern"),
                Timestamp("2011-01-02", tz="US/Eastern"),
                Timestamp("2011-01-03", tz="US/Eastern"),
            ],
            [pd.Timedelta("1 days"), pd.Timedelta("2 days"), pd.Timedelta("3 days")],
            # NaT
            [
                Timestamp("2011-01-01"),
                Timestamp("2011-01-02"),
                Timestamp("2011-01-03"),
                pd.NaT,
            ],
            [
                Timestamp("2011-01-01", tz="US/Eastern"),
                Timestamp("2011-01-02", tz="US/Eastern"),
                Timestamp("2011-01-03", tz="US/Eastern"),
                pd.NaT,
            ],
            [
                pd.Timedelta("1 days"),
                pd.Timedelta("2 days"),
                pd.Timedelta("3 days"),
                pd.NaT,
            ],
        ],
    )
    def test_quantile_box(self, case):
        ser = Series(case, name="XXX")
        res = ser.quantile(0.5)
        assert res == case[1]

        res = ser.quantile([0.5])
        exp = Series([case[1]], index=[0.5], name="XXX")
        tm.assert_series_equal(res, exp)

    def test_datetime_timedelta_quantiles(self):
        # covers #9694
        assert pd.isna(Series([], dtype="M8[ns]").quantile(0.5))
        assert pd.isna(Series([], dtype="m8[ns]").quantile(0.5))

    def test_quantile_nat(self):
        res = Series([pd.NaT, pd.NaT]).quantile(0.5)
        assert res is pd.NaT

        res = Series([pd.NaT, pd.NaT]).quantile([0.5])
        tm.assert_series_equal(res, Series([pd.NaT], index=[0.5]))

    @pytest.mark.parametrize(
        "values, dtype",
        [([0, 0, 0, 1, 2, 3], "Sparse[int]"), ([0.0, None, 1.0, 2.0], "Sparse[float]")],
    )
    def test_quantile_sparse(self, values, dtype):
        ser = Series(values, dtype=dtype)
        result = ser.quantile([0.5])
        expected = Series(np.asarray(ser)).quantile([0.5]).astype("Sparse[float]")
        tm.assert_series_equal(result, expected)

    def test_quantile_empty_float64(self):
        # floats
        ser = Series([], dtype="float64")

        res = ser.quantile(0.5)
        assert np.isnan(res)

        res = ser.quantile([0.5])
        exp = Series([np.nan], index=[0.5])
        tm.assert_series_equal(res, exp)

    def test_quantile_empty_int64(self):
        # int
        ser = Series([], dtype="int64")

        res = ser.quantile(0.5)
        assert np.isnan(res)

        res = ser.quantile([0.5])
        exp = Series([np.nan], index=[0.5])
        tm.assert_series_equal(res, exp)

    def test_quantile_empty_dt64(self):
        # datetime
        ser = Series([], dtype="datetime64[ns]")

        res = ser.quantile(0.5)
        assert res is pd.NaT

        res = ser.quantile([0.5])
        exp = Series([pd.NaT], index=[0.5], dtype=ser.dtype)
        tm.assert_series_equal(res, exp)

    @pytest.mark.parametrize("dtype", [int, float, "Int64"])
    def test_quantile_dtypes(self, dtype):
        result = Series([1, 2, 3], dtype=dtype).quantile(np.arange(0, 1, 0.25))
        expected = Series(np.arange(1, 3, 0.5), index=np.arange(0, 1, 0.25))
        if dtype == "Int64":
            expected = expected.astype("Float64")
        tm.assert_series_equal(result, expected)

    def test_quantile_all_na(self, any_int_ea_dtype):
        # GH#50681
        ser = Series([pd.NA, pd.NA], dtype=any_int_ea_dtype)
        with tm.assert_produces_warning(None):
            result = ser.quantile([0.1, 0.5])
        expected = Series([pd.NA, pd.NA], dtype=any_int_ea_dtype, index=[0.1, 0.5])
        tm.assert_series_equal(result, expected)

    def test_quantile_dtype_size(self, any_int_ea_dtype):
        # GH#50681
        ser = Series([pd.NA, pd.NA, 1], dtype=any_int_ea_dtype)
        result = ser.quantile([0.1, 0.5])
        expected = Series([1, 1], dtype=any_int_ea_dtype, index=[0.1, 0.5])
        tm.assert_series_equal(result, expected)
