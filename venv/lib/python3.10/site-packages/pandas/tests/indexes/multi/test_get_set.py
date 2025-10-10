import numpy as np
import pytest

from pandas.compat import PY311

from pandas.core.dtypes.dtypes import DatetimeTZDtype

import pandas as pd
from pandas import (
    CategoricalIndex,
    MultiIndex,
)
import pandas._testing as tm


def assert_matching(actual, expected, check_dtype=False):
    # avoid specifying internal representation
    # as much as possible
    assert len(actual) == len(expected)
    for act, exp in zip(actual, expected):
        act = np.asarray(act)
        exp = np.asarray(exp)
        tm.assert_numpy_array_equal(act, exp, check_dtype=check_dtype)


def test_get_level_number_integer(idx):
    idx.names = [1, 0]
    assert idx._get_level_number(1) == 0
    assert idx._get_level_number(0) == 1
    msg = "Too many levels: Index has only 2 levels, not 3"
    with pytest.raises(IndexError, match=msg):
        idx._get_level_number(2)
    with pytest.raises(KeyError, match="Level fourth not found"):
        idx._get_level_number("fourth")


def test_get_dtypes(using_infer_string):
    # Test MultiIndex.dtypes (# Gh37062)
    idx_multitype = MultiIndex.from_product(
        [[1, 2, 3], ["a", "b", "c"], pd.date_range("20200101", periods=2, tz="UTC")],
        names=["int", "string", "dt"],
    )

    exp = "object" if not using_infer_string else pd.StringDtype(na_value=np.nan)
    expected = pd.Series(
        {
            "int": np.dtype("int64"),
            "string": exp,
            "dt": DatetimeTZDtype(tz="utc"),
        }
    )
    tm.assert_series_equal(expected, idx_multitype.dtypes)


def test_get_dtypes_no_level_name(using_infer_string):
    # Test MultiIndex.dtypes (# GH38580 )
    idx_multitype = MultiIndex.from_product(
        [
            [1, 2, 3],
            ["a", "b", "c"],
            pd.date_range("20200101", periods=2, tz="UTC"),
        ],
    )
    exp = "object" if not using_infer_string else pd.StringDtype(na_value=np.nan)
    expected = pd.Series(
        {
            "level_0": np.dtype("int64"),
            "level_1": exp,
            "level_2": DatetimeTZDtype(tz="utc"),
        }
    )
    tm.assert_series_equal(expected, idx_multitype.dtypes)


def test_get_dtypes_duplicate_level_names(using_infer_string):
    # Test MultiIndex.dtypes with non-unique level names (# GH45174)
    result = MultiIndex.from_product(
        [
            [1, 2, 3],
            ["a", "b", "c"],
            pd.date_range("20200101", periods=2, tz="UTC"),
        ],
        names=["A", "A", "A"],
    ).dtypes
    exp = "object" if not using_infer_string else pd.StringDtype(na_value=np.nan)
    expected = pd.Series(
        [np.dtype("int64"), exp, DatetimeTZDtype(tz="utc")],
        index=["A", "A", "A"],
    )
    tm.assert_series_equal(result, expected)


def test_get_level_number_out_of_bounds(multiindex_dataframe_random_data):
    frame = multiindex_dataframe_random_data

    with pytest.raises(IndexError, match="Too many levels"):
        frame.index._get_level_number(2)
    with pytest.raises(IndexError, match="not a valid level number"):
        frame.index._get_level_number(-3)


def test_set_name_methods(idx):
    # so long as these are synonyms, we don't need to test set_names
    index_names = ["first", "second"]
    assert idx.rename == idx.set_names
    new_names = [name + "SUFFIX" for name in index_names]
    ind = idx.set_names(new_names)
    assert idx.names == index_names
    assert ind.names == new_names
    msg = "Length of names must match number of levels in MultiIndex"
    with pytest.raises(ValueError, match=msg):
        ind.set_names(new_names + new_names)
    new_names2 = [name + "SUFFIX2" for name in new_names]
    res = ind.set_names(new_names2, inplace=True)
    assert res is None
    assert ind.names == new_names2

    # set names for specific level (# GH7792)
    ind = idx.set_names(new_names[0], level=0)
    assert idx.names == index_names
    assert ind.names == [new_names[0], index_names[1]]

    res = ind.set_names(new_names2[0], level=0, inplace=True)
    assert res is None
    assert ind.names == [new_names2[0], index_names[1]]

    # set names for multiple levels
    ind = idx.set_names(new_names, level=[0, 1])
    assert idx.names == index_names
    assert ind.names == new_names

    res = ind.set_names(new_names2, level=[0, 1], inplace=True)
    assert res is None
    assert ind.names == new_names2


def test_set_levels_codes_directly(idx):
    # setting levels/codes directly raises AttributeError

    levels = idx.levels
    new_levels = [[lev + "a" for lev in level] for level in levels]

    codes = idx.codes
    major_codes, minor_codes = codes
    major_codes = [(x + 1) % 3 for x in major_codes]
    minor_codes = [(x + 1) % 1 for x in minor_codes]
    new_codes = [major_codes, minor_codes]

    msg = "Can't set attribute"
    with pytest.raises(AttributeError, match=msg):
        idx.levels = new_levels

    msg = (
        "property 'codes' of 'MultiIndex' object has no setter"
        if PY311
        else "can't set attribute"
    )
    with pytest.raises(AttributeError, match=msg):
        idx.codes = new_codes


def test_set_levels(idx):
    # side note - you probably wouldn't want to use levels and codes
    # directly like this - but it is possible.
    levels = idx.levels
    new_levels = [[lev + "a" for lev in level] for level in levels]

    # level changing [w/o mutation]
    ind2 = idx.set_levels(new_levels)
    assert_matching(ind2.levels, new_levels)
    assert_matching(idx.levels, levels)

    # level changing specific level [w/o mutation]
    ind2 = idx.set_levels(new_levels[0], level=0)
    assert_matching(ind2.levels, [new_levels[0], levels[1]])
    assert_matching(idx.levels, levels)

    ind2 = idx.set_levels(new_levels[1], level=1)
    assert_matching(ind2.levels, [levels[0], new_levels[1]])
    assert_matching(idx.levels, levels)

    # level changing multiple levels [w/o mutation]
    ind2 = idx.set_levels(new_levels, level=[0, 1])
    assert_matching(ind2.levels, new_levels)
    assert_matching(idx.levels, levels)

    # illegal level changing should not change levels
    # GH 13754
    original_index = idx.copy()
    with pytest.raises(ValueError, match="^On"):
        idx.set_levels(["c"], level=0)
    assert_matching(idx.levels, original_index.levels, check_dtype=True)

    with pytest.raises(ValueError, match="^On"):
        idx.set_codes([0, 1, 2, 3, 4, 5], level=0)
    assert_matching(idx.codes, original_index.codes, check_dtype=True)

    with pytest.raises(TypeError, match="^Levels"):
        idx.set_levels("c", level=0)
    assert_matching(idx.levels, original_index.levels, check_dtype=True)

    with pytest.raises(TypeError, match="^Codes"):
        idx.set_codes(1, level=0)
    assert_matching(idx.codes, original_index.codes, check_dtype=True)


def test_set_codes(idx):
    # side note - you probably wouldn't want to use levels and codes
    # directly like this - but it is possible.
    codes = idx.codes
    major_codes, minor_codes = codes
    major_codes = [(x + 1) % 3 for x in major_codes]
    minor_codes = [(x + 1) % 1 for x in minor_codes]
    new_codes = [major_codes, minor_codes]

    # changing codes w/o mutation
    ind2 = idx.set_codes(new_codes)
    assert_matching(ind2.codes, new_codes)
    assert_matching(idx.codes, codes)

    # codes changing specific level w/o mutation
    ind2 = idx.set_codes(new_codes[0], level=0)
    assert_matching(ind2.codes, [new_codes[0], codes[1]])
    assert_matching(idx.codes, codes)

    ind2 = idx.set_codes(new_codes[1], level=1)
    assert_matching(ind2.codes, [codes[0], new_codes[1]])
    assert_matching(idx.codes, codes)

    # codes changing multiple levels w/o mutation
    ind2 = idx.set_codes(new_codes, level=[0, 1])
    assert_matching(ind2.codes, new_codes)
    assert_matching(idx.codes, codes)

    # label changing for levels of different magnitude of categories
    ind = MultiIndex.from_tuples([(0, i) for i in range(130)])
    new_codes = range(129, -1, -1)
    expected = MultiIndex.from_tuples([(0, i) for i in new_codes])

    # [w/o mutation]
    result = ind.set_codes(codes=new_codes, level=1)
    assert result.equals(expected)


def test_set_levels_codes_names_bad_input(idx):
    levels, codes = idx.levels, idx.codes
    names = idx.names

    with pytest.raises(ValueError, match="Length of levels"):
        idx.set_levels([levels[0]])

    with pytest.raises(ValueError, match="Length of codes"):
        idx.set_codes([codes[0]])

    with pytest.raises(ValueError, match="Length of names"):
        idx.set_names([names[0]])

    # shouldn't scalar data error, instead should demand list-like
    with pytest.raises(TypeError, match="list of lists-like"):
        idx.set_levels(levels[0])

    # shouldn't scalar data error, instead should demand list-like
    with pytest.raises(TypeError, match="list of lists-like"):
        idx.set_codes(codes[0])

    # shouldn't scalar data error, instead should demand list-like
    with pytest.raises(TypeError, match="list-like"):
        idx.set_names(names[0])

    # should have equal lengths
    with pytest.raises(TypeError, match="list of lists-like"):
        idx.set_levels(levels[0], level=[0, 1])

    with pytest.raises(TypeError, match="list-like"):
        idx.set_levels(levels, level=0)

    # should have equal lengths
    with pytest.raises(TypeError, match="list of lists-like"):
        idx.set_codes(codes[0], level=[0, 1])

    with pytest.raises(TypeError, match="list-like"):
        idx.set_codes(codes, level=0)

    # should have equal lengths
    with pytest.raises(ValueError, match="Length of names"):
        idx.set_names(names[0], level=[0, 1])

    with pytest.raises(TypeError, match="Names must be a"):
        idx.set_names(names, level=0)


@pytest.mark.parametrize("inplace", [True, False])
def test_set_names_with_nlevel_1(inplace):
    # GH 21149
    # Ensure that .set_names for MultiIndex with
    # nlevels == 1 does not raise any errors
    expected = MultiIndex(levels=[[0, 1]], codes=[[0, 1]], names=["first"])
    m = MultiIndex.from_product([[0, 1]])
    result = m.set_names("first", level=0, inplace=inplace)

    if inplace:
        result = m

    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("ordered", [True, False])
def test_set_levels_categorical(ordered):
    # GH13854
    index = MultiIndex.from_arrays([list("xyzx"), [0, 1, 2, 3]])

    cidx = CategoricalIndex(list("bac"), ordered=ordered)
    result = index.set_levels(cidx, level=0)
    expected = MultiIndex(levels=[cidx, [0, 1, 2, 3]], codes=index.codes)
    tm.assert_index_equal(result, expected)

    result_lvl = result.get_level_values(0)
    expected_lvl = CategoricalIndex(
        list("bacb"), categories=cidx.categories, ordered=cidx.ordered
    )
    tm.assert_index_equal(result_lvl, expected_lvl)


def test_set_value_keeps_names():
    # motivating example from #3742
    lev1 = ["hans", "hans", "hans", "grethe", "grethe", "grethe"]
    lev2 = ["1", "2", "3"] * 2
    idx = MultiIndex.from_arrays([lev1, lev2], names=["Name", "Number"])
    df = pd.DataFrame(
        np.random.default_rng(2).standard_normal((6, 4)),
        columns=["one", "two", "three", "four"],
        index=idx,
    )
    df = df.sort_index()
    assert df._is_copy is None
    assert df.index.names == ("Name", "Number")
    df.at[("grethe", "4"), "one"] = 99.34
    assert df._is_copy is None
    assert df.index.names == ("Name", "Number")


def test_set_levels_with_iterable():
    # GH23273
    sizes = [1, 2, 3]
    colors = ["black"] * 3
    index = MultiIndex.from_arrays([sizes, colors], names=["size", "color"])

    result = index.set_levels(map(int, ["3", "2", "1"]), level="size")

    expected_sizes = [3, 2, 1]
    expected = MultiIndex.from_arrays([expected_sizes, colors], names=["size", "color"])
    tm.assert_index_equal(result, expected)


def test_set_empty_level():
    # GH#48636
    midx = MultiIndex.from_arrays([[]], names=["A"])
    result = midx.set_levels(pd.DatetimeIndex([]), level=0)
    expected = MultiIndex.from_arrays([pd.DatetimeIndex([])], names=["A"])
    tm.assert_index_equal(result, expected)


def test_set_levels_pos_args_removal():
    # https://github.com/pandas-dev/pandas/issues/41485
    idx = MultiIndex.from_tuples(
        [
            (1, "one"),
            (3, "one"),
        ],
        names=["foo", "bar"],
    )
    with pytest.raises(TypeError, match="positional arguments"):
        idx.set_levels(["a", "b", "c"], 0)

    with pytest.raises(TypeError, match="positional arguments"):
        idx.set_codes([[0, 1], [1, 0]], 0)


def test_set_levels_categorical_keep_dtype():
    # GH#52125
    midx = MultiIndex.from_arrays([[5, 6]])
    result = midx.set_levels(levels=pd.Categorical([1, 2]), level=0)
    expected = MultiIndex.from_arrays([pd.Categorical([1, 2])])
    tm.assert_index_equal(result, expected)
