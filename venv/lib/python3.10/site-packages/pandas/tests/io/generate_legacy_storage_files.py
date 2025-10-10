"""
self-contained to write legacy storage pickle files

To use this script. Create an environment where you want
generate pickles, say its for 0.20.3, with your pandas clone
in ~/pandas

. activate pandas_0.20.3
cd ~/pandas/pandas

$ python -m tests.io.generate_legacy_storage_files \
    tests/io/data/legacy_pickle/0.20.3/ pickle

This script generates a storage file for the current arch, system,
and python version
  pandas version: 0.20.3
  output dir    : pandas/pandas/tests/io/data/legacy_pickle/0.20.3/
  storage format: pickle
created pickle file: 0.20.3_x86_64_darwin_3.5.2.pickle

The idea here is you are using the *current* version of the
generate_legacy_storage_files with an *older* version of pandas to
generate a pickle file. We will then check this file into a current
branch, and test using test_pickle.py. This will load the *older*
pickles and test versus the current data that is generated
(with main). These are then compared.

If we have cases where we changed the signature (e.g. we renamed
offset -> freq in Timestamp). Then we have to conditionally execute
in the generate_legacy_storage_files.py to make it
run under the older AND the newer version.

"""

from datetime import timedelta
import os
import pickle
import platform as pl
import sys

# Remove script directory from path, otherwise Python will try to
# import the JSON test directory as the json module
sys.path.pop(0)

import numpy as np

import pandas
from pandas import (
    Categorical,
    DataFrame,
    Index,
    MultiIndex,
    NaT,
    Period,
    RangeIndex,
    Series,
    Timestamp,
    bdate_range,
    date_range,
    interval_range,
    period_range,
    timedelta_range,
)
from pandas.arrays import SparseArray

from pandas.tseries.offsets import (
    FY5253,
    BusinessDay,
    BusinessHour,
    CustomBusinessDay,
    DateOffset,
    Day,
    Easter,
    Hour,
    LastWeekOfMonth,
    Minute,
    MonthBegin,
    MonthEnd,
    QuarterBegin,
    QuarterEnd,
    SemiMonthBegin,
    SemiMonthEnd,
    Week,
    WeekOfMonth,
    YearBegin,
    YearEnd,
)


def _create_sp_series():
    nan = np.nan

    # nan-based
    arr = np.arange(15, dtype=np.float64)
    arr[7:12] = nan
    arr[-1:] = nan

    bseries = Series(SparseArray(arr, kind="block"))
    bseries.name = "bseries"
    return bseries


def _create_sp_tsseries():
    nan = np.nan

    # nan-based
    arr = np.arange(15, dtype=np.float64)
    arr[7:12] = nan
    arr[-1:] = nan

    date_index = bdate_range("1/1/2011", periods=len(arr))
    bseries = Series(SparseArray(arr, kind="block"), index=date_index)
    bseries.name = "btsseries"
    return bseries


def _create_sp_frame():
    nan = np.nan

    data = {
        "A": [nan, nan, nan, 0, 1, 2, 3, 4, 5, 6],
        "B": [0, 1, 2, nan, nan, nan, 3, 4, 5, 6],
        "C": np.arange(10).astype(np.int64),
        "D": [0, 1, 2, 3, 4, 5, nan, nan, nan, nan],
    }

    dates = bdate_range("1/1/2011", periods=10)
    return DataFrame(data, index=dates).apply(SparseArray)


def create_pickle_data():
    """create the pickle data"""
    data = {
        "A": [0.0, 1.0, 2.0, 3.0, np.nan],
        "B": [0, 1, 0, 1, 0],
        "C": ["foo1", "foo2", "foo3", "foo4", "foo5"],
        "D": date_range("1/1/2009", periods=5),
        "E": [0.0, 1, Timestamp("20100101"), "foo", 2.0],
    }

    scalars = {"timestamp": Timestamp("20130101"), "period": Period("2012", "M")}

    index = {
        "int": Index(np.arange(10)),
        "date": date_range("20130101", periods=10),
        "period": period_range("2013-01-01", freq="M", periods=10),
        "float": Index(np.arange(10, dtype=np.float64)),
        "uint": Index(np.arange(10, dtype=np.uint64)),
        "timedelta": timedelta_range("00:00:00", freq="30min", periods=10),
        "string": Index(["foo", "bar", "baz", "qux", "quux"], dtype="string"),
    }

    index["range"] = RangeIndex(10)

    index["interval"] = interval_range(0, periods=10)

    mi = {
        "reg2": MultiIndex.from_tuples(
            tuple(
                zip(
                    *[
                        ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
                        ["one", "two", "one", "two", "one", "two", "one", "two"],
                    ]
                )
            ),
            names=["first", "second"],
        )
    }

    series = {
        "float": Series(data["A"]),
        "int": Series(data["B"]),
        "mixed": Series(data["E"]),
        "ts": Series(
            np.arange(10).astype(np.int64), index=date_range("20130101", periods=10)
        ),
        "mi": Series(
            np.arange(5).astype(np.float64),
            index=MultiIndex.from_tuples(
                tuple(zip(*[[1, 1, 2, 2, 2], [3, 4, 3, 4, 5]])), names=["one", "two"]
            ),
        ),
        "dup": Series(np.arange(5).astype(np.float64), index=["A", "B", "C", "D", "A"]),
        "cat": Series(Categorical(["foo", "bar", "baz"])),
        "dt": Series(date_range("20130101", periods=5)),
        "dt_tz": Series(date_range("20130101", periods=5, tz="US/Eastern")),
        "period": Series([Period("2000Q1")] * 5),
        "string": Series(["foo", "bar", "baz", "qux", "quux"], dtype="string"),
    }

    mixed_dup_df = DataFrame(data)
    mixed_dup_df.columns = list("ABCDA")
    frame = {
        "float": DataFrame({"A": series["float"], "B": series["float"] + 1}),
        "int": DataFrame({"A": series["int"], "B": series["int"] + 1}),
        "mixed": DataFrame({k: data[k] for k in ["A", "B", "C", "D"]}),
        "mi": DataFrame(
            {"A": np.arange(5).astype(np.float64), "B": np.arange(5).astype(np.int64)},
            index=MultiIndex.from_tuples(
                tuple(
                    zip(
                        *[
                            ["bar", "bar", "baz", "baz", "baz"],
                            ["one", "two", "one", "two", "three"],
                        ]
                    )
                ),
                names=["first", "second"],
            ),
        ),
        "dup": DataFrame(
            np.arange(15).reshape(5, 3).astype(np.float64), columns=["A", "B", "A"]
        ),
        "cat_onecol": DataFrame({"A": Categorical(["foo", "bar"])}),
        "cat_and_float": DataFrame(
            {
                "A": Categorical(["foo", "bar", "baz"]),
                "B": np.arange(3).astype(np.int64),
            }
        ),
        "mixed_dup": mixed_dup_df,
        "dt_mixed_tzs": DataFrame(
            {
                "A": Timestamp("20130102", tz="US/Eastern"),
                "B": Timestamp("20130603", tz="CET"),
            },
            index=range(5),
        ),
        "dt_mixed2_tzs": DataFrame(
            {
                "A": Timestamp("20130102", tz="US/Eastern"),
                "B": Timestamp("20130603", tz="CET"),
                "C": Timestamp("20130603", tz="UTC"),
            },
            index=range(5),
        ),
        "string": DataFrame(
            {
                "A": Series(["foo", "bar", "baz", "qux", "quux"], dtype="string"),
                "B": Series(["one", "two", "one", "two", "three"], dtype="string"),
            }
        ),
    }

    cat = {
        "int8": Categorical(list("abcdefg")),
        "int16": Categorical(np.arange(1000)),
        "int32": Categorical(np.arange(10000)),
    }

    timestamp = {
        "normal": Timestamp("2011-01-01"),
        "nat": NaT,
        "tz": Timestamp("2011-01-01", tz="US/Eastern"),
    }

    off = {
        "DateOffset": DateOffset(years=1),
        "DateOffset_h_ns": DateOffset(hour=6, nanoseconds=5824),
        "BusinessDay": BusinessDay(offset=timedelta(seconds=9)),
        "BusinessHour": BusinessHour(normalize=True, n=6, end="15:14"),
        "CustomBusinessDay": CustomBusinessDay(weekmask="Mon Fri"),
        "SemiMonthBegin": SemiMonthBegin(day_of_month=9),
        "SemiMonthEnd": SemiMonthEnd(day_of_month=24),
        "MonthBegin": MonthBegin(1),
        "MonthEnd": MonthEnd(1),
        "QuarterBegin": QuarterBegin(1),
        "QuarterEnd": QuarterEnd(1),
        "Day": Day(1),
        "YearBegin": YearBegin(1),
        "YearEnd": YearEnd(1),
        "Week": Week(1),
        "Week_Tues": Week(2, normalize=False, weekday=1),
        "WeekOfMonth": WeekOfMonth(week=3, weekday=4),
        "LastWeekOfMonth": LastWeekOfMonth(n=1, weekday=3),
        "FY5253": FY5253(n=2, weekday=6, startingMonth=7, variation="last"),
        "Easter": Easter(),
        "Hour": Hour(1),
        "Minute": Minute(1),
    }

    return {
        "series": series,
        "frame": frame,
        "index": index,
        "scalars": scalars,
        "mi": mi,
        "sp_series": {"float": _create_sp_series(), "ts": _create_sp_tsseries()},
        "sp_frame": {"float": _create_sp_frame()},
        "cat": cat,
        "timestamp": timestamp,
        "offsets": off,
    }


def platform_name():
    return "_".join(
        [
            str(pandas.__version__),
            str(pl.machine()),
            str(pl.system().lower()),
            str(pl.python_version()),
        ]
    )


def write_legacy_pickles(output_dir):
    version = pandas.__version__

    print(
        "This script generates a storage file for the current arch, system, "
        "and python version"
    )
    print(f"  pandas version: {version}")
    print(f"  output dir    : {output_dir}")
    print("  storage format: pickle")

    pth = f"{platform_name()}.pickle"

    with open(os.path.join(output_dir, pth), "wb") as fh:
        pickle.dump(create_pickle_data(), fh, pickle.DEFAULT_PROTOCOL)

    print(f"created pickle file: {pth}")


def write_legacy_file():
    # force our cwd to be the first searched
    sys.path.insert(0, "")

    if not 3 <= len(sys.argv) <= 4:
        sys.exit(
            "Specify output directory and storage type: generate_legacy_"
            "storage_files.py <output_dir> <storage_type> "
        )

    output_dir = str(sys.argv[1])
    storage_type = str(sys.argv[2])

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    if storage_type == "pickle":
        write_legacy_pickles(output_dir=output_dir)
    else:
        sys.exit("storage_type must be one of {'pickle'}")


if __name__ == "__main__":
    write_legacy_file()
