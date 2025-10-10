"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from io import StringIO

import numpy as np
import pytest

from pandas.compat import is_platform_linux

from pandas import DataFrame
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)
xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


@skip_pyarrow  # ParserError: CSV parse error: Empty CSV file or block
def test_float_parser(all_parsers):
    # see gh-9565
    parser = all_parsers
    data = "45e-1,4.5,45.,inf,-inf"
    result = parser.read_csv(StringIO(data), header=None)

    expected = DataFrame([[float(s) for s in data.split(",")]])
    tm.assert_frame_equal(result, expected)


def test_scientific_no_exponent(all_parsers_all_precisions):
    # see gh-12215
    df = DataFrame.from_dict({"w": ["2e"], "x": ["3E"], "y": ["42e"], "z": ["632E"]})
    data = df.to_csv(index=False)
    parser, precision = all_parsers_all_precisions

    df_roundtrip = parser.read_csv(StringIO(data), float_precision=precision)
    tm.assert_frame_equal(df_roundtrip, df)


@pytest.mark.parametrize(
    "neg_exp",
    [
        -617,
        -100000,
        pytest.param(-99999999999999999, marks=pytest.mark.skip_ubsan),
    ],
)
def test_very_negative_exponent(all_parsers_all_precisions, neg_exp):
    # GH#38753
    parser, precision = all_parsers_all_precisions

    data = f"data\n10E{neg_exp}"
    result = parser.read_csv(StringIO(data), float_precision=precision)
    expected = DataFrame({"data": [0.0]})
    tm.assert_frame_equal(result, expected)


@pytest.mark.skip_ubsan
@xfail_pyarrow  # AssertionError: Attributes of DataFrame.iloc[:, 0] are different
@pytest.mark.parametrize("exp", [999999999999999999, -999999999999999999])
def test_too_many_exponent_digits(all_parsers_all_precisions, exp, request):
    # GH#38753
    parser, precision = all_parsers_all_precisions
    data = f"data\n10E{exp}"
    result = parser.read_csv(StringIO(data), float_precision=precision)
    if precision == "round_trip":
        if exp == 999999999999999999 and is_platform_linux():
            mark = pytest.mark.xfail(reason="GH38794, on Linux gives object result")
            request.applymarker(mark)

        value = np.inf if exp > 0 else 0.0
        expected = DataFrame({"data": [value]})
    else:
        expected = DataFrame({"data": [f"10E{exp}"]})

    tm.assert_frame_equal(result, expected)
