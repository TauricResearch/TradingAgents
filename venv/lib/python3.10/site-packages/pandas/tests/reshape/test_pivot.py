from datetime import (
    date,
    datetime,
    timedelta,
)
from itertools import product
import re

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas.errors import PerformanceWarning

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Grouper,
    Index,
    MultiIndex,
    Series,
    concat,
    date_range,
)
import pandas._testing as tm
from pandas.api.types import CategoricalDtype
from pandas.core.reshape import reshape as reshape_lib
from pandas.core.reshape.pivot import pivot_table


@pytest.fixture(params=[True, False])
def dropna(request):
    return request.param


@pytest.fixture(params=[([0] * 4, [1] * 4), (range(3), range(1, 4))])
def interval_values(request, closed):
    left, right = request.param
    return Categorical(pd.IntervalIndex.from_arrays(left, right, closed))


class TestPivotTable:
    @pytest.fixture
    def data(self):
        return DataFrame(
            {
                "A": [
                    "foo",
                    "foo",
                    "foo",
                    "foo",
                    "bar",
                    "bar",
                    "bar",
                    "bar",
                    "foo",
                    "foo",
                    "foo",
                ],
                "B": [
                    "one",
                    "one",
                    "one",
                    "two",
                    "one",
                    "one",
                    "one",
                    "two",
                    "two",
                    "two",
                    "one",
                ],
                "C": [
                    "dull",
                    "dull",
                    "shiny",
                    "dull",
                    "dull",
                    "shiny",
                    "shiny",
                    "dull",
                    "shiny",
                    "shiny",
                    "shiny",
                ],
                "D": np.random.default_rng(2).standard_normal(11),
                "E": np.random.default_rng(2).standard_normal(11),
                "F": np.random.default_rng(2).standard_normal(11),
            }
        )

    def test_pivot_table(self, observed, data):
        index = ["A", "B"]
        columns = "C"
        table = pivot_table(
            data, values="D", index=index, columns=columns, observed=observed
        )

        table2 = data.pivot_table(
            values="D", index=index, columns=columns, observed=observed
        )
        tm.assert_frame_equal(table, table2)

        # this works
        pivot_table(data, values="D", index=index, observed=observed)

        if len(index) > 1:
            assert table.index.names == tuple(index)
        else:
            assert table.index.name == index[0]

        if len(columns) > 1:
            assert table.columns.names == columns
        else:
            assert table.columns.name == columns[0]

        expected = data.groupby(index + [columns])["D"].agg("mean").unstack()
        tm.assert_frame_equal(table, expected)

    def test_pivot_table_categorical_observed_equal(self, observed):
        # issue #24923
        df = DataFrame(
            {"col1": list("abcde"), "col2": list("fghij"), "col3": [1, 2, 3, 4, 5]}
        )

        expected = df.pivot_table(
            index="col1", values="col3", columns="col2", aggfunc="sum", fill_value=0
        )

        expected.index = expected.index.astype("category")
        expected.columns = expected.columns.astype("category")

        df.col1 = df.col1.astype("category")
        df.col2 = df.col2.astype("category")

        result = df.pivot_table(
            index="col1",
            values="col3",
            columns="col2",
            aggfunc="sum",
            fill_value=0,
            observed=observed,
        )

        tm.assert_frame_equal(result, expected)

    def test_pivot_table_nocols(self):
        df = DataFrame(
            {"rows": ["a", "b", "c"], "cols": ["x", "y", "z"], "values": [1, 2, 3]}
        )
        rs = df.pivot_table(columns="cols", aggfunc="sum")
        xp = df.pivot_table(index="cols", aggfunc="sum").T
        tm.assert_frame_equal(rs, xp)

        rs = df.pivot_table(columns="cols", aggfunc={"values": "mean"})
        xp = df.pivot_table(index="cols", aggfunc={"values": "mean"}).T
        tm.assert_frame_equal(rs, xp)

    def test_pivot_table_dropna(self):
        df = DataFrame(
            {
                "amount": {0: 60000, 1: 100000, 2: 50000, 3: 30000},
                "customer": {0: "A", 1: "A", 2: "B", 3: "C"},
                "month": {0: 201307, 1: 201309, 2: 201308, 3: 201310},
                "product": {0: "a", 1: "b", 2: "c", 3: "d"},
                "quantity": {0: 2000000, 1: 500000, 2: 1000000, 3: 1000000},
            }
        )
        pv_col = df.pivot_table(
            "quantity", "month", ["customer", "product"], dropna=False
        )
        pv_ind = df.pivot_table(
            "quantity", ["customer", "product"], "month", dropna=False
        )

        m = MultiIndex.from_tuples(
            [
                ("A", "a"),
                ("A", "b"),
                ("A", "c"),
                ("A", "d"),
                ("B", "a"),
                ("B", "b"),
                ("B", "c"),
                ("B", "d"),
                ("C", "a"),
                ("C", "b"),
                ("C", "c"),
                ("C", "d"),
            ],
            names=["customer", "product"],
        )
        tm.assert_index_equal(pv_col.columns, m)
        tm.assert_index_equal(pv_ind.index, m)

    def test_pivot_table_categorical(self):
        cat1 = Categorical(
            ["a", "a", "b", "b"], categories=["a", "b", "z"], ordered=True
        )
        cat2 = Categorical(
            ["c", "d", "c", "d"], categories=["c", "d", "y"], ordered=True
        )
        df = DataFrame({"A": cat1, "B": cat2, "values": [1, 2, 3, 4]})
        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = pivot_table(df, values="values", index=["A", "B"], dropna=True)

        exp_index = MultiIndex.from_arrays([cat1, cat2], names=["A", "B"])
        expected = DataFrame({"values": [1.0, 2.0, 3.0, 4.0]}, index=exp_index)
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_dropna_categoricals(self, dropna):
        # GH 15193
        categories = ["a", "b", "c", "d"]

        df = DataFrame(
            {
                "A": ["a", "a", "a", "b", "b", "b", "c", "c", "c"],
                "B": [1, 2, 3, 1, 2, 3, 1, 2, 3],
                "C": range(9),
            }
        )

        df["A"] = df["A"].astype(CategoricalDtype(categories, ordered=False))
        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.pivot_table(index="B", columns="A", values="C", dropna=dropna)
        expected_columns = Series(["a", "b", "c"], name="A")
        expected_columns = expected_columns.astype(
            CategoricalDtype(categories, ordered=False)
        )
        expected_index = Series([1, 2, 3], name="B")
        expected = DataFrame(
            [[0.0, 3.0, 6.0], [1.0, 4.0, 7.0], [2.0, 5.0, 8.0]],
            index=expected_index,
            columns=expected_columns,
        )
        if not dropna:
            # add back the non observed to compare
            expected = expected.reindex(columns=Categorical(categories)).astype("float")

        tm.assert_frame_equal(result, expected)

    def test_pivot_with_non_observable_dropna(self, dropna):
        # gh-21133
        df = DataFrame(
            {
                "A": Categorical(
                    [np.nan, "low", "high", "low", "high"],
                    categories=["low", "high"],
                    ordered=True,
                ),
                "B": [0.0, 1.0, 2.0, 3.0, 4.0],
            }
        )

        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.pivot_table(index="A", values="B", dropna=dropna)
        if dropna:
            values = [2.0, 3.0]
            codes = [0, 1]
        else:
            # GH: 10772
            values = [2.0, 3.0, 0.0]
            codes = [0, 1, -1]
        expected = DataFrame(
            {"B": values},
            index=Index(
                Categorical.from_codes(
                    codes, categories=["low", "high"], ordered=dropna
                ),
                name="A",
            ),
        )

        tm.assert_frame_equal(result, expected)

    def test_pivot_with_non_observable_dropna_multi_cat(self, dropna):
        # gh-21378
        df = DataFrame(
            {
                "A": Categorical(
                    ["left", "low", "high", "low", "high"],
                    categories=["low", "high", "left"],
                    ordered=True,
                ),
                "B": range(5),
            }
        )

        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.pivot_table(index="A", values="B", dropna=dropna)
        expected = DataFrame(
            {"B": [2.0, 3.0, 0.0]},
            index=Index(
                Categorical.from_codes(
                    [0, 1, 2], categories=["low", "high", "left"], ordered=True
                ),
                name="A",
            ),
        )
        if not dropna:
            expected["B"] = expected["B"].astype(float)

        tm.assert_frame_equal(result, expected)

    def test_pivot_with_interval_index(self, interval_values, dropna):
        # GH 25814
        df = DataFrame({"A": interval_values, "B": 1})

        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.pivot_table(index="A", values="B", dropna=dropna)
        expected = DataFrame(
            {"B": 1.0}, index=Index(interval_values.unique(), name="A")
        )
        if not dropna:
            expected = expected.astype(float)
        tm.assert_frame_equal(result, expected)

    def test_pivot_with_interval_index_margins(self):
        # GH 25815
        ordered_cat = pd.IntervalIndex.from_arrays([0, 0, 1, 1], [1, 1, 2, 2])
        df = DataFrame(
            {
                "A": np.arange(4, 0, -1, dtype=np.intp),
                "B": ["a", "b", "a", "b"],
                "C": Categorical(ordered_cat, ordered=True).sort_values(
                    ascending=False
                ),
            }
        )

        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            pivot_tab = pivot_table(
                df, index="C", columns="B", values="A", aggfunc="sum", margins=True
            )

        result = pivot_tab["All"]
        expected = Series(
            [3, 7, 10],
            index=Index([pd.Interval(0, 1), pd.Interval(1, 2), "All"], name="C"),
            name="All",
            dtype=np.intp,
        )
        tm.assert_series_equal(result, expected)

    def test_pass_array(self, data):
        result = data.pivot_table("D", index=data.A, columns=data.C)
        expected = data.pivot_table("D", index="A", columns="C")
        tm.assert_frame_equal(result, expected)

    def test_pass_function(self, data):
        result = data.pivot_table("D", index=lambda x: x // 5, columns=data.C)
        expected = data.pivot_table("D", index=data.index // 5, columns="C")
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_multiple(self, data):
        index = ["A", "B"]
        columns = "C"
        table = pivot_table(data, index=index, columns=columns)
        expected = data.groupby(index + [columns]).agg("mean").unstack()
        tm.assert_frame_equal(table, expected)

    def test_pivot_dtypes(self):
        # can convert dtypes
        f = DataFrame(
            {
                "a": ["cat", "bat", "cat", "bat"],
                "v": [1, 2, 3, 4],
                "i": ["a", "b", "a", "b"],
            }
        )
        assert f.dtypes["v"] == "int64"

        z = pivot_table(
            f, values="v", index=["a"], columns=["i"], fill_value=0, aggfunc="sum"
        )
        result = z.dtypes
        expected = Series([np.dtype("int64")] * 2, index=Index(list("ab"), name="i"))
        tm.assert_series_equal(result, expected)

        # cannot convert dtypes
        f = DataFrame(
            {
                "a": ["cat", "bat", "cat", "bat"],
                "v": [1.5, 2.5, 3.5, 4.5],
                "i": ["a", "b", "a", "b"],
            }
        )
        assert f.dtypes["v"] == "float64"

        z = pivot_table(
            f, values="v", index=["a"], columns=["i"], fill_value=0, aggfunc="mean"
        )
        result = z.dtypes
        expected = Series([np.dtype("float64")] * 2, index=Index(list("ab"), name="i"))
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "columns,values",
        [
            ("bool1", ["float1", "float2"]),
            ("bool1", ["float1", "float2", "bool1"]),
            ("bool2", ["float1", "float2", "bool1"]),
        ],
    )
    def test_pivot_preserve_dtypes(self, columns, values):
        # GH 7142 regression test
        v = np.arange(5, dtype=np.float64)
        df = DataFrame(
            {"float1": v, "float2": v + 2.0, "bool1": v <= 2, "bool2": v <= 3}
        )

        df_res = df.reset_index().pivot_table(
            index="index", columns=columns, values=values
        )

        result = dict(df_res.dtypes)
        expected = {col: np.dtype("float64") for col in df_res}
        assert result == expected

    def test_pivot_no_values(self):
        # GH 14380
        idx = pd.DatetimeIndex(
            ["2011-01-01", "2011-02-01", "2011-01-02", "2011-01-01", "2011-01-02"]
        )
        df = DataFrame({"A": [1, 2, 3, 4, 5]}, index=idx)
        res = df.pivot_table(index=df.index.month, columns=df.index.day)

        exp_columns = MultiIndex.from_tuples([("A", 1), ("A", 2)])
        exp_columns = exp_columns.set_levels(
            exp_columns.levels[1].astype(np.int32), level=1
        )
        exp = DataFrame(
            [[2.5, 4.0], [2.0, np.nan]],
            index=Index([1, 2], dtype=np.int32),
            columns=exp_columns,
        )
        tm.assert_frame_equal(res, exp)

        df = DataFrame(
            {
                "A": [1, 2, 3, 4, 5],
                "dt": date_range("2011-01-01", freq="D", periods=5),
            },
            index=idx,
        )
        res = df.pivot_table(index=df.index.month, columns=Grouper(key="dt", freq="ME"))
        exp_columns = MultiIndex.from_arrays(
            [["A"], pd.DatetimeIndex(["2011-01-31"], dtype="M8[ns]")],
            names=[None, "dt"],
        )
        exp = DataFrame(
            [3.25, 2.0], index=Index([1, 2], dtype=np.int32), columns=exp_columns
        )
        tm.assert_frame_equal(res, exp)

        res = df.pivot_table(
            index=Grouper(freq="YE"), columns=Grouper(key="dt", freq="ME")
        )
        exp = DataFrame(
            [3.0],
            index=pd.DatetimeIndex(["2011-12-31"], freq="YE"),
            columns=exp_columns,
        )
        tm.assert_frame_equal(res, exp)

    def test_pivot_multi_values(self, data):
        result = pivot_table(
            data, values=["D", "E"], index="A", columns=["B", "C"], fill_value=0
        )
        expected = pivot_table(
            data.drop(["F"], axis=1), index="A", columns=["B", "C"], fill_value=0
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_multi_functions(self, data):
        f = lambda func: pivot_table(
            data, values=["D", "E"], index=["A", "B"], columns="C", aggfunc=func
        )
        result = f(["mean", "std"])
        means = f("mean")
        stds = f("std")
        expected = concat([means, stds], keys=["mean", "std"], axis=1)
        tm.assert_frame_equal(result, expected)

        # margins not supported??
        f = lambda func: pivot_table(
            data,
            values=["D", "E"],
            index=["A", "B"],
            columns="C",
            aggfunc=func,
            margins=True,
        )
        result = f(["mean", "std"])
        means = f("mean")
        stds = f("std")
        expected = concat([means, stds], keys=["mean", "std"], axis=1)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_index_with_nan(self, method):
        # GH 3588
        nan = np.nan
        df = DataFrame(
            {
                "a": ["R1", "R2", nan, "R4"],
                "b": ["C1", "C2", "C3", "C4"],
                "c": [10, 15, 17, 20],
            }
        )
        if method:
            result = df.pivot(index="a", columns="b", values="c")
        else:
            result = pd.pivot(df, index="a", columns="b", values="c")
        expected = DataFrame(
            [
                [nan, nan, 17, nan],
                [10, nan, nan, nan],
                [nan, 15, nan, nan],
                [nan, nan, nan, 20],
            ],
            index=Index([nan, "R1", "R2", "R4"], name="a"),
            columns=Index(["C1", "C2", "C3", "C4"], name="b"),
        )
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(df.pivot(index="b", columns="a", values="c"), expected.T)

    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_index_with_nan_dates(self, method):
        # GH9491
        df = DataFrame(
            {
                "a": date_range("2014-02-01", periods=6, freq="D"),
                "c": 100 + np.arange(6),
            }
        )
        df["b"] = df["a"] - pd.Timestamp("2014-02-02")
        df.loc[1, "a"] = df.loc[3, "a"] = np.nan
        df.loc[1, "b"] = df.loc[4, "b"] = np.nan

        if method:
            pv = df.pivot(index="a", columns="b", values="c")
        else:
            pv = pd.pivot(df, index="a", columns="b", values="c")
        assert pv.notna().values.sum() == len(df)

        for _, row in df.iterrows():
            assert pv.loc[row["a"], row["b"]] == row["c"]

        if method:
            result = df.pivot(index="b", columns="a", values="c")
        else:
            result = pd.pivot(df, index="b", columns="a", values="c")
        tm.assert_frame_equal(result, pv.T)

    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_with_tz(self, method, unit):
        # GH 5878
        df = DataFrame(
            {
                "dt1": pd.DatetimeIndex(
                    [
                        datetime(2013, 1, 1, 9, 0),
                        datetime(2013, 1, 2, 9, 0),
                        datetime(2013, 1, 1, 9, 0),
                        datetime(2013, 1, 2, 9, 0),
                    ],
                    dtype=f"M8[{unit}, US/Pacific]",
                ),
                "dt2": pd.DatetimeIndex(
                    [
                        datetime(2014, 1, 1, 9, 0),
                        datetime(2014, 1, 1, 9, 0),
                        datetime(2014, 1, 2, 9, 0),
                        datetime(2014, 1, 2, 9, 0),
                    ],
                    dtype=f"M8[{unit}, Asia/Tokyo]",
                ),
                "data1": np.arange(4, dtype="int64"),
                "data2": np.arange(4, dtype="int64"),
            }
        )

        exp_col1 = Index(["data1", "data1", "data2", "data2"])
        exp_col2 = pd.DatetimeIndex(
            ["2014/01/01 09:00", "2014/01/02 09:00"] * 2,
            name="dt2",
            dtype=f"M8[{unit}, Asia/Tokyo]",
        )
        exp_col = MultiIndex.from_arrays([exp_col1, exp_col2])
        exp_idx = pd.DatetimeIndex(
            ["2013/01/01 09:00", "2013/01/02 09:00"],
            name="dt1",
            dtype=f"M8[{unit}, US/Pacific]",
        )
        expected = DataFrame(
            [[0, 2, 0, 2], [1, 3, 1, 3]],
            index=exp_idx,
            columns=exp_col,
        )

        if method:
            pv = df.pivot(index="dt1", columns="dt2")
        else:
            pv = pd.pivot(df, index="dt1", columns="dt2")
        tm.assert_frame_equal(pv, expected)

        expected = DataFrame(
            [[0, 2], [1, 3]],
            index=exp_idx,
            columns=exp_col2[:2],
        )

        if method:
            pv = df.pivot(index="dt1", columns="dt2", values="data1")
        else:
            pv = pd.pivot(df, index="dt1", columns="dt2", values="data1")
        tm.assert_frame_equal(pv, expected)

    def test_pivot_tz_in_values(self):
        # GH 14948
        df = DataFrame(
            [
                {
                    "uid": "aa",
                    "ts": pd.Timestamp("2016-08-12 13:00:00-0700", tz="US/Pacific"),
                },
                {
                    "uid": "aa",
                    "ts": pd.Timestamp("2016-08-12 08:00:00-0700", tz="US/Pacific"),
                },
                {
                    "uid": "aa",
                    "ts": pd.Timestamp("2016-08-12 14:00:00-0700", tz="US/Pacific"),
                },
                {
                    "uid": "aa",
                    "ts": pd.Timestamp("2016-08-25 11:00:00-0700", tz="US/Pacific"),
                },
                {
                    "uid": "aa",
                    "ts": pd.Timestamp("2016-08-25 13:00:00-0700", tz="US/Pacific"),
                },
            ]
        )

        df = df.set_index("ts").reset_index()
        mins = df.ts.map(lambda x: x.replace(hour=0, minute=0, second=0, microsecond=0))

        result = pivot_table(
            df.set_index("ts").reset_index(),
            values="ts",
            index=["uid"],
            columns=[mins],
            aggfunc="min",
        )
        expected = DataFrame(
            [
                [
                    pd.Timestamp("2016-08-12 08:00:00-0700", tz="US/Pacific"),
                    pd.Timestamp("2016-08-25 11:00:00-0700", tz="US/Pacific"),
                ]
            ],
            index=Index(["aa"], name="uid"),
            columns=pd.DatetimeIndex(
                [
                    pd.Timestamp("2016-08-12 00:00:00", tz="US/Pacific"),
                    pd.Timestamp("2016-08-25 00:00:00", tz="US/Pacific"),
                ],
                name="ts",
            ),
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_periods(self, method):
        df = DataFrame(
            {
                "p1": [
                    pd.Period("2013-01-01", "D"),
                    pd.Period("2013-01-02", "D"),
                    pd.Period("2013-01-01", "D"),
                    pd.Period("2013-01-02", "D"),
                ],
                "p2": [
                    pd.Period("2013-01", "M"),
                    pd.Period("2013-01", "M"),
                    pd.Period("2013-02", "M"),
                    pd.Period("2013-02", "M"),
                ],
                "data1": np.arange(4, dtype="int64"),
                "data2": np.arange(4, dtype="int64"),
            }
        )

        exp_col1 = Index(["data1", "data1", "data2", "data2"])
        exp_col2 = pd.PeriodIndex(["2013-01", "2013-02"] * 2, name="p2", freq="M")
        exp_col = MultiIndex.from_arrays([exp_col1, exp_col2])
        expected = DataFrame(
            [[0, 2, 0, 2], [1, 3, 1, 3]],
            index=pd.PeriodIndex(["2013-01-01", "2013-01-02"], name="p1", freq="D"),
            columns=exp_col,
        )
        if method:
            pv = df.pivot(index="p1", columns="p2")
        else:
            pv = pd.pivot(df, index="p1", columns="p2")
        tm.assert_frame_equal(pv, expected)

        expected = DataFrame(
            [[0, 2], [1, 3]],
            index=pd.PeriodIndex(["2013-01-01", "2013-01-02"], name="p1", freq="D"),
            columns=pd.PeriodIndex(["2013-01", "2013-02"], name="p2", freq="M"),
        )
        if method:
            pv = df.pivot(index="p1", columns="p2", values="data1")
        else:
            pv = pd.pivot(df, index="p1", columns="p2", values="data1")
        tm.assert_frame_equal(pv, expected)

    def test_pivot_periods_with_margins(self):
        # GH 28323
        df = DataFrame(
            {
                "a": [1, 1, 2, 2],
                "b": [
                    pd.Period("2019Q1"),
                    pd.Period("2019Q2"),
                    pd.Period("2019Q1"),
                    pd.Period("2019Q2"),
                ],
                "x": 1.0,
            }
        )

        expected = DataFrame(
            data=1.0,
            index=Index([1, 2, "All"], name="a"),
            columns=Index([pd.Period("2019Q1"), pd.Period("2019Q2"), "All"], name="b"),
        )

        result = df.pivot_table(index="a", columns="b", values="x", margins=True)
        tm.assert_frame_equal(expected, result)

    @pytest.mark.parametrize(
        "values",
        [
            ["baz", "zoo"],
            np.array(["baz", "zoo"]),
            Series(["baz", "zoo"]),
            Index(["baz", "zoo"]),
        ],
    )
    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_with_list_like_values(self, values, method):
        # issue #17160
        df = DataFrame(
            {
                "foo": ["one", "one", "one", "two", "two", "two"],
                "bar": ["A", "B", "C", "A", "B", "C"],
                "baz": [1, 2, 3, 4, 5, 6],
                "zoo": ["x", "y", "z", "q", "w", "t"],
            }
        )

        if method:
            result = df.pivot(index="foo", columns="bar", values=values)
        else:
            result = pd.pivot(df, index="foo", columns="bar", values=values)

        data = [[1, 2, 3, "x", "y", "z"], [4, 5, 6, "q", "w", "t"]]
        index = Index(data=["one", "two"], name="foo")
        columns = MultiIndex(
            levels=[["baz", "zoo"], ["A", "B", "C"]],
            codes=[[0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 1, 2]],
            names=[None, "bar"],
        )
        expected = DataFrame(data=data, index=index, columns=columns)
        expected["baz"] = expected["baz"].astype(object)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "values",
        [
            ["bar", "baz"],
            np.array(["bar", "baz"]),
            Series(["bar", "baz"]),
            Index(["bar", "baz"]),
        ],
    )
    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_with_list_like_values_nans(self, values, method):
        # issue #17160
        df = DataFrame(
            {
                "foo": ["one", "one", "one", "two", "two", "two"],
                "bar": ["A", "B", "C", "A", "B", "C"],
                "baz": [1, 2, 3, 4, 5, 6],
                "zoo": ["x", "y", "z", "q", "w", "t"],
            }
        )

        if method:
            result = df.pivot(index="zoo", columns="foo", values=values)
        else:
            result = pd.pivot(df, index="zoo", columns="foo", values=values)

        data = [
            [np.nan, "A", np.nan, 4],
            [np.nan, "C", np.nan, 6],
            [np.nan, "B", np.nan, 5],
            ["A", np.nan, 1, np.nan],
            ["B", np.nan, 2, np.nan],
            ["C", np.nan, 3, np.nan],
        ]
        index = Index(data=["q", "t", "w", "x", "y", "z"], name="zoo")
        columns = MultiIndex(
            levels=[["bar", "baz"], ["one", "two"]],
            codes=[[0, 0, 1, 1], [0, 1, 0, 1]],
            names=[None, "foo"],
        )
        expected = DataFrame(data=data, index=index, columns=columns)
        expected["baz"] = expected["baz"].astype(object)
        tm.assert_frame_equal(result, expected)

    def test_pivot_columns_none_raise_error(self):
        # GH 30924
        df = DataFrame({"col1": ["a", "b", "c"], "col2": [1, 2, 3], "col3": [1, 2, 3]})
        msg = r"pivot\(\) missing 1 required keyword-only argument: 'columns'"
        with pytest.raises(TypeError, match=msg):
            df.pivot(index="col1", values="col3")  # pylint: disable=missing-kwoa

    @pytest.mark.xfail(
        reason="MultiIndexed unstack with tuple names fails with KeyError GH#19966"
    )
    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_with_multiindex(self, method):
        # issue #17160
        index = Index(data=[0, 1, 2, 3, 4, 5])
        data = [
            ["one", "A", 1, "x"],
            ["one", "B", 2, "y"],
            ["one", "C", 3, "z"],
            ["two", "A", 4, "q"],
            ["two", "B", 5, "w"],
            ["two", "C", 6, "t"],
        ]
        columns = MultiIndex(
            levels=[["bar", "baz"], ["first", "second"]],
            codes=[[0, 0, 1, 1], [0, 1, 0, 1]],
        )
        df = DataFrame(data=data, index=index, columns=columns, dtype="object")
        if method:
            result = df.pivot(
                index=("bar", "first"),
                columns=("bar", "second"),
                values=("baz", "first"),
            )
        else:
            result = pd.pivot(
                df,
                index=("bar", "first"),
                columns=("bar", "second"),
                values=("baz", "first"),
            )

        data = {
            "A": Series([1, 4], index=["one", "two"]),
            "B": Series([2, 5], index=["one", "two"]),
            "C": Series([3, 6], index=["one", "two"]),
        }
        expected = DataFrame(data)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("method", [True, False])
    def test_pivot_with_tuple_of_values(self, method):
        # issue #17160
        df = DataFrame(
            {
                "foo": ["one", "one", "one", "two", "two", "two"],
                "bar": ["A", "B", "C", "A", "B", "C"],
                "baz": [1, 2, 3, 4, 5, 6],
                "zoo": ["x", "y", "z", "q", "w", "t"],
            }
        )
        with pytest.raises(KeyError, match=r"^\('bar', 'baz'\)$"):
            # tuple is seen as a single column name
            if method:
                df.pivot(index="zoo", columns="foo", values=("bar", "baz"))
            else:
                pd.pivot(df, index="zoo", columns="foo", values=("bar", "baz"))

    def _check_output(
        self,
        result,
        values_col,
        data,
        index=["A", "B"],
        columns=["C"],
        margins_col="All",
    ):
        col_margins = result.loc[result.index[:-1], margins_col]
        expected_col_margins = data.groupby(index)[values_col].mean()
        tm.assert_series_equal(col_margins, expected_col_margins, check_names=False)
        assert col_margins.name == margins_col

        result = result.sort_index()
        index_margins = result.loc[(margins_col, "")].iloc[:-1]

        expected_ix_margins = data.groupby(columns)[values_col].mean()
        tm.assert_series_equal(index_margins, expected_ix_margins, check_names=False)
        assert index_margins.name == (margins_col, "")

        grand_total_margins = result.loc[(margins_col, ""), margins_col]
        expected_total_margins = data[values_col].mean()
        assert grand_total_margins == expected_total_margins

    def test_margins(self, data):
        # column specified
        result = data.pivot_table(
            values="D", index=["A", "B"], columns="C", margins=True, aggfunc="mean"
        )
        self._check_output(result, "D", data)

        # Set a different margins_name (not 'All')
        result = data.pivot_table(
            values="D",
            index=["A", "B"],
            columns="C",
            margins=True,
            aggfunc="mean",
            margins_name="Totals",
        )
        self._check_output(result, "D", data, margins_col="Totals")

        # no column specified
        table = data.pivot_table(
            index=["A", "B"], columns="C", margins=True, aggfunc="mean"
        )
        for value_col in table.columns.levels[0]:
            self._check_output(table[value_col], value_col, data)

    def test_no_col(self, data, using_infer_string):
        # no col

        # to help with a buglet
        data.columns = [k * 2 for k in data.columns]
        msg = re.escape("agg function failed [how->mean,dtype->")
        if using_infer_string:
            msg = "dtype 'str' does not support operation 'mean'"
        with pytest.raises(TypeError, match=msg):
            data.pivot_table(index=["AA", "BB"], margins=True, aggfunc="mean")
        table = data.drop(columns="CC").pivot_table(
            index=["AA", "BB"], margins=True, aggfunc="mean"
        )
        for value_col in table.columns:
            totals = table.loc[("All", ""), value_col]
            assert totals == data[value_col].mean()

        with pytest.raises(TypeError, match=msg):
            data.pivot_table(index=["AA", "BB"], margins=True, aggfunc="mean")
        table = data.drop(columns="CC").pivot_table(
            index=["AA", "BB"], margins=True, aggfunc="mean"
        )
        for item in ["DD", "EE", "FF"]:
            totals = table.loc[("All", ""), item]
            assert totals == data[item].mean()

    @pytest.mark.parametrize(
        "columns, aggfunc, values, expected_columns",
        [
            (
                "A",
                "mean",
                [[5.5, 5.5, 2.2, 2.2], [8.0, 8.0, 4.4, 4.4]],
                Index(["bar", "All", "foo", "All"], name="A"),
            ),
            (
                ["A", "B"],
                "sum",
                [
                    [9, 13, 22, 5, 6, 11],
                    [14, 18, 32, 11, 11, 22],
                ],
                MultiIndex.from_tuples(
                    [
                        ("bar", "one"),
                        ("bar", "two"),
                        ("bar", "All"),
                        ("foo", "one"),
                        ("foo", "two"),
                        ("foo", "All"),
                    ],
                    names=["A", "B"],
                ),
            ),
        ],
    )
    def test_margin_with_only_columns_defined(
        self, columns, aggfunc, values, expected_columns, using_infer_string
    ):
        # GH 31016
        df = DataFrame(
            {
                "A": ["foo", "foo", "foo", "foo", "foo", "bar", "bar", "bar", "bar"],
                "B": ["one", "one", "one", "two", "two", "one", "one", "two", "two"],
                "C": [
                    "small",
                    "large",
                    "large",
                    "small",
                    "small",
                    "large",
                    "small",
                    "small",
                    "large",
                ],
                "D": [1, 2, 2, 3, 3, 4, 5, 6, 7],
                "E": [2, 4, 5, 5, 6, 6, 8, 9, 9],
            }
        )
        if aggfunc != "sum":
            msg = re.escape("agg function failed [how->mean,dtype->")
            if using_infer_string:
                msg = "dtype 'str' does not support operation 'mean'"
            with pytest.raises(TypeError, match=msg):
                df.pivot_table(columns=columns, margins=True, aggfunc=aggfunc)
        if "B" not in columns:
            df = df.drop(columns="B")
        result = df.drop(columns="C").pivot_table(
            columns=columns, margins=True, aggfunc=aggfunc
        )
        expected = DataFrame(values, index=Index(["D", "E"]), columns=expected_columns)

        tm.assert_frame_equal(result, expected)

    def test_margins_dtype(self, data):
        # GH 17013

        df = data.copy()
        df[["D", "E", "F"]] = np.arange(len(df) * 3).reshape(len(df), 3).astype("i8")

        mi_val = list(product(["bar", "foo"], ["one", "two"])) + [("All", "")]
        mi = MultiIndex.from_tuples(mi_val, names=("A", "B"))
        expected = DataFrame(
            {"dull": [12, 21, 3, 9, 45], "shiny": [33, 0, 36, 51, 120]}, index=mi
        ).rename_axis("C", axis=1)
        expected["All"] = expected["dull"] + expected["shiny"]

        result = df.pivot_table(
            values="D",
            index=["A", "B"],
            columns="C",
            margins=True,
            aggfunc="sum",
            fill_value=0,
        )

        tm.assert_frame_equal(expected, result)

    def test_margins_dtype_len(self, data):
        mi_val = list(product(["bar", "foo"], ["one", "two"])) + [("All", "")]
        mi = MultiIndex.from_tuples(mi_val, names=("A", "B"))
        expected = DataFrame(
            {"dull": [1, 1, 2, 1, 5], "shiny": [2, 0, 2, 2, 6]}, index=mi
        ).rename_axis("C", axis=1)
        expected["All"] = expected["dull"] + expected["shiny"]

        result = data.pivot_table(
            values="D",
            index=["A", "B"],
            columns="C",
            margins=True,
            aggfunc=len,
            fill_value=0,
        )

        tm.assert_frame_equal(expected, result)

    @pytest.mark.parametrize("cols", [(1, 2), ("a", "b"), (1, "b"), ("a", 1)])
    def test_pivot_table_multiindex_only(self, cols):
        # GH 17038
        df2 = DataFrame({cols[0]: [1, 2, 3], cols[1]: [1, 2, 3], "v": [4, 5, 6]})

        result = df2.pivot_table(values="v", columns=cols)
        expected = DataFrame(
            [[4.0, 5.0, 6.0]],
            columns=MultiIndex.from_tuples([(1, 1), (2, 2), (3, 3)], names=cols),
            index=Index(["v"], dtype="str" if cols == ("a", "b") else "object"),
        )

        tm.assert_frame_equal(result, expected)

    def test_pivot_table_retains_tz(self):
        dti = date_range("2016-01-01", periods=3, tz="Europe/Amsterdam")
        df = DataFrame(
            {
                "A": np.random.default_rng(2).standard_normal(3),
                "B": np.random.default_rng(2).standard_normal(3),
                "C": dti,
            }
        )
        result = df.pivot_table(index=["B", "C"], dropna=False)

        # check tz retention
        assert result.index.levels[1].equals(dti)

    def test_pivot_integer_columns(self):
        # caused by upstream bug in unstack

        d = date.min
        data = list(
            product(
                ["foo", "bar"],
                ["A", "B", "C"],
                ["x1", "x2"],
                [d + timedelta(i) for i in range(20)],
                [1.0],
            )
        )
        df = DataFrame(data)
        table = df.pivot_table(values=4, index=[0, 1, 3], columns=[2])

        df2 = df.rename(columns=str)
        table2 = df2.pivot_table(values="4", index=["0", "1", "3"], columns=["2"])

        tm.assert_frame_equal(table, table2, check_names=False)

    def test_pivot_no_level_overlap(self):
        # GH #1181

        data = DataFrame(
            {
                "a": ["a", "a", "a", "a", "b", "b", "b", "b"] * 2,
                "b": [0, 0, 0, 0, 1, 1, 1, 1] * 2,
                "c": (["foo"] * 4 + ["bar"] * 4) * 2,
                "value": np.random.default_rng(2).standard_normal(16),
            }
        )

        table = data.pivot_table("value", index="a", columns=["b", "c"])

        grouped = data.groupby(["a", "b", "c"])["value"].mean()
        expected = grouped.unstack("b").unstack("c").dropna(axis=1, how="all")
        tm.assert_frame_equal(table, expected)

    def test_pivot_columns_lexsorted(self):
        n = 10000

        dtype = np.dtype(
            [
                ("Index", object),
                ("Symbol", object),
                ("Year", int),
                ("Month", int),
                ("Day", int),
                ("Quantity", int),
                ("Price", float),
            ]
        )

        products = np.array(
            [
                ("SP500", "ADBE"),
                ("SP500", "NVDA"),
                ("SP500", "ORCL"),
                ("NDQ100", "AAPL"),
                ("NDQ100", "MSFT"),
                ("NDQ100", "GOOG"),
                ("FTSE", "DGE.L"),
                ("FTSE", "TSCO.L"),
                ("FTSE", "GSK.L"),
            ],
            dtype=[("Index", object), ("Symbol", object)],
        )
        items = np.empty(n, dtype=dtype)
        iproduct = np.random.default_rng(2).integers(0, len(products), n)
        items["Index"] = products["Index"][iproduct]
        items["Symbol"] = products["Symbol"][iproduct]
        dr = date_range(date(2000, 1, 1), date(2010, 12, 31))
        dates = dr[np.random.default_rng(2).integers(0, len(dr), n)]
        items["Year"] = dates.year
        items["Month"] = dates.month
        items["Day"] = dates.day
        items["Price"] = np.random.default_rng(2).lognormal(4.0, 2.0, n)

        df = DataFrame(items)

        pivoted = df.pivot_table(
            "Price",
            index=["Month", "Day"],
            columns=["Index", "Symbol", "Year"],
            aggfunc="mean",
        )

        assert pivoted.columns.is_monotonic_increasing

    def test_pivot_complex_aggfunc(self, data):
        f = {"D": ["std"], "E": ["sum"]}
        expected = data.groupby(["A", "B"]).agg(f).unstack("B")
        result = data.pivot_table(index="A", columns="B", aggfunc=f)

        tm.assert_frame_equal(result, expected)

    def test_margins_no_values_no_cols(self, data):
        # Regression test on pivot table: no values or cols passed.
        result = data[["A", "B"]].pivot_table(
            index=["A", "B"], aggfunc=len, margins=True
        )
        result_list = result.tolist()
        assert sum(result_list[:-1]) == result_list[-1]

    def test_margins_no_values_two_rows(self, data):
        # Regression test on pivot table: no values passed but rows are a
        # multi-index
        result = data[["A", "B", "C"]].pivot_table(
            index=["A", "B"], columns="C", aggfunc=len, margins=True
        )
        assert result.All.tolist() == [3.0, 1.0, 4.0, 3.0, 11.0]

    def test_margins_no_values_one_row_one_col(self, data):
        # Regression test on pivot table: no values passed but row and col
        # defined
        result = data[["A", "B"]].pivot_table(
            index="A", columns="B", aggfunc=len, margins=True
        )
        assert result.All.tolist() == [4.0, 7.0, 11.0]

    def test_margins_no_values_two_row_two_cols(self, data):
        # Regression test on pivot table: no values passed but rows and cols
        # are multi-indexed
        data["D"] = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]
        result = data[["A", "B", "C", "D"]].pivot_table(
            index=["A", "B"], columns=["C", "D"], aggfunc=len, margins=True
        )
        assert result.All.tolist() == [3.0, 1.0, 4.0, 3.0, 11.0]

    @pytest.mark.parametrize("margin_name", ["foo", "one", 666, None, ["a", "b"]])
    def test_pivot_table_with_margins_set_margin_name(self, margin_name, data):
        # see gh-3335
        msg = (
            f'Conflicting name "{margin_name}" in margins|'
            "margins_name argument must be a string"
        )
        with pytest.raises(ValueError, match=msg):
            # multi-index index
            pivot_table(
                data,
                values="D",
                index=["A", "B"],
                columns=["C"],
                margins=True,
                margins_name=margin_name,
            )
        with pytest.raises(ValueError, match=msg):
            # multi-index column
            pivot_table(
                data,
                values="D",
                index=["C"],
                columns=["A", "B"],
                margins=True,
                margins_name=margin_name,
            )
        with pytest.raises(ValueError, match=msg):
            # non-multi-index index/column
            pivot_table(
                data,
                values="D",
                index=["A"],
                columns=["B"],
                margins=True,
                margins_name=margin_name,
            )

    def test_pivot_timegrouper(self, using_array_manager):
        df = DataFrame(
            {
                "Branch": "A A A A A A A B".split(),
                "Buyer": "Carl Mark Carl Carl Joe Joe Joe Carl".split(),
                "Quantity": [1, 3, 5, 1, 8, 1, 9, 3],
                "Date": [
                    datetime(2013, 1, 1),
                    datetime(2013, 1, 1),
                    datetime(2013, 10, 1),
                    datetime(2013, 10, 2),
                    datetime(2013, 10, 1),
                    datetime(2013, 10, 2),
                    datetime(2013, 12, 2),
                    datetime(2013, 12, 2),
                ],
            }
        ).set_index("Date")

        expected = DataFrame(
            np.array([10, 18, 3], dtype="int64").reshape(1, 3),
            index=pd.DatetimeIndex([datetime(2013, 12, 31)], freq="YE"),
            columns="Carl Joe Mark".split(),
        )
        expected.index.name = "Date"
        expected.columns.name = "Buyer"

        result = pivot_table(
            df,
            index=Grouper(freq="YE"),
            columns="Buyer",
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index="Buyer",
            columns=Grouper(freq="YE"),
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected.T)

        expected = DataFrame(
            np.array([1, np.nan, 3, 9, 18, np.nan]).reshape(2, 3),
            index=pd.DatetimeIndex(
                [datetime(2013, 1, 1), datetime(2013, 7, 1)], freq="6MS"
            ),
            columns="Carl Joe Mark".split(),
        )
        expected.index.name = "Date"
        expected.columns.name = "Buyer"
        if using_array_manager:
            # INFO(ArrayManager) column without NaNs can preserve int dtype
            expected["Carl"] = expected["Carl"].astype("int64")

        result = pivot_table(
            df,
            index=Grouper(freq="6MS"),
            columns="Buyer",
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index="Buyer",
            columns=Grouper(freq="6MS"),
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected.T)

        # passing the name
        df = df.reset_index()
        result = pivot_table(
            df,
            index=Grouper(freq="6MS", key="Date"),
            columns="Buyer",
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index="Buyer",
            columns=Grouper(freq="6MS", key="Date"),
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected.T)

        msg = "'The grouper name foo is not found'"
        with pytest.raises(KeyError, match=msg):
            pivot_table(
                df,
                index=Grouper(freq="6MS", key="foo"),
                columns="Buyer",
                values="Quantity",
                aggfunc="sum",
            )
        with pytest.raises(KeyError, match=msg):
            pivot_table(
                df,
                index="Buyer",
                columns=Grouper(freq="6MS", key="foo"),
                values="Quantity",
                aggfunc="sum",
            )

        # passing the level
        df = df.set_index("Date")
        result = pivot_table(
            df,
            index=Grouper(freq="6MS", level="Date"),
            columns="Buyer",
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index="Buyer",
            columns=Grouper(freq="6MS", level="Date"),
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected.T)

        msg = "The level foo is not valid"
        with pytest.raises(ValueError, match=msg):
            pivot_table(
                df,
                index=Grouper(freq="6MS", level="foo"),
                columns="Buyer",
                values="Quantity",
                aggfunc="sum",
            )
        with pytest.raises(ValueError, match=msg):
            pivot_table(
                df,
                index="Buyer",
                columns=Grouper(freq="6MS", level="foo"),
                values="Quantity",
                aggfunc="sum",
            )

    def test_pivot_timegrouper_double(self):
        # double grouper
        df = DataFrame(
            {
                "Branch": "A A A A A A A B".split(),
                "Buyer": "Carl Mark Carl Carl Joe Joe Joe Carl".split(),
                "Quantity": [1, 3, 5, 1, 8, 1, 9, 3],
                "Date": [
                    datetime(2013, 11, 1, 13, 0),
                    datetime(2013, 9, 1, 13, 5),
                    datetime(2013, 10, 1, 20, 0),
                    datetime(2013, 10, 2, 10, 0),
                    datetime(2013, 11, 1, 20, 0),
                    datetime(2013, 10, 2, 10, 0),
                    datetime(2013, 10, 2, 12, 0),
                    datetime(2013, 12, 5, 14, 0),
                ],
                "PayDay": [
                    datetime(2013, 10, 4, 0, 0),
                    datetime(2013, 10, 15, 13, 5),
                    datetime(2013, 9, 5, 20, 0),
                    datetime(2013, 11, 2, 10, 0),
                    datetime(2013, 10, 7, 20, 0),
                    datetime(2013, 9, 5, 10, 0),
                    datetime(2013, 12, 30, 12, 0),
                    datetime(2013, 11, 20, 14, 0),
                ],
            }
        )

        result = pivot_table(
            df,
            index=Grouper(freq="ME", key="Date"),
            columns=Grouper(freq="ME", key="PayDay"),
            values="Quantity",
            aggfunc="sum",
        )
        expected = DataFrame(
            np.array(
                [
                    np.nan,
                    3,
                    np.nan,
                    np.nan,
                    6,
                    np.nan,
                    1,
                    9,
                    np.nan,
                    9,
                    np.nan,
                    np.nan,
                    np.nan,
                    np.nan,
                    3,
                    np.nan,
                ]
            ).reshape(4, 4),
            index=pd.DatetimeIndex(
                [
                    datetime(2013, 9, 30),
                    datetime(2013, 10, 31),
                    datetime(2013, 11, 30),
                    datetime(2013, 12, 31),
                ],
                freq="ME",
            ),
            columns=pd.DatetimeIndex(
                [
                    datetime(2013, 9, 30),
                    datetime(2013, 10, 31),
                    datetime(2013, 11, 30),
                    datetime(2013, 12, 31),
                ],
                freq="ME",
            ),
        )
        expected.index.name = "Date"
        expected.columns.name = "PayDay"

        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index=Grouper(freq="ME", key="PayDay"),
            columns=Grouper(freq="ME", key="Date"),
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected.T)

        tuples = [
            (datetime(2013, 9, 30), datetime(2013, 10, 31)),
            (datetime(2013, 10, 31), datetime(2013, 9, 30)),
            (datetime(2013, 10, 31), datetime(2013, 11, 30)),
            (datetime(2013, 10, 31), datetime(2013, 12, 31)),
            (datetime(2013, 11, 30), datetime(2013, 10, 31)),
            (datetime(2013, 12, 31), datetime(2013, 11, 30)),
        ]
        idx = MultiIndex.from_tuples(tuples, names=["Date", "PayDay"])
        expected = DataFrame(
            np.array(
                [3, np.nan, 6, np.nan, 1, np.nan, 9, np.nan, 9, np.nan, np.nan, 3]
            ).reshape(6, 2),
            index=idx,
            columns=["A", "B"],
        )
        expected.columns.name = "Branch"

        result = pivot_table(
            df,
            index=[Grouper(freq="ME", key="Date"), Grouper(freq="ME", key="PayDay")],
            columns=["Branch"],
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index=["Branch"],
            columns=[Grouper(freq="ME", key="Date"), Grouper(freq="ME", key="PayDay")],
            values="Quantity",
            aggfunc="sum",
        )
        tm.assert_frame_equal(result, expected.T)

    def test_pivot_datetime_tz(self):
        dates1 = pd.DatetimeIndex(
            [
                "2011-07-19 07:00:00",
                "2011-07-19 08:00:00",
                "2011-07-19 09:00:00",
                "2011-07-19 07:00:00",
                "2011-07-19 08:00:00",
                "2011-07-19 09:00:00",
            ],
            dtype="M8[ns, US/Pacific]",
            name="dt1",
        )
        dates2 = pd.DatetimeIndex(
            [
                "2013-01-01 15:00:00",
                "2013-01-01 15:00:00",
                "2013-01-01 15:00:00",
                "2013-02-01 15:00:00",
                "2013-02-01 15:00:00",
                "2013-02-01 15:00:00",
            ],
            dtype="M8[ns, Asia/Tokyo]",
        )
        df = DataFrame(
            {
                "label": ["a", "a", "a", "b", "b", "b"],
                "dt1": dates1,
                "dt2": dates2,
                "value1": np.arange(6, dtype="int64"),
                "value2": [1, 2] * 3,
            }
        )

        exp_idx = dates1[:3]
        exp_col1 = Index(["value1", "value1"])
        exp_col2 = Index(["a", "b"], name="label")
        exp_col = MultiIndex.from_arrays([exp_col1, exp_col2])
        expected = DataFrame(
            [[0.0, 3.0], [1.0, 4.0], [2.0, 5.0]], index=exp_idx, columns=exp_col
        )
        result = pivot_table(df, index=["dt1"], columns=["label"], values=["value1"])
        tm.assert_frame_equal(result, expected)

        exp_col1 = Index(["sum", "sum", "sum", "sum", "mean", "mean", "mean", "mean"])
        exp_col2 = Index(["value1", "value1", "value2", "value2"] * 2)
        exp_col3 = pd.DatetimeIndex(
            ["2013-01-01 15:00:00", "2013-02-01 15:00:00"] * 4,
            dtype="M8[ns, Asia/Tokyo]",
            name="dt2",
        )
        exp_col = MultiIndex.from_arrays([exp_col1, exp_col2, exp_col3])
        expected1 = DataFrame(
            np.array(
                [
                    [
                        0,
                        3,
                        1,
                        2,
                    ],
                    [1, 4, 2, 1],
                    [2, 5, 1, 2],
                ],
                dtype="int64",
            ),
            index=exp_idx,
            columns=exp_col[:4],
        )
        expected2 = DataFrame(
            np.array(
                [
                    [0.0, 3.0, 1.0, 2.0],
                    [1.0, 4.0, 2.0, 1.0],
                    [2.0, 5.0, 1.0, 2.0],
                ],
            ),
            index=exp_idx,
            columns=exp_col[4:],
        )
        expected = concat([expected1, expected2], axis=1)

        result = pivot_table(
            df,
            index=["dt1"],
            columns=["dt2"],
            values=["value1", "value2"],
            aggfunc=["sum", "mean"],
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_dtaccessor(self):
        # GH 8103
        dates1 = pd.DatetimeIndex(
            [
                "2011-07-19 07:00:00",
                "2011-07-19 08:00:00",
                "2011-07-19 09:00:00",
                "2011-07-19 07:00:00",
                "2011-07-19 08:00:00",
                "2011-07-19 09:00:00",
            ]
        )
        dates2 = pd.DatetimeIndex(
            [
                "2013-01-01 15:00:00",
                "2013-01-01 15:00:00",
                "2013-01-01 15:00:00",
                "2013-02-01 15:00:00",
                "2013-02-01 15:00:00",
                "2013-02-01 15:00:00",
            ]
        )
        df = DataFrame(
            {
                "label": ["a", "a", "a", "b", "b", "b"],
                "dt1": dates1,
                "dt2": dates2,
                "value1": np.arange(6, dtype="int64"),
                "value2": [1, 2] * 3,
            }
        )

        result = pivot_table(
            df, index="label", columns=df["dt1"].dt.hour, values="value1"
        )

        exp_idx = Index(["a", "b"], name="label")
        expected = DataFrame(
            {7: [0.0, 3.0], 8: [1.0, 4.0], 9: [2.0, 5.0]},
            index=exp_idx,
            columns=Index([7, 8, 9], dtype=np.int32, name="dt1"),
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df, index=df["dt2"].dt.month, columns=df["dt1"].dt.hour, values="value1"
        )

        expected = DataFrame(
            {7: [0.0, 3.0], 8: [1.0, 4.0], 9: [2.0, 5.0]},
            index=Index([1, 2], dtype=np.int32, name="dt2"),
            columns=Index([7, 8, 9], dtype=np.int32, name="dt1"),
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index=df["dt2"].dt.year.values,
            columns=[df["dt1"].dt.hour, df["dt2"].dt.month],
            values="value1",
        )

        exp_col = MultiIndex.from_arrays(
            [
                np.array([7, 7, 8, 8, 9, 9], dtype=np.int32),
                np.array([1, 2] * 3, dtype=np.int32),
            ],
            names=["dt1", "dt2"],
        )
        expected = DataFrame(
            np.array([[0.0, 3.0, 1.0, 4.0, 2.0, 5.0]]),
            index=Index([2013], dtype=np.int32),
            columns=exp_col,
        )
        tm.assert_frame_equal(result, expected)

        result = pivot_table(
            df,
            index=np.array(["X", "X", "X", "X", "Y", "Y"]),
            columns=[df["dt1"].dt.hour, df["dt2"].dt.month],
            values="value1",
        )
        expected = DataFrame(
            np.array(
                [[0, 3, 1, np.nan, 2, np.nan], [np.nan, np.nan, np.nan, 4, np.nan, 5]]
            ),
            index=["X", "Y"],
            columns=exp_col,
        )
        tm.assert_frame_equal(result, expected)

    def test_daily(self):
        rng = date_range("1/1/2000", "12/31/2004", freq="D")
        ts = Series(np.arange(len(rng)), index=rng)

        result = pivot_table(
            DataFrame(ts), index=ts.index.year, columns=ts.index.dayofyear
        )
        result.columns = result.columns.droplevel(0)

        doy = np.asarray(ts.index.dayofyear)

        expected = {}
        for y in ts.index.year.unique().values:
            mask = ts.index.year == y
            expected[y] = Series(ts.values[mask], index=doy[mask])
        expected = DataFrame(expected, dtype=float).T
        tm.assert_frame_equal(result, expected)

    def test_monthly(self):
        rng = date_range("1/1/2000", "12/31/2004", freq="ME")
        ts = Series(np.arange(len(rng)), index=rng)

        result = pivot_table(DataFrame(ts), index=ts.index.year, columns=ts.index.month)
        result.columns = result.columns.droplevel(0)

        month = np.asarray(ts.index.month)
        expected = {}
        for y in ts.index.year.unique().values:
            mask = ts.index.year == y
            expected[y] = Series(ts.values[mask], index=month[mask])
        expected = DataFrame(expected, dtype=float).T
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_with_iterator_values(self, data):
        # GH 12017
        aggs = {"D": "sum", "E": "mean"}

        pivot_values_list = pivot_table(
            data, index=["A"], values=list(aggs.keys()), aggfunc=aggs
        )

        pivot_values_keys = pivot_table(
            data, index=["A"], values=aggs.keys(), aggfunc=aggs
        )
        tm.assert_frame_equal(pivot_values_keys, pivot_values_list)

        agg_values_gen = (value for value in aggs)
        pivot_values_gen = pivot_table(
            data, index=["A"], values=agg_values_gen, aggfunc=aggs
        )
        tm.assert_frame_equal(pivot_values_gen, pivot_values_list)

    def test_pivot_table_margins_name_with_aggfunc_list(self):
        # GH 13354
        margins_name = "Weekly"
        costs = DataFrame(
            {
                "item": ["bacon", "cheese", "bacon", "cheese"],
                "cost": [2.5, 4.5, 3.2, 3.3],
                "day": ["ME", "ME", "T", "T"],
            }
        )
        table = costs.pivot_table(
            index="item",
            columns="day",
            margins=True,
            margins_name=margins_name,
            aggfunc=["mean", "max"],
        )
        ix = Index(["bacon", "cheese", margins_name], name="item")
        tups = [
            ("mean", "cost", "ME"),
            ("mean", "cost", "T"),
            ("mean", "cost", margins_name),
            ("max", "cost", "ME"),
            ("max", "cost", "T"),
            ("max", "cost", margins_name),
        ]
        cols = MultiIndex.from_tuples(tups, names=[None, None, "day"])
        expected = DataFrame(table.values, index=ix, columns=cols)
        tm.assert_frame_equal(table, expected)

    def test_categorical_margins(self, observed):
        # GH 10989
        df = DataFrame(
            {"x": np.arange(8), "y": np.arange(8) // 4, "z": np.arange(8) % 2}
        )

        expected = DataFrame([[1.0, 2.0, 1.5], [5, 6, 5.5], [3, 4, 3.5]])
        expected.index = Index([0, 1, "All"], name="y")
        expected.columns = Index([0, 1, "All"], name="z")

        table = df.pivot_table("x", "y", "z", dropna=observed, margins=True)
        tm.assert_frame_equal(table, expected)

    def test_categorical_margins_category(self, observed):
        df = DataFrame(
            {"x": np.arange(8), "y": np.arange(8) // 4, "z": np.arange(8) % 2}
        )

        expected = DataFrame([[1.0, 2.0, 1.5], [5, 6, 5.5], [3, 4, 3.5]])
        expected.index = Index([0, 1, "All"], name="y")
        expected.columns = Index([0, 1, "All"], name="z")

        df.y = df.y.astype("category")
        df.z = df.z.astype("category")
        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            table = df.pivot_table("x", "y", "z", dropna=observed, margins=True)
        tm.assert_frame_equal(table, expected)

    def test_margins_casted_to_float(self):
        # GH 24893
        df = DataFrame(
            {
                "A": [2, 4, 6, 8],
                "B": [1, 4, 5, 8],
                "C": [1, 3, 4, 6],
                "D": ["X", "X", "Y", "Y"],
            }
        )

        result = pivot_table(df, index="D", margins=True)
        expected = DataFrame(
            {"A": [3.0, 7.0, 5], "B": [2.5, 6.5, 4.5], "C": [2.0, 5.0, 3.5]},
            index=Index(["X", "Y", "All"], name="D"),
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_with_categorical(self, observed, ordered):
        # gh-21370
        idx = [np.nan, "low", "high", "low", np.nan]
        col = [np.nan, "A", "B", np.nan, "A"]
        df = DataFrame(
            {
                "In": Categorical(idx, categories=["low", "high"], ordered=ordered),
                "Col": Categorical(col, categories=["A", "B"], ordered=ordered),
                "Val": range(1, 6),
            }
        )
        # case with index/columns/value
        result = df.pivot_table(
            index="In", columns="Col", values="Val", observed=observed
        )

        expected_cols = pd.CategoricalIndex(["A", "B"], ordered=ordered, name="Col")

        expected = DataFrame(data=[[2.0, np.nan], [np.nan, 3.0]], columns=expected_cols)
        expected.index = Index(
            Categorical(["low", "high"], categories=["low", "high"], ordered=ordered),
            name="In",
        )

        tm.assert_frame_equal(result, expected)

        # case with columns/value
        result = df.pivot_table(columns="Col", values="Val", observed=observed)

        expected = DataFrame(
            data=[[3.5, 3.0]], columns=expected_cols, index=Index(["Val"])
        )

        tm.assert_frame_equal(result, expected)

    def test_categorical_aggfunc(self, observed):
        # GH 9534
        df = DataFrame(
            {"C1": ["A", "B", "C", "C"], "C2": ["a", "a", "b", "b"], "V": [1, 2, 3, 4]}
        )
        df["C1"] = df["C1"].astype("category")
        msg = "The default value of observed=False is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.pivot_table(
                "V", index="C1", columns="C2", dropna=observed, aggfunc="count"
            )

        expected_index = pd.CategoricalIndex(
            ["A", "B", "C"], categories=["A", "B", "C"], ordered=False, name="C1"
        )
        expected_columns = Index(["a", "b"], name="C2")
        expected_data = np.array([[1, 0], [1, 0], [0, 2]], dtype=np.int64)
        expected = DataFrame(
            expected_data, index=expected_index, columns=expected_columns
        )
        tm.assert_frame_equal(result, expected)

    def test_categorical_pivot_index_ordering(self, observed):
        # GH 8731
        df = DataFrame(
            {
                "Sales": [100, 120, 220],
                "Month": ["January", "January", "January"],
                "Year": [2013, 2014, 2013],
            }
        )
        months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        df["Month"] = df["Month"].astype("category").cat.set_categories(months)
        result = df.pivot_table(
            values="Sales",
            index="Month",
            columns="Year",
            observed=observed,
            aggfunc="sum",
        )
        expected_columns = Index([2013, 2014], name="Year", dtype="int64")
        expected_index = pd.CategoricalIndex(
            months, categories=months, ordered=False, name="Month"
        )
        expected_data = [[320, 120]] + [[0, 0]] * 11
        expected = DataFrame(
            expected_data, index=expected_index, columns=expected_columns
        )
        if observed:
            expected = expected.loc[["January"]]

        tm.assert_frame_equal(result, expected)

    def test_pivot_table_not_series(self):
        # GH 4386
        # pivot_table always returns a DataFrame
        # when values is not list like and columns is None
        # and aggfunc is not instance of list
        df = DataFrame({"col1": [3, 4, 5], "col2": ["C", "D", "E"], "col3": [1, 3, 9]})

        result = df.pivot_table("col1", index=["col3", "col2"], aggfunc="sum")
        m = MultiIndex.from_arrays([[1, 3, 9], ["C", "D", "E"]], names=["col3", "col2"])
        expected = DataFrame([3, 4, 5], index=m, columns=["col1"])

        tm.assert_frame_equal(result, expected)

        result = df.pivot_table("col1", index="col3", columns="col2", aggfunc="sum")
        expected = DataFrame(
            [[3, np.nan, np.nan], [np.nan, 4, np.nan], [np.nan, np.nan, 5]],
            index=Index([1, 3, 9], name="col3"),
            columns=Index(["C", "D", "E"], name="col2"),
        )

        tm.assert_frame_equal(result, expected)

        result = df.pivot_table("col1", index="col3", aggfunc=["sum"])
        m = MultiIndex.from_arrays([["sum"], ["col1"]])
        expected = DataFrame([3, 4, 5], index=Index([1, 3, 9], name="col3"), columns=m)

        tm.assert_frame_equal(result, expected)

    def test_pivot_margins_name_unicode(self):
        # issue #13292
        greek = "\u0394\u03bf\u03ba\u03b9\u03bc\u03ae"
        frame = DataFrame({"foo": [1, 2, 3]}, columns=Index(["foo"], dtype=object))
        table = pivot_table(
            frame, index=["foo"], aggfunc=len, margins=True, margins_name=greek
        )
        index = Index([1, 2, 3, greek], dtype="object", name="foo")
        expected = DataFrame(index=index, columns=[])
        tm.assert_frame_equal(table, expected)

    def test_pivot_string_as_func(self):
        # GH #18713
        # for correctness purposes
        data = DataFrame(
            {
                "A": [
                    "foo",
                    "foo",
                    "foo",
                    "foo",
                    "bar",
                    "bar",
                    "bar",
                    "bar",
                    "foo",
                    "foo",
                    "foo",
                ],
                "B": [
                    "one",
                    "one",
                    "one",
                    "two",
                    "one",
                    "one",
                    "one",
                    "two",
                    "two",
                    "two",
                    "one",
                ],
                "C": range(11),
            }
        )

        result = pivot_table(data, index="A", columns="B", aggfunc="sum")
        mi = MultiIndex(
            levels=[["C"], ["one", "two"]], codes=[[0, 0], [0, 1]], names=[None, "B"]
        )
        expected = DataFrame(
            {("C", "one"): {"bar": 15, "foo": 13}, ("C", "two"): {"bar": 7, "foo": 20}},
            columns=mi,
        ).rename_axis("A")
        tm.assert_frame_equal(result, expected)

        result = pivot_table(data, index="A", columns="B", aggfunc=["sum", "mean"])
        mi = MultiIndex(
            levels=[["sum", "mean"], ["C"], ["one", "two"]],
            codes=[[0, 0, 1, 1], [0, 0, 0, 0], [0, 1, 0, 1]],
            names=[None, None, "B"],
        )
        expected = DataFrame(
            {
                ("mean", "C", "one"): {"bar": 5.0, "foo": 3.25},
                ("mean", "C", "two"): {"bar": 7.0, "foo": 6.666666666666667},
                ("sum", "C", "one"): {"bar": 15, "foo": 13},
                ("sum", "C", "two"): {"bar": 7, "foo": 20},
            },
            columns=mi,
        ).rename_axis("A")
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "f, f_numpy",
        [
            ("sum", np.sum),
            ("mean", np.mean),
            ("std", np.std),
            (["sum", "mean"], [np.sum, np.mean]),
            (["sum", "std"], [np.sum, np.std]),
            (["std", "mean"], [np.std, np.mean]),
        ],
    )
    def test_pivot_string_func_vs_func(self, f, f_numpy, data):
        # GH #18713
        # for consistency purposes
        data = data.drop(columns="C")
        result = pivot_table(data, index="A", columns="B", aggfunc=f)
        ops = "|".join(f) if isinstance(f, list) else f
        msg = f"using DataFrameGroupBy.[{ops}]"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            expected = pivot_table(data, index="A", columns="B", aggfunc=f_numpy)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.slow
    def test_pivot_number_of_levels_larger_than_int32(self, monkeypatch):
        # GH 20601
        # GH 26314: Change ValueError to PerformanceWarning
        class MockUnstacker(reshape_lib._Unstacker):
            def __init__(self, *args, **kwargs) -> None:
                # __init__ will raise the warning
                super().__init__(*args, **kwargs)
                raise Exception("Don't compute final result.")

        with monkeypatch.context() as m:
            m.setattr(reshape_lib, "_Unstacker", MockUnstacker)
            df = DataFrame(
                {"ind1": np.arange(2**16), "ind2": np.arange(2**16), "count": 0}
            )

            msg = "The following operation may generate"
            with tm.assert_produces_warning(PerformanceWarning, match=msg):
                with pytest.raises(Exception, match="Don't compute final result."):
                    df.pivot_table(
                        index="ind1", columns="ind2", values="count", aggfunc="count"
                    )

    def test_pivot_table_aggfunc_dropna(self, dropna):
        # GH 22159
        df = DataFrame(
            {
                "fruit": ["apple", "peach", "apple"],
                "size": [1, 1, 2],
                "taste": [7, 6, 6],
            }
        )

        def ret_one(x):
            return 1

        def ret_sum(x):
            return sum(x)

        def ret_none(x):
            return np.nan

        result = pivot_table(
            df, columns="fruit", aggfunc=[ret_sum, ret_none, ret_one], dropna=dropna
        )

        data = [[3, 1, np.nan, np.nan, 1, 1], [13, 6, np.nan, np.nan, 1, 1]]
        col = MultiIndex.from_product(
            [["ret_sum", "ret_none", "ret_one"], ["apple", "peach"]],
            names=[None, "fruit"],
        )
        expected = DataFrame(data, index=["size", "taste"], columns=col)

        if dropna:
            expected = expected.dropna(axis="columns")

        tm.assert_frame_equal(result, expected)

    def test_pivot_table_aggfunc_scalar_dropna(self, dropna):
        # GH 22159
        df = DataFrame(
            {"A": ["one", "two", "one"], "x": [3, np.nan, 2], "y": [1, np.nan, np.nan]}
        )

        result = pivot_table(df, columns="A", aggfunc="mean", dropna=dropna)

        data = [[2.5, np.nan], [1, np.nan]]
        col = Index(["one", "two"], name="A")
        expected = DataFrame(data, index=["x", "y"], columns=col)

        if dropna:
            expected = expected.dropna(axis="columns")

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("margins", [True, False])
    def test_pivot_table_empty_aggfunc(self, margins):
        # GH 9186 & GH 13483 & GH 49240
        df = DataFrame(
            {
                "A": [2, 2, 3, 3, 2],
                "id": [5, 6, 7, 8, 9],
                "C": ["p", "q", "q", "p", "q"],
                "D": [None, None, None, None, None],
            }
        )
        result = df.pivot_table(
            index="A", columns="D", values="id", aggfunc=np.size, margins=margins
        )
        exp_cols = Index([], name="D")
        expected = DataFrame(index=Index([], dtype="int64", name="A"), columns=exp_cols)
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_no_column_raises(self):
        # GH 10326
        def agg(arr):
            return np.mean(arr)

        df = DataFrame({"X": [0, 0, 1, 1], "Y": [0, 1, 0, 1], "Z": [10, 20, 30, 40]})
        with pytest.raises(KeyError, match="notpresent"):
            df.pivot_table("notpresent", "X", "Y", aggfunc=agg)

    def test_pivot_table_multiindex_columns_doctest_case(self):
        # The relevant characteristic is that the call
        #  to maybe_downcast_to_dtype(agged[v], data[v].dtype) in
        #  __internal_pivot_table has `agged[v]` a DataFrame instead of Series,
        #  In this case this is because agged.columns is a MultiIndex and 'v'
        #  is only indexing on its first level.
        df = DataFrame(
            {
                "A": ["foo", "foo", "foo", "foo", "foo", "bar", "bar", "bar", "bar"],
                "B": ["one", "one", "one", "two", "two", "one", "one", "two", "two"],
                "C": [
                    "small",
                    "large",
                    "large",
                    "small",
                    "small",
                    "large",
                    "small",
                    "small",
                    "large",
                ],
                "D": [1, 2, 2, 3, 3, 4, 5, 6, 7],
                "E": [2, 4, 5, 5, 6, 6, 8, 9, 9],
            }
        )

        table = pivot_table(
            df,
            values=["D", "E"],
            index=["A", "C"],
            aggfunc={"D": "mean", "E": ["min", "max", "mean"]},
        )
        cols = MultiIndex.from_tuples(
            [("D", "mean"), ("E", "max"), ("E", "mean"), ("E", "min")]
        )
        index = MultiIndex.from_tuples(
            [("bar", "large"), ("bar", "small"), ("foo", "large"), ("foo", "small")],
            names=["A", "C"],
        )
        vals = np.array(
            [
                [5.5, 9.0, 7.5, 6.0],
                [5.5, 9.0, 8.5, 8.0],
                [2.0, 5.0, 4.5, 4.0],
                [2.33333333, 6.0, 4.33333333, 2.0],
            ]
        )
        expected = DataFrame(vals, columns=cols, index=index)
        expected[("E", "min")] = expected[("E", "min")].astype(np.int64)
        expected[("E", "max")] = expected[("E", "max")].astype(np.int64)
        tm.assert_frame_equal(table, expected)

    def test_pivot_table_sort_false(self):
        # GH#39143
        df = DataFrame(
            {
                "a": ["d1", "d4", "d3"],
                "col": ["a", "b", "c"],
                "num": [23, 21, 34],
                "year": ["2018", "2018", "2019"],
            }
        )
        result = df.pivot_table(
            index=["a", "col"], columns="year", values="num", aggfunc="sum", sort=False
        )
        expected = DataFrame(
            [[23, np.nan], [21, np.nan], [np.nan, 34]],
            columns=Index(["2018", "2019"], name="year"),
            index=MultiIndex.from_arrays(
                [["d1", "d4", "d3"], ["a", "b", "c"]], names=["a", "col"]
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_nullable_margins(self):
        # GH#48681
        df = DataFrame(
            {"a": "A", "b": [1, 2], "sales": Series([10, 11], dtype="Int64")}
        )

        result = df.pivot_table(index="b", columns="a", margins=True, aggfunc="sum")
        expected = DataFrame(
            [[10, 10], [11, 11], [21, 21]],
            index=Index([1, 2, "All"], name="b"),
            columns=MultiIndex.from_tuples(
                [("sales", "A"), ("sales", "All")], names=[None, "a"]
            ),
            dtype="Int64",
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_sort_false_with_multiple_values(self):
        df = DataFrame(
            {
                "firstname": ["John", "Michael"],
                "lastname": ["Foo", "Bar"],
                "height": [173, 182],
                "age": [47, 33],
            }
        )
        result = df.pivot_table(
            index=["lastname", "firstname"], values=["height", "age"], sort=False
        )
        expected = DataFrame(
            [[173.0, 47.0], [182.0, 33.0]],
            columns=["height", "age"],
            index=MultiIndex.from_tuples(
                [("Foo", "John"), ("Bar", "Michael")],
                names=["lastname", "firstname"],
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_with_margins_and_numeric_columns(self):
        # GH 26568
        df = DataFrame([["a", "x", 1], ["a", "y", 2], ["b", "y", 3], ["b", "z", 4]])
        df.columns = [10, 20, 30]

        result = df.pivot_table(
            index=10, columns=20, values=30, aggfunc="sum", fill_value=0, margins=True
        )

        expected = DataFrame([[1, 2, 0, 3], [0, 3, 4, 7], [1, 5, 4, 10]])
        expected.columns = ["x", "y", "z", "All"]
        expected.index = ["a", "b", "All"]
        expected.columns.name = 20
        expected.index.name = 10

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dropna", [True, False])
    def test_pivot_ea_dtype_dropna(self, dropna):
        # GH#47477
        df = DataFrame({"x": "a", "y": "b", "age": Series([20, 40], dtype="Int64")})
        result = df.pivot_table(
            index="x", columns="y", values="age", aggfunc="mean", dropna=dropna
        )
        expected = DataFrame(
            [[30]],
            index=Index(["a"], name="x"),
            columns=Index(["b"], name="y"),
            dtype="Float64",
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_datetime_warning(self):
        # GH#48683
        df = DataFrame(
            {
                "a": "A",
                "b": [1, 2],
                "date": pd.Timestamp("2019-12-31"),
                "sales": [10.0, 11],
            }
        )
        with tm.assert_produces_warning(None):
            result = df.pivot_table(
                index=["b", "date"], columns="a", margins=True, aggfunc="sum"
            )
        expected = DataFrame(
            [[10.0, 10.0], [11.0, 11.0], [21.0, 21.0]],
            index=MultiIndex.from_arrays(
                [
                    Index([1, 2, "All"], name="b"),
                    Index(
                        [pd.Timestamp("2019-12-31"), pd.Timestamp("2019-12-31"), ""],
                        dtype=object,
                        name="date",
                    ),
                ]
            ),
            columns=MultiIndex.from_tuples(
                [("sales", "A"), ("sales", "All")], names=[None, "a"]
            ),
        )
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_with_mixed_nested_tuples(self, using_array_manager):
        # GH 50342
        df = DataFrame(
            {
                "A": ["foo", "foo", "foo", "foo", "foo", "bar", "bar", "bar", "bar"],
                "B": ["one", "one", "one", "two", "two", "one", "one", "two", "two"],
                "C": [
                    "small",
                    "large",
                    "large",
                    "small",
                    "small",
                    "large",
                    "small",
                    "small",
                    "large",
                ],
                "D": [1, 2, 2, 3, 3, 4, 5, 6, 7],
                "E": [2, 4, 5, 5, 6, 6, 8, 9, 9],
                ("col5",): [
                    "foo",
                    "foo",
                    "foo",
                    "foo",
                    "foo",
                    "bar",
                    "bar",
                    "bar",
                    "bar",
                ],
                ("col6", 6): [
                    "one",
                    "one",
                    "one",
                    "two",
                    "two",
                    "one",
                    "one",
                    "two",
                    "two",
                ],
                (7, "seven"): [
                    "small",
                    "large",
                    "large",
                    "small",
                    "small",
                    "large",
                    "small",
                    "small",
                    "large",
                ],
            }
        )
        result = pivot_table(
            df, values="D", index=["A", "B"], columns=[(7, "seven")], aggfunc="sum"
        )
        expected = DataFrame(
            [[4.0, 5.0], [7.0, 6.0], [4.0, 1.0], [np.nan, 6.0]],
            columns=Index(["large", "small"], name=(7, "seven")),
            index=MultiIndex.from_arrays(
                [["bar", "bar", "foo", "foo"], ["one", "two"] * 2], names=["A", "B"]
            ),
        )
        if using_array_manager:
            # INFO(ArrayManager) column without NaNs can preserve int dtype
            expected["small"] = expected["small"].astype("int64")
        tm.assert_frame_equal(result, expected)

    def test_pivot_table_aggfunc_nunique_with_different_values(self):
        test = DataFrame(
            {
                "a": range(10),
                "b": range(10),
                "c": range(10),
                "d": range(10),
            }
        )

        columnval = MultiIndex.from_arrays(
            [
                ["nunique" for i in range(10)],
                ["c" for i in range(10)],
                range(10),
            ],
            names=(None, None, "b"),
        )
        nparr = np.full((10, 10), np.nan)
        np.fill_diagonal(nparr, 1.0)

        expected = DataFrame(nparr, index=Index(range(10), name="a"), columns=columnval)
        result = test.pivot_table(
            index=[
                "a",
            ],
            columns=[
                "b",
            ],
            values=[
                "c",
            ],
            aggfunc=["nunique"],
        )

        tm.assert_frame_equal(result, expected)


class TestPivot:
    def test_pivot(self):
        data = {
            "index": ["A", "B", "C", "C", "B", "A"],
            "columns": ["One", "One", "One", "Two", "Two", "Two"],
            "values": [1.0, 2.0, 3.0, 3.0, 2.0, 1.0],
        }

        frame = DataFrame(data)
        pivoted = frame.pivot(index="index", columns="columns", values="values")

        expected = DataFrame(
            {
                "One": {"A": 1.0, "B": 2.0, "C": 3.0},
                "Two": {"A": 1.0, "B": 2.0, "C": 3.0},
            }
        )

        expected.index.name, expected.columns.name = "index", "columns"
        tm.assert_frame_equal(pivoted, expected)

        # name tracking
        assert pivoted.index.name == "index"
        assert pivoted.columns.name == "columns"

        # don't specify values
        pivoted = frame.pivot(index="index", columns="columns")
        assert pivoted.index.name == "index"
        assert pivoted.columns.names == (None, "columns")

    def test_pivot_duplicates(self):
        data = DataFrame(
            {
                "a": ["bar", "bar", "foo", "foo", "foo"],
                "b": ["one", "two", "one", "one", "two"],
                "c": [1.0, 2.0, 3.0, 3.0, 4.0],
            }
        )
        with pytest.raises(ValueError, match="duplicate entries"):
            data.pivot(index="a", columns="b", values="c")

    def test_pivot_empty(self):
        df = DataFrame(columns=["a", "b", "c"])
        result = df.pivot(index="a", columns="b", values="c")
        expected = DataFrame(index=[], columns=[])
        tm.assert_frame_equal(result, expected, check_names=False)

    def test_pivot_integer_bug(self, any_string_dtype):
        df = DataFrame(
            data=[("A", "1", "A1"), ("B", "2", "B2")], dtype=any_string_dtype
        )

        result = df.pivot(index=1, columns=0, values=2)
        expected_columns = Index(["A", "B"], name=0, dtype=any_string_dtype)
        if any_string_dtype == "object":
            expected_columns = expected_columns.astype("str")
        tm.assert_index_equal(result.columns, expected_columns)

    def test_pivot_index_none(self):
        # GH#3962
        data = {
            "index": ["A", "B", "C", "C", "B", "A"],
            "columns": ["One", "One", "One", "Two", "Two", "Two"],
            "values": [1.0, 2.0, 3.0, 3.0, 2.0, 1.0],
        }

        frame = DataFrame(data).set_index("index")
        result = frame.pivot(columns="columns", values="values")
        expected = DataFrame(
            {
                "One": {"A": 1.0, "B": 2.0, "C": 3.0},
                "Two": {"A": 1.0, "B": 2.0, "C": 3.0},
            }
        )

        expected.index.name, expected.columns.name = "index", "columns"
        tm.assert_frame_equal(result, expected)

        # omit values
        result = frame.pivot(columns="columns")

        expected.columns = MultiIndex.from_tuples(
            [("values", "One"), ("values", "Two")], names=[None, "columns"]
        )
        expected.index.name = "index"
        tm.assert_frame_equal(result, expected, check_names=False)
        assert result.index.name == "index"
        assert result.columns.names == (None, "columns")
        expected.columns = expected.columns.droplevel(0)
        result = frame.pivot(columns="columns", values="values")

        expected.columns.name = "columns"
        tm.assert_frame_equal(result, expected)

    def test_pivot_index_list_values_none_immutable_args(self):
        # GH37635
        df = DataFrame(
            {
                "lev1": [1, 1, 1, 2, 2, 2],
                "lev2": [1, 1, 2, 1, 1, 2],
                "lev3": [1, 2, 1, 2, 1, 2],
                "lev4": [1, 2, 3, 4, 5, 6],
                "values": [0, 1, 2, 3, 4, 5],
            }
        )
        index = ["lev1", "lev2"]
        columns = ["lev3"]
        result = df.pivot(index=index, columns=columns)

        expected = DataFrame(
            np.array(
                [
                    [1.0, 2.0, 0.0, 1.0],
                    [3.0, np.nan, 2.0, np.nan],
                    [5.0, 4.0, 4.0, 3.0],
                    [np.nan, 6.0, np.nan, 5.0],
                ]
            ),
            index=MultiIndex.from_arrays(
                [(1, 1, 2, 2), (1, 2, 1, 2)], names=["lev1", "lev2"]
            ),
            columns=MultiIndex.from_arrays(
                [("lev4", "lev4", "values", "values"), (1, 2, 1, 2)],
                names=[None, "lev3"],
            ),
        )

        tm.assert_frame_equal(result, expected)

        assert index == ["lev1", "lev2"]
        assert columns == ["lev3"]

    def test_pivot_columns_not_given(self):
        # GH#48293
        df = DataFrame({"a": [1], "b": 1})
        with pytest.raises(TypeError, match="missing 1 required keyword-only argument"):
            df.pivot()  # pylint: disable=missing-kwoa

    # this still fails because columns=None gets passed down to unstack as level=None
    # while at that point None was converted to NaN
    @pytest.mark.xfail(
        using_string_dtype(), reason="TODO(infer_string) None is cast to NaN"
    )
    def test_pivot_columns_is_none(self):
        # GH#48293
        df = DataFrame({None: [1], "b": 2, "c": 3})
        result = df.pivot(columns=None)
        expected = DataFrame({("b", 1): [2], ("c", 1): 3})
        tm.assert_frame_equal(result, expected)

        result = df.pivot(columns=None, index="b")
        expected = DataFrame({("c", 1): 3}, index=Index([2], name="b"))
        tm.assert_frame_equal(result, expected)

        result = df.pivot(columns=None, index="b", values="c")
        expected = DataFrame({1: 3}, index=Index([2], name="b"))
        tm.assert_frame_equal(result, expected)

    def test_pivot_index_is_none(self, using_infer_string):
        # GH#48293
        df = DataFrame({None: [1], "b": 2, "c": 3})

        result = df.pivot(columns="b", index=None)
        expected = DataFrame({("c", 2): 3}, index=[1])
        expected.columns.names = [None, "b"]
        tm.assert_frame_equal(result, expected)

        result = df.pivot(columns="b", index=None, values="c")
        expected = DataFrame(3, index=[1], columns=Index([2], name="b"))
        if using_infer_string:
            expected.index.name = np.nan
        tm.assert_frame_equal(result, expected)

    def test_pivot_values_is_none(self):
        # GH#48293
        df = DataFrame({None: [1], "b": 2, "c": 3})

        result = df.pivot(columns="b", index="c", values=None)
        expected = DataFrame(
            1, index=Index([3], name="c"), columns=Index([2], name="b")
        )
        tm.assert_frame_equal(result, expected)

        result = df.pivot(columns="b", values=None)
        expected = DataFrame(1, index=[0], columns=Index([2], name="b"))
        tm.assert_frame_equal(result, expected)

    def test_pivot_not_changing_index_name(self):
        # GH#52692
        df = DataFrame({"one": ["a"], "two": 0, "three": 1})
        expected = df.copy(deep=True)
        df.pivot(index="one", columns="two", values="three")
        tm.assert_frame_equal(df, expected)

    def test_pivot_table_empty_dataframe_correct_index(self):
        # GH 21932
        df = DataFrame([], columns=["a", "b", "value"])
        pivot = df.pivot_table(index="a", columns="b", values="value", aggfunc="count")

        expected = Index([], dtype="object", name="b")
        tm.assert_index_equal(pivot.columns, expected)

    def test_pivot_table_handles_explicit_datetime_types(self):
        # GH#43574
        df = DataFrame(
            [
                {"a": "x", "date_str": "2023-01-01", "amount": 1},
                {"a": "y", "date_str": "2023-01-02", "amount": 2},
                {"a": "z", "date_str": "2023-01-03", "amount": 3},
            ]
        )
        df["date"] = pd.to_datetime(df["date_str"])

        with tm.assert_produces_warning(False):
            pivot = df.pivot_table(
                index=["a", "date"], values=["amount"], aggfunc="sum", margins=True
            )

        expected = MultiIndex.from_tuples(
            [
                ("x", datetime.strptime("2023-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")),
                ("y", datetime.strptime("2023-01-02 00:00:00", "%Y-%m-%d %H:%M:%S")),
                ("z", datetime.strptime("2023-01-03 00:00:00", "%Y-%m-%d %H:%M:%S")),
                ("All", ""),
            ],
            names=["a", "date"],
        )
        tm.assert_index_equal(pivot.index, expected)

    def test_pivot_table_with_margins_and_numeric_column_names(self):
        # GH#26568
        df = DataFrame([["a", "x", 1], ["a", "y", 2], ["b", "y", 3], ["b", "z", 4]])

        result = df.pivot_table(
            index=0, columns=1, values=2, aggfunc="sum", fill_value=0, margins=True
        )

        expected = DataFrame(
            [[1, 2, 0, 3], [0, 3, 4, 7], [1, 5, 4, 10]],
            columns=Index(["x", "y", "z", "All"], name=1),
            index=Index(["a", "b", "All"], name=0),
        )
        tm.assert_frame_equal(result, expected)
