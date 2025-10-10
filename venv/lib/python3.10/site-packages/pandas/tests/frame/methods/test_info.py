from io import StringIO
import re
from string import ascii_uppercase
import sys
import textwrap

import numpy as np
import pytest

from pandas._config import using_string_dtype

from pandas.compat import (
    HAS_PYARROW,
    IS64,
    PYPY,
    is_platform_arm,
)

from pandas import (
    CategoricalIndex,
    DataFrame,
    Index,
    MultiIndex,
    Series,
    date_range,
    option_context,
)
import pandas._testing as tm
from pandas.util.version import Version


@pytest.fixture
def duplicate_columns_frame():
    """Dataframe with duplicate column names."""
    return DataFrame(
        np.random.default_rng(2).standard_normal((1500, 4)),
        columns=["a", "a", "b", "b"],
    )


def test_info_empty():
    # GH #45494
    df = DataFrame()
    buf = StringIO()
    df.info(buf=buf)
    result = buf.getvalue()
    expected = textwrap.dedent(
        """\
        <class 'pandas.core.frame.DataFrame'>
        RangeIndex: 0 entries
        Empty DataFrame\n"""
    )
    assert result == expected


def test_info_categorical_column_smoke_test():
    n = 2500
    df = DataFrame({"int64": np.random.default_rng(2).integers(100, size=n, dtype=int)})
    df["category"] = Series(
        np.array(list("abcdefghij")).take(
            np.random.default_rng(2).integers(0, 10, size=n, dtype=int)
        )
    ).astype("category")
    df.isna()
    buf = StringIO()
    df.info(buf=buf)

    df2 = df[df["category"] == "d"]
    buf = StringIO()
    df2.info(buf=buf)


@pytest.mark.parametrize(
    "fixture_func_name",
    [
        "int_frame",
        "float_frame",
        "datetime_frame",
        "duplicate_columns_frame",
        "float_string_frame",
    ],
)
def test_info_smoke_test(fixture_func_name, request):
    frame = request.getfixturevalue(fixture_func_name)
    buf = StringIO()
    frame.info(buf=buf)
    result = buf.getvalue().splitlines()
    assert len(result) > 10

    buf = StringIO()
    frame.info(buf=buf, verbose=False)


def test_info_smoke_test2(float_frame):
    # pretty useless test, used to be mixed into the repr tests
    buf = StringIO()
    float_frame.reindex(columns=["A"]).info(verbose=False, buf=buf)
    float_frame.reindex(columns=["A", "B"]).info(verbose=False, buf=buf)

    # no columns or index
    DataFrame().info(buf=buf)


@pytest.mark.parametrize(
    "num_columns, max_info_columns, verbose",
    [
        (10, 100, True),
        (10, 11, True),
        (10, 10, True),
        (10, 9, False),
        (10, 1, False),
    ],
)
def test_info_default_verbose_selection(num_columns, max_info_columns, verbose):
    frame = DataFrame(np.random.default_rng(2).standard_normal((5, num_columns)))
    with option_context("display.max_info_columns", max_info_columns):
        io_default = StringIO()
        frame.info(buf=io_default)
        result = io_default.getvalue()

        io_explicit = StringIO()
        frame.info(buf=io_explicit, verbose=verbose)
        expected = io_explicit.getvalue()

        assert result == expected


def test_info_verbose_check_header_separator_body():
    buf = StringIO()
    size = 1001
    start = 5
    frame = DataFrame(np.random.default_rng(2).standard_normal((3, size)))
    frame.info(verbose=True, buf=buf)

    res = buf.getvalue()
    header = " #     Column  Dtype  \n---    ------  -----  "
    assert header in res

    frame.info(verbose=True, buf=buf)
    buf.seek(0)
    lines = buf.readlines()
    assert len(lines) > 0

    for i, line in enumerate(lines):
        if start <= i < start + size:
            line_nr = f" {i - start} "
            assert line.startswith(line_nr)


@pytest.mark.parametrize(
    "size, header_exp, separator_exp, first_line_exp, last_line_exp",
    [
        (
            4,
            " #   Column  Non-Null Count  Dtype  ",
            "---  ------  --------------  -----  ",
            " 0   0       3 non-null      float64",
            " 3   3       3 non-null      float64",
        ),
        (
            11,
            " #   Column  Non-Null Count  Dtype  ",
            "---  ------  --------------  -----  ",
            " 0   0       3 non-null      float64",
            " 10  10      3 non-null      float64",
        ),
        (
            101,
            " #    Column  Non-Null Count  Dtype  ",
            "---   ------  --------------  -----  ",
            " 0    0       3 non-null      float64",
            " 100  100     3 non-null      float64",
        ),
        (
            1001,
            " #     Column  Non-Null Count  Dtype  ",
            "---    ------  --------------  -----  ",
            " 0     0       3 non-null      float64",
            " 1000  1000    3 non-null      float64",
        ),
        (
            10001,
            " #      Column  Non-Null Count  Dtype  ",
            "---     ------  --------------  -----  ",
            " 0      0       3 non-null      float64",
            " 10000  10000   3 non-null      float64",
        ),
    ],
)
def test_info_verbose_with_counts_spacing(
    size, header_exp, separator_exp, first_line_exp, last_line_exp
):
    """Test header column, spacer, first line and last line in verbose mode."""
    frame = DataFrame(np.random.default_rng(2).standard_normal((3, size)))
    with StringIO() as buf:
        frame.info(verbose=True, show_counts=True, buf=buf)
        all_lines = buf.getvalue().splitlines()
    # Here table would contain only header, separator and table lines
    # dframe repr, index summary, memory usage and dtypes are excluded
    table = all_lines[3:-2]
    header, separator, first_line, *rest, last_line = table
    assert header == header_exp
    assert separator == separator_exp
    assert first_line == first_line_exp
    assert last_line == last_line_exp


def test_info_memory():
    # https://github.com/pandas-dev/pandas/issues/21056
    df = DataFrame({"a": Series([1, 2], dtype="i8")})
    buf = StringIO()
    df.info(buf=buf)
    result = buf.getvalue()
    bytes = float(df.memory_usage().sum())
    expected = textwrap.dedent(
        f"""\
    <class 'pandas.core.frame.DataFrame'>
    RangeIndex: 2 entries, 0 to 1
    Data columns (total 1 columns):
     #   Column  Non-Null Count  Dtype
    ---  ------  --------------  -----
     0   a       2 non-null      int64
    dtypes: int64(1)
    memory usage: {bytes} bytes
    """
    )
    assert result == expected


def test_info_wide():
    io = StringIO()
    df = DataFrame(np.random.default_rng(2).standard_normal((5, 101)))
    df.info(buf=io)

    io = StringIO()
    df.info(buf=io, max_cols=101)
    result = io.getvalue()
    assert len(result.splitlines()) > 100

    expected = result
    with option_context("display.max_info_columns", 101):
        io = StringIO()
        df.info(buf=io)
        result = io.getvalue()
        assert result == expected


def test_info_duplicate_columns_shows_correct_dtypes():
    # GH11761
    io = StringIO()
    frame = DataFrame([[1, 2.0]], columns=["a", "a"])
    frame.info(buf=io)
    lines = io.getvalue().splitlines(True)
    assert " 0   a       1 non-null      int64  \n" == lines[5]
    assert " 1   a       1 non-null      float64\n" == lines[6]


def test_info_shows_column_dtypes():
    dtypes = [
        "int64",
        "float64",
        "datetime64[ns]",
        "timedelta64[ns]",
        "complex128",
        "object",
        "bool",
    ]
    data = {}
    n = 10
    for i, dtype in enumerate(dtypes):
        data[i] = np.random.default_rng(2).integers(2, size=n).astype(dtype)
    df = DataFrame(data)
    buf = StringIO()
    df.info(buf=buf)
    res = buf.getvalue()
    header = (
        " #   Column  Non-Null Count  Dtype          \n"
        "---  ------  --------------  -----          "
    )
    assert header in res
    for i, dtype in enumerate(dtypes):
        name = f" {i:d}   {i:d}       {n:d} non-null     {dtype}"
        assert name in res


def test_info_max_cols():
    df = DataFrame(np.random.default_rng(2).standard_normal((10, 5)))
    for len_, verbose in [(5, None), (5, False), (12, True)]:
        # For verbose always      ^ setting  ^ summarize ^ full output
        with option_context("max_info_columns", 4):
            buf = StringIO()
            df.info(buf=buf, verbose=verbose)
            res = buf.getvalue()
            assert len(res.strip().split("\n")) == len_

    for len_, verbose in [(12, None), (5, False), (12, True)]:
        # max_cols not exceeded
        with option_context("max_info_columns", 5):
            buf = StringIO()
            df.info(buf=buf, verbose=verbose)
            res = buf.getvalue()
            assert len(res.strip().split("\n")) == len_

    for len_, max_cols in [(12, 5), (5, 4)]:
        # setting truncates
        with option_context("max_info_columns", 4):
            buf = StringIO()
            df.info(buf=buf, max_cols=max_cols)
            res = buf.getvalue()
            assert len(res.strip().split("\n")) == len_

        # setting wouldn't truncate
        with option_context("max_info_columns", 5):
            buf = StringIO()
            df.info(buf=buf, max_cols=max_cols)
            res = buf.getvalue()
            assert len(res.strip().split("\n")) == len_


def test_info_memory_usage():
    # Ensure memory usage is displayed, when asserted, on the last line
    dtypes = [
        "int64",
        "float64",
        "datetime64[ns]",
        "timedelta64[ns]",
        "complex128",
        "object",
        "bool",
    ]
    data = {}
    n = 10
    for i, dtype in enumerate(dtypes):
        data[i] = np.random.default_rng(2).integers(2, size=n).astype(dtype)
    df = DataFrame(data)
    buf = StringIO()

    # display memory usage case
    df.info(buf=buf, memory_usage=True)
    res = buf.getvalue().splitlines()
    assert "memory usage: " in res[-1]

    # do not display memory usage case
    df.info(buf=buf, memory_usage=False)
    res = buf.getvalue().splitlines()
    assert "memory usage: " not in res[-1]

    df.info(buf=buf, memory_usage=True)
    res = buf.getvalue().splitlines()

    # memory usage is a lower bound, so print it as XYZ+ MB
    assert re.match(r"memory usage: [^+]+\+", res[-1])

    df.iloc[:, :5].info(buf=buf, memory_usage=True)
    res = buf.getvalue().splitlines()

    # excluded column with object dtype, so estimate is accurate
    assert not re.match(r"memory usage: [^+]+\+", res[-1])

    # Test a DataFrame with duplicate columns
    dtypes = ["int64", "int64", "int64", "float64"]
    data = {}
    n = 100
    for i, dtype in enumerate(dtypes):
        data[i] = np.random.default_rng(2).integers(2, size=n).astype(dtype)
    df = DataFrame(data)
    df.columns = dtypes

    df_with_object_index = DataFrame({"a": [1]}, index=Index(["foo"], dtype=object))
    df_with_object_index.info(buf=buf, memory_usage=True)
    res = buf.getvalue().splitlines()
    assert re.match(r"memory usage: [^+]+\+", res[-1])

    df_with_object_index.info(buf=buf, memory_usage="deep")
    res = buf.getvalue().splitlines()
    assert re.match(r"memory usage: [^+]+$", res[-1])

    # Ensure df size is as expected
    # (cols * rows * bytes) + index size
    df_size = df.memory_usage().sum()
    exp_size = len(dtypes) * n * 8 + df.index.nbytes
    assert df_size == exp_size

    # Ensure number of cols in memory_usage is the same as df
    size_df = np.size(df.columns.values) + 1  # index=True; default
    assert size_df == np.size(df.memory_usage())

    # assert deep works only on object
    assert df.memory_usage().sum() == df.memory_usage(deep=True).sum()

    # test for validity
    DataFrame(1, index=["a"], columns=["A"]).memory_usage(index=True)
    DataFrame(1, index=["a"], columns=["A"]).index.nbytes
    df = DataFrame(
        data=1, index=MultiIndex.from_product([["a"], range(1000)]), columns=["A"]
    )
    df.index.nbytes
    df.memory_usage(index=True)
    df.index.values.nbytes

    mem = df.memory_usage(deep=True).sum()
    assert mem > 0


@pytest.mark.skipif(PYPY, reason="on PyPy deep=True doesn't change result")
def test_info_memory_usage_deep_not_pypy():
    df_with_object_index = DataFrame({"a": [1]}, index=Index(["foo"], dtype=object))
    assert (
        df_with_object_index.memory_usage(index=True, deep=True).sum()
        > df_with_object_index.memory_usage(index=True).sum()
    )

    df_object = DataFrame({"a": Series(["a"], dtype=object)})
    assert df_object.memory_usage(deep=True).sum() > df_object.memory_usage().sum()


@pytest.mark.xfail(not PYPY, reason="on PyPy deep=True does not change result")
def test_info_memory_usage_deep_pypy():
    df_with_object_index = DataFrame({"a": [1]}, index=Index(["foo"], dtype=object))
    assert (
        df_with_object_index.memory_usage(index=True, deep=True).sum()
        == df_with_object_index.memory_usage(index=True).sum()
    )

    df_object = DataFrame({"a": Series(["a"], dtype=object)})
    assert df_object.memory_usage(deep=True).sum() == df_object.memory_usage().sum()


@pytest.mark.skipif(PYPY, reason="PyPy getsizeof() fails by design")
def test_usage_via_getsizeof():
    df = DataFrame(
        data=1, index=MultiIndex.from_product([["a"], range(1000)]), columns=["A"]
    )
    mem = df.memory_usage(deep=True).sum()
    # sys.getsizeof will call the .memory_usage with
    # deep=True, and add on some GC overhead
    diff = mem - sys.getsizeof(df)
    assert abs(diff) < 100


def test_info_memory_usage_qualified(using_infer_string):
    buf = StringIO()
    df = DataFrame(1, columns=list("ab"), index=[1, 2, 3])
    df.info(buf=buf)
    assert "+" not in buf.getvalue()

    buf = StringIO()
    df = DataFrame(1, columns=list("ab"), index=Index(list("ABC"), dtype=object))
    df.info(buf=buf)
    assert "+" in buf.getvalue()

    buf = StringIO()
    df = DataFrame(1, columns=list("ab"), index=Index(list("ABC"), dtype="str"))
    df.info(buf=buf)
    if using_infer_string and HAS_PYARROW:
        assert "+" not in buf.getvalue()
    else:
        assert "+" in buf.getvalue()

    buf = StringIO()
    df = DataFrame(
        1, columns=list("ab"), index=MultiIndex.from_product([range(3), range(3)])
    )
    df.info(buf=buf)
    assert "+" not in buf.getvalue()

    buf = StringIO()
    df = DataFrame(
        1, columns=list("ab"), index=MultiIndex.from_product([range(3), ["foo", "bar"]])
    )
    df.info(buf=buf)
    if using_infer_string and HAS_PYARROW:
        assert "+" not in buf.getvalue()
    else:
        assert "+" in buf.getvalue()


def test_info_memory_usage_bug_on_multiindex():
    # GH 14308
    # memory usage introspection should not materialize .values

    def memory_usage(f):
        return f.memory_usage(deep=True).sum()

    N = 100
    M = len(ascii_uppercase)
    index = MultiIndex.from_product(
        [list(ascii_uppercase), date_range("20160101", periods=N)],
        names=["id", "date"],
    )
    df = DataFrame(
        {"value": np.random.default_rng(2).standard_normal(N * M)}, index=index
    )

    unstacked = df.unstack("id")
    assert df.values.nbytes == unstacked.values.nbytes
    assert memory_usage(df) > memory_usage(unstacked)

    # high upper bound
    assert memory_usage(unstacked) - memory_usage(df) < 2000


def test_info_categorical():
    # GH14298
    idx = CategoricalIndex(["a", "b"])
    df = DataFrame(np.zeros((2, 2)), index=idx, columns=idx)

    buf = StringIO()
    df.info(buf=buf)


@pytest.mark.xfail(not IS64, reason="GH 36579: fail on 32-bit system")
def test_info_int_columns(using_infer_string):
    # GH#37245
    df = DataFrame({1: [1, 2], 2: [2, 3]}, index=["A", "B"])
    buf = StringIO()
    df.info(show_counts=True, buf=buf)
    result = buf.getvalue()
    expected = textwrap.dedent(
        f"""\
        <class 'pandas.core.frame.DataFrame'>
        Index: 2 entries, A to B
        Data columns (total 2 columns):
         #   Column  Non-Null Count  Dtype
        ---  ------  --------------  -----
         0   1       2 non-null      int64
         1   2       2 non-null      int64
        dtypes: int64(2)
        memory usage: {'50.0' if using_infer_string and HAS_PYARROW else '48.0+'} bytes
        """
    )
    assert result == expected


@pytest.mark.xfail(using_string_dtype(), reason="TODO(infer_string)")
def test_memory_usage_empty_no_warning(using_infer_string):
    # GH#50066
    df = DataFrame(index=["a", "b"])
    with tm.assert_produces_warning(None):
        result = df.memory_usage()
    if using_infer_string and HAS_PYARROW:
        value = 18
    else:
        value = 16 if IS64 else 8
    expected = Series(value, index=["Index"])
    tm.assert_series_equal(result, expected)


@pytest.mark.single_cpu
def test_info_compute_numba():
    # GH#51922
    numba = pytest.importorskip("numba")
    if Version(numba.__version__) == Version("0.61") and is_platform_arm():
        pytest.skip(f"Segfaults on ARM platforms with numba {numba.__version__}")
    df = DataFrame([[1, 2], [3, 4]])

    with option_context("compute.use_numba", True):
        buf = StringIO()
        df.info(buf=buf)
        result = buf.getvalue()

    buf = StringIO()
    df.info(buf=buf)
    expected = buf.getvalue()
    assert result == expected


@pytest.mark.parametrize(
    "row, columns, show_counts, result",
    [
        [20, 20, None, True],
        [20, 20, True, True],
        [20, 20, False, False],
        [5, 5, None, False],
        [5, 5, True, False],
        [5, 5, False, False],
    ],
)
def test_info_show_counts(row, columns, show_counts, result):
    # Explicit cast to float to avoid implicit cast when setting nan
    df = DataFrame(1, columns=range(10), index=range(10)).astype({1: "float"})
    df.iloc[1, 1] = np.nan

    with option_context(
        "display.max_info_rows", row, "display.max_info_columns", columns
    ):
        with StringIO() as buf:
            df.info(buf=buf, show_counts=show_counts)
            assert ("non-null" in buf.getvalue()) is result
