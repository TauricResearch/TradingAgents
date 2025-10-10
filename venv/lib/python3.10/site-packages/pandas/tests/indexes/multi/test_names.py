import pytest

import pandas as pd
from pandas import MultiIndex
import pandas._testing as tm


def check_level_names(index, names):
    assert [level.name for level in index.levels] == list(names)


def test_slice_keep_name():
    x = MultiIndex.from_tuples([("a", "b"), (1, 2), ("c", "d")], names=["x", "y"])
    assert x[1:].names == x.names


def test_index_name_retained():
    # GH9857
    result = pd.DataFrame({"x": [1, 2, 6], "y": [2, 2, 8], "z": [-5, 0, 5]})
    result = result.set_index("z")
    result.loc[10] = [9, 10]
    df_expected = pd.DataFrame(
        {"x": [1, 2, 6, 9], "y": [2, 2, 8, 10], "z": [-5, 0, 5, 10]}
    )
    df_expected = df_expected.set_index("z")
    tm.assert_frame_equal(result, df_expected)


def test_changing_names(idx):
    assert [level.name for level in idx.levels] == ["first", "second"]

    view = idx.view()
    copy = idx.copy()
    shallow_copy = idx._view()

    # changing names should not change level names on object
    new_names = [name + "a" for name in idx.names]
    idx.names = new_names
    check_level_names(idx, ["firsta", "seconda"])

    # and not on copies
    check_level_names(view, ["first", "second"])
    check_level_names(copy, ["first", "second"])
    check_level_names(shallow_copy, ["first", "second"])

    # and copies shouldn't change original
    shallow_copy.names = [name + "c" for name in shallow_copy.names]
    check_level_names(idx, ["firsta", "seconda"])


def test_take_preserve_name(idx):
    taken = idx.take([3, 0, 1])
    assert taken.names == idx.names


def test_copy_names():
    # Check that adding a "names" parameter to the copy is honored
    # GH14302
    multi_idx = MultiIndex.from_tuples([(1, 2), (3, 4)], names=["MyName1", "MyName2"])
    multi_idx1 = multi_idx.copy()

    assert multi_idx.equals(multi_idx1)
    assert multi_idx.names == ["MyName1", "MyName2"]
    assert multi_idx1.names == ["MyName1", "MyName2"]

    multi_idx2 = multi_idx.copy(names=["NewName1", "NewName2"])

    assert multi_idx.equals(multi_idx2)
    assert multi_idx.names == ["MyName1", "MyName2"]
    assert multi_idx2.names == ["NewName1", "NewName2"]

    multi_idx3 = multi_idx.copy(name=["NewName1", "NewName2"])

    assert multi_idx.equals(multi_idx3)
    assert multi_idx.names == ["MyName1", "MyName2"]
    assert multi_idx3.names == ["NewName1", "NewName2"]

    # gh-35592
    with pytest.raises(ValueError, match="Length of new names must be 2, got 1"):
        multi_idx.copy(names=["mario"])

    with pytest.raises(TypeError, match="MultiIndex.name must be a hashable type"):
        multi_idx.copy(names=[["mario"], ["luigi"]])


def test_names(idx):
    # names are assigned in setup
    assert idx.names == ["first", "second"]
    level_names = [level.name for level in idx.levels]
    assert level_names == idx.names

    # setting bad names on existing
    index = idx
    with pytest.raises(ValueError, match="^Length of names"):
        setattr(index, "names", list(index.names) + ["third"])
    with pytest.raises(ValueError, match="^Length of names"):
        setattr(index, "names", [])

    # initializing with bad names (should always be equivalent)
    major_axis, minor_axis = idx.levels
    major_codes, minor_codes = idx.codes
    with pytest.raises(ValueError, match="^Length of names"):
        MultiIndex(
            levels=[major_axis, minor_axis],
            codes=[major_codes, minor_codes],
            names=["first"],
        )
    with pytest.raises(ValueError, match="^Length of names"):
        MultiIndex(
            levels=[major_axis, minor_axis],
            codes=[major_codes, minor_codes],
            names=["first", "second", "third"],
        )

    # names are assigned on index, but not transferred to the levels
    index.names = ["a", "b"]
    level_names = [level.name for level in index.levels]
    assert level_names == ["a", "b"]


def test_duplicate_level_names_access_raises(idx):
    # GH19029
    idx.names = ["foo", "foo"]
    with pytest.raises(ValueError, match="name foo occurs multiple times"):
        idx._get_level_number("foo")


def test_get_names_from_levels():
    idx = MultiIndex.from_product([["a"], [1, 2]], names=["a", "b"])

    assert idx.levels[0].name == "a"
    assert idx.levels[1].name == "b"


def test_setting_names_from_levels_raises():
    idx = MultiIndex.from_product([["a"], [1, 2]], names=["a", "b"])
    with pytest.raises(RuntimeError, match="set_names"):
        idx.levels[0].name = "foo"

    with pytest.raises(RuntimeError, match="set_names"):
        idx.levels[1].name = "foo"

    new = pd.Series(1, index=idx.levels[0])
    with pytest.raises(RuntimeError, match="set_names"):
        new.index.name = "bar"

    assert pd.Index._no_setting_name is False
    assert pd.RangeIndex._no_setting_name is False


@pytest.mark.parametrize("func", ["rename", "set_names"])
@pytest.mark.parametrize(
    "rename_dict, exp_names",
    [
        ({"x": "z"}, ["z", "y", "z"]),
        ({"x": "z", "y": "x"}, ["z", "x", "z"]),
        ({"y": "z"}, ["x", "z", "x"]),
        ({}, ["x", "y", "x"]),
        ({"z": "a"}, ["x", "y", "x"]),
        ({"y": "z", "a": "b"}, ["x", "z", "x"]),
    ],
)
def test_name_mi_with_dict_like_duplicate_names(func, rename_dict, exp_names):
    # GH#20421
    mi = MultiIndex.from_arrays([[1, 2], [3, 4], [5, 6]], names=["x", "y", "x"])
    result = getattr(mi, func)(rename_dict)
    expected = MultiIndex.from_arrays([[1, 2], [3, 4], [5, 6]], names=exp_names)
    tm.assert_index_equal(result, expected)


@pytest.mark.parametrize("func", ["rename", "set_names"])
@pytest.mark.parametrize(
    "rename_dict, exp_names",
    [
        ({"x": "z"}, ["z", "y"]),
        ({"x": "z", "y": "x"}, ["z", "x"]),
        ({"a": "z"}, ["x", "y"]),
        ({}, ["x", "y"]),
    ],
)
def test_name_mi_with_dict_like(func, rename_dict, exp_names):
    # GH#20421
    mi = MultiIndex.from_arrays([[1, 2], [3, 4]], names=["x", "y"])
    result = getattr(mi, func)(rename_dict)
    expected = MultiIndex.from_arrays([[1, 2], [3, 4]], names=exp_names)
    tm.assert_index_equal(result, expected)


def test_index_name_with_dict_like_raising():
    # GH#20421
    ix = pd.Index([1, 2])
    msg = "Can only pass dict-like as `names` for MultiIndex."
    with pytest.raises(TypeError, match=msg):
        ix.set_names({"x": "z"})


def test_multiindex_name_and_level_raising():
    # GH#20421
    mi = MultiIndex.from_arrays([[1, 2], [3, 4]], names=["x", "y"])
    with pytest.raises(TypeError, match="Can not pass level for dictlike `names`."):
        mi.set_names(names={"x": "z"}, level={"x": "z"})
