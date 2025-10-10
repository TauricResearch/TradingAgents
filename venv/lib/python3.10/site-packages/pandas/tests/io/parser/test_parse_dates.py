"""
Tests date parsing functionality for all of the
parsers defined in parsers.py
"""

from datetime import (
    date,
    datetime,
    timedelta,
    timezone,
)
from io import StringIO

from dateutil.parser import parse as du_parse
import numpy as np
import pytest
import pytz

from pandas._libs.tslibs import parsing

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Index,
    MultiIndex,
    Series,
    Timestamp,
)
import pandas._testing as tm
from pandas.core.indexes.datetimes import date_range
from pandas.core.tools.datetimes import start_caching_at

from pandas.io.parsers import read_csv

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


@xfail_pyarrow
def test_read_csv_with_custom_date_parser(all_parsers):
    # GH36111
    def __custom_date_parser(time):
        time = time.astype(np.float64)
        time = time.astype(int)  # convert float seconds to int type
        return pd.to_timedelta(time, unit="s")

    testdata = StringIO(
        """time e n h
        41047.00 -98573.7297 871458.0640 389.0089
        41048.00 -98573.7299 871458.0640 389.0089
        41049.00 -98573.7300 871458.0642 389.0088
        41050.00 -98573.7299 871458.0643 389.0088
        41051.00 -98573.7302 871458.0640 389.0086
        """
    )
    result = all_parsers.read_csv_check_warnings(
        FutureWarning,
        "Please use 'date_format' instead",
        testdata,
        delim_whitespace=True,
        parse_dates=True,
        date_parser=__custom_date_parser,
        index_col="time",
    )
    time = [41047, 41048, 41049, 41050, 41051]
    time = pd.TimedeltaIndex([pd.to_timedelta(i, unit="s") for i in time], name="time")
    expected = DataFrame(
        {
            "e": [-98573.7297, -98573.7299, -98573.7300, -98573.7299, -98573.7302],
            "n": [871458.0640, 871458.0640, 871458.0642, 871458.0643, 871458.0640],
            "h": [389.0089, 389.0089, 389.0088, 389.0088, 389.0086],
        },
        index=time,
    )

    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_read_csv_with_custom_date_parser_parse_dates_false(all_parsers):
    # GH44366
    def __custom_date_parser(time):
        time = time.astype(np.float64)
        time = time.astype(int)  # convert float seconds to int type
        return pd.to_timedelta(time, unit="s")

    testdata = StringIO(
        """time e
        41047.00 -93.77
        41048.00 -95.79
        41049.00 -98.73
        41050.00 -93.99
        41051.00 -97.72
        """
    )
    result = all_parsers.read_csv_check_warnings(
        FutureWarning,
        "Please use 'date_format' instead",
        testdata,
        delim_whitespace=True,
        parse_dates=False,
        date_parser=__custom_date_parser,
        index_col="time",
    )
    time = Series([41047.00, 41048.00, 41049.00, 41050.00, 41051.00], name="time")
    expected = DataFrame(
        {"e": [-93.77, -95.79, -98.73, -93.99, -97.72]},
        index=time,
    )

    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_separator_date_conflict(all_parsers):
    # Regression test for gh-4678
    #
    # Make sure thousands separator and
    # date parsing do not conflict.
    parser = all_parsers
    data = "06-02-2013;13:00;1-000.215"
    expected = DataFrame(
        [[datetime(2013, 6, 2, 13, 0, 0), 1000.215]], columns=["Date", 2]
    )

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        df = parser.read_csv(
            StringIO(data),
            sep=";",
            thousands="-",
            parse_dates={"Date": [0, 1]},
            header=None,
        )
    tm.assert_frame_equal(df, expected)


@pytest.mark.parametrize("keep_date_col", [True, False])
def test_multiple_date_col_custom(all_parsers, keep_date_col, request):
    data = """\
KORD,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000
"""
    parser = all_parsers

    if keep_date_col and parser.engine == "pyarrow":
        # For this to pass, we need to disable auto-inference on the date columns
        # in parse_dates. We have no way of doing this though
        mark = pytest.mark.xfail(
            reason="pyarrow doesn't support disabling auto-inference on column numbers."
        )
        request.applymarker(mark)

    def date_parser(*date_cols):
        """
        Test date parser.

        Parameters
        ----------
        date_cols : args
            The list of data columns to parse.

        Returns
        -------
        parsed : Series
        """
        return parsing.try_parse_dates(
            parsing.concat_date_cols(date_cols), parser=du_parse
        )

    kwds = {
        "header": None,
        "date_parser": date_parser,
        "parse_dates": {"actual": [1, 2], "nominal": [1, 3]},
        "keep_date_col": keep_date_col,
        "names": ["X0", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8"],
    }
    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        **kwds,
        raise_on_extra_warnings=False,
    )

    expected = DataFrame(
        [
            [
                datetime(1999, 1, 27, 19, 0),
                datetime(1999, 1, 27, 18, 56),
                "KORD",
                "19990127",
                " 19:00:00",
                " 18:56:00",
                0.81,
                2.81,
                7.2,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 20, 0),
                datetime(1999, 1, 27, 19, 56),
                "KORD",
                "19990127",
                " 20:00:00",
                " 19:56:00",
                0.01,
                2.21,
                7.2,
                0.0,
                260.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                datetime(1999, 1, 27, 20, 56),
                "KORD",
                "19990127",
                " 21:00:00",
                " 20:56:00",
                -0.59,
                2.21,
                5.7,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                datetime(1999, 1, 27, 21, 18),
                "KORD",
                "19990127",
                " 21:00:00",
                " 21:18:00",
                -0.99,
                2.01,
                3.6,
                0.0,
                270.0,
            ],
            [
                datetime(1999, 1, 27, 22, 0),
                datetime(1999, 1, 27, 21, 56),
                "KORD",
                "19990127",
                " 22:00:00",
                " 21:56:00",
                -0.59,
                1.71,
                5.1,
                0.0,
                290.0,
            ],
            [
                datetime(1999, 1, 27, 23, 0),
                datetime(1999, 1, 27, 22, 56),
                "KORD",
                "19990127",
                " 23:00:00",
                " 22:56:00",
                -0.59,
                1.71,
                4.6,
                0.0,
                280.0,
            ],
        ],
        columns=[
            "actual",
            "nominal",
            "X0",
            "X1",
            "X2",
            "X3",
            "X4",
            "X5",
            "X6",
            "X7",
            "X8",
        ],
    )

    if not keep_date_col:
        expected = expected.drop(["X1", "X2", "X3"], axis=1)

    # Python can sometimes be flaky about how
    # the aggregated columns are entered, so
    # this standardizes the order.
    result = result[expected.columns]
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("container", [list, tuple, Index, Series])
@pytest.mark.parametrize("dim", [1, 2])
def test_concat_date_col_fail(container, dim):
    msg = "not all elements from date_cols are numpy arrays"
    value = "19990127"

    date_cols = tuple(container([value]) for _ in range(dim))

    with pytest.raises(ValueError, match=msg):
        parsing.concat_date_cols(date_cols)


@pytest.mark.parametrize("keep_date_col", [True, False])
def test_multiple_date_col(all_parsers, keep_date_col, request):
    data = """\
KORD,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000
"""
    parser = all_parsers

    if keep_date_col and parser.engine == "pyarrow":
        # For this to pass, we need to disable auto-inference on the date columns
        # in parse_dates. We have no way of doing this though
        mark = pytest.mark.xfail(
            reason="pyarrow doesn't support disabling auto-inference on column numbers."
        )
        request.applymarker(mark)

    depr_msg = "The 'keep_date_col' keyword in pd.read_csv is deprecated"

    kwds = {
        "header": None,
        "parse_dates": [[1, 2], [1, 3]],
        "keep_date_col": keep_date_col,
        "names": ["X0", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8"],
    }
    with tm.assert_produces_warning(
        (DeprecationWarning, FutureWarning), match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(StringIO(data), **kwds)

    expected = DataFrame(
        [
            [
                datetime(1999, 1, 27, 19, 0),
                datetime(1999, 1, 27, 18, 56),
                "KORD",
                "19990127",
                " 19:00:00",
                " 18:56:00",
                0.81,
                2.81,
                7.2,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 20, 0),
                datetime(1999, 1, 27, 19, 56),
                "KORD",
                "19990127",
                " 20:00:00",
                " 19:56:00",
                0.01,
                2.21,
                7.2,
                0.0,
                260.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                datetime(1999, 1, 27, 20, 56),
                "KORD",
                "19990127",
                " 21:00:00",
                " 20:56:00",
                -0.59,
                2.21,
                5.7,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                datetime(1999, 1, 27, 21, 18),
                "KORD",
                "19990127",
                " 21:00:00",
                " 21:18:00",
                -0.99,
                2.01,
                3.6,
                0.0,
                270.0,
            ],
            [
                datetime(1999, 1, 27, 22, 0),
                datetime(1999, 1, 27, 21, 56),
                "KORD",
                "19990127",
                " 22:00:00",
                " 21:56:00",
                -0.59,
                1.71,
                5.1,
                0.0,
                290.0,
            ],
            [
                datetime(1999, 1, 27, 23, 0),
                datetime(1999, 1, 27, 22, 56),
                "KORD",
                "19990127",
                " 23:00:00",
                " 22:56:00",
                -0.59,
                1.71,
                4.6,
                0.0,
                280.0,
            ],
        ],
        columns=[
            "X1_X2",
            "X1_X3",
            "X0",
            "X1",
            "X2",
            "X3",
            "X4",
            "X5",
            "X6",
            "X7",
            "X8",
        ],
    )

    if not keep_date_col:
        expected = expected.drop(["X1", "X2", "X3"], axis=1)

    tm.assert_frame_equal(result, expected)


def test_date_col_as_index_col(all_parsers):
    data = """\
KORD,19990127 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
"""
    parser = all_parsers
    kwds = {
        "header": None,
        "parse_dates": [1],
        "index_col": 1,
        "names": ["X0", "X1", "X2", "X3", "X4", "X5", "X6", "X7"],
    }
    result = parser.read_csv(StringIO(data), **kwds)

    index = Index(
        [
            datetime(1999, 1, 27, 19, 0),
            datetime(1999, 1, 27, 20, 0),
            datetime(1999, 1, 27, 21, 0),
            datetime(1999, 1, 27, 21, 0),
            datetime(1999, 1, 27, 22, 0),
        ],
        name="X1",
    )
    expected = DataFrame(
        [
            ["KORD", " 18:56:00", 0.81, 2.81, 7.2, 0.0, 280.0],
            ["KORD", " 19:56:00", 0.01, 2.21, 7.2, 0.0, 260.0],
            ["KORD", " 20:56:00", -0.59, 2.21, 5.7, 0.0, 280.0],
            ["KORD", " 21:18:00", -0.99, 2.01, 3.6, 0.0, 270.0],
            ["KORD", " 21:56:00", -0.59, 1.71, 5.1, 0.0, 290.0],
        ],
        columns=["X0", "X2", "X3", "X4", "X5", "X6", "X7"],
        index=index,
    )
    if parser.engine == "pyarrow":
        # https://github.com/pandas-dev/pandas/issues/44231
        # pyarrow 6.0 starts to infer time type
        expected["X2"] = pd.to_datetime("1970-01-01" + expected["X2"]).dt.time

    tm.assert_frame_equal(result, expected)


def test_multiple_date_cols_int_cast(all_parsers):
    data = (
        "KORD,19990127, 19:00:00, 18:56:00, 0.8100\n"
        "KORD,19990127, 20:00:00, 19:56:00, 0.0100\n"
        "KORD,19990127, 21:00:00, 20:56:00, -0.5900\n"
        "KORD,19990127, 21:00:00, 21:18:00, -0.9900\n"
        "KORD,19990127, 22:00:00, 21:56:00, -0.5900\n"
        "KORD,19990127, 23:00:00, 22:56:00, -0.5900"
    )
    parse_dates = {"actual": [1, 2], "nominal": [1, 3]}
    parser = all_parsers

    kwds = {
        "header": None,
        "parse_dates": parse_dates,
        "date_parser": pd.to_datetime,
    }
    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        **kwds,
        raise_on_extra_warnings=False,
    )

    expected = DataFrame(
        [
            [datetime(1999, 1, 27, 19, 0), datetime(1999, 1, 27, 18, 56), "KORD", 0.81],
            [datetime(1999, 1, 27, 20, 0), datetime(1999, 1, 27, 19, 56), "KORD", 0.01],
            [
                datetime(1999, 1, 27, 21, 0),
                datetime(1999, 1, 27, 20, 56),
                "KORD",
                -0.59,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                datetime(1999, 1, 27, 21, 18),
                "KORD",
                -0.99,
            ],
            [
                datetime(1999, 1, 27, 22, 0),
                datetime(1999, 1, 27, 21, 56),
                "KORD",
                -0.59,
            ],
            [
                datetime(1999, 1, 27, 23, 0),
                datetime(1999, 1, 27, 22, 56),
                "KORD",
                -0.59,
            ],
        ],
        columns=["actual", "nominal", 0, 4],
    )

    # Python can sometimes be flaky about how
    # the aggregated columns are entered, so
    # this standardizes the order.
    result = result[expected.columns]
    tm.assert_frame_equal(result, expected)


def test_multiple_date_col_timestamp_parse(all_parsers):
    parser = all_parsers
    data = """05/31/2012,15:30:00.029,1306.25,1,E,0,,1306.25
05/31/2012,15:30:00.029,1306.25,8,E,0,,1306.25"""

    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        parse_dates=[[0, 1]],
        header=None,
        date_parser=Timestamp,
        raise_on_extra_warnings=False,
    )
    expected = DataFrame(
        [
            [
                Timestamp("05/31/2012, 15:30:00.029"),
                1306.25,
                1,
                "E",
                0,
                np.nan,
                1306.25,
            ],
            [
                Timestamp("05/31/2012, 15:30:00.029"),
                1306.25,
                8,
                "E",
                0,
                np.nan,
                1306.25,
            ],
        ],
        columns=["0_1", 2, 3, 4, 5, 6, 7],
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_multiple_date_cols_with_header(all_parsers):
    parser = all_parsers
    data = """\
ID,date,NominalTime,ActualTime,TDew,TAir,Windspeed,Precip,WindDir
KORD,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000"""

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(StringIO(data), parse_dates={"nominal": [1, 2]})
    expected = DataFrame(
        [
            [
                datetime(1999, 1, 27, 19, 0),
                "KORD",
                " 18:56:00",
                0.81,
                2.81,
                7.2,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 20, 0),
                "KORD",
                " 19:56:00",
                0.01,
                2.21,
                7.2,
                0.0,
                260.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                "KORD",
                " 20:56:00",
                -0.59,
                2.21,
                5.7,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                "KORD",
                " 21:18:00",
                -0.99,
                2.01,
                3.6,
                0.0,
                270.0,
            ],
            [
                datetime(1999, 1, 27, 22, 0),
                "KORD",
                " 21:56:00",
                -0.59,
                1.71,
                5.1,
                0.0,
                290.0,
            ],
            [
                datetime(1999, 1, 27, 23, 0),
                "KORD",
                " 22:56:00",
                -0.59,
                1.71,
                4.6,
                0.0,
                280.0,
            ],
        ],
        columns=[
            "nominal",
            "ID",
            "ActualTime",
            "TDew",
            "TAir",
            "Windspeed",
            "Precip",
            "WindDir",
        ],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data,parse_dates,msg",
    [
        (
            """\
date_NominalTime,date,NominalTime
KORD1,19990127, 19:00:00
KORD2,19990127, 20:00:00""",
            [[1, 2]],
            ("New date column already in dict date_NominalTime"),
        ),
        (
            """\
ID,date,nominalTime
KORD,19990127, 19:00:00
KORD,19990127, 20:00:00""",
            {"ID": [1, 2]},
            "Date column ID already in dict",
        ),
    ],
)
def test_multiple_date_col_name_collision(all_parsers, data, parse_dates, msg):
    parser = all_parsers

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with pytest.raises(ValueError, match=msg):
        with tm.assert_produces_warning(
            (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
        ):
            parser.read_csv(StringIO(data), parse_dates=parse_dates)


def test_date_parser_int_bug(all_parsers):
    # see gh-3071
    parser = all_parsers
    data = (
        "posix_timestamp,elapsed,sys,user,queries,query_time,rows,"
        "accountid,userid,contactid,level,silo,method\n"
        "1343103150,0.062353,0,4,6,0.01690,3,"
        "12345,1,-1,3,invoice_InvoiceResource,search\n"
    )

    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        index_col=0,
        parse_dates=[0],
        # Note: we must pass tz and then drop the tz attribute
        # (if we don't CI will flake out depending on the runner's local time)
        date_parser=lambda x: datetime.fromtimestamp(int(x), tz=timezone.utc).replace(
            tzinfo=None
        ),
        raise_on_extra_warnings=False,
    )
    expected = DataFrame(
        [
            [
                0.062353,
                0,
                4,
                6,
                0.01690,
                3,
                12345,
                1,
                -1,
                3,
                "invoice_InvoiceResource",
                "search",
            ]
        ],
        columns=[
            "elapsed",
            "sys",
            "user",
            "queries",
            "query_time",
            "rows",
            "accountid",
            "userid",
            "contactid",
            "level",
            "silo",
            "method",
        ],
        index=Index([Timestamp("2012-07-24 04:12:30")], name="posix_timestamp"),
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_nat_parse(all_parsers):
    # see gh-3062
    parser = all_parsers
    df = DataFrame(
        {
            "A": np.arange(10, dtype="float64"),
            "B": Timestamp("20010101").as_unit("ns"),
        }
    )
    df.iloc[3:6, :] = np.nan

    with tm.ensure_clean("__nat_parse_.csv") as path:
        df.to_csv(path)

        result = parser.read_csv(path, index_col=0, parse_dates=["B"])
        tm.assert_frame_equal(result, df)


@skip_pyarrow
def test_csv_custom_parser(all_parsers):
    data = """A,B,C
20090101,a,1,2
20090102,b,3,4
20090103,c,4,5
"""
    parser = all_parsers
    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        date_parser=lambda x: datetime.strptime(x, "%Y%m%d"),
    )
    expected = parser.read_csv(StringIO(data), parse_dates=True)
    tm.assert_frame_equal(result, expected)
    result = parser.read_csv(StringIO(data), date_format="%Y%m%d")
    tm.assert_frame_equal(result, expected)


@skip_pyarrow
def test_parse_dates_implicit_first_col(all_parsers):
    data = """A,B,C
20090101,a,1,2
20090102,b,3,4
20090103,c,4,5
"""
    parser = all_parsers
    result = parser.read_csv(StringIO(data), parse_dates=True)

    expected = parser.read_csv(StringIO(data), index_col=0, parse_dates=True)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_parse_dates_string(all_parsers):
    data = """date,A,B,C
20090101,a,1,2
20090102,b,3,4
20090103,c,4,5
"""
    parser = all_parsers
    result = parser.read_csv(StringIO(data), index_col="date", parse_dates=["date"])
    # freq doesn't round-trip
    index = date_range("1/1/2009", periods=3, name="date")._with_freq(None)

    expected = DataFrame(
        {"A": ["a", "b", "c"], "B": [1, 3, 4], "C": [2, 4, 5]}, index=index
    )
    tm.assert_frame_equal(result, expected)


# Bug in https://github.com/dateutil/dateutil/issues/217
# has been addressed, but we just don't pass in the `yearfirst`
@pytest.mark.xfail(reason="yearfirst is not surfaced in read_*")
@pytest.mark.parametrize("parse_dates", [[["date", "time"]], [[0, 1]]])
def test_yy_format_with_year_first(all_parsers, parse_dates):
    data = """date,time,B,C
090131,0010,1,2
090228,1020,3,4
090331,0830,5,6
"""
    parser = all_parsers
    result = parser.read_csv_check_warnings(
        UserWarning,
        "Could not infer format",
        StringIO(data),
        index_col=0,
        parse_dates=parse_dates,
    )
    index = DatetimeIndex(
        [
            datetime(2009, 1, 31, 0, 10, 0),
            datetime(2009, 2, 28, 10, 20, 0),
            datetime(2009, 3, 31, 8, 30, 0),
        ],
        dtype=object,
        name="date_time",
    )
    expected = DataFrame({"B": [1, 3, 5], "C": [2, 4, 6]}, index=index)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
@pytest.mark.parametrize("parse_dates", [[0, 2], ["a", "c"]])
def test_parse_dates_column_list(all_parsers, parse_dates):
    data = "a,b,c\n01/01/2010,1,15/02/2010"
    parser = all_parsers

    expected = DataFrame(
        {"a": [datetime(2010, 1, 1)], "b": [1], "c": [datetime(2010, 2, 15)]}
    )
    expected = expected.set_index(["a", "b"])

    result = parser.read_csv(
        StringIO(data), index_col=[0, 1], parse_dates=parse_dates, dayfirst=True
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
@pytest.mark.parametrize("index_col", [[0, 1], [1, 0]])
def test_multi_index_parse_dates(all_parsers, index_col):
    data = """index1,index2,A,B,C
20090101,one,a,1,2
20090101,two,b,3,4
20090101,three,c,4,5
20090102,one,a,1,2
20090102,two,b,3,4
20090102,three,c,4,5
20090103,one,a,1,2
20090103,two,b,3,4
20090103,three,c,4,5
"""
    parser = all_parsers
    index = MultiIndex.from_product(
        [
            (datetime(2009, 1, 1), datetime(2009, 1, 2), datetime(2009, 1, 3)),
            ("one", "two", "three"),
        ],
        names=["index1", "index2"],
    )

    # Out of order.
    if index_col == [1, 0]:
        index = index.swaplevel(0, 1)

    expected = DataFrame(
        [
            ["a", 1, 2],
            ["b", 3, 4],
            ["c", 4, 5],
            ["a", 1, 2],
            ["b", 3, 4],
            ["c", 4, 5],
            ["a", 1, 2],
            ["b", 3, 4],
            ["c", 4, 5],
        ],
        columns=["A", "B", "C"],
        index=index,
    )
    result = parser.read_csv_check_warnings(
        UserWarning,
        "Could not infer format",
        StringIO(data),
        index_col=index_col,
        parse_dates=True,
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
@pytest.mark.parametrize("kwargs", [{"dayfirst": True}, {"day_first": True}])
def test_parse_dates_custom_euro_format(all_parsers, kwargs):
    parser = all_parsers
    data = """foo,bar,baz
31/01/2010,1,2
01/02/2010,1,NA
02/02/2010,1,2
"""
    if "dayfirst" in kwargs:
        df = parser.read_csv_check_warnings(
            FutureWarning,
            "use 'date_format' instead",
            StringIO(data),
            names=["time", "Q", "NTU"],
            date_parser=lambda d: du_parse(d, **kwargs),
            header=0,
            index_col=0,
            parse_dates=True,
            na_values=["NA"],
        )
        exp_index = Index(
            [datetime(2010, 1, 31), datetime(2010, 2, 1), datetime(2010, 2, 2)],
            name="time",
        )
        expected = DataFrame(
            {"Q": [1, 1, 1], "NTU": [2, np.nan, 2]},
            index=exp_index,
            columns=["Q", "NTU"],
        )
        tm.assert_frame_equal(df, expected)
    else:
        msg = "got an unexpected keyword argument 'day_first'"
        with pytest.raises(TypeError, match=msg):
            parser.read_csv_check_warnings(
                FutureWarning,
                "use 'date_format' instead",
                StringIO(data),
                names=["time", "Q", "NTU"],
                date_parser=lambda d: du_parse(d, **kwargs),
                skiprows=[0],
                index_col=0,
                parse_dates=True,
                na_values=["NA"],
            )


def test_parse_tz_aware(all_parsers):
    # See gh-1693
    parser = all_parsers
    data = "Date,x\n2012-06-13T01:39:00Z,0.5"

    result = parser.read_csv(StringIO(data), index_col=0, parse_dates=True)
    # TODO: make unit check more specific
    if parser.engine == "pyarrow":
        result.index = result.index.as_unit("ns")
    expected = DataFrame(
        {"x": [0.5]}, index=Index([Timestamp("2012-06-13 01:39:00+00:00")], name="Date")
    )
    if parser.engine == "pyarrow":
        expected_tz = pytz.utc
    else:
        expected_tz = timezone.utc
    tm.assert_frame_equal(result, expected)
    assert result.index.tz is expected_tz


@xfail_pyarrow
@pytest.mark.parametrize(
    "parse_dates,index_col",
    [({"nominal": [1, 2]}, "nominal"), ({"nominal": [1, 2]}, 0), ([[1, 2]], 0)],
)
def test_multiple_date_cols_index(all_parsers, parse_dates, index_col):
    parser = all_parsers
    data = """
ID,date,NominalTime,ActualTime,TDew,TAir,Windspeed,Precip,WindDir
KORD1,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD2,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD3,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD4,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD5,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD6,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000
"""
    expected = DataFrame(
        [
            [
                datetime(1999, 1, 27, 19, 0),
                "KORD1",
                " 18:56:00",
                0.81,
                2.81,
                7.2,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 20, 0),
                "KORD2",
                " 19:56:00",
                0.01,
                2.21,
                7.2,
                0.0,
                260.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                "KORD3",
                " 20:56:00",
                -0.59,
                2.21,
                5.7,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                "KORD4",
                " 21:18:00",
                -0.99,
                2.01,
                3.6,
                0.0,
                270.0,
            ],
            [
                datetime(1999, 1, 27, 22, 0),
                "KORD5",
                " 21:56:00",
                -0.59,
                1.71,
                5.1,
                0.0,
                290.0,
            ],
            [
                datetime(1999, 1, 27, 23, 0),
                "KORD6",
                " 22:56:00",
                -0.59,
                1.71,
                4.6,
                0.0,
                280.0,
            ],
        ],
        columns=[
            "nominal",
            "ID",
            "ActualTime",
            "TDew",
            "TAir",
            "Windspeed",
            "Precip",
            "WindDir",
        ],
    )
    expected = expected.set_index("nominal")

    if not isinstance(parse_dates, dict):
        expected.index.name = "date_NominalTime"

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), parse_dates=parse_dates, index_col=index_col
        )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_multiple_date_cols_chunked(all_parsers):
    parser = all_parsers
    data = """\
ID,date,nominalTime,actualTime,A,B,C,D,E
KORD,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000
"""

    expected = DataFrame(
        [
            [
                datetime(1999, 1, 27, 19, 0),
                "KORD",
                " 18:56:00",
                0.81,
                2.81,
                7.2,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 20, 0),
                "KORD",
                " 19:56:00",
                0.01,
                2.21,
                7.2,
                0.0,
                260.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                "KORD",
                " 20:56:00",
                -0.59,
                2.21,
                5.7,
                0.0,
                280.0,
            ],
            [
                datetime(1999, 1, 27, 21, 0),
                "KORD",
                " 21:18:00",
                -0.99,
                2.01,
                3.6,
                0.0,
                270.0,
            ],
            [
                datetime(1999, 1, 27, 22, 0),
                "KORD",
                " 21:56:00",
                -0.59,
                1.71,
                5.1,
                0.0,
                290.0,
            ],
            [
                datetime(1999, 1, 27, 23, 0),
                "KORD",
                " 22:56:00",
                -0.59,
                1.71,
                4.6,
                0.0,
                280.0,
            ],
        ],
        columns=["nominal", "ID", "actualTime", "A", "B", "C", "D", "E"],
    )
    expected = expected.set_index("nominal")

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        with parser.read_csv(
            StringIO(data),
            parse_dates={"nominal": [1, 2]},
            index_col="nominal",
            chunksize=2,
        ) as reader:
            chunks = list(reader)

    tm.assert_frame_equal(chunks[0], expected[:2])
    tm.assert_frame_equal(chunks[1], expected[2:4])
    tm.assert_frame_equal(chunks[2], expected[4:])


def test_multiple_date_col_named_index_compat(all_parsers):
    parser = all_parsers
    data = """\
ID,date,nominalTime,actualTime,A,B,C,D,E
KORD,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000
"""

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        with_indices = parser.read_csv(
            StringIO(data), parse_dates={"nominal": [1, 2]}, index_col="nominal"
        )

    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        with_names = parser.read_csv(
            StringIO(data),
            index_col="nominal",
            parse_dates={"nominal": ["date", "nominalTime"]},
        )
    tm.assert_frame_equal(with_indices, with_names)


def test_multiple_date_col_multiple_index_compat(all_parsers):
    parser = all_parsers
    data = """\
ID,date,nominalTime,actualTime,A,B,C,D,E
KORD,19990127, 19:00:00, 18:56:00, 0.8100, 2.8100, 7.2000, 0.0000, 280.0000
KORD,19990127, 20:00:00, 19:56:00, 0.0100, 2.2100, 7.2000, 0.0000, 260.0000
KORD,19990127, 21:00:00, 20:56:00, -0.5900, 2.2100, 5.7000, 0.0000, 280.0000
KORD,19990127, 21:00:00, 21:18:00, -0.9900, 2.0100, 3.6000, 0.0000, 270.0000
KORD,19990127, 22:00:00, 21:56:00, -0.5900, 1.7100, 5.1000, 0.0000, 290.0000
KORD,19990127, 23:00:00, 22:56:00, -0.5900, 1.7100, 4.6000, 0.0000, 280.0000
"""
    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), index_col=["nominal", "ID"], parse_dates={"nominal": [1, 2]}
        )
    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        expected = parser.read_csv(StringIO(data), parse_dates={"nominal": [1, 2]})

    expected = expected.set_index(["nominal", "ID"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("kwargs", [{}, {"index_col": "C"}])
def test_read_with_parse_dates_scalar_non_bool(all_parsers, kwargs):
    # see gh-5636
    parser = all_parsers
    msg = (
        "Only booleans, lists, and dictionaries "
        "are accepted for the 'parse_dates' parameter"
    )
    data = """A,B,C
    1,2,2003-11-1"""

    with pytest.raises(TypeError, match=msg):
        parser.read_csv(StringIO(data), parse_dates="C", **kwargs)


@pytest.mark.parametrize("parse_dates", [(1,), np.array([4, 5]), {1, 3}])
def test_read_with_parse_dates_invalid_type(all_parsers, parse_dates):
    parser = all_parsers
    msg = (
        "Only booleans, lists, and dictionaries "
        "are accepted for the 'parse_dates' parameter"
    )
    data = """A,B,C
    1,2,2003-11-1"""

    with pytest.raises(TypeError, match=msg):
        parser.read_csv(StringIO(data), parse_dates=(1,))


@pytest.mark.parametrize("cache_dates", [True, False])
@pytest.mark.parametrize("value", ["nan", ""])
def test_bad_date_parse(all_parsers, cache_dates, value):
    # if we have an invalid date make sure that we handle this with
    # and w/o the cache properly
    parser = all_parsers
    s = StringIO((f"{value},\n") * (start_caching_at + 1))

    parser.read_csv(
        s,
        header=None,
        names=["foo", "bar"],
        parse_dates=["foo"],
        cache_dates=cache_dates,
    )


@pytest.mark.parametrize("cache_dates", [True, False])
@pytest.mark.parametrize("value", ["0"])
def test_bad_date_parse_with_warning(all_parsers, cache_dates, value):
    # if we have an invalid date make sure that we handle this with
    # and w/o the cache properly.
    parser = all_parsers
    s = StringIO((f"{value},\n") * 50000)

    if parser.engine == "pyarrow":
        # pyarrow reads "0" as 0 (of type int64), and so
        # pandas doesn't try to guess the datetime format
        # TODO: parse dates directly in pyarrow, see
        # https://github.com/pandas-dev/pandas/issues/48017
        warn = None
    elif cache_dates:
        # Note: warning is not raised if 'cache_dates', because here there is only a
        # single unique date and hence no risk of inconsistent parsing.
        warn = None
    else:
        warn = UserWarning
    parser.read_csv_check_warnings(
        warn,
        "Could not infer format",
        s,
        header=None,
        names=["foo", "bar"],
        parse_dates=["foo"],
        cache_dates=cache_dates,
        raise_on_extra_warnings=False,
    )


@xfail_pyarrow
def test_parse_dates_empty_string(all_parsers):
    # see gh-2263
    parser = all_parsers
    data = "Date,test\n2012-01-01,1\n,2"
    result = parser.read_csv(StringIO(data), parse_dates=["Date"], na_filter=False)

    expected = DataFrame(
        [[datetime(2012, 1, 1), 1], [pd.NaT, 2]], columns=["Date", "test"]
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "reader", ["read_csv_check_warnings", "read_table_check_warnings"]
)
def test_parse_dates_infer_datetime_format_warning(all_parsers, reader):
    # GH 49024, 51017
    parser = all_parsers
    data = "Date,test\n2012-01-01,1\n,2"

    getattr(parser, reader)(
        FutureWarning,
        "The argument 'infer_datetime_format' is deprecated",
        StringIO(data),
        parse_dates=["Date"],
        infer_datetime_format=True,
        sep=",",
        raise_on_extra_warnings=False,
    )


@pytest.mark.parametrize(
    "reader", ["read_csv_check_warnings", "read_table_check_warnings"]
)
def test_parse_dates_date_parser_and_date_format(all_parsers, reader):
    # GH 50601
    parser = all_parsers
    data = "Date,test\n2012-01-01,1\n,2"
    msg = "Cannot use both 'date_parser' and 'date_format'"
    with pytest.raises(TypeError, match=msg):
        getattr(parser, reader)(
            FutureWarning,
            "use 'date_format' instead",
            StringIO(data),
            parse_dates=["Date"],
            date_parser=pd.to_datetime,
            date_format="ISO8601",
            sep=",",
        )


@xfail_pyarrow
@pytest.mark.parametrize(
    "data,kwargs,expected",
    [
        (
            "a\n04.15.2016",
            {"parse_dates": ["a"]},
            DataFrame([datetime(2016, 4, 15)], columns=["a"]),
        ),
        (
            "a\n04.15.2016",
            {"parse_dates": True, "index_col": 0},
            DataFrame(index=DatetimeIndex(["2016-04-15"], name="a"), columns=[]),
        ),
        (
            "a,b\n04.15.2016,09.16.2013",
            {"parse_dates": ["a", "b"]},
            DataFrame(
                [[datetime(2016, 4, 15), datetime(2013, 9, 16)]], columns=["a", "b"]
            ),
        ),
        (
            "a,b\n04.15.2016,09.16.2013",
            {"parse_dates": True, "index_col": [0, 1]},
            DataFrame(
                index=MultiIndex.from_tuples(
                    [(datetime(2016, 4, 15), datetime(2013, 9, 16))], names=["a", "b"]
                ),
                columns=[],
            ),
        ),
    ],
)
def test_parse_dates_no_convert_thousands(all_parsers, data, kwargs, expected):
    # see gh-14066
    parser = all_parsers

    result = parser.read_csv(StringIO(data), thousands=".", **kwargs)
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_parse_date_time_multi_level_column_name(all_parsers):
    data = """\
D,T,A,B
date, time,a,b
2001-01-05, 09:00:00, 0.0, 10.
2001-01-06, 00:00:00, 1.0, 11.
"""
    parser = all_parsers
    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        header=[0, 1],
        parse_dates={"date_time": [0, 1]},
        date_parser=pd.to_datetime,
    )

    expected_data = [
        [datetime(2001, 1, 5, 9, 0, 0), 0.0, 10.0],
        [datetime(2001, 1, 6, 0, 0, 0), 1.0, 11.0],
    ]
    expected = DataFrame(expected_data, columns=["date_time", ("A", "a"), ("B", "b")])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data,kwargs,expected",
    [
        (
            """\
date,time,a,b
2001-01-05, 10:00:00, 0.0, 10.
2001-01-05, 00:00:00, 1., 11.
""",
            {"header": 0, "parse_dates": {"date_time": [0, 1]}},
            DataFrame(
                [
                    [datetime(2001, 1, 5, 10, 0, 0), 0.0, 10],
                    [datetime(2001, 1, 5, 0, 0, 0), 1.0, 11.0],
                ],
                columns=["date_time", "a", "b"],
            ),
        ),
        (
            (
                "KORD,19990127, 19:00:00, 18:56:00, 0.8100\n"
                "KORD,19990127, 20:00:00, 19:56:00, 0.0100\n"
                "KORD,19990127, 21:00:00, 20:56:00, -0.5900\n"
                "KORD,19990127, 21:00:00, 21:18:00, -0.9900\n"
                "KORD,19990127, 22:00:00, 21:56:00, -0.5900\n"
                "KORD,19990127, 23:00:00, 22:56:00, -0.5900"
            ),
            {"header": None, "parse_dates": {"actual": [1, 2], "nominal": [1, 3]}},
            DataFrame(
                [
                    [
                        datetime(1999, 1, 27, 19, 0),
                        datetime(1999, 1, 27, 18, 56),
                        "KORD",
                        0.81,
                    ],
                    [
                        datetime(1999, 1, 27, 20, 0),
                        datetime(1999, 1, 27, 19, 56),
                        "KORD",
                        0.01,
                    ],
                    [
                        datetime(1999, 1, 27, 21, 0),
                        datetime(1999, 1, 27, 20, 56),
                        "KORD",
                        -0.59,
                    ],
                    [
                        datetime(1999, 1, 27, 21, 0),
                        datetime(1999, 1, 27, 21, 18),
                        "KORD",
                        -0.99,
                    ],
                    [
                        datetime(1999, 1, 27, 22, 0),
                        datetime(1999, 1, 27, 21, 56),
                        "KORD",
                        -0.59,
                    ],
                    [
                        datetime(1999, 1, 27, 23, 0),
                        datetime(1999, 1, 27, 22, 56),
                        "KORD",
                        -0.59,
                    ],
                ],
                columns=["actual", "nominal", 0, 4],
            ),
        ),
    ],
)
def test_parse_date_time(all_parsers, data, kwargs, expected):
    parser = all_parsers
    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        date_parser=pd.to_datetime,
        **kwargs,
        raise_on_extra_warnings=False,
    )

    # Python can sometimes be flaky about how
    # the aggregated columns are entered, so
    # this standardizes the order.
    result = result[expected.columns]
    tm.assert_frame_equal(result, expected)


def test_parse_date_fields(all_parsers):
    parser = all_parsers
    data = "year,month,day,a\n2001,01,10,10.\n2001,02,1,11."
    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        header=0,
        parse_dates={"ymd": [0, 1, 2]},
        date_parser=lambda x: x,
        raise_on_extra_warnings=False,
    )

    expected = DataFrame(
        [[datetime(2001, 1, 10), 10.0], [datetime(2001, 2, 1), 11.0]],
        columns=["ymd", "a"],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    ("key", "value", "warn"),
    [
        (
            "date_parser",
            lambda x: pd.to_datetime(x, format="%Y %m %d %H %M %S"),
            FutureWarning,
        ),
        ("date_format", "%Y %m %d %H %M %S", None),
    ],
)
def test_parse_date_all_fields(all_parsers, key, value, warn):
    parser = all_parsers
    data = """\
year,month,day,hour,minute,second,a,b
2001,01,05,10,00,0,0.0,10.
2001,01,5,10,0,00,1.,11.
"""
    result = parser.read_csv_check_warnings(
        warn,
        "use 'date_format' instead",
        StringIO(data),
        header=0,
        parse_dates={"ymdHMS": [0, 1, 2, 3, 4, 5]},
        **{key: value},
        raise_on_extra_warnings=False,
    )
    expected = DataFrame(
        [
            [datetime(2001, 1, 5, 10, 0, 0), 0.0, 10.0],
            [datetime(2001, 1, 5, 10, 0, 0), 1.0, 11.0],
        ],
        columns=["ymdHMS", "a", "b"],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    ("key", "value", "warn"),
    [
        (
            "date_parser",
            lambda x: pd.to_datetime(x, format="%Y %m %d %H %M %S.%f"),
            FutureWarning,
        ),
        ("date_format", "%Y %m %d %H %M %S.%f", None),
    ],
)
def test_datetime_fractional_seconds(all_parsers, key, value, warn):
    parser = all_parsers
    data = """\
year,month,day,hour,minute,second,a,b
2001,01,05,10,00,0.123456,0.0,10.
2001,01,5,10,0,0.500000,1.,11.
"""
    result = parser.read_csv_check_warnings(
        warn,
        "use 'date_format' instead",
        StringIO(data),
        header=0,
        parse_dates={"ymdHMS": [0, 1, 2, 3, 4, 5]},
        **{key: value},
        raise_on_extra_warnings=False,
    )
    expected = DataFrame(
        [
            [datetime(2001, 1, 5, 10, 0, 0, microsecond=123456), 0.0, 10.0],
            [datetime(2001, 1, 5, 10, 0, 0, microsecond=500000), 1.0, 11.0],
        ],
        columns=["ymdHMS", "a", "b"],
    )
    tm.assert_frame_equal(result, expected)


def test_generic(all_parsers):
    parser = all_parsers
    data = "year,month,day,a\n2001,01,10,10.\n2001,02,1,11."

    def parse_function(yy, mm):
        return [date(year=int(y), month=int(m), day=1) for y, m in zip(yy, mm)]

    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        header=0,
        parse_dates={"ym": [0, 1]},
        date_parser=parse_function,
        raise_on_extra_warnings=False,
    )
    expected = DataFrame(
        [[date(2001, 1, 1), 10, 10.0], [date(2001, 2, 1), 1, 11.0]],
        columns=["ym", "day", "a"],
    )
    expected["ym"] = expected["ym"].astype("datetime64[ns]")
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow
def test_date_parser_resolution_if_not_ns(all_parsers):
    # see gh-10245
    parser = all_parsers
    data = """\
date,time,prn,rxstatus
2013-11-03,19:00:00,126,00E80000
2013-11-03,19:00:00,23,00E80000
2013-11-03,19:00:00,13,00E80000
"""

    def date_parser(dt, time):
        try:
            arr = dt + "T" + time
        except TypeError:
            # dt & time are date/time objects
            arr = [datetime.combine(d, t) for d, t in zip(dt, time)]
        return np.array(arr, dtype="datetime64[s]")

    result = parser.read_csv_check_warnings(
        FutureWarning,
        "use 'date_format' instead",
        StringIO(data),
        date_parser=date_parser,
        parse_dates={"datetime": ["date", "time"]},
        index_col=["datetime", "prn"],
    )

    datetimes = np.array(["2013-11-03T19:00:00"] * 3, dtype="datetime64[s]")
    expected = DataFrame(
        data={"rxstatus": ["00E80000"] * 3},
        index=MultiIndex.from_arrays(
            [datetimes, [126, 23, 13]],
            names=["datetime", "prn"],
        ),
    )
    tm.assert_frame_equal(result, expected)


def test_parse_date_column_with_empty_string(all_parsers):
    # see gh-6428
    parser = all_parsers
    data = "case,opdate\n7,10/18/2006\n7,10/18/2008\n621, "
    result = parser.read_csv(StringIO(data), parse_dates=["opdate"])

    expected_data = [[7, "10/18/2006"], [7, "10/18/2008"], [621, " "]]
    expected = DataFrame(expected_data, columns=["case", "opdate"])
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "data,expected",
    [
        (
            "a\n135217135789158401\n1352171357E+5",
            DataFrame({"a": [135217135789158401, 135217135700000]}, dtype="float64"),
        ),
        (
            "a\n99999999999\n123456789012345\n1234E+0",
            DataFrame({"a": [99999999999, 123456789012345, 1234]}, dtype="float64"),
        ),
    ],
)
@pytest.mark.parametrize("parse_dates", [True, False])
def test_parse_date_float(all_parsers, data, expected, parse_dates):
    # see gh-2697
    #
    # Date parsing should fail, so we leave the data untouched
    # (i.e. float precision should remain unchanged).
    parser = all_parsers

    result = parser.read_csv(StringIO(data), parse_dates=parse_dates)
    tm.assert_frame_equal(result, expected)


def test_parse_timezone(all_parsers):
    # see gh-22256
    parser = all_parsers
    data = """dt,val
              2018-01-04 09:01:00+09:00,23350
              2018-01-04 09:02:00+09:00,23400
              2018-01-04 09:03:00+09:00,23400
              2018-01-04 09:04:00+09:00,23400
              2018-01-04 09:05:00+09:00,23400"""
    result = parser.read_csv(StringIO(data), parse_dates=["dt"])

    dti = date_range(
        start="2018-01-04 09:01:00",
        end="2018-01-04 09:05:00",
        freq="1min",
        tz=timezone(timedelta(minutes=540)),
    )._with_freq(None)
    expected_data = {"dt": dti, "val": [23350, 23400, 23400, 23400, 23400]}

    expected = DataFrame(expected_data)
    tm.assert_frame_equal(result, expected)


@skip_pyarrow  # pandas.errors.ParserError: CSV parse error
@pytest.mark.parametrize(
    "date_string",
    ["32/32/2019", "02/30/2019", "13/13/2019", "13/2019", "a3/11/2018", "10/11/2o17"],
)
def test_invalid_parse_delimited_date(all_parsers, date_string):
    parser = all_parsers
    expected = DataFrame({0: [date_string]}, dtype="str")
    result = parser.read_csv(
        StringIO(date_string),
        header=None,
        parse_dates=[0],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "date_string,dayfirst,expected",
    [
        # %d/%m/%Y; month > 12 thus replacement
        ("13/02/2019", True, datetime(2019, 2, 13)),
        # %m/%d/%Y; day > 12 thus there will be no replacement
        ("02/13/2019", False, datetime(2019, 2, 13)),
        # %d/%m/%Y; dayfirst==True thus replacement
        ("04/02/2019", True, datetime(2019, 2, 4)),
    ],
)
def test_parse_delimited_date_swap_no_warning(
    all_parsers, date_string, dayfirst, expected, request
):
    parser = all_parsers
    expected = DataFrame({0: [expected]}, dtype="datetime64[ns]")
    if parser.engine == "pyarrow":
        if not dayfirst:
            # "CSV parse error: Empty CSV file or block"
            pytest.skip(reason="https://github.com/apache/arrow/issues/38676")
        msg = "The 'dayfirst' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(date_string), header=None, dayfirst=dayfirst, parse_dates=[0]
            )
        return

    result = parser.read_csv(
        StringIO(date_string), header=None, dayfirst=dayfirst, parse_dates=[0]
    )
    tm.assert_frame_equal(result, expected)


# ArrowInvalid: CSV parse error: Empty CSV file or block: cannot infer number of columns
@skip_pyarrow
@pytest.mark.parametrize(
    "date_string,dayfirst,expected",
    [
        # %d/%m/%Y; month > 12
        ("13/02/2019", False, datetime(2019, 2, 13)),
        # %m/%d/%Y; day > 12
        ("02/13/2019", True, datetime(2019, 2, 13)),
    ],
)
def test_parse_delimited_date_swap_with_warning(
    all_parsers, date_string, dayfirst, expected
):
    parser = all_parsers
    expected = DataFrame({0: [expected]}, dtype="datetime64[ns]")
    warning_msg = (
        "Parsing dates in .* format when dayfirst=.* was specified. "
        "Pass `dayfirst=.*` or specify a format to silence this warning."
    )
    result = parser.read_csv_check_warnings(
        UserWarning,
        warning_msg,
        StringIO(date_string),
        header=None,
        dayfirst=dayfirst,
        parse_dates=[0],
    )
    tm.assert_frame_equal(result, expected)


def test_parse_multiple_delimited_dates_with_swap_warnings():
    # GH46210
    with pytest.raises(
        ValueError,
        match=(
            r'^time data "31/05/2000" doesn\'t match format "%m/%d/%Y", '
            r"at position 1. You might want to try:"
        ),
    ):
        pd.to_datetime(["01/01/2000", "31/05/2000", "31/05/2001", "01/02/2000"])


# ArrowKeyError: Column 'fdate1' in include_columns does not exist in CSV file
@skip_pyarrow
@pytest.mark.parametrize(
    "names, usecols, parse_dates, missing_cols",
    [
        (None, ["val"], ["date", "time"], "date, time"),
        (None, ["val"], [0, "time"], "time"),
        (None, ["val"], [["date", "time"]], "date, time"),
        (None, ["val"], [[0, "time"]], "time"),
        (None, ["val"], {"date": [0, "time"]}, "time"),
        (None, ["val"], {"date": ["date", "time"]}, "date, time"),
        (None, ["val"], [["date", "time"], "date"], "date, time"),
        (["date1", "time1", "temperature"], None, ["date", "time"], "date, time"),
        (
            ["date1", "time1", "temperature"],
            ["date1", "temperature"],
            ["date1", "time"],
            "time",
        ),
    ],
)
def test_missing_parse_dates_column_raises(
    all_parsers, names, usecols, parse_dates, missing_cols
):
    # gh-31251 column names provided in parse_dates could be missing.
    parser = all_parsers
    content = StringIO("date,time,val\n2020-01-31,04:20:32,32\n")
    msg = f"Missing column provided to 'parse_dates': '{missing_cols}'"

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    warn = FutureWarning
    if isinstance(parse_dates, list) and all(
        isinstance(x, (int, str)) for x in parse_dates
    ):
        warn = None

    with pytest.raises(ValueError, match=msg):
        with tm.assert_produces_warning(warn, match=depr_msg, check_stacklevel=False):
            parser.read_csv(
                content, sep=",", names=names, usecols=usecols, parse_dates=parse_dates
            )


@xfail_pyarrow  # mismatched shape
def test_date_parser_and_names(all_parsers):
    # GH#33699
    parser = all_parsers
    data = StringIO("""x,y\n1,2""")
    warn = UserWarning
    if parser.engine == "pyarrow":
        # DeprecationWarning for passing a Manager object
        warn = (UserWarning, DeprecationWarning)
    result = parser.read_csv_check_warnings(
        warn,
        "Could not infer format",
        data,
        parse_dates=["B"],
        names=["B"],
    )
    expected = DataFrame({"B": ["y", "2"]}, index=["x", "1"])
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # TypeError: an integer is required
def test_date_parser_multiindex_columns(all_parsers):
    parser = all_parsers
    data = """a,b
1,2
2019-12-31,6"""
    result = parser.read_csv(StringIO(data), parse_dates=[("a", "1")], header=[0, 1])
    expected = DataFrame(
        {("a", "1"): Timestamp("2019-12-31").as_unit("ns"), ("b", "2"): [6]}
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # TypeError: an integer is required
@pytest.mark.parametrize(
    "parse_spec, col_name",
    [
        ([[("a", "1"), ("b", "2")]], ("a_b", "1_2")),
        ({("foo", "1"): [("a", "1"), ("b", "2")]}, ("foo", "1")),
    ],
)
def test_date_parser_multiindex_columns_combine_cols(all_parsers, parse_spec, col_name):
    parser = all_parsers
    data = """a,b,c
1,2,3
2019-12,-31,6"""

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data),
            parse_dates=parse_spec,
            header=[0, 1],
        )
    expected = DataFrame(
        {col_name: Timestamp("2019-12-31").as_unit("ns"), ("c", "3"): [6]}
    )
    tm.assert_frame_equal(result, expected)


def test_date_parser_usecols_thousands(all_parsers):
    # GH#39365
    data = """A,B,C
    1,3,20-09-01-01
    2,4,20-09-01-01
    """

    parser = all_parsers

    if parser.engine == "pyarrow":
        # DeprecationWarning for passing a Manager object
        msg = "The 'thousands' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(
                StringIO(data),
                parse_dates=[1],
                usecols=[1, 2],
                thousands="-",
            )
        return

    result = parser.read_csv_check_warnings(
        UserWarning,
        "Could not infer format",
        StringIO(data),
        parse_dates=[1],
        usecols=[1, 2],
        thousands="-",
    )
    expected = DataFrame({"B": [3, 4], "C": [Timestamp("20-09-2001 01:00:00")] * 2})
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # mismatched shape
def test_parse_dates_and_keep_original_column(all_parsers):
    # GH#13378
    parser = all_parsers
    data = """A
20150908
20150909
"""
    depr_msg = "The 'keep_date_col' keyword in pd.read_csv is deprecated"
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), parse_dates={"date": ["A"]}, keep_date_col=True
        )
    expected_data = [Timestamp("2015-09-08"), Timestamp("2015-09-09")]
    expected = DataFrame({"date": expected_data, "A": expected_data})
    tm.assert_frame_equal(result, expected)


def test_dayfirst_warnings():
    # GH 12585

    # CASE 1: valid input
    input = "date\n31/12/2014\n10/03/2011"
    expected = DatetimeIndex(
        ["2014-12-31", "2011-03-10"], dtype="datetime64[ns]", freq=None, name="date"
    )
    warning_msg = (
        "Parsing dates in .* format when dayfirst=.* was specified. "
        "Pass `dayfirst=.*` or specify a format to silence this warning."
    )

    # A. dayfirst arg correct, no warning
    res1 = read_csv(
        StringIO(input), parse_dates=["date"], dayfirst=True, index_col="date"
    ).index
    tm.assert_index_equal(expected, res1)

    # B. dayfirst arg incorrect, warning
    with tm.assert_produces_warning(UserWarning, match=warning_msg):
        res2 = read_csv(
            StringIO(input), parse_dates=["date"], dayfirst=False, index_col="date"
        ).index
    tm.assert_index_equal(expected, res2)

    # CASE 2: invalid input
    # cannot consistently process with single format
    # return to user unaltered

    # first in DD/MM/YYYY, second in MM/DD/YYYY
    input = "date\n31/12/2014\n03/30/2011"
    expected = Index(["31/12/2014", "03/30/2011"], dtype="str", name="date")

    # A. use dayfirst=True
    res5 = read_csv(
        StringIO(input), parse_dates=["date"], dayfirst=True, index_col="date"
    ).index
    tm.assert_index_equal(expected, res5)

    # B. use dayfirst=False
    with tm.assert_produces_warning(UserWarning, match=warning_msg):
        res6 = read_csv(
            StringIO(input), parse_dates=["date"], dayfirst=False, index_col="date"
        ).index
    tm.assert_index_equal(expected, res6)


@pytest.mark.parametrize(
    "date_string, dayfirst",
    [
        pytest.param(
            "31/1/2014",
            False,
            id="second date is single-digit",
        ),
        pytest.param(
            "1/31/2014",
            True,
            id="first date is single-digit",
        ),
    ],
)
def test_dayfirst_warnings_no_leading_zero(date_string, dayfirst):
    # GH47880
    initial_value = f"date\n{date_string}"
    expected = DatetimeIndex(
        ["2014-01-31"], dtype="datetime64[ns]", freq=None, name="date"
    )
    warning_msg = (
        "Parsing dates in .* format when dayfirst=.* was specified. "
        "Pass `dayfirst=.*` or specify a format to silence this warning."
    )
    with tm.assert_produces_warning(UserWarning, match=warning_msg):
        res = read_csv(
            StringIO(initial_value),
            parse_dates=["date"],
            index_col="date",
            dayfirst=dayfirst,
        ).index
    tm.assert_index_equal(expected, res)


@skip_pyarrow  # CSV parse error: Expected 3 columns, got 4
def test_infer_first_column_as_index(all_parsers):
    # GH#11019
    parser = all_parsers
    data = "a,b,c\n1970-01-01,2,3,4"
    result = parser.read_csv(
        StringIO(data),
        parse_dates=["a"],
    )
    expected = DataFrame({"a": "2", "b": 3, "c": 4}, index=["1970-01-01"])
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # pyarrow engine doesn't support passing a dict for na_values
@pytest.mark.parametrize(
    ("key", "value", "warn"),
    [
        ("date_parser", lambda x: pd.to_datetime(x, format="%Y-%m-%d"), FutureWarning),
        ("date_format", "%Y-%m-%d", None),
    ],
)
def test_replace_nans_before_parsing_dates(all_parsers, key, value, warn):
    # GH#26203
    parser = all_parsers
    data = """Test
2012-10-01
0
2015-05-15
#
2017-09-09
"""
    result = parser.read_csv_check_warnings(
        warn,
        "use 'date_format' instead",
        StringIO(data),
        na_values={"Test": ["#", "0"]},
        parse_dates=["Test"],
        **{key: value},
    )
    expected = DataFrame(
        {
            "Test": [
                Timestamp("2012-10-01"),
                pd.NaT,
                Timestamp("2015-05-15"),
                pd.NaT,
                Timestamp("2017-09-09"),
            ]
        }
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # string[python] instead of dt64[ns]
def test_parse_dates_and_string_dtype(all_parsers):
    # GH#34066
    parser = all_parsers
    data = """a,b
1,2019-12-31
"""
    result = parser.read_csv(StringIO(data), dtype="string", parse_dates=["b"])
    expected = DataFrame({"a": ["1"], "b": [Timestamp("2019-12-31")]})
    expected["a"] = expected["a"].astype("string")
    tm.assert_frame_equal(result, expected)


def test_parse_dot_separated_dates(all_parsers):
    # https://github.com/pandas-dev/pandas/issues/2586
    parser = all_parsers
    data = """a,b
27.03.2003 14:55:00.000,1
03.08.2003 15:20:00.000,2"""
    if parser.engine == "pyarrow":
        expected_index = Index(
            ["27.03.2003 14:55:00.000", "03.08.2003 15:20:00.000"],
            dtype="str",
            name="a",
        )
        warn = None
    else:
        expected_index = DatetimeIndex(
            ["2003-03-27 14:55:00", "2003-08-03 15:20:00"],
            dtype="datetime64[ns]",
            name="a",
        )
        warn = UserWarning
    msg = r"when dayfirst=False \(the default\) was specified"
    result = parser.read_csv_check_warnings(
        warn,
        msg,
        StringIO(data),
        parse_dates=True,
        index_col=0,
        raise_on_extra_warnings=False,
    )
    expected = DataFrame({"b": [1, 2]}, index=expected_index)
    tm.assert_frame_equal(result, expected)


def test_parse_dates_dict_format(all_parsers):
    # GH#51240
    parser = all_parsers
    data = """a,b
2019-12-31,31-12-2019
2020-12-31,31-12-2020"""

    result = parser.read_csv(
        StringIO(data),
        date_format={"a": "%Y-%m-%d", "b": "%d-%m-%Y"},
        parse_dates=["a", "b"],
    )
    expected = DataFrame(
        {
            "a": [Timestamp("2019-12-31"), Timestamp("2020-12-31")],
            "b": [Timestamp("2019-12-31"), Timestamp("2020-12-31")],
        }
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize(
    "key, parse_dates", [("a_b", [[0, 1]]), ("foo", {"foo": [0, 1]})]
)
def test_parse_dates_dict_format_two_columns(all_parsers, key, parse_dates):
    # GH#51240
    parser = all_parsers
    data = """a,b
31-,12-2019
31-,12-2020"""

    depr_msg = (
        "Support for nested sequences for 'parse_dates' in pd.read_csv is deprecated"
    )
    with tm.assert_produces_warning(
        (FutureWarning, DeprecationWarning), match=depr_msg, check_stacklevel=False
    ):
        result = parser.read_csv(
            StringIO(data), date_format={key: "%d- %m-%Y"}, parse_dates=parse_dates
        )
    expected = DataFrame(
        {
            key: [Timestamp("2019-12-31"), Timestamp("2020-12-31")],
        }
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # object dtype index
def test_parse_dates_dict_format_index(all_parsers):
    # GH#51240
    parser = all_parsers
    data = """a,b
2019-12-31,31-12-2019
2020-12-31,31-12-2020"""

    result = parser.read_csv(
        StringIO(data), date_format={"a": "%Y-%m-%d"}, parse_dates=True, index_col=0
    )
    expected = DataFrame(
        {
            "b": ["31-12-2019", "31-12-2020"],
        },
        index=Index([Timestamp("2019-12-31"), Timestamp("2020-12-31")], name="a"),
    )
    tm.assert_frame_equal(result, expected)


def test_parse_dates_arrow_engine(all_parsers):
    # GH#53295
    parser = all_parsers
    data = """a,b
2000-01-01 00:00:00,1
2000-01-01 00:00:01,1"""

    result = parser.read_csv(StringIO(data), parse_dates=["a"])
    # TODO: make unit check more specific
    if parser.engine == "pyarrow":
        result["a"] = result["a"].dt.as_unit("ns")
    expected = DataFrame(
        {
            "a": [
                Timestamp("2000-01-01 00:00:00"),
                Timestamp("2000-01-01 00:00:01"),
            ],
            "b": 1,
        }
    )
    tm.assert_frame_equal(result, expected)


@xfail_pyarrow  # object dtype index
def test_from_csv_with_mixed_offsets(all_parsers):
    parser = all_parsers
    data = "a\n2020-01-01T00:00:00+01:00\n2020-01-01T00:00:00+00:00"
    result = parser.read_csv(StringIO(data), parse_dates=["a"])["a"]
    expected = Series(
        [
            Timestamp("2020-01-01 00:00:00+01:00"),
            Timestamp("2020-01-01 00:00:00+00:00"),
        ],
        name="a",
        index=[0, 1],
    )
    tm.assert_series_equal(result, expected)
