from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    Series,
    bdate_range,
)


@pytest.fixture(params=[True, False])
def raw(request):
    """raw keyword argument for rolling.apply"""
    return request.param


@pytest.fixture(
    params=[
        "sum",
        "mean",
        "median",
        "max",
        "min",
        "var",
        "std",
        "kurt",
        "skew",
        "count",
        "sem",
    ]
)
def arithmetic_win_operators(request):
    return request.param


@pytest.fixture(params=[True, False])
def center(request):
    return request.param


@pytest.fixture(params=[None, 1])
def min_periods(request):
    return request.param


@pytest.fixture(params=[True, False])
def parallel(request):
    """parallel keyword argument for numba.jit"""
    return request.param


# Can parameterize nogil & nopython over True | False, but limiting per
# https://github.com/pandas-dev/pandas/pull/41971#issuecomment-860607472


@pytest.fixture(params=[False])
def nogil(request):
    """nogil keyword argument for numba.jit"""
    return request.param


@pytest.fixture(params=[True])
def nopython(request):
    """nopython keyword argument for numba.jit"""
    return request.param


@pytest.fixture(params=[True, False])
def adjust(request):
    """adjust keyword argument for ewm"""
    return request.param


@pytest.fixture(params=[True, False])
def ignore_na(request):
    """ignore_na keyword argument for ewm"""
    return request.param


@pytest.fixture(params=[True, False])
def numeric_only(request):
    """numeric_only keyword argument"""
    return request.param


@pytest.fixture(
    params=[
        pytest.param("numba", marks=[td.skip_if_no("numba"), pytest.mark.single_cpu]),
        "cython",
    ]
)
def engine(request):
    """engine keyword argument for rolling.apply"""
    return request.param


@pytest.fixture(
    params=[
        pytest.param(
            ("numba", True), marks=[td.skip_if_no("numba"), pytest.mark.single_cpu]
        ),
        ("cython", True),
        ("cython", False),
    ]
)
def engine_and_raw(request):
    """engine and raw keyword arguments for rolling.apply"""
    return request.param


@pytest.fixture(params=["1 day", timedelta(days=1), np.timedelta64(1, "D")])
def halflife_with_times(request):
    """Halflife argument for EWM when times is specified."""
    return request.param


@pytest.fixture
def series():
    """Make mocked series as fixture."""
    arr = np.random.default_rng(2).standard_normal(100)
    locs = np.arange(20, 40)
    arr[locs] = np.nan
    series = Series(arr, index=bdate_range(datetime(2009, 1, 1), periods=100))
    return series


@pytest.fixture
def frame():
    """Make mocked frame as fixture."""
    return DataFrame(
        np.random.default_rng(2).standard_normal((100, 10)),
        index=bdate_range(datetime(2009, 1, 1), periods=100),
    )


@pytest.fixture(params=[None, 1, 2, 5, 10])
def step(request):
    """step keyword argument for rolling window operations."""
    return request.param
