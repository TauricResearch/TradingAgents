from datetime import datetime
import re

import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    _testing as tm,
)
from pandas.tests.strings import (
    _convert_na_value,
    is_object_or_nan_string_dtype,
)


@pytest.mark.parametrize("method", ["split", "rsplit"])
def test_split(any_string_dtype, method):
    values = Series(["a_b_c", "c_d_e", np.nan, "f_g_h"], dtype=any_string_dtype)

    result = getattr(values.str, method)("_")
    exp = Series([["a", "b", "c"], ["c", "d", "e"], np.nan, ["f", "g", "h"]])
    exp = _convert_na_value(values, exp)
    tm.assert_series_equal(result, exp)


@pytest.mark.parametrize("method", ["split", "rsplit"])
def test_split_more_than_one_char(any_string_dtype, method):
    # more than one char
    values = Series(["a__b__c", "c__d__e", np.nan, "f__g__h"], dtype=any_string_dtype)
    result = getattr(values.str, method)("__")
    exp = Series([["a", "b", "c"], ["c", "d", "e"], np.nan, ["f", "g", "h"]])
    exp = _convert_na_value(values, exp)
    tm.assert_series_equal(result, exp)

    result = getattr(values.str, method)("__", expand=False)
    tm.assert_series_equal(result, exp)


def test_split_more_regex_split(any_string_dtype):
    # regex split
    values = Series(["a,b_c", "c_d,e", np.nan, "f,g,h"], dtype=any_string_dtype)
    result = values.str.split("[,_]")
    exp = Series([["a", "b", "c"], ["c", "d", "e"], np.nan, ["f", "g", "h"]])
    exp = _convert_na_value(values, exp)
    tm.assert_series_equal(result, exp)


def test_split_regex(any_string_dtype):
    # GH 43563
    # explicit regex = True split
    values = Series("xxxjpgzzz.jpg", dtype=any_string_dtype)
    result = values.str.split(r"\.jpg", regex=True)
    exp = Series([["xxxjpgzzz", ""]])
    tm.assert_series_equal(result, exp)


def test_split_regex_explicit(any_string_dtype):
    # explicit regex = True split with compiled regex
    regex_pat = re.compile(r".jpg")
    values = Series("xxxjpgzzz.jpg", dtype=any_string_dtype)
    result = values.str.split(regex_pat)
    exp = Series([["xx", "zzz", ""]])
    tm.assert_series_equal(result, exp)

    # explicit regex = False split
    result = values.str.split(r"\.jpg", regex=False)
    exp = Series([["xxxjpgzzz.jpg"]])
    tm.assert_series_equal(result, exp)

    # non explicit regex split, pattern length == 1
    result = values.str.split(r".")
    exp = Series([["xxxjpgzzz", "jpg"]])
    tm.assert_series_equal(result, exp)

    # non explicit regex split, pattern length != 1
    result = values.str.split(r".jpg")
    exp = Series([["xx", "zzz", ""]])
    tm.assert_series_equal(result, exp)

    # regex=False with pattern compiled regex raises error
    with pytest.raises(
        ValueError,
        match="Cannot use a compiled regex as replacement pattern with regex=False",
    ):
        values.str.split(regex_pat, regex=False)


@pytest.mark.parametrize("expand", [None, False])
@pytest.mark.parametrize("method", ["split", "rsplit"])
def test_split_object_mixed(expand, method):
    mixed = Series(["a_b_c", np.nan, "d_e_f", True, datetime.today(), None, 1, 2.0])
    result = getattr(mixed.str, method)("_", expand=expand)
    exp = Series(
        [
            ["a", "b", "c"],
            np.nan,
            ["d", "e", "f"],
            np.nan,
            np.nan,
            None,
            np.nan,
            np.nan,
        ]
    )
    assert isinstance(result, Series)
    tm.assert_almost_equal(result, exp)


@pytest.mark.parametrize("method", ["split", "rsplit"])
@pytest.mark.parametrize("n", [None, 0])
def test_split_n(any_string_dtype, method, n):
    s = Series(["a b", pd.NA, "b c"], dtype=any_string_dtype)
    expected = Series([["a", "b"], pd.NA, ["b", "c"]])
    result = getattr(s.str, method)(" ", n=n)
    expected = _convert_na_value(s, expected)
    tm.assert_series_equal(result, expected)


def test_rsplit(any_string_dtype):
    # regex split is not supported by rsplit
    values = Series(["a,b_c", "c_d,e", np.nan, "f,g,h"], dtype=any_string_dtype)
    result = values.str.rsplit("[,_]")
    exp = Series([["a,b_c"], ["c_d,e"], np.nan, ["f,g,h"]])
    exp = _convert_na_value(values, exp)
    tm.assert_series_equal(result, exp)


def test_rsplit_max_number(any_string_dtype):
    # setting max number of splits, make sure it's from reverse
    values = Series(["a_b_c", "c_d_e", np.nan, "f_g_h"], dtype=any_string_dtype)
    result = values.str.rsplit("_", n=1)
    exp = Series([["a_b", "c"], ["c_d", "e"], np.nan, ["f_g", "h"]])
    exp = _convert_na_value(values, exp)
    tm.assert_series_equal(result, exp)


def test_split_blank_string(any_string_dtype):
    # expand blank split GH 20067
    values = Series([""], name="test", dtype=any_string_dtype)
    result = values.str.split(expand=True)
    exp = DataFrame([[]], dtype=any_string_dtype)  # NOTE: this is NOT an empty df
    tm.assert_frame_equal(result, exp)


def test_split_blank_string_with_non_empty(any_string_dtype):
    values = Series(["a b c", "a b", "", " "], name="test", dtype=any_string_dtype)
    result = values.str.split(expand=True)
    exp = DataFrame(
        [
            ["a", "b", "c"],
            ["a", "b", None],
            [None, None, None],
            [None, None, None],
        ],
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)


@pytest.mark.parametrize("method", ["split", "rsplit"])
def test_split_noargs(any_string_dtype, method):
    # #1859
    s = Series(["Wes McKinney", "Travis  Oliphant"], dtype=any_string_dtype)
    result = getattr(s.str, method)()
    expected = ["Travis", "Oliphant"]
    assert result[1] == expected


@pytest.mark.parametrize(
    "data, pat",
    [
        (["bd asdf jfg", "kjasdflqw asdfnfk"], None),
        (["bd asdf jfg", "kjasdflqw asdfnfk"], "asdf"),
        (["bd_asdf_jfg", "kjasdflqw_asdfnfk"], "_"),
    ],
)
@pytest.mark.parametrize("n", [-1, 0])
def test_split_maxsplit(data, pat, any_string_dtype, n):
    # re.split 0, str.split -1
    s = Series(data, dtype=any_string_dtype)

    result = s.str.split(pat=pat, n=n)
    xp = s.str.split(pat=pat)
    tm.assert_series_equal(result, xp)


@pytest.mark.parametrize(
    "data, pat, expected",
    [
        (
            ["split once", "split once too!"],
            None,
            Series({0: ["split", "once"], 1: ["split", "once too!"]}),
        ),
        (
            ["split_once", "split_once_too!"],
            "_",
            Series({0: ["split", "once"], 1: ["split", "once_too!"]}),
        ),
    ],
)
def test_split_no_pat_with_nonzero_n(data, pat, expected, any_string_dtype):
    s = Series(data, dtype=any_string_dtype)
    result = s.str.split(pat=pat, n=1)
    tm.assert_series_equal(expected, result, check_index_type=False)


def test_split_to_dataframe_no_splits(any_string_dtype):
    s = Series(["nosplit", "alsonosplit"], dtype=any_string_dtype)
    result = s.str.split("_", expand=True)
    exp = DataFrame({0: Series(["nosplit", "alsonosplit"], dtype=any_string_dtype)})
    tm.assert_frame_equal(result, exp)


def test_split_to_dataframe(any_string_dtype):
    s = Series(["some_equal_splits", "with_no_nans"], dtype=any_string_dtype)
    result = s.str.split("_", expand=True)
    exp = DataFrame(
        {0: ["some", "with"], 1: ["equal", "no"], 2: ["splits", "nans"]},
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)


def test_split_to_dataframe_unequal_splits(any_string_dtype):
    s = Series(
        ["some_unequal_splits", "one_of_these_things_is_not"], dtype=any_string_dtype
    )
    result = s.str.split("_", expand=True)
    exp = DataFrame(
        {
            0: ["some", "one"],
            1: ["unequal", "of"],
            2: ["splits", "these"],
            3: [None, "things"],
            4: [None, "is"],
            5: [None, "not"],
        },
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)


def test_split_to_dataframe_with_index(any_string_dtype):
    s = Series(
        ["some_splits", "with_index"], index=["preserve", "me"], dtype=any_string_dtype
    )
    result = s.str.split("_", expand=True)
    exp = DataFrame(
        {0: ["some", "with"], 1: ["splits", "index"]},
        index=["preserve", "me"],
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)

    with pytest.raises(ValueError, match="expand must be"):
        s.str.split("_", expand="not_a_boolean")


def test_split_to_multiindex_expand_no_splits():
    # https://github.com/pandas-dev/pandas/issues/23677

    idx = Index(["nosplit", "alsonosplit", np.nan])
    result = idx.str.split("_", expand=True)
    exp = idx
    tm.assert_index_equal(result, exp)
    assert result.nlevels == 1


def test_split_to_multiindex_expand():
    idx = Index(["some_equal_splits", "with_no_nans", np.nan, None])
    result = idx.str.split("_", expand=True)
    exp = MultiIndex.from_tuples(
        [
            ("some", "equal", "splits"),
            ("with", "no", "nans"),
            [np.nan, np.nan, np.nan],
            [None, None, None],
        ]
    )
    tm.assert_index_equal(result, exp)
    assert result.nlevels == 3


def test_split_to_multiindex_expand_unequal_splits():
    idx = Index(["some_unequal_splits", "one_of_these_things_is_not", np.nan, None])
    result = idx.str.split("_", expand=True)
    exp = MultiIndex.from_tuples(
        [
            ("some", "unequal", "splits", np.nan, np.nan, np.nan),
            ("one", "of", "these", "things", "is", "not"),
            (np.nan, np.nan, np.nan, np.nan, np.nan, np.nan),
            (None, None, None, None, None, None),
        ]
    )
    tm.assert_index_equal(result, exp)
    assert result.nlevels == 6

    with pytest.raises(ValueError, match="expand must be"):
        idx.str.split("_", expand="not_a_boolean")


def test_rsplit_to_dataframe_expand_no_splits(any_string_dtype):
    s = Series(["nosplit", "alsonosplit"], dtype=any_string_dtype)
    result = s.str.rsplit("_", expand=True)
    exp = DataFrame({0: Series(["nosplit", "alsonosplit"])}, dtype=any_string_dtype)
    tm.assert_frame_equal(result, exp)


def test_rsplit_to_dataframe_expand(any_string_dtype):
    s = Series(["some_equal_splits", "with_no_nans"], dtype=any_string_dtype)
    result = s.str.rsplit("_", expand=True)
    exp = DataFrame(
        {0: ["some", "with"], 1: ["equal", "no"], 2: ["splits", "nans"]},
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)

    result = s.str.rsplit("_", expand=True, n=2)
    exp = DataFrame(
        {0: ["some", "with"], 1: ["equal", "no"], 2: ["splits", "nans"]},
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)

    result = s.str.rsplit("_", expand=True, n=1)
    exp = DataFrame(
        {0: ["some_equal", "with_no"], 1: ["splits", "nans"]}, dtype=any_string_dtype
    )
    tm.assert_frame_equal(result, exp)


def test_rsplit_to_dataframe_expand_with_index(any_string_dtype):
    s = Series(
        ["some_splits", "with_index"], index=["preserve", "me"], dtype=any_string_dtype
    )
    result = s.str.rsplit("_", expand=True)
    exp = DataFrame(
        {0: ["some", "with"], 1: ["splits", "index"]},
        index=["preserve", "me"],
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, exp)


def test_rsplit_to_multiindex_expand_no_split():
    idx = Index(["nosplit", "alsonosplit"])
    result = idx.str.rsplit("_", expand=True)
    exp = idx
    tm.assert_index_equal(result, exp)
    assert result.nlevels == 1


def test_rsplit_to_multiindex_expand():
    idx = Index(["some_equal_splits", "with_no_nans"])
    result = idx.str.rsplit("_", expand=True)
    exp = MultiIndex.from_tuples([("some", "equal", "splits"), ("with", "no", "nans")])
    tm.assert_index_equal(result, exp)
    assert result.nlevels == 3


def test_rsplit_to_multiindex_expand_n():
    idx = Index(["some_equal_splits", "with_no_nans"])
    result = idx.str.rsplit("_", expand=True, n=1)
    exp = MultiIndex.from_tuples([("some_equal", "splits"), ("with_no", "nans")])
    tm.assert_index_equal(result, exp)
    assert result.nlevels == 2


def test_split_nan_expand(any_string_dtype):
    # gh-18450
    s = Series(["foo,bar,baz", np.nan], dtype=any_string_dtype)
    result = s.str.split(",", expand=True)
    exp = DataFrame(
        [["foo", "bar", "baz"], [np.nan, np.nan, np.nan]], dtype=any_string_dtype
    )
    tm.assert_frame_equal(result, exp)

    # check that these are actually np.nan/pd.NA and not None
    # TODO see GH 18463
    # tm.assert_frame_equal does not differentiate
    if is_object_or_nan_string_dtype(any_string_dtype):
        assert all(np.isnan(x) for x in result.iloc[1])
    else:
        assert all(x is pd.NA for x in result.iloc[1])


def test_split_with_name_series(any_string_dtype):
    # GH 12617

    # should preserve name
    s = Series(["a,b", "c,d"], name="xxx", dtype=any_string_dtype)
    res = s.str.split(",")
    exp = Series([["a", "b"], ["c", "d"]], name="xxx")
    tm.assert_series_equal(res, exp)

    res = s.str.split(",", expand=True)
    exp = DataFrame([["a", "b"], ["c", "d"]], dtype=any_string_dtype)
    tm.assert_frame_equal(res, exp)


def test_split_with_name_index():
    # GH 12617
    idx = Index(["a,b", "c,d"], name="xxx")
    res = idx.str.split(",")
    exp = Index([["a", "b"], ["c", "d"]], name="xxx")
    assert res.nlevels == 1
    tm.assert_index_equal(res, exp)

    res = idx.str.split(",", expand=True)
    exp = MultiIndex.from_tuples([("a", "b"), ("c", "d")])
    assert res.nlevels == 2
    tm.assert_index_equal(res, exp)


@pytest.mark.parametrize(
    "method, exp",
    [
        [
            "partition",
            [
                ("a", "__", "b__c"),
                ("c", "__", "d__e"),
                np.nan,
                ("f", "__", "g__h"),
                None,
            ],
        ],
        [
            "rpartition",
            [
                ("a__b", "__", "c"),
                ("c__d", "__", "e"),
                np.nan,
                ("f__g", "__", "h"),
                None,
            ],
        ],
    ],
)
def test_partition_series_more_than_one_char(method, exp, any_string_dtype):
    # https://github.com/pandas-dev/pandas/issues/23558
    # more than one char
    s = Series(["a__b__c", "c__d__e", np.nan, "f__g__h", None], dtype=any_string_dtype)
    result = getattr(s.str, method)("__", expand=False)
    expected = Series(exp)
    expected = _convert_na_value(s, expected)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method, exp",
    [
        [
            "partition",
            [("a", " ", "b c"), ("c", " ", "d e"), np.nan, ("f", " ", "g h"), None],
        ],
        [
            "rpartition",
            [("a b", " ", "c"), ("c d", " ", "e"), np.nan, ("f g", " ", "h"), None],
        ],
    ],
)
def test_partition_series_none(any_string_dtype, method, exp):
    # https://github.com/pandas-dev/pandas/issues/23558
    # None
    s = Series(["a b c", "c d e", np.nan, "f g h", None], dtype=any_string_dtype)
    result = getattr(s.str, method)(expand=False)
    expected = Series(exp)
    expected = _convert_na_value(s, expected)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method, exp",
    [
        [
            "partition",
            [("abc", "", ""), ("cde", "", ""), np.nan, ("fgh", "", ""), None],
        ],
        [
            "rpartition",
            [("", "", "abc"), ("", "", "cde"), np.nan, ("", "", "fgh"), None],
        ],
    ],
)
def test_partition_series_not_split(any_string_dtype, method, exp):
    # https://github.com/pandas-dev/pandas/issues/23558
    # Not split
    s = Series(["abc", "cde", np.nan, "fgh", None], dtype=any_string_dtype)
    result = getattr(s.str, method)("_", expand=False)
    expected = Series(exp)
    expected = _convert_na_value(s, expected)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "method, exp",
    [
        [
            "partition",
            [("a", "_", "b_c"), ("c", "_", "d_e"), np.nan, ("f", "_", "g_h")],
        ],
        [
            "rpartition",
            [("a_b", "_", "c"), ("c_d", "_", "e"), np.nan, ("f_g", "_", "h")],
        ],
    ],
)
def test_partition_series_unicode(any_string_dtype, method, exp):
    # https://github.com/pandas-dev/pandas/issues/23558
    # unicode
    s = Series(["a_b_c", "c_d_e", np.nan, "f_g_h"], dtype=any_string_dtype)

    result = getattr(s.str, method)("_", expand=False)
    expected = Series(exp)
    expected = _convert_na_value(s, expected)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("method", ["partition", "rpartition"])
def test_partition_series_stdlib(any_string_dtype, method):
    # https://github.com/pandas-dev/pandas/issues/23558
    # compare to standard lib
    s = Series(["A_B_C", "B_C_D", "E_F_G", "EFGHEF"], dtype=any_string_dtype)
    result = getattr(s.str, method)("_", expand=False).tolist()
    assert result == [getattr(v, method)("_") for v in s]


@pytest.mark.parametrize(
    "method, expand, exp, exp_levels",
    [
        [
            "partition",
            False,
            np.array(
                [("a", "_", "b_c"), ("c", "_", "d_e"), ("f", "_", "g_h"), np.nan, None],
                dtype=object,
            ),
            1,
        ],
        [
            "rpartition",
            False,
            np.array(
                [("a_b", "_", "c"), ("c_d", "_", "e"), ("f_g", "_", "h"), np.nan, None],
                dtype=object,
            ),
            1,
        ],
    ],
)
def test_partition_index(method, expand, exp, exp_levels):
    # https://github.com/pandas-dev/pandas/issues/23558

    values = Index(["a_b_c", "c_d_e", "f_g_h", np.nan, None])

    result = getattr(values.str, method)("_", expand=expand)
    exp = Index(exp)
    tm.assert_index_equal(result, exp)
    assert result.nlevels == exp_levels


@pytest.mark.parametrize(
    "method, exp",
    [
        [
            "partition",
            {
                0: ["a", "c", np.nan, "f", None],
                1: ["_", "_", np.nan, "_", None],
                2: ["b_c", "d_e", np.nan, "g_h", None],
            },
        ],
        [
            "rpartition",
            {
                0: ["a_b", "c_d", np.nan, "f_g", None],
                1: ["_", "_", np.nan, "_", None],
                2: ["c", "e", np.nan, "h", None],
            },
        ],
    ],
)
def test_partition_to_dataframe(any_string_dtype, method, exp):
    # https://github.com/pandas-dev/pandas/issues/23558

    s = Series(["a_b_c", "c_d_e", np.nan, "f_g_h", None], dtype=any_string_dtype)
    result = getattr(s.str, method)("_")
    expected = DataFrame(
        exp,
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "method, exp",
    [
        [
            "partition",
            {
                0: ["a", "c", np.nan, "f", None],
                1: ["_", "_", np.nan, "_", None],
                2: ["b_c", "d_e", np.nan, "g_h", None],
            },
        ],
        [
            "rpartition",
            {
                0: ["a_b", "c_d", np.nan, "f_g", None],
                1: ["_", "_", np.nan, "_", None],
                2: ["c", "e", np.nan, "h", None],
            },
        ],
    ],
)
def test_partition_to_dataframe_from_series(any_string_dtype, method, exp):
    # https://github.com/pandas-dev/pandas/issues/23558
    s = Series(["a_b_c", "c_d_e", np.nan, "f_g_h", None], dtype=any_string_dtype)
    result = getattr(s.str, method)("_", expand=True)
    expected = DataFrame(
        exp,
        dtype=any_string_dtype,
    )
    tm.assert_frame_equal(result, expected)


def test_partition_with_name(any_string_dtype):
    # GH 12617

    s = Series(["a,b", "c,d"], name="xxx", dtype=any_string_dtype)
    result = s.str.partition(",")
    expected = DataFrame(
        {0: ["a", "c"], 1: [",", ","], 2: ["b", "d"]}, dtype=any_string_dtype
    )
    tm.assert_frame_equal(result, expected)


def test_partition_with_name_expand(any_string_dtype):
    # GH 12617
    # should preserve name
    s = Series(["a,b", "c,d"], name="xxx", dtype=any_string_dtype)
    result = s.str.partition(",", expand=False)
    expected = Series([("a", ",", "b"), ("c", ",", "d")], name="xxx")
    tm.assert_series_equal(result, expected)


def test_partition_index_with_name():
    idx = Index(["a,b", "c,d"], name="xxx")
    result = idx.str.partition(",")
    expected = MultiIndex.from_tuples([("a", ",", "b"), ("c", ",", "d")])
    assert result.nlevels == 3
    tm.assert_index_equal(result, expected)


def test_partition_index_with_name_expand_false():
    idx = Index(["a,b", "c,d"], name="xxx")
    # should preserve name
    result = idx.str.partition(",", expand=False)
    expected = Index(np.array([("a", ",", "b"), ("c", ",", "d")]), name="xxx")
    assert result.nlevels == 1
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("method", ["partition", "rpartition"])
def test_partition_sep_kwarg(any_string_dtype, method):
    # GH 22676; depr kwarg "pat" in favor of "sep"
    s = Series(["a_b_c", "c_d_e", np.nan, "f_g_h"], dtype=any_string_dtype)

    expected = getattr(s.str, method)(sep="_")
    result = getattr(s.str, method)("_")
    tm.assert_frame_equal(result, expected)


def test_get():
    ser = Series(["a_b_c", "c_d_e", np.nan, "f_g_h"])
    result = ser.str.split("_").str.get(1)
    expected = Series(["b", "d", np.nan, "g"], dtype=object)
    tm.assert_series_equal(result, expected)


def test_get_mixed_object():
    ser = Series(["a_b_c", np.nan, "c_d_e", True, datetime.today(), None, 1, 2.0])
    result = ser.str.split("_").str.get(1)
    expected = Series(
        ["b", np.nan, "d", np.nan, np.nan, None, np.nan, np.nan], dtype=object
    )
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("idx", [2, -3])
def test_get_bounds(idx):
    ser = Series(["1_2_3_4_5", "6_7_8_9_10", "11_12"])
    result = ser.str.split("_").str.get(idx)
    expected = Series(["3", "8", np.nan], dtype=object)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "idx, exp", [[2, [3, 3, np.nan, "b"]], [-1, [3, 3, np.nan, np.nan]]]
)
def test_get_complex(idx, exp):
    # GH 20671, getting value not in dict raising `KeyError`
    ser = Series([(1, 2, 3), [1, 2, 3], {1, 2, 3}, {1: "a", 2: "b", 3: "c"}])

    result = ser.str.get(idx)
    expected = Series(exp)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("to_type", [tuple, list, np.array])
def test_get_complex_nested(to_type):
    ser = Series([to_type([to_type([1, 2])])])

    result = ser.str.get(0)
    expected = Series([to_type([1, 2])])
    tm.assert_series_equal(result, expected)

    result = ser.str.get(1)
    expected = Series([np.nan])
    tm.assert_series_equal(result, expected)


def test_get_strings(any_string_dtype):
    ser = Series(["a", "ab", np.nan, "abc"], dtype=any_string_dtype)
    result = ser.str.get(2)
    expected = Series([np.nan, np.nan, np.nan, "c"], dtype=any_string_dtype)
    tm.assert_series_equal(result, expected)
