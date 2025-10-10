from datetime import (
    datetime,
    timedelta,
)
import itertools

import numpy as np
import pytest

from pandas.compat import WARNING_CHECK_DISABLED
from pandas.errors import PerformanceWarning
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Series,
    Timestamp,
    date_range,
    option_context,
)
import pandas._testing as tm
from pandas.core.internals.blocks import NumpyBlock

# Segregated collection of methods that require the BlockManager internal data
# structure


# TODO(ArrayManager) check which of those tests need to be rewritten to test the
# equivalent for ArrayManager
pytestmark = td.skip_array_manager_invalid_test


class TestDataFrameBlockInternals:
    def test_setitem_invalidates_datetime_index_freq(self):
        # GH#24096 altering a datetime64tz column inplace invalidates the
        #  `freq` attribute on the underlying DatetimeIndex

        dti = date_range("20130101", periods=3, tz="US/Eastern")
        ts = dti[1]

        df = DataFrame({"B": dti})
        assert df["B"]._values.freq is None

        df.iloc[1, 0] = pd.NaT
        assert df["B"]._values.freq is None

        # check that the DatetimeIndex was not altered in place
        assert dti.freq == "D"
        assert dti[1] == ts

    def test_cast_internals(self, float_frame):
        msg = "Passing a BlockManager to DataFrame"
        with tm.assert_produces_warning(
            DeprecationWarning, match=msg, check_stacklevel=False
        ):
            casted = DataFrame(float_frame._mgr, dtype=int)
        expected = DataFrame(float_frame._series, dtype=int)
        tm.assert_frame_equal(casted, expected)

        with tm.assert_produces_warning(
            DeprecationWarning, match=msg, check_stacklevel=False
        ):
            casted = DataFrame(float_frame._mgr, dtype=np.int32)
        expected = DataFrame(float_frame._series, dtype=np.int32)
        tm.assert_frame_equal(casted, expected)

    def test_consolidate(self, float_frame):
        float_frame["E"] = 7.0
        consolidated = float_frame._consolidate()
        assert len(consolidated._mgr.blocks) == 1

        # Ensure copy, do I want this?
        recons = consolidated._consolidate()
        assert recons is not consolidated
        tm.assert_frame_equal(recons, consolidated)

        float_frame["F"] = 8.0
        assert len(float_frame._mgr.blocks) == 3

        return_value = float_frame._consolidate_inplace()
        assert return_value is None
        assert len(float_frame._mgr.blocks) == 1

    def test_consolidate_inplace(self, float_frame):
        # triggers in-place consolidation
        for letter in range(ord("A"), ord("Z")):
            float_frame[chr(letter)] = chr(letter)

    def test_modify_values(self, float_frame, using_copy_on_write):
        if using_copy_on_write:
            with pytest.raises(ValueError, match="read-only"):
                float_frame.values[5] = 5
            assert (float_frame.values[5] != 5).all()
            return

        float_frame.values[5] = 5
        assert (float_frame.values[5] == 5).all()

        # unconsolidated
        float_frame["E"] = 7.0
        col = float_frame["E"]
        float_frame.values[6] = 6
        # as of 2.0 .values does not consolidate, so subsequent calls to .values
        #  does not share data
        assert not (float_frame.values[6] == 6).all()

        assert (col == 7).all()

    def test_boolean_set_uncons(self, float_frame):
        float_frame["E"] = 7.0

        expected = float_frame.values.copy()
        expected[expected > 1] = 2

        float_frame[float_frame > 1] = 2
        tm.assert_almost_equal(expected, float_frame.values)

    def test_constructor_with_convert(self):
        # this is actually mostly a test of lib.maybe_convert_objects
        # #2845
        df = DataFrame({"A": [2**63 - 1]})
        result = df["A"]
        expected = Series(np.asarray([2**63 - 1], np.int64), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [2**63]})
        result = df["A"]
        expected = Series(np.asarray([2**63], np.uint64), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [datetime(2005, 1, 1), True]})
        result = df["A"]
        expected = Series(
            np.asarray([datetime(2005, 1, 1), True], np.object_), name="A"
        )
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [None, 1]})
        result = df["A"]
        expected = Series(np.asarray([np.nan, 1], np.float64), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [1.0, 2]})
        result = df["A"]
        expected = Series(np.asarray([1.0, 2], np.float64), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [1.0 + 2.0j, 3]})
        result = df["A"]
        expected = Series(np.asarray([1.0 + 2.0j, 3], np.complex128), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [1.0 + 2.0j, 3.0]})
        result = df["A"]
        expected = Series(np.asarray([1.0 + 2.0j, 3.0], np.complex128), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [1.0 + 2.0j, True]})
        result = df["A"]
        expected = Series(np.asarray([1.0 + 2.0j, True], np.object_), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [1.0, None]})
        result = df["A"]
        expected = Series(np.asarray([1.0, np.nan], np.float64), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [1.0 + 2.0j, None]})
        result = df["A"]
        expected = Series(np.asarray([1.0 + 2.0j, np.nan], np.complex128), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [2.0, 1, True, None]})
        result = df["A"]
        expected = Series(np.asarray([2.0, 1, True, None], np.object_), name="A")
        tm.assert_series_equal(result, expected)

        df = DataFrame({"A": [2.0, 1, datetime(2006, 1, 1), None]})
        result = df["A"]
        expected = Series(
            np.asarray([2.0, 1, datetime(2006, 1, 1), None], np.object_), name="A"
        )
        tm.assert_series_equal(result, expected)

    def test_construction_with_mixed(self, float_string_frame, using_infer_string):
        # mixed-type frames
        float_string_frame["datetime"] = datetime.now()
        float_string_frame["timedelta"] = timedelta(days=1, seconds=1)
        assert float_string_frame["datetime"].dtype == "M8[us]"
        assert float_string_frame["timedelta"].dtype == "m8[us]"
        result = float_string_frame.dtypes
        expected = Series(
            [np.dtype("float64")] * 4
            + [
                np.dtype("object")
                if not using_infer_string
                else pd.StringDtype(na_value=np.nan),
                np.dtype("datetime64[us]"),
                np.dtype("timedelta64[us]"),
            ],
            index=list("ABCD") + ["foo", "datetime", "timedelta"],
        )
        tm.assert_series_equal(result, expected)

    def test_construction_with_conversions(self):
        # convert from a numpy array of non-ns timedelta64; as of 2.0 this does
        #  *not* convert
        arr = np.array([1, 2, 3], dtype="timedelta64[s]")
        df = DataFrame({"A": arr})
        expected = DataFrame(
            {"A": pd.timedelta_range("00:00:01", periods=3, freq="s")}, index=range(3)
        )
        tm.assert_numpy_array_equal(df["A"].to_numpy(), arr)

        expected = DataFrame(
            {
                "dt1": Timestamp("20130101"),
                "dt2": date_range("20130101", periods=3).astype("M8[s]"),
                # 'dt3' : date_range('20130101 00:00:01',periods=3,freq='s'),
                # FIXME: don't leave commented-out
            },
            index=range(3),
        )
        assert expected.dtypes["dt1"] == "M8[s]"
        assert expected.dtypes["dt2"] == "M8[s]"

        dt1 = np.datetime64("2013-01-01")
        dt2 = np.array(
            ["2013-01-01", "2013-01-02", "2013-01-03"], dtype="datetime64[D]"
        )
        df = DataFrame({"dt1": dt1, "dt2": dt2})

        # df['dt3'] = np.array(['2013-01-01 00:00:01','2013-01-01
        # 00:00:02','2013-01-01 00:00:03'],dtype='datetime64[s]')
        # FIXME: don't leave commented-out

        tm.assert_frame_equal(df, expected)

    def test_constructor_compound_dtypes(self):
        # GH 5191
        # compound dtypes should raise not-implementederror

        def f(dtype):
            data = list(itertools.repeat((datetime(2001, 1, 1), "aa", 20), 9))
            return DataFrame(data=data, columns=["A", "B", "C"], dtype=dtype)

        msg = "compound dtypes are not implemented in the DataFrame constructor"
        with pytest.raises(NotImplementedError, match=msg):
            f([("A", "datetime64[h]"), ("B", "str"), ("C", "int32")])

        # pre-2.0 these used to work (though results may be unexpected)
        with pytest.raises(TypeError, match="argument must be"):
            f("int64")
        with pytest.raises(TypeError, match="argument must be"):
            f("float64")

        # 10822
        msg = "^Unknown datetime string format, unable to parse: aa, at position 0$"
        with pytest.raises(ValueError, match=msg):
            f("M8[ns]")

    def test_pickle(self, float_string_frame, timezone_frame):
        empty_frame = DataFrame()

        unpickled = tm.round_trip_pickle(float_string_frame)
        tm.assert_frame_equal(float_string_frame, unpickled)

        # buglet
        float_string_frame._mgr.ndim

        # empty
        unpickled = tm.round_trip_pickle(empty_frame)
        repr(unpickled)

        # tz frame
        unpickled = tm.round_trip_pickle(timezone_frame)
        tm.assert_frame_equal(timezone_frame, unpickled)

    def test_consolidate_datetime64(self):
        # numpy vstack bug

        df = DataFrame(
            {
                "starting": pd.to_datetime(
                    [
                        "2012-06-21 00:00",
                        "2012-06-23 07:00",
                        "2012-06-23 16:30",
                        "2012-06-25 08:00",
                        "2012-06-26 12:00",
                    ]
                ),
                "ending": pd.to_datetime(
                    [
                        "2012-06-23 07:00",
                        "2012-06-23 16:30",
                        "2012-06-25 08:00",
                        "2012-06-26 12:00",
                        "2012-06-27 08:00",
                    ]
                ),
                "measure": [77, 65, 77, 0, 77],
            }
        )

        ser_starting = df.starting
        ser_starting.index = ser_starting.values
        ser_starting = ser_starting.tz_localize("US/Eastern")
        ser_starting = ser_starting.tz_convert("UTC")
        ser_starting.index.name = "starting"

        ser_ending = df.ending
        ser_ending.index = ser_ending.values
        ser_ending = ser_ending.tz_localize("US/Eastern")
        ser_ending = ser_ending.tz_convert("UTC")
        ser_ending.index.name = "ending"

        df.starting = ser_starting.index
        df.ending = ser_ending.index

        tm.assert_index_equal(pd.DatetimeIndex(df.starting), ser_starting.index)
        tm.assert_index_equal(pd.DatetimeIndex(df.ending), ser_ending.index)

    def test_is_mixed_type(self, float_frame, float_string_frame):
        assert not float_frame._is_mixed_type
        assert float_string_frame._is_mixed_type

    def test_stale_cached_series_bug_473(self, using_copy_on_write, warn_copy_on_write):
        # this is chained, but ok
        with option_context("chained_assignment", None):
            Y = DataFrame(
                np.random.default_rng(2).random((4, 4)),
                index=("a", "b", "c", "d"),
                columns=("e", "f", "g", "h"),
            )
            repr(Y)
            Y["e"] = Y["e"].astype("object")
            with tm.raises_chained_assignment_error():
                Y["g"]["c"] = np.nan
            repr(Y)
            Y.sum()
            Y["g"].sum()
            if using_copy_on_write:
                assert not pd.isna(Y["g"]["c"])
            else:
                assert pd.isna(Y["g"]["c"])

    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    def test_strange_column_corruption_issue(self, using_copy_on_write):
        # TODO(wesm): Unclear how exactly this is related to internal matters
        df = DataFrame(index=[0, 1])
        df[0] = np.nan
        wasCol = {}

        with tm.assert_produces_warning(
            PerformanceWarning, raise_on_extra_warnings=False
        ):
            for i, dt in enumerate(df.index):
                for col in range(100, 200):
                    if col not in wasCol:
                        wasCol[col] = 1
                        df[col] = np.nan
                    if using_copy_on_write:
                        df.loc[dt, col] = i
                    else:
                        df[col][dt] = i

        myid = 100

        first = len(df.loc[pd.isna(df[myid]), [myid]])
        second = len(df.loc[pd.isna(df[myid]), [myid]])
        assert first == second == 0

    def test_constructor_no_pandas_array(self):
        # Ensure that NumpyExtensionArray isn't allowed inside Series
        # See https://github.com/pandas-dev/pandas/issues/23995 for more.
        arr = Series([1, 2, 3]).array
        result = DataFrame({"A": arr})
        expected = DataFrame({"A": [1, 2, 3]})
        tm.assert_frame_equal(result, expected)
        assert isinstance(result._mgr.blocks[0], NumpyBlock)
        assert result._mgr.blocks[0].is_numeric

    def test_add_column_with_pandas_array(self):
        # GH 26390
        df = DataFrame({"a": [1, 2, 3, 4], "b": ["a", "b", "c", "d"]})
        df["c"] = pd.arrays.NumpyExtensionArray(np.array([1, 2, None, 3], dtype=object))
        df2 = DataFrame(
            {
                "a": [1, 2, 3, 4],
                "b": ["a", "b", "c", "d"],
                "c": pd.arrays.NumpyExtensionArray(
                    np.array([1, 2, None, 3], dtype=object)
                ),
            }
        )
        assert type(df["c"]._mgr.blocks[0]) == NumpyBlock
        assert df["c"]._mgr.blocks[0].is_object
        assert type(df2["c"]._mgr.blocks[0]) == NumpyBlock
        assert df2["c"]._mgr.blocks[0].is_object
        tm.assert_frame_equal(df, df2)


def test_update_inplace_sets_valid_block_values(using_copy_on_write):
    # https://github.com/pandas-dev/pandas/issues/33457
    df = DataFrame({"a": Series([1, 2, None], dtype="category")})

    # inplace update of a single column
    if using_copy_on_write:
        with tm.raises_chained_assignment_error():
            df["a"].fillna(1, inplace=True)
    else:
        with tm.assert_produces_warning(
            FutureWarning if not WARNING_CHECK_DISABLED else None,
            match="inplace method",
        ):
            df["a"].fillna(1, inplace=True)

    # check we haven't put a Series into any block.values
    assert isinstance(df._mgr.blocks[0].values, Categorical)

    if not using_copy_on_write:
        # smoketest for OP bug from GH#35731
        assert df.isnull().sum().sum() == 0


def test_nonconsolidated_item_cache_take():
    # https://github.com/pandas-dev/pandas/issues/35521

    # create non-consolidated dataframe with object dtype columns
    df = DataFrame(
        {
            "col1": Series(["a"], dtype=object),
        }
    )
    df["col2"] = Series([0], dtype=object)
    assert not df._mgr.is_consolidated()

    # access column (item cache)
    df["col1"] == "A"
    # take operation
    # (regression was that this consolidated but didn't reset item cache,
    # resulting in an invalid cache and the .at operation not working properly)
    df[df["col2"] == 0]

    # now setting value should update actual dataframe
    df.at[0, "col1"] = "A"

    expected = DataFrame({"col1": ["A"], "col2": [0]}, dtype=object)
    tm.assert_frame_equal(df, expected)
    assert df.at[0, "col1"] == "A"
