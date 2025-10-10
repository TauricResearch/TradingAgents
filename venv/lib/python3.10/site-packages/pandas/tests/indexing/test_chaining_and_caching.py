from string import ascii_letters

import numpy as np
import pytest

from pandas.errors import (
    SettingWithCopyError,
    SettingWithCopyWarning,
)
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
    date_range,
    option_context,
)
import pandas._testing as tm

msg = "A value is trying to be set on a copy of a slice from a DataFrame"


def random_text(nobs=100):
    # Construct a DataFrame where each row is a random slice from 'letters'
    idxs = np.random.default_rng(2).integers(len(ascii_letters), size=(nobs, 2))
    idxs.sort(axis=1)
    strings = [ascii_letters[x[0] : x[1]] for x in idxs]

    return DataFrame(strings, columns=["letters"])


class TestCaching:
    def test_slice_consolidate_invalidate_item_cache(self, using_copy_on_write):
        # this is chained assignment, but will 'work'
        with option_context("chained_assignment", None):
            # #3970
            df = DataFrame({"aa": np.arange(5), "bb": [2.2] * 5})

            # Creates a second float block
            df["cc"] = 0.0

            # caches a reference to the 'bb' series
            df["bb"]

            # Assignment to wrong series
            with tm.raises_chained_assignment_error():
                df["bb"].iloc[0] = 0.17
            df._clear_item_cache()
            if not using_copy_on_write:
                tm.assert_almost_equal(df["bb"][0], 0.17)
            else:
                # with ArrayManager, parent is not mutated with chained assignment
                tm.assert_almost_equal(df["bb"][0], 2.2)

    @pytest.mark.parametrize("do_ref", [True, False])
    def test_setitem_cache_updating(self, do_ref):
        # GH 5424
        cont = ["one", "two", "three", "four", "five", "six", "seven"]

        df = DataFrame({"a": cont, "b": cont[3:] + cont[:3], "c": np.arange(7)})

        # ref the cache
        if do_ref:
            df.loc[0, "c"]

        # set it
        df.loc[7, "c"] = 1

        assert df.loc[0, "c"] == 0.0
        assert df.loc[7, "c"] == 1.0

    def test_setitem_cache_updating_slices(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # GH 7084
        # not updating cache on series setting with slices
        expected = DataFrame(
            {"A": [600, 600, 600]}, index=date_range("5/7/2014", "5/9/2014")
        )
        out = DataFrame({"A": [0, 0, 0]}, index=date_range("5/7/2014", "5/9/2014"))
        df = DataFrame({"C": ["A", "A", "A"], "D": [100, 200, 300]})

        # loop through df to update out
        six = Timestamp("5/7/2014")
        eix = Timestamp("5/9/2014")
        for ix, row in df.iterrows():
            out.loc[six:eix, row["C"]] = out.loc[six:eix, row["C"]] + row["D"]

        tm.assert_frame_equal(out, expected)
        tm.assert_series_equal(out["A"], expected["A"])

        # try via a chain indexing
        # this actually works
        out = DataFrame({"A": [0, 0, 0]}, index=date_range("5/7/2014", "5/9/2014"))
        out_original = out.copy()
        for ix, row in df.iterrows():
            v = out[row["C"]][six:eix] + row["D"]
            with tm.raises_chained_assignment_error(
                (ix == 0) or warn_copy_on_write or using_copy_on_write
            ):
                out[row["C"]][six:eix] = v

        if not using_copy_on_write:
            tm.assert_frame_equal(out, expected)
            tm.assert_series_equal(out["A"], expected["A"])
        else:
            tm.assert_frame_equal(out, out_original)
            tm.assert_series_equal(out["A"], out_original["A"])

        out = DataFrame({"A": [0, 0, 0]}, index=date_range("5/7/2014", "5/9/2014"))
        for ix, row in df.iterrows():
            out.loc[six:eix, row["C"]] += row["D"]

        tm.assert_frame_equal(out, expected)
        tm.assert_series_equal(out["A"], expected["A"])

    def test_altering_series_clears_parent_cache(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # GH #33675
        df = DataFrame([[1, 2], [3, 4]], index=["a", "b"], columns=["A", "B"])
        ser = df["A"]

        if using_copy_on_write or warn_copy_on_write:
            assert "A" not in df._item_cache
        else:
            assert "A" in df._item_cache

        # Adding a new entry to ser swaps in a new array, so "A" needs to
        #  be removed from df._item_cache
        ser["c"] = 5
        assert len(ser) == 3
        assert "A" not in df._item_cache
        assert df["A"] is not ser
        assert len(df["A"]) == 2


class TestChaining:
    def test_setitem_chained_setfault(self, using_copy_on_write):
        # GH6026
        data = ["right", "left", "left", "left", "right", "left", "timeout"]
        mdata = ["right", "left", "left", "left", "right", "left", "none"]

        df = DataFrame({"response": np.array(data)})
        mask = df.response == "timeout"
        with tm.raises_chained_assignment_error():
            df.response[mask] = "none"
        if using_copy_on_write:
            tm.assert_frame_equal(df, DataFrame({"response": data}))
        else:
            tm.assert_frame_equal(df, DataFrame({"response": mdata}))

        recarray = np.rec.fromarrays([data], names=["response"])
        df = DataFrame(recarray)
        mask = df.response == "timeout"
        with tm.raises_chained_assignment_error():
            df.response[mask] = "none"
        if using_copy_on_write:
            tm.assert_frame_equal(df, DataFrame({"response": data}))
        else:
            tm.assert_frame_equal(df, DataFrame({"response": mdata}))

        df = DataFrame({"response": data, "response1": data})
        df_original = df.copy()
        mask = df.response == "timeout"
        with tm.raises_chained_assignment_error():
            df.response[mask] = "none"
        if using_copy_on_write:
            tm.assert_frame_equal(df, df_original)
        else:
            tm.assert_frame_equal(df, DataFrame({"response": mdata, "response1": data}))

        # GH 6056
        expected = DataFrame({"A": [np.nan, "bar", "bah", "foo", "bar"]})
        df = DataFrame({"A": np.array(["foo", "bar", "bah", "foo", "bar"])})
        with tm.raises_chained_assignment_error():
            df["A"].iloc[0] = np.nan
        if using_copy_on_write:
            expected = DataFrame({"A": ["foo", "bar", "bah", "foo", "bar"]})
        else:
            expected = DataFrame({"A": [np.nan, "bar", "bah", "foo", "bar"]})
        result = df.head()
        tm.assert_frame_equal(result, expected)

        df = DataFrame({"A": np.array(["foo", "bar", "bah", "foo", "bar"])})
        with tm.raises_chained_assignment_error():
            df.A.iloc[0] = np.nan
        result = df.head()
        tm.assert_frame_equal(result, expected)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment(self, using_copy_on_write):
        with option_context("chained_assignment", "raise"):
            # work with the chain
            expected = DataFrame([[-5, 1], [-6, 3]], columns=list("AB"))
            df = DataFrame(
                np.arange(4).reshape(2, 2), columns=list("AB"), dtype="int64"
            )
            df_original = df.copy()
            assert df._is_copy is None

            with tm.raises_chained_assignment_error():
                df["A"][0] = -5
            with tm.raises_chained_assignment_error():
                df["A"][1] = -6
            if using_copy_on_write:
                tm.assert_frame_equal(df, df_original)
            else:
                tm.assert_frame_equal(df, expected)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_raises(
        self, using_array_manager, using_copy_on_write, warn_copy_on_write
    ):
        # test with the chaining
        df = DataFrame(
            {
                "A": Series(range(2), dtype="int64"),
                "B": np.array(np.arange(2, 4), dtype=np.float64),
            }
        )
        df_original = df.copy()
        assert df._is_copy is None

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df["A"][0] = -5
            with tm.raises_chained_assignment_error():
                df["A"][1] = -6
            tm.assert_frame_equal(df, df_original)
        elif warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df["A"][0] = -5
            with tm.raises_chained_assignment_error():
                df["A"][1] = np.nan
        elif not using_array_manager:
            with pytest.raises(SettingWithCopyError, match=msg):
                with tm.raises_chained_assignment_error():
                    df["A"][0] = -5

            with pytest.raises(SettingWithCopyError, match=msg):
                with tm.raises_chained_assignment_error():
                    df["A"][1] = np.nan

            assert df["A"]._is_copy is None
        else:
            # INFO(ArrayManager) for ArrayManager it doesn't matter that it's
            # a mixed dataframe
            df["A"][0] = -5
            df["A"][1] = -6
            expected = DataFrame([[-5, 2], [-6, 3]], columns=list("AB"))
            expected["B"] = expected["B"].astype("float64")
            tm.assert_frame_equal(df, expected)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_fails(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # Using a copy (the chain), fails
        df = DataFrame(
            {
                "A": Series(range(2), dtype="int64"),
                "B": np.array(np.arange(2, 4), dtype=np.float64),
            }
        )

        if using_copy_on_write or warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df.loc[0]["A"] = -5
        else:
            with pytest.raises(SettingWithCopyError, match=msg):
                df.loc[0]["A"] = -5

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_doc_example(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # Doc example
        df = DataFrame(
            {
                "a": ["one", "one", "two", "three", "two", "one", "six"],
                "c": Series(range(7), dtype="int64"),
            }
        )
        assert df._is_copy is None

        indexer = df.a.str.startswith("o")
        if using_copy_on_write or warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df[indexer]["c"] = 42
        else:
            with pytest.raises(SettingWithCopyError, match=msg):
                df[indexer]["c"] = 42

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_object_dtype(
        self, using_array_manager, using_copy_on_write, warn_copy_on_write
    ):
        expected = DataFrame({"A": [111, "bbb", "ccc"], "B": [1, 2, 3]})
        df = DataFrame(
            {"A": Series(["aaa", "bbb", "ccc"], dtype=object), "B": [1, 2, 3]}
        )
        df_original = df.copy()

        if not using_copy_on_write and not warn_copy_on_write:
            with pytest.raises(SettingWithCopyError, match=msg):
                df.loc[0]["A"] = 111

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df["A"][0] = 111
            tm.assert_frame_equal(df, df_original)
        elif warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df["A"][0] = 111
            tm.assert_frame_equal(df, expected)
        elif not using_array_manager:
            with pytest.raises(SettingWithCopyError, match=msg):
                with tm.raises_chained_assignment_error():
                    df["A"][0] = 111

            df.loc[0, "A"] = 111
            tm.assert_frame_equal(df, expected)
        else:
            # INFO(ArrayManager) for ArrayManager it doesn't matter that it's
            # a mixed dataframe
            df["A"][0] = 111
            tm.assert_frame_equal(df, expected)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_is_copy_pickle(self):
        # gh-5475: Make sure that is_copy is picked up reconstruction
        df = DataFrame({"A": [1, 2]})
        assert df._is_copy is None

        with tm.ensure_clean("__tmp__pickle") as path:
            df.to_pickle(path)
            df2 = pd.read_pickle(path)
            df2["B"] = df2["A"]
            df2["B"] = df2["A"]

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_setting_entire_column(self):
        # gh-5597: a spurious raise as we are setting the entire column here

        df = random_text(100000)

        # Always a copy
        x = df.iloc[[0, 1, 2]]
        assert x._is_copy is not None

        x = df.iloc[[0, 1, 2, 4]]
        assert x._is_copy is not None

        # Explicitly copy
        indexer = df.letters.apply(lambda x: len(x) > 10)
        df = df.loc[indexer].copy()

        assert df._is_copy is None
        df["letters"] = df["letters"].apply(str.lower)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_implicit_take(self):
        # Implicitly take
        df = random_text(100000)
        indexer = df.letters.apply(lambda x: len(x) > 10)
        df = df.loc[indexer]

        assert df._is_copy is not None
        df["letters"] = df["letters"].apply(str.lower)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_implicit_take2(
        self, using_copy_on_write, warn_copy_on_write
    ):
        if using_copy_on_write or warn_copy_on_write:
            pytest.skip("_is_copy is not always set for CoW")
        # Implicitly take 2
        df = random_text(100000)
        indexer = df.letters.apply(lambda x: len(x) > 10)

        df = df.loc[indexer]
        assert df._is_copy is not None
        df.loc[:, "letters"] = df["letters"].apply(str.lower)

        # with the enforcement of #45333 in 2.0, the .loc[:, letters] setting
        #  is inplace, so df._is_copy remains non-None.
        assert df._is_copy is not None

        df["letters"] = df["letters"].apply(str.lower)
        assert df._is_copy is None

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_str(self):
        df = random_text(100000)
        indexer = df.letters.apply(lambda x: len(x) > 10)
        df.loc[indexer, "letters"] = df.loc[indexer, "letters"].apply(str.lower)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_is_copy(self):
        # an identical take, so no copy
        df = DataFrame({"a": [1]}).dropna()
        assert df._is_copy is None
        df["a"] += 1

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_sorting(self):
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)))
        ser = df.iloc[:, 0].sort_values()

        tm.assert_series_equal(ser, df.iloc[:, 0].sort_values())
        tm.assert_series_equal(ser, df[0].sort_values())

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_false_positives(self):
        # see gh-6025: false positives
        df = DataFrame({"column1": ["a", "a", "a"], "column2": [4, 8, 9]})
        str(df)

        df["column1"] = df["column1"] + "b"
        str(df)

        df = df[df["column2"] != 8]
        str(df)

        df["column1"] = df["column1"] + "c"
        str(df)

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_undefined_column(
        self, using_copy_on_write, warn_copy_on_write
    ):
        # from SO:
        # https://stackoverflow.com/questions/24054495/potential-bug-setting-value-for-undefined-column-using-iloc
        df = DataFrame(np.arange(0, 9), columns=["count"])
        df["group"] = "b"
        df_original = df.copy()

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df.iloc[0:5]["group"] = "a"
            tm.assert_frame_equal(df, df_original)
        elif warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df.iloc[0:5]["group"] = "a"
        else:
            with pytest.raises(SettingWithCopyError, match=msg):
                with tm.raises_chained_assignment_error():
                    df.iloc[0:5]["group"] = "a"

    @pytest.mark.arm_slow
    def test_detect_chained_assignment_changing_dtype(
        self, using_array_manager, using_copy_on_write, warn_copy_on_write
    ):
        # Mixed type setting but same dtype & changing dtype
        df = DataFrame(
            {
                "A": date_range("20130101", periods=5),
                "B": np.random.default_rng(2).standard_normal(5),
                "C": np.arange(5, dtype="int64"),
                "D": ["a", "b", "c", "d", "e"],
            }
        )
        df_original = df.copy()

        if using_copy_on_write or warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df.loc[2]["D"] = "foo"
            with tm.raises_chained_assignment_error():
                df.loc[2]["C"] = "foo"
            tm.assert_frame_equal(df, df_original)
            with tm.raises_chained_assignment_error(extra_warnings=(FutureWarning,)):
                df["C"][2] = "foo"
            if using_copy_on_write:
                tm.assert_frame_equal(df, df_original)
            else:
                assert df.loc[2, "C"] == "foo"
        else:
            with pytest.raises(SettingWithCopyError, match=msg):
                df.loc[2]["D"] = "foo"

            with pytest.raises(SettingWithCopyError, match=msg):
                df.loc[2]["C"] = "foo"

            if not using_array_manager:
                with pytest.raises(SettingWithCopyError, match=msg):
                    with tm.raises_chained_assignment_error():
                        df["C"][2] = "foo"
            else:
                # INFO(ArrayManager) for ArrayManager it doesn't matter if it's
                # changing the dtype or not
                df["C"][2] = "foo"
                assert df.loc[2, "C"] == "foo"

    def test_setting_with_copy_bug(self, using_copy_on_write, warn_copy_on_write):
        # operating on a copy
        df = DataFrame(
            {"a": list(range(4)), "b": list("ab.."), "c": ["a", "b", np.nan, "d"]}
        )
        df_original = df.copy()
        mask = pd.isna(df.c)

        if using_copy_on_write:
            with tm.raises_chained_assignment_error():
                df[["c"]][mask] = df[["b"]][mask]
            tm.assert_frame_equal(df, df_original)
        elif warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df[["c"]][mask] = df[["b"]][mask]
        else:
            with pytest.raises(SettingWithCopyError, match=msg):
                df[["c"]][mask] = df[["b"]][mask]

    def test_setting_with_copy_bug_no_warning(self):
        # invalid warning as we are returning a new object
        # GH 8730
        df1 = DataFrame({"x": Series(["a", "b", "c"]), "y": Series(["d", "e", "f"])})
        df2 = df1[["x"]]

        # this should not raise
        df2["y"] = ["g", "h", "i"]

    def test_detect_chained_assignment_warnings_errors(
        self, using_copy_on_write, warn_copy_on_write
    ):
        df = DataFrame({"A": ["aaa", "bbb", "ccc"], "B": [1, 2, 3]})
        if using_copy_on_write or warn_copy_on_write:
            with tm.raises_chained_assignment_error():
                df.loc[0]["A"] = 111
            return

        with option_context("chained_assignment", "warn"):
            with tm.assert_produces_warning(SettingWithCopyWarning):
                df.loc[0]["A"] = 111

        with option_context("chained_assignment", "raise"):
            with pytest.raises(SettingWithCopyError, match=msg):
                df.loc[0]["A"] = 111

    @pytest.mark.parametrize("rhs", [3, DataFrame({0: [1, 2, 3, 4]})])
    def test_detect_chained_assignment_warning_stacklevel(
        self, rhs, using_copy_on_write, warn_copy_on_write
    ):
        # GH#42570
        df = DataFrame(np.arange(25).reshape(5, 5))
        df_original = df.copy()
        chained = df.loc[:3]
        with option_context("chained_assignment", "warn"):
            if not using_copy_on_write and not warn_copy_on_write:
                with tm.assert_produces_warning(SettingWithCopyWarning) as t:
                    chained[2] = rhs
                    assert t[0].filename == __file__
            else:
                # INFO(CoW) no warning, and original dataframe not changed
                chained[2] = rhs
                tm.assert_frame_equal(df, df_original)

    # TODO(ArrayManager) fast_xs with array-like scalars is not yet working
    @td.skip_array_manager_not_yet_implemented
    def test_chained_getitem_with_lists(self):
        # GH6394
        # Regression in chained getitem indexing with embedded list-like from
        # 0.12

        df = DataFrame({"A": 5 * [np.zeros(3)], "B": 5 * [np.ones(3)]})
        expected = df["A"].iloc[2]
        result = df.loc[2, "A"]
        tm.assert_numpy_array_equal(result, expected)
        result2 = df.iloc[2]["A"]
        tm.assert_numpy_array_equal(result2, expected)
        result3 = df["A"].loc[2]
        tm.assert_numpy_array_equal(result3, expected)
        result4 = df["A"].iloc[2]
        tm.assert_numpy_array_equal(result4, expected)

    def test_cache_updating(self):
        # GH 4939, make sure to update the cache on setitem

        df = DataFrame(
            np.zeros((10, 4)),
            columns=Index(list("ABCD"), dtype=object),
        )
        df["A"]  # cache series
        df.loc["Hello Friend"] = df.iloc[0]
        assert "Hello Friend" in df["A"].index
        assert "Hello Friend" in df["B"].index

    def test_cache_updating2(self, using_copy_on_write):
        # 10264
        df = DataFrame(
            np.zeros((5, 5), dtype="int64"),
            columns=["a", "b", "c", "d", "e"],
            index=range(5),
        )
        df["f"] = 0
        df_orig = df.copy()
        if using_copy_on_write:
            with pytest.raises(ValueError, match="read-only"):
                df.f.values[3] = 1
            tm.assert_frame_equal(df, df_orig)
            return

        df.f.values[3] = 1

        df.f.values[3] = 2
        expected = DataFrame(
            np.zeros((5, 6), dtype="int64"),
            columns=["a", "b", "c", "d", "e", "f"],
            index=range(5),
        )
        expected.at[3, "f"] = 2
        tm.assert_frame_equal(df, expected)
        expected = Series([0, 0, 0, 2, 0], name="f")
        tm.assert_series_equal(df.f, expected)

    def test_iloc_setitem_chained_assignment(self, using_copy_on_write):
        # GH#3970
        with option_context("chained_assignment", None):
            df = DataFrame({"aa": range(5), "bb": [2.2] * 5})
            df["cc"] = 0.0

            ck = [True] * len(df)

            with tm.raises_chained_assignment_error():
                df["bb"].iloc[0] = 0.13

            # GH#3970 this lookup used to break the chained setting to 0.15
            df.iloc[ck]

            with tm.raises_chained_assignment_error():
                df["bb"].iloc[0] = 0.15

            if not using_copy_on_write:
                assert df["bb"].iloc[0] == 0.15
            else:
                assert df["bb"].iloc[0] == 2.2

    def test_getitem_loc_assignment_slice_state(self):
        # GH 13569
        df = DataFrame({"a": [10, 20, 30]})
        with tm.raises_chained_assignment_error():
            df["a"].loc[4] = 40
        tm.assert_frame_equal(df, DataFrame({"a": [10, 20, 30]}))
        tm.assert_series_equal(df["a"], Series([10, 20, 30], name="a"))
