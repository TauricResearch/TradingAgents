import numpy as np
import pytest

from pandas.compat import is_platform_arm
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    Index,
)
import pandas._testing as tm
from pandas.util.version import Version

pytestmark = [td.skip_if_no("numba"), pytest.mark.single_cpu, pytest.mark.skipif()]

numba = pytest.importorskip("numba")
pytestmark.append(
    pytest.mark.skipif(
        Version(numba.__version__) == Version("0.61") and is_platform_arm(),
        reason=f"Segfaults on ARM platforms with numba {numba.__version__}",
    )
)


@pytest.fixture(params=[0, 1])
def apply_axis(request):
    return request.param


def test_numba_vs_python_noop(float_frame, apply_axis):
    func = lambda x: x
    result = float_frame.apply(func, engine="numba", axis=apply_axis)
    expected = float_frame.apply(func, engine="python", axis=apply_axis)
    tm.assert_frame_equal(result, expected)


def test_numba_vs_python_string_index():
    # GH#56189
    df = DataFrame(
        1,
        index=Index(["a", "b"], dtype=pd.StringDtype(na_value=np.nan)),
        columns=Index(["x", "y"], dtype=pd.StringDtype(na_value=np.nan)),
    )
    func = lambda x: x
    result = df.apply(func, engine="numba", axis=0)
    expected = df.apply(func, engine="python", axis=0)
    tm.assert_frame_equal(
        result, expected, check_column_type=False, check_index_type=False
    )


def test_numba_vs_python_indexing():
    frame = DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": [7.0, 8.0, 9.0]},
        index=Index(["A", "B", "C"]),
    )
    row_func = lambda x: x["c"]
    result = frame.apply(row_func, engine="numba", axis=1)
    expected = frame.apply(row_func, engine="python", axis=1)
    tm.assert_series_equal(result, expected)

    col_func = lambda x: x["A"]
    result = frame.apply(col_func, engine="numba", axis=0)
    expected = frame.apply(col_func, engine="python", axis=0)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize(
    "reduction",
    [lambda x: x.mean(), lambda x: x.min(), lambda x: x.max(), lambda x: x.sum()],
)
def test_numba_vs_python_reductions(reduction, apply_axis):
    df = DataFrame(np.ones((4, 4), dtype=np.float64))
    result = df.apply(reduction, engine="numba", axis=apply_axis)
    expected = df.apply(reduction, engine="python", axis=apply_axis)
    tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("colnames", [[1, 2, 3], [1.0, 2.0, 3.0]])
def test_numba_numeric_colnames(colnames):
    # Check that numeric column names lower properly and can be indxed on
    df = DataFrame(
        np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.int64), columns=colnames
    )
    first_col = colnames[0]
    f = lambda x: x[first_col]  # Get the first column
    result = df.apply(f, engine="numba", axis=1)
    expected = df.apply(f, engine="python", axis=1)
    tm.assert_series_equal(result, expected)


def test_numba_parallel_unsupported(float_frame):
    f = lambda x: x
    with pytest.raises(
        NotImplementedError,
        match="Parallel apply is not supported when raw=False and engine='numba'",
    ):
        float_frame.apply(f, engine="numba", engine_kwargs={"parallel": True})


def test_numba_nonunique_unsupported(apply_axis):
    f = lambda x: x
    df = DataFrame({"a": [1, 2]}, index=Index(["a", "a"]))
    with pytest.raises(
        NotImplementedError,
        match="The index/columns must be unique when raw=False and engine='numba'",
    ):
        df.apply(f, engine="numba", axis=apply_axis)


def test_numba_unsupported_dtypes(apply_axis):
    pytest.importorskip("pyarrow")
    f = lambda x: x
    df = DataFrame({"a": [1, 2], "b": ["a", "b"], "c": [4, 5]})
    df["c"] = df["c"].astype("double[pyarrow]")

    with pytest.raises(
        ValueError,
        match="Column b must have a numeric dtype. Found 'object|str' instead",
    ):
        df.apply(f, engine="numba", axis=apply_axis)

    with pytest.raises(
        ValueError,
        match="Column c is backed by an extension array, "
        "which is not supported by the numba engine.",
    ):
        df["c"].to_frame().apply(f, engine="numba", axis=apply_axis)
