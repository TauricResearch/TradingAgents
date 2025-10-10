from __future__ import annotations

from datetime import datetime
import re

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm


@pytest.fixture
def mix_ab() -> dict[str, list[int | str]]:
    return {"a": list(range(4)), "b": list("ab..")}


@pytest.fixture
def mix_abc() -> dict[str, list[float | str]]:
    return {"a": list(range(4)), "b": list("ab.."), "c": ["a", "b", np.nan, "d"]}


class TestDataFrameReplace:
    def test_replace_inplace(self, datetime_frame, float_string_frame):
        datetime_frame.loc[datetime_frame.index[:5], "A"] = np.nan
        datetime_frame.loc[datetime_frame.index[-5:], "A"] = np.nan

        tsframe = datetime_frame.copy()
        return_value = tsframe.replace(np.nan, 0, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(tsframe, datetime_frame.fillna(0))

        # mixed type
        mf = float_string_frame
        mf.iloc[5:20, mf.columns.get_loc("foo")] = np.nan
        mf.iloc[-10:, mf.columns.get_loc("A")] = np.nan

        result = float_string_frame.replace(np.nan, 0)
        expected = float_string_frame.copy()
        expected["foo"] = expected["foo"].astype(object)
        expected = expected.fillna(value=0)
        tm.assert_frame_equal(result, expected)

        tsframe = datetime_frame.copy()
        return_value = tsframe.replace([np.nan], [0], inplace=True)
        assert return_value is None
        tm.assert_frame_equal(tsframe, datetime_frame.fillna(0))

    @pytest.mark.parametrize(
        "to_replace,values,expected",
        [
            # lists of regexes and values
            # list of [re1, re2, ..., reN] -> [v1, v2, ..., vN]
            (
                [r"\s*\.\s*", r"e|f|g"],
                [np.nan, "crap"],
                {
                    "a": ["a", "b", np.nan, np.nan],
                    "b": ["crap"] * 3 + ["h"],
                    "c": ["h", "crap", "l", "o"],
                },
            ),
            # list of [re1, re2, ..., reN] -> [re1, re2, .., reN]
            (
                [r"\s*(\.)\s*", r"(e|f|g)"],
                [r"\1\1", r"\1_crap"],
                {
                    "a": ["a", "b", "..", ".."],
                    "b": ["e_crap", "f_crap", "g_crap", "h"],
                    "c": ["h", "e_crap", "l", "o"],
                },
            ),
            # list of [re1, re2, ..., reN] -> [(re1 or v1), (re2 or v2), ..., (reN
            # or vN)]
            (
                [r"\s*(\.)\s*", r"e"],
                [r"\1\1", r"crap"],
                {
                    "a": ["a", "b", "..", ".."],
                    "b": ["crap", "f", "g", "h"],
                    "c": ["h", "crap", "l", "o"],
                },
            ),
        ],
    )
    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize("use_value_regex_args", [True, False])
    def test_regex_replace_list_obj(
        self, to_replace, values, expected, inplace, use_value_regex_args
    ):
        df = DataFrame({"a": list("ab.."), "b": list("efgh"), "c": list("helo")})

        if use_value_regex_args:
            result = df.replace(value=values, regex=to_replace, inplace=inplace)
        else:
            result = df.replace(to_replace, values, regex=True, inplace=inplace)

        if inplace:
            assert result is None
            result = df

        expected = DataFrame(expected)
        tm.assert_frame_equal(result, expected)

    def test_regex_replace_list_mixed(self, mix_ab):
        # mixed frame to make sure this doesn't break things
        dfmix = DataFrame(mix_ab)

        # lists of regexes and values
        # list of [re1, re2, ..., reN] -> [v1, v2, ..., vN]
        to_replace_res = [r"\s*\.\s*", r"a"]
        values = [np.nan, "crap"]
        mix2 = {"a": list(range(4)), "b": list("ab.."), "c": list("halo")}
        dfmix2 = DataFrame(mix2)
        res = dfmix2.replace(to_replace_res, values, regex=True)
        expec = DataFrame(
            {
                "a": mix2["a"],
                "b": ["crap", "b", np.nan, np.nan],
                "c": ["h", "crap", "l", "o"],
            }
        )
        tm.assert_frame_equal(res, expec)

        # list of [re1, re2, ..., reN] -> [re1, re2, .., reN]
        to_replace_res = [r"\s*(\.)\s*", r"(a|b)"]
        values = [r"\1\1", r"\1_crap"]
        res = dfmix.replace(to_replace_res, values, regex=True)
        expec = DataFrame({"a": mix_ab["a"], "b": ["a_crap", "b_crap", "..", ".."]})
        tm.assert_frame_equal(res, expec)

        # list of [re1, re2, ..., reN] -> [(re1 or v1), (re2 or v2), ..., (reN
        # or vN)]
        to_replace_res = [r"\s*(\.)\s*", r"a", r"(b)"]
        values = [r"\1\1", r"crap", r"\1_crap"]
        res = dfmix.replace(to_replace_res, values, regex=True)
        expec = DataFrame({"a": mix_ab["a"], "b": ["crap", "b_crap", "..", ".."]})
        tm.assert_frame_equal(res, expec)

        to_replace_res = [r"\s*(\.)\s*", r"a", r"(b)"]
        values = [r"\1\1", r"crap", r"\1_crap"]
        res = dfmix.replace(regex=to_replace_res, value=values)
        expec = DataFrame({"a": mix_ab["a"], "b": ["crap", "b_crap", "..", ".."]})
        tm.assert_frame_equal(res, expec)

    def test_regex_replace_list_mixed_inplace(self, mix_ab):
        dfmix = DataFrame(mix_ab)
        # the same inplace
        # lists of regexes and values
        # list of [re1, re2, ..., reN] -> [v1, v2, ..., vN]
        to_replace_res = [r"\s*\.\s*", r"a"]
        values = [np.nan, "crap"]
        res = dfmix.copy()
        return_value = res.replace(to_replace_res, values, inplace=True, regex=True)
        assert return_value is None
        expec = DataFrame({"a": mix_ab["a"], "b": ["crap", "b", np.nan, np.nan]})
        tm.assert_frame_equal(res, expec)

        # list of [re1, re2, ..., reN] -> [re1, re2, .., reN]
        to_replace_res = [r"\s*(\.)\s*", r"(a|b)"]
        values = [r"\1\1", r"\1_crap"]
        res = dfmix.copy()
        return_value = res.replace(to_replace_res, values, inplace=True, regex=True)
        assert return_value is None
        expec = DataFrame({"a": mix_ab["a"], "b": ["a_crap", "b_crap", "..", ".."]})
        tm.assert_frame_equal(res, expec)

        # list of [re1, re2, ..., reN] -> [(re1 or v1), (re2 or v2), ..., (reN
        # or vN)]
        to_replace_res = [r"\s*(\.)\s*", r"a", r"(b)"]
        values = [r"\1\1", r"crap", r"\1_crap"]
        res = dfmix.copy()
        return_value = res.replace(to_replace_res, values, inplace=True, regex=True)
        assert return_value is None
        expec = DataFrame({"a": mix_ab["a"], "b": ["crap", "b_crap", "..", ".."]})
        tm.assert_frame_equal(res, expec)

        to_replace_res = [r"\s*(\.)\s*", r"a", r"(b)"]
        values = [r"\1\1", r"crap", r"\1_crap"]
        res = dfmix.copy()
        return_value = res.replace(regex=to_replace_res, value=values, inplace=True)
        assert return_value is None
        expec = DataFrame({"a": mix_ab["a"], "b": ["crap", "b_crap", "..", ".."]})
        tm.assert_frame_equal(res, expec)

    def test_regex_replace_dict_mixed(self, mix_abc):
        dfmix = DataFrame(mix_abc)

        # dicts
        # single dict {re1: v1}, search the whole frame
        # need test for this...

        # list of dicts {re1: v1, re2: v2, ..., re3: v3}, search the whole
        # frame
        res = dfmix.replace({"b": r"\s*\.\s*"}, {"b": np.nan}, regex=True)
        res2 = dfmix.copy()
        return_value = res2.replace(
            {"b": r"\s*\.\s*"}, {"b": np.nan}, inplace=True, regex=True
        )
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": ["a", "b", np.nan, np.nan], "c": mix_abc["c"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)

        # list of dicts {re1: re11, re2: re12, ..., reN: re1N}, search the
        # whole frame
        res = dfmix.replace({"b": r"\s*(\.)\s*"}, {"b": r"\1ty"}, regex=True)
        res2 = dfmix.copy()
        return_value = res2.replace(
            {"b": r"\s*(\.)\s*"}, {"b": r"\1ty"}, inplace=True, regex=True
        )
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": ["a", "b", ".ty", ".ty"], "c": mix_abc["c"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)

        res = dfmix.replace(regex={"b": r"\s*(\.)\s*"}, value={"b": r"\1ty"})
        res2 = dfmix.copy()
        return_value = res2.replace(
            regex={"b": r"\s*(\.)\s*"}, value={"b": r"\1ty"}, inplace=True
        )
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": ["a", "b", ".ty", ".ty"], "c": mix_abc["c"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)

        # scalar -> dict
        # to_replace regex, {value: value}
        expec = DataFrame(
            {"a": mix_abc["a"], "b": [np.nan, "b", ".", "."], "c": mix_abc["c"]}
        )
        res = dfmix.replace("a", {"b": np.nan}, regex=True)
        res2 = dfmix.copy()
        return_value = res2.replace("a", {"b": np.nan}, regex=True, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)

        res = dfmix.replace("a", {"b": np.nan}, regex=True)
        res2 = dfmix.copy()
        return_value = res2.replace(regex="a", value={"b": np.nan}, inplace=True)
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": [np.nan, "b", ".", "."], "c": mix_abc["c"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)

    def test_regex_replace_dict_nested(self, mix_abc):
        # nested dicts will not work until this is implemented for Series
        dfmix = DataFrame(mix_abc)
        res = dfmix.replace({"b": {r"\s*\.\s*": np.nan}}, regex=True)
        res2 = dfmix.copy()
        res4 = dfmix.copy()
        return_value = res2.replace(
            {"b": {r"\s*\.\s*": np.nan}}, inplace=True, regex=True
        )
        assert return_value is None
        res3 = dfmix.replace(regex={"b": {r"\s*\.\s*": np.nan}})
        return_value = res4.replace(regex={"b": {r"\s*\.\s*": np.nan}}, inplace=True)
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": ["a", "b", np.nan, np.nan], "c": mix_abc["c"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)
        tm.assert_frame_equal(res3, expec)
        tm.assert_frame_equal(res4, expec)

    def test_regex_replace_dict_nested_non_first_character(self, any_string_dtype):
        # GH 25259
        dtype = any_string_dtype
        df = DataFrame({"first": ["abc", "bca", "cab"]}, dtype=dtype)
        result = df.replace({"a": "."}, regex=True)
        expected = DataFrame({"first": [".bc", "bc.", "c.b"]}, dtype=dtype)
        tm.assert_frame_equal(result, expected)

    def test_regex_replace_dict_nested_gh4115(self):
        df = DataFrame(
            {"Type": Series(["Q", "T", "Q", "Q", "T"], dtype=object), "tmp": 2}
        )
        expected = DataFrame({"Type": [0, 1, 0, 0, 1], "tmp": 2})
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.replace({"Type": {"Q": 0, "T": 1}})

        tm.assert_frame_equal(result, expected)

    def test_regex_replace_list_to_scalar(self, mix_abc, using_infer_string):
        df = DataFrame(mix_abc)
        expec = DataFrame(
            {
                "a": mix_abc["a"],
                "b": [np.nan] * 4,
                "c": [np.nan, np.nan, np.nan, "d"],
            }
        )
        if using_infer_string:
            expec["b"] = expec["b"].astype("str")
        msg = "Downcasting behavior in `replace`"
        warn = None if using_infer_string else FutureWarning
        with tm.assert_produces_warning(warn, match=msg):
            res = df.replace([r"\s*\.\s*", "a|b"], np.nan, regex=True)
        res2 = df.copy()
        res3 = df.copy()
        with tm.assert_produces_warning(warn, match=msg):
            return_value = res2.replace(
                [r"\s*\.\s*", "a|b"], np.nan, regex=True, inplace=True
            )
        assert return_value is None
        with tm.assert_produces_warning(warn, match=msg):
            return_value = res3.replace(
                regex=[r"\s*\.\s*", "a|b"], value=np.nan, inplace=True
            )
        assert return_value is None
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)
        tm.assert_frame_equal(res3, expec)

    def test_regex_replace_str_to_numeric(self, mix_abc):
        # what happens when you try to replace a numeric value with a regex?
        df = DataFrame(mix_abc)
        res = df.replace(r"\s*\.\s*", 0, regex=True)
        res2 = df.copy()
        return_value = res2.replace(r"\s*\.\s*", 0, inplace=True, regex=True)
        assert return_value is None
        res3 = df.copy()
        return_value = res3.replace(regex=r"\s*\.\s*", value=0, inplace=True)
        assert return_value is None
        expec = DataFrame({"a": mix_abc["a"], "b": ["a", "b", 0, 0], "c": mix_abc["c"]})
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)
        tm.assert_frame_equal(res3, expec)

    def test_regex_replace_regex_list_to_numeric(self, mix_abc):
        df = DataFrame(mix_abc)
        res = df.replace([r"\s*\.\s*", "b"], 0, regex=True)
        res2 = df.copy()
        return_value = res2.replace([r"\s*\.\s*", "b"], 0, regex=True, inplace=True)
        assert return_value is None
        res3 = df.copy()
        return_value = res3.replace(regex=[r"\s*\.\s*", "b"], value=0, inplace=True)
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": ["a", 0, 0, 0], "c": ["a", 0, np.nan, "d"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)
        tm.assert_frame_equal(res3, expec)

    def test_regex_replace_series_of_regexes(self, mix_abc):
        df = DataFrame(mix_abc)
        s1 = Series({"b": r"\s*\.\s*"})
        s2 = Series({"b": np.nan})
        res = df.replace(s1, s2, regex=True)
        res2 = df.copy()
        return_value = res2.replace(s1, s2, inplace=True, regex=True)
        assert return_value is None
        res3 = df.copy()
        return_value = res3.replace(regex=s1, value=s2, inplace=True)
        assert return_value is None
        expec = DataFrame(
            {"a": mix_abc["a"], "b": ["a", "b", np.nan, np.nan], "c": mix_abc["c"]}
        )
        tm.assert_frame_equal(res, expec)
        tm.assert_frame_equal(res2, expec)
        tm.assert_frame_equal(res3, expec)

    def test_regex_replace_numeric_to_object_conversion(self, mix_abc):
        df = DataFrame(mix_abc)
        expec = DataFrame({"a": ["a", 1, 2, 3], "b": mix_abc["b"], "c": mix_abc["c"]})
        res = df.replace(0, "a")
        tm.assert_frame_equal(res, expec)
        assert res.a.dtype == np.object_

    @pytest.mark.parametrize(
        "to_replace", [{"": np.nan, ",": ""}, {",": "", "": np.nan}]
    )
    def test_joint_simple_replace_and_regex_replace(self, to_replace):
        # GH-39338
        df = DataFrame(
            {
                "col1": ["1,000", "a", "3"],
                "col2": ["a", "", "b"],
                "col3": ["a", "b", "c"],
            }
        )
        result = df.replace(regex=to_replace)
        expected = DataFrame(
            {
                "col1": ["1000", "a", "3"],
                "col2": ["a", np.nan, "b"],
                "col3": ["a", "b", "c"],
            }
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("metachar", ["[]", "()", r"\d", r"\w", r"\s"])
    def test_replace_regex_metachar(self, metachar):
        df = DataFrame({"a": [metachar, "else"]})
        result = df.replace({"a": {metachar: "paren"}})
        expected = DataFrame({"a": ["paren", "else"]})
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "data,to_replace,expected",
        [
            (["xax", "xbx"], {"a": "c", "b": "d"}, ["xcx", "xdx"]),
            (["d", "", ""], {r"^\s*$": pd.NA}, ["d", pd.NA, pd.NA]),
        ],
    )
    def test_regex_replace_string_types(
        self, data, to_replace, expected, frame_or_series, any_string_dtype
    ):
        # GH-41333, GH-35977
        dtype = any_string_dtype
        obj = frame_or_series(data, dtype=dtype)
        result = obj.replace(to_replace, regex=True)
        expected = frame_or_series(expected, dtype=dtype)

        tm.assert_equal(result, expected)

    def test_replace(self, datetime_frame):
        datetime_frame.loc[datetime_frame.index[:5], "A"] = np.nan
        datetime_frame.loc[datetime_frame.index[-5:], "A"] = np.nan

        zero_filled = datetime_frame.replace(np.nan, -1e8)
        tm.assert_frame_equal(zero_filled, datetime_frame.fillna(-1e8))
        tm.assert_frame_equal(zero_filled.replace(-1e8, np.nan), datetime_frame)

        datetime_frame.loc[datetime_frame.index[:5], "A"] = np.nan
        datetime_frame.loc[datetime_frame.index[-5:], "A"] = np.nan
        datetime_frame.loc[datetime_frame.index[:5], "B"] = -1e8

        # empty
        df = DataFrame(index=["a", "b"])
        tm.assert_frame_equal(df, df.replace(5, 7))

        # GH 11698
        # test for mixed data types.
        df = DataFrame(
            [("-", pd.to_datetime("20150101")), ("a", pd.to_datetime("20150102"))]
        )
        df1 = df.replace("-", np.nan)
        expected_df = DataFrame(
            [(np.nan, pd.to_datetime("20150101")), ("a", pd.to_datetime("20150102"))]
        )
        tm.assert_frame_equal(df1, expected_df)

    def test_replace_list(self):
        obj = {"a": list("ab.."), "b": list("efgh"), "c": list("helo")}
        dfobj = DataFrame(obj)

        # lists of regexes and values
        # list of [v1, v2, ..., vN] -> [v1, v2, ..., vN]
        to_replace_res = [r".", r"e"]
        values = [np.nan, "crap"]
        res = dfobj.replace(to_replace_res, values)
        expec = DataFrame(
            {
                "a": ["a", "b", np.nan, np.nan],
                "b": ["crap", "f", "g", "h"],
                "c": ["h", "crap", "l", "o"],
            }
        )
        tm.assert_frame_equal(res, expec)

        # list of [v1, v2, ..., vN] -> [v1, v2, .., vN]
        to_replace_res = [r".", r"f"]
        values = [r"..", r"crap"]
        res = dfobj.replace(to_replace_res, values)
        expec = DataFrame(
            {
                "a": ["a", "b", "..", ".."],
                "b": ["e", "crap", "g", "h"],
                "c": ["h", "e", "l", "o"],
            }
        )
        tm.assert_frame_equal(res, expec)

    def test_replace_with_empty_list(self, frame_or_series):
        # GH 21977
        ser = Series([["a", "b"], [], np.nan, [1]])
        obj = DataFrame({"col": ser})
        obj = tm.get_obj(obj, frame_or_series)
        expected = obj
        result = obj.replace([], np.nan)
        tm.assert_equal(result, expected)

        # GH 19266
        msg = (
            "NumPy boolean array indexing assignment cannot assign {size} "
            "input values to the 1 output values where the mask is true"
        )
        with pytest.raises(ValueError, match=msg.format(size=0)):
            obj.replace({np.nan: []})
        with pytest.raises(ValueError, match=msg.format(size=2)):
            obj.replace({np.nan: ["dummy", "alt"]})

    def test_replace_series_dict(self):
        # from GH 3064
        df = DataFrame({"zero": {"a": 0.0, "b": 1}, "one": {"a": 2.0, "b": 0}})
        result = df.replace(0, {"zero": 0.5, "one": 1.0})
        expected = DataFrame({"zero": {"a": 0.5, "b": 1}, "one": {"a": 2.0, "b": 1.0}})
        tm.assert_frame_equal(result, expected)

        result = df.replace(0, df.mean())
        tm.assert_frame_equal(result, expected)

        # series to series/dict
        df = DataFrame({"zero": {"a": 0.0, "b": 1}, "one": {"a": 2.0, "b": 0}})
        s = Series({"zero": 0.0, "one": 2.0})
        result = df.replace(s, {"zero": 0.5, "one": 1.0})
        expected = DataFrame({"zero": {"a": 0.5, "b": 1}, "one": {"a": 1.0, "b": 0.0}})
        tm.assert_frame_equal(result, expected)

        result = df.replace(s, df.mean())
        tm.assert_frame_equal(result, expected)

    def test_replace_convert(self):
        # gh 3907
        df = DataFrame([["foo", "bar", "bah"], ["bar", "foo", "bah"]])
        m = {"foo": 1, "bar": 2, "bah": 3}
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rep = df.replace(m)
        expec = Series([np.int64] * 3)
        res = rep.dtypes
        tm.assert_series_equal(expec, res)

    def test_replace_mixed(self, float_string_frame):
        mf = float_string_frame
        mf.iloc[5:20, mf.columns.get_loc("foo")] = np.nan
        mf.iloc[-10:, mf.columns.get_loc("A")] = np.nan

        result = float_string_frame.replace(np.nan, -18)
        expected = float_string_frame.copy()
        expected["foo"] = expected["foo"].astype(object)
        expected = expected.fillna(value=-18)
        tm.assert_frame_equal(result, expected)
        expected2 = float_string_frame.copy()
        expected2["foo"] = expected2["foo"].astype(object)
        tm.assert_frame_equal(result.replace(-18, np.nan), expected2)

        result = float_string_frame.replace(np.nan, -1e8)
        expected = float_string_frame.copy()
        expected["foo"] = expected["foo"].astype(object)
        expected = expected.fillna(value=-1e8)
        tm.assert_frame_equal(result, expected)
        expected2 = float_string_frame.copy()
        expected2["foo"] = expected2["foo"].astype(object)
        tm.assert_frame_equal(result.replace(-1e8, np.nan), expected2)

    def test_replace_mixed_int_block_upcasting(self):
        # int block upcasting
        df = DataFrame(
            {
                "A": Series([1.0, 2.0], dtype="float64"),
                "B": Series([0, 1], dtype="int64"),
            }
        )
        expected = DataFrame(
            {
                "A": Series([1.0, 2.0], dtype="float64"),
                "B": Series([0.5, 1], dtype="float64"),
            }
        )
        result = df.replace(0, 0.5)
        tm.assert_frame_equal(result, expected)

        return_value = df.replace(0, 0.5, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(df, expected)

    def test_replace_mixed_int_block_splitting(self):
        # int block splitting
        df = DataFrame(
            {
                "A": Series([1.0, 2.0], dtype="float64"),
                "B": Series([0, 1], dtype="int64"),
                "C": Series([1, 2], dtype="int64"),
            }
        )
        expected = DataFrame(
            {
                "A": Series([1.0, 2.0], dtype="float64"),
                "B": Series([0.5, 1], dtype="float64"),
                "C": Series([1, 2], dtype="int64"),
            }
        )
        result = df.replace(0, 0.5)
        tm.assert_frame_equal(result, expected)

    def test_replace_mixed2(self, using_infer_string):
        # to object block upcasting
        df = DataFrame(
            {
                "A": Series([1.0, 2.0], dtype="float64"),
                "B": Series([0, 1], dtype="int64"),
            }
        )
        expected = DataFrame(
            {
                "A": Series([1, "foo"], dtype="object"),
                "B": Series([0, 1], dtype="int64"),
            }
        )
        result = df.replace(2, "foo")
        tm.assert_frame_equal(result, expected)

        expected = DataFrame(
            {
                "A": Series(["foo", "bar"], dtype="object"),
                "B": Series([0, "foo"], dtype="object"),
            }
        )
        result = df.replace([1, 2], ["foo", "bar"])
        tm.assert_frame_equal(result, expected)

    def test_replace_mixed3(self):
        # test case from
        df = DataFrame(
            {"A": Series([3, 0], dtype="int64"), "B": Series([0, 3], dtype="int64")}
        )
        result = df.replace(3, df.mean().to_dict())
        expected = df.copy().astype("float64")
        m = df.mean()
        expected.iloc[0, 0] = m.iloc[0]
        expected.iloc[1, 1] = m.iloc[1]
        tm.assert_frame_equal(result, expected)

    def test_replace_nullable_int_with_string_doesnt_cast(self):
        # GH#25438 don't cast df['a'] to float64
        df = DataFrame({"a": [1, 2, 3, np.nan], "b": ["some", "strings", "here", "he"]})
        df["a"] = df["a"].astype("Int64")

        res = df.replace("", np.nan)
        tm.assert_series_equal(res["a"], df["a"])

    @pytest.mark.parametrize("dtype", ["boolean", "Int64", "Float64"])
    def test_replace_with_nullable_column(self, dtype):
        # GH-44499
        nullable_ser = Series([1, 0, 1], dtype=dtype)
        df = DataFrame({"A": ["A", "B", "x"], "B": nullable_ser})
        result = df.replace("x", "X")
        expected = DataFrame({"A": ["A", "B", "X"], "B": nullable_ser})
        tm.assert_frame_equal(result, expected)

    def test_replace_simple_nested_dict(self):
        df = DataFrame({"col": range(1, 5)})
        expected = DataFrame({"col": ["a", 2, 3, "b"]})

        result = df.replace({"col": {1: "a", 4: "b"}})
        tm.assert_frame_equal(expected, result)

        # in this case, should be the same as the not nested version
        result = df.replace({1: "a", 4: "b"})
        tm.assert_frame_equal(expected, result)

    def test_replace_simple_nested_dict_with_nonexistent_value(self):
        df = DataFrame({"col": range(1, 5)})
        expected = DataFrame({"col": ["a", 2, 3, "b"]})

        result = df.replace({-1: "-", 1: "a", 4: "b"})
        tm.assert_frame_equal(expected, result)

        result = df.replace({"col": {-1: "-", 1: "a", 4: "b"}})
        tm.assert_frame_equal(expected, result)

    def test_replace_NA_with_None(self):
        # gh-45601
        df = DataFrame({"value": [42, None]}).astype({"value": "Int64"})
        result = df.replace({pd.NA: None})
        expected = DataFrame({"value": [42, None]}, dtype=object)
        tm.assert_frame_equal(result, expected)

    def test_replace_NAT_with_None(self):
        # gh-45836
        df = DataFrame([pd.NaT, pd.NaT])
        result = df.replace({pd.NaT: None, np.nan: None})
        expected = DataFrame([None, None])
        tm.assert_frame_equal(result, expected)

    def test_replace_with_None_keeps_categorical(self):
        # gh-46634
        cat_series = Series(["b", "b", "b", "d"], dtype="category")
        df = DataFrame(
            {
                "id": Series([5, 4, 3, 2], dtype="float64"),
                "col": cat_series,
            }
        )
        result = df.replace({3: None})

        expected = DataFrame(
            {
                "id": Series([5.0, 4.0, None, 2.0], dtype="object"),
                "col": cat_series,
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_replace_value_is_none(self, datetime_frame):
        orig_value = datetime_frame.iloc[0, 0]
        orig2 = datetime_frame.iloc[1, 0]

        datetime_frame.iloc[0, 0] = np.nan
        datetime_frame.iloc[1, 0] = 1

        result = datetime_frame.replace(to_replace={np.nan: 0})
        expected = datetime_frame.T.replace(to_replace={np.nan: 0}).T
        tm.assert_frame_equal(result, expected)

        result = datetime_frame.replace(to_replace={np.nan: 0, 1: -1e8})
        tsframe = datetime_frame.copy()
        tsframe.iloc[0, 0] = 0
        tsframe.iloc[1, 0] = -1e8
        expected = tsframe
        tm.assert_frame_equal(expected, result)
        datetime_frame.iloc[0, 0] = orig_value
        datetime_frame.iloc[1, 0] = orig2

    def test_replace_for_new_dtypes(self, datetime_frame):
        # dtypes
        tsframe = datetime_frame.copy().astype(np.float32)
        tsframe.loc[tsframe.index[:5], "A"] = np.nan
        tsframe.loc[tsframe.index[-5:], "A"] = np.nan

        zero_filled = tsframe.replace(np.nan, -1e8)
        tm.assert_frame_equal(zero_filled, tsframe.fillna(-1e8))
        tm.assert_frame_equal(zero_filled.replace(-1e8, np.nan), tsframe)

        tsframe.loc[tsframe.index[:5], "A"] = np.nan
        tsframe.loc[tsframe.index[-5:], "A"] = np.nan
        tsframe.loc[tsframe.index[:5], "B"] = np.nan
        msg = "DataFrame.fillna with 'method' is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            # TODO: what is this even testing?
            result = tsframe.fillna(method="bfill")
            tm.assert_frame_equal(result, tsframe.fillna(method="bfill"))

    @pytest.mark.parametrize(
        "frame, to_replace, value, expected",
        [
            (DataFrame({"ints": [1, 2, 3]}), 1, 0, DataFrame({"ints": [0, 2, 3]})),
            (
                DataFrame({"ints": [1, 2, 3]}, dtype=np.int32),
                1,
                0,
                DataFrame({"ints": [0, 2, 3]}, dtype=np.int32),
            ),
            (
                DataFrame({"ints": [1, 2, 3]}, dtype=np.int16),
                1,
                0,
                DataFrame({"ints": [0, 2, 3]}, dtype=np.int16),
            ),
            (
                DataFrame({"bools": [True, False, True]}),
                False,
                True,
                DataFrame({"bools": [True, True, True]}),
            ),
            (
                DataFrame({"complex": [1j, 2j, 3j]}),
                1j,
                0,
                DataFrame({"complex": [0j, 2j, 3j]}),
            ),
            (
                DataFrame(
                    {
                        "datetime64": Index(
                            [
                                datetime(2018, 5, 28),
                                datetime(2018, 7, 28),
                                datetime(2018, 5, 28),
                            ]
                        )
                    }
                ),
                datetime(2018, 5, 28),
                datetime(2018, 7, 28),
                DataFrame({"datetime64": Index([datetime(2018, 7, 28)] * 3)}),
            ),
            # GH 20380
            (
                DataFrame({"dt": [datetime(3017, 12, 20)], "str": ["foo"]}),
                "foo",
                "bar",
                DataFrame({"dt": [datetime(3017, 12, 20)], "str": ["bar"]}),
            ),
            # GH 36782
            (
                DataFrame({"dt": [datetime(2920, 10, 1)]}),
                datetime(2920, 10, 1),
                datetime(2020, 10, 1),
                DataFrame({"dt": [datetime(2020, 10, 1)]}),
            ),
            (
                DataFrame(
                    {
                        "A": date_range("20130101", periods=3, tz="US/Eastern"),
                        "B": [0, np.nan, 2],
                    }
                ),
                Timestamp("20130102", tz="US/Eastern"),
                Timestamp("20130104", tz="US/Eastern"),
                DataFrame(
                    {
                        "A": pd.DatetimeIndex(
                            [
                                Timestamp("20130101", tz="US/Eastern"),
                                Timestamp("20130104", tz="US/Eastern"),
                                Timestamp("20130103", tz="US/Eastern"),
                            ]
                        ).as_unit("ns"),
                        "B": [0, np.nan, 2],
                    }
                ),
            ),
            # GH 35376
            (
                DataFrame([[1, 1.0], [2, 2.0]]),
                1.0,
                5,
                DataFrame([[5, 5.0], [2, 2.0]]),
            ),
            (
                DataFrame([[1, 1.0], [2, 2.0]]),
                1,
                5,
                DataFrame([[5, 5.0], [2, 2.0]]),
            ),
            (
                DataFrame([[1, 1.0], [2, 2.0]]),
                1.0,
                5.0,
                DataFrame([[5, 5.0], [2, 2.0]]),
            ),
            (
                DataFrame([[1, 1.0], [2, 2.0]]),
                1,
                5.0,
                DataFrame([[5, 5.0], [2, 2.0]]),
            ),
        ],
    )
    def test_replace_dtypes(self, frame, to_replace, value, expected):
        warn = None
        if isinstance(to_replace, datetime) and to_replace.year == 2920:
            warn = FutureWarning
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(warn, match=msg):
            result = frame.replace(to_replace, value)
        tm.assert_frame_equal(result, expected)

    def test_replace_input_formats_listlike(self):
        # both dicts
        to_rep = {"A": np.nan, "B": 0, "C": ""}
        values = {"A": 0, "B": -1, "C": "missing"}
        df = DataFrame(
            {"A": [np.nan, 0, np.inf], "B": [0, 2, 5], "C": ["", "asdf", "fd"]}
        )
        filled = df.replace(to_rep, values)
        expected = {k: v.replace(to_rep[k], values[k]) for k, v in df.items()}
        tm.assert_frame_equal(filled, DataFrame(expected))

        result = df.replace([0, 2, 5], [5, 2, 0])
        expected = DataFrame(
            {"A": [np.nan, 5, np.inf], "B": [5, 2, 0], "C": ["", "asdf", "fd"]}
        )
        tm.assert_frame_equal(result, expected)

        # scalar to dict
        values = {"A": 0, "B": -1, "C": "missing"}
        df = DataFrame(
            {"A": [np.nan, 0, np.nan], "B": [0, 2, 5], "C": ["", "asdf", "fd"]}
        )
        filled = df.replace(np.nan, values)
        expected = {k: v.replace(np.nan, values[k]) for k, v in df.items()}
        tm.assert_frame_equal(filled, DataFrame(expected))

        # list to list
        to_rep = [np.nan, 0, ""]
        values = [-2, -1, "missing"]
        result = df.replace(to_rep, values)
        expected = df.copy()
        for rep, value in zip(to_rep, values):
            return_value = expected.replace(rep, value, inplace=True)
            assert return_value is None
        tm.assert_frame_equal(result, expected)

        msg = r"Replacement lists must match in length\. Expecting 3 got 2"
        with pytest.raises(ValueError, match=msg):
            df.replace(to_rep, values[1:])

    def test_replace_input_formats_scalar(self):
        df = DataFrame(
            {"A": [np.nan, 0, np.inf], "B": [0, 2, 5], "C": ["", "asdf", "fd"]}
        )

        # dict to scalar
        to_rep = {"A": np.nan, "B": 0, "C": ""}
        filled = df.replace(to_rep, 0)
        expected = {k: v.replace(to_rep[k], 0) for k, v in df.items()}
        tm.assert_frame_equal(filled, DataFrame(expected))

        msg = "value argument must be scalar, dict, or Series"
        with pytest.raises(TypeError, match=msg):
            df.replace(to_rep, [np.nan, 0, ""])

        # list to scalar
        to_rep = [np.nan, 0, ""]
        result = df.replace(to_rep, -1)
        expected = df.copy()
        for rep in to_rep:
            return_value = expected.replace(rep, -1, inplace=True)
            assert return_value is None
        tm.assert_frame_equal(result, expected)

    def test_replace_limit(self):
        # TODO
        pass

    def test_replace_dict_no_regex(self, any_string_dtype):
        answer = Series(
            {
                0: "Strongly Agree",
                1: "Agree",
                2: "Neutral",
                3: "Disagree",
                4: "Strongly Disagree",
            },
            dtype=any_string_dtype,
        )
        weights = {
            "Agree": 4,
            "Disagree": 2,
            "Neutral": 3,
            "Strongly Agree": 5,
            "Strongly Disagree": 1,
        }
        expected = Series({0: 5, 1: 4, 2: 3, 3: 2, 4: 1})
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = answer.replace(weights)
        tm.assert_series_equal(result, expected)

    def test_replace_series_no_regex(self, any_string_dtype):
        answer = Series(
            {
                0: "Strongly Agree",
                1: "Agree",
                2: "Neutral",
                3: "Disagree",
                4: "Strongly Disagree",
            },
            dtype=any_string_dtype,
        )
        weights = Series(
            {
                "Agree": 4,
                "Disagree": 2,
                "Neutral": 3,
                "Strongly Agree": 5,
                "Strongly Disagree": 1,
            }
        )
        expected = Series({0: 5, 1: 4, 2: 3, 3: 2, 4: 1})
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = answer.replace(weights)
        tm.assert_series_equal(result, expected)

    def test_replace_dict_tuple_list_ordering_remains_the_same(self):
        df = DataFrame({"A": [np.nan, 1]})
        res1 = df.replace(to_replace={np.nan: 0, 1: -1e8})
        res2 = df.replace(to_replace=(1, np.nan), value=[-1e8, 0])
        res3 = df.replace(to_replace=[1, np.nan], value=[-1e8, 0])

        expected = DataFrame({"A": [0, -1e8]})
        tm.assert_frame_equal(res1, res2)
        tm.assert_frame_equal(res2, res3)
        tm.assert_frame_equal(res3, expected)

    def test_replace_doesnt_replace_without_regex(self):
        df = DataFrame(
            {
                "fol": [1, 2, 2, 3],
                "T_opp": ["0", "vr", "0", "0"],
                "T_Dir": ["0", "0", "0", "bt"],
                "T_Enh": ["vo", "0", "0", "0"],
            }
        )
        res = df.replace({r"\D": 1})
        tm.assert_frame_equal(df, res)

    def test_replace_bool_with_string(self):
        df = DataFrame({"a": [True, False], "b": list("ab")})
        result = df.replace(True, "a")
        expected = DataFrame({"a": ["a", False], "b": df.b})
        tm.assert_frame_equal(result, expected)

    def test_replace_pure_bool_with_string_no_op(self):
        df = DataFrame(np.random.default_rng(2).random((2, 2)) > 0.5)
        result = df.replace("asdf", "fdsa")
        tm.assert_frame_equal(df, result)

    def test_replace_bool_with_bool(self):
        df = DataFrame(np.random.default_rng(2).random((2, 2)) > 0.5)
        result = df.replace(False, True)
        expected = DataFrame(np.ones((2, 2), dtype=bool))
        tm.assert_frame_equal(result, expected)

    def test_replace_with_dict_with_bool_keys(self):
        df = DataFrame({0: [True, False], 1: [False, True]})
        result = df.replace({"asdf": "asdb", True: "yes"})
        expected = DataFrame({0: ["yes", False], 1: [False, "yes"]})
        tm.assert_frame_equal(result, expected)

    def test_replace_dict_strings_vs_ints(self):
        # GH#34789
        df = DataFrame({"Y0": [1, 2], "Y1": [3, 4]})
        result = df.replace({"replace_string": "test"})

        tm.assert_frame_equal(result, df)

        result = df["Y0"].replace({"replace_string": "test"})
        tm.assert_series_equal(result, df["Y0"])

    def test_replace_truthy(self):
        df = DataFrame({"a": [True, True]})
        r = df.replace([np.inf, -np.inf], np.nan)
        e = df
        tm.assert_frame_equal(r, e)

    def test_nested_dict_overlapping_keys_replace_int(self):
        # GH 27660 keep behaviour consistent for simple dictionary and
        # nested dictionary replacement
        df = DataFrame({"a": list(range(1, 5))})

        result = df.replace({"a": dict(zip(range(1, 5), range(2, 6)))})
        expected = df.replace(dict(zip(range(1, 5), range(2, 6))))
        tm.assert_frame_equal(result, expected)

    def test_nested_dict_overlapping_keys_replace_str(self):
        # GH 27660
        a = np.arange(1, 5)
        astr = a.astype(str)
        bstr = np.arange(2, 6).astype(str)
        df = DataFrame({"a": astr})
        result = df.replace(dict(zip(astr, bstr)))
        expected = df.replace({"a": dict(zip(astr, bstr))})
        tm.assert_frame_equal(result, expected)

    def test_replace_swapping_bug(self):
        df = DataFrame({"a": [True, False, True]})
        res = df.replace({"a": {True: "Y", False: "N"}})
        expect = DataFrame({"a": ["Y", "N", "Y"]}, dtype=object)
        tm.assert_frame_equal(res, expect)

        df = DataFrame({"a": [0, 1, 0]})
        res = df.replace({"a": {0: "Y", 1: "N"}})
        expect = DataFrame({"a": ["Y", "N", "Y"]}, dtype=object)
        tm.assert_frame_equal(res, expect)

    def test_replace_period(self):
        d = {
            "fname": {
                "out_augmented_AUG_2011.json": pd.Period(year=2011, month=8, freq="M"),
                "out_augmented_JAN_2011.json": pd.Period(year=2011, month=1, freq="M"),
                "out_augmented_MAY_2012.json": pd.Period(year=2012, month=5, freq="M"),
                "out_augmented_SUBSIDY_WEEK.json": pd.Period(
                    year=2011, month=4, freq="M"
                ),
                "out_augmented_AUG_2012.json": pd.Period(year=2012, month=8, freq="M"),
                "out_augmented_MAY_2011.json": pd.Period(year=2011, month=5, freq="M"),
                "out_augmented_SEP_2013.json": pd.Period(year=2013, month=9, freq="M"),
            }
        }

        df = DataFrame(
            [
                "out_augmented_AUG_2012.json",
                "out_augmented_SEP_2013.json",
                "out_augmented_SUBSIDY_WEEK.json",
                "out_augmented_MAY_2012.json",
                "out_augmented_MAY_2011.json",
                "out_augmented_AUG_2011.json",
                "out_augmented_JAN_2011.json",
            ],
            columns=["fname"],
        )
        assert set(df.fname.values) == set(d["fname"].keys())

        expected = DataFrame({"fname": [d["fname"][k] for k in df.fname.values]})
        assert expected.dtypes.iloc[0] == "Period[M]"
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.replace(d)
        tm.assert_frame_equal(result, expected)

    def test_replace_datetime(self):
        d = {
            "fname": {
                "out_augmented_AUG_2011.json": Timestamp("2011-08"),
                "out_augmented_JAN_2011.json": Timestamp("2011-01"),
                "out_augmented_MAY_2012.json": Timestamp("2012-05"),
                "out_augmented_SUBSIDY_WEEK.json": Timestamp("2011-04"),
                "out_augmented_AUG_2012.json": Timestamp("2012-08"),
                "out_augmented_MAY_2011.json": Timestamp("2011-05"),
                "out_augmented_SEP_2013.json": Timestamp("2013-09"),
            }
        }

        df = DataFrame(
            [
                "out_augmented_AUG_2012.json",
                "out_augmented_SEP_2013.json",
                "out_augmented_SUBSIDY_WEEK.json",
                "out_augmented_MAY_2012.json",
                "out_augmented_MAY_2011.json",
                "out_augmented_AUG_2011.json",
                "out_augmented_JAN_2011.json",
            ],
            columns=["fname"],
        )
        assert set(df.fname.values) == set(d["fname"].keys())
        expected = DataFrame({"fname": [d["fname"][k] for k in df.fname.values]})
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.replace(d)
        tm.assert_frame_equal(result, expected)

    def test_replace_datetimetz(self):
        # GH 11326
        # behaving poorly when presented with a datetime64[ns, tz]
        df = DataFrame(
            {
                "A": date_range("20130101", periods=3, tz="US/Eastern"),
                "B": [0, np.nan, 2],
            }
        )
        result = df.replace(np.nan, 1)
        expected = DataFrame(
            {
                "A": date_range("20130101", periods=3, tz="US/Eastern"),
                "B": Series([0, 1, 2], dtype="float64"),
            }
        )
        tm.assert_frame_equal(result, expected)

        result = df.fillna(1)
        tm.assert_frame_equal(result, expected)

        result = df.replace(0, np.nan)
        expected = DataFrame(
            {
                "A": date_range("20130101", periods=3, tz="US/Eastern"),
                "B": [np.nan, np.nan, 2],
            }
        )
        tm.assert_frame_equal(result, expected)

        result = df.replace(
            Timestamp("20130102", tz="US/Eastern"),
            Timestamp("20130104", tz="US/Eastern"),
        )
        expected = DataFrame(
            {
                "A": [
                    Timestamp("20130101", tz="US/Eastern"),
                    Timestamp("20130104", tz="US/Eastern"),
                    Timestamp("20130103", tz="US/Eastern"),
                ],
                "B": [0, np.nan, 2],
            }
        )
        expected["A"] = expected["A"].dt.as_unit("ns")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        result.iloc[1, 0] = np.nan
        result = result.replace({"A": pd.NaT}, Timestamp("20130104", tz="US/Eastern"))
        tm.assert_frame_equal(result, expected)

        # pre-2.0 this would coerce to object with mismatched tzs
        result = df.copy()
        result.iloc[1, 0] = np.nan
        result = result.replace({"A": pd.NaT}, Timestamp("20130104", tz="US/Pacific"))
        expected = DataFrame(
            {
                "A": [
                    Timestamp("20130101", tz="US/Eastern"),
                    Timestamp("20130104", tz="US/Pacific").tz_convert("US/Eastern"),
                    Timestamp("20130103", tz="US/Eastern"),
                ],
                "B": [0, np.nan, 2],
            }
        )
        expected["A"] = expected["A"].dt.as_unit("ns")
        tm.assert_frame_equal(result, expected)

        result = df.copy()
        result.iloc[1, 0] = np.nan
        result = result.replace({"A": np.nan}, Timestamp("20130104"))
        expected = DataFrame(
            {
                "A": [
                    Timestamp("20130101", tz="US/Eastern"),
                    Timestamp("20130104"),
                    Timestamp("20130103", tz="US/Eastern"),
                ],
                "B": [0, np.nan, 2],
            }
        )
        tm.assert_frame_equal(result, expected)

    def test_replace_with_empty_dictlike(self, mix_abc):
        # GH 15289
        df = DataFrame(mix_abc)
        tm.assert_frame_equal(df, df.replace({}))
        tm.assert_frame_equal(df, df.replace(Series([], dtype=object)))

        tm.assert_frame_equal(df, df.replace({"b": {}}))
        tm.assert_frame_equal(df, df.replace(Series({"b": {}})))

    @pytest.mark.parametrize(
        "to_replace, method, expected",
        [
            (0, "bfill", {"A": [1, 1, 2], "B": [5, np.nan, 7], "C": ["a", "b", "c"]}),
            (
                np.nan,
                "bfill",
                {"A": [0, 1, 2], "B": [5.0, 7.0, 7.0], "C": ["a", "b", "c"]},
            ),
            ("d", "ffill", {"A": [0, 1, 2], "B": [5, np.nan, 7], "C": ["a", "b", "c"]}),
            (
                [0, 2],
                "bfill",
                {"A": [1, 1, 2], "B": [5, np.nan, 7], "C": ["a", "b", "c"]},
            ),
            (
                [1, 2],
                "pad",
                {"A": [0, 0, 0], "B": [5, np.nan, 7], "C": ["a", "b", "c"]},
            ),
            (
                (1, 2),
                "bfill",
                {"A": [0, 2, 2], "B": [5, np.nan, 7], "C": ["a", "b", "c"]},
            ),
            (
                ["b", "c"],
                "ffill",
                {"A": [0, 1, 2], "B": [5, np.nan, 7], "C": ["a", "a", "a"]},
            ),
        ],
    )
    def test_replace_method(self, to_replace, method, expected):
        # GH 19632
        df = DataFrame({"A": [0, 1, 2], "B": [5, np.nan, 7], "C": ["a", "b", "c"]})

        msg = "The 'method' keyword in DataFrame.replace is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.replace(to_replace=to_replace, value=None, method=method)
        expected = DataFrame(expected)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "replace_dict, final_data",
        [({"a": 1, "b": 1}, [[3, 3], [2, 2]]), ({"a": 1, "b": 2}, [[3, 1], [2, 3]])],
    )
    def test_categorical_replace_with_dict(self, replace_dict, final_data):
        # GH 26988
        df = DataFrame([[1, 1], [2, 2]], columns=["a", "b"], dtype="category")

        final_data = np.array(final_data)

        a = pd.Categorical(final_data[:, 0], categories=[3, 2])

        ex_cat = [3, 2] if replace_dict["b"] == 1 else [1, 3]
        b = pd.Categorical(final_data[:, 1], categories=ex_cat)

        expected = DataFrame({"a": a, "b": b})
        msg2 = "with CategoricalDtype is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg2):
            result = df.replace(replace_dict, 3)
        tm.assert_frame_equal(result, expected)
        msg = (
            r"Attributes of DataFrame.iloc\[:, 0\] \(column name=\"a\"\) are "
            "different"
        )
        with pytest.raises(AssertionError, match=msg):
            # ensure non-inplace call does not affect original
            tm.assert_frame_equal(df, expected)
        with tm.assert_produces_warning(FutureWarning, match=msg2):
            return_value = df.replace(replace_dict, 3, inplace=True)
        assert return_value is None
        tm.assert_frame_equal(df, expected)

    @pytest.mark.parametrize(
        "df, to_replace, exp",
        [
            (
                {"col1": [1, 2, 3], "col2": [4, 5, 6]},
                {4: 5, 5: 6, 6: 7},
                {"col1": [1, 2, 3], "col2": [5, 6, 7]},
            ),
            (
                {"col1": [1, 2, 3], "col2": ["4", "5", "6"]},
                {"4": "5", "5": "6", "6": "7"},
                {"col1": [1, 2, 3], "col2": ["5", "6", "7"]},
            ),
        ],
    )
    def test_replace_commutative(self, df, to_replace, exp):
        # GH 16051
        # DataFrame.replace() overwrites when values are non-numeric
        # also added to data frame whilst issue was for series

        df = DataFrame(df)

        expected = DataFrame(exp)
        result = df.replace(to_replace)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "replacer",
        [
            Timestamp("20170827"),
            np.int8(1),
            np.int16(1),
            np.float32(1),
            np.float64(1),
        ],
    )
    def test_replace_replacer_dtype(self, replacer):
        # GH26632
        df = DataFrame(["a"], dtype=object)
        msg = "Downcasting behavior in `replace` "
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = df.replace({"a": replacer, "b": replacer})
        expected = DataFrame([replacer])
        tm.assert_frame_equal(result, expected)

    def test_replace_after_convert_dtypes(self):
        # GH31517
        df = DataFrame({"grp": [1, 2, 3, 4, 5]}, dtype="Int64")
        result = df.replace(1, 10)
        expected = DataFrame({"grp": [10, 2, 3, 4, 5]}, dtype="Int64")
        tm.assert_frame_equal(result, expected)

    def test_replace_invalid_to_replace(self):
        # GH 18634
        # API: replace() should raise an exception if invalid argument is given
        df = DataFrame({"one": ["a", "b ", "c"], "two": ["d ", "e ", "f "]})
        msg = (
            r"Expecting 'to_replace' to be either a scalar, array-like, "
            r"dict or None, got invalid type.*"
        )
        msg2 = (
            "DataFrame.replace without 'value' and with non-dict-like "
            "'to_replace' is deprecated"
        )
        with pytest.raises(TypeError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=msg2):
                df.replace(lambda x: x.strip())

    @pytest.mark.parametrize("dtype", ["float", "float64", "int64", "Int64", "boolean"])
    @pytest.mark.parametrize("value", [np.nan, pd.NA])
    def test_replace_no_replacement_dtypes(self, dtype, value):
        # https://github.com/pandas-dev/pandas/issues/32988
        df = DataFrame(np.eye(2), dtype=dtype)
        result = df.replace(to_replace=[None, -np.inf, np.inf], value=value)
        tm.assert_frame_equal(result, df)

    @pytest.mark.parametrize("replacement", [np.nan, 5])
    def test_replace_with_duplicate_columns(self, replacement):
        # GH 24798
        result = DataFrame({"A": [1, 2, 3], "A1": [4, 5, 6], "B": [7, 8, 9]})
        result.columns = list("AAB")

        expected = DataFrame(
            {"A": [1, 2, 3], "A1": [4, 5, 6], "B": [replacement, 8, 9]}
        )
        expected.columns = list("AAB")

        result["B"] = result["B"].replace(7, replacement)

        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("value", [pd.Period("2020-01"), pd.Interval(0, 5)])
    def test_replace_ea_ignore_float(self, frame_or_series, value):
        # GH#34871
        obj = DataFrame({"Per": [value] * 3})
        obj = tm.get_obj(obj, frame_or_series)

        expected = obj.copy()
        result = obj.replace(1.0, 0.0)
        tm.assert_equal(expected, result)

    def test_replace_value_category_type(self):
        """
        Test for #23305: to ensure category dtypes are maintained
        after replace with direct values
        """

        # create input data
        input_dict = {
            "col1": [1, 2, 3, 4],
            "col2": ["a", "b", "c", "d"],
            "col3": [1.5, 2.5, 3.5, 4.5],
            "col4": ["cat1", "cat2", "cat3", "cat4"],
            "col5": ["obj1", "obj2", "obj3", "obj4"],
        }
        # explicitly cast columns as category and order them
        input_df = DataFrame(data=input_dict).astype(
            {"col2": "category", "col4": "category"}
        )
        input_df["col2"] = input_df["col2"].cat.reorder_categories(
            ["a", "b", "c", "d"], ordered=True
        )
        input_df["col4"] = input_df["col4"].cat.reorder_categories(
            ["cat1", "cat2", "cat3", "cat4"], ordered=True
        )

        # create expected dataframe
        expected_dict = {
            "col1": [1, 2, 3, 4],
            "col2": ["a", "b", "c", "z"],
            "col3": [1.5, 2.5, 3.5, 4.5],
            "col4": ["cat1", "catX", "cat3", "cat4"],
            "col5": ["obj9", "obj2", "obj3", "obj4"],
        }
        # explicitly cast columns as category and order them
        expected = DataFrame(data=expected_dict).astype(
            {"col2": "category", "col4": "category"}
        )
        expected["col2"] = expected["col2"].cat.reorder_categories(
            ["a", "b", "c", "z"], ordered=True
        )
        expected["col4"] = expected["col4"].cat.reorder_categories(
            ["cat1", "catX", "cat3", "cat4"], ordered=True
        )

        # replace values in input dataframe
        msg = (
            r"The behavior of Series\.replace \(and DataFrame.replace\) "
            "with CategoricalDtype"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            input_df = input_df.replace("d", "z")
            input_df = input_df.replace("obj1", "obj9")
            result = input_df.replace("cat2", "catX")

        result = result.astype({"col1": "int64", "col3": "float64", "col5": "str"})
        tm.assert_frame_equal(result, expected)

    def test_replace_dict_category_type(self):
        """
        Test to ensure category dtypes are maintained
        after replace with dict values
        """
        # GH#35268, GH#44940

        # create input dataframe
        input_dict = {"col1": ["a"], "col2": ["obj1"], "col3": ["cat1"]}
        # explicitly cast columns as category
        input_df = DataFrame(data=input_dict).astype(
            {"col1": "category", "col2": "category", "col3": "category"}
        )

        # create expected dataframe
        expected_dict = {"col1": ["z"], "col2": ["obj9"], "col3": ["catX"]}
        # explicitly cast columns as category
        expected = DataFrame(data=expected_dict).astype(
            {"col1": "category", "col2": "category", "col3": "category"}
        )

        # replace values in input dataframe using a dict
        msg = (
            r"The behavior of Series\.replace \(and DataFrame.replace\) "
            "with CategoricalDtype"
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result = input_df.replace({"a": "z", "obj1": "obj9", "cat1": "catX"})

        tm.assert_frame_equal(result, expected)

    def test_replace_with_compiled_regex(self):
        # https://github.com/pandas-dev/pandas/issues/35680
        df = DataFrame(["a", "b", "c"])
        regex = re.compile("^a$")
        result = df.replace({regex: "z"}, regex=True)
        expected = DataFrame(["z", "b", "c"])
        tm.assert_frame_equal(result, expected)

    def test_replace_intervals(self):
        # https://github.com/pandas-dev/pandas/issues/35931
        df = DataFrame({"a": [pd.Interval(0, 1), pd.Interval(0, 1)]})
        result = df.replace({"a": {pd.Interval(0, 1): "x"}})
        expected = DataFrame({"a": ["x", "x"]}, dtype=object)
        tm.assert_frame_equal(result, expected)

    def test_replace_unicode(self):
        # GH: 16784
        columns_values_map = {"positive": {"正面": 1, "中立": 1, "负面": 0}}
        df1 = DataFrame({"positive": np.ones(3)})
        result = df1.replace(columns_values_map)
        expected = DataFrame({"positive": np.ones(3)})
        tm.assert_frame_equal(result, expected)

    def test_replace_bytes(self, frame_or_series):
        # GH#38900
        obj = frame_or_series(["o"]).astype("|S")
        expected = obj.copy()
        obj = obj.replace({None: np.nan})
        tm.assert_equal(obj, expected)

    @pytest.mark.parametrize(
        "data, to_replace, value, expected",
        [
            ([1], [1.0], [0], [0]),
            ([1], [1], [0], [0]),
            ([1.0], [1.0], [0], [0.0]),
            ([1.0], [1], [0], [0.0]),
        ],
    )
    @pytest.mark.parametrize("box", [list, tuple, np.array])
    def test_replace_list_with_mixed_type(
        self, data, to_replace, value, expected, box, frame_or_series
    ):
        # GH#40371
        obj = frame_or_series(data)
        expected = frame_or_series(expected)
        result = obj.replace(box(to_replace), value)
        tm.assert_equal(result, expected)

    @pytest.mark.parametrize("val", [2, np.nan, 2.0])
    def test_replace_value_none_dtype_numeric(self, val):
        # GH#48231
        df = DataFrame({"a": [1, val]})
        result = df.replace(val, None)
        expected = DataFrame({"a": [1, None]}, dtype=object)
        tm.assert_frame_equal(result, expected)

        df = DataFrame({"a": [1, val]})
        result = df.replace({val: None})
        tm.assert_frame_equal(result, expected)

    def test_replace_with_nil_na(self):
        # GH 32075
        ser = DataFrame({"a": ["nil", pd.NA]})
        expected = DataFrame({"a": ["anything else", pd.NA]}, index=[0, 1])
        result = ser.replace("nil", "anything else")
        tm.assert_frame_equal(expected, result)


class TestDataFrameReplaceRegex:
    @pytest.mark.parametrize(
        "data",
        [
            {"a": list("ab.."), "b": list("efgh")},
            {"a": list("ab.."), "b": list(range(4))},
        ],
    )
    @pytest.mark.parametrize(
        "to_replace,value", [(r"\s*\.\s*", np.nan), (r"\s*(\.)\s*", r"\1\1\1")]
    )
    @pytest.mark.parametrize("compile_regex", [True, False])
    @pytest.mark.parametrize("regex_kwarg", [True, False])
    @pytest.mark.parametrize("inplace", [True, False])
    def test_regex_replace_scalar(
        self, data, to_replace, value, compile_regex, regex_kwarg, inplace
    ):
        df = DataFrame(data)
        expected = df.copy()

        if compile_regex:
            to_replace = re.compile(to_replace)

        if regex_kwarg:
            regex = to_replace
            to_replace = None
        else:
            regex = True

        result = df.replace(to_replace, value, inplace=inplace, regex=regex)

        if inplace:
            assert result is None
            result = df

        if value is np.nan:
            expected_replace_val = np.nan
        else:
            expected_replace_val = "..."

        expected.loc[expected["a"] == ".", "a"] = expected_replace_val
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("regex", [False, True])
    def test_replace_regex_dtype_frame(self, regex):
        # GH-48644
        df1 = DataFrame({"A": ["0"], "B": ["0"]})
        expected_df1 = DataFrame({"A": [1], "B": [1]})
        msg = "Downcasting behavior in `replace`"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result_df1 = df1.replace(to_replace="0", value=1, regex=regex)
        tm.assert_frame_equal(result_df1, expected_df1)

        df2 = DataFrame({"A": ["0"], "B": ["1"]})
        expected_df2 = DataFrame({"A": [1], "B": ["1"]})
        with tm.assert_produces_warning(FutureWarning, match=msg):
            result_df2 = df2.replace(to_replace="0", value=1, regex=regex)
        tm.assert_frame_equal(result_df2, expected_df2)

    def test_replace_with_value_also_being_replaced(self):
        # GH46306
        df = DataFrame({"A": [0, 1, 2], "B": [1, 0, 2]})
        result = df.replace({0: 1, 1: np.nan})
        expected = DataFrame({"A": [1, np.nan, 2], "B": [np.nan, 1, 2]})
        tm.assert_frame_equal(result, expected)

    def test_replace_categorical_no_replacement(self):
        # GH#46672
        df = DataFrame(
            {
                "a": ["one", "two", None, "three"],
                "b": ["one", None, "two", "three"],
            },
            dtype="category",
        )
        expected = df.copy()

        result = df.replace(to_replace=[".", "def"], value=["_", None])
        tm.assert_frame_equal(result, expected)

    def test_replace_object_splitting(self, using_infer_string):
        # GH#53977
        df = DataFrame({"a": ["a"], "b": "b"})
        if using_infer_string:
            assert len(df._mgr.blocks) == 2
        else:
            assert len(df._mgr.blocks) == 1
        df.replace(to_replace=r"^\s*$", value="", inplace=True, regex=True)
        if using_infer_string:
            assert len(df._mgr.blocks) == 2
        else:
            assert len(df._mgr.blocks) == 1
