""" test label based indexing with loc """
from collections import namedtuple
import contextlib
from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
import re

from dateutil.tz import gettz
import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas._libs import index as libindex
from pandas.compat.numpy import np_version_gt2
from pandas.errors import IndexingError
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    Categorical,
    CategoricalDtype,
    CategoricalIndex,
    DataFrame,
    DatetimeIndex,
    Index,
    IndexSlice,
    MultiIndex,
    Period,
    PeriodIndex,
    Series,
    SparseDtype,
    Timedelta,
    Timestamp,
    date_range,
    timedelta_range,
    to_datetime,
    to_timedelta,
)
import pandas._testing as tm
from pandas.api.types import is_scalar
from pandas.core.indexing import _one_ellipsis_message
from pandas.tests.indexing.common import check_indexing_smoketest_or_raises


@pytest.mark.parametrize(
    "series, new_series, expected_ser",
    [
        [[np.nan, np.nan, "b"], ["a", np.nan, np.nan], [False, True, True]],
        [[np.nan, "b"], ["a", np.nan], [False, True]],
    ],
)
def test_not_change_nan_loc(series, new_series, expected_ser):
    # GH 28403
    df = DataFrame({"A": series})
    df.loc[:, "A"] = new_series
    expected = DataFrame({"A": expected_ser})
    tm.assert_frame_equal(df.isna(), expected)
    tm.assert_frame_equal(df.notna(), ~expected)


class TestLoc:
    def test_none_values_on_string_columns(self, using_infer_string):
        # Issue #32218
        df = DataFrame(["1", "2", None], columns=["a"], dtype=object)
        assert df.loc[2, "a"] is None

        df = DataFrame(["1", "2", None], columns=["a"], dtype="str")
        if using_infer_string:
            assert np.isnan(df.loc[2, "a"])
        else:
            assert df.loc[2, "a"] is None

    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_int(self, kind, request):
        # int label
        obj = request.getfixturevalue(f"{kind}_labels")
        check_indexing_smoketest_or_raises(obj, "loc", 2, fails=KeyError)

    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_label(self, kind, request):
        # label
        obj = request.getfixturevalue(f"{kind}_empty")
        check_indexing_smoketest_or_raises(obj, "loc", "c", fails=KeyError)

    @pytest.mark.parametrize(
        "key, typs, axes",
        [
            ["f", ["ints", "uints", "labels", "mixed", "ts"], None],
            ["f", ["floats"], None],
            [20, ["ints", "uints", "mixed"], None],
            [20, ["labels"], None],
            [20, ["ts"], 0],
            [20, ["floats"], 0],
        ],
    )
    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_label_out_of_range(self, key, typs, axes, kind, request):
        for typ in typs:
            obj = request.getfixturevalue(f"{kind}_{typ}")
            # out of range label
            check_indexing_smoketest_or_raises(
                obj, "loc", key, axes=axes, fails=KeyError
            )

    @pytest.mark.parametrize(
        "key, typs",
        [
            [[0, 1, 2], ["ints", "uints", "floats"]],
            [[1, 3.0, "A"], ["ints", "uints", "floats"]],
        ],
    )
    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_label_list(self, key, typs, kind, request):
        for typ in typs:
            obj = request.getfixturevalue(f"{kind}_{typ}")
            # list of labels
            check_indexing_smoketest_or_raises(obj, "loc", key, fails=KeyError)

    @pytest.mark.parametrize(
        "key, typs, axes",
        [
            [[0, 1, 2], ["empty"], None],
            [[0, 2, 10], ["ints", "uints", "floats"], 0],
            [[3, 6, 7], ["ints", "uints", "floats"], 1],
            # GH 17758 - MultiIndex and missing keys
            [[(1, 3), (1, 4), (2, 5)], ["multi"], 0],
        ],
    )
    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_label_list_with_missing(self, key, typs, axes, kind, request):
        for typ in typs:
            obj = request.getfixturevalue(f"{kind}_{typ}")
            check_indexing_smoketest_or_raises(
                obj, "loc", key, axes=axes, fails=KeyError
            )

    @pytest.mark.parametrize("typs", ["ints", "uints"])
    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_label_list_fails(self, typs, kind, request):
        # fails
        obj = request.getfixturevalue(f"{kind}_{typs}")
        check_indexing_smoketest_or_raises(
            obj, "loc", [20, 30, 40], axes=1, fails=KeyError
        )

    def test_loc_getitem_label_array_like(self):
        # TODO: test something?
        # array like
        pass

    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_bool(self, kind, request):
        obj = request.getfixturevalue(f"{kind}_empty")
        # boolean indexers
        b = [True, False, True, False]

        check_indexing_smoketest_or_raises(obj, "loc", b, fails=IndexError)

    @pytest.mark.parametrize(
        "slc, typs, axes, fails",
        [
            [
                slice(1, 3),
                ["labels", "mixed", "empty", "ts", "floats"],
                None,
                TypeError,
            ],
            [slice("20130102", "20130104"), ["ts"], 1, TypeError],
            [slice(2, 8), ["mixed"], 0, TypeError],
            [slice(2, 8), ["mixed"], 1, KeyError],
            [slice(2, 4, 2), ["mixed"], 0, TypeError],
        ],
    )
    @pytest.mark.parametrize("kind", ["series", "frame"])
    def test_loc_getitem_label_slice(self, slc, typs, axes, fails, kind, request):
        # label slices (with ints)

        # real label slices

        # GH 14316
        for typ in typs:
            obj = request.getfixturevalue(f"{kind}_{typ}")
            check_indexing_smoketest_or_raises(
                obj,
                "loc",
                slc,
                axes=axes,
                fails=fails,
            )

    def test_setitem_from_duplicate_axis(self):
        # GH#34034
        df = DataFrame(
            [[20, "a"], [200, "a"], [200, "a"]],
            columns=["col1", "col2"],
            index=[10, 1, 1],
        )
        df.loc[1, "col1"] = np.arange(2)
        expected = DataFrame(
            [[20, "a"], [0, "a"], [1, "a"]], columns=["col1", "col2"], index=[10, 1, 1]
        )
        tm.assert_frame_equal(df, expected)

    def test_column_types_consistent(self):
        # GH 26779
        df = DataFrame(
            data={
                "channel": [1, 2, 3],
                "A": ["String 1", np.nan, "String 2"],
                "B": [
                    Timestamp("2019-06-11 11:00:00"),
                    pd.NaT,
                    Timestamp("2019-06-11 12:00:00"),
                ],
            }
        )
        df2 = DataFrame(
            data={"A": ["String 3"], "B": [Timestamp("2019-06-11 12:00:00")]}
        )
        # Change Columns A and B to df2.values wherever Column A is NaN
        df.loc[df["A"].isna(), ["A", "B"]] = df2.values
        expected = DataFrame(
            data={
                "channel": [1, 2, 3],
                "A": ["String 1", "String 3", "String 2"],
                "B": [
                    Timestamp("2019-06-11 11:00:00"),
                    Timestamp("2019-06-11 12:00:00"),
                    Timestamp("2019-06-11 12:00:00"),
                ],
            }
        )
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "obj, key, exp",
        [
            (
                DataFrame([[1]], columns=Index([False])),
                IndexSlice[:, False],
                Series([1], name=False),
            ),
            (Series([1], index=Index([False])), False, [1]),
            (DataFrame([[1]], index=Index([False])), False, Series([1], name=False)),
        ],
    )
    def test_loc_getitem_single_boolean_arg(self, obj, key, exp):
        # GH 44322
        res = obj.loc[key]
        if isinstance(exp, (DataFrame, Series)):
            tm.assert_equal(res, exp)
        else:
            assert res == exp


class TestLocBaseIndependent:
    # Tests for loc that do not depend on subclassing Base
    def test_loc_npstr(self):
        # GH#45580
        df = DataFrame(index=date_range("2021", "2022"))
        result = df.loc[np.array(["2021/6/1"])[0] :]
        expected = df.iloc[151:]
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "msg, key",
        [
            (r"Period\('2019', 'Y-DEC'\), 'foo', 'bar'", (Period(2019), "foo", "bar")),
            (r"Period\('2019', 'Y-DEC'\), 'y1', 'bar'", (Period(2019), "y1", "bar")),
            (r"Period\('2019', 'Y-DEC'\), 'foo', 'z1'", (Period(2019), "foo", "z1")),
            (
                r"Period\('2018', 'Y-DEC'\), Period\('2016', 'Y-DEC'\), 'bar'",
                (Period(2018), Period(2016), "bar"),
            ),
            (r"Period\('2018', 'Y-DEC'\), 'foo', 'y1'", (Period(2018), "foo", "y1")),
            (
                r"Period\('2017', 'Y-DEC'\), 'foo', Period\('2015', 'Y-DEC'\)",
                (Period(2017), "foo", Period(2015)),
            ),
            (r"Period\('2017', 'Y-DEC'\), 'z1', 'bar'", (Period(2017), "z1", "bar")),
        ],
    )
    def test_contains_raise_error_if_period_index_is_in_multi_index(self, msg, key):
        # GH#20684
        """
        parse_datetime_string_with_reso return parameter if type not matched.
        PeriodIndex.get_loc takes returned value from parse_datetime_string_with_reso
        as a tuple.
        If first argument is Period and a tuple has 3 items,
        process go on not raise exception
        """
        df = DataFrame(
            {
                "A": [Period(2019), "x1", "x2"],
                "B": [Period(2018), Period(2016), "y1"],
                "C": [Period(2017), "z1", Period(2015)],
                "V1": [1, 2, 3],
                "V2": [10, 20, 30],
            }
        ).set_index(["A", "B", "C"])
        with pytest.raises(KeyError, match=msg):
            df.loc[key]

    def test_loc_getitem_missing_unicode_key(self):
        df = DataFrame({"a": [1]})
        with pytest.raises(KeyError, match="\u05d0"):
            df.loc[:, "\u05d0"]  # should not raise UnicodeEncodeError

    def test_loc_getitem_dups(self):
        # GH 5678
        # repeated getitems on a dup index returning a ndarray
        df = DataFrame(
            np.random.default_rng(2).random((20, 5)),
            index=["ABCDE"[x % 5] for x in range(20)],
        )
        expected = df.loc["A", 0]
        result = df.loc[:, 0].loc["A"]
        tm.assert_series_equal(result, expected)

    def test_loc_getitem_dups2(self):
        # GH4726
        # dup indexing with iloc/loc
        df = DataFrame(
            [[1, 2, "foo", "bar", Timestamp("20130101")]],
            columns=["a", "a", "a", "a", "a"],
            index=[1],
        )
        expected = Series(
            [1, 2, "foo", "bar", Timestamp("20130101")],
            index=["a", "a", "a", "a", "a"],
            name=1,
        )

        result = df.iloc[0]
        tm.assert_series_equal(result, expected)

        result = df.loc[1]
        tm.assert_series_equal(result, expected)

    def test_loc_setitem_dups(self):
        # GH 6541
        df_orig = DataFrame(
            {
                "me": list("rttti"),
                "foo": list("aaade"),
                "bar": np.arange(5, dtype="float64") * 1.34 + 2,
                "bar2": np.arange(5, dtype="float64") * -0.34 + 2,
            }
        ).set_index("me")

        indexer = (
            "r",
            ["bar", "bar2"],
        )
        df = df_orig.copy()
        df.loc[indexer] *= 2.0
        tm.assert_series_equal(df.loc[indexer], 2.0 * df_orig.loc[indexer])

        indexer = (
            "r",
            "bar",
        )
        df = df_orig.copy()
        df.loc[indexer] *= 2.0
        assert df.loc[indexer] == 2.0 * df_orig.loc[indexer]

        indexer = (
            "t",
            ["bar", "bar2"],
        )
        df = df_orig.copy()
        df.loc[indexer] *= 2.0
        tm.assert_frame_equal(df.loc[indexer], 2.0 * df_orig.loc[indexer])

    def test_loc_setitem_slice(self):
        # GH10503

        # assigning the same type should not change the type
        df1 = DataFrame({"a": [0, 1, 1], "b": Series([100, 200, 300], dtype="uint32")})
        ix = df1["a"] == 1
        newb1 = df1.loc[ix, "b"] + 1
        df1.loc[ix, "b"] = newb1
        expected = DataFrame(
            {"a": [0, 1, 1], "b": Series([100, 201, 301], dtype="uint32")}
        )
        tm.assert_frame_equal(df1, expected)

        # assigning a new type should get the inferred type
        df2 = DataFrame({"a": [0, 1, 1], "b": [100, 200, 300]}, dtype="uint64")
        ix = df1["a"] == 1
        newb2 = df2.loc[ix, "b"]
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            df1.loc[ix, "b"] = newb2
        expected = DataFrame({"a": [0, 1, 1], "b": [100, 200, 300]}, dtype="uint64")
        tm.assert_frame_equal(df2, expected)

    def test_loc_setitem_dtype(self):
        # GH31340
        df = DataFrame({"id": ["A"], "a": [1.2], "b": [0.0], "c": [-2.5]})
        cols = ["a", "b", "c"]
        df.loc[:, cols] = df.loc[:, cols].astype("float32")

        # pre-2.0 this setting would swap in new arrays, in 2.0 it is correctly
        #  in-place, consistent with non-split-path
        expected = DataFrame(
            {
                "id": ["A"],
                "a": np.array([1.2], dtype="float64"),
                "b": np.array([0.0], dtype="float64"),
                "c": np.array([-2.5], dtype="float64"),
            }
        )  # id is inferred as object

        tm.assert_frame_equal(df, expected)

    def test_getitem_label_list_with_missing(self):
        s = Series(range(3), index=["a", "b", "c"])

        # consistency
        with pytest.raises(KeyError, match="not in index"):
            s[["a", "d"]]

        s = Series(range(3))
        with pytest.raises(KeyError, match="not in index"):
            s[[0, 3]]

    @pytest.mark.parametrize("index", [[True, False], [True, False, True, False]])
    def test_loc_getitem_bool_diff_len(self, index):
        # GH26658
        s = Series([1, 2, 3])
        msg = f"Boolean index has wrong length: {len(index)} instead of {len(s)}"
        with pytest.raises(IndexError, match=msg):
            s.loc[index]

    def test_loc_getitem_int_slice(self):
        # TODO: test something here?
        pass

    def test_loc_to_fail(self):
        # GH3449
        df = DataFrame(
            np.random.default_rng(2).random((3, 3)),
            index=["a", "b", "c"],
            columns=["e", "f", "g"],
        )

        msg = (
            rf"\"None of \[Index\(\[1, 2\], dtype='{np.dtype(int)}'\)\] are "
            r"in the \[index\]\""
        )
        with pytest.raises(KeyError, match=msg):
            df.loc[[1, 2], [1, 2]]

    def test_loc_to_fail2(self):
        # GH  7496
        # loc should not fallback

        s = Series(dtype=object)
        s.loc[1] = 1
        s.loc["a"] = 2

        with pytest.raises(KeyError, match=r"^-1$"):
            s.loc[-1]

        msg = (
            rf"\"None of \[Index\(\[-1, -2\], dtype='{np.dtype(int)}'\)\] are "
            r"in the \[index\]\""
        )
        with pytest.raises(KeyError, match=msg):
            s.loc[[-1, -2]]

        msg = r"\"None of \[Index\(\['4'\], dtype='object'\)\] are in the \[index\]\""
        with pytest.raises(KeyError, match=msg):
            s.loc[Index(["4"], dtype=object)]

        s.loc[-1] = 3
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[-1, -2]]

        s["a"] = 2
        msg = (
            rf"\"None of \[Index\(\[-2\], dtype='{np.dtype(int)}'\)\] are "
            r"in the \[index\]\""
        )
        with pytest.raises(KeyError, match=msg):
            s.loc[[-2]]

        del s["a"]

        with pytest.raises(KeyError, match=msg):
            s.loc[[-2]] = 0

    def test_loc_to_fail3(self):
        # inconsistency between .loc[values] and .loc[values,:]
        # GH 7999
        df = DataFrame([["a"], ["b"]], index=[1, 2], columns=["value"])

        msg = (
            rf"\"None of \[Index\(\[3\], dtype='{np.dtype(int)}'\)\] are "
            r"in the \[index\]\""
        )
        with pytest.raises(KeyError, match=msg):
            df.loc[[3], :]

        with pytest.raises(KeyError, match=msg):
            df.loc[[3]]

    def test_loc_getitem_list_with_fail(self):
        # 15747
        # should KeyError if *any* missing labels

        s = Series([1, 2, 3])

        s.loc[[2]]

        msg = f"\"None of [Index([3], dtype='{np.dtype(int)}')] are in the [index]"
        with pytest.raises(KeyError, match=re.escape(msg)):
            s.loc[[3]]

        # a non-match and a match
        with pytest.raises(KeyError, match="not in index"):
            s.loc[[2, 3]]

    def test_loc_index(self):
        # gh-17131
        # a boolean index should index like a boolean numpy array

        df = DataFrame(
            np.random.default_rng(2).random(size=(5, 10)),
            index=["alpha_0", "alpha_1", "alpha_2", "beta_0", "beta_1"],
        )

        mask = df.index.map(lambda x: "alpha" in x)
        expected = df.loc[np.array(mask)]

        result = df.loc[mask]
        tm.assert_frame_equal(result, expected)

        result = df.loc[mask.values]
        tm.assert_frame_equal(result, expected)

        result = df.loc[pd.array(mask, dtype="boolean")]
        tm.assert_frame_equal(result, expected)

    def test_loc_general(self):
        df = DataFrame(
            np.random.default_rng(2).random((4, 4)),
            columns=["A", "B", "C", "D"],
            index=["A", "B", "C", "D"],
        )

        # want this to work
        result = df.loc[:, "A":"B"].iloc[0:2, :]
        assert (result.columns == ["A", "B"]).all()
        assert (result.index == ["A", "B"]).all()

        # mixed type
        result = DataFrame({"a": [Timestamp("20130101")], "b": [1]}).iloc[0]
        expected = Series([Timestamp("20130101"), 1], index=["a", "b"], name=0)
        tm.assert_series_equal(result, expected)
        assert result.dtype == object

    @pytest.fixture
    def frame_for_consistency(self):
        return DataFrame(
            {
                "date": date_range("2000-01-01", "2000-01-5"),
                "val": Series(range(5), dtype=np.int64),
            }
        )

    @pytest.mark.parametrize(
        "val",
        [0, np.array(0, dtype=np.int64), np.array([0, 0, 0, 0, 0], dtype=np.int64)],
    )
    def test_loc_setitem_consistency(self, frame_for_consistency, val):
        # GH 6149
        # coerce similarly for setitem and loc when rows have a null-slice
        expected = DataFrame(
            {
                "date": Series(0, index=range(5), dtype=np.int64),
                "val": Series(range(5), dtype=np.int64),
            }
        )
        df = frame_for_consistency.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            df.loc[:, "date"] = val
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_consistency_dt64_to_str(self, frame_for_consistency):
        # GH 6149
        # coerce similarly for setitem and loc when rows have a null-slice

        expected = DataFrame(
            {
                "date": Series("foo", index=range(5)),
                "val": Series(range(5), dtype=np.int64),
            }
        )
        df = frame_for_consistency.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            df.loc[:, "date"] = "foo"
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_consistency_dt64_to_float(self, frame_for_consistency):
        # GH 6149
        # coerce similarly for setitem and loc when rows have a null-slice
        expected = DataFrame(
            {
                "date": Series(1.0, index=range(5)),
                "val": Series(range(5), dtype=np.int64),
            }
        )
        df = frame_for_consistency.copy()
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            df.loc[:, "date"] = 1.0
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_consistency_single_row(self):
        # GH 15494
        # setting on frame with single row
        df = DataFrame({"date": Series([Timestamp("20180101")])})
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            df.loc[:, "date"] = "string"
        expected = DataFrame({"date": Series(["string"])})
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_consistency_empty(self):
        # empty (essentially noops)
        # before the enforcement of #45333 in 2.0, the loc.setitem here would
        #  change the dtype of df.x to int64
        expected = DataFrame(columns=["x", "y"])
        df = DataFrame(columns=["x", "y"])
        with tm.assert_produces_warning(None):
            df.loc[:, "x"] = 1
        tm.assert_frame_equal(df, expected)

        # setting with setitem swaps in a new array, so changes the dtype
        df = DataFrame(columns=["x", "y"])
        df["x"] = 1
        expected["x"] = expected["x"].astype(np.int64)
        tm.assert_frame_equal(df, expected)

    # incompatible dtype warning
    @pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)")
    def test_loc_setitem_consistency_slice_column_len(self, using_infer_string):
        # .loc[:,column] setting with slice == len of the column
        # GH10408
        levels = [
            ["Region_1"] * 4,
            ["Site_1", "Site_1", "Site_2", "Site_2"],
            [3987227376, 3980680971, 3977723249, 3977723089],
        ]
        mi = MultiIndex.from_arrays(levels, names=["Region", "Site", "RespondentID"])

        clevels = [
            ["Respondent", "Respondent", "Respondent", "OtherCat", "OtherCat"],
            ["Something", "StartDate", "EndDate", "Yes/No", "SomethingElse"],
        ]
        cols = MultiIndex.from_arrays(clevels, names=["Level_0", "Level_1"])

        values = [
            ["A", "5/25/2015 10:59", "5/25/2015 11:22", "Yes", np.nan],
            ["A", "5/21/2015 9:40", "5/21/2015 9:52", "Yes", "Yes"],
            ["A", "5/20/2015 8:27", "5/20/2015 8:41", "Yes", np.nan],
            ["A", "5/20/2015 8:33", "5/20/2015 9:09", "Yes", "No"],
        ]
        df = DataFrame(values, index=mi, columns=cols)

        ctx = contextlib.nullcontext()
        if using_infer_string:
            ctx = pytest.raises(TypeError, match="Invalid value")

        with ctx:
            df.loc[:, ("Respondent", "StartDate")] = to_datetime(
                df.loc[:, ("Respondent", "StartDate")]
            )
        with ctx:
            df.loc[:, ("Respondent", "EndDate")] = to_datetime(
                df.loc[:, ("Respondent", "EndDate")]
            )

        if using_infer_string:
            # infer-objects won't infer stuff anymore
            return

        df = df.infer_objects()

        # Adding a new key
        df.loc[:, ("Respondent", "Duration")] = (
            df.loc[:, ("Respondent", "EndDate")]
            - df.loc[:, ("Respondent", "StartDate")]
        )

        # timedelta64[m] -> float, so this cannot be done inplace, so
        #  no warning
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            df.loc[:, ("Respondent", "Duration")] = df.loc[
                :, ("Respondent", "Duration")
            ] / Timedelta(60_000_000_000)

        expected = Series(
            [23.0, 12.0, 14.0, 36.0], index=df.index, name=("Respondent", "Duration")
        )
        tm.assert_series_equal(df[("Respondent", "Duration")], expected)

    @pytest.mark.parametrize("unit", ["Y", "M", "D", "h", "m", "s", "ms", "us"])
    def test_loc_assign_non_ns_datetime(self, unit):
        # GH 27395, non-ns dtype assignment via .loc should work
        # and return the same result when using simple assignment
        df = DataFrame(
            {
                "timestamp": [
                    np.datetime64("2017-02-11 12:41:29"),
                    np.datetime64("1991-11-07 04:22:37"),
                ]
            }
        )

        df.loc[:, unit] = df.loc[:, "timestamp"].values.astype(f"datetime64[{unit}]")
        df["expected"] = df.loc[:, "timestamp"].values.astype(f"datetime64[{unit}]")
        expected = Series(df.loc[:, "expected"], name=unit)
        tm.assert_series_equal(df.loc[:, unit], expected)

    def test_loc_modify_datetime(self):
        # see gh-28837
        df = DataFrame.from_dict(
            {"date": [1485264372711, 1485265925110, 1540215845888, 1540282121025]}
        )

        df["date_dt"] = to_datetime(df["date"], unit="ms", cache=True)

        df.loc[:, "date_dt_cp"] = df.loc[:, "date_dt"]
        df.loc[[2, 3], "date_dt_cp"] = df.loc[[2, 3], "date_dt"]

        expected = DataFrame(
            [
                [1485264372711, "2017-01-24 13:26:12.711", "2017-01-24 13:26:12.711"],
                [1485265925110, "2017-01-24 13:52:05.110", "2017-01-24 13:52:05.110"],
                [1540215845888, "2018-10-22 13:44:05.888", "2018-10-22 13:44:05.888"],
                [1540282121025, "2018-10-23 08:08:41.025", "2018-10-23 08:08:41.025"],
            ],
            columns=["date", "date_dt", "date_dt_cp"],
        )

        columns = ["date_dt", "date_dt_cp"]
        expected[columns] = expected[columns].apply(to_datetime)

        tm.assert_frame_equal(df, expected)

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    @pytest.mark.parametrize("has_ref", [True, False])
    def test_loc_setitem_frame_with_reindex(self, has_ref):
        # GH#6254 setting issue
        df = DataFrame(index=[3, 5, 4], columns=["A"], dtype=float)
        if has_ref:
            view = df[:]  # noqa: F841
        df.loc[[4, 3, 5], "A"] = np.array([1, 2, 3], dtype="int64")

        # setting integer values into a float dataframe with loc is inplace,
        #  so we retain float dtype
        ser = Series([2, 3, 1], index=[3, 5, 4], dtype=float)
        expected = DataFrame({"A": ser})
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_frame_with_reindex_mixed(self):
        # GH#40480
        df = DataFrame(index=[3, 5, 4], columns=["A", "B"], dtype=float)
        df["B"] = "string"
        df.loc[[4, 3, 5], "A"] = np.array([1, 2, 3], dtype="int64")
        ser = Series([2, 3, 1], index=[3, 5, 4], dtype="int64")
        # pre-2.0 this setting swapped in a new array, now it is inplace
        #  consistent with non-split-path
        expected = DataFrame({"A": ser.astype(float)})
        expected["B"] = "string"
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_frame_with_inverted_slice(self):
        # GH#40480
        df = DataFrame(index=[1, 2, 3], columns=["A", "B"], dtype=float)
        df["B"] = "string"
        df.loc[slice(3, 0, -1), "A"] = np.array([1, 2, 3], dtype="int64")
        # pre-2.0 this setting swapped in a new array, now it is inplace
        #  consistent with non-split-path
        expected = DataFrame({"A": [3.0, 2.0, 1.0], "B": "string"}, index=[1, 2, 3])
        tm.assert_frame_equal(df, expected)

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    @pytest.mark.parametrize("has_ref", [True, False])
    def test_loc_setitem_empty_frame(self, has_ref):
        # GH#6252 setting with an empty frame
        keys1 = ["@" + str(i) for i in range(5)]
        val1 = np.arange(5, dtype="int64")

        keys2 = ["@" + str(i) for i in range(4)]
        val2 = np.arange(4, dtype="int64")

        index = list(set(keys1).union(keys2))
        df = DataFrame(index=index)
        df["A"] = np.nan
        if has_ref:
            view = df[:]  # noqa: F841
        df.loc[keys1, "A"] = val1

        df["B"] = np.nan
        df.loc[keys2, "B"] = val2

        # Because df["A"] was initialized as float64, setting values into it
        #  is inplace, so that dtype is retained
        sera = Series(val1, index=keys1, dtype=np.float64)
        serb = Series(val2, index=keys2)
        expected = DataFrame({"A": sera, "B": serb}, columns=Index(["A", "B"])).reindex(
            index=index
        )
        tm.assert_frame_equal(df, expected)

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    @pytest.mark.parametrize("has_ref", [True, False])
    def test_loc_setitem_frame(self, has_ref):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((4, 4)),
            index=list("abcd"),
            columns=list("ABCD"),
        )
        if has_ref:
            view = df[:]  # noqa: F841

        result = df.iloc[0, 0]

        df.loc["a", "A"] = 1
        result = df.loc["a", "A"]
        assert result == 1

        result = df.iloc[0, 0]
        assert result == 1

        df.loc[:, "B":"D"] = 0
        expected = df.loc[:, "B":"D"]
        result = df.iloc[:, 1:]
        tm.assert_frame_equal(result, expected)

    def test_loc_setitem_frame_nan_int_coercion_invalid(self):
        # GH 8669
        # invalid coercion of nan -> int
        df = DataFrame({"A": [1, 2, 3], "B": np.nan})
        df.loc[df.B > df.A, "B"] = df.A
        expected = DataFrame({"A": [1, 2, 3], "B": np.nan})
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_frame_mixed_labels(self):
        # GH 6546
        # setting with mixed labels
        df = DataFrame({1: [1, 2], 2: [3, 4], "a": ["a", "b"]})

        result = df.loc[0, [1, 2]]
        expected = Series(
            [1, 3], index=Index([1, 2], dtype=object), dtype=object, name=0
        )
        tm.assert_series_equal(result, expected)

        expected = DataFrame({1: [5, 2], 2: [6, 4], "a": ["a", "b"]})
        df.loc[0, [1, 2]] = [5, 6]
        tm.assert_frame_equal(df, expected)

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    def test_loc_setitem_frame_multiples(self, warn_copy_on_write):
        # multiple setting
        df = DataFrame(
            {"A": ["foo", "bar", "baz"], "B": Series(range(3), dtype=np.int64)}
        )
        rhs = df.loc[1:2]
        rhs.index = df.index[0:2]
        df.loc[0:1] = rhs
        expected = DataFrame(
            {"A": ["bar", "baz", "baz"], "B": Series([1, 2, 2], dtype=np.int64)}
        )
        tm.assert_frame_equal(df, expected)

        # multiple setting with frame on rhs (with M8)
        df = DataFrame(
            {
                "date": date_range("2000-01-01", "2000-01-5"),
                "val": Series(range(5), dtype=np.int64),
            }
        )
        expected = DataFrame(
            {
                "date": [
                    Timestamp("20000101"),
                    Timestamp("20000102"),
                    Timestamp("20000101"),
                    Timestamp("20000102"),
                    Timestamp("20000103"),
                ],
                "val": Series([0, 1, 0, 1, 2], dtype=np.int64),
            }
        )
        rhs = df.loc[0:2]
        rhs.index = df.index[2:5]
        df.loc[2:4] = rhs
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "indexer", [["A"], slice(None, "A", None), np.array(["A"])]
    )
    @pytest.mark.parametrize("value", [["Z"], np.array(["Z"])])
    def test_loc_setitem_with_scalar_index(self, indexer, value):
        # GH #19474
        # assigning like "df.loc[0, ['A']] = ['Z']" should be evaluated
        # elementwisely, not using "setter('A', ['Z'])".

        # Set object dtype to avoid upcast when setting 'Z'
        df = DataFrame([[1, 2], [3, 4]], columns=["A", "B"]).astype({"A": object})
        df.loc[0, indexer] = value
        result = df.loc[0, "A"]

        assert is_scalar(result) and result == "Z"

    @pytest.mark.parametrize(
        "index,box,expected",
        [
            (
                ([0, 2], ["A", "B", "C", "D"]),
                7,
                DataFrame(
                    [[7, 7, 7, 7], [3, 4, np.nan, np.nan], [7, 7, 7, 7]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                (1, ["C", "D"]),
                [7, 8],
                DataFrame(
                    [[1, 2, np.nan, np.nan], [3, 4, 7, 8], [5, 6, np.nan, np.nan]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                (1, ["A", "B", "C"]),
                np.array([7, 8, 9], dtype=np.int64),
                DataFrame(
                    [[1, 2, np.nan], [7, 8, 9], [5, 6, np.nan]], columns=["A", "B", "C"]
                ),
            ),
            (
                (slice(1, 3, None), ["B", "C", "D"]),
                [[7, 8, 9], [10, 11, 12]],
                DataFrame(
                    [[1, 2, np.nan, np.nan], [3, 7, 8, 9], [5, 10, 11, 12]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                (slice(1, 3, None), ["C", "A", "D"]),
                np.array([[7, 8, 9], [10, 11, 12]], dtype=np.int64),
                DataFrame(
                    [[1, 2, np.nan, np.nan], [8, 4, 7, 9], [11, 6, 10, 12]],
                    columns=["A", "B", "C", "D"],
                ),
            ),
            (
                (slice(None, None, None), ["A", "C"]),
                DataFrame([[7, 8], [9, 10], [11, 12]], columns=["A", "C"]),
                DataFrame(
                    [[7, 2, 8], [9, 4, 10], [11, 6, 12]], columns=["A", "B", "C"]
                ),
            ),
        ],
    )
    def test_loc_setitem_missing_columns(self, index, box, expected):
        # GH 29334
        df = DataFrame([[1, 2], [3, 4], [5, 6]], columns=["A", "B"])

        df.loc[index] = box
        tm.assert_frame_equal(df, expected)

    def test_loc_coercion(self):
        # GH#12411
        df = DataFrame({"date": [Timestamp("20130101").tz_localize("UTC"), pd.NaT]})
        expected = df.dtypes

        result = df.iloc[[0]]
        tm.assert_series_equal(result.dtypes, expected)

        result = df.iloc[[1]]
        tm.assert_series_equal(result.dtypes, expected)

    def test_loc_coercion2(self):
        # GH#12045
        df = DataFrame({"date": [datetime(2012, 1, 1), datetime(1012, 1, 2)]})
        expected = df.dtypes

        result = df.iloc[[0]]
        tm.assert_series_equal(result.dtypes, expected)

        result = df.iloc[[1]]
        tm.assert_series_equal(result.dtypes, expected)

    def test_loc_coercion3(self):
        # GH#11594
        df = DataFrame({"text": ["some words"] + [None] * 9})
        expected = df.dtypes

        result = df.iloc[0:2]
        tm.assert_series_equal(result.dtypes, expected)

        result = df.iloc[3:]
        tm.assert_series_equal(result.dtypes, expected)

    def test_setitem_new_key_tz(self, indexer_sl):
        # GH#12862 should not raise on assigning the second value
        vals = [
            to_datetime(42).tz_localize("UTC"),
            to_datetime(666).tz_localize("UTC"),
        ]
        expected = Series(vals, index=Index(["foo", "bar"]))

        ser = Series(dtype=object)
        indexer_sl(ser)["foo"] = vals[0]
        indexer_sl(ser)["bar"] = vals[1]

        tm.assert_series_equal(ser, expected)

    def test_loc_non_unique(self):
        # GH3659
        # non-unique indexer with loc slice
        # https://groups.google.com/forum/?fromgroups#!topic/pydata/zTm2No0crYs

        # these are going to raise because the we are non monotonic
        df = DataFrame(
            {"A": [1, 2, 3, 4, 5, 6], "B": [3, 4, 5, 6, 7, 8]}, index=[0, 1, 0, 1, 2, 3]
        )
        msg = "'Cannot get left slice bound for non-unique label: 1'"
        with pytest.raises(KeyError, match=msg):
            df.loc[1:]
        msg = "'Cannot get left slice bound for non-unique label: 0'"
        with pytest.raises(KeyError, match=msg):
            df.loc[0:]
        msg = "'Cannot get left slice bound for non-unique label: 1'"
        with pytest.raises(KeyError, match=msg):
            df.loc[1:2]

        # monotonic are ok
        df = DataFrame(
            {"A": [1, 2, 3, 4, 5, 6], "B": [3, 4, 5, 6, 7, 8]}, index=[0, 1, 0, 1, 2, 3]
        ).sort_index(axis=0)
        result = df.loc[1:]
        expected = DataFrame({"A": [2, 4, 5, 6], "B": [4, 6, 7, 8]}, index=[1, 1, 2, 3])
        tm.assert_frame_equal(result, expected)

        result = df.loc[0:]
        tm.assert_frame_equal(result, df)

        result = df.loc[1:2]
        expected = DataFrame({"A": [2, 4, 5], "B": [4, 6, 7]}, index=[1, 1, 2])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.arm_slow
    @pytest.mark.parametrize("length, l2", [[900, 100], [900000, 100000]])
    def test_loc_non_unique_memory_error(self, length, l2):
        # GH 4280
        # non_unique index with a large selection triggers a memory error

        columns = list("ABCDEFG")

        df = pd.concat(
            [
                DataFrame(
                    np.random.default_rng(2).standard_normal((length, len(columns))),
                    index=np.arange(length),
                    columns=columns,
                ),
                DataFrame(np.ones((l2, len(columns))), index=[0] * l2, columns=columns),
            ]
        )

        assert df.index.is_unique is False

        mask = np.arange(l2)
        result = df.loc[mask]
        expected = pd.concat(
            [
                df.take([0]),
                DataFrame(
                    np.ones((len(mask), len(columns))),
                    index=[0] * len(mask),
                    columns=columns,
                ),
                df.take(mask[1:]),
            ]
        )
        tm.assert_frame_equal(result, expected)

    def test_loc_name(self):
        # GH 3880
        df = DataFrame([[1, 1], [1, 1]])
        df.index.name = "index_name"
        result = df.iloc[[0, 1]].index.name
        assert result == "index_name"

        result = df.loc[[0, 1]].index.name
        assert result == "index_name"

    def test_loc_empty_list_indexer_is_ok(self):
        df = DataFrame(
            np.ones((5, 2)),
            index=Index([f"i-{i}" for i in range(5)], name="a"),
            columns=Index([f"i-{i}" for i in range(2)], name="a"),
        )
        # vertical empty
        tm.assert_frame_equal(
            df.loc[:, []], df.iloc[:, :0], check_index_type=True, check_column_type=True
        )
        # horizontal empty
        tm.assert_frame_equal(
            df.loc[[], :], df.iloc[:0, :], check_index_type=True, check_column_type=True
        )
        # horizontal empty
        tm.assert_frame_equal(
            df.loc[[]], df.iloc[:0, :], check_index_type=True, check_column_type=True
        )

    def test_identity_slice_returns_new_object(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # GH13873

        original_df = DataFrame({"a": [1, 2, 3]})
        sliced_df = original_df.loc[:]
        assert sliced_df is not original_df
        assert original_df[:] is not original_df
        assert original_df.loc[:, :] is not original_df

        # should be a shallow copy
        assert np.shares_memory(original_df["a"]._values, sliced_df["a"]._values)

        # Setting using .loc[:, "a"] sets inplace so alters both sliced and orig
        # depending on CoW
        with tm.assert_cow_warning(warn_copy_on_write):
            original_df.loc[:, "a"] = [4, 4, 4]
        if using_copy_on_write:
            assert (sliced_df["a"] == [1, 2, 3]).all()
        else:
            assert (sliced_df["a"] == 4).all()

        # These should not return copies
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)))
        if using_copy_on_write or warn_copy_on_write:
            assert df[0] is not df.loc[:, 0]
        else:
            assert df[0] is df.loc[:, 0]

        # Same tests for Series
        original_series = Series([1, 2, 3, 4, 5, 6])
        sliced_series = original_series.loc[:]
        assert sliced_series is not original_series
        assert original_series[:] is not original_series

        with tm.assert_cow_warning(warn_copy_on_write):
            original_series[:3] = [7, 8, 9]
        if using_copy_on_write:
            assert all(sliced_series[:3] == [1, 2, 3])
        else:
            assert all(sliced_series[:3] == [7, 8, 9])

    def test_loc_copy_vs_view(self, request, using_copy_on_write):
        # GH 15631

        if not using_copy_on_write:
            mark = pytest.mark.xfail(reason="accidental fix reverted - GH37497")
            request.applymarker(mark)
        x = DataFrame(zip(range(3), range(3)), columns=["a", "b"])

        y = x.copy()
        q = y.loc[:, "a"]
        q += 2

        tm.assert_frame_equal(x, y)

        z = x.copy()
        q = z.loc[x.index, "a"]
        q += 2

        tm.assert_frame_equal(x, z)

    def test_loc_uint64(self):
        # GH20722
        # Test whether loc accept uint64 max value as index.
        umax = np.iinfo("uint64").max
        ser = Series([1, 2], index=[umax - 1, umax])

        result = ser.loc[umax - 1]
        expected = ser.iloc[0]
        assert result == expected

        result = ser.loc[[umax - 1]]
        expected = ser.iloc[[0]]
        tm.assert_series_equal(result, expected)

        result = ser.loc[[umax - 1, umax]]
        tm.assert_series_equal(result, ser)

    def test_loc_uint64_disallow_negative(self):
        # GH#41775
        umax = np.iinfo("uint64").max
        ser = Series([1, 2], index=[umax - 1, umax])

        with pytest.raises(KeyError, match="-1"):
            # don't wrap around
            ser.loc[-1]

        with pytest.raises(KeyError, match="-1"):
            # don't wrap around
            ser.loc[[-1]]

    def test_loc_setitem_empty_append_expands_rows(self):
        # GH6173, various appends to an empty dataframe

        data = [1, 2, 3]
        expected = DataFrame(
            {"x": data, "y": np.array([np.nan] * len(data), dtype=object)}
        )

        # appends to fit length of data
        df = DataFrame(columns=["x", "y"])
        df.loc[:, "x"] = data
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_empty_append_expands_rows_mixed_dtype(self):
        # GH#37932 same as test_loc_setitem_empty_append_expands_rows
        #  but with mixed dtype so we go through take_split_path
        data = [1, 2, 3]
        expected = DataFrame(
            {"x": data, "y": np.array([np.nan] * len(data), dtype=object)}
        )

        df = DataFrame(columns=["x", "y"])
        df["x"] = df["x"].astype(np.int64)
        df.loc[:, "x"] = data
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_empty_append_single_value(self):
        # only appends one value
        expected = DataFrame({"x": [1.0], "y": [np.nan]})
        df = DataFrame(columns=["x", "y"], dtype=float)
        df.loc[0, "x"] = expected.loc[0, "x"]
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_empty_append_raises(self):
        # GH6173, various appends to an empty dataframe

        data = [1, 2]
        df = DataFrame(columns=["x", "y"])
        df.index = df.index.astype(np.int64)
        msg = (
            rf"None of \[Index\(\[0, 1\], dtype='{np.dtype(int)}'\)\] "
            r"are in the \[index\]"
        )
        with pytest.raises(KeyError, match=msg):
            df.loc[[0, 1], "x"] = data

        msg = "setting an array element with a sequence."
        with pytest.raises(ValueError, match=msg):
            df.loc[0:2, "x"] = data

    def test_indexing_zerodim_np_array(self):
        # GH24924
        df = DataFrame([[1, 2], [3, 4]])
        result = df.loc[np.array(0)]
        s = Series([1, 2], name=0)
        tm.assert_series_equal(result, s)

    def test_series_indexing_zerodim_np_array(self):
        # GH24924
        s = Series([1, 2])
        result = s.loc[np.array(0)]
        assert result == 1

    def test_loc_reverse_assignment(self):
        # GH26939
        data = [1, 2, 3, 4, 5, 6] + [None] * 4
        expected = Series(data, index=range(2010, 2020))

        result = Series(index=range(2010, 2020), dtype=np.float64)
        result.loc[2015:2010:-1] = [6, 5, 4, 3, 2, 1]

        tm.assert_series_equal(result, expected)

    def test_loc_setitem_str_to_small_float_conversion_type(self, using_infer_string):
        # GH#20388

        col_data = [str(np.random.default_rng(2).random() * 1e-12) for _ in range(5)]
        result = DataFrame(col_data, columns=["A"])
        expected = DataFrame(col_data, columns=["A"])
        tm.assert_frame_equal(result, expected)

        # assigning with loc/iloc attempts to set the values inplace, which
        #  in this case is successful
        if using_infer_string:
            with pytest.raises(TypeError, match="Invalid value"):
                result.loc[result.index, "A"] = [float(x) for x in col_data]
        else:
            result.loc[result.index, "A"] = [float(x) for x in col_data]
            expected = DataFrame(col_data, columns=["A"], dtype=float).astype(object)
            tm.assert_frame_equal(result, expected)

        # assigning the entire column using __setitem__ swaps in the new array
        # GH#???
        result["A"] = [float(x) for x in col_data]
        expected = DataFrame(col_data, columns=["A"], dtype=float)
        tm.assert_frame_equal(result, expected)

    def test_loc_getitem_time_object(self, frame_or_series):
        rng = date_range("1/1/2000", "1/5/2000", freq="5min")
        mask = (rng.hour == 9) & (rng.minute == 30)

        obj = DataFrame(
            np.random.default_rng(2).standard_normal((len(rng), 3)), index=rng
        )
        obj = tm.get_obj(obj, frame_or_series)

        result = obj.loc[time(9, 30)]
        exp = obj.loc[mask]
        tm.assert_equal(result, exp)

        chunk = obj.loc["1/4/2000":]
        result = chunk.loc[time(9, 30)]
        expected = result[-1:]

        # Without resetting the freqs, these are 5 min and 1440 min, respectively
        result.index = result.index._with_freq(None)
        expected.index = expected.index._with_freq(None)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("spmatrix_t", ["coo_matrix", "csc_matrix", "csr_matrix"])
    @pytest.mark.parametrize("dtype", [np.int64, np.float64, complex])
    def test_loc_getitem_range_from_spmatrix(self, spmatrix_t, dtype):
        sp_sparse = pytest.importorskip("scipy.sparse")

        spmatrix_t = getattr(sp_sparse, spmatrix_t)

        # The bug is triggered by a sparse matrix with purely sparse columns.  So the
        # recipe below generates a rectangular matrix of dimension (5, 7) where all the
        # diagonal cells are ones, meaning the last two columns are purely sparse.
        rows, cols = 5, 7
        spmatrix = spmatrix_t(np.eye(rows, cols, dtype=dtype), dtype=dtype)
        df = DataFrame.sparse.from_spmatrix(spmatrix)

        # regression test for GH#34526
        itr_idx = range(2, rows)
        result = df.loc[itr_idx].values
        expected = spmatrix.toarray()[itr_idx]
        tm.assert_numpy_array_equal(result, expected)

        # regression test for GH#34540
        result = df.loc[itr_idx].dtypes.values
        expected = np.full(cols, SparseDtype(dtype, fill_value=0))
        tm.assert_numpy_array_equal(result, expected)

    def test_loc_getitem_listlike_all_retains_sparse(self):
        df = DataFrame({"A": pd.array([0, 0], dtype=SparseDtype("int64"))})
        result = df.loc[[0, 1]]
        tm.assert_frame_equal(result, df)

    def test_loc_getitem_sparse_frame(self):
        # GH34687
        sp_sparse = pytest.importorskip("scipy.sparse")

        df = DataFrame.sparse.from_spmatrix(sp_sparse.eye(5))
        result = df.loc[range(2)]
        expected = DataFrame(
            [[1.0, 0.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0, 0.0]],
            dtype=SparseDtype("float64", 0.0),
        )
        tm.assert_frame_equal(result, expected)

        result = df.loc[range(2)].loc[range(1)]
        expected = DataFrame(
            [[1.0, 0.0, 0.0, 0.0, 0.0]], dtype=SparseDtype("float64", 0.0)
        )
        tm.assert_frame_equal(result, expected)

    def test_loc_getitem_sparse_series(self):
        # GH34687
        s = Series([1.0, 0.0, 0.0, 0.0, 0.0], dtype=SparseDtype("float64", 0.0))

        result = s.loc[range(2)]
        expected = Series([1.0, 0.0], dtype=SparseDtype("float64", 0.0))
        tm.assert_series_equal(result, expected)

        result = s.loc[range(3)].loc[range(2)]
        expected = Series([1.0, 0.0], dtype=SparseDtype("float64", 0.0))
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("indexer", ["loc", "iloc"])
    def test_getitem_single_row_sparse_df(self, indexer):
        # GH#46406
        df = DataFrame([[1.0, 0.0, 1.5], [0.0, 2.0, 0.0]], dtype=SparseDtype(float))
        result = getattr(df, indexer)[0]
        expected = Series([1.0, 0.0, 1.5], dtype=SparseDtype(float), name=0)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("key_type", [iter, np.array, Series, Index])
    def test_loc_getitem_iterable(self, float_frame, key_type):
        idx = key_type(["A", "B", "C"])
        result = float_frame.loc[:, idx]
        expected = float_frame.loc[:, ["A", "B", "C"]]
        tm.assert_frame_equal(result, expected)

    def test_loc_getitem_timedelta_0seconds(self):
        # GH#10583
        df = DataFrame(np.random.default_rng(2).normal(size=(10, 4)))
        df.index = timedelta_range(start="0s", periods=10, freq="s")
        expected = df.loc[Timedelta("0s") :, :]
        result = df.loc["0s":, :]
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "val,expected", [(2**63 - 1, Series([1])), (2**63, Series([2]))]
    )
    def test_loc_getitem_uint64_scalar(self, val, expected):
        # see GH#19399
        df = DataFrame([1, 2], index=[2**63 - 1, 2**63])
        result = df.loc[val]

        expected.name = val
        tm.assert_series_equal(result, expected)

    def test_loc_setitem_int_label_with_float_index(self, float_numpy_dtype):
        # note labels are floats
        dtype = float_numpy_dtype
        ser = Series(["a", "b", "c"], index=Index([0, 0.5, 1], dtype=dtype))
        expected = ser.copy()

        ser.loc[1] = "zoo"
        expected.iloc[2] = "zoo"

        tm.assert_series_equal(ser, expected)

    @pytest.mark.parametrize(
        "indexer, expected",
        [
            # The test name is a misnomer in the 0 case as df.index[indexer]
            #  is a scalar.
            (0, [20, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
            (slice(4, 8), [0, 1, 2, 3, 20, 20, 20, 20, 8, 9]),
            ([3, 5], [0, 1, 2, 20, 4, 20, 6, 7, 8, 9]),
        ],
    )
    def test_loc_setitem_listlike_with_timedelta64index(self, indexer, expected):
        # GH#16637
        tdi = to_timedelta(range(10), unit="s")
        df = DataFrame({"x": range(10)}, dtype="int64", index=tdi)

        df.loc[df.index[indexer], "x"] = 20

        expected = DataFrame(
            expected,
            index=tdi,
            columns=["x"],
            dtype="int64",
        )

        tm.assert_frame_equal(expected, df)

    def test_loc_setitem_categorical_values_partial_column_slice(self):
        # Assigning a Category to parts of a int/... column uses the values of
        # the Categorical
        df = DataFrame({"a": [1, 1, 1, 1, 1], "b": list("aaaaa")})
        exp = DataFrame({"a": [1, "b", "b", 1, 1], "b": list("aabba")})
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            df.loc[1:2, "a"] = Categorical(["b", "b"], categories=["a", "b"])
            df.loc[2:3, "b"] = Categorical(["b", "b"], categories=["a", "b"])
        tm.assert_frame_equal(df, exp)

    def test_loc_setitem_single_row_categorical(self, using_infer_string):
        # GH#25495
        df = DataFrame({"Alpha": ["a"], "Numeric": [0]})
        categories = Categorical(df["Alpha"], categories=["a", "b", "c"])

        # pre-2.0 this swapped in a new array, in 2.0 it operates inplace,
        #  consistent with non-split-path
        df.loc[:, "Alpha"] = categories

        result = df["Alpha"]
        expected = Series(categories, index=df.index, name="Alpha").astype(
            object if not using_infer_string else "str"
        )
        tm.assert_series_equal(result, expected)

        # double-check that the non-loc setting retains categoricalness
        df["Alpha"] = categories
        tm.assert_series_equal(df["Alpha"], Series(categories, name="Alpha"))

    def test_loc_setitem_datetime_coercion(self):
        # GH#1048
        df = DataFrame({"c": [Timestamp("2010-10-01")] * 3})
        df.loc[0:1, "c"] = np.datetime64("2008-08-08")
        assert Timestamp("2008-08-08") == df.loc[0, "c"]
        assert Timestamp("2008-08-08") == df.loc[1, "c"]
        with tm.assert_produces_warning(FutureWarning, match="incompatible dtype"):
            df.loc[2, "c"] = date(2005, 5, 5)
        assert Timestamp("2005-05-05").date() == df.loc[2, "c"]

    @pytest.mark.parametrize("idxer", ["var", ["var"]])
    def test_loc_setitem_datetimeindex_tz(self, idxer, tz_naive_fixture):
        # GH#11365
        tz = tz_naive_fixture
        idx = date_range(start="2015-07-12", periods=3, freq="h", tz=tz)
        expected = DataFrame(1.2, index=idx, columns=["var"])
        # if result started off with object dtype, then the .loc.__setitem__
        #  below would retain object dtype
        result = DataFrame(index=idx, columns=["var"], dtype=np.float64)
        with tm.assert_produces_warning(
            FutureWarning if idxer == "var" else None, match="incompatible dtype"
        ):
            # See https://github.com/pandas-dev/pandas/issues/56223
            result.loc[:, idxer] = expected
        tm.assert_frame_equal(result, expected)

    def test_loc_setitem_time_key(self, using_array_manager):
        index = date_range("2012-01-01", "2012-01-05", freq="30min")
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(index), 5)), index=index
        )
        akey = time(12, 0, 0)
        bkey = slice(time(13, 0, 0), time(14, 0, 0))
        ainds = [24, 72, 120, 168]
        binds = [26, 27, 28, 74, 75, 76, 122, 123, 124, 170, 171, 172]

        result = df.copy()
        result.loc[akey] = 0
        result = result.loc[akey]
        expected = df.loc[akey].copy()
        expected.loc[:] = 0
        if using_array_manager:
            # TODO(ArrayManager) we are still overwriting columns
            expected = expected.astype(float)
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        result.loc[akey] = 0
        result.loc[akey] = df.iloc[ainds]
        tm.assert_frame_equal(result, df)

        result = df.copy()
        result.loc[bkey] = 0
        result = result.loc[bkey]
        expected = df.loc[bkey].copy()
        expected.loc[:] = 0
        if using_array_manager:
            # TODO(ArrayManager) we are still overwriting columns
            expected = expected.astype(float)
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        result.loc[bkey] = 0
        result.loc[bkey] = df.iloc[binds]
        tm.assert_frame_equal(result, df)

    @pytest.mark.parametrize("key", ["A", ["A"], ("A", slice(None))])
    def test_loc_setitem_unsorted_multiindex_columns(self, key):
        # GH#38601
        mi = MultiIndex.from_tuples([("A", 4), ("B", "3"), ("A", "2")])
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=mi)
        obj = df.copy()
        obj.loc[:, key] = np.zeros((2, 2), dtype="int64")
        expected = DataFrame([[0, 2, 0], [0, 5, 0]], columns=mi)
        tm.assert_frame_equal(obj, expected)

        df = df.sort_index(axis=1)
        df.loc[:, key] = np.zeros((2, 2), dtype="int64")
        expected = expected.sort_index(axis=1)
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_uint_drop(self, any_int_numpy_dtype):
        # see GH#18311
        # assigning series.loc[0] = 4 changed series.dtype to int
        series = Series([1, 2, 3], dtype=any_int_numpy_dtype)
        series.loc[0] = 4
        expected = Series([4, 2, 3], dtype=any_int_numpy_dtype)
        tm.assert_series_equal(series, expected)

    def test_loc_setitem_td64_non_nano(self):
        # GH#14155
        ser = Series(10 * [np.timedelta64(10, "m")])
        ser.loc[[1, 2, 3]] = np.timedelta64(20, "m")
        expected = Series(10 * [np.timedelta64(10, "m")])
        expected.loc[[1, 2, 3]] = Timedelta(np.timedelta64(20, "m"))
        tm.assert_series_equal(ser, expected)

    def test_loc_setitem_2d_to_1d_raises(self):
        data = np.random.default_rng(2).standard_normal((2, 2))
        # float64 dtype to avoid upcast when trying to set float data
        ser = Series(range(2), dtype="float64")

        msg = "setting an array element with a sequence."
        with pytest.raises(ValueError, match=msg):
            ser.loc[range(2)] = data

        with pytest.raises(ValueError, match=msg):
            ser.loc[:] = data

    def test_loc_getitem_interval_index(self):
        # GH#19977
        index = pd.interval_range(start=0, periods=3)
        df = DataFrame(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]], index=index, columns=["A", "B", "C"]
        )

        expected = 1
        result = df.loc[0.5, "A"]
        tm.assert_almost_equal(result, expected)

    def test_loc_getitem_interval_index2(self):
        # GH#19977
        index = pd.interval_range(start=0, periods=3, closed="both")
        df = DataFrame(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]], index=index, columns=["A", "B", "C"]
        )

        index_exp = pd.interval_range(start=0, periods=2, freq=1, closed="both")
        expected = Series([1, 4], index=index_exp, name="A")
        result = df.loc[1, "A"]
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("tpl", [(1,), (1, 2)])
    def test_loc_getitem_index_single_double_tuples(self, tpl):
        # GH#20991
        idx = Index(
            [(1,), (1, 2)],
            name="A",
            tupleize_cols=False,
        )
        df = DataFrame(index=idx)

        result = df.loc[[tpl]]
        idx = Index([tpl], name="A", tupleize_cols=False)
        expected = DataFrame(index=idx)
        tm.assert_frame_equal(result, expected)

    def test_loc_getitem_index_namedtuple(self):
        IndexType = namedtuple("IndexType", ["a", "b"])
        idx1 = IndexType("foo", "bar")
        idx2 = IndexType("baz", "bof")
        index = Index([idx1, idx2], name="composite_index", tupleize_cols=False)
        df = DataFrame([(1, 2), (3, 4)], index=index, columns=["A", "B"])

        result = df.loc[IndexType("foo", "bar")]["A"]
        assert result == 1

    def test_loc_setitem_single_column_mixed(self, using_infer_string):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 3)),
            index=["a", "b", "c", "d", "e"],
            columns=["foo", "bar", "baz"],
        )
        df["str"] = "qux"
        df.loc[df.index[::2], "str"] = np.nan
        expected = Series(
            [np.nan, "qux", np.nan, "qux", np.nan],
            dtype=object if not using_infer_string else "str",
        ).values
        tm.assert_almost_equal(df["str"].values, expected)

    def test_loc_setitem_cast2(self):
        # GH#7704
        # dtype conversion on setting
        df = DataFrame(np.random.default_rng(2).random((30, 3)), columns=tuple("ABC"))
        df["event"] = np.nan
        with tm.assert_produces_warning(
            FutureWarning, match="item of incompatible dtype"
        ):
            df.loc[10, "event"] = "foo"
        result = df.dtypes
        expected = Series(
            [np.dtype("float64")] * 3 + [np.dtype("object")],
            index=["A", "B", "C", "event"],
        )
        tm.assert_series_equal(result, expected)

    def test_loc_setitem_cast3(self):
        # Test that data type is preserved . GH#5782
        df = DataFrame({"one": np.arange(6, dtype=np.int8)})
        df.loc[1, "one"] = 6
        assert df.dtypes.one == np.dtype(np.int8)
        df.one = np.int8(7)
        assert df.dtypes.one == np.dtype(np.int8)

    def test_loc_setitem_range_key(self, frame_or_series):
        # GH#45479 don't treat range key as positional
        obj = frame_or_series(range(5), index=[3, 4, 1, 0, 2])

        values = [9, 10, 11]
        if obj.ndim == 2:
            values = [[9], [10], [11]]

        obj.loc[range(3)] = values

        expected = frame_or_series([0, 1, 10, 9, 11], index=obj.index)
        tm.assert_equal(obj, expected)

    def test_loc_setitem_numpy_frame_categorical_value(self):
        # GH#52927
        df = DataFrame({"a": [1, 1, 1, 1, 1], "b": ["a", "a", "a", "a", "a"]})
        df.loc[1:2, "a"] = Categorical([2, 2], categories=[1, 2])

        expected = DataFrame({"a": [1, 2, 2, 1, 1], "b": ["a", "a", "a", "a", "a"]})
        tm.assert_frame_equal(df, expected)


class TestLocWithEllipsis:
    @pytest.fixture(params=[tm.loc, tm.iloc])
    def indexer(self, request):
        # Test iloc while we're here
        return request.param

    @pytest.fixture
    def obj(self, series_with_simple_index, frame_or_series):
        obj = series_with_simple_index
        if frame_or_series is not Series:
            obj = obj.to_frame()
        return obj

    def test_loc_iloc_getitem_ellipsis(self, obj, indexer):
        result = indexer(obj)[...]
        tm.assert_equal(result, obj)

    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_loc_iloc_getitem_leading_ellipses(self, series_with_simple_index, indexer):
        obj = series_with_simple_index
        key = 0 if (indexer is tm.iloc or len(obj) == 0) else obj.index[0]

        if indexer is tm.loc and obj.index.inferred_type == "boolean":
            # passing [False] will get interpreted as a boolean mask
            # TODO: should it?  unambiguous when lengths dont match?
            return
        if indexer is tm.loc and isinstance(obj.index, MultiIndex):
            msg = "MultiIndex does not support indexing with Ellipsis"
            with pytest.raises(NotImplementedError, match=msg):
                result = indexer(obj)[..., [key]]

        elif len(obj) != 0:
            result = indexer(obj)[..., [key]]
            expected = indexer(obj)[[key]]
            tm.assert_series_equal(result, expected)

        key2 = 0 if indexer is tm.iloc else obj.name
        df = obj.to_frame()
        result = indexer(df)[..., [key2]]
        expected = indexer(df)[:, [key2]]
        tm.assert_frame_equal(result, expected)

    def test_loc_iloc_getitem_ellipses_only_one_ellipsis(self, obj, indexer):
        # GH37750
        key = 0 if (indexer is tm.iloc or len(obj) == 0) else obj.index[0]

        with pytest.raises(IndexingError, match=_one_ellipsis_message):
            indexer(obj)[..., ...]

        with pytest.raises(IndexingError, match=_one_ellipsis_message):
            indexer(obj)[..., [key], ...]

        with pytest.raises(IndexingError, match=_one_ellipsis_message):
            indexer(obj)[..., ..., key]

        # one_ellipsis_message takes precedence over "Too many indexers"
        #  only when the first key is Ellipsis
        with pytest.raises(IndexingError, match="Too many indexers"):
            indexer(obj)[key, ..., ...]


class TestLocWithMultiIndex:
    @pytest.mark.parametrize(
        "keys, expected",
        [
            (["b", "a"], [["b", "b", "a", "a"], [1, 2, 1, 2]]),
            (["a", "b"], [["a", "a", "b", "b"], [1, 2, 1, 2]]),
            ((["a", "b"], [1, 2]), [["a", "a", "b", "b"], [1, 2, 1, 2]]),
            ((["a", "b"], [2, 1]), [["a", "a", "b", "b"], [2, 1, 2, 1]]),
            ((["b", "a"], [2, 1]), [["b", "b", "a", "a"], [2, 1, 2, 1]]),
            ((["b", "a"], [1, 2]), [["b", "b", "a", "a"], [1, 2, 1, 2]]),
            ((["c", "a"], [2, 1]), [["c", "a", "a"], [1, 2, 1]]),
        ],
    )
    @pytest.mark.parametrize("dim", ["index", "columns"])
    def test_loc_getitem_multilevel_index_order(self, dim, keys, expected):
        # GH#22797
        # Try to respect order of keys given for MultiIndex.loc
        kwargs = {dim: [["c", "a", "a", "b", "b"], [1, 1, 2, 1, 2]]}
        df = DataFrame(np.arange(25).reshape(5, 5), **kwargs)
        exp_index = MultiIndex.from_arrays(expected)
        if dim == "index":
            res = df.loc[keys, :]
            tm.assert_index_equal(res.index, exp_index)
        elif dim == "columns":
            res = df.loc[:, keys]
            tm.assert_index_equal(res.columns, exp_index)

    def test_loc_preserve_names(self, multiindex_year_month_day_dataframe_random_data):
        ymd = multiindex_year_month_day_dataframe_random_data

        result = ymd.loc[2000]
        result2 = ymd["A"].loc[2000]
        assert result.index.names == ymd.index.names[1:]
        assert result2.index.names == ymd.index.names[1:]

        result = ymd.loc[2000, 2]
        result2 = ymd["A"].loc[2000, 2]
        assert result.index.name == ymd.index.names[2]
        assert result2.index.name == ymd.index.names[2]

    def test_loc_getitem_multiindex_nonunique_len_zero(self):
        # GH#13691
        mi = MultiIndex.from_product([[0], [1, 1]])
        ser = Series(0, index=mi)

        res = ser.loc[[]]

        expected = ser[:0]
        tm.assert_series_equal(res, expected)

        res2 = ser.loc[ser.iloc[0:0]]
        tm.assert_series_equal(res2, expected)

    def test_loc_getitem_access_none_value_in_multiindex(self):
        # GH#34318: test that you can access a None value using .loc
        #  through a Multiindex

        ser = Series([None], MultiIndex.from_arrays([["Level1"], ["Level2"]]))
        result = ser.loc[("Level1", "Level2")]
        assert result is None

        midx = MultiIndex.from_product([["Level1"], ["Level2_a", "Level2_b"]])
        ser = Series([None] * len(midx), dtype=object, index=midx)
        result = ser.loc[("Level1", "Level2_a")]
        assert result is None

        ser = Series([1] * len(midx), dtype=object, index=midx)
        result = ser.loc[("Level1", "Level2_a")]
        assert result == 1

    def test_loc_setitem_multiindex_slice(self):
        # GH 34870

        index = MultiIndex.from_tuples(
            zip(
                ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
                ["one", "two", "one", "two", "one", "two", "one", "two"],
            ),
            names=["first", "second"],
        )

        result = Series([1, 1, 1, 1, 1, 1, 1, 1], index=index)
        result.loc[("baz", "one"):("foo", "two")] = 100

        expected = Series([1, 1, 100, 100, 100, 100, 1, 1], index=index)

        tm.assert_series_equal(result, expected)

    def test_loc_getitem_slice_datetime_objs_with_datetimeindex(self):
        times = date_range("2000-01-01", freq="10min", periods=100000)
        ser = Series(range(100000), times)
        result = ser.loc[datetime(1900, 1, 1) : datetime(2100, 1, 1)]
        tm.assert_series_equal(result, ser)

    def test_loc_getitem_datetime_string_with_datetimeindex(self):
        # GH 16710
        df = DataFrame(
            {"a": range(10), "b": range(10)},
            index=date_range("2010-01-01", "2010-01-10"),
        )
        result = df.loc[["2010-01-01", "2010-01-05"], ["a", "b"]]
        expected = DataFrame(
            {"a": [0, 4], "b": [0, 4]},
            index=DatetimeIndex(["2010-01-01", "2010-01-05"]),
        )
        tm.assert_frame_equal(result, expected)

    def test_loc_getitem_sorted_index_level_with_duplicates(self):
        # GH#4516 sorting a MultiIndex with duplicates and multiple dtypes
        mi = MultiIndex.from_tuples(
            [
                ("foo", "bar"),
                ("foo", "bar"),
                ("bah", "bam"),
                ("bah", "bam"),
                ("foo", "bar"),
                ("bah", "bam"),
            ],
            names=["A", "B"],
        )
        df = DataFrame(
            [
                [1.0, 1],
                [2.0, 2],
                [3.0, 3],
                [4.0, 4],
                [5.0, 5],
                [6.0, 6],
            ],
            index=mi,
            columns=["C", "D"],
        )
        df = df.sort_index(level=0)

        expected = DataFrame(
            [[1.0, 1], [2.0, 2], [5.0, 5]], columns=["C", "D"], index=mi.take([0, 1, 4])
        )

        result = df.loc[("foo", "bar")]
        tm.assert_frame_equal(result, expected)

    def test_additional_element_to_categorical_series_loc(self):
        # GH#47677
        result = Series(["a", "b", "c"], dtype="category")
        result.loc[3] = 0
        expected = Series(["a", "b", "c", 0], dtype="object")
        tm.assert_series_equal(result, expected)

    def test_additional_categorical_element_loc(self):
        # GH#47677
        result = Series(["a", "b", "c"], dtype="category")
        result.loc[3] = "a"
        expected = Series(["a", "b", "c", "a"], dtype="category")
        tm.assert_series_equal(result, expected)

    def test_loc_set_nan_in_categorical_series(self, any_numeric_ea_dtype):
        # GH#47677
        srs = Series(
            [1, 2, 3],
            dtype=CategoricalDtype(Index([1, 2, 3], dtype=any_numeric_ea_dtype)),
        )
        # enlarge
        srs.loc[3] = np.nan
        expected = Series(
            [1, 2, 3, np.nan],
            dtype=CategoricalDtype(Index([1, 2, 3], dtype=any_numeric_ea_dtype)),
        )
        tm.assert_series_equal(srs, expected)
        # set into
        srs.loc[1] = np.nan
        expected = Series(
            [1, np.nan, 3, np.nan],
            dtype=CategoricalDtype(Index([1, 2, 3], dtype=any_numeric_ea_dtype)),
        )
        tm.assert_series_equal(srs, expected)

    @pytest.mark.parametrize("na", (np.nan, pd.NA, None, pd.NaT))
    def test_loc_consistency_series_enlarge_set_into(self, na):
        # GH#47677
        srs_enlarge = Series(["a", "b", "c"], dtype="category")
        srs_enlarge.loc[3] = na

        srs_setinto = Series(["a", "b", "c", "a"], dtype="category")
        srs_setinto.loc[3] = na

        tm.assert_series_equal(srs_enlarge, srs_setinto)
        expected = Series(["a", "b", "c", na], dtype="category")
        tm.assert_series_equal(srs_enlarge, expected)

    def test_loc_getitem_preserves_index_level_category_dtype(self):
        # GH#15166
        df = DataFrame(
            data=np.arange(2, 22, 2),
            index=MultiIndex(
                levels=[CategoricalIndex(["a", "b"]), range(10)],
                codes=[[0] * 5 + [1] * 5, range(10)],
                names=["Index1", "Index2"],
            ),
        )

        expected = CategoricalIndex(
            ["a", "b"],
            categories=["a", "b"],
            ordered=False,
            name="Index1",
            dtype="category",
        )

        result = df.index.levels[0]
        tm.assert_index_equal(result, expected)

        result = df.loc[["a"]].index.levels[0]
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("lt_value", [30, 10])
    def test_loc_multiindex_levels_contain_values_not_in_index_anymore(self, lt_value):
        # GH#41170
        df = DataFrame({"a": [12, 23, 34, 45]}, index=[list("aabb"), [0, 1, 2, 3]])
        with pytest.raises(KeyError, match=r"\['b'\] not in index"):
            df.loc[df["a"] < lt_value, :].loc[["b"], :]

    def test_loc_multiindex_null_slice_na_level(self):
        # GH#42055
        lev1 = np.array([np.nan, np.nan])
        lev2 = ["bar", "baz"]
        mi = MultiIndex.from_arrays([lev1, lev2])
        ser = Series([0, 1], index=mi)
        result = ser.loc[:, "bar"]

        # TODO: should we have name="bar"?
        expected = Series([0], index=[np.nan])
        tm.assert_series_equal(result, expected)

    def test_loc_drops_level(self):
        # Based on test_series_varied_multiindex_alignment, where
        #  this used to fail to drop the first level
        mi = MultiIndex.from_product(
            [list("ab"), list("xy"), [1, 2]], names=["ab", "xy", "num"]
        )
        ser = Series(range(8), index=mi)

        loc_result = ser.loc["a", :, :]
        expected = ser.index.droplevel(0)[:4]
        tm.assert_index_equal(loc_result.index, expected)


class TestLocSetitemWithExpansion:
    def test_loc_setitem_with_expansion_large_dataframe(self, monkeypatch):
        # GH#10692
        size_cutoff = 50
        with monkeypatch.context():
            monkeypatch.setattr(libindex, "_SIZE_CUTOFF", size_cutoff)
            result = DataFrame({"x": range(size_cutoff)}, dtype="int64")
            result.loc[size_cutoff] = size_cutoff
        expected = DataFrame({"x": range(size_cutoff + 1)}, dtype="int64")
        tm.assert_frame_equal(result, expected)

    def test_loc_setitem_empty_series(self):
        # GH#5226

        # partially set with an empty object series
        ser = Series(dtype=object)
        ser.loc[1] = 1
        tm.assert_series_equal(ser, Series([1], index=[1]))
        ser.loc[3] = 3
        tm.assert_series_equal(ser, Series([1, 3], index=[1, 3]))

    def test_loc_setitem_empty_series_float(self):
        # GH#5226

        # partially set with an empty object series
        ser = Series(dtype=object)
        ser.loc[1] = 1.0
        tm.assert_series_equal(ser, Series([1.0], index=[1]))
        ser.loc[3] = 3.0
        tm.assert_series_equal(ser, Series([1.0, 3.0], index=[1, 3]))

    def test_loc_setitem_empty_series_str_idx(self):
        # GH#5226

        # partially set with an empty object series
        ser = Series(dtype=object)
        ser.loc["foo"] = 1
        tm.assert_series_equal(ser, Series([1], index=Index(["foo"])))
        ser.loc["bar"] = 3
        tm.assert_series_equal(ser, Series([1, 3], index=Index(["foo", "bar"])))
        ser.loc[3] = 4
        tm.assert_series_equal(ser, Series([1, 3, 4], index=Index(["foo", "bar", 3])))

    def test_loc_setitem_incremental_with_dst(self):
        # GH#20724
        base = datetime(2015, 11, 1, tzinfo=gettz("US/Pacific"))
        idxs = [base + timedelta(seconds=i * 900) for i in range(16)]
        result = Series([0], index=[idxs[0]])
        for ts in idxs:
            result.loc[ts] = 1
        expected = Series(1, index=idxs)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "conv",
        [
            lambda x: x,
            lambda x: x.to_datetime64(),
            lambda x: x.to_pydatetime(),
            lambda x: np.datetime64(x),
        ],
        ids=["self", "to_datetime64", "to_pydatetime", "np.datetime64"],
    )
    def test_loc_setitem_datetime_keys_cast(self, conv, using_infer_string):
        # GH#9516, GH#51363 changed in 3.0 to not cast on Index.insert
        dt1 = Timestamp("20130101 09:00:00")
        dt2 = Timestamp("20130101 10:00:00")
        df = DataFrame()
        df.loc[conv(dt1), "one"] = 100
        df.loc[conv(dt2), "one"] = 200

        # the dtype constructed by Index([..]) does not yet follow the unit
        # of the input on 2.3.x -> so checking this is datetime64, but then
        # specifying the exact dtype in the expected result
        if using_infer_string:
            assert df.index.dtype.kind == "M"
            exp_dtype = df.index.dtype
        else:
            exp_dtype = "datetime64[ns]"
        expected = DataFrame(
            {"one": [100.0, 200.0]},
            index=Index([dt1, dt2], dtype=exp_dtype),
            columns=Index(["one"]),
        )
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_categorical_column_retains_dtype(self, ordered):
        # GH16360
        result = DataFrame({"A": [1]})
        result.loc[:, "B"] = Categorical(["b"], ordered=ordered)
        expected = DataFrame({"A": [1], "B": Categorical(["b"], ordered=ordered)})
        tm.assert_frame_equal(result, expected)

    def test_loc_setitem_with_expansion_and_existing_dst(self):
        # GH#18308
        start = Timestamp("2017-10-29 00:00:00+0200", tz="Europe/Madrid")
        end = Timestamp("2017-10-29 03:00:00+0100", tz="Europe/Madrid")
        ts = Timestamp("2016-10-10 03:00:00", tz="Europe/Madrid")
        idx = date_range(start, end, inclusive="left", freq="h")
        assert ts not in idx  # i.e. result.loc setitem is with-expansion

        result = DataFrame(index=idx, columns=["value"])
        result.loc[ts, "value"] = 12
        expected = DataFrame(
            [np.nan] * len(idx) + [12],
            index=idx.append(DatetimeIndex([ts])),
            columns=["value"],
            dtype=object,
        )
        tm.assert_frame_equal(result, expected)

    def test_setitem_with_expansion(self):
        # indexing - setting an element
        df = DataFrame(
            data=to_datetime(["2015-03-30 20:12:32", "2015-03-12 00:11:11"]),
            columns=["time"],
        )
        df["new_col"] = ["new", "old"]
        df.time = df.set_index("time").index.tz_localize("UTC")
        v = df[df.new_col == "new"].set_index("time").index.tz_convert("US/Pacific")

        # pre-2.0  trying to set a single element on a part of a different
        #  timezone converted to object; in 2.0 it retains dtype
        df2 = df.copy()
        df2.loc[df2.new_col == "new", "time"] = v

        expected = Series([v[0].tz_convert("UTC"), df.loc[1, "time"]], name="time")
        tm.assert_series_equal(df2.time, expected)

        v = df.loc[df.new_col == "new", "time"] + Timedelta("1s")
        df.loc[df.new_col == "new", "time"] = v
        tm.assert_series_equal(df.loc[df.new_col == "new", "time"], v)

    def test_loc_setitem_with_expansion_inf_upcast_empty(self):
        # Test with np.inf in columns
        df = DataFrame()
        df.loc[0, 0] = 1
        df.loc[1, 1] = 2
        df.loc[0, np.inf] = 3

        result = df.columns
        expected = Index([0, 1, np.inf], dtype=np.float64)
        tm.assert_index_equal(result, expected)

    @pytest.mark.filterwarnings("ignore:indexing past lexsort depth")
    @pytest.mark.parametrize("has_ref", [True, False])
    def test_loc_setitem_with_expansion_nonunique_index(self, index, has_ref):
        # GH#40096
        if not len(index):
            pytest.skip("Not relevant for empty Index")

        index = index.repeat(2)  # ensure non-unique
        N = len(index)
        arr = np.arange(N).astype(np.int64)

        orig = DataFrame(arr, index=index, columns=[0])

        # key that will requiring object-dtype casting in the index
        key = "kapow"
        assert key not in index  # otherwise test is invalid
        # TODO: using a tuple key breaks here in many cases

        exp_index = index.insert(len(index), key)
        if isinstance(index, MultiIndex):
            assert exp_index[-1][0] == key
        else:
            assert exp_index[-1] == key
        exp_data = np.arange(N + 1).astype(np.float64)
        expected = DataFrame(exp_data, index=exp_index, columns=[0])

        # Add new row, but no new columns
        df = orig.copy()
        if has_ref:
            view = df[:]
        df.loc[key, 0] = N
        tm.assert_frame_equal(df, expected)

        # add new row on a Series
        ser = orig.copy()[0]
        if has_ref:
            view = ser[:]
        ser.loc[key] = N
        # the series machinery lets us preserve int dtype instead of float
        expected = expected[0].astype(np.int64)
        tm.assert_series_equal(ser, expected)

        # add new row and new column
        df = orig.copy()
        if has_ref:
            view = df[:]  # noqa: F841
        df.loc[key, 1] = N
        expected = DataFrame(
            {0: list(arr) + [np.nan], 1: [np.nan] * N + [float(N)]},
            index=exp_index,
        )
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "dtype", ["Int32", "Int64", "UInt32", "UInt64", "Float32", "Float64"]
    )
    def test_loc_setitem_with_expansion_preserves_nullable_int(self, dtype):
        # GH#42099
        ser = Series([0, 1, 2, 3], dtype=dtype)
        df = DataFrame({"data": ser})

        result = DataFrame(index=df.index)
        result.loc[df.index, "data"] = ser

        tm.assert_frame_equal(result, df, check_column_type=False)

        result = DataFrame(index=df.index)
        result.loc[df.index, "data"] = ser._values
        tm.assert_frame_equal(result, df, check_column_type=False)

    def test_loc_setitem_ea_not_full_column(self):
        # GH#39163
        df = DataFrame({"A": range(5)})

        val = date_range("2016-01-01", periods=3, tz="US/Pacific")

        df.loc[[0, 1, 2], "B"] = val

        bex = val.append(DatetimeIndex([pd.NaT, pd.NaT], dtype=val.dtype))
        expected = DataFrame({"A": range(5), "B": bex})
        assert expected.dtypes["B"] == val.dtype
        tm.assert_frame_equal(df, expected)


class TestLocCallable:
    def test_frame_loc_getitem_callable(self):
        # GH#11485
        df = DataFrame({"A": [1, 2, 3, 4], "B": list("aabb"), "C": [1, 2, 3, 4]})
        # iloc cannot use boolean Series (see GH3635)

        # return bool indexer
        res = df.loc[lambda x: x.A > 2]
        tm.assert_frame_equal(res, df.loc[df.A > 2])

        res = df.loc[lambda x: x.B == "b", :]
        tm.assert_frame_equal(res, df.loc[df.B == "b", :])

        res = df.loc[lambda x: x.A > 2, lambda x: x.columns == "B"]
        tm.assert_frame_equal(res, df.loc[df.A > 2, [False, True, False]])

        res = df.loc[lambda x: x.A > 2, lambda x: "B"]
        tm.assert_series_equal(res, df.loc[df.A > 2, "B"])

        res = df.loc[lambda x: x.A > 2, lambda x: ["A", "B"]]
        tm.assert_frame_equal(res, df.loc[df.A > 2, ["A", "B"]])

        res = df.loc[lambda x: x.A == 2, lambda x: ["A", "B"]]
        tm.assert_frame_equal(res, df.loc[df.A == 2, ["A", "B"]])

        # scalar
        res = df.loc[lambda x: 1, lambda x: "A"]
        assert res == df.loc[1, "A"]

    def test_frame_loc_getitem_callable_mixture(self):
        # GH#11485
        df = DataFrame({"A": [1, 2, 3, 4], "B": list("aabb"), "C": [1, 2, 3, 4]})

        res = df.loc[lambda x: x.A > 2, ["A", "B"]]
        tm.assert_frame_equal(res, df.loc[df.A > 2, ["A", "B"]])

        res = df.loc[[2, 3], lambda x: ["A", "B"]]
        tm.assert_frame_equal(res, df.loc[[2, 3], ["A", "B"]])

        res = df.loc[3, lambda x: ["A", "B"]]
        tm.assert_series_equal(res, df.loc[3, ["A", "B"]])

    def test_frame_loc_getitem_callable_labels(self):
        # GH#11485
        df = DataFrame({"X": [1, 2, 3, 4], "Y": list("aabb")}, index=list("ABCD"))

        # return label
        res = df.loc[lambda x: ["A", "C"]]
        tm.assert_frame_equal(res, df.loc[["A", "C"]])

        res = df.loc[lambda x: ["A", "C"], :]
        tm.assert_frame_equal(res, df.loc[["A", "C"], :])

        res = df.loc[lambda x: ["A", "C"], lambda x: "X"]
        tm.assert_series_equal(res, df.loc[["A", "C"], "X"])

        res = df.loc[lambda x: ["A", "C"], lambda x: ["X"]]
        tm.assert_frame_equal(res, df.loc[["A", "C"], ["X"]])

        # mixture
        res = df.loc[["A", "C"], lambda x: "X"]
        tm.assert_series_equal(res, df.loc[["A", "C"], "X"])

        res = df.loc[["A", "C"], lambda x: ["X"]]
        tm.assert_frame_equal(res, df.loc[["A", "C"], ["X"]])

        res = df.loc[lambda x: ["A", "C"], "X"]
        tm.assert_series_equal(res, df.loc[["A", "C"], "X"])

        res = df.loc[lambda x: ["A", "C"], ["X"]]
        tm.assert_frame_equal(res, df.loc[["A", "C"], ["X"]])

    def test_frame_loc_setitem_callable(self):
        # GH#11485
        df = DataFrame(
            {"X": [1, 2, 3, 4], "Y": Series(list("aabb"), dtype=object)},
            index=list("ABCD"),
        )

        # return label
        res = df.copy()
        res.loc[lambda x: ["A", "C"]] = -20
        exp = df.copy()
        exp.loc[["A", "C"]] = -20
        tm.assert_frame_equal(res, exp)

        res = df.copy()
        res.loc[lambda x: ["A", "C"], :] = 20
        exp = df.copy()
        exp.loc[["A", "C"], :] = 20
        tm.assert_frame_equal(res, exp)

        res = df.copy()
        res.loc[lambda x: ["A", "C"], lambda x: "X"] = -1
        exp = df.copy()
        exp.loc[["A", "C"], "X"] = -1
        tm.assert_frame_equal(res, exp)

        res = df.copy()
        res.loc[lambda x: ["A", "C"], lambda x: ["X"]] = [5, 10]
        exp = df.copy()
        exp.loc[["A", "C"], ["X"]] = [5, 10]
        tm.assert_frame_equal(res, exp)

        # mixture
        res = df.copy()
        res.loc[["A", "C"], lambda x: "X"] = np.array([-1, -2])
        exp = df.copy()
        exp.loc[["A", "C"], "X"] = np.array([-1, -2])
        tm.assert_frame_equal(res, exp)

        res = df.copy()
        res.loc[["A", "C"], lambda x: ["X"]] = 10
        exp = df.copy()
        exp.loc[["A", "C"], ["X"]] = 10
        tm.assert_frame_equal(res, exp)

        res = df.copy()
        res.loc[lambda x: ["A", "C"], "X"] = -2
        exp = df.copy()
        exp.loc[["A", "C"], "X"] = -2
        tm.assert_frame_equal(res, exp)

        res = df.copy()
        res.loc[lambda x: ["A", "C"], ["X"]] = -4
        exp = df.copy()
        exp.loc[["A", "C"], ["X"]] = -4
        tm.assert_frame_equal(res, exp)


class TestPartialStringSlicing:
    def test_loc_getitem_partial_string_slicing_datetimeindex(self):
        # GH#35509
        df = DataFrame(
            {"col1": ["a", "b", "c"], "col2": [1, 2, 3]},
            index=to_datetime(["2020-08-01", "2020-07-02", "2020-08-05"]),
        )
        expected = DataFrame(
            {"col1": ["a", "c"], "col2": [1, 3]},
            index=to_datetime(["2020-08-01", "2020-08-05"]),
        )
        result = df.loc["2020-08"]
        tm.assert_frame_equal(result, expected)

    def test_loc_getitem_partial_string_slicing_with_periodindex(self):
        pi = pd.period_range(start="2017-01-01", end="2018-01-01", freq="M")
        ser = pi.to_series()
        result = ser.loc[:"2017-12"]
        expected = ser.iloc[:-1]

        tm.assert_series_equal(result, expected)

    def test_loc_getitem_partial_string_slicing_with_timedeltaindex(self):
        ix = timedelta_range(start="1 day", end="2 days", freq="1h")
        ser = ix.to_series()
        result = ser.loc[:"1 days"]
        expected = ser.iloc[:-1]

        tm.assert_series_equal(result, expected)

    def test_loc_getitem_str_timedeltaindex(self):
        # GH#16896
        df = DataFrame({"x": range(3)}, index=to_timedelta(range(3), unit="days"))
        expected = df.iloc[0]
        sliced = df.loc["0 days"]
        tm.assert_series_equal(sliced, expected)

    @pytest.mark.parametrize("indexer_end", [None, "2020-01-02 23:59:59.999999999"])
    def test_loc_getitem_partial_slice_non_monotonicity(
        self, tz_aware_fixture, indexer_end, frame_or_series
    ):
        # GH#33146
        obj = frame_or_series(
            [1] * 5,
            index=DatetimeIndex(
                [
                    Timestamp("2019-12-30"),
                    Timestamp("2020-01-01"),
                    Timestamp("2019-12-25"),
                    Timestamp("2020-01-02 23:59:59.999999999"),
                    Timestamp("2019-12-19"),
                ],
                tz=tz_aware_fixture,
            ),
        )
        expected = frame_or_series(
            [1] * 2,
            index=DatetimeIndex(
                [
                    Timestamp("2020-01-01"),
                    Timestamp("2020-01-02 23:59:59.999999999"),
                ],
                tz=tz_aware_fixture,
            ),
        )
        indexer = slice("2020-01-01", indexer_end)

        result = obj[indexer]
        tm.assert_equal(result, expected)

        result = obj.loc[indexer]
        tm.assert_equal(result, expected)


class TestLabelSlicing:
    def test_loc_getitem_slicing_datetimes_frame(self):
        # GH#7523

        # unique
        df_unique = DataFrame(
            np.arange(4.0, dtype="float64"),
            index=[datetime(2001, 1, i, 10, 00) for i in [1, 2, 3, 4]],
        )

        # duplicates
        df_dups = DataFrame(
            np.arange(5.0, dtype="float64"),
            index=[datetime(2001, 1, i, 10, 00) for i in [1, 2, 2, 3, 4]],
        )

        for df in [df_unique, df_dups]:
            result = df.loc[datetime(2001, 1, 1, 10) :]
            tm.assert_frame_equal(result, df)
            result = df.loc[: datetime(2001, 1, 4, 10)]
            tm.assert_frame_equal(result, df)
            result = df.loc[datetime(2001, 1, 1, 10) : datetime(2001, 1, 4, 10)]
            tm.assert_frame_equal(result, df)

            result = df.loc[datetime(2001, 1, 1, 11) :]
            expected = df.iloc[1:]
            tm.assert_frame_equal(result, expected)
            result = df.loc["20010101 11":]
            tm.assert_frame_equal(result, expected)

    def test_loc_getitem_label_slice_across_dst(self):
        # GH#21846
        idx = date_range(
            "2017-10-29 01:30:00", tz="Europe/Berlin", periods=5, freq="30 min"
        )
        series2 = Series([0, 1, 2, 3, 4], index=idx)

        t_1 = Timestamp("2017-10-29 02:30:00+02:00", tz="Europe/Berlin")
        t_2 = Timestamp("2017-10-29 02:00:00+01:00", tz="Europe/Berlin")
        result = series2.loc[t_1:t_2]
        expected = Series([2, 3], index=idx[2:4])
        tm.assert_series_equal(result, expected)

        result = series2[t_1]
        expected = 2
        assert result == expected

    @pytest.mark.parametrize(
        "index",
        [
            pd.period_range(start="2017-01-01", end="2018-01-01", freq="M"),
            timedelta_range(start="1 day", end="2 days", freq="1h"),
        ],
    )
    def test_loc_getitem_label_slice_period_timedelta(self, index):
        ser = index.to_series()
        result = ser.loc[: index[-2]]
        expected = ser.iloc[:-1]

        tm.assert_series_equal(result, expected)

    def test_loc_getitem_slice_floats_inexact(self):
        index = [52195.504153, 52196.303147, 52198.369883]
        df = DataFrame(np.random.default_rng(2).random((3, 2)), index=index)

        s1 = df.loc[52195.1:52196.5]
        assert len(s1) == 2

        s1 = df.loc[52195.1:52196.6]
        assert len(s1) == 2

        s1 = df.loc[52195.1:52198.9]
        assert len(s1) == 3

    def test_loc_getitem_float_slice_floatindex(self, float_numpy_dtype):
        dtype = float_numpy_dtype
        ser = Series(
            np.random.default_rng(2).random(10), index=np.arange(10, 20, dtype=dtype)
        )

        assert len(ser.loc[12.0:]) == 8
        assert len(ser.loc[12.5:]) == 7

        idx = np.arange(10, 20, dtype=dtype)
        idx[2] = 12.2
        ser.index = idx
        assert len(ser.loc[12.0:]) == 8
        assert len(ser.loc[12.5:]) == 7

    @pytest.mark.parametrize(
        "start,stop, expected_slice",
        [
            [np.timedelta64(0, "ns"), None, slice(0, 11)],
            [np.timedelta64(1, "D"), np.timedelta64(6, "D"), slice(1, 7)],
            [None, np.timedelta64(4, "D"), slice(0, 5)],
        ],
    )
    def test_loc_getitem_slice_label_td64obj(self, start, stop, expected_slice):
        # GH#20393
        ser = Series(range(11), timedelta_range("0 days", "10 days"))
        result = ser.loc[slice(start, stop)]
        expected = ser.iloc[expected_slice]
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize("start", ["2018", "2020"])
    def test_loc_getitem_slice_unordered_dt_index(self, frame_or_series, start):
        obj = frame_or_series(
            [1, 2, 3],
            index=[Timestamp("2016"), Timestamp("2019"), Timestamp("2017")],
        )
        with pytest.raises(
            KeyError, match="Value based partial slicing on non-monotonic"
        ):
            obj.loc[start:"2022"]

    @pytest.mark.parametrize("value", [1, 1.5])
    def test_loc_getitem_slice_labels_int_in_object_index(self, frame_or_series, value):
        # GH: 26491
        obj = frame_or_series(range(4), index=[value, "first", 2, "third"])
        result = obj.loc[value:"third"]
        expected = frame_or_series(range(4), index=[value, "first", 2, "third"])
        tm.assert_equal(result, expected)

    def test_loc_getitem_slice_columns_mixed_dtype(self):
        # GH: 20975
        df = DataFrame({"test": 1, 1: 2, 2: 3}, index=[0])
        expected = DataFrame(
            data=[[2, 3]], index=[0], columns=Index([1, 2], dtype=object)
        )
        tm.assert_frame_equal(df.loc[:, 1:], expected)


class TestLocBooleanLabelsAndSlices:
    @pytest.mark.parametrize("bool_value", [True, False])
    def test_loc_bool_incompatible_index_raises(
        self, index, frame_or_series, bool_value
    ):
        # GH20432
        message = f"{bool_value}: boolean label can not be used without a boolean index"
        if index.inferred_type != "boolean":
            obj = frame_or_series(index=index, dtype="object")
            with pytest.raises(KeyError, match=message):
                obj.loc[bool_value]

    @pytest.mark.parametrize("bool_value", [True, False])
    def test_loc_bool_should_not_raise(self, frame_or_series, bool_value):
        obj = frame_or_series(
            index=Index([True, False], dtype="boolean"), dtype="object"
        )
        obj.loc[bool_value]

    def test_loc_bool_slice_raises(self, index, frame_or_series):
        # GH20432
        message = (
            r"slice\(True, False, None\): boolean values can not be used in a slice"
        )
        obj = frame_or_series(index=index, dtype="object")
        with pytest.raises(TypeError, match=message):
            obj.loc[True:False]


class TestLocBooleanMask:
    def test_loc_setitem_bool_mask_timedeltaindex(self):
        # GH#14946
        df = DataFrame({"x": range(10)})
        df.index = to_timedelta(range(10), unit="s")
        conditions = [df["x"] > 3, df["x"] == 3, df["x"] < 3]
        expected_data = [
            [0, 1, 2, 3, 10, 10, 10, 10, 10, 10],
            [0, 1, 2, 10, 4, 5, 6, 7, 8, 9],
            [10, 10, 10, 3, 4, 5, 6, 7, 8, 9],
        ]
        for cond, data in zip(conditions, expected_data):
            result = df.copy()
            result.loc[cond, "x"] = 10

            expected = DataFrame(
                data,
                index=to_timedelta(range(10), unit="s"),
                columns=["x"],
                dtype="int64",
            )
            tm.assert_frame_equal(expected, result)

    @pytest.mark.parametrize("tz", [None, "UTC"])
    def test_loc_setitem_mask_with_datetimeindex_tz(self, tz):
        # GH#16889
        # support .loc with alignment and tz-aware DatetimeIndex
        mask = np.array([True, False, True, False])

        idx = date_range("20010101", periods=4, tz=tz)
        df = DataFrame({"a": np.arange(4)}, index=idx).astype("float64")

        result = df.copy()
        result.loc[mask, :] = df.loc[mask, :]
        tm.assert_frame_equal(result, df)

        result = df.copy()
        result.loc[mask] = df.loc[mask]
        tm.assert_frame_equal(result, df)

    def test_loc_setitem_mask_and_label_with_datetimeindex(self):
        # GH#9478
        # a datetimeindex alignment issue with partial setting
        df = DataFrame(
            np.arange(6.0).reshape(3, 2),
            columns=list("AB"),
            index=date_range("1/1/2000", periods=3, freq="1h"),
        )
        expected = df.copy()
        expected["C"] = [expected.index[0]] + [pd.NaT, pd.NaT]

        mask = df.A < 1
        df.loc[mask, "C"] = df.loc[mask].index
        tm.assert_frame_equal(df, expected)

    def test_loc_setitem_mask_td64_series_value(self):
        # GH#23462 key list of bools, value is a Series
        td1 = Timedelta(0)
        td2 = Timedelta(28767471428571405)
        df = DataFrame({"col": Series([td1, td2])})
        df_copy = df.copy()
        ser = Series([td1])

        expected = df["col"].iloc[1]._value
        df.loc[[True, False]] = ser
        result = df["col"].iloc[1]._value

        assert expected == result
        tm.assert_frame_equal(df, df_copy)

    @td.skip_array_manager_invalid_test  # TODO(ArrayManager) rewrite not using .values
    def test_loc_setitem_boolean_and_column(self, float_frame):
        expected = float_frame.copy()
        mask = float_frame["A"] > 0

        float_frame.loc[mask, "B"] = 0

        values = expected.values.copy()
        values[mask.values, 1] = 0
        expected = DataFrame(values, index=expected.index, columns=expected.columns)
        tm.assert_frame_equal(float_frame, expected)

    def test_loc_setitem_ndframe_values_alignment(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # GH#45501
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df.loc[[False, False, True], ["a"]] = DataFrame(
            {"a": [10, 20, 30]}, index=[2, 1, 0]
        )

        expected = DataFrame({"a": [1, 2, 10], "b": [4, 5, 6]})
        tm.assert_frame_equal(df, expected)

        # same thing with Series RHS
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df.loc[[False, False, True], ["a"]] = Series([10, 11, 12], index=[2, 1, 0])
        tm.assert_frame_equal(df, expected)

        # same thing but setting "a" instead of ["a"]
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df.loc[[False, False, True], "a"] = Series([10, 11, 12], index=[2, 1, 0])
        tm.assert_frame_equal(df, expected)

        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df_orig = df.copy()
        ser = df["a"]
        with tm.assert_cow_warning(warn_copy_on_write):
            ser.loc[[False, False, True]] = Series([10, 11, 12], index=[2, 1, 0])
        if using_copy_on_write:
            tm.assert_frame_equal(df, df_orig)
        else:
            tm.assert_frame_equal(df, expected)

    def test_loc_indexer_empty_broadcast(self):
        # GH#51450
        df = DataFrame({"a": [], "b": []}, dtype=object)
        expected = df.copy()
        df.loc[np.array([], dtype=np.bool_), ["a"]] = df["a"].copy()
        tm.assert_frame_equal(df, expected)

    def test_loc_indexer_all_false_broadcast(self):
        # GH#51450
        df = DataFrame({"a": ["x"], "b": ["y"]}, dtype=object)
        expected = df.copy()
        df.loc[np.array([False], dtype=np.bool_), ["a"]] = df["b"].copy()
        tm.assert_frame_equal(df, expected)

    def test_loc_indexer_length_one(self):
        # GH#51435
        df = DataFrame({"a": ["x"], "b": ["y"]}, dtype=object)
        expected = DataFrame({"a": ["y"], "b": ["y"]}, dtype=object)
        df.loc[np.array([True], dtype=np.bool_), ["a"]] = df["b"].copy()
        tm.assert_frame_equal(df, expected)


class TestLocListlike:
    @pytest.mark.parametrize("box", [lambda x: x, np.asarray, list])
    def test_loc_getitem_list_of_labels_categoricalindex_with_na(self, box):
        # passing a list can include valid categories _or_ NA values
        ci = CategoricalIndex(["A", "B", np.nan])
        ser = Series(range(3), index=ci)

        result = ser.loc[box(ci)]
        tm.assert_series_equal(result, ser)

        result = ser[box(ci)]
        tm.assert_series_equal(result, ser)

        result = ser.to_frame().loc[box(ci)]
        tm.assert_frame_equal(result, ser.to_frame())

        ser2 = ser[:-1]
        ci2 = ci[1:]
        # but if there are no NAs present, this should raise KeyError
        msg = "not in index"
        with pytest.raises(KeyError, match=msg):
            ser2.loc[box(ci2)]

        with pytest.raises(KeyError, match=msg):
            ser2[box(ci2)]

        with pytest.raises(KeyError, match=msg):
            ser2.to_frame().loc[box(ci2)]

    def test_loc_getitem_series_label_list_missing_values(self):
        # gh-11428
        key = np.array(
            ["2001-01-04", "2001-01-02", "2001-01-04", "2001-01-14"], dtype="datetime64"
        )
        ser = Series([2, 5, 8, 11], date_range("2001-01-01", freq="D", periods=4))
        with pytest.raises(KeyError, match="not in index"):
            ser.loc[key]

    def test_loc_getitem_series_label_list_missing_integer_values(self):
        # GH: 25927
        ser = Series(
            index=np.array([9730701000001104, 10049011000001109]),
            data=np.array([999000011000001104, 999000011000001104]),
        )
        with pytest.raises(KeyError, match="not in index"):
            ser.loc[np.array([9730701000001104, 10047311000001102])]

    @pytest.mark.parametrize("to_period", [True, False])
    def test_loc_getitem_listlike_of_datetimelike_keys(self, to_period):
        # GH#11497

        idx = date_range("2011-01-01", "2011-01-02", freq="D", name="idx")
        if to_period:
            idx = idx.to_period("D")
        ser = Series([0.1, 0.2], index=idx, name="s")

        keys = [Timestamp("2011-01-01"), Timestamp("2011-01-02")]
        if to_period:
            keys = [x.to_period("D") for x in keys]
        result = ser.loc[keys]
        exp = Series([0.1, 0.2], index=idx, name="s")
        if not to_period:
            exp.index = exp.index._with_freq(None)
        tm.assert_series_equal(result, exp, check_index_type=True)

        keys = [
            Timestamp("2011-01-02"),
            Timestamp("2011-01-02"),
            Timestamp("2011-01-01"),
        ]
        if to_period:
            keys = [x.to_period("D") for x in keys]
        exp = Series(
            [0.2, 0.2, 0.1], index=Index(keys, name="idx", dtype=idx.dtype), name="s"
        )
        result = ser.loc[keys]
        tm.assert_series_equal(result, exp, check_index_type=True)

        keys = [
            Timestamp("2011-01-03"),
            Timestamp("2011-01-02"),
            Timestamp("2011-01-03"),
        ]
        if to_period:
            keys = [x.to_period("D") for x in keys]

        with pytest.raises(KeyError, match="not in index"):
            ser.loc[keys]

    def test_loc_named_index(self):
        # GH 42790
        df = DataFrame(
            [[1, 2], [4, 5], [7, 8]],
            index=["cobra", "viper", "sidewinder"],
            columns=["max_speed", "shield"],
        )
        expected = df.iloc[:2]
        expected.index.name = "foo"
        result = df.loc[Index(["cobra", "viper"], name="foo")]
        tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "columns, column_key, expected_columns",
    [
        ([2011, 2012, 2013], [2011, 2012], [0, 1]),
        ([2011, 2012, "All"], [2011, 2012], [0, 1]),
        ([2011, 2012, "All"], [2011, "All"], [0, 2]),
    ],
)
def test_loc_getitem_label_list_integer_labels(columns, column_key, expected_columns):
    # gh-14836
    df = DataFrame(
        np.random.default_rng(2).random((3, 3)), columns=columns, index=list("ABC")
    )
    expected = df.iloc[:, expected_columns]
    result = df.loc[["A", "B", "C"], column_key]

    tm.assert_frame_equal(result, expected, check_column_type=True)


def test_loc_setitem_float_intindex():
    # GH 8720
    rand_data = np.random.default_rng(2).standard_normal((8, 4))
    result = DataFrame(rand_data)
    result.loc[:, 0.5] = np.nan
    expected_data = np.hstack((rand_data, np.array([np.nan] * 8).reshape(8, 1)))
    expected = DataFrame(expected_data, columns=[0.0, 1.0, 2.0, 3.0, 0.5])
    tm.assert_frame_equal(result, expected)

    result = DataFrame(rand_data)
    result.loc[:, 0.5] = np.nan
    tm.assert_frame_equal(result, expected)


def test_loc_axis_1_slice():
    # GH 10586
    cols = [(yr, m) for yr in [2014, 2015] for m in [7, 8, 9, 10]]
    df = DataFrame(
        np.ones((10, 8)),
        index=tuple("ABCDEFGHIJ"),
        columns=MultiIndex.from_tuples(cols),
    )
    result = df.loc(axis=1)[(2014, 9):(2015, 8)]
    expected = DataFrame(
        np.ones((10, 4)),
        index=tuple("ABCDEFGHIJ"),
        columns=MultiIndex.from_tuples([(2014, 9), (2014, 10), (2015, 7), (2015, 8)]),
    )
    tm.assert_frame_equal(result, expected)


def test_loc_set_dataframe_multiindex():
    # GH 14592
    expected = DataFrame(
        "a", index=range(2), columns=MultiIndex.from_product([range(2), range(2)])
    )
    result = expected.copy()
    result.loc[0, [(0, 1)]] = result.loc[0, [(0, 1)]]
    tm.assert_frame_equal(result, expected)


def test_loc_mixed_int_float():
    # GH#19456
    ser = Series(range(2), Index([1, 2.0], dtype=object))

    result = ser.loc[1]
    assert result == 0


def test_loc_with_positional_slice_raises():
    # GH#31840
    ser = Series(range(4), index=["A", "B", "C", "D"])

    with pytest.raises(TypeError, match="Slicing a positional slice with .loc"):
        ser.loc[:3] = 2


def test_loc_slice_disallows_positional():
    # GH#16121, GH#24612, GH#31810
    dti = date_range("2016-01-01", periods=3)
    df = DataFrame(np.random.default_rng(2).random((3, 2)), index=dti)

    ser = df[0]

    msg = (
        "cannot do slice indexing on DatetimeIndex with these "
        r"indexers \[1\] of type int"
    )

    for obj in [df, ser]:
        with pytest.raises(TypeError, match=msg):
            obj.loc[1:3]

        with pytest.raises(TypeError, match="Slicing a positional slice with .loc"):
            # GH#31840 enforce incorrect behavior
            obj.loc[1:3] = 1

    with pytest.raises(TypeError, match=msg):
        df.loc[1:3, 1]

    with pytest.raises(TypeError, match="Slicing a positional slice with .loc"):
        # GH#31840 enforce incorrect behavior
        df.loc[1:3, 1] = 2


def test_loc_datetimelike_mismatched_dtypes():
    # GH#32650 dont mix and match datetime/timedelta/period dtypes

    df = DataFrame(
        np.random.default_rng(2).standard_normal((5, 3)),
        columns=["a", "b", "c"],
        index=date_range("2012", freq="h", periods=5),
    )
    # create dataframe with non-unique DatetimeIndex
    df = df.iloc[[0, 2, 2, 3]].copy()

    dti = df.index
    tdi = pd.TimedeltaIndex(dti.asi8)  # matching i8 values

    msg = r"None of \[TimedeltaIndex.* are in the \[index\]"
    with pytest.raises(KeyError, match=msg):
        df.loc[tdi]

    with pytest.raises(KeyError, match=msg):
        df["a"].loc[tdi]


def test_loc_with_period_index_indexer():
    # GH#4125
    idx = pd.period_range("2002-01", "2003-12", freq="M")
    df = DataFrame(np.random.default_rng(2).standard_normal((24, 10)), index=idx)
    tm.assert_frame_equal(df, df.loc[idx])
    tm.assert_frame_equal(df, df.loc[list(idx)])
    tm.assert_frame_equal(df, df.loc[list(idx)])
    tm.assert_frame_equal(df.iloc[0:5], df.loc[idx[0:5]])
    tm.assert_frame_equal(df, df.loc[list(idx)])


def test_loc_setitem_multiindex_timestamp():
    # GH#13831
    vals = np.random.default_rng(2).standard_normal((8, 6))
    idx = date_range("1/1/2000", periods=8)
    cols = ["A", "B", "C", "D", "E", "F"]
    exp = DataFrame(vals, index=idx, columns=cols)
    exp.loc[exp.index[1], ("A", "B")] = np.nan
    vals[1][0:2] = np.nan
    res = DataFrame(vals, index=idx, columns=cols)
    tm.assert_frame_equal(res, exp)


def test_loc_getitem_multiindex_tuple_level():
    # GH#27591
    lev1 = ["a", "b", "c"]
    lev2 = [(0, 1), (1, 0)]
    lev3 = [0, 1]
    cols = MultiIndex.from_product([lev1, lev2, lev3], names=["x", "y", "z"])
    df = DataFrame(6, index=range(5), columns=cols)

    # the lev2[0] here should be treated as a single label, not as a sequence
    #  of labels
    result = df.loc[:, (lev1[0], lev2[0], lev3[0])]

    # TODO: i think this actually should drop levels
    expected = df.iloc[:, :1]
    tm.assert_frame_equal(result, expected)

    alt = df.xs((lev1[0], lev2[0], lev3[0]), level=[0, 1, 2], axis=1)
    tm.assert_frame_equal(alt, expected)

    # same thing on a Series
    ser = df.iloc[0]
    expected2 = ser.iloc[:1]

    alt2 = ser.xs((lev1[0], lev2[0], lev3[0]), level=[0, 1, 2], axis=0)
    tm.assert_series_equal(alt2, expected2)

    result2 = ser.loc[lev1[0], lev2[0], lev3[0]]
    assert result2 == 6


def test_loc_getitem_nullable_index_with_duplicates():
    # GH#34497
    df = DataFrame(
        data=np.array([[1, 2, 3, 4], [5, 6, 7, 8], [1, 2, np.nan, np.nan]]).T,
        columns=["a", "b", "c"],
        dtype="Int64",
    )
    df2 = df.set_index("c")
    assert df2.index.dtype == "Int64"

    res = df2.loc[1]
    expected = Series([1, 5], index=df2.columns, dtype="Int64", name=1)
    tm.assert_series_equal(res, expected)

    # pd.NA and duplicates in an object-dtype Index
    df2.index = df2.index.astype(object)
    res = df2.loc[1]
    tm.assert_series_equal(res, expected)


@pytest.mark.parametrize("value", [300, np.uint16(300), np.int16(300)])
def test_loc_setitem_uint8_upcast(value):
    # GH#26049

    df = DataFrame([1, 2, 3, 4], columns=["col1"], dtype="uint8")
    with tm.assert_produces_warning(FutureWarning, match="item of incompatible dtype"):
        df.loc[2, "col1"] = value  # value that can't be held in uint8

    if np_version_gt2 and isinstance(value, np.int16):
        # Note, result type of uint8 + int16 is int16
        # in numpy < 2, though, numpy would inspect the
        # value and see that it could fit in an uint16, resulting in a uint16
        dtype = "int16"
    else:
        dtype = "uint16"

    expected = DataFrame([1, 2, 300, 4], columns=["col1"], dtype=dtype)
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize(
    "fill_val,exp_dtype",
    [
        (Timestamp("2022-01-06"), "datetime64[ns]"),
        (Timestamp("2022-01-07", tz="US/Eastern"), "datetime64[ns, US/Eastern]"),
    ],
)
def test_loc_setitem_using_datetimelike_str_as_index(fill_val, exp_dtype):
    data = ["2022-01-02", "2022-01-03", "2022-01-04", fill_val.date()]
    index = DatetimeIndex(data, tz=fill_val.tz, dtype=exp_dtype)
    df = DataFrame([10, 11, 12, 14], columns=["a"], index=index)
    # adding new row using an unexisting datetime-like str index
    df.loc["2022-01-08", "a"] = 13

    data.append("2022-01-08")
    expected_index = DatetimeIndex(data, dtype=exp_dtype)
    tm.assert_index_equal(df.index, expected_index, exact=True)


def test_loc_set_int_dtype():
    # GH#23326
    df = DataFrame([list("abc")])
    df.loc[:, "col1"] = 5

    expected = DataFrame({0: ["a"], 1: ["b"], 2: ["c"], "col1": [5]})
    tm.assert_frame_equal(df, expected)


@pytest.mark.filterwarnings(r"ignore:Period with BDay freq is deprecated:FutureWarning")
@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
def test_loc_periodindex_3_levels():
    # GH#24091
    p_index = PeriodIndex(
        ["20181101 1100", "20181101 1200", "20181102 1300", "20181102 1400"],
        name="datetime",
        freq="B",
    )
    mi_series = DataFrame(
        [["A", "B", 1.0], ["A", "C", 2.0], ["Z", "Q", 3.0], ["W", "F", 4.0]],
        index=p_index,
        columns=["ONE", "TWO", "VALUES"],
    )
    mi_series = mi_series.set_index(["ONE", "TWO"], append=True)["VALUES"]
    assert mi_series.loc[(p_index[0], "A", "B")] == 1.0


def test_loc_setitem_pyarrow_strings():
    # GH#52319
    pytest.importorskip("pyarrow")
    df = DataFrame(
        {
            "strings": Series(["A", "B", "C"], dtype="string[pyarrow]"),
            "ids": Series([True, True, False]),
        }
    )
    new_value = Series(["X", "Y"])
    df.loc[df.ids, "strings"] = new_value

    expected_df = DataFrame(
        {
            "strings": Series(["X", "Y", "C"], dtype="string[pyarrow]"),
            "ids": Series([True, True, False]),
        }
    )

    tm.assert_frame_equal(df, expected_df)


class TestLocSeries:
    @pytest.mark.parametrize("val,expected", [(2**63 - 1, 3), (2**63, 4)])
    def test_loc_uint64(self, val, expected):
        # see GH#19399
        ser = Series({2**63 - 1: 3, 2**63: 4})
        assert ser.loc[val] == expected

    def test_loc_getitem(self, string_series, datetime_series):
        inds = string_series.index[[3, 4, 7]]
        tm.assert_series_equal(string_series.loc[inds], string_series.reindex(inds))
        tm.assert_series_equal(string_series.iloc[5::2], string_series[5::2])

        # slice with indices
        d1, d2 = datetime_series.index[[5, 15]]
        result = datetime_series.loc[d1:d2]
        expected = datetime_series.truncate(d1, d2)
        tm.assert_series_equal(result, expected)

        # boolean
        mask = string_series > string_series.median()
        tm.assert_series_equal(string_series.loc[mask], string_series[mask])

        # ask for index value
        assert datetime_series.loc[d1] == datetime_series[d1]
        assert datetime_series.loc[d2] == datetime_series[d2]

    def test_loc_getitem_not_monotonic(self, datetime_series):
        d1, d2 = datetime_series.index[[5, 15]]

        ts2 = datetime_series[::2].iloc[[1, 2, 0]]

        msg = r"Timestamp\('2000-01-10 00:00:00'\)"
        with pytest.raises(KeyError, match=msg):
            ts2.loc[d1:d2]
        with pytest.raises(KeyError, match=msg):
            ts2.loc[d1:d2] = 0

    def test_loc_getitem_setitem_integer_slice_keyerrors(self):
        ser = Series(
            np.random.default_rng(2).standard_normal(10), index=list(range(0, 20, 2))
        )

        # this is OK
        cp = ser.copy()
        cp.iloc[4:10] = 0
        assert (cp.iloc[4:10] == 0).all()

        # so is this
        cp = ser.copy()
        cp.iloc[3:11] = 0
        assert (cp.iloc[3:11] == 0).values.all()

        result = ser.iloc[2:6]
        result2 = ser.loc[3:11]
        expected = ser.reindex([4, 6, 8, 10])

        tm.assert_series_equal(result, expected)
        tm.assert_series_equal(result2, expected)

        # non-monotonic, raise KeyError
        s2 = ser.iloc[list(range(5)) + list(range(9, 4, -1))]
        with pytest.raises(KeyError, match=r"^3$"):
            s2.loc[3:11]
        with pytest.raises(KeyError, match=r"^3$"):
            s2.loc[3:11] = 0

    def test_loc_getitem_iterator(self, string_series):
        idx = iter(string_series.index[:10])
        result = string_series.loc[idx]
        tm.assert_series_equal(result, string_series[:10])

    def test_loc_setitem_boolean(self, string_series):
        mask = string_series > string_series.median()

        result = string_series.copy()
        result.loc[mask] = 0
        expected = string_series
        expected[mask] = 0
        tm.assert_series_equal(result, expected)

    def test_loc_setitem_corner(self, string_series):
        inds = list(string_series.index[[5, 8, 12]])
        string_series.loc[inds] = 5
        msg = r"\['foo'\] not in index"
        with pytest.raises(KeyError, match=msg):
            string_series.loc[inds + ["foo"]] = 5

    def test_basic_setitem_with_labels(self, datetime_series):
        indices = datetime_series.index[[5, 10, 15]]

        cp = datetime_series.copy()
        exp = datetime_series.copy()
        cp[indices] = 0
        exp.loc[indices] = 0
        tm.assert_series_equal(cp, exp)

        cp = datetime_series.copy()
        exp = datetime_series.copy()
        cp[indices[0] : indices[2]] = 0
        exp.loc[indices[0] : indices[2]] = 0
        tm.assert_series_equal(cp, exp)

    def test_loc_setitem_listlike_of_ints(self):
        # integer indexes, be careful
        ser = Series(
            np.random.default_rng(2).standard_normal(10), index=list(range(0, 20, 2))
        )
        inds = [0, 4, 6]
        arr_inds = np.array([0, 4, 6])

        cp = ser.copy()
        exp = ser.copy()
        ser[inds] = 0
        ser.loc[inds] = 0
        tm.assert_series_equal(cp, exp)

        cp = ser.copy()
        exp = ser.copy()
        ser[arr_inds] = 0
        ser.loc[arr_inds] = 0
        tm.assert_series_equal(cp, exp)

        inds_notfound = [0, 4, 5, 6]
        arr_inds_notfound = np.array([0, 4, 5, 6])
        msg = r"\[5\] not in index"
        with pytest.raises(KeyError, match=msg):
            ser[inds_notfound] = 0
        with pytest.raises(Exception, match=msg):
            ser[arr_inds_notfound] = 0

    def test_loc_setitem_dt64tz_values(self):
        # GH#12089
        ser = Series(
            date_range("2011-01-01", periods=3, tz="US/Eastern"),
            index=["a", "b", "c"],
        )
        s2 = ser.copy()
        expected = Timestamp("2011-01-03", tz="US/Eastern")
        s2.loc["a"] = expected
        result = s2.loc["a"]
        assert result == expected

        s2 = ser.copy()
        s2.iloc[0] = expected
        result = s2.iloc[0]
        assert result == expected

        s2 = ser.copy()
        s2["a"] = expected
        result = s2["a"]
        assert result == expected

    @pytest.mark.parametrize("array_fn", [np.array, pd.array, list, tuple])
    @pytest.mark.parametrize("size", [0, 4, 5, 6])
    def test_loc_iloc_setitem_with_listlike(self, size, array_fn):
        # GH37748
        # testing insertion, in a Series of size N (here 5), of a listlike object
        # of size  0, N-1, N, N+1

        arr = array_fn([0] * size)
        expected = Series([arr, 0, 0, 0, 0], index=list("abcde"), dtype=object)

        ser = Series(0, index=list("abcde"), dtype=object)
        ser.loc["a"] = arr
        tm.assert_series_equal(ser, expected)

        ser = Series(0, index=list("abcde"), dtype=object)
        ser.iloc[0] = arr
        tm.assert_series_equal(ser, expected)

    @pytest.mark.parametrize("indexer", [IndexSlice["A", :], ("A", slice(None))])
    def test_loc_series_getitem_too_many_dimensions(self, indexer):
        # GH#35349
        ser = Series(
            index=MultiIndex.from_tuples([("A", "0"), ("A", "1"), ("B", "0")]),
            data=[21, 22, 23],
        )
        msg = "Too many indexers"
        with pytest.raises(IndexingError, match=msg):
            ser.loc[indexer, :]

        with pytest.raises(IndexingError, match=msg):
            ser.loc[indexer, :] = 1

    def test_loc_setitem(self, string_series):
        inds = string_series.index[[3, 4, 7]]

        result = string_series.copy()
        result.loc[inds] = 5

        expected = string_series.copy()
        expected.iloc[[3, 4, 7]] = 5
        tm.assert_series_equal(result, expected)

        result.iloc[5:10] = 10
        expected[5:10] = 10
        tm.assert_series_equal(result, expected)

        # set slice with indices
        d1, d2 = string_series.index[[5, 15]]
        result.loc[d1:d2] = 6
        expected[5:16] = 6  # because it's inclusive
        tm.assert_series_equal(result, expected)

        # set index value
        string_series.loc[d1] = 4
        string_series.loc[d2] = 6
        assert string_series[d1] == 4
        assert string_series[d2] == 6

    @pytest.mark.parametrize("dtype", ["object", "string"])
    def test_loc_assign_dict_to_row(self, dtype):
        # GH41044
        df = DataFrame({"A": ["abc", "def"], "B": ["ghi", "jkl"]}, dtype=dtype)
        df.loc[0, :] = {"A": "newA", "B": "newB"}

        expected = DataFrame({"A": ["newA", "def"], "B": ["newB", "jkl"]}, dtype=dtype)

        tm.assert_frame_equal(df, expected)

    @td.skip_array_manager_invalid_test
    def test_loc_setitem_dict_timedelta_multiple_set(self):
        # GH 16309
        result = DataFrame(columns=["time", "value"])
        result.loc[1] = {"time": Timedelta(6, unit="s"), "value": "foo"}
        result.loc[1] = {"time": Timedelta(6, unit="s"), "value": "foo"}
        expected = DataFrame(
            [[Timedelta(6, unit="s"), "foo"]], columns=["time", "value"], index=[1]
        )
        tm.assert_frame_equal(result, expected)

    def test_loc_set_multiple_items_in_multiple_new_columns(self):
        # GH 25594
        df = DataFrame(index=[1, 2], columns=["a"])
        df.loc[1, ["b", "c"]] = [6, 7]

        expected = DataFrame(
            {
                "a": Series([np.nan, np.nan], dtype="object"),
                "b": [6, np.nan],
                "c": [7, np.nan],
            },
            index=[1, 2],
        )

        tm.assert_frame_equal(df, expected)

    def test_getitem_loc_str_periodindex(self):
        # GH#33964
        msg = "Period with BDay freq is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            index = pd.period_range(start="2000", periods=20, freq="B")
            series = Series(range(20), index=index)
            assert series.loc["2000-01-14"] == 9

    def test_loc_nonunique_masked_index(self):
        # GH 57027
        ids = list(range(11))
        index = Index(ids * 1000, dtype="Int64")
        df = DataFrame({"val": np.arange(len(index), dtype=np.intp)}, index=index)
        result = df.loc[ids]
        expected = DataFrame(
            {"val": index.argsort(kind="stable").astype(np.intp)},
            index=Index(np.array(ids).repeat(1000), dtype="Int64"),
        )
        tm.assert_frame_equal(result, expected)
