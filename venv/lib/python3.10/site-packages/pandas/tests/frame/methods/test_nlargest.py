"""
Note: for naming purposes, most tests are title with as e.g. "test_nlargest_foo"
but are implicitly also testing nsmallest_foo.
"""
from string import ascii_lowercase

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.util.version import Version


@pytest.fixture
def df_duplicates():
    return pd.DataFrame(
        {"a": [1, 2, 3, 4, 4], "b": [1, 1, 1, 1, 1], "c": [0, 1, 2, 5, 4]},
        index=[0, 0, 1, 1, 1],
    )


@pytest.fixture
def df_strings():
    return pd.DataFrame(
        {
            "a": np.random.default_rng(2).permutation(10),
            "b": list(ascii_lowercase[:10]),
            "c": np.random.default_rng(2).permutation(10).astype("float64"),
        }
    )


@pytest.fixture
def df_main_dtypes():
    return pd.DataFrame(
        {
            "group": [1, 1, 2],
            "int": [1, 2, 3],
            "float": [4.0, 5.0, 6.0],
            "string": list("abc"),
            "category_string": pd.Series(list("abc")).astype("category"),
            "category_int": [7, 8, 9],
            "datetime": pd.date_range("20130101", periods=3),
            "datetimetz": pd.date_range("20130101", periods=3, tz="US/Eastern"),
            "timedelta": pd.timedelta_range("1 s", periods=3, freq="s"),
        },
        columns=[
            "group",
            "int",
            "float",
            "string",
            "category_string",
            "category_int",
            "datetime",
            "datetimetz",
            "timedelta",
        ],
    )


class TestNLargestNSmallest:
    # ----------------------------------------------------------------------
    # Top / bottom
    @pytest.mark.parametrize(
        "order",
        [
            ["a"],
            ["c"],
            ["a", "b"],
            ["a", "c"],
            ["b", "a"],
            ["b", "c"],
            ["a", "b", "c"],
            ["c", "a", "b"],
            ["c", "b", "a"],
            ["b", "c", "a"],
            ["b", "a", "c"],
            # dups!
            ["b", "c", "c"],
        ],
    )
    @pytest.mark.parametrize("n", range(1, 11))
    def test_nlargest_n(self, df_strings, nselect_method, n, order):
        # GH#10393
        df = df_strings
        if "b" in order:
            error_msg = (
                f"Column 'b' has dtype (object|str), "
                f"cannot use method '{nselect_method}' with this dtype"
            )
            with pytest.raises(TypeError, match=error_msg):
                getattr(df, nselect_method)(n, order)
        else:
            ascending = nselect_method == "nsmallest"
            result = getattr(df, nselect_method)(n, order)
            expected = df.sort_values(order, ascending=ascending).head(n)
            tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "columns", [["group", "category_string"], ["group", "string"]]
    )
    def test_nlargest_error(self, df_main_dtypes, nselect_method, columns):
        df = df_main_dtypes
        col = columns[1]
        error_msg = (
            f"Column '{col}' has dtype {df[col].dtype}, "
            f"cannot use method '{nselect_method}' with this dtype"
        )
        # escape some characters that may be in the repr
        error_msg = (
            error_msg.replace("(", "\\(")
            .replace(")", "\\)")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )
        with pytest.raises(TypeError, match=error_msg):
            getattr(df, nselect_method)(2, columns)

    def test_nlargest_all_dtypes(self, df_main_dtypes):
        df = df_main_dtypes
        df.nsmallest(2, list(set(df) - {"category_string", "string"}))
        df.nlargest(2, list(set(df) - {"category_string", "string"}))

    def test_nlargest_duplicates_on_starter_columns(self):
        # regression test for GH#22752

        df = pd.DataFrame({"a": [2, 2, 2, 1, 1, 1], "b": [1, 2, 3, 3, 2, 1]})

        result = df.nlargest(4, columns=["a", "b"])
        expected = pd.DataFrame(
            {"a": [2, 2, 2, 1], "b": [3, 2, 1, 3]}, index=[2, 1, 0, 3]
        )
        tm.assert_frame_equal(result, expected)

        result = df.nsmallest(4, columns=["a", "b"])
        expected = pd.DataFrame(
            {"a": [1, 1, 1, 2], "b": [1, 2, 3, 1]}, index=[5, 4, 3, 0]
        )
        tm.assert_frame_equal(result, expected)

    def test_nlargest_n_identical_values(self):
        # GH#15297
        df = pd.DataFrame({"a": [1] * 5, "b": [1, 2, 3, 4, 5]})

        result = df.nlargest(3, "a")
        expected = pd.DataFrame({"a": [1] * 3, "b": [1, 2, 3]}, index=[0, 1, 2])
        tm.assert_frame_equal(result, expected)

        result = df.nsmallest(3, "a")
        expected = pd.DataFrame({"a": [1] * 3, "b": [1, 2, 3]})
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "order",
        [["a", "b", "c"], ["c", "b", "a"], ["a"], ["b"], ["a", "b"], ["c", "b"]],
    )
    @pytest.mark.parametrize("n", range(1, 6))
    def test_nlargest_n_duplicate_index(self, df_duplicates, n, order, request):
        # GH#13412

        df = df_duplicates
        result = df.nsmallest(n, order)
        expected = df.sort_values(order).head(n)
        tm.assert_frame_equal(result, expected)

        result = df.nlargest(n, order)
        expected = df.sort_values(order, ascending=False).head(n)
        if Version(np.__version__) >= Version("1.25") and (
            (order == ["a"] and n in (1, 2, 3, 4)) or (order == ["a", "b"]) and n == 5
        ):
            request.applymarker(
                pytest.mark.xfail(
                    reason=(
                        "pandas default unstable sorting of duplicates"
                        "issue with numpy>=1.25 with AVX instructions"
                    ),
                    strict=False,
                )
            )
        tm.assert_frame_equal(result, expected)

    def test_nlargest_duplicate_keep_all_ties(self):
        # GH#16818
        df = pd.DataFrame(
            {"a": [5, 4, 4, 2, 3, 3, 3, 3], "b": [10, 9, 8, 7, 5, 50, 10, 20]}
        )
        result = df.nlargest(4, "a", keep="all")
        expected = pd.DataFrame(
            {
                "a": {0: 5, 1: 4, 2: 4, 4: 3, 5: 3, 6: 3, 7: 3},
                "b": {0: 10, 1: 9, 2: 8, 4: 5, 5: 50, 6: 10, 7: 20},
            }
        )
        tm.assert_frame_equal(result, expected)

        result = df.nsmallest(2, "a", keep="all")
        expected = pd.DataFrame(
            {
                "a": {3: 2, 4: 3, 5: 3, 6: 3, 7: 3},
                "b": {3: 7, 4: 5, 5: 50, 6: 10, 7: 20},
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_nlargest_multiindex_column_lookup(self):
        # Check whether tuples are correctly treated as multi-level lookups.
        # GH#23033
        df = pd.DataFrame(
            columns=pd.MultiIndex.from_product([["x"], ["a", "b"]]),
            data=[[0.33, 0.13], [0.86, 0.25], [0.25, 0.70], [0.85, 0.91]],
        )

        # nsmallest
        result = df.nsmallest(3, ("x", "a"))
        expected = df.iloc[[2, 0, 3]]
        tm.assert_frame_equal(result, expected)

        # nlargest
        result = df.nlargest(3, ("x", "b"))
        expected = df.iloc[[3, 2, 1]]
        tm.assert_frame_equal(result, expected)

    def test_nlargest_nan(self):
        # GH#43060
        df = pd.DataFrame([np.nan, np.nan, 0, 1, 2, 3])
        result = df.nlargest(5, 0)
        expected = df.sort_values(0, ascending=False).head(5)
        tm.assert_frame_equal(result, expected)

    def test_nsmallest_nan_after_n_element(self):
        # GH#46589
        df = pd.DataFrame(
            {
                "a": [1, 2, 3, 4, 5, None, 7],
                "b": [7, 6, 5, 4, 3, 2, 1],
                "c": [1, 1, 2, 2, 3, 3, 3],
            },
            index=range(7),
        )
        result = df.nsmallest(5, columns=["a", "b"])
        expected = pd.DataFrame(
            {
                "a": [1, 2, 3, 4, 5],
                "b": [7, 6, 5, 4, 3],
                "c": [1, 1, 2, 2, 3],
            },
            index=range(5),
        ).astype({"a": "float"})
        tm.assert_frame_equal(result, expected)
