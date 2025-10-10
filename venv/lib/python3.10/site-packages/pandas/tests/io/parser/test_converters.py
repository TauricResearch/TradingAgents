"""
Tests column conversion functionality during parsing
for all of the parsers defined in parsers.py
"""
from io import StringIO

from dateutil.parser import parse
import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
)
import pandas._testing as tm


def test_converters_type_must_be_dict(all_parsers):
    parser = all_parsers
    data = """index,A,B,C,D
foo,2,3,4,5
"""
    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), converters=0)
        return
    with pytest.raises(TypeError, match="Type converters.+"):
        parser.read_csv(StringIO(data), converters=0)


@pytest.mark.parametrize("column", [3, "D"])
@pytest.mark.parametrize(
    "converter", [parse, lambda x: int(x.split("/")[2])]  # Produce integer.
)
def test_converters(all_parsers, column, converter):
    parser = all_parsers
    data = """A,B,C,D
a,1,2,01/01/2009
b,3,4,01/02/2009
c,4,5,01/03/2009
"""
    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), converters={column: converter})
        return

    result = parser.read_csv(StringIO(data), converters={column: converter})

    expected = parser.read_csv(StringIO(data))
    expected["D"] = expected["D"].map(converter)

    tm.assert_frame_equal(result, expected)


def test_converters_no_implicit_conv(all_parsers):
    # see gh-2184
    parser = all_parsers
    data = """000102,1.2,A\n001245,2,B"""

    converters = {0: lambda x: x.strip()}

    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), header=None, converters=converters)
        return

    result = parser.read_csv(StringIO(data), header=None, converters=converters)

    # Column 0 should not be casted to numeric and should remain as object.
    expected = DataFrame([["000102", 1.2, "A"], ["001245", 2, "B"]])
    tm.assert_frame_equal(result, expected)


def test_converters_euro_decimal_format(all_parsers):
    # see gh-583
    converters = {}
    parser = all_parsers

    data = """Id;Number1;Number2;Text1;Text2;Number3
1;1521,1541;187101,9543;ABC;poi;4,7387
2;121,12;14897,76;DEF;uyt;0,3773
3;878,158;108013,434;GHI;rez;2,7356"""
    converters["Number1"] = converters["Number2"] = converters[
        "Number3"
    ] = lambda x: float(x.replace(",", "."))

    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), sep=";", converters=converters)
        return

    result = parser.read_csv(StringIO(data), sep=";", converters=converters)
    expected = DataFrame(
        [
            [1, 1521.1541, 187101.9543, "ABC", "poi", 4.7387],
            [2, 121.12, 14897.76, "DEF", "uyt", 0.3773],
            [3, 878.158, 108013.434, "GHI", "rez", 2.7356],
        ],
        columns=["Id", "Number1", "Number2", "Text1", "Text2", "Number3"],
    )
    tm.assert_frame_equal(result, expected)


def test_converters_corner_with_nans(all_parsers):
    parser = all_parsers
    data = """id,score,days
1,2,12
2,2-5,
3,,14+
4,6-12,2"""

    # Example converters.
    def convert_days(x):
        x = x.strip()

        if not x:
            return np.nan

        is_plus = x.endswith("+")

        if is_plus:
            x = int(x[:-1]) + 1
        else:
            x = int(x)

        return x

    def convert_days_sentinel(x):
        x = x.strip()

        if not x:
            return np.nan

        is_plus = x.endswith("+")

        if is_plus:
            x = int(x[:-1]) + 1
        else:
            x = int(x)

        return x

    def convert_score(x):
        x = x.strip()

        if not x:
            return np.nan

        if x.find("-") > 0:
            val_min, val_max = map(int, x.split("-"))
            val = 0.5 * (val_min + val_max)
        else:
            val = float(x)

        return val

    results = []

    for day_converter in [convert_days, convert_days_sentinel]:
        if parser.engine == "pyarrow":
            msg = "The 'converters' option is not supported with the 'pyarrow' engine"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(
                    StringIO(data),
                    converters={"score": convert_score, "days": day_converter},
                    na_values=["", None],
                )
            continue

        result = parser.read_csv(
            StringIO(data),
            converters={"score": convert_score, "days": day_converter},
            na_values=["", None],
        )
        assert pd.isna(result["days"][1])
        results.append(result)

    if parser.engine != "pyarrow":
        tm.assert_frame_equal(results[0], results[1])


@pytest.mark.parametrize("conv_f", [lambda x: x, str])
def test_converter_index_col_bug(all_parsers, conv_f):
    # see gh-1835 , GH#40589
    parser = all_parsers
    data = "A;B\n1;2\n3;4"

    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(data), sep=";", index_col="A", converters={"A": conv_f}
            )
        return

    rs = parser.read_csv(
        StringIO(data), sep=";", index_col="A", converters={"A": conv_f}
    )

    xp = DataFrame({"B": [2, 4]}, index=Index(["1", "3"], name="A"))
    tm.assert_frame_equal(rs, xp)


def test_converter_identity_object(all_parsers):
    # GH#40589
    parser = all_parsers
    data = "A,B\n1,2\n3,4"

    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), converters={"A": lambda x: x})
        return

    rs = parser.read_csv(StringIO(data), converters={"A": lambda x: x})

    xp = DataFrame({"A": ["1", "3"], "B": [2, 4]})
    tm.assert_frame_equal(rs, xp)


def test_converter_multi_index(all_parsers):
    # GH 42446
    parser = all_parsers
    data = "A,B,B\nX,Y,Z\n1,2,3"

    if parser.engine == "pyarrow":
        msg = "The 'converters' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(data),
                header=list(range(2)),
                converters={
                    ("A", "X"): np.int32,
                    ("B", "Y"): np.int32,
                    ("B", "Z"): np.float32,
                },
            )
        return

    result = parser.read_csv(
        StringIO(data),
        header=list(range(2)),
        converters={
            ("A", "X"): np.int32,
            ("B", "Y"): np.int32,
            ("B", "Z"): np.float32,
        },
    )

    expected = DataFrame(
        {
            ("A", "X"): np.int32([1]),
            ("B", "Y"): np.int32([2]),
            ("B", "Z"): np.float32([3]),
        }
    )

    tm.assert_frame_equal(result, expected)
