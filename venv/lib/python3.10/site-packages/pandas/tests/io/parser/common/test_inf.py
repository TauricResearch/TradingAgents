"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from io import StringIO

import numpy as np
import pytest

from pandas import (
    DataFrame,
    option_context,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")


@xfail_pyarrow  # AssertionError: DataFrame.index are different
@pytest.mark.parametrize("na_filter", [True, False])
def test_inf_parsing(all_parsers, na_filter):
    parser = all_parsers
    data = """\
,A
a,inf
b,-inf
c,+Inf
d,-Inf
e,INF
f,-INF
g,+INf
h,-INf
i,inF
j,-inF"""
    expected = DataFrame(
        {"A": [float("inf"), float("-inf")] * 5},
        index=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
    )
    result = parser.read_csv(StringIO(data), index_col=0, na_filter=na_filter)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # AssertionError: DataFrame.index are different
@pytest.mark.parametrize("na_filter", [True, False])
def test_infinity_parsing(all_parsers, na_filter):
    parser = all_parsers
    data = """\
,A
a,Infinity
b,-Infinity
c,+Infinity
"""
    expected = DataFrame(
        {"A": [float("infinity"), float("-infinity"), float("+infinity")]},
        index=["a", "b", "c"],
    )
    result = parser.read_csv(StringIO(data), index_col=0, na_filter=na_filter)
    tm.assert_frame_equal(result, expected)


def test_read_csv_with_use_inf_as_na(all_parsers):
    # https://github.com/pandas-dev/pandas/issues/35493
    parser = all_parsers
    data = "1.0\nNaN\n3.0"
    msg = "use_inf_as_na option is deprecated"
    warn = FutureWarning
    if parser.engine == "pyarrow":
        warn = (FutureWarning, DeprecationWarning)

    with tm.assert_produces_warning(warn, match=msg, check_stacklevel=False):
        with option_context("use_inf_as_na", True):
            result = parser.read_csv(StringIO(data), header=None)
    expected = DataFrame([1.0, np.nan, 3.0])
    tm.assert_frame_equal(result, expected)
