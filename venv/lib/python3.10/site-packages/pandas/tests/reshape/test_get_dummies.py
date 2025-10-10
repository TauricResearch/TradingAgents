import re
import unicodedata

import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas.core.dtypes.common import is_integer_dtype

import pandas as pd
from pandas import (
    ArrowDtype,
    Categorical,
    CategoricalDtype,
    CategoricalIndex,
    DataFrame,
    Index,
    RangeIndex,
    Series,
    SparseDtype,
    get_dummies,
)
import pandas._testing as tm
from pandas.core.arrays.sparse import SparseArray

try:
    import pyarrow as pa
except ImportError:
    pa = None


class TestGetDummies:
    @pytest.fixture
    def df(self):
        return DataFrame({"A": ["a", "b", "a"], "B": ["b", "b", "c"], "C": [1, 2, 3]})

    @pytest.fixture(params=["uint8", "i8", np.float64, bool, None])
    def dtype(self, request):
        return np.dtype(request.param)

    @pytest.fixture(params=["dense", "sparse"])
    def sparse(self, request):
        # params are strings to simplify reading test results,
        # e.g. TestGetDummies::test_basic[uint8-sparse] instead of [uint8-True]
        return request.param == "sparse"

    def effective_dtype(self, dtype):
        if dtype is None:
            return np.uint8
        return dtype

    def test_get_dummies_raises_on_dtype_object(self, df):
        msg = "dtype=object is not a valid dtype for get_dummies"
        with pytest.raises(ValueError, match=msg):
            get_dummies(df, dtype="object")

    def test_get_dummies_basic(self, sparse, dtype):
        s_list = list("abc")
        s_series = Series(s_list)
        s_series_index = Series(s_list, list("ABC"))

        expected = DataFrame(
            {"a": [1, 0, 0], "b": [0, 1, 0], "c": [0, 0, 1]},
            dtype=self.effective_dtype(dtype),
        )
        if sparse:
            if dtype.kind == "b":
                expected = expected.apply(SparseArray, fill_value=False)
            else:
                expected = expected.apply(SparseArray, fill_value=0.0)
        result = get_dummies(s_list, sparse=sparse, dtype=dtype)
        tm.assert_frame_equal(result, expected)

        result = get_dummies(s_series, sparse=sparse, dtype=dtype)
        tm.assert_frame_equal(result, expected)

        expected.index = list("ABC")
        result = get_dummies(s_series_index, sparse=sparse, dtype=dtype)
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_basic_types(self, sparse, dtype, using_infer_string):
        # GH 10531
        s_list = list("abc")
        s_series = Series(s_list)
        s_df = DataFrame(
            {"a": [0, 1, 0, 1, 2], "b": ["A", "A", "B", "C", "C"], "c": [2, 3, 3, 3, 2]}
        )

        expected = DataFrame(
            {"a": [1, 0, 0], "b": [0, 1, 0], "c": [0, 0, 1]},
            dtype=self.effective_dtype(dtype),
            columns=list("abc"),
        )
        if sparse:
            if is_integer_dtype(dtype):
                fill_value = 0
            elif dtype == bool:
                fill_value = False
            else:
                fill_value = 0.0

            expected = expected.apply(SparseArray, fill_value=fill_value)
        result = get_dummies(s_list, sparse=sparse, dtype=dtype)
        tm.assert_frame_equal(result, expected)

        result = get_dummies(s_series, sparse=sparse, dtype=dtype)
        tm.assert_frame_equal(result, expected)

        result = get_dummies(s_df, columns=s_df.columns, sparse=sparse, dtype=dtype)
        if sparse:
            dtype_name = f"Sparse[{self.effective_dtype(dtype).name}, {fill_value}]"
        else:
            dtype_name = self.effective_dtype(dtype).name

        expected = Series({dtype_name: 8}, name="count")
        result = result.dtypes.value_counts()
        result.index = [str(i) for i in result.index]
        tm.assert_series_equal(result, expected)

        result = get_dummies(s_df, columns=["a"], sparse=sparse, dtype=dtype)

        key = "str" if using_infer_string else "object"
        expected_counts = {"int64": 1, key: 1}
        expected_counts[dtype_name] = 3 + expected_counts.get(dtype_name, 0)

        expected = Series(expected_counts, name="count").sort_index()
        result = result.dtypes.value_counts()
        result.index = [str(i) for i in result.index]
        result = result.sort_index()
        tm.assert_series_equal(result, expected)

    def test_get_dummies_just_na(self, sparse):
        just_na_list = [np.nan]
        just_na_series = Series(just_na_list)
        just_na_series_index = Series(just_na_list, index=["A"])

        res_list = get_dummies(just_na_list, sparse=sparse)
        res_series = get_dummies(just_na_series, sparse=sparse)
        res_series_index = get_dummies(just_na_series_index, sparse=sparse)

        assert res_list.empty
        assert res_series.empty
        assert res_series_index.empty

        assert res_list.index.tolist() == [0]
        assert res_series.index.tolist() == [0]
        assert res_series_index.index.tolist() == ["A"]

    def test_get_dummies_include_na(self, sparse, dtype):
        s = ["a", "b", np.nan]
        res = get_dummies(s, sparse=sparse, dtype=dtype)
        exp = DataFrame(
            {"a": [1, 0, 0], "b": [0, 1, 0]}, dtype=self.effective_dtype(dtype)
        )
        if sparse:
            if dtype.kind == "b":
                exp = exp.apply(SparseArray, fill_value=False)
            else:
                exp = exp.apply(SparseArray, fill_value=0.0)
        tm.assert_frame_equal(res, exp)

        # Sparse dataframes do not allow nan labelled columns, see #GH8822
        res_na = get_dummies(s, dummy_na=True, sparse=sparse, dtype=dtype)
        exp_na = DataFrame(
            {np.nan: [0, 0, 1], "a": [1, 0, 0], "b": [0, 1, 0]},
            dtype=self.effective_dtype(dtype),
        )
        exp_na = exp_na.reindex(["a", "b", np.nan], axis=1)
        # hack (NaN handling in assert_index_equal)
        exp_na.columns = res_na.columns
        if sparse:
            if dtype.kind == "b":
                exp_na = exp_na.apply(SparseArray, fill_value=False)
            else:
                exp_na = exp_na.apply(SparseArray, fill_value=0.0)
        tm.assert_frame_equal(res_na, exp_na)

        res_just_na = get_dummies([np.nan], dummy_na=True, sparse=sparse, dtype=dtype)
        exp_just_na = DataFrame(
            Series(1, index=[0]), columns=[np.nan], dtype=self.effective_dtype(dtype)
        )
        tm.assert_numpy_array_equal(res_just_na.values, exp_just_na.values)

    def test_get_dummies_unicode(self, sparse):
        # See GH 6885 - get_dummies chokes on unicode values
        e = "e"
        eacute = unicodedata.lookup("LATIN SMALL LETTER E WITH ACUTE")
        s = [e, eacute, eacute]
        res = get_dummies(s, prefix="letter", sparse=sparse)
        exp = DataFrame(
            {"letter_e": [True, False, False], f"letter_{eacute}": [False, True, True]}
        )
        if sparse:
            exp = exp.apply(SparseArray, fill_value=False)
        tm.assert_frame_equal(res, exp)

    def test_dataframe_dummies_all_obj(self, df, sparse):
        df = df[["A", "B"]]
        result = get_dummies(df, sparse=sparse)
        expected = DataFrame(
            {"A_a": [1, 0, 1], "A_b": [0, 1, 0], "B_b": [1, 1, 0], "B_c": [0, 0, 1]},
            dtype=bool,
        )
        if sparse:
            expected = DataFrame(
                {
                    "A_a": SparseArray([1, 0, 1], dtype="bool"),
                    "A_b": SparseArray([0, 1, 0], dtype="bool"),
                    "B_b": SparseArray([1, 1, 0], dtype="bool"),
                    "B_c": SparseArray([0, 0, 1], dtype="bool"),
                }
            )

        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_string_dtype(self, df, any_string_dtype):
        # GH44965
        df = df[["A", "B"]]
        df = df.astype({"A": "str", "B": any_string_dtype})
        result = get_dummies(df)
        expected = DataFrame(
            {
                "A_a": [1, 0, 1],
                "A_b": [0, 1, 0],
                "B_b": [1, 1, 0],
                "B_c": [0, 0, 1],
            },
            dtype=bool,
        )
        if any_string_dtype == "string" and any_string_dtype.na_value is pd.NA:
            expected[["B_b", "B_c"]] = expected[["B_b", "B_c"]].astype("boolean")
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_mix_default(self, df, sparse, dtype):
        result = get_dummies(df, sparse=sparse, dtype=dtype)
        if sparse:
            arr = SparseArray
            if dtype.kind == "b":
                typ = SparseDtype(dtype, False)
            else:
                typ = SparseDtype(dtype, 0)
        else:
            arr = np.array
            typ = dtype
        expected = DataFrame(
            {
                "C": [1, 2, 3],
                "A_a": arr([1, 0, 1], dtype=typ),
                "A_b": arr([0, 1, 0], dtype=typ),
                "B_b": arr([1, 1, 0], dtype=typ),
                "B_c": arr([0, 0, 1], dtype=typ),
            }
        )
        expected = expected[["C", "A_a", "A_b", "B_b", "B_c"]]
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_prefix_list(self, df, sparse):
        prefixes = ["from_A", "from_B"]
        result = get_dummies(df, prefix=prefixes, sparse=sparse)
        expected = DataFrame(
            {
                "C": [1, 2, 3],
                "from_A_a": [True, False, True],
                "from_A_b": [False, True, False],
                "from_B_b": [True, True, False],
                "from_B_c": [False, False, True],
            },
        )
        expected[["C"]] = df[["C"]]
        cols = ["from_A_a", "from_A_b", "from_B_b", "from_B_c"]
        expected = expected[["C"] + cols]

        typ = SparseArray if sparse else Series
        expected[cols] = expected[cols].apply(lambda x: typ(x))
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_prefix_str(self, df, sparse):
        # not that you should do this...
        result = get_dummies(df, prefix="bad", sparse=sparse)
        bad_columns = ["bad_a", "bad_b", "bad_b", "bad_c"]
        expected = DataFrame(
            [
                [1, True, False, True, False],
                [2, False, True, True, False],
                [3, True, False, False, True],
            ],
            columns=["C"] + bad_columns,
        )
        expected = expected.astype({"C": np.int64})
        if sparse:
            # work around astyping & assigning with duplicate columns
            # https://github.com/pandas-dev/pandas/issues/14427
            expected = pd.concat(
                [
                    Series([1, 2, 3], name="C"),
                    Series([True, False, True], name="bad_a", dtype="Sparse[bool]"),
                    Series([False, True, False], name="bad_b", dtype="Sparse[bool]"),
                    Series([True, True, False], name="bad_b", dtype="Sparse[bool]"),
                    Series([False, False, True], name="bad_c", dtype="Sparse[bool]"),
                ],
                axis=1,
            )

        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_subset(self, df, sparse):
        result = get_dummies(df, prefix=["from_A"], columns=["A"], sparse=sparse)
        expected = DataFrame(
            {
                "B": ["b", "b", "c"],
                "C": [1, 2, 3],
                "from_A_a": [1, 0, 1],
                "from_A_b": [0, 1, 0],
            },
        )
        cols = expected.columns
        expected[cols[1:]] = expected[cols[1:]].astype(bool)
        expected[["C"]] = df[["C"]]
        if sparse:
            cols = ["from_A_a", "from_A_b"]
            expected[cols] = expected[cols].astype(SparseDtype("bool", False))
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_prefix_sep(self, df, sparse):
        result = get_dummies(df, prefix_sep="..", sparse=sparse)
        expected = DataFrame(
            {
                "C": [1, 2, 3],
                "A..a": [True, False, True],
                "A..b": [False, True, False],
                "B..b": [True, True, False],
                "B..c": [False, False, True],
            },
        )
        expected[["C"]] = df[["C"]]
        expected = expected[["C", "A..a", "A..b", "B..b", "B..c"]]
        if sparse:
            cols = ["A..a", "A..b", "B..b", "B..c"]
            expected[cols] = expected[cols].astype(SparseDtype("bool", False))

        tm.assert_frame_equal(result, expected)

        result = get_dummies(df, prefix_sep=["..", "__"], sparse=sparse)
        expected = expected.rename(columns={"B..b": "B__b", "B..c": "B__c"})
        tm.assert_frame_equal(result, expected)

        result = get_dummies(df, prefix_sep={"A": "..", "B": "__"}, sparse=sparse)
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_prefix_bad_length(self, df, sparse):
        msg = re.escape(
            "Length of 'prefix' (1) did not match the length of the columns being "
            "encoded (2)"
        )
        with pytest.raises(ValueError, match=msg):
            get_dummies(df, prefix=["too few"], sparse=sparse)

    def test_dataframe_dummies_prefix_sep_bad_length(self, df, sparse):
        msg = re.escape(
            "Length of 'prefix_sep' (1) did not match the length of the columns being "
            "encoded (2)"
        )
        with pytest.raises(ValueError, match=msg):
            get_dummies(df, prefix_sep=["bad"], sparse=sparse)

    def test_dataframe_dummies_prefix_dict(self, sparse):
        prefixes = {"A": "from_A", "B": "from_B"}
        df = DataFrame({"C": [1, 2, 3], "A": ["a", "b", "a"], "B": ["b", "b", "c"]})
        result = get_dummies(df, prefix=prefixes, sparse=sparse)

        expected = DataFrame(
            {
                "C": [1, 2, 3],
                "from_A_a": [1, 0, 1],
                "from_A_b": [0, 1, 0],
                "from_B_b": [1, 1, 0],
                "from_B_c": [0, 0, 1],
            }
        )

        columns = ["from_A_a", "from_A_b", "from_B_b", "from_B_c"]
        expected[columns] = expected[columns].astype(bool)
        if sparse:
            expected[columns] = expected[columns].astype(SparseDtype("bool", False))

        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_with_na(self, df, sparse, dtype):
        df.loc[3, :] = [np.nan, np.nan, np.nan]
        result = get_dummies(df, dummy_na=True, sparse=sparse, dtype=dtype).sort_index(
            axis=1
        )

        if sparse:
            arr = SparseArray
            if dtype.kind == "b":
                typ = SparseDtype(dtype, False)
            else:
                typ = SparseDtype(dtype, 0)
        else:
            arr = np.array
            typ = dtype

        expected = DataFrame(
            {
                "C": [1, 2, 3, np.nan],
                "A_a": arr([1, 0, 1, 0], dtype=typ),
                "A_b": arr([0, 1, 0, 0], dtype=typ),
                "A_nan": arr([0, 0, 0, 1], dtype=typ),
                "B_b": arr([1, 1, 0, 0], dtype=typ),
                "B_c": arr([0, 0, 1, 0], dtype=typ),
                "B_nan": arr([0, 0, 0, 1], dtype=typ),
            }
        ).sort_index(axis=1)

        tm.assert_frame_equal(result, expected)

        result = get_dummies(df, dummy_na=False, sparse=sparse, dtype=dtype)
        expected = expected[["C", "A_a", "A_b", "B_b", "B_c"]]
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_with_categorical(self, df, sparse, dtype):
        df["cat"] = Categorical(["x", "y", "y"])
        result = get_dummies(df, sparse=sparse, dtype=dtype).sort_index(axis=1)
        if sparse:
            arr = SparseArray
            if dtype.kind == "b":
                typ = SparseDtype(dtype, False)
            else:
                typ = SparseDtype(dtype, 0)
        else:
            arr = np.array
            typ = dtype

        expected = DataFrame(
            {
                "C": [1, 2, 3],
                "A_a": arr([1, 0, 1], dtype=typ),
                "A_b": arr([0, 1, 0], dtype=typ),
                "B_b": arr([1, 1, 0], dtype=typ),
                "B_c": arr([0, 0, 1], dtype=typ),
                "cat_x": arr([1, 0, 0], dtype=typ),
                "cat_y": arr([0, 1, 1], dtype=typ),
            }
        ).sort_index(axis=1)

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "get_dummies_kwargs,expected",
        [
            (
                {"data": DataFrame({"ä": ["a"]})},
                DataFrame({"ä_a": [True]}),
            ),
            (
                {"data": DataFrame({"x": ["ä"]})},
                DataFrame({"x_ä": [True]}),
            ),
            (
                {"data": DataFrame({"x": ["a"]}), "prefix": "ä"},
                DataFrame({"ä_a": [True]}),
            ),
            (
                {"data": DataFrame({"x": ["a"]}), "prefix_sep": "ä"},
                DataFrame({"xäa": [True]}),
            ),
        ],
    )
    def test_dataframe_dummies_unicode(self, get_dummies_kwargs, expected):
        # GH22084 get_dummies incorrectly encodes unicode characters
        # in dataframe column names
        result = get_dummies(**get_dummies_kwargs)
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_basic_drop_first(self, sparse):
        # GH12402 Add a new parameter `drop_first` to avoid collinearity
        # Basic case
        s_list = list("abc")
        s_series = Series(s_list)
        s_series_index = Series(s_list, list("ABC"))

        expected = DataFrame({"b": [0, 1, 0], "c": [0, 0, 1]}, dtype=bool)

        result = get_dummies(s_list, drop_first=True, sparse=sparse)
        if sparse:
            expected = expected.apply(SparseArray, fill_value=False)
        tm.assert_frame_equal(result, expected)

        result = get_dummies(s_series, drop_first=True, sparse=sparse)
        tm.assert_frame_equal(result, expected)

        expected.index = list("ABC")
        result = get_dummies(s_series_index, drop_first=True, sparse=sparse)
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_basic_drop_first_one_level(self, sparse):
        # Test the case that categorical variable only has one level.
        s_list = list("aaa")
        s_series = Series(s_list)
        s_series_index = Series(s_list, list("ABC"))

        expected = DataFrame(index=RangeIndex(3))

        result = get_dummies(s_list, drop_first=True, sparse=sparse)
        tm.assert_frame_equal(result, expected)

        result = get_dummies(s_series, drop_first=True, sparse=sparse)
        tm.assert_frame_equal(result, expected)

        expected = DataFrame(index=list("ABC"))
        result = get_dummies(s_series_index, drop_first=True, sparse=sparse)
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_basic_drop_first_NA(self, sparse):
        # Test NA handling together with drop_first
        s_NA = ["a", "b", np.nan]
        res = get_dummies(s_NA, drop_first=True, sparse=sparse)
        exp = DataFrame({"b": [0, 1, 0]}, dtype=bool)
        if sparse:
            exp = exp.apply(SparseArray, fill_value=False)

        tm.assert_frame_equal(res, exp)

        res_na = get_dummies(s_NA, dummy_na=True, drop_first=True, sparse=sparse)
        exp_na = DataFrame({"b": [0, 1, 0], np.nan: [0, 0, 1]}, dtype=bool).reindex(
            ["b", np.nan], axis=1
        )
        if sparse:
            exp_na = exp_na.apply(SparseArray, fill_value=False)
        tm.assert_frame_equal(res_na, exp_na)

        res_just_na = get_dummies(
            [np.nan], dummy_na=True, drop_first=True, sparse=sparse
        )
        exp_just_na = DataFrame(index=RangeIndex(1))
        tm.assert_frame_equal(res_just_na, exp_just_na)

    def test_dataframe_dummies_drop_first(self, df, sparse):
        df = df[["A", "B"]]
        result = get_dummies(df, drop_first=True, sparse=sparse)
        expected = DataFrame({"A_b": [0, 1, 0], "B_c": [0, 0, 1]}, dtype=bool)
        if sparse:
            expected = expected.apply(SparseArray, fill_value=False)
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_drop_first_with_categorical(self, df, sparse, dtype):
        df["cat"] = Categorical(["x", "y", "y"])
        result = get_dummies(df, drop_first=True, sparse=sparse)
        expected = DataFrame(
            {"C": [1, 2, 3], "A_b": [0, 1, 0], "B_c": [0, 0, 1], "cat_y": [0, 1, 1]}
        )
        cols = ["A_b", "B_c", "cat_y"]
        expected[cols] = expected[cols].astype(bool)
        expected = expected[["C", "A_b", "B_c", "cat_y"]]
        if sparse:
            for col in cols:
                expected[col] = SparseArray(expected[col])
        tm.assert_frame_equal(result, expected)

    def test_dataframe_dummies_drop_first_with_na(self, df, sparse):
        df.loc[3, :] = [np.nan, np.nan, np.nan]
        result = get_dummies(
            df, dummy_na=True, drop_first=True, sparse=sparse
        ).sort_index(axis=1)
        expected = DataFrame(
            {
                "C": [1, 2, 3, np.nan],
                "A_b": [0, 1, 0, 0],
                "A_nan": [0, 0, 0, 1],
                "B_c": [0, 0, 1, 0],
                "B_nan": [0, 0, 0, 1],
            }
        )
        cols = ["A_b", "A_nan", "B_c", "B_nan"]
        expected[cols] = expected[cols].astype(bool)
        expected = expected.sort_index(axis=1)
        if sparse:
            for col in cols:
                expected[col] = SparseArray(expected[col])

        tm.assert_frame_equal(result, expected)

        result = get_dummies(df, dummy_na=False, drop_first=True, sparse=sparse)
        expected = expected[["C", "A_b", "B_c"]]
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_int_int(self):
        data = Series([1, 2, 1])
        result = get_dummies(data)
        expected = DataFrame([[1, 0], [0, 1], [1, 0]], columns=[1, 2], dtype=bool)
        tm.assert_frame_equal(result, expected)

        data = Series(Categorical(["a", "b", "a"]))
        result = get_dummies(data)
        expected = DataFrame(
            [[1, 0], [0, 1], [1, 0]], columns=Categorical(["a", "b"]), dtype=bool
        )
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_int_df(self, dtype):
        data = DataFrame(
            {
                "A": [1, 2, 1],
                "B": Categorical(["a", "b", "a"]),
                "C": [1, 2, 1],
                "D": [1.0, 2.0, 1.0],
            }
        )
        columns = ["C", "D", "A_1", "A_2", "B_a", "B_b"]
        expected = DataFrame(
            [[1, 1.0, 1, 0, 1, 0], [2, 2.0, 0, 1, 0, 1], [1, 1.0, 1, 0, 1, 0]],
            columns=columns,
        )
        expected[columns[2:]] = expected[columns[2:]].astype(dtype)
        result = get_dummies(data, columns=["A", "B"], dtype=dtype)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("ordered", [True, False])
    def test_dataframe_dummies_preserve_categorical_dtype(self, dtype, ordered):
        # GH13854
        cat = Categorical(list("xy"), categories=list("xyz"), ordered=ordered)
        result = get_dummies(cat, dtype=dtype)

        data = np.array([[1, 0, 0], [0, 1, 0]], dtype=self.effective_dtype(dtype))
        cols = CategoricalIndex(
            cat.categories, categories=cat.categories, ordered=ordered
        )
        expected = DataFrame(data, columns=cols, dtype=self.effective_dtype(dtype))

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("sparse", [True, False])
    def test_get_dummies_dont_sparsify_all_columns(self, sparse):
        # GH18914
        df = DataFrame.from_dict({"GDP": [1, 2], "Nation": ["AB", "CD"]})
        df = get_dummies(df, columns=["Nation"], sparse=sparse)
        df2 = df.reindex(columns=["GDP"])

        tm.assert_frame_equal(df[["GDP"]], df2)

    def test_get_dummies_duplicate_columns(self, df):
        # GH20839
        df.columns = ["A", "A", "A"]
        result = get_dummies(df).sort_index(axis=1)

        expected = DataFrame(
            [
                [1, True, False, True, False],
                [2, False, True, True, False],
                [3, True, False, False, True],
            ],
            columns=["A", "A_a", "A_b", "A_b", "A_c"],
        ).sort_index(axis=1)

        expected = expected.astype({"A": np.int64})

        tm.assert_frame_equal(result, expected)

    def test_get_dummies_all_sparse(self):
        df = DataFrame({"A": [1, 2]})
        result = get_dummies(df, columns=["A"], sparse=True)
        dtype = SparseDtype("bool", False)
        expected = DataFrame(
            {
                "A_1": SparseArray([1, 0], dtype=dtype),
                "A_2": SparseArray([0, 1], dtype=dtype),
            }
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("values", ["baz"])
    def test_get_dummies_with_string_values(self, values):
        # issue #28383
        df = DataFrame(
            {
                "bar": [1, 2, 3, 4, 5, 6],
                "foo": ["one", "one", "one", "two", "two", "two"],
                "baz": ["A", "B", "C", "A", "B", "C"],
                "zoo": ["x", "y", "z", "q", "w", "t"],
            }
        )

        msg = "Input must be a list-like for parameter `columns`"

        with pytest.raises(TypeError, match=msg):
            get_dummies(df, columns=values)

    def test_get_dummies_ea_dtype_series(self, any_numeric_ea_and_arrow_dtype):
        # GH#32430
        ser = Series(list("abca"))
        result = get_dummies(ser, dtype=any_numeric_ea_and_arrow_dtype)
        expected = DataFrame(
            {"a": [1, 0, 0, 1], "b": [0, 1, 0, 0], "c": [0, 0, 1, 0]},
            dtype=any_numeric_ea_and_arrow_dtype,
        )
        tm.assert_frame_equal(result, expected)

    def test_get_dummies_ea_dtype_dataframe(self, any_numeric_ea_and_arrow_dtype):
        # GH#32430
        df = DataFrame({"x": list("abca")})
        result = get_dummies(df, dtype=any_numeric_ea_and_arrow_dtype)
        expected = DataFrame(
            {"x_a": [1, 0, 0, 1], "x_b": [0, 1, 0, 0], "x_c": [0, 0, 1, 0]},
            dtype=any_numeric_ea_and_arrow_dtype,
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype_type", ["string", "category"])
    def test_get_dummies_ea_dtype(self, dtype_type, string_dtype_no_object):
        # GH#56273
        dtype = string_dtype_no_object
        exp_dtype = "boolean" if dtype.na_value is pd.NA else "bool"
        if dtype_type == "category":
            dtype = CategoricalDtype(Index(["a"], dtype))
        df = DataFrame({"name": Series(["a"], dtype=dtype), "x": 1})
        result = get_dummies(df)
        expected = DataFrame({"x": 1, "name_a": Series([True], dtype=exp_dtype)})
        tm.assert_frame_equal(result, expected)

    @td.skip_if_no("pyarrow")
    def test_get_dummies_arrow_dtype(self):
        # GH#56273
        df = DataFrame({"name": Series(["a"], dtype=ArrowDtype(pa.string())), "x": 1})
        result = get_dummies(df)
        expected = DataFrame({"x": 1, "name_a": Series([True], dtype="bool[pyarrow]")})
        tm.assert_frame_equal(result, expected)

        df = DataFrame(
            {
                "name": Series(
                    ["a"],
                    dtype=CategoricalDtype(Index(["a"], dtype=ArrowDtype(pa.string()))),
                ),
                "x": 1,
            }
        )
        result = get_dummies(df)
        tm.assert_frame_equal(result, expected)
