import numpy as np
import pytest

from pandas.core.dtypes.dtypes import ExtensionDtype

import pandas as pd
from pandas import (
    DataFrame,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.arrays import ExtensionArray


class DummyDtype(ExtensionDtype):
    type = int

    def __init__(self, numeric) -> None:
        self._numeric = numeric

    @property
    def name(self):
        return "Dummy"

    @property
    def _is_numeric(self):
        return self._numeric


class DummyArray(ExtensionArray):
    def __init__(self, data, dtype) -> None:
        self.data = data
        self._dtype = dtype

    def __array__(self, dtype=None, copy=None):
        return self.data

    @property
    def dtype(self):
        return self._dtype

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, item):
        pass

    def copy(self):
        return self


class TestSelectDtypes:
    def test_select_dtypes_include_using_list_like(self, using_infer_string):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.Categorical(list("abc")),
                "g": pd.date_range("20130101", periods=3),
                "h": pd.date_range("20130101", periods=3, tz="US/Eastern"),
                "i": pd.date_range("20130101", periods=3, tz="CET"),
                "j": pd.period_range("2013-01", periods=3, freq="M"),
                "k": pd.timedelta_range("1 day", periods=3),
            }
        )

        ri = df.select_dtypes(include=[np.number])
        ei = df[["b", "c", "d", "k"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=[np.number], exclude=["timedelta"])
        ei = df[["b", "c", "d"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=[np.number, "category"], exclude=["timedelta"])
        ei = df[["b", "c", "d", "f"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=["datetime"])
        ei = df[["g"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=["datetime64"])
        ei = df[["g"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=["datetimetz"])
        ei = df[["h", "i"]]
        tm.assert_frame_equal(ri, ei)

        with pytest.raises(NotImplementedError, match=r"^$"):
            df.select_dtypes(include=["period"])

        if using_infer_string:
            ri = df.select_dtypes(include=["str"])
            ei = df[["a"]]
            tm.assert_frame_equal(ri, ei)

            ri = df.select_dtypes(include=[str])
            tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=["object"])
        ei = df[["a"]]
        tm.assert_frame_equal(ri, ei)

    def test_select_dtypes_exclude_using_list_like(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
            }
        )
        re = df.select_dtypes(exclude=[np.number])
        ee = df[["a", "e"]]
        tm.assert_frame_equal(re, ee)

    def test_select_dtypes_exclude_include_using_list_like(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6, dtype="u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )
        exclude = (np.datetime64,)
        include = np.bool_, "integer"
        r = df.select_dtypes(include=include, exclude=exclude)
        e = df[["b", "c", "e"]]
        tm.assert_frame_equal(r, e)

        exclude = ("datetime",)
        include = "bool", "int64", "int32"
        r = df.select_dtypes(include=include, exclude=exclude)
        e = df[["b", "e"]]
        tm.assert_frame_equal(r, e)

    @pytest.mark.parametrize(
        "include", [(np.bool_, "int"), (np.bool_, "integer"), ("bool", int)]
    )
    def test_select_dtypes_exclude_include_int(self, include):
        # Fix select_dtypes(include='int') for Windows, FYI #36596
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6, dtype="int32"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )
        exclude = (np.datetime64,)
        result = df.select_dtypes(include=include, exclude=exclude)
        expected = df[["b", "c", "e"]]
        tm.assert_frame_equal(result, expected)

    def test_select_dtypes_include_using_scalars(self, using_infer_string):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.Categorical(list("abc")),
                "g": pd.date_range("20130101", periods=3),
                "h": pd.date_range("20130101", periods=3, tz="US/Eastern"),
                "i": pd.date_range("20130101", periods=3, tz="CET"),
                "j": pd.period_range("2013-01", periods=3, freq="M"),
                "k": pd.timedelta_range("1 day", periods=3),
            }
        )

        ri = df.select_dtypes(include=np.number)
        ei = df[["b", "c", "d", "k"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include="datetime")
        ei = df[["g"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include="datetime64")
        ei = df[["g"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include="category")
        ei = df[["f"]]
        tm.assert_frame_equal(ri, ei)

        with pytest.raises(NotImplementedError, match=r"^$"):
            df.select_dtypes(include="period")

        if using_infer_string:
            ri = df.select_dtypes(include="str")
            ei = df[["a"]]
            tm.assert_frame_equal(ri, ei)

    def test_select_dtypes_exclude_using_scalars(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.Categorical(list("abc")),
                "g": pd.date_range("20130101", periods=3),
                "h": pd.date_range("20130101", periods=3, tz="US/Eastern"),
                "i": pd.date_range("20130101", periods=3, tz="CET"),
                "j": pd.period_range("2013-01", periods=3, freq="M"),
                "k": pd.timedelta_range("1 day", periods=3),
            }
        )

        ri = df.select_dtypes(exclude=np.number)
        ei = df[["a", "e", "f", "g", "h", "i", "j"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(exclude="category")
        ei = df[["a", "b", "c", "d", "e", "g", "h", "i", "j", "k"]]
        tm.assert_frame_equal(ri, ei)

        with pytest.raises(NotImplementedError, match=r"^$"):
            df.select_dtypes(exclude="period")

    def test_select_dtypes_include_exclude_using_scalars(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.Categorical(list("abc")),
                "g": pd.date_range("20130101", periods=3),
                "h": pd.date_range("20130101", periods=3, tz="US/Eastern"),
                "i": pd.date_range("20130101", periods=3, tz="CET"),
                "j": pd.period_range("2013-01", periods=3, freq="M"),
                "k": pd.timedelta_range("1 day", periods=3),
            }
        )

        ri = df.select_dtypes(include=np.number, exclude="floating")
        ei = df[["b", "c", "k"]]
        tm.assert_frame_equal(ri, ei)

    def test_select_dtypes_include_exclude_mixed_scalars_lists(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.Categorical(list("abc")),
                "g": pd.date_range("20130101", periods=3),
                "h": pd.date_range("20130101", periods=3, tz="US/Eastern"),
                "i": pd.date_range("20130101", periods=3, tz="CET"),
                "j": pd.period_range("2013-01", periods=3, freq="M"),
                "k": pd.timedelta_range("1 day", periods=3),
            }
        )

        ri = df.select_dtypes(include=np.number, exclude=["floating", "timedelta"])
        ei = df[["b", "c"]]
        tm.assert_frame_equal(ri, ei)

        ri = df.select_dtypes(include=[np.number, "category"], exclude="floating")
        ei = df[["b", "c", "f", "k"]]
        tm.assert_frame_equal(ri, ei)

    def test_select_dtypes_duplicate_columns(self):
        # GH20839
        df = DataFrame(
            {
                "a": ["a", "b", "c"],
                "b": [1, 2, 3],
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )
        df.columns = ["a", "a", "b", "b", "b", "c"]

        expected = DataFrame(
            {"a": list(range(1, 4)), "b": np.arange(3, 6).astype("u1")}
        )

        result = df.select_dtypes(include=[np.number], exclude=["floating"])
        tm.assert_frame_equal(result, expected)

    def test_select_dtypes_not_an_attr_but_still_valid_dtype(self, using_infer_string):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )
        df["g"] = df.f.diff()
        assert not hasattr(np, "u8")
        r = df.select_dtypes(include=["i8", "O"], exclude=["timedelta"])
        # if using_infer_string:
        #     TODO warn
        e = df[["a", "b"]]
        tm.assert_frame_equal(r, e)

        r = df.select_dtypes(include=["i8", "O", "timedelta64[ns]"])
        # if using_infer_string:
        #     TODO warn
        e = df[["a", "b", "g"]]
        tm.assert_frame_equal(r, e)

    def test_select_dtypes_empty(self):
        df = DataFrame({"a": list("abc"), "b": list(range(1, 4))})
        msg = "at least one of include or exclude must be nonempty"
        with pytest.raises(ValueError, match=msg):
            df.select_dtypes()

    def test_select_dtypes_bad_datetime64(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )
        with pytest.raises(ValueError, match=".+ is too specific"):
            df.select_dtypes(include=["datetime64[D]"])

        with pytest.raises(ValueError, match=".+ is too specific"):
            df.select_dtypes(exclude=["datetime64[as]"])

    def test_select_dtypes_datetime_with_tz(self):
        df2 = DataFrame(
            {
                "A": Timestamp("20130102", tz="US/Eastern"),
                "B": Timestamp("20130603", tz="CET"),
            },
            index=range(5),
        )
        df3 = pd.concat([df2.A.to_frame(), df2.B.to_frame()], axis=1)
        result = df3.select_dtypes(include=["datetime64[ns]"])
        expected = df3.reindex(columns=[])
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("dtype", [str, "str", np.bytes_, "S1", np.str_, "U1"])
    @pytest.mark.parametrize("arg", ["include", "exclude"])
    def test_select_dtypes_str_raises(self, dtype, arg, using_infer_string):
        if using_infer_string and (dtype == "str" or dtype is str):
            # this is tested below
            pytest.skip("Selecting string columns works with future strings")
        df = DataFrame(
            {
                "a": list("abc"),
                "g": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )
        msg = "string dtypes are not allowed"
        kwargs = {arg: [dtype]}

        with pytest.raises(TypeError, match=msg):
            df.select_dtypes(**kwargs)

    def test_select_dtypes_bad_arg_raises(self):
        df = DataFrame(
            {
                "a": list("abc"),
                "g": list("abc"),
                "b": list(range(1, 4)),
                "c": np.arange(3, 6).astype("u1"),
                "d": np.arange(4.0, 7.0, dtype="float64"),
                "e": [True, False, True],
                "f": pd.date_range("now", periods=3).values,
            }
        )

        msg = "data type.*not understood"
        with pytest.raises(TypeError, match=msg):
            df.select_dtypes(["blargy, blarg, blarg"])

    def test_select_dtypes_typecodes(self):
        # GH 11990
        df = DataFrame(np.random.default_rng(2).random((5, 3)))
        FLOAT_TYPES = list(np.typecodes["AllFloat"])
        tm.assert_frame_equal(df.select_dtypes(FLOAT_TYPES), df)

    @pytest.mark.parametrize(
        "arr,expected",
        (
            (np.array([1, 2], dtype=np.int32), True),
            (pd.array([1, 2], dtype="Int32"), True),
            (DummyArray([1, 2], dtype=DummyDtype(numeric=True)), True),
            (DummyArray([1, 2], dtype=DummyDtype(numeric=False)), False),
        ),
    )
    def test_select_dtypes_numeric(self, arr, expected):
        # GH 35340

        df = DataFrame(arr)
        is_selected = df.select_dtypes(np.number).shape == df.shape
        assert is_selected == expected

    def test_select_dtypes_numeric_nullable_string(self, nullable_string_dtype):
        arr = pd.array(["a", "b"], dtype=nullable_string_dtype)
        df = DataFrame(arr)
        is_selected = df.select_dtypes(np.number).shape == df.shape
        assert not is_selected

    @pytest.mark.parametrize(
        "expected, float_dtypes",
        [
            [
                DataFrame(
                    {"A": range(3), "B": range(5, 8), "C": range(10, 7, -1)}
                ).astype(dtype={"A": float, "B": np.float64, "C": np.float32}),
                float,
            ],
            [
                DataFrame(
                    {"A": range(3), "B": range(5, 8), "C": range(10, 7, -1)}
                ).astype(dtype={"A": float, "B": np.float64, "C": np.float32}),
                "float",
            ],
            [DataFrame({"C": range(10, 7, -1)}, dtype=np.float32), np.float32],
            [
                DataFrame({"A": range(3), "B": range(5, 8)}).astype(
                    dtype={"A": float, "B": np.float64}
                ),
                np.float64,
            ],
        ],
    )
    def test_select_dtypes_float_dtype(self, expected, float_dtypes):
        # GH#42452
        dtype_dict = {"A": float, "B": np.float64, "C": np.float32}
        df = DataFrame(
            {"A": range(3), "B": range(5, 8), "C": range(10, 7, -1)},
        )
        df = df.astype(dtype_dict)
        result = df.select_dtypes(include=float_dtypes)
        tm.assert_frame_equal(result, expected)

    def test_np_bool_ea_boolean_include_number(self):
        # GH 46870
        df = DataFrame(
            {
                "a": [1, 2, 3],
                "b": pd.Series([True, False, True], dtype="boolean"),
                "c": np.array([True, False, True]),
                "d": pd.Categorical([True, False, True]),
                "e": pd.arrays.SparseArray([True, False, True]),
            }
        )
        result = df.select_dtypes(include="number")
        expected = DataFrame({"a": [1, 2, 3]})
        tm.assert_frame_equal(result, expected)

    def test_select_dtypes_no_view(self):
        # https://github.com/pandas-dev/pandas/issues/48090
        # result of this method is not a view on the original dataframe
        df = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        df_orig = df.copy()
        result = df.select_dtypes(include=["number"])
        result.iloc[0, 0] = 0
        tm.assert_frame_equal(df, df_orig)

    def test_select_dtype_object_and_str(self, using_infer_string):
        # https://github.com/pandas-dev/pandas/issues/61916
        df = DataFrame(
            {
                "a": ["a", "b", "c"],
                "b": [1, 2, 3],
                "c": pd.array(["a", "b", "c"], dtype="string"),
            }
        )

        # with "object" -> only select the object or default str dtype column
        result = df.select_dtypes(include=["object"])
        expected = df[["a"]]
        tm.assert_frame_equal(result, expected)

        # with "string" -> select both the default 'str' and the nullable 'string'
        result = df.select_dtypes(include=["string"])
        if using_infer_string:
            expected = df[["a", "c"]]
        else:
            expected = df[["c"]]
        tm.assert_frame_equal(result, expected)
