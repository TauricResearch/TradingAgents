import datetime as dt
from itertools import combinations

import dateutil
import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
    concat,
    isna,
)
import pandas._testing as tm


class TestAppend:
    def test_append(self, sort, float_frame):
        mixed_frame = float_frame.copy()
        mixed_frame["foo"] = "bar"

        begin_index = float_frame.index[:5]
        end_index = float_frame.index[5:]

        begin_frame = float_frame.reindex(begin_index)
        end_frame = float_frame.reindex(end_index)

        appended = begin_frame._append(end_frame)
        tm.assert_almost_equal(appended["A"], float_frame["A"])

        del end_frame["A"]
        partial_appended = begin_frame._append(end_frame, sort=sort)
        assert "A" in partial_appended

        partial_appended = end_frame._append(begin_frame, sort=sort)
        assert "A" in partial_appended

        # mixed type handling
        appended = mixed_frame[:5]._append(mixed_frame[5:])
        tm.assert_frame_equal(appended, mixed_frame)

        # what to test here
        mixed_appended = mixed_frame[:5]._append(float_frame[5:], sort=sort)
        mixed_appended2 = float_frame[:5]._append(mixed_frame[5:], sort=sort)

        # all equal except 'foo' column
        tm.assert_frame_equal(
            mixed_appended.reindex(columns=["A", "B", "C", "D"]),
            mixed_appended2.reindex(columns=["A", "B", "C", "D"]),
        )

    def test_append_empty(self, float_frame):
        empty = DataFrame()

        appended = float_frame._append(empty)
        tm.assert_frame_equal(float_frame, appended)
        assert appended is not float_frame

        appended = empty._append(float_frame)
        tm.assert_frame_equal(float_frame, appended)
        assert appended is not float_frame

    def test_append_overlap_raises(self, float_frame):
        msg = "Indexes have overlapping values"
        with pytest.raises(ValueError, match=msg):
            float_frame._append(float_frame, verify_integrity=True)

    def test_append_new_columns(self):
        # see gh-6129: new columns
        df = DataFrame({"a": {"x": 1, "y": 2}, "b": {"x": 3, "y": 4}})
        row = Series([5, 6, 7], index=["a", "b", "c"], name="z")
        expected = DataFrame(
            {
                "a": {"x": 1, "y": 2, "z": 5},
                "b": {"x": 3, "y": 4, "z": 6},
                "c": {"z": 7},
            }
        )
        result = df._append(row)
        tm.assert_frame_equal(result, expected)

    def test_append_length0_frame(self, sort):
        df = DataFrame(columns=["A", "B", "C"])
        df3 = DataFrame(index=[0, 1], columns=["A", "B"])
        df5 = df._append(df3, sort=sort)

        expected = DataFrame(index=[0, 1], columns=["A", "B", "C"])
        tm.assert_frame_equal(df5, expected)

    def test_append_records(self):
        arr1 = np.zeros((2,), dtype=("i4,f4,S10"))
        arr1[:] = [(1, 2.0, "Hello"), (2, 3.0, "World")]

        arr2 = np.zeros((3,), dtype=("i4,f4,S10"))
        arr2[:] = [(3, 4.0, "foo"), (5, 6.0, "bar"), (7.0, 8.0, "baz")]

        df1 = DataFrame(arr1)
        df2 = DataFrame(arr2)

        result = df1._append(df2, ignore_index=True)
        expected = DataFrame(np.concatenate((arr1, arr2)))
        tm.assert_frame_equal(result, expected)

    # rewrite sort fixture, since we also want to test default of None
    def test_append_sorts(self, sort):
        df1 = DataFrame({"a": [1, 2], "b": [1, 2]}, columns=["b", "a"])
        df2 = DataFrame({"a": [1, 2], "c": [3, 4]}, index=[2, 3])

        result = df1._append(df2, sort=sort)

        # for None / True
        expected = DataFrame(
            {"b": [1, 2, None, None], "a": [1, 2, 1, 2], "c": [None, None, 3, 4]},
            columns=["a", "b", "c"],
        )
        if sort is False:
            expected = expected[["b", "a", "c"]]
        tm.assert_frame_equal(result, expected)

    def test_append_different_columns(self, sort):
        df = DataFrame(
            {
                "bools": np.random.default_rng(2).standard_normal(10) > 0,
                "ints": np.random.default_rng(2).integers(0, 10, 10),
                "floats": np.random.default_rng(2).standard_normal(10),
                "strings": ["foo", "bar"] * 5,
            }
        )

        a = df[:5].loc[:, ["bools", "ints", "floats"]]
        b = df[5:].loc[:, ["strings", "ints", "floats"]]

        appended = a._append(b, sort=sort)
        assert isna(appended["strings"][0:4]).all()
        assert isna(appended["bools"][5:]).all()

    def test_append_many(self, sort, float_frame):
        chunks = [
            float_frame[:5],
            float_frame[5:10],
            float_frame[10:15],
            float_frame[15:],
        ]

        result = chunks[0]._append(chunks[1:])
        tm.assert_frame_equal(result, float_frame)

        chunks[-1] = chunks[-1].copy()
        chunks[-1]["foo"] = "bar"
        result = chunks[0]._append(chunks[1:], sort=sort)
        tm.assert_frame_equal(result.loc[:, float_frame.columns], float_frame)
        assert (result["foo"][15:] == "bar").all()
        assert result["foo"][:15].isna().all()

    def test_append_preserve_index_name(self):
        # #980
        df1 = DataFrame(columns=["A", "B", "C"])
        df1 = df1.set_index(["A"])
        df2 = DataFrame(data=[[1, 4, 7], [2, 5, 8], [3, 6, 9]], columns=["A", "B", "C"])
        df2 = df2.set_index(["A"])

        msg = "The behavior of array concatenation with empty entries is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df1._append(df2)
        assert result.index.name == "A"

    indexes_can_append = [
        pd.RangeIndex(3),
        Index([4, 5, 6]),
        Index([4.5, 5.5, 6.5]),
        Index(list("abc")),
        pd.CategoricalIndex("A B C".split()),
        pd.CategoricalIndex("D E F".split(), ordered=True),
        pd.IntervalIndex.from_breaks([7, 8, 9, 10]),
        pd.DatetimeIndex(
            [
                dt.datetime(2013, 1, 3, 0, 0),
                dt.datetime(2013, 1, 3, 6, 10),
                dt.datetime(2013, 1, 3, 7, 12),
            ]
        ),
        pd.MultiIndex.from_arrays(["A B C".split(), "D E F".split()]),
    ]

    @pytest.mark.parametrize(
        "index", indexes_can_append, ids=lambda x: type(x).__name__
    )
    def test_append_same_columns_type(self, index):
        # GH18359

        # df wider than ser
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=index)
        ser_index = index[:2]
        ser = Series([7, 8], index=ser_index, name=2)
        result = df._append(ser)
        expected = DataFrame(
            [[1, 2, 3.0], [4, 5, 6], [7, 8, np.nan]], index=[0, 1, 2], columns=index
        )
        # integer dtype is preserved for columns present in ser.index
        assert expected.dtypes.iloc[0].kind == "i"
        assert expected.dtypes.iloc[1].kind == "i"

        tm.assert_frame_equal(result, expected)

        # ser wider than df
        ser_index = index
        index = index[:2]
        df = DataFrame([[1, 2], [4, 5]], columns=index)
        ser = Series([7, 8, 9], index=ser_index, name=2)
        result = df._append(ser)
        expected = DataFrame(
            [[1, 2, np.nan], [4, 5, np.nan], [7, 8, 9]],
            index=[0, 1, 2],
            columns=ser_index,
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "df_columns, series_index",
        combinations(indexes_can_append, r=2),
        ids=lambda x: type(x).__name__,
    )
    def test_append_different_columns_types(self, df_columns, series_index):
        # GH18359
        # See also test 'test_append_different_columns_types_raises' below
        # for errors raised when appending

        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=df_columns)
        ser = Series([7, 8, 9], index=series_index, name=2)

        result = df._append(ser)
        idx_diff = ser.index.difference(df_columns)
        combined_columns = Index(df_columns.tolist()).append(idx_diff)
        expected = DataFrame(
            [
                [1.0, 2.0, 3.0, np.nan, np.nan, np.nan],
                [4, 5, 6, np.nan, np.nan, np.nan],
                [np.nan, np.nan, np.nan, 7, 8, 9],
            ],
            index=[0, 1, 2],
            columns=combined_columns,
        )
        tm.assert_frame_equal(result, expected)

    def test_append_dtype_coerce(self, sort):
        # GH 4993
        # appending with datetime will incorrectly convert datetime64

        df1 = DataFrame(
            index=[1, 2],
            data=[dt.datetime(2013, 1, 1, 0, 0), dt.datetime(2013, 1, 2, 0, 0)],
            columns=["start_time"],
        )
        df2 = DataFrame(
            index=[4, 5],
            data=[
                [dt.datetime(2013, 1, 3, 0, 0), dt.datetime(2013, 1, 3, 6, 10)],
                [dt.datetime(2013, 1, 4, 0, 0), dt.datetime(2013, 1, 4, 7, 10)],
            ],
            columns=["start_time", "end_time"],
        )

        expected = concat(
            [
                Series(
                    [
                        pd.NaT,
                        pd.NaT,
                        dt.datetime(2013, 1, 3, 6, 10),
                        dt.datetime(2013, 1, 4, 7, 10),
                    ],
                    name="end_time",
                ),
                Series(
                    [
                        dt.datetime(2013, 1, 1, 0, 0),
                        dt.datetime(2013, 1, 2, 0, 0),
                        dt.datetime(2013, 1, 3, 0, 0),
                        dt.datetime(2013, 1, 4, 0, 0),
                    ],
                    name="start_time",
                ),
            ],
            axis=1,
            sort=sort,
        )
        result = df1._append(df2, ignore_index=True, sort=sort)
        if sort:
            expected = expected[["end_time", "start_time"]]
        else:
            expected = expected[["start_time", "end_time"]]

        tm.assert_frame_equal(result, expected)

    def test_append_missing_column_proper_upcast(self, sort):
        df1 = DataFrame({"A": np.array([1, 2, 3, 4], dtype="i8")})
        df2 = DataFrame({"B": np.array([True, False, True, False], dtype=bool)})

        appended = df1._append(df2, ignore_index=True, sort=sort)
        assert appended["A"].dtype == "f8"
        assert appended["B"].dtype == "O"

    def test_append_empty_frame_to_series_with_dateutil_tz(self):
        # GH 23682
        date = Timestamp("2018-10-24 07:30:00", tz=dateutil.tz.tzutc())
        ser = Series({"a": 1.0, "b": 2.0, "date": date})
        df = DataFrame(columns=["c", "d"])
        result_a = df._append(ser, ignore_index=True)
        expected = DataFrame(
            [[np.nan, np.nan, 1.0, 2.0, date]], columns=["c", "d", "a", "b", "date"]
        )
        # These columns get cast to object after append
        expected["c"] = expected["c"].astype(object)
        expected["d"] = expected["d"].astype(object)
        tm.assert_frame_equal(result_a, expected)

        expected = DataFrame(
            [[np.nan, np.nan, 1.0, 2.0, date]] * 2, columns=["c", "d", "a", "b", "date"]
        )
        expected["c"] = expected["c"].astype(object)
        expected["d"] = expected["d"].astype(object)
        result_b = result_a._append(ser, ignore_index=True)
        tm.assert_frame_equal(result_b, expected)

        result = df._append([ser, ser], ignore_index=True)
        tm.assert_frame_equal(result, expected)

    def test_append_empty_tz_frame_with_datetime64ns(self, using_array_manager):
        # https://github.com/pandas-dev/pandas/issues/35460
        df = DataFrame(columns=["a"]).astype("datetime64[ns, UTC]")

        # pd.NaT gets inferred as tz-naive, so append result is tz-naive
        result = df._append({"a": pd.NaT}, ignore_index=True)
        if using_array_manager:
            expected = DataFrame({"a": [pd.NaT]}, dtype=object)
        else:
            expected = DataFrame({"a": [np.nan]}, dtype=object)
        tm.assert_frame_equal(result, expected)

        # also test with typed value to append
        df = DataFrame(columns=["a"]).astype("datetime64[ns, UTC]")
        other = Series({"a": pd.NaT}, dtype="datetime64[ns]")
        result = df._append(other, ignore_index=True)
        tm.assert_frame_equal(result, expected)

        # mismatched tz
        other = Series({"a": pd.NaT}, dtype="datetime64[ns, US/Pacific]")
        result = df._append(other, ignore_index=True)
        expected = DataFrame({"a": [pd.NaT]}).astype(object)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype_str", ["datetime64[ns, UTC]", "datetime64[ns]", "Int64", "int64"]
    )
    @pytest.mark.parametrize("val", [1, "NaT"])
    def test_append_empty_frame_with_timedelta64ns_nat(
        self, dtype_str, val, using_array_manager
    ):
        # https://github.com/pandas-dev/pandas/issues/35460
        df = DataFrame(columns=["a"]).astype(dtype_str)

        other = DataFrame({"a": [np.timedelta64(val, "ns")]})
        result = df._append(other, ignore_index=True)

        expected = other.astype(object)
        if isinstance(val, str) and dtype_str != "int64" and not using_array_manager:
            # TODO: expected used to be `other.astype(object)` which is a more
            #  reasonable result.  This was changed when tightening
            #  assert_frame_equal's treatment of mismatched NAs to match the
            #  existing behavior.
            expected = DataFrame({"a": [np.nan]}, dtype=object)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "dtype_str", ["datetime64[ns, UTC]", "datetime64[ns]", "Int64", "int64"]
    )
    @pytest.mark.parametrize("val", [1, "NaT"])
    def test_append_frame_with_timedelta64ns_nat(self, dtype_str, val):
        # https://github.com/pandas-dev/pandas/issues/35460
        df = DataFrame({"a": pd.array([1], dtype=dtype_str)})

        other = DataFrame({"a": [np.timedelta64(val, "ns")]})
        result = df._append(other, ignore_index=True)

        expected = DataFrame({"a": [df.iloc[0, 0], other.iloc[0, 0]]}, dtype=object)
        tm.assert_frame_equal(result, expected)
