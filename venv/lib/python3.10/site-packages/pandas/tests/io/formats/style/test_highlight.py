import numpy as np
import pytest

from pandas import (
    NA,
    DataFrame,
    IndexSlice,
)

pytest.importorskip("jinja2")

from pandas.io.formats.style import Styler


@pytest.fixture(params=[(None, "float64"), (NA, "Int64")])
def df(request):
    # GH 45804
    return DataFrame(
        {"A": [0, np.nan, 10], "B": [1, request.param[0], 2]}, dtype=request.param[1]
    )


@pytest.fixture
def styler(df):
    return Styler(df, uuid_len=0)


def test_highlight_null(styler):
    result = styler.highlight_null()._compute().ctx
    expected = {
        (1, 0): [("background-color", "red")],
        (1, 1): [("background-color", "red")],
    }
    assert result == expected


def test_highlight_null_subset(styler):
    # GH 31345
    result = (
        styler.highlight_null(color="red", subset=["A"])
        .highlight_null(color="green", subset=["B"])
        ._compute()
        .ctx
    )
    expected = {
        (1, 0): [("background-color", "red")],
        (1, 1): [("background-color", "green")],
    }
    assert result == expected


@pytest.mark.parametrize("f", ["highlight_min", "highlight_max"])
def test_highlight_minmax_basic(df, f):
    expected = {
        (0, 1): [("background-color", "red")],
        # ignores NaN row,
        (2, 0): [("background-color", "red")],
    }
    if f == "highlight_min":
        df = -df
    result = getattr(df.style, f)(axis=1, color="red")._compute().ctx
    assert result == expected


@pytest.mark.parametrize("f", ["highlight_min", "highlight_max"])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"axis": None, "color": "red"},  # test axis
        {"axis": 0, "subset": ["A"], "color": "red"},  # test subset and ignores NaN
        {"axis": None, "props": "background-color: red"},  # test props
    ],
)
def test_highlight_minmax_ext(df, f, kwargs):
    expected = {(2, 0): [("background-color", "red")]}
    if f == "highlight_min":
        df = -df
    result = getattr(df.style, f)(**kwargs)._compute().ctx
    assert result == expected


@pytest.mark.parametrize("f", ["highlight_min", "highlight_max"])
@pytest.mark.parametrize("axis", [None, 0, 1])
def test_highlight_minmax_nulls(f, axis):
    # GH 42750
    expected = {
        (1, 0): [("background-color", "yellow")],
        (1, 1): [("background-color", "yellow")],
    }
    if axis == 1:
        expected.update({(2, 1): [("background-color", "yellow")]})

    if f == "highlight_max":
        df = DataFrame({"a": [NA, 1, None], "b": [np.nan, 1, -1]})
    else:
        df = DataFrame({"a": [NA, -1, None], "b": [np.nan, -1, 1]})

    result = getattr(df.style, f)(axis=axis)._compute().ctx
    assert result == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"left": 0, "right": 1},  # test basic range
        {"left": 0, "right": 1, "props": "background-color: yellow"},  # test props
        {"left": -100, "right": 100, "subset": IndexSlice[[0, 1], :]},  # test subset
        {"left": 0, "subset": IndexSlice[[0, 1], :]},  # test no right
        {"right": 1},  # test no left
        {"left": [0, 0, 11], "axis": 0},  # test left as sequence
        {"left": DataFrame({"A": [0, 0, 11], "B": [1, 1, 11]}), "axis": None},  # axis
        {"left": 0, "right": [0, 1], "axis": 1},  # test sequence right
    ],
)
def test_highlight_between(styler, kwargs):
    expected = {
        (0, 0): [("background-color", "yellow")],
        (0, 1): [("background-color", "yellow")],
    }
    result = styler.highlight_between(**kwargs)._compute().ctx
    assert result == expected


@pytest.mark.parametrize(
    "arg, map, axis",
    [
        ("left", [1, 2], 0),  # 0 axis has 3 elements not 2
        ("left", [1, 2, 3], 1),  # 1 axis has 2 elements not 3
        ("left", np.array([[1, 2], [1, 2]]), None),  # df is (2,3) not (2,2)
        ("right", [1, 2], 0),  # same tests as above for 'right' not 'left'
        ("right", [1, 2, 3], 1),  # ..
        ("right", np.array([[1, 2], [1, 2]]), None),  # ..
    ],
)
def test_highlight_between_raises(arg, styler, map, axis):
    msg = f"supplied '{arg}' is not correct shape"
    with pytest.raises(ValueError, match=msg):
        styler.highlight_between(**{arg: map, "axis": axis})._compute()


def test_highlight_between_raises2(styler):
    msg = "values can be 'both', 'left', 'right', or 'neither'"
    with pytest.raises(ValueError, match=msg):
        styler.highlight_between(inclusive="badstring")._compute()

    with pytest.raises(ValueError, match=msg):
        styler.highlight_between(inclusive=1)._compute()


@pytest.mark.parametrize(
    "inclusive, expected",
    [
        (
            "both",
            {
                (0, 0): [("background-color", "yellow")],
                (0, 1): [("background-color", "yellow")],
            },
        ),
        ("neither", {}),
        ("left", {(0, 0): [("background-color", "yellow")]}),
        ("right", {(0, 1): [("background-color", "yellow")]}),
    ],
)
def test_highlight_between_inclusive(styler, inclusive, expected):
    kwargs = {"left": 0, "right": 1, "subset": IndexSlice[[0, 1], :]}
    result = styler.highlight_between(**kwargs, inclusive=inclusive)._compute()
    assert result.ctx == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"q_left": 0.5, "q_right": 1, "axis": 0},  # base case
        {"q_left": 0.5, "q_right": 1, "axis": None},  # test axis
        {"q_left": 0, "q_right": 1, "subset": IndexSlice[2, :]},  # test subset
        {"q_left": 0.5, "axis": 0},  # test no high
        {"q_right": 1, "subset": IndexSlice[2, :], "axis": 1},  # test no low
        {"q_left": 0.5, "axis": 0, "props": "background-color: yellow"},  # tst prop
    ],
)
def test_highlight_quantile(styler, kwargs):
    expected = {
        (2, 0): [("background-color", "yellow")],
        (2, 1): [("background-color", "yellow")],
    }
    result = styler.highlight_quantile(**kwargs)._compute().ctx
    assert result == expected


@pytest.mark.parametrize(
    "f,kwargs",
    [
        ("highlight_min", {"axis": 1, "subset": IndexSlice[1, :]}),
        ("highlight_max", {"axis": 0, "subset": [0]}),
        ("highlight_quantile", {"axis": None, "q_left": 0.6, "q_right": 0.8}),
        ("highlight_between", {"subset": [0]}),
    ],
)
@pytest.mark.parametrize(
    "df",
    [
        DataFrame([[0, 10], [20, 30]], dtype=int),
        DataFrame([[0, 10], [20, 30]], dtype=float),
        DataFrame([[0, 10], [20, 30]], dtype="datetime64[ns]"),
        DataFrame([[0, 10], [20, 30]], dtype=str),
        DataFrame([[0, 10], [20, 30]], dtype="timedelta64[ns]"),
    ],
)
def test_all_highlight_dtypes(f, kwargs, df):
    if f == "highlight_quantile" and isinstance(df.iloc[0, 0], (str)):
        return None  # quantile incompatible with str
    if f == "highlight_between":
        kwargs["left"] = df.iloc[1, 0]  # set the range low for testing

    expected = {(1, 0): [("background-color", "yellow")]}
    result = getattr(df.style, f)(**kwargs)._compute().ctx
    assert result == expected
