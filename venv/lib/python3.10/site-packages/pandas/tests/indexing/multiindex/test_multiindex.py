import numpy as np
import pytest

import pandas._libs.index as libindex
from pandas.errors import PerformanceWarning

import pandas as pd
from pandas import (
    CategoricalDtype,
    DataFrame,
    Index,
    MultiIndex,
    Series,
)
import pandas._testing as tm
from pandas.core.arrays.boolean import BooleanDtype


class TestMultiIndexBasic:
    def test_multiindex_perf_warn(self):
        df = DataFrame(
            {
                "jim": [0, 0, 1, 1],
                "joe": ["x", "x", "z", "y"],
                "jolie": np.random.default_rng(2).random(4),
            }
        ).set_index(["jim", "joe"])

        with tm.assert_produces_warning(PerformanceWarning):
            df.loc[(1, "z")]

        df = df.iloc[[2, 1, 3, 0]]
        with tm.assert_produces_warning(PerformanceWarning):
            df.loc[(0,)]

    @pytest.mark.parametrize("offset", [-5, 5])
    def test_indexing_over_hashtable_size_cutoff(self, monkeypatch, offset):
        size_cutoff = 20
        n = size_cutoff + offset

        with monkeypatch.context():
            monkeypatch.setattr(libindex, "_SIZE_CUTOFF", size_cutoff)
            s = Series(np.arange(n), MultiIndex.from_arrays((["a"] * n, np.arange(n))))

            # hai it works!
            assert s[("a", 5)] == 5
            assert s[("a", 6)] == 6
            assert s[("a", 7)] == 7

    def test_multi_nan_indexing(self):
        # GH 3588
        df = DataFrame(
            {
                "a": ["R1", "R2", np.nan, "R4"],
                "b": ["C1", "C2", "C3", "C4"],
                "c": [10, 15, np.nan, 20],
            }
        )
        result = df.set_index(["a", "b"], drop=False)
        expected = DataFrame(
            {
                "a": ["R1", "R2", np.nan, "R4"],
                "b": ["C1", "C2", "C3", "C4"],
                "c": [10, 15, np.nan, 20],
            },
            index=[
                Index(["R1", "R2", np.nan, "R4"], name="a"),
                Index(["C1", "C2", "C3", "C4"], name="b"),
            ],
        )
        tm.assert_frame_equal(result, expected)

    def test_exclusive_nat_column_indexing(self):
        # GH 38025
        # test multi indexing when one column exclusively contains NaT values
        df = DataFrame(
            {
                "a": [pd.NaT, pd.NaT, pd.NaT, pd.NaT],
                "b": ["C1", "C2", "C3", "C4"],
                "c": [10, 15, np.nan, 20],
            }
        )
        df = df.set_index(["a", "b"])
        expected = DataFrame(
            {
                "c": [10, 15, np.nan, 20],
            },
            index=[
                Index([pd.NaT, pd.NaT, pd.NaT, pd.NaT], name="a"),
                Index(["C1", "C2", "C3", "C4"], name="b"),
            ],
        )
        tm.assert_frame_equal(df, expected)

    def test_nested_tuples_duplicates(self):
        # GH#30892

        dti = pd.to_datetime(["20190101", "20190101", "20190102"])
        idx = Index(["a", "a", "c"])
        mi = MultiIndex.from_arrays([dti, idx], names=["index1", "index2"])

        df = DataFrame({"c1": [1, 2, 3], "c2": [np.nan, np.nan, np.nan]}, index=mi)

        expected = DataFrame({"c1": df["c1"], "c2": [1.0, 1.0, np.nan]}, index=mi)

        df2 = df.copy(deep=True)
        df2.loc[(dti[0], "a"), "c2"] = 1.0
        tm.assert_frame_equal(df2, expected)

        df3 = df.copy(deep=True)
        df3.loc[[(dti[0], "a")], "c2"] = 1.0
        tm.assert_frame_equal(df3, expected)

    def test_multiindex_with_datatime_level_preserves_freq(self):
        # https://github.com/pandas-dev/pandas/issues/35563
        idx = Index(range(2), name="A")
        dti = pd.date_range("2020-01-01", periods=7, freq="D", name="B")
        mi = MultiIndex.from_product([idx, dti])
        df = DataFrame(np.random.default_rng(2).standard_normal((14, 2)), index=mi)
        result = df.loc[0].index
        tm.assert_index_equal(result, dti)
        assert result.freq == dti.freq

    def test_multiindex_complex(self):
        # GH#42145
        complex_data = [1 + 2j, 4 - 3j, 10 - 1j]
        non_complex_data = [3, 4, 5]
        result = DataFrame(
            {
                "x": complex_data,
                "y": non_complex_data,
                "z": non_complex_data,
            }
        )
        result.set_index(["x", "y"], inplace=True)
        expected = DataFrame(
            {"z": non_complex_data},
            index=MultiIndex.from_arrays(
                [complex_data, non_complex_data],
                names=("x", "y"),
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_rename_multiindex_with_duplicates(self):
        # GH 38015
        mi = MultiIndex.from_tuples([("A", "cat"), ("B", "cat"), ("B", "cat")])
        df = DataFrame(index=mi)
        df = df.rename(index={"A": "Apple"}, level=0)

        mi2 = MultiIndex.from_tuples([("Apple", "cat"), ("B", "cat"), ("B", "cat")])
        expected = DataFrame(index=mi2)
        tm.assert_frame_equal(df, expected)

    def test_series_align_multiindex_with_nan_overlap_only(self):
        # GH 38439
        mi1 = MultiIndex.from_arrays([[81.0, np.nan], [np.nan, np.nan]])
        mi2 = MultiIndex.from_arrays([[np.nan, 82.0], [np.nan, np.nan]])
        ser1 = Series([1, 2], index=mi1)
        ser2 = Series([1, 2], index=mi2)
        result1, result2 = ser1.align(ser2)

        mi = MultiIndex.from_arrays([[81.0, 82.0, np.nan], [np.nan, np.nan, np.nan]])
        expected1 = Series([1.0, np.nan, 2.0], index=mi)
        expected2 = Series([np.nan, 2.0, 1.0], index=mi)

        tm.assert_series_equal(result1, expected1)
        tm.assert_series_equal(result2, expected2)

    def test_series_align_multiindex_with_nan(self):
        # GH 38439
        mi1 = MultiIndex.from_arrays([[81.0, np.nan], [np.nan, np.nan]])
        mi2 = MultiIndex.from_arrays([[np.nan, 81.0], [np.nan, np.nan]])
        ser1 = Series([1, 2], index=mi1)
        ser2 = Series([1, 2], index=mi2)
        result1, result2 = ser1.align(ser2)

        mi = MultiIndex.from_arrays([[81.0, np.nan], [np.nan, np.nan]])
        expected1 = Series([1, 2], index=mi)
        expected2 = Series([2, 1], index=mi)

        tm.assert_series_equal(result1, expected1)
        tm.assert_series_equal(result2, expected2)

    def test_nunique_smoke(self):
        # GH 34019
        n = DataFrame([[1, 2], [1, 2]]).set_index([0, 1]).index.nunique()
        assert n == 1

    def test_multiindex_repeated_keys(self):
        # GH19414
        tm.assert_series_equal(
            Series([1, 2], MultiIndex.from_arrays([["a", "b"]])).loc[
                ["a", "a", "b", "b"]
            ],
            Series([1, 1, 2, 2], MultiIndex.from_arrays([["a", "a", "b", "b"]])),
        )

    def test_multiindex_with_na_missing_key(self):
        # GH46173
        df = DataFrame.from_dict(
            {
                ("foo",): [1, 2, 3],
                ("bar",): [5, 6, 7],
                (None,): [8, 9, 0],
            }
        )
        with pytest.raises(KeyError, match="missing_key"):
            df[[("missing_key",)]]

    def test_multiindex_dtype_preservation(self):
        # GH51261
        columns = MultiIndex.from_tuples([("A", "B")], names=["lvl1", "lvl2"])
        df = DataFrame(["value"], columns=columns).astype("category")
        df_no_multiindex = df["A"]
        assert isinstance(df_no_multiindex["B"].dtype, CategoricalDtype)

        # geopandas 1763 analogue
        df = DataFrame(
            [[1, 0], [0, 1]],
            columns=[
                ["foo", "foo"],
                ["location", "location"],
                ["x", "y"],
            ],
        ).assign(bools=Series([True, False], dtype="boolean"))
        assert isinstance(df["bools"].dtype, BooleanDtype)

    def test_multiindex_from_tuples_with_nan(self):
        # GH#23578
        result = MultiIndex.from_tuples([("a", "b", "c"), np.nan, ("d", "", "")])
        expected = MultiIndex.from_tuples(
            [("a", "b", "c"), (np.nan, np.nan, np.nan), ("d", "", "")]
        )
        tm.assert_index_equal(result, expected)
