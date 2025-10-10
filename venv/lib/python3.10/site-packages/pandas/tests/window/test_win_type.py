import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
    Timedelta,
    concat,
    date_range,
)
import pandas._testing as tm
from pandas.api.indexers import BaseIndexer


@pytest.fixture(
    params=[
        "triang",
        "blackman",
        "hamming",
        "bartlett",
        "bohman",
        "blackmanharris",
        "nuttall",
        "barthann",
    ]
)
def win_types(request):
    return request.param


@pytest.fixture(params=["kaiser", "gaussian", "general_gaussian", "exponential"])
def win_types_special(request):
    return request.param


def test_constructor(frame_or_series):
    # GH 12669
    pytest.importorskip("scipy")
    c = frame_or_series(range(5)).rolling

    # valid
    c(win_type="boxcar", window=2, min_periods=1)
    c(win_type="boxcar", window=2, min_periods=1, center=True)
    c(win_type="boxcar", window=2, min_periods=1, center=False)


@pytest.mark.parametrize("w", [2.0, "foo", np.array([2])])
def test_invalid_constructor(frame_or_series, w):
    # not valid
    pytest.importorskip("scipy")
    c = frame_or_series(range(5)).rolling
    with pytest.raises(ValueError, match="min_periods must be an integer"):
        c(win_type="boxcar", window=2, min_periods=w)
    with pytest.raises(ValueError, match="center must be a boolean"):
        c(win_type="boxcar", window=2, min_periods=1, center=w)


@pytest.mark.parametrize("wt", ["foobar", 1])
def test_invalid_constructor_wintype(frame_or_series, wt):
    pytest.importorskip("scipy")
    c = frame_or_series(range(5)).rolling
    with pytest.raises(ValueError, match="Invalid win_type"):
        c(win_type=wt, window=2)


def test_constructor_with_win_type(frame_or_series, win_types):
    # GH 12669
    pytest.importorskip("scipy")
    c = frame_or_series(range(5)).rolling
    c(win_type=win_types, window=2)


@pytest.mark.parametrize("arg", ["median", "kurt", "skew"])
def test_agg_function_support(arg):
    pytest.importorskip("scipy")
    df = DataFrame({"A": np.arange(5)})
    roll = df.rolling(2, win_type="triang")

    msg = f"'{arg}' is not a valid function for 'Window' object"
    with pytest.raises(AttributeError, match=msg):
        roll.agg(arg)

    with pytest.raises(AttributeError, match=msg):
        roll.agg([arg])

    with pytest.raises(AttributeError, match=msg):
        roll.agg({"A": arg})


def test_invalid_scipy_arg():
    # This error is raised by scipy
    pytest.importorskip("scipy")
    msg = r"boxcar\(\) got an unexpected"
    with pytest.raises(TypeError, match=msg):
        Series(range(3)).rolling(1, win_type="boxcar").mean(foo="bar")


def test_constructor_with_win_type_invalid(frame_or_series):
    # GH 13383
    pytest.importorskip("scipy")
    c = frame_or_series(range(5)).rolling

    msg = "window must be an integer 0 or greater"

    with pytest.raises(ValueError, match=msg):
        c(-1, win_type="boxcar")


def test_window_with_args(step):
    # make sure that we are aggregating window functions correctly with arg
    pytest.importorskip("scipy")
    r = Series(np.random.default_rng(2).standard_normal(100)).rolling(
        window=10, min_periods=1, win_type="gaussian", step=step
    )
    expected = concat([r.mean(std=10), r.mean(std=0.01)], axis=1)
    expected.columns = ["<lambda>", "<lambda>"]
    result = r.aggregate([lambda x: x.mean(std=10), lambda x: x.mean(std=0.01)])
    tm.assert_frame_equal(result, expected)

    def a(x):
        return x.mean(std=10)

    def b(x):
        return x.mean(std=0.01)

    expected = concat([r.mean(std=10), r.mean(std=0.01)], axis=1)
    expected.columns = ["a", "b"]
    result = r.aggregate([a, b])
    tm.assert_frame_equal(result, expected)


def test_win_type_with_method_invalid():
    pytest.importorskip("scipy")
    with pytest.raises(
        NotImplementedError, match="'single' is the only supported method type."
    ):
        Series(range(1)).rolling(1, win_type="triang", method="table")


@pytest.mark.parametrize("arg", [2000000000, "2s", Timedelta("2s")])
def test_consistent_win_type_freq(arg):
    # GH 15969
    pytest.importorskip("scipy")
    s = Series(range(1))
    with pytest.raises(ValueError, match="Invalid win_type freq"):
        s.rolling(arg, win_type="freq")


def test_win_type_freq_return_none():
    # GH 48838
    freq_roll = Series(range(2), index=date_range("2020", periods=2)).rolling("2s")
    assert freq_roll.win_type is None


def test_win_type_not_implemented():
    pytest.importorskip("scipy")

    class CustomIndexer(BaseIndexer):
        def get_window_bounds(self, num_values, min_periods, center, closed, step):
            return np.array([0, 1]), np.array([1, 2])

    df = DataFrame({"values": range(2)})
    indexer = CustomIndexer()
    with pytest.raises(NotImplementedError, match="BaseIndexer subclasses not"):
        df.rolling(indexer, win_type="boxcar")


def test_cmov_mean(step):
    # GH 8238
    pytest.importorskip("scipy")
    vals = np.array([6.95, 15.21, 4.72, 9.12, 13.81, 13.49, 16.68, 9.48, 10.63, 14.48])
    result = Series(vals).rolling(5, center=True, step=step).mean()
    expected_values = [
        np.nan,
        np.nan,
        9.962,
        11.27,
        11.564,
        12.516,
        12.818,
        12.952,
        np.nan,
        np.nan,
    ]
    expected = Series(expected_values)[::step]
    tm.assert_series_equal(expected, result)


def test_cmov_window(step):
    # GH 8238
    pytest.importorskip("scipy")
    vals = np.array([6.95, 15.21, 4.72, 9.12, 13.81, 13.49, 16.68, 9.48, 10.63, 14.48])
    result = Series(vals).rolling(5, win_type="boxcar", center=True, step=step).mean()
    expected_values = [
        np.nan,
        np.nan,
        9.962,
        11.27,
        11.564,
        12.516,
        12.818,
        12.952,
        np.nan,
        np.nan,
    ]
    expected = Series(expected_values)[::step]
    tm.assert_series_equal(expected, result)


def test_cmov_window_corner(step):
    # GH 8238
    # all nan
    pytest.importorskip("scipy")
    vals = Series([np.nan] * 10)
    result = vals.rolling(5, center=True, win_type="boxcar", step=step).mean()
    assert np.isnan(result).all()

    # empty
    vals = Series([], dtype=object)
    result = vals.rolling(5, center=True, win_type="boxcar", step=step).mean()
    assert len(result) == 0

    # shorter than window
    vals = Series(np.random.default_rng(2).standard_normal(5))
    result = vals.rolling(10, win_type="boxcar", step=step).mean()
    assert np.isnan(result).all()
    assert len(result) == len(range(0, 5, step or 1))


@pytest.mark.parametrize(
    "f,xp",
    [
        (
            "mean",
            [
                [np.nan, np.nan],
                [np.nan, np.nan],
                [9.252, 9.392],
                [8.644, 9.906],
                [8.87, 10.208],
                [6.81, 8.588],
                [7.792, 8.644],
                [9.05, 7.824],
                [np.nan, np.nan],
                [np.nan, np.nan],
            ],
        ),
        (
            "std",
            [
                [np.nan, np.nan],
                [np.nan, np.nan],
                [3.789706, 4.068313],
                [3.429232, 3.237411],
                [3.589269, 3.220810],
                [3.405195, 2.380655],
                [3.281839, 2.369869],
                [3.676846, 1.801799],
                [np.nan, np.nan],
                [np.nan, np.nan],
            ],
        ),
        (
            "var",
            [
                [np.nan, np.nan],
                [np.nan, np.nan],
                [14.36187, 16.55117],
                [11.75963, 10.48083],
                [12.88285, 10.37362],
                [11.59535, 5.66752],
                [10.77047, 5.61628],
                [13.51920, 3.24648],
                [np.nan, np.nan],
                [np.nan, np.nan],
            ],
        ),
        (
            "sum",
            [
                [np.nan, np.nan],
                [np.nan, np.nan],
                [46.26, 46.96],
                [43.22, 49.53],
                [44.35, 51.04],
                [34.05, 42.94],
                [38.96, 43.22],
                [45.25, 39.12],
                [np.nan, np.nan],
                [np.nan, np.nan],
            ],
        ),
    ],
)
def test_cmov_window_frame(f, xp, step):
    # Gh 8238
    pytest.importorskip("scipy")
    df = DataFrame(
        np.array(
            [
                [12.18, 3.64],
                [10.18, 9.16],
                [13.24, 14.61],
                [4.51, 8.11],
                [6.15, 11.44],
                [9.14, 6.21],
                [11.31, 10.67],
                [2.94, 6.51],
                [9.42, 8.39],
                [12.44, 7.34],
            ]
        )
    )
    xp = DataFrame(np.array(xp))[::step]

    roll = df.rolling(5, win_type="boxcar", center=True, step=step)
    rs = getattr(roll, f)()

    tm.assert_frame_equal(xp, rs)


@pytest.mark.parametrize("min_periods", [0, 1, 2, 3, 4, 5])
def test_cmov_window_na_min_periods(step, min_periods):
    pytest.importorskip("scipy")
    vals = Series(np.random.default_rng(2).standard_normal(10))
    vals[4] = np.nan
    vals[8] = np.nan

    xp = vals.rolling(5, min_periods=min_periods, center=True, step=step).mean()
    rs = vals.rolling(
        5, win_type="boxcar", min_periods=min_periods, center=True, step=step
    ).mean()
    tm.assert_series_equal(xp, rs)


def test_cmov_window_regular(win_types, step):
    # GH 8238
    pytest.importorskip("scipy")
    vals = np.array([6.95, 15.21, 4.72, 9.12, 13.81, 13.49, 16.68, 9.48, 10.63, 14.48])
    xps = {
        "hamming": [
            np.nan,
            np.nan,
            8.71384,
            9.56348,
            12.38009,
            14.03687,
            13.8567,
            11.81473,
            np.nan,
            np.nan,
        ],
        "triang": [
            np.nan,
            np.nan,
            9.28667,
            10.34667,
            12.00556,
            13.33889,
            13.38,
            12.33667,
            np.nan,
            np.nan,
        ],
        "barthann": [
            np.nan,
            np.nan,
            8.4425,
            9.1925,
            12.5575,
            14.3675,
            14.0825,
            11.5675,
            np.nan,
            np.nan,
        ],
        "bohman": [
            np.nan,
            np.nan,
            7.61599,
            9.1764,
            12.83559,
            14.17267,
            14.65923,
            11.10401,
            np.nan,
            np.nan,
        ],
        "blackmanharris": [
            np.nan,
            np.nan,
            6.97691,
            9.16438,
            13.05052,
            14.02156,
            15.10512,
            10.74574,
            np.nan,
            np.nan,
        ],
        "nuttall": [
            np.nan,
            np.nan,
            7.04618,
            9.16786,
            13.02671,
            14.03559,
            15.05657,
            10.78514,
            np.nan,
            np.nan,
        ],
        "blackman": [
            np.nan,
            np.nan,
            7.73345,
            9.17869,
            12.79607,
            14.20036,
            14.57726,
            11.16988,
            np.nan,
            np.nan,
        ],
        "bartlett": [
            np.nan,
            np.nan,
            8.4425,
            9.1925,
            12.5575,
            14.3675,
            14.0825,
            11.5675,
            np.nan,
            np.nan,
        ],
    }

    xp = Series(xps[win_types])[::step]
    rs = Series(vals).rolling(5, win_type=win_types, center=True, step=step).mean()
    tm.assert_series_equal(xp, rs)


def test_cmov_window_regular_linear_range(win_types, step):
    # GH 8238
    pytest.importorskip("scipy")
    vals = np.array(range(10), dtype=float)
    xp = vals.copy()
    xp[:2] = np.nan
    xp[-2:] = np.nan
    xp = Series(xp)[::step]

    rs = Series(vals).rolling(5, win_type=win_types, center=True, step=step).mean()
    tm.assert_series_equal(xp, rs)


def test_cmov_window_regular_missing_data(win_types, step):
    # GH 8238
    pytest.importorskip("scipy")
    vals = np.array(
        [6.95, 15.21, 4.72, 9.12, 13.81, 13.49, 16.68, np.nan, 10.63, 14.48]
    )
    xps = {
        "bartlett": [
            np.nan,
            np.nan,
            9.70333,
            10.5225,
            8.4425,
            9.1925,
            12.5575,
            14.3675,
            15.61667,
            13.655,
        ],
        "blackman": [
            np.nan,
            np.nan,
            9.04582,
            11.41536,
            7.73345,
            9.17869,
            12.79607,
            14.20036,
            15.8706,
            13.655,
        ],
        "barthann": [
            np.nan,
            np.nan,
            9.70333,
            10.5225,
            8.4425,
            9.1925,
            12.5575,
            14.3675,
            15.61667,
            13.655,
        ],
        "bohman": [
            np.nan,
            np.nan,
            8.9444,
            11.56327,
            7.61599,
            9.1764,
            12.83559,
            14.17267,
            15.90976,
            13.655,
        ],
        "hamming": [
            np.nan,
            np.nan,
            9.59321,
            10.29694,
            8.71384,
            9.56348,
            12.38009,
            14.20565,
            15.24694,
            13.69758,
        ],
        "nuttall": [
            np.nan,
            np.nan,
            8.47693,
            12.2821,
            7.04618,
            9.16786,
            13.02671,
            14.03673,
            16.08759,
            13.65553,
        ],
        "triang": [
            np.nan,
            np.nan,
            9.33167,
            9.76125,
            9.28667,
            10.34667,
            12.00556,
            13.82125,
            14.49429,
            13.765,
        ],
        "blackmanharris": [
            np.nan,
            np.nan,
            8.42526,
            12.36824,
            6.97691,
            9.16438,
            13.05052,
            14.02175,
            16.1098,
            13.65509,
        ],
    }

    xp = Series(xps[win_types])[::step]
    rs = Series(vals).rolling(5, win_type=win_types, min_periods=3, step=step).mean()
    tm.assert_series_equal(xp, rs)


def test_cmov_window_special(win_types_special, step):
    # GH 8238
    pytest.importorskip("scipy")
    kwds = {
        "kaiser": {"beta": 1.0},
        "gaussian": {"std": 1.0},
        "general_gaussian": {"p": 2.0, "sig": 2.0},
        "exponential": {"tau": 10},
    }

    vals = np.array([6.95, 15.21, 4.72, 9.12, 13.81, 13.49, 16.68, 9.48, 10.63, 14.48])

    xps = {
        "gaussian": [
            np.nan,
            np.nan,
            8.97297,
            9.76077,
            12.24763,
            13.89053,
            13.65671,
            12.01002,
            np.nan,
            np.nan,
        ],
        "general_gaussian": [
            np.nan,
            np.nan,
            9.85011,
            10.71589,
            11.73161,
            13.08516,
            12.95111,
            12.74577,
            np.nan,
            np.nan,
        ],
        "kaiser": [
            np.nan,
            np.nan,
            9.86851,
            11.02969,
            11.65161,
            12.75129,
            12.90702,
            12.83757,
            np.nan,
            np.nan,
        ],
        "exponential": [
            np.nan,
            np.nan,
            9.83364,
            11.10472,
            11.64551,
            12.66138,
            12.92379,
            12.83770,
            np.nan,
            np.nan,
        ],
    }

    xp = Series(xps[win_types_special])[::step]
    rs = (
        Series(vals)
        .rolling(5, win_type=win_types_special, center=True, step=step)
        .mean(**kwds[win_types_special])
    )
    tm.assert_series_equal(xp, rs)


def test_cmov_window_special_linear_range(win_types_special, step):
    # GH 8238
    pytest.importorskip("scipy")
    kwds = {
        "kaiser": {"beta": 1.0},
        "gaussian": {"std": 1.0},
        "general_gaussian": {"p": 2.0, "sig": 2.0},
        "slepian": {"width": 0.5},
        "exponential": {"tau": 10},
    }

    vals = np.array(range(10), dtype=float)
    xp = vals.copy()
    xp[:2] = np.nan
    xp[-2:] = np.nan
    xp = Series(xp)[::step]

    rs = (
        Series(vals)
        .rolling(5, win_type=win_types_special, center=True, step=step)
        .mean(**kwds[win_types_special])
    )
    tm.assert_series_equal(xp, rs)


def test_weighted_var_big_window_no_segfault(win_types, center):
    # GitHub Issue #46772
    pytest.importorskip("scipy")
    x = Series(0)
    result = x.rolling(window=16, center=center, win_type=win_types).var()
    expected = Series(np.nan)

    tm.assert_series_equal(result, expected)


def test_rolling_center_axis_1():
    pytest.importorskip("scipy")
    df = DataFrame(
        {"a": [1, 1, 0, 0, 0, 1], "b": [1, 0, 0, 1, 0, 0], "c": [1, 0, 0, 1, 0, 1]}
    )

    msg = "Support for axis=1 in DataFrame.rolling is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=msg):
        result = df.rolling(window=3, axis=1, win_type="boxcar", center=True).sum()

    expected = DataFrame(
        {"a": [np.nan] * 6, "b": [3.0, 1.0, 0.0, 2.0, 0.0, 2.0], "c": [np.nan] * 6}
    )

    tm.assert_frame_equal(result, expected, check_dtype=True)
