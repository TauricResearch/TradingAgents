import numpy as np
import pytest

from pandas.compat import HAS_PYARROW

from pandas.core.dtypes.cast import find_common_type

import pandas as pd
import pandas._testing as tm
from pandas.util.version import Version


@pytest.mark.parametrize(
    "to_concat_dtypes, result_dtype",
    [
        # same types
        ([("pyarrow", pd.NA), ("pyarrow", pd.NA)], ("pyarrow", pd.NA)),
        ([("pyarrow", np.nan), ("pyarrow", np.nan)], ("pyarrow", np.nan)),
        ([("python", pd.NA), ("python", pd.NA)], ("python", pd.NA)),
        ([("python", np.nan), ("python", np.nan)], ("python", np.nan)),
        # pyarrow preference
        ([("pyarrow", pd.NA), ("python", pd.NA)], ("pyarrow", pd.NA)),
        # NA preference
        ([("python", pd.NA), ("python", np.nan)], ("python", pd.NA)),
    ],
)
def test_concat_series(request, to_concat_dtypes, result_dtype):
    if any(storage == "pyarrow" for storage, _ in to_concat_dtypes) and not HAS_PYARROW:
        pytest.skip("Could not import 'pyarrow'")

    ser_list = [
        pd.Series(["a", "b", None], dtype=pd.StringDtype(storage, na_value))
        for storage, na_value in to_concat_dtypes
    ]

    result = pd.concat(ser_list, ignore_index=True)
    expected = pd.Series(
        ["a", "b", None, "a", "b", None], dtype=pd.StringDtype(*result_dtype)
    )
    tm.assert_series_equal(result, expected)

    # order doesn't matter for result
    result = pd.concat(ser_list[::1], ignore_index=True)
    tm.assert_series_equal(result, expected)


def test_concat_with_object(string_dtype_arguments):
    # _get_common_dtype cannot inspect values, so object dtype with strings still
    # results in object dtype
    result = pd.concat(
        [
            pd.Series(["a", "b", None], dtype=pd.StringDtype(*string_dtype_arguments)),
            pd.Series(["a", "b", None], dtype=object),
        ]
    )
    assert result.dtype == np.dtype("object")


def test_concat_with_numpy(string_dtype_arguments):
    # common type with a numpy string dtype always preserves the pandas string dtype
    dtype = pd.StringDtype(*string_dtype_arguments)
    assert find_common_type([dtype, np.dtype("U")]) == dtype
    assert find_common_type([np.dtype("U"), dtype]) == dtype
    assert find_common_type([dtype, np.dtype("U10")]) == dtype
    assert find_common_type([np.dtype("U10"), dtype]) == dtype

    # with any other numpy dtype -> object
    assert find_common_type([dtype, np.dtype("S")]) == np.dtype("object")
    assert find_common_type([dtype, np.dtype("int64")]) == np.dtype("object")

    if Version(np.__version__) >= Version("2"):
        assert find_common_type([dtype, np.dtypes.StringDType()]) == dtype
        assert find_common_type([np.dtypes.StringDType(), dtype]) == dtype
