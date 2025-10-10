""" test scalar indexing, including at and iat """
from datetime import (
    datetime,
    timedelta,
)
import itertools

import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    Timedelta,
    Timestamp,
    date_range,
)
import pandas._testing as tm


def generate_indices(f, values=False):
    """
    generate the indices
    if values is True , use the axis values
    is False, use the range
    """
    axes = f.axes
    if values:
        axes = (list(range(len(ax))) for ax in axes)

    return itertools.product(*axes)


class TestScalar:
    @pytest.mark.parametrize("kind", ["series", "frame"])
    @pytest.mark.parametrize("col", ["ints", "uints"])
    def test_iat_set_ints(self, kind, col, request):
        f = request.getfixturevalue(f"{kind}_{col}")
        indices = generate_indices(f, True)
        for i in indices:
            f.iat[i] = 1
            expected = f.values[i]
            tm.assert_almost_equal(expected, 1)

    @pytest.mark.parametrize("kind", ["series", "frame"])
    @pytest.mark.parametrize("col", ["labels", "ts", "floats"])
    def test_iat_set_other(self, kind, col, request):
        f = request.getfixturevalue(f"{kind}_{col}")
        msg = "iAt based indexing can only have integer indexers"
        with pytest.raises(ValueError, match=msg):
            idx = next(generate_indices(f, False))
            f.iat[idx] = 1

    @pytest.mark.parametrize("kind", ["series", "frame"])
    @pytest.mark.parametrize("col", ["ints", "uints", "labels", "ts", "floats"])
    def test_at_set_ints_other(self, kind, col, request):
        f = request.getfixturevalue(f"{kind}_{col}")
        indices = generate_indices(f, False)
        for i in indices:
            f.at[i] = 1
            expected = f.loc[i]
            tm.assert_almost_equal(expected, 1)


class TestAtAndiAT:
    # at and iat tests that don't need Base class

    def test_float_index_at_iat(self):
        ser = Series([1, 2, 3], index=[0.1, 0.2, 0.3])
        for el, item in ser.items():
            assert ser.at[el] == item
        for i in range(len(ser)):
            assert ser.iat[i] == i + 1

    def test_at_iat_coercion(self):
        # as timestamp is not a tuple!
        dates = date_range("1/1/2000", periods=8)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((8, 4)),
            index=dates,
            columns=["A", "B", "C", "D"],
        )
        s = df["A"]

        result = s.at[dates[5]]
        xp = s.values[5]
        assert result == xp

    @pytest.mark.parametrize(
        "ser, expected",
        [
            [
                Series(["2014-01-01", "2014-02-02"], dtype="datetime64[ns]"),
                Timestamp("2014-02-02"),
            ],
            [
                Series(["1 days", "2 days"], dtype="timedelta64[ns]"),
                Timedelta("2 days"),
            ],
        ],
    )
    def test_iloc_iat_coercion_datelike(self, indexer_ial, ser, expected):
        # GH 7729
        # make sure we are boxing the returns
        result = indexer_ial(ser)[1]
        assert result == expected

    def test_imethods_with_dups(self):
        # GH6493
        # iat/iloc with dups

        s = Series(range(5), index=[1, 1, 2, 2, 3], dtype="int64")
        result = s.iloc[2]
        assert result == 2
        result = s.iat[2]
        assert result == 2

        msg = "index 10 is out of bounds for axis 0 with size 5"
        with pytest.raises(IndexError, match=msg):
            s.iat[10]
        msg = "index -10 is out of bounds for axis 0 with size 5"
        with pytest.raises(IndexError, match=msg):
            s.iat[-10]

        result = s.iloc[[2, 3]]
        expected = Series([2, 3], [2, 2], dtype="int64")
        tm.assert_series_equal(result, expected)

        df = s.to_frame()
        result = df.iloc[2]
        expected = Series(2, index=[0], name=2)
        tm.assert_series_equal(result, expected)

        result = df.iat[2, 0]
        assert result == 2

    def test_frame_at_with_duplicate_axes(self):
        # GH#33041
        arr = np.random.default_rng(2).standard_normal(6).reshape(3, 2)
        df = DataFrame(arr, columns=["A", "A"])

        result = df.at[0, "A"]
        expected = df.iloc[0].copy()

        tm.assert_series_equal(result, expected)

        result = df.T.at["A", 0]
        tm.assert_series_equal(result, expected)

        # setter
        df.at[1, "A"] = 2
        expected = Series([2.0, 2.0], index=["A", "A"], name=1)
        tm.assert_series_equal(df.iloc[1], expected)

    def test_at_getitem_dt64tz_values(self):
        # gh-15822
        df = DataFrame(
            {
                "name": ["John", "Anderson"],
                "date": [
                    Timestamp(2017, 3, 13, 13, 32, 56),
                    Timestamp(2017, 2, 16, 12, 10, 3),
                ],
            }
        )
        df["date"] = df["date"].dt.tz_localize("Asia/Shanghai")

        expected = Timestamp("2017-03-13 13:32:56+0800", tz="Asia/Shanghai")

        result = df.loc[0, "date"]
        assert result == expected

        result = df.at[0, "date"]
        assert result == expected

    def test_mixed_index_at_iat_loc_iloc_series(self):
        # GH 19860
        s = Series([1, 2, 3, 4, 5], index=["a", "b", "c", 1, 2])
        for el, item in s.items():
            assert s.at[el] == s.loc[el] == item
        for i in range(len(s)):
            assert s.iat[i] == s.iloc[i] == i + 1

        with pytest.raises(KeyError, match="^4$"):
            s.at[4]
        with pytest.raises(KeyError, match="^4$"):
            s.loc[4]

    def test_mixed_index_at_iat_loc_iloc_dataframe(self):
        # GH 19860
        df = DataFrame(
            [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]], columns=["a", "b", "c", 1, 2]
        )
        for rowIdx, row in df.iterrows():
            for el, item in row.items():
                assert df.at[rowIdx, el] == df.loc[rowIdx, el] == item

        for row in range(2):
            for i in range(5):
                assert df.iat[row, i] == df.iloc[row, i] == row * 5 + i

        with pytest.raises(KeyError, match="^3$"):
            df.at[0, 3]
        with pytest.raises(KeyError, match="^3$"):
            df.loc[0, 3]

    def test_iat_setter_incompatible_assignment(self):
        # GH 23236
        result = DataFrame({"a": [0.0, 1.0], "b": [4, 5]})
        result.iat[0, 0] = None
        expected = DataFrame({"a": [None, 1], "b": [4, 5]})
        tm.assert_frame_equal(result, expected)


def test_iat_dont_wrap_object_datetimelike():
    # GH#32809 .iat calls go through DataFrame._get_value, should not
    #  call maybe_box_datetimelike
    dti = date_range("2016-01-01", periods=3)
    tdi = dti - dti
    ser = Series(dti.to_pydatetime(), dtype=object)
    ser2 = Series(tdi.to_pytimedelta(), dtype=object)
    df = DataFrame({"A": ser, "B": ser2})
    assert (df.dtypes == object).all()

    for result in [df.at[0, "A"], df.iat[0, 0], df.loc[0, "A"], df.iloc[0, 0]]:
        assert result is ser[0]
        assert isinstance(result, datetime)
        assert not isinstance(result, Timestamp)

    for result in [df.at[1, "B"], df.iat[1, 1], df.loc[1, "B"], df.iloc[1, 1]]:
        assert result is ser2[1]
        assert isinstance(result, timedelta)
        assert not isinstance(result, Timedelta)


def test_at_with_tuple_index_get():
    # GH 26989
    # DataFrame.at getter works with Index of tuples
    df = DataFrame({"a": [1, 2]}, index=[(1, 2), (3, 4)])
    assert df.index.nlevels == 1
    assert df.at[(1, 2), "a"] == 1

    # Series.at getter works with Index of tuples
    series = df["a"]
    assert series.index.nlevels == 1
    assert series.at[(1, 2)] == 1


@pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
def test_at_with_tuple_index_set():
    # GH 26989
    # DataFrame.at setter works with Index of tuples
    df = DataFrame({"a": [1, 2]}, index=[(1, 2), (3, 4)])
    assert df.index.nlevels == 1
    df.at[(1, 2), "a"] = 2
    assert df.at[(1, 2), "a"] == 2

    # Series.at setter works with Index of tuples
    series = df["a"]
    assert series.index.nlevels == 1
    series.at[1, 2] = 3
    assert series.at[1, 2] == 3


class TestMultiIndexScalar:
    def test_multiindex_at_get(self):
        # GH 26989
        # DataFrame.at and DataFrame.loc getter works with MultiIndex
        df = DataFrame({"a": [1, 2]}, index=[[1, 2], [3, 4]])
        assert df.index.nlevels == 2
        assert df.at[(1, 3), "a"] == 1
        assert df.loc[(1, 3), "a"] == 1

        # Series.at and Series.loc getter works with MultiIndex
        series = df["a"]
        assert series.index.nlevels == 2
        assert series.at[1, 3] == 1
        assert series.loc[1, 3] == 1

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    def test_multiindex_at_set(self):
        # GH 26989
        # DataFrame.at and DataFrame.loc setter works with MultiIndex
        df = DataFrame({"a": [1, 2]}, index=[[1, 2], [3, 4]])
        assert df.index.nlevels == 2
        df.at[(1, 3), "a"] = 3
        assert df.at[(1, 3), "a"] == 3
        df.loc[(1, 3), "a"] = 4
        assert df.loc[(1, 3), "a"] == 4

        # Series.at and Series.loc setter works with MultiIndex
        series = df["a"]
        assert series.index.nlevels == 2
        series.at[1, 3] = 5
        assert series.at[1, 3] == 5
        series.loc[1, 3] = 6
        assert series.loc[1, 3] == 6

    def test_multiindex_at_get_one_level(self):
        # GH#38053
        s2 = Series((0, 1), index=[[False, True]])
        result = s2.at[False]
        assert result == 0
