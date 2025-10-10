from io import StringIO
from string import ascii_uppercase
import textwrap

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas.compat import (
    HAS_PYARROW,
    PYPY,
)

from pandas import (
    CategoricalIndex,
    Index,
    MultiIndex,
    Series,
    date_range,
)


def test_info_categorical_column_just_works():
    n = 2500
    data = np.array(list("abcdefghij")).take(
        np.random.default_rng(2).integers(0, 10, size=n, dtype=int)
    )
    s = Series(data).astype("category")
    s.isna()
    buf = StringIO()
    s.info(buf=buf)

    s2 = s[s == "d"]
    buf = StringIO()
    s2.info(buf=buf)


def test_info_categorical():
    # GH14298
    idx = CategoricalIndex(["a", "b"])
    s = Series(np.zeros(2), index=idx)
    buf = StringIO()
    s.info(buf=buf)


@pytest.mark.parametrize("verbose", [True, False])
def test_info_series(
    lexsorted_two_level_string_multiindex, verbose, using_infer_string
):
    index = lexsorted_two_level_string_multiindex
    ser = Series(range(len(index)), index=index, name="sth")
    buf = StringIO()
    ser.info(verbose=verbose, buf=buf)
    result = buf.getvalue()

    expected = textwrap.dedent(
        """\
        <class 'pandas.core.series.Series'>
        MultiIndex: 10 entries, ('foo', 'one') to ('qux', 'three')
        """
    )
    if verbose:
        expected += textwrap.dedent(
            """\
            Series name: sth
            Non-Null Count  Dtype
            --------------  -----
            10 non-null     int64
            """
        )
    qualifier = "" if using_infer_string and HAS_PYARROW else "+"
    expected += textwrap.dedent(
        f"""\
        dtypes: int64(1)
        memory usage: {ser.memory_usage()}.0{qualifier} bytes
        """
    )
    assert result == expected


def test_info_memory():
    s = Series([1, 2], dtype="i8")
    buf = StringIO()
    s.info(buf=buf)
    result = buf.getvalue()
    memory_bytes = float(s.memory_usage())
    expected = textwrap.dedent(
        f"""\
    <class 'pandas.core.series.Series'>
    RangeIndex: 2 entries, 0 to 1
    Series name: None
    Non-Null Count  Dtype
    --------------  -----
    2 non-null      int64
    dtypes: int64(1)
    memory usage: {memory_bytes} bytes
    """
    )
    assert result == expected


def test_info_wide():
    s = Series(np.random.default_rng(2).standard_normal(101))
    msg = "Argument `max_cols` can only be passed in DataFrame.info, not Series.info"
    with pytest.raises(ValueError, match=msg):
        s.info(max_cols=1)


def test_info_shows_dtypes():
    dtypes = [
        "int64",
        "float64",
        "datetime64[ns]",
        "timedelta64[ns]",
        "complex128",
        "object",
        "bool",
    ]
    n = 10
    for dtype in dtypes:
        s = Series(np.random.default_rng(2).integers(2, size=n).astype(dtype))
        buf = StringIO()
        s.info(buf=buf)
        res = buf.getvalue()
        name = f"{n:d} non-null     {dtype}"
        assert name in res


@pytest.mark.xfail(PYPY, reason="on PyPy deep=True doesn't change result")
def test_info_memory_usage_deep_not_pypy():
    s_with_object_index = Series({"a": [1]}, index=["foo"])
    assert s_with_object_index.memory_usage(
        index=True, deep=True
    ) > s_with_object_index.memory_usage(index=True)

    s_object = Series({"a": ["a"]})
    assert s_object.memory_usage(deep=True) > s_object.memory_usage()


@pytest.mark.xfail(not PYPY, reason="on PyPy deep=True does not change result")
def test_info_memory_usage_deep_pypy():
    s_with_object_index = Series({"a": [1]}, index=["foo"])
    assert s_with_object_index.memory_usage(
        index=True, deep=True
    ) == s_with_object_index.memory_usage(index=True)

    s_object = Series({"a": ["a"]})
    assert s_object.memory_usage(deep=True) == s_object.memory_usage()


@pytest.mark.parametrize(
    "index, plus",
    [
        ([1, 2, 3], False),
        (Index(list("ABC"), dtype="str"), not (using_string_dtype() and HAS_PYARROW)),
        (Index(list("ABC"), dtype=object), True),
        (MultiIndex.from_product([range(3), range(3)]), False),
        (
            MultiIndex.from_product([range(3), ["foo", "bar"]]),
            not (using_string_dtype() and HAS_PYARROW),
        ),
    ],
)
def test_info_memory_usage_qualified(index, plus):
    series = Series(1, index=index)
    buf = StringIO()
    series.info(buf=buf)
    if plus:
        assert "+" in buf.getvalue()
    else:
        assert "+" not in buf.getvalue()


def test_info_memory_usage_bug_on_multiindex():
    # GH 14308
    # memory usage introspection should not materialize .values
    N = 100
    M = len(ascii_uppercase)
    index = MultiIndex.from_product(
        [list(ascii_uppercase), date_range("20160101", periods=N)],
        names=["id", "date"],
    )
    s = Series(np.random.default_rng(2).standard_normal(N * M), index=index)

    unstacked = s.unstack("id")
    assert s.values.nbytes == unstacked.values.nbytes
    assert s.memory_usage(deep=True) > unstacked.memory_usage(deep=True).sum()

    # high upper bound
    diff = unstacked.memory_usage(deep=True).sum() - s.memory_usage(deep=True)
    assert diff < 2000
