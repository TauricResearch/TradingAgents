"""
This file is very long and growing, but it was decided to not split it yet, as
it's still manageable (2020-03-17, ~1.1k LoC). See gh-31989

Instead of splitting it was decided to define sections here:
- Configuration / Settings
- Autouse fixtures
- Common arguments
- Missing values & co.
- Classes
- Indices
- Series'
- DataFrames
- Operators & Operations
- Data sets/files
- Time zones
- Dtypes
- Misc
"""
from __future__ import annotations

from collections import abc
from datetime import (
    date,
    datetime,
    time,
    timedelta,
    timezone,
)
from decimal import Decimal
import operator
import os
from typing import (
    TYPE_CHECKING,
    Callable,
)

from dateutil.tz import (
    tzlocal,
    tzutc,
)
import hypothesis
from hypothesis import strategies as st
import numpy as np
import pytest
from pytz import (
    FixedOffset,
    utc,
)

from pandas._config.config import _get_option

import pandas.util._test_decorators as td

from pandas.core.dtypes.dtypes import (
    DatetimeTZDtype,
    IntervalDtype,
)

import pandas as pd
from pandas import (
    CategoricalIndex,
    DataFrame,
    Interval,
    IntervalIndex,
    Period,
    RangeIndex,
    Series,
    Timedelta,
    Timestamp,
    date_range,
    period_range,
    timedelta_range,
)
import pandas._testing as tm
from pandas.core import ops
from pandas.core.indexes.api import (
    Index,
    MultiIndex,
)
from pandas.util.version import Version

if TYPE_CHECKING:
    from collections.abc import (
        Hashable,
        Iterator,
    )

try:
    import pyarrow as pa
except ImportError:
    has_pyarrow = False
else:
    del pa
    has_pyarrow = True

import zoneinfo

try:
    zoneinfo.ZoneInfo("UTC")
except zoneinfo.ZoneInfoNotFoundError:
    zoneinfo = None  # type: ignore[assignment]


# ----------------------------------------------------------------
# Configuration / Settings
# ----------------------------------------------------------------
# pytest


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--no-strict-data-files",
        action="store_false",
        help="Don't fail if a test is skipped for missing data file.",
    )


def ignore_doctest_warning(item: pytest.Item, path: str, message: str) -> None:
    """Ignore doctest warning.

    Parameters
    ----------
    item : pytest.Item
        pytest test item.
    path : str
        Module path to Python object, e.g. "pandas.core.frame.DataFrame.append". A
        warning will be filtered when item.name ends with in given path. So it is
        sufficient to specify e.g. "DataFrame.append".
    message : str
        Message to be filtered.
    """
    if item.name.endswith(path):
        item.add_marker(pytest.mark.filterwarnings(f"ignore:{message}"))


def pytest_collection_modifyitems(items, config) -> None:
    is_doctest = config.getoption("--doctest-modules") or config.getoption(
        "--doctest-cython", default=False
    )

    # Warnings from doctests that can be ignored; place reason in comment above.
    # Each entry specifies (path, message) - see the ignore_doctest_warning function
    ignored_doctest_warnings = [
        ("is_int64_dtype", "is_int64_dtype is deprecated"),
        ("is_interval_dtype", "is_interval_dtype is deprecated"),
        ("is_period_dtype", "is_period_dtype is deprecated"),
        ("is_datetime64tz_dtype", "is_datetime64tz_dtype is deprecated"),
        ("is_categorical_dtype", "is_categorical_dtype is deprecated"),
        ("is_sparse", "is_sparse is deprecated"),
        ("DataFrameGroupBy.fillna", "DataFrameGroupBy.fillna is deprecated"),
        ("NDFrame.replace", "The 'method' keyword"),
        ("NDFrame.replace", "Series.replace without 'value'"),
        ("NDFrame.clip", "Downcasting behavior in Series and DataFrame methods"),
        ("Series.idxmin", "The behavior of Series.idxmin"),
        ("Series.idxmax", "The behavior of Series.idxmax"),
        ("SeriesGroupBy.fillna", "SeriesGroupBy.fillna is deprecated"),
        ("SeriesGroupBy.idxmin", "The behavior of Series.idxmin"),
        ("SeriesGroupBy.idxmax", "The behavior of Series.idxmax"),
        # Docstring divides by zero to show behavior difference
        ("missing.mask_zero_div_zero", "divide by zero encountered"),
        (
            "to_pydatetime",
            "The behavior of DatetimeProperties.to_pydatetime is deprecated",
        ),
        (
            "pandas.core.generic.NDFrame.bool",
            "(Series|DataFrame).bool is now deprecated and will be removed "
            "in future version of pandas",
        ),
        (
            "pandas.core.generic.NDFrame.first",
            "first is deprecated and will be removed in a future version. "
            "Please create a mask and filter using `.loc` instead",
        ),
        (
            "Resampler.fillna",
            "DatetimeIndexResampler.fillna is deprecated",
        ),
        (
            "DataFrameGroupBy.fillna",
            "DataFrameGroupBy.fillna with 'method' is deprecated",
        ),
        (
            "DataFrameGroupBy.fillna",
            "DataFrame.fillna with 'method' is deprecated",
        ),
        ("read_parquet", "Passing a BlockManager to DataFrame is deprecated"),
    ]

    if is_doctest:
        for item in items:
            for path, message in ignored_doctest_warnings:
                ignore_doctest_warning(item, path, message)


hypothesis_health_checks = [hypothesis.HealthCheck.too_slow]
if Version(hypothesis.__version__) >= Version("6.83.2"):
    hypothesis_health_checks.append(hypothesis.HealthCheck.differing_executors)

# Hypothesis
hypothesis.settings.register_profile(
    "ci",
    # Hypothesis timing checks are tuned for scalars by default, so we bump
    # them from 200ms to 500ms per test case as the global default.  If this
    # is too short for a specific test, (a) try to make it faster, and (b)
    # if it really is slow add `@settings(deadline=...)` with a working value,
    # or `deadline=None` to entirely disable timeouts for that test.
    # 2022-02-09: Changed deadline from 500 -> None. Deadline leads to
    # non-actionable, flaky CI failures (# GH 24641, 44969, 45118, 44969)
    deadline=None,
    suppress_health_check=tuple(hypothesis_health_checks),
)
hypothesis.settings.load_profile("ci")

# Registering these strategies makes them globally available via st.from_type,
# which is use for offsets in tests/tseries/offsets/test_offsets_properties.py
for name in "MonthBegin MonthEnd BMonthBegin BMonthEnd".split():
    cls = getattr(pd.tseries.offsets, name)
    st.register_type_strategy(
        cls, st.builds(cls, n=st.integers(-99, 99), normalize=st.booleans())
    )

for name in "YearBegin YearEnd BYearBegin BYearEnd".split():
    cls = getattr(pd.tseries.offsets, name)
    st.register_type_strategy(
        cls,
        st.builds(
            cls,
            n=st.integers(-5, 5),
            normalize=st.booleans(),
            month=st.integers(min_value=1, max_value=12),
        ),
    )

for name in "QuarterBegin QuarterEnd BQuarterBegin BQuarterEnd".split():
    cls = getattr(pd.tseries.offsets, name)
    st.register_type_strategy(
        cls,
        st.builds(
            cls,
            n=st.integers(-24, 24),
            normalize=st.booleans(),
            startingMonth=st.integers(min_value=1, max_value=12),
        ),
    )


# ----------------------------------------------------------------
# Autouse fixtures
# ----------------------------------------------------------------


# https://github.com/pytest-dev/pytest/issues/11873
# Would like to avoid autouse=True, but cannot as of pytest 8.0.0
@pytest.fixture(autouse=True)
def add_doctest_imports(doctest_namespace) -> None:
    """
    Make `np` and `pd` names available for doctests.
    """
    doctest_namespace["np"] = np
    doctest_namespace["pd"] = pd


@pytest.fixture(autouse=True)
def configure_tests() -> None:
    """
    Configure settings for all tests and test modules.
    """
    pd.set_option("chained_assignment", "raise")


# ----------------------------------------------------------------
# Common arguments
# ----------------------------------------------------------------
@pytest.fixture(params=[0, 1, "index", "columns"], ids=lambda x: f"axis={repr(x)}")
def axis(request):
    """
    Fixture for returning the axis numbers of a DataFrame.
    """
    return request.param


axis_frame = axis


@pytest.fixture(params=[1, "columns"], ids=lambda x: f"axis={repr(x)}")
def axis_1(request):
    """
    Fixture for returning aliases of axis 1 of a DataFrame.
    """
    return request.param


@pytest.fixture(params=[True, False, None])
def observed(request):
    """
    Pass in the observed keyword to groupby for [True, False]
    This indicates whether categoricals should return values for
    values which are not in the grouper [False / None], or only values which
    appear in the grouper [True]. [None] is supported for future compatibility
    if we decide to change the default (and would need to warn if this
    parameter is not passed).
    """
    return request.param


@pytest.fixture(params=[True, False, None])
def ordered(request):
    """
    Boolean 'ordered' parameter for Categorical.
    """
    return request.param


@pytest.fixture(params=[True, False])
def skipna(request):
    """
    Boolean 'skipna' parameter.
    """
    return request.param


@pytest.fixture(params=["first", "last", False])
def keep(request):
    """
    Valid values for the 'keep' parameter used in
    .duplicated or .drop_duplicates
    """
    return request.param


@pytest.fixture(params=["both", "neither", "left", "right"])
def inclusive_endpoints_fixture(request):
    """
    Fixture for trying all interval 'inclusive' parameters.
    """
    return request.param


@pytest.fixture(params=["left", "right", "both", "neither"])
def closed(request):
    """
    Fixture for trying all interval closed parameters.
    """
    return request.param


@pytest.fixture(params=["left", "right", "both", "neither"])
def other_closed(request):
    """
    Secondary closed fixture to allow parametrizing over all pairs of closed.
    """
    return request.param


@pytest.fixture(
    params=[
        None,
        "gzip",
        "bz2",
        "zip",
        "xz",
        "tar",
        pytest.param("zstd", marks=td.skip_if_no("zstandard")),
    ]
)
def compression(request):
    """
    Fixture for trying common compression types in compression tests.
    """
    return request.param


@pytest.fixture(
    params=[
        "gzip",
        "bz2",
        "zip",
        "xz",
        "tar",
        pytest.param("zstd", marks=td.skip_if_no("zstandard")),
    ]
)
def compression_only(request):
    """
    Fixture for trying common compression types in compression tests excluding
    uncompressed case.
    """
    return request.param


@pytest.fixture(params=[True, False])
def writable(request):
    """
    Fixture that an array is writable.
    """
    return request.param


@pytest.fixture(params=["inner", "outer", "left", "right"])
def join_type(request):
    """
    Fixture for trying all types of join operations.
    """
    return request.param


@pytest.fixture(params=["nlargest", "nsmallest"])
def nselect_method(request):
    """
    Fixture for trying all nselect methods.
    """
    return request.param


# ----------------------------------------------------------------
# Missing values & co.
# ----------------------------------------------------------------
@pytest.fixture(params=tm.NULL_OBJECTS, ids=lambda x: type(x).__name__)
def nulls_fixture(request):
    """
    Fixture for each null type in pandas.
    """
    return request.param


nulls_fixture2 = nulls_fixture  # Generate cartesian product of nulls_fixture


@pytest.fixture(params=[None, np.nan, pd.NaT])
def unique_nulls_fixture(request):
    """
    Fixture for each null type in pandas, each null type exactly once.
    """
    return request.param


# Generate cartesian product of unique_nulls_fixture:
unique_nulls_fixture2 = unique_nulls_fixture


@pytest.fixture(params=tm.NP_NAT_OBJECTS, ids=lambda x: type(x).__name__)
def np_nat_fixture(request):
    """
    Fixture for each NaT type in numpy.
    """
    return request.param


# Generate cartesian product of np_nat_fixture:
np_nat_fixture2 = np_nat_fixture


# ----------------------------------------------------------------
# Classes
# ----------------------------------------------------------------


@pytest.fixture(params=[DataFrame, Series])
def frame_or_series(request):
    """
    Fixture to parametrize over DataFrame and Series.
    """
    return request.param


@pytest.fixture(params=[Index, Series], ids=["index", "series"])
def index_or_series(request):
    """
    Fixture to parametrize over Index and Series, made necessary by a mypy
    bug, giving an error:

    List item 0 has incompatible type "Type[Series]"; expected "Type[PandasObject]"

    See GH#29725
    """
    return request.param


# Generate cartesian product of index_or_series fixture:
index_or_series2 = index_or_series


@pytest.fixture(params=[Index, Series, pd.array], ids=["index", "series", "array"])
def index_or_series_or_array(request):
    """
    Fixture to parametrize over Index, Series, and ExtensionArray
    """
    return request.param


@pytest.fixture(params=[Index, Series, DataFrame, pd.array], ids=lambda x: x.__name__)
def box_with_array(request):
    """
    Fixture to test behavior for Index, Series, DataFrame, and pandas Array
    classes
    """
    return request.param


box_with_array2 = box_with_array


@pytest.fixture
def dict_subclass() -> type[dict]:
    """
    Fixture for a dictionary subclass.
    """

    class TestSubDict(dict):
        def __init__(self, *args, **kwargs) -> None:
            dict.__init__(self, *args, **kwargs)

    return TestSubDict


@pytest.fixture
def non_dict_mapping_subclass() -> type[abc.Mapping]:
    """
    Fixture for a non-mapping dictionary subclass.
    """

    class TestNonDictMapping(abc.Mapping):
        def __init__(self, underlying_dict) -> None:
            self._data = underlying_dict

        def __getitem__(self, key):
            return self._data.__getitem__(key)

        def __iter__(self) -> Iterator:
            return self._data.__iter__()

        def __len__(self) -> int:
            return self._data.__len__()

    return TestNonDictMapping


# ----------------------------------------------------------------
# Indices
# ----------------------------------------------------------------
@pytest.fixture
def multiindex_year_month_day_dataframe_random_data():
    """
    DataFrame with 3 level MultiIndex (year, month, day) covering
    first 100 business days from 2000-01-01 with random data
    """
    tdf = DataFrame(
        np.random.default_rng(2).standard_normal((100, 4)),
        columns=Index(list("ABCD")),
        index=date_range("2000-01-01", periods=100, freq="B"),
    )
    ymd = tdf.groupby([lambda x: x.year, lambda x: x.month, lambda x: x.day]).sum()
    # use int64 Index, to make sure things work
    ymd.index = ymd.index.set_levels([lev.astype("i8") for lev in ymd.index.levels])
    ymd.index.set_names(["year", "month", "day"], inplace=True)
    return ymd


@pytest.fixture
def lexsorted_two_level_string_multiindex() -> MultiIndex:
    """
    2-level MultiIndex, lexsorted, with string names.
    """
    return MultiIndex(
        levels=[["foo", "bar", "baz", "qux"], ["one", "two", "three"]],
        codes=[[0, 0, 0, 1, 1, 2, 2, 3, 3, 3], [0, 1, 2, 0, 1, 1, 2, 0, 1, 2]],
        names=["first", "second"],
    )


@pytest.fixture
def multiindex_dataframe_random_data(
    lexsorted_two_level_string_multiindex,
) -> DataFrame:
    """DataFrame with 2 level MultiIndex with random data"""
    index = lexsorted_two_level_string_multiindex
    return DataFrame(
        np.random.default_rng(2).standard_normal((10, 3)),
        index=index,
        columns=Index(["A", "B", "C"], name="exp"),
    )


def _create_multiindex():
    """
    MultiIndex used to test the general functionality of this object
    """

    # See Also: tests.multi.conftest.idx
    major_axis = Index(["foo", "bar", "baz", "qux"])
    minor_axis = Index(["one", "two"])

    major_codes = np.array([0, 0, 1, 2, 3, 3])
    minor_codes = np.array([0, 1, 0, 1, 0, 1])
    index_names = ["first", "second"]
    return MultiIndex(
        levels=[major_axis, minor_axis],
        codes=[major_codes, minor_codes],
        names=index_names,
        verify_integrity=False,
    )


def _create_mi_with_dt64tz_level():
    """
    MultiIndex with a level that is a tzaware DatetimeIndex.
    """
    # GH#8367 round trip with pickle
    return MultiIndex.from_product(
        [[1, 2], ["a", "b"], date_range("20130101", periods=3, tz="US/Eastern")],
        names=["one", "two", "three"],
    )


indices_dict = {
    "object": Index([f"pandas_{i}" for i in range(100)], dtype=object),
    "string": Index([f"pandas_{i}" for i in range(100)], dtype="str"),
    "datetime": date_range("2020-01-01", periods=100),
    "datetime-tz": date_range("2020-01-01", periods=100, tz="US/Pacific"),
    "period": period_range("2020-01-01", periods=100, freq="D"),
    "timedelta": timedelta_range(start="1 day", periods=100, freq="D"),
    "range": RangeIndex(100),
    "int8": Index(np.arange(100), dtype="int8"),
    "int16": Index(np.arange(100), dtype="int16"),
    "int32": Index(np.arange(100), dtype="int32"),
    "int64": Index(np.arange(100), dtype="int64"),
    "uint8": Index(np.arange(100), dtype="uint8"),
    "uint16": Index(np.arange(100), dtype="uint16"),
    "uint32": Index(np.arange(100), dtype="uint32"),
    "uint64": Index(np.arange(100), dtype="uint64"),
    "float32": Index(np.arange(100), dtype="float32"),
    "float64": Index(np.arange(100), dtype="float64"),
    "bool-object": Index([True, False] * 5, dtype=object),
    "bool-dtype": Index([True, False] * 5, dtype=bool),
    "complex64": Index(
        np.arange(100, dtype="complex64") + 1.0j * np.arange(100, dtype="complex64")
    ),
    "complex128": Index(
        np.arange(100, dtype="complex128") + 1.0j * np.arange(100, dtype="complex128")
    ),
    "categorical": CategoricalIndex(list("abcd") * 25),
    "interval": IntervalIndex.from_breaks(np.linspace(0, 100, num=101)),
    "empty": Index([]),
    "tuples": MultiIndex.from_tuples(zip(["foo", "bar", "baz"], [1, 2, 3])),
    "mi-with-dt64tz-level": _create_mi_with_dt64tz_level(),
    "multi": _create_multiindex(),
    "repeats": Index([0, 0, 1, 1, 2, 2]),
    "nullable_int": Index(np.arange(100), dtype="Int64"),
    "nullable_uint": Index(np.arange(100), dtype="UInt16"),
    "nullable_float": Index(np.arange(100), dtype="Float32"),
    "nullable_bool": Index(np.arange(100).astype(bool), dtype="boolean"),
    "string-python": Index(
        pd.array([f"pandas_{i}" for i in range(100)], dtype="string[python]")
    ),
}
if has_pyarrow:
    idx = Index(pd.array([f"pandas_{i}" for i in range(100)], dtype="string[pyarrow]"))
    indices_dict["string-pyarrow"] = idx


@pytest.fixture(params=indices_dict.keys())
def index(request):
    """
    Fixture for many "simple" kinds of indices.

    These indices are unlikely to cover corner cases, e.g.
        - no names
        - no NaTs/NaNs
        - no values near implementation bounds
        - ...
    """
    # copy to avoid mutation, e.g. setting .name
    return indices_dict[request.param].copy()


# Needed to generate cartesian product of indices
index_fixture2 = index


@pytest.fixture(
    params=[
        key for key, value in indices_dict.items() if not isinstance(value, MultiIndex)
    ]
)
def index_flat(request):
    """
    index fixture, but excluding MultiIndex cases.
    """
    key = request.param
    return indices_dict[key].copy()


# Alias so we can test with cartesian product of index_flat
index_flat2 = index_flat


@pytest.fixture(
    params=[
        key
        for key, value in indices_dict.items()
        if not (
            key.startswith(("int", "uint", "float"))
            or key in ["range", "empty", "repeats", "bool-dtype"]
        )
        and not isinstance(value, MultiIndex)
    ]
)
def index_with_missing(request):
    """
    Fixture for indices with missing values.

    Integer-dtype and empty cases are excluded because they cannot hold missing
    values.

    MultiIndex is excluded because isna() is not defined for MultiIndex.
    """

    # GH 35538. Use deep copy to avoid illusive bug on np-dev
    # GHA pipeline that writes into indices_dict despite copy
    ind = indices_dict[request.param].copy(deep=True)
    vals = ind.values.copy()
    if request.param in ["tuples", "mi-with-dt64tz-level", "multi"]:
        # For setting missing values in the top level of MultiIndex
        vals = ind.tolist()
        vals[0] = (None,) + vals[0][1:]
        vals[-1] = (None,) + vals[-1][1:]
        return MultiIndex.from_tuples(vals)
    else:
        vals[0] = None
        vals[-1] = None
        return type(ind)(vals)


# ----------------------------------------------------------------
# Series'
# ----------------------------------------------------------------
@pytest.fixture
def string_series() -> Series:
    """
    Fixture for Series of floats with Index of unique strings
    """
    return Series(
        np.arange(30, dtype=np.float64) * 1.1,
        index=Index([f"i_{i}" for i in range(30)]),
        name="series",
    )


@pytest.fixture
def object_series() -> Series:
    """
    Fixture for Series of dtype object with Index of unique strings
    """
    data = [f"foo_{i}" for i in range(30)]
    index = Index([f"bar_{i}" for i in range(30)])
    return Series(data, index=index, name="objects", dtype=object)


@pytest.fixture
def datetime_series() -> Series:
    """
    Fixture for Series of floats with DatetimeIndex
    """
    return Series(
        np.random.default_rng(2).standard_normal(30),
        index=date_range("2000-01-01", periods=30, freq="B"),
        name="ts",
    )


def _create_series(index):
    """Helper for the _series dict"""
    size = len(index)
    data = np.random.default_rng(2).standard_normal(size)
    return Series(data, index=index, name="a", copy=False)


_series = {
    f"series-with-{index_id}-index": _create_series(index)
    for index_id, index in indices_dict.items()
}


@pytest.fixture
def series_with_simple_index(index) -> Series:
    """
    Fixture for tests on series with changing types of indices.
    """
    return _create_series(index)


_narrow_series = {
    f"{dtype.__name__}-series": Series(
        range(30), index=[f"i-{i}" for i in range(30)], name="a", dtype=dtype
    )
    for dtype in tm.NARROW_NP_DTYPES
}


_index_or_series_objs = {**indices_dict, **_series, **_narrow_series}


@pytest.fixture(params=_index_or_series_objs.keys())
def index_or_series_obj(request):
    """
    Fixture for tests on indexes, series and series with a narrow dtype
    copy to avoid mutation, e.g. setting .name
    """
    return _index_or_series_objs[request.param].copy(deep=True)


_typ_objects_series = {
    f"{dtype.__name__}-series": Series(dtype) for dtype in tm.PYTHON_DATA_TYPES
}


_index_or_series_memory_objs = {
    **indices_dict,
    **_series,
    **_narrow_series,
    **_typ_objects_series,
}


@pytest.fixture(params=_index_or_series_memory_objs.keys())
def index_or_series_memory_obj(request):
    """
    Fixture for tests on indexes, series, series with a narrow dtype and
    series with empty objects type
    copy to avoid mutation, e.g. setting .name
    """
    return _index_or_series_memory_objs[request.param].copy(deep=True)


# ----------------------------------------------------------------
# DataFrames
# ----------------------------------------------------------------
@pytest.fixture
def int_frame() -> DataFrame:
    """
    Fixture for DataFrame of ints with index of unique strings

    Columns are ['A', 'B', 'C', 'D']
    """
    return DataFrame(
        np.ones((30, 4), dtype=np.int64),
        index=Index([f"foo_{i}" for i in range(30)]),
        columns=Index(list("ABCD")),
    )


@pytest.fixture
def float_frame() -> DataFrame:
    """
    Fixture for DataFrame of floats with index of unique strings

    Columns are ['A', 'B', 'C', 'D'].
    """
    return DataFrame(
        np.random.default_rng(2).standard_normal((30, 4)),
        index=Index([f"foo_{i}" for i in range(30)]),
        columns=Index(list("ABCD")),
    )


@pytest.fixture
def rand_series_with_duplicate_datetimeindex() -> Series:
    """
    Fixture for Series with a DatetimeIndex that has duplicates.
    """
    dates = [
        datetime(2000, 1, 2),
        datetime(2000, 1, 2),
        datetime(2000, 1, 2),
        datetime(2000, 1, 3),
        datetime(2000, 1, 3),
        datetime(2000, 1, 3),
        datetime(2000, 1, 4),
        datetime(2000, 1, 4),
        datetime(2000, 1, 4),
        datetime(2000, 1, 5),
    ]

    return Series(np.random.default_rng(2).standard_normal(len(dates)), index=dates)


# ----------------------------------------------------------------
# Scalars
# ----------------------------------------------------------------
@pytest.fixture(
    params=[
        (Interval(left=0, right=5), IntervalDtype("int64", "right")),
        (Interval(left=0.1, right=0.5), IntervalDtype("float64", "right")),
        (Period("2012-01", freq="M"), "period[M]"),
        (Period("2012-02-01", freq="D"), "period[D]"),
        (
            Timestamp("2011-01-01", tz="US/Eastern"),
            DatetimeTZDtype(unit="s", tz="US/Eastern"),
        ),
        (Timedelta(seconds=500), "timedelta64[ns]"),
    ]
)
def ea_scalar_and_dtype(request):
    return request.param


# ----------------------------------------------------------------
# Operators & Operations
# ----------------------------------------------------------------


@pytest.fixture(params=tm.arithmetic_dunder_methods)
def all_arithmetic_operators(request):
    """
    Fixture for dunder names for common arithmetic operations.
    """
    return request.param


@pytest.fixture(
    params=[
        operator.add,
        ops.radd,
        operator.sub,
        ops.rsub,
        operator.mul,
        ops.rmul,
        operator.truediv,
        ops.rtruediv,
        operator.floordiv,
        ops.rfloordiv,
        operator.mod,
        ops.rmod,
        operator.pow,
        ops.rpow,
        operator.eq,
        operator.ne,
        operator.lt,
        operator.le,
        operator.gt,
        operator.ge,
        operator.and_,
        ops.rand_,
        operator.xor,
        ops.rxor,
        operator.or_,
        ops.ror_,
    ]
)
def all_binary_operators(request):
    """
    Fixture for operator and roperator arithmetic, comparison, and logical ops.
    """
    return request.param


@pytest.fixture(
    params=[
        operator.add,
        ops.radd,
        operator.sub,
        ops.rsub,
        operator.mul,
        ops.rmul,
        operator.truediv,
        ops.rtruediv,
        operator.floordiv,
        ops.rfloordiv,
        operator.mod,
        ops.rmod,
        operator.pow,
        ops.rpow,
    ]
)
def all_arithmetic_functions(request):
    """
    Fixture for operator and roperator arithmetic functions.

    Notes
    -----
    This includes divmod and rdivmod, whereas all_arithmetic_operators
    does not.
    """
    return request.param


_all_numeric_reductions = [
    "count",
    "sum",
    "max",
    "min",
    "mean",
    "prod",
    "std",
    "var",
    "median",
    "kurt",
    "skew",
    "sem",
]


@pytest.fixture(params=_all_numeric_reductions)
def all_numeric_reductions(request):
    """
    Fixture for numeric reduction names.
    """
    return request.param


_all_boolean_reductions = ["all", "any"]


@pytest.fixture(params=_all_boolean_reductions)
def all_boolean_reductions(request):
    """
    Fixture for boolean reduction names.
    """
    return request.param


_all_reductions = _all_numeric_reductions + _all_boolean_reductions


@pytest.fixture(params=_all_reductions)
def all_reductions(request):
    """
    Fixture for all (boolean + numeric) reduction names.
    """
    return request.param


@pytest.fixture(
    params=[
        operator.eq,
        operator.ne,
        operator.gt,
        operator.ge,
        operator.lt,
        operator.le,
    ]
)
def comparison_op(request):
    """
    Fixture for operator module comparison functions.
    """
    return request.param


@pytest.fixture(params=["__le__", "__lt__", "__ge__", "__gt__"])
def compare_operators_no_eq_ne(request):
    """
    Fixture for dunder names for compare operations except == and !=

    * >=
    * >
    * <
    * <=
    """
    return request.param


@pytest.fixture(
    params=["__and__", "__rand__", "__or__", "__ror__", "__xor__", "__rxor__"]
)
def all_logical_operators(request):
    """
    Fixture for dunder names for common logical operations

    * |
    * &
    * ^
    """
    return request.param


_all_numeric_accumulations = ["cumsum", "cumprod", "cummin", "cummax"]


@pytest.fixture(params=_all_numeric_accumulations)
def all_numeric_accumulations(request):
    """
    Fixture for numeric accumulation names
    """
    return request.param


# ----------------------------------------------------------------
# Data sets/files
# ----------------------------------------------------------------
@pytest.fixture
def strict_data_files(pytestconfig):
    """
    Returns the configuration for the test setting `--no-strict-data-files`.
    """
    return pytestconfig.getoption("--no-strict-data-files")


@pytest.fixture
def datapath(strict_data_files: str) -> Callable[..., str]:
    """
    Get the path to a data file.

    Parameters
    ----------
    path : str
        Path to the file, relative to ``pandas/tests/``

    Returns
    -------
    path including ``pandas/tests``.

    Raises
    ------
    ValueError
        If the path doesn't exist and the --no-strict-data-files option is not set.
    """
    BASE_PATH = os.path.join(os.path.dirname(__file__), "tests")

    def deco(*args):
        path = os.path.join(BASE_PATH, *args)
        if not os.path.exists(path):
            if strict_data_files:
                raise ValueError(
                    f"Could not find file {path} and --no-strict-data-files is not set."
                )
            pytest.skip(f"Could not find {path}.")
        return path

    return deco


# ----------------------------------------------------------------
# Time zones
# ----------------------------------------------------------------
TIMEZONES = [
    None,
    "UTC",
    "US/Eastern",
    "Asia/Tokyo",
    "dateutil/US/Pacific",
    "dateutil/Asia/Singapore",
    "+01:15",
    "-02:15",
    "UTC+01:15",
    "UTC-02:15",
    tzutc(),
    tzlocal(),
    FixedOffset(300),
    FixedOffset(0),
    FixedOffset(-300),
    timezone.utc,
    timezone(timedelta(hours=1)),
    timezone(timedelta(hours=-1), name="foo"),
]
if zoneinfo is not None:
    TIMEZONES.extend(
        [
            zoneinfo.ZoneInfo("US/Pacific"),  # type: ignore[list-item]
            zoneinfo.ZoneInfo("UTC"),  # type: ignore[list-item]
        ]
    )
TIMEZONE_IDS = [repr(i) for i in TIMEZONES]


@td.parametrize_fixture_doc(str(TIMEZONE_IDS))
@pytest.fixture(params=TIMEZONES, ids=TIMEZONE_IDS)
def tz_naive_fixture(request):
    """
    Fixture for trying timezones including default (None): {0}
    """
    return request.param


@td.parametrize_fixture_doc(str(TIMEZONE_IDS[1:]))
@pytest.fixture(params=TIMEZONES[1:], ids=TIMEZONE_IDS[1:])
def tz_aware_fixture(request):
    """
    Fixture for trying explicit timezones: {0}
    """
    return request.param


# Generate cartesian product of tz_aware_fixture:
tz_aware_fixture2 = tz_aware_fixture


_UTCS = ["utc", "dateutil/UTC", utc, tzutc(), timezone.utc]
if zoneinfo is not None:
    _UTCS.append(zoneinfo.ZoneInfo("UTC"))


@pytest.fixture(params=_UTCS)
def utc_fixture(request):
    """
    Fixture to provide variants of UTC timezone strings and tzinfo objects.
    """
    return request.param


utc_fixture2 = utc_fixture


@pytest.fixture(params=["s", "ms", "us", "ns"])
def unit(request):
    """
    datetime64 units we support.
    """
    return request.param


unit2 = unit


# ----------------------------------------------------------------
# Dtypes
# ----------------------------------------------------------------
@pytest.fixture(params=tm.STRING_DTYPES)
def string_dtype(request):
    """
    Parametrized fixture for string dtypes.

    * str
    * 'str'
    * 'U'
    """
    return request.param


@pytest.fixture(
    params=[
        ("python", pd.NA),
        pytest.param(("pyarrow", pd.NA), marks=td.skip_if_no("pyarrow")),
        pytest.param(("pyarrow", np.nan), marks=td.skip_if_no("pyarrow")),
        ("python", np.nan),
    ],
    ids=[
        "string=string[python]",
        "string=string[pyarrow]",
        "string=str[pyarrow]",
        "string=str[python]",
    ],
)
def string_dtype_no_object(request):
    """
    Parametrized fixture for string dtypes.
    * 'string[python]' (NA variant)
    * 'string[pyarrow]' (NA variant)
    * 'str' (NaN variant, with pyarrow)
    * 'str' (NaN variant, without pyarrow)
    """
    # need to instantiate the StringDtype here instead of in the params
    # to avoid importing pyarrow during test collection
    storage, na_value = request.param
    return pd.StringDtype(storage, na_value)


@pytest.fixture(
    params=[
        "string[python]",
        pytest.param("string[pyarrow]", marks=td.skip_if_no("pyarrow")),
    ]
)
def nullable_string_dtype(request):
    """
    Parametrized fixture for string dtypes.

    * 'string[python]'
    * 'string[pyarrow]'
    """
    return request.param


@pytest.fixture(
    params=[
        pytest.param(("pyarrow", np.nan), marks=td.skip_if_no("pyarrow")),
        pytest.param(("pyarrow", pd.NA), marks=td.skip_if_no("pyarrow")),
    ]
)
def pyarrow_string_dtype(request):
    """
    Parametrized fixture for string dtypes backed by Pyarrow.

    * 'str[pyarrow]'
    * 'string[pyarrow]'
    """
    return pd.StringDtype(*request.param)


@pytest.fixture(
    params=[
        "python",
        pytest.param("pyarrow", marks=td.skip_if_no("pyarrow")),
    ]
)
def string_storage(request):
    """
    Parametrized fixture for pd.options.mode.string_storage.

    * 'python'
    * 'pyarrow'
    """
    return request.param


@pytest.fixture(
    params=[
        ("python", pd.NA),
        pytest.param(("pyarrow", pd.NA), marks=td.skip_if_no("pyarrow")),
        pytest.param(("pyarrow", np.nan), marks=td.skip_if_no("pyarrow")),
        ("python", np.nan),
    ],
    ids=[
        "string=string[python]",
        "string=string[pyarrow]",
        "string=str[pyarrow]",
        "string=str[python]",
    ],
)
def string_dtype_arguments(request):
    """
    Parametrized fixture for StringDtype storage and na_value.

    * 'python' + pd.NA
    * 'pyarrow' + pd.NA
    * 'pyarrow' + np.nan
    """
    return request.param


@pytest.fixture(
    params=[
        "numpy_nullable",
        pytest.param("pyarrow", marks=td.skip_if_no("pyarrow")),
    ]
)
def dtype_backend(request):
    """
    Parametrized fixture for pd.options.mode.string_storage.

    * 'python'
    * 'pyarrow'
    """
    return request.param


# Alias so we can test with cartesian product of string_storage
string_storage2 = string_storage
string_dtype_arguments2 = string_dtype_arguments


@pytest.fixture(params=tm.BYTES_DTYPES)
def bytes_dtype(request):
    """
    Parametrized fixture for bytes dtypes.

    * bytes
    * 'bytes'
    """
    return request.param


@pytest.fixture(params=tm.OBJECT_DTYPES)
def object_dtype(request):
    """
    Parametrized fixture for object dtypes.

    * object
    * 'object'
    """
    return request.param


@pytest.fixture(
    params=[
        np.dtype("object"),
        ("python", pd.NA),
        pytest.param(("pyarrow", pd.NA), marks=td.skip_if_no("pyarrow")),
        pytest.param(("pyarrow", np.nan), marks=td.skip_if_no("pyarrow")),
        ("python", np.nan),
    ],
    ids=[
        "string=object",
        "string=string[python]",
        "string=string[pyarrow]",
        "string=str[pyarrow]",
        "string=str[python]",
    ],
)
def any_string_dtype(request):
    """
    Parametrized fixture for string dtypes.
    * 'object'
    * 'string[python]' (NA variant)
    * 'string[pyarrow]' (NA variant)
    * 'str' (NaN variant, with pyarrow)
    * 'str' (NaN variant, without pyarrow)
    """
    if isinstance(request.param, np.dtype):
        return request.param
    else:
        # need to instantiate the StringDtype here instead of in the params
        # to avoid importing pyarrow during test collection
        storage, na_value = request.param
        return pd.StringDtype(storage, na_value)


@pytest.fixture(params=tm.DATETIME64_DTYPES)
def datetime64_dtype(request):
    """
    Parametrized fixture for datetime64 dtypes.

    * 'datetime64[ns]'
    * 'M8[ns]'
    """
    return request.param


@pytest.fixture(params=tm.TIMEDELTA64_DTYPES)
def timedelta64_dtype(request):
    """
    Parametrized fixture for timedelta64 dtypes.

    * 'timedelta64[ns]'
    * 'm8[ns]'
    """
    return request.param


@pytest.fixture
def fixed_now_ts() -> Timestamp:
    """
    Fixture emits fixed Timestamp.now()
    """
    return Timestamp(  # pyright: ignore[reportGeneralTypeIssues]
        year=2021, month=1, day=1, hour=12, minute=4, second=13, microsecond=22
    )


@pytest.fixture(params=tm.FLOAT_NUMPY_DTYPES)
def float_numpy_dtype(request):
    """
    Parameterized fixture for float dtypes.

    * float
    * 'float32'
    * 'float64'
    """
    return request.param


@pytest.fixture(params=tm.FLOAT_EA_DTYPES)
def float_ea_dtype(request):
    """
    Parameterized fixture for float dtypes.

    * 'Float32'
    * 'Float64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_FLOAT_DTYPES)
def any_float_dtype(request):
    """
    Parameterized fixture for float dtypes.

    * float
    * 'float32'
    * 'float64'
    * 'Float32'
    * 'Float64'
    """
    return request.param


@pytest.fixture(params=tm.COMPLEX_DTYPES)
def complex_dtype(request):
    """
    Parameterized fixture for complex dtypes.

    * complex
    * 'complex64'
    * 'complex128'
    """
    return request.param


@pytest.fixture(params=tm.COMPLEX_FLOAT_DTYPES)
def complex_or_float_dtype(request):
    """
    Parameterized fixture for complex and numpy float dtypes.

    * complex
    * 'complex64'
    * 'complex128'
    * float
    * 'float32'
    * 'float64'
    """
    return request.param


@pytest.fixture(params=tm.SIGNED_INT_NUMPY_DTYPES)
def any_signed_int_numpy_dtype(request):
    """
    Parameterized fixture for signed integer dtypes.

    * int
    * 'int8'
    * 'int16'
    * 'int32'
    * 'int64'
    """
    return request.param


@pytest.fixture(params=tm.UNSIGNED_INT_NUMPY_DTYPES)
def any_unsigned_int_numpy_dtype(request):
    """
    Parameterized fixture for unsigned integer dtypes.

    * 'uint8'
    * 'uint16'
    * 'uint32'
    * 'uint64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_INT_NUMPY_DTYPES)
def any_int_numpy_dtype(request):
    """
    Parameterized fixture for any integer dtype.

    * int
    * 'int8'
    * 'uint8'
    * 'int16'
    * 'uint16'
    * 'int32'
    * 'uint32'
    * 'int64'
    * 'uint64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_INT_EA_DTYPES)
def any_int_ea_dtype(request):
    """
    Parameterized fixture for any nullable integer dtype.

    * 'UInt8'
    * 'Int8'
    * 'UInt16'
    * 'Int16'
    * 'UInt32'
    * 'Int32'
    * 'UInt64'
    * 'Int64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_INT_DTYPES)
def any_int_dtype(request):
    """
    Parameterized fixture for any nullable integer dtype.

    * int
    * 'int8'
    * 'uint8'
    * 'int16'
    * 'uint16'
    * 'int32'
    * 'uint32'
    * 'int64'
    * 'uint64'
    * 'UInt8'
    * 'Int8'
    * 'UInt16'
    * 'Int16'
    * 'UInt32'
    * 'Int32'
    * 'UInt64'
    * 'Int64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_INT_EA_DTYPES + tm.FLOAT_EA_DTYPES)
def any_numeric_ea_dtype(request):
    """
    Parameterized fixture for any nullable integer dtype and
    any float ea dtypes.

    * 'UInt8'
    * 'Int8'
    * 'UInt16'
    * 'Int16'
    * 'UInt32'
    * 'Int32'
    * 'UInt64'
    * 'Int64'
    * 'Float32'
    * 'Float64'
    """
    return request.param


#  Unsupported operand types for + ("List[Union[str, ExtensionDtype, dtype[Any],
#  Type[object]]]" and "List[str]")
@pytest.fixture(
    params=tm.ALL_INT_EA_DTYPES
    + tm.FLOAT_EA_DTYPES
    + tm.ALL_INT_PYARROW_DTYPES_STR_REPR
    + tm.FLOAT_PYARROW_DTYPES_STR_REPR  # type: ignore[operator]
)
def any_numeric_ea_and_arrow_dtype(request):
    """
    Parameterized fixture for any nullable integer dtype and
    any float ea dtypes.

    * 'UInt8'
    * 'Int8'
    * 'UInt16'
    * 'Int16'
    * 'UInt32'
    * 'Int32'
    * 'UInt64'
    * 'Int64'
    * 'Float32'
    * 'Float64'
    * 'uint8[pyarrow]'
    * 'int8[pyarrow]'
    * 'uint16[pyarrow]'
    * 'int16[pyarrow]'
    * 'uint32[pyarrow]'
    * 'int32[pyarrow]'
    * 'uint64[pyarrow]'
    * 'int64[pyarrow]'
    * 'float32[pyarrow]'
    * 'float64[pyarrow]'
    """
    return request.param


@pytest.fixture(params=tm.SIGNED_INT_EA_DTYPES)
def any_signed_int_ea_dtype(request):
    """
    Parameterized fixture for any signed nullable integer dtype.

    * 'Int8'
    * 'Int16'
    * 'Int32'
    * 'Int64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_REAL_NUMPY_DTYPES)
def any_real_numpy_dtype(request):
    """
    Parameterized fixture for any (purely) real numeric dtype.

    * int
    * 'int8'
    * 'uint8'
    * 'int16'
    * 'uint16'
    * 'int32'
    * 'uint32'
    * 'int64'
    * 'uint64'
    * float
    * 'float32'
    * 'float64'
    """
    return request.param


@pytest.fixture(params=tm.ALL_REAL_DTYPES)
def any_real_numeric_dtype(request):
    """
    Parameterized fixture for any (purely) real numeric dtype.

    * int
    * 'int8'
    * 'uint8'
    * 'int16'
    * 'uint16'
    * 'int32'
    * 'uint32'
    * 'int64'
    * 'uint64'
    * float
    * 'float32'
    * 'float64'

    and associated ea dtypes.
    """
    return request.param


@pytest.fixture(params=tm.ALL_NUMPY_DTYPES)
def any_numpy_dtype(request):
    """
    Parameterized fixture for all numpy dtypes.

    * bool
    * 'bool'
    * int
    * 'int8'
    * 'uint8'
    * 'int16'
    * 'uint16'
    * 'int32'
    * 'uint32'
    * 'int64'
    * 'uint64'
    * float
    * 'float32'
    * 'float64'
    * complex
    * 'complex64'
    * 'complex128'
    * str
    * 'str'
    * 'U'
    * bytes
    * 'bytes'
    * 'datetime64[ns]'
    * 'M8[ns]'
    * 'timedelta64[ns]'
    * 'm8[ns]'
    * object
    * 'object'
    """
    return request.param


@pytest.fixture(params=tm.ALL_REAL_NULLABLE_DTYPES)
def any_real_nullable_dtype(request):
    """
    Parameterized fixture for all real dtypes that can hold NA.

    * float
    * 'float32'
    * 'float64'
    * 'Float32'
    * 'Float64'
    * 'UInt8'
    * 'UInt16'
    * 'UInt32'
    * 'UInt64'
    * 'Int8'
    * 'Int16'
    * 'Int32'
    * 'Int64'
    * 'uint8[pyarrow]'
    * 'uint16[pyarrow]'
    * 'uint32[pyarrow]'
    * 'uint64[pyarrow]'
    * 'int8[pyarrow]'
    * 'int16[pyarrow]'
    * 'int32[pyarrow]'
    * 'int64[pyarrow]'
    * 'float[pyarrow]'
    * 'double[pyarrow]'
    """
    return request.param


@pytest.fixture(params=tm.ALL_NUMERIC_DTYPES)
def any_numeric_dtype(request):
    """
    Parameterized fixture for all numeric dtypes.

    * int
    * 'int8'
    * 'uint8'
    * 'int16'
    * 'uint16'
    * 'int32'
    * 'uint32'
    * 'int64'
    * 'uint64'
    * float
    * 'float32'
    * 'float64'
    * complex
    * 'complex64'
    * 'complex128'
    * 'UInt8'
    * 'Int8'
    * 'UInt16'
    * 'Int16'
    * 'UInt32'
    * 'Int32'
    * 'UInt64'
    * 'Int64'
    * 'Float32'
    * 'Float64'
    """
    return request.param


# categoricals are handled separately
_any_skipna_inferred_dtype = [
    ("string", ["a", np.nan, "c"]),
    ("string", ["a", pd.NA, "c"]),
    ("mixed", ["a", pd.NaT, "c"]),  # pd.NaT not considered valid by is_string_array
    ("bytes", [b"a", np.nan, b"c"]),
    ("empty", [np.nan, np.nan, np.nan]),
    ("empty", []),
    ("mixed-integer", ["a", np.nan, 2]),
    ("mixed", ["a", np.nan, 2.0]),
    ("floating", [1.0, np.nan, 2.0]),
    ("integer", [1, np.nan, 2]),
    ("mixed-integer-float", [1, np.nan, 2.0]),
    ("decimal", [Decimal(1), np.nan, Decimal(2)]),
    ("boolean", [True, np.nan, False]),
    ("boolean", [True, pd.NA, False]),
    ("datetime64", [np.datetime64("2013-01-01"), np.nan, np.datetime64("2018-01-01")]),
    ("datetime", [Timestamp("20130101"), np.nan, Timestamp("20180101")]),
    ("date", [date(2013, 1, 1), np.nan, date(2018, 1, 1)]),
    ("complex", [1 + 1j, np.nan, 2 + 2j]),
    # The following dtype is commented out due to GH 23554
    # ('timedelta64', [np.timedelta64(1, 'D'),
    #                  np.nan, np.timedelta64(2, 'D')]),
    ("timedelta", [timedelta(1), np.nan, timedelta(2)]),
    ("time", [time(1), np.nan, time(2)]),
    ("period", [Period(2013), pd.NaT, Period(2018)]),
    ("interval", [Interval(0, 1), np.nan, Interval(0, 2)]),
]
ids, _ = zip(*_any_skipna_inferred_dtype)  # use inferred type as fixture-id


@pytest.fixture(params=_any_skipna_inferred_dtype, ids=ids)
def any_skipna_inferred_dtype(request):
    """
    Fixture for all inferred dtypes from _libs.lib.infer_dtype

    The covered (inferred) types are:
    * 'string'
    * 'empty'
    * 'bytes'
    * 'mixed'
    * 'mixed-integer'
    * 'mixed-integer-float'
    * 'floating'
    * 'integer'
    * 'decimal'
    * 'boolean'
    * 'datetime64'
    * 'datetime'
    * 'date'
    * 'timedelta'
    * 'time'
    * 'period'
    * 'interval'

    Returns
    -------
    inferred_dtype : str
        The string for the inferred dtype from _libs.lib.infer_dtype
    values : np.ndarray
        An array of object dtype that will be inferred to have
        `inferred_dtype`

    Examples
    --------
    >>> from pandas._libs import lib
    >>>
    >>> def test_something(any_skipna_inferred_dtype):
    ...     inferred_dtype, values = any_skipna_inferred_dtype
    ...     # will pass
    ...     assert lib.infer_dtype(values, skipna=True) == inferred_dtype
    """
    inferred_dtype, values = request.param
    values = np.array(values, dtype=object)  # object dtype to avoid casting

    # correctness of inference tested in tests/dtypes/test_inference.py
    return inferred_dtype, values


# ----------------------------------------------------------------
# Misc
# ----------------------------------------------------------------
@pytest.fixture
def ip():
    """
    Get an instance of IPython.InteractiveShell.

    Will raise a skip if IPython is not installed.
    """
    pytest.importorskip("IPython", minversion="6.0.0")
    from IPython.core.interactiveshell import InteractiveShell

    # GH#35711 make sure sqlite history file handle is not leaked
    from traitlets.config import Config  # isort:skip

    c = Config()
    c.HistoryManager.hist_file = ":memory:"

    return InteractiveShell(config=c)


@pytest.fixture(params=["bsr", "coo", "csc", "csr", "dia", "dok", "lil"])
def spmatrix(request):
    """
    Yields scipy sparse matrix classes.
    """
    sparse = pytest.importorskip("scipy.sparse")

    return getattr(sparse, request.param + "_matrix")


@pytest.fixture(
    params=[
        getattr(pd.offsets, o)
        for o in pd.offsets.__all__
        if issubclass(getattr(pd.offsets, o), pd.offsets.Tick) and o != "Tick"
    ]
)
def tick_classes(request):
    """
    Fixture for Tick based datetime offsets available for a time series.
    """
    return request.param


@pytest.fixture(params=[None, lambda x: x])
def sort_by_key(request):
    """
    Simple fixture for testing keys in sorting methods.
    Tests None (no key) and the identity key.
    """
    return request.param


@pytest.fixture(
    params=[
        ("foo", None, None),
        ("Egon", "Venkman", None),
        ("NCC1701D", "NCC1701D", "NCC1701D"),
        # possibly-matching NAs
        (np.nan, np.nan, np.nan),
        (np.nan, pd.NaT, None),
        (np.nan, pd.NA, None),
        (pd.NA, pd.NA, pd.NA),
    ]
)
def names(request) -> tuple[Hashable, Hashable, Hashable]:
    """
    A 3-tuple of names, the first two for operands, the last for a result.
    """
    return request.param


@pytest.fixture(params=[tm.setitem, tm.loc, tm.iloc])
def indexer_sli(request):
    """
    Parametrize over __setitem__, loc.__setitem__, iloc.__setitem__
    """
    return request.param


@pytest.fixture(params=[tm.loc, tm.iloc])
def indexer_li(request):
    """
    Parametrize over loc.__getitem__, iloc.__getitem__
    """
    return request.param


@pytest.fixture(params=[tm.setitem, tm.iloc])
def indexer_si(request):
    """
    Parametrize over __setitem__, iloc.__setitem__
    """
    return request.param


@pytest.fixture(params=[tm.setitem, tm.loc])
def indexer_sl(request):
    """
    Parametrize over __setitem__, loc.__setitem__
    """
    return request.param


@pytest.fixture(params=[tm.at, tm.loc])
def indexer_al(request):
    """
    Parametrize over at.__setitem__, loc.__setitem__
    """
    return request.param


@pytest.fixture(params=[tm.iat, tm.iloc])
def indexer_ial(request):
    """
    Parametrize over iat.__setitem__, iloc.__setitem__
    """
    return request.param


@pytest.fixture
def using_array_manager() -> bool:
    """
    Fixture to check if the array manager is being used.
    """
    return _get_option("mode.data_manager", silent=True) == "array"


@pytest.fixture
def using_copy_on_write() -> bool:
    """
    Fixture to check if Copy-on-Write is enabled.
    """
    return (
        pd.options.mode.copy_on_write is True
        and _get_option("mode.data_manager", silent=True) == "block"
    )


@pytest.fixture
def warn_copy_on_write() -> bool:
    """
    Fixture to check if Copy-on-Write is in warning mode.
    """
    return (
        pd.options.mode.copy_on_write == "warn"
        and _get_option("mode.data_manager", silent=True) == "block"
    )


@pytest.fixture
def using_infer_string() -> bool:
    """
    Fixture to check if infer string option is enabled.
    """
    return pd.options.future.infer_string is True


warsaws = ["Europe/Warsaw", "dateutil/Europe/Warsaw"]
if zoneinfo is not None:
    warsaws.append(zoneinfo.ZoneInfo("Europe/Warsaw"))  # type: ignore[arg-type]


@pytest.fixture(params=warsaws)
def warsaw(request) -> str:
    """
    tzinfo for Europe/Warsaw using pytz, dateutil, or zoneinfo.
    """
    return request.param


@pytest.fixture()
def arrow_string_storage():
    return ("pyarrow", "pyarrow_numpy")
