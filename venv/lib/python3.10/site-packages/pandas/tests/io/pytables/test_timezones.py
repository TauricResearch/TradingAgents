from datetime import (
    date,
    timedelta,
)

import numpy as np
import pytest

from pandas._libs.tslibs.timezones import maybe_get_tz
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    Timestamp,
    date_range,
)
import pandas._testing as tm
from pandas.tests.io.pytables.common import (
    _maybe_remove,
    ensure_clean_store,
)


def _compare_with_tz(a, b):
    tm.assert_frame_equal(a, b)

    # compare the zones on each element
    for c in a.columns:
        for i in a.index:
            a_e = a.loc[i, c]
            b_e = b.loc[i, c]
            if not (a_e == b_e and a_e.tz == b_e.tz):
                raise AssertionError(f"invalid tz comparison [{a_e}] [{b_e}]")


# use maybe_get_tz instead of dateutil.tz.gettz to handle the windows
# filename issues.
gettz_dateutil = lambda x: maybe_get_tz("dateutil/" + x)
gettz_pytz = lambda x: x


@pytest.mark.parametrize("gettz", [gettz_dateutil, gettz_pytz])
def test_append_with_timezones(setup_path, gettz):
    # as columns

    # Single-tzinfo, no DST transition
    df_est = DataFrame(
        {
            "A": [
                Timestamp("20130102 2:00:00", tz=gettz("US/Eastern")).as_unit("ns")
                + timedelta(hours=1) * i
                for i in range(5)
            ]
        }
    )

    # frame with all columns having same tzinfo, but different sides
    #  of DST transition
    df_crosses_dst = DataFrame(
        {
            "A": Timestamp("20130102", tz=gettz("US/Eastern")).as_unit("ns"),
            "B": Timestamp("20130603", tz=gettz("US/Eastern")).as_unit("ns"),
        },
        index=range(5),
    )

    df_mixed_tz = DataFrame(
        {
            "A": Timestamp("20130102", tz=gettz("US/Eastern")).as_unit("ns"),
            "B": Timestamp("20130102", tz=gettz("EET")).as_unit("ns"),
        },
        index=range(5),
    )

    df_different_tz = DataFrame(
        {
            "A": Timestamp("20130102", tz=gettz("US/Eastern")).as_unit("ns"),
            "B": Timestamp("20130102", tz=gettz("CET")).as_unit("ns"),
        },
        index=range(5),
    )

    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df_tz")
        store.append("df_tz", df_est, data_columns=["A"])
        result = store["df_tz"]
        _compare_with_tz(result, df_est)
        tm.assert_frame_equal(result, df_est)

        # select with tz aware
        expected = df_est[df_est.A >= df_est.A[3]]
        result = store.select("df_tz", where="A>=df_est.A[3]")
        _compare_with_tz(result, expected)

        # ensure we include dates in DST and STD time here.
        _maybe_remove(store, "df_tz")
        store.append("df_tz", df_crosses_dst)
        result = store["df_tz"]
        _compare_with_tz(result, df_crosses_dst)
        tm.assert_frame_equal(result, df_crosses_dst)

        msg = (
            r"invalid info for \[values_block_1\] for \[tz\], "
            r"existing_value \[(dateutil/.*)?(US/Eastern|America/New_York)\] "
            r"conflicts with new value \[(dateutil/.*)?EET\]"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df_tz", df_mixed_tz)

        # this is ok
        _maybe_remove(store, "df_tz")
        store.append("df_tz", df_mixed_tz, data_columns=["A", "B"])
        result = store["df_tz"]
        _compare_with_tz(result, df_mixed_tz)
        tm.assert_frame_equal(result, df_mixed_tz)

        # can't append with diff timezone
        msg = (
            r"invalid info for \[B\] for \[tz\], "
            r"existing_value \[(dateutil/.*)?EET\] "
            r"conflicts with new value \[(dateutil/.*)?CET\]"
        )
        with pytest.raises(ValueError, match=msg):
            store.append("df_tz", df_different_tz)


@pytest.mark.parametrize("gettz", [gettz_dateutil, gettz_pytz])
def test_append_with_timezones_as_index(setup_path, gettz):
    # GH#4098 example

    dti = date_range("2000-1-1", periods=3, freq="h", tz=gettz("US/Eastern"))
    dti = dti._with_freq(None)  # freq doesn't round-trip

    df = DataFrame({"A": Series(range(3), index=dti)})

    with ensure_clean_store(setup_path) as store:
        _maybe_remove(store, "df")
        store.put("df", df)
        result = store.select("df")
        tm.assert_frame_equal(result, df)

        _maybe_remove(store, "df")
        store.append("df", df)
        result = store.select("df")
        tm.assert_frame_equal(result, df)


def test_roundtrip_tz_aware_index(setup_path, unit):
    # GH 17618
    ts = Timestamp("2000-01-01 01:00:00", tz="US/Eastern")
    dti = DatetimeIndex([ts]).as_unit(unit)
    df = DataFrame(data=[0], index=dti)

    with ensure_clean_store(setup_path) as store:
        store.put("frame", df, format="fixed")
        recons = store["frame"]
        tm.assert_frame_equal(recons, df)

    value = recons.index[0]._value
    denom = {"ns": 1, "us": 1000, "ms": 10**6, "s": 10**9}[unit]
    assert value == 946706400000000000 // denom


def test_store_index_name_with_tz(setup_path):
    # GH 13884
    df = DataFrame({"A": [1, 2]})
    df.index = DatetimeIndex([1234567890123456787, 1234567890123456788])
    df.index = df.index.tz_localize("UTC")
    df.index.name = "foo"

    with ensure_clean_store(setup_path) as store:
        store.put("frame", df, format="table")
        recons = store["frame"]
        tm.assert_frame_equal(recons, df)


def test_tseries_select_index_column(setup_path):
    # GH7777
    # selecting a UTC datetimeindex column did
    # not preserve UTC tzinfo set before storing

    # check that no tz still works
    rng = date_range("1/1/2000", "1/30/2000")
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((len(rng), 4)), index=rng
    )

    with ensure_clean_store(setup_path) as store:
        store.append("frame", frame)
        result = store.select_column("frame", "index")
        assert rng.tz == DatetimeIndex(result.values).tz

    # check utc
    rng = date_range("1/1/2000", "1/30/2000", tz="UTC")
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((len(rng), 4)), index=rng
    )

    with ensure_clean_store(setup_path) as store:
        store.append("frame", frame)
        result = store.select_column("frame", "index")
        assert rng.tz == result.dt.tz

    # double check non-utc
    rng = date_range("1/1/2000", "1/30/2000", tz="US/Eastern")
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((len(rng), 4)), index=rng
    )

    with ensure_clean_store(setup_path) as store:
        store.append("frame", frame)
        result = store.select_column("frame", "index")
        assert rng.tz == result.dt.tz


def test_timezones_fixed_format_frame_non_empty(setup_path):
    with ensure_clean_store(setup_path) as store:
        # index
        rng = date_range("1/1/2000", "1/30/2000", tz="US/Eastern")
        rng = rng._with_freq(None)  # freq doesn't round-trip
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(rng), 4)), index=rng
        )
        store["df"] = df
        result = store["df"]
        tm.assert_frame_equal(result, df)

        # as data
        # GH11411
        _maybe_remove(store, "df")
        df = DataFrame(
            {
                "A": rng,
                "B": rng.tz_convert("UTC").tz_localize(None),
                "C": rng.tz_convert("CET"),
                "D": range(len(rng)),
            },
            index=rng,
        )
        store["df"] = df
        result = store["df"]
        tm.assert_frame_equal(result, df)


def test_timezones_fixed_format_empty(setup_path, tz_aware_fixture, frame_or_series):
    # GH 20594

    dtype = pd.DatetimeTZDtype(tz=tz_aware_fixture)

    obj = Series(dtype=dtype, name="A")
    if frame_or_series is DataFrame:
        obj = obj.to_frame()

    with ensure_clean_store(setup_path) as store:
        store["obj"] = obj
        result = store["obj"]
        tm.assert_equal(result, obj)


def test_timezones_fixed_format_series_nonempty(setup_path, tz_aware_fixture):
    # GH 20594

    dtype = pd.DatetimeTZDtype(tz=tz_aware_fixture)

    with ensure_clean_store(setup_path) as store:
        s = Series([0], dtype=dtype)
        store["s"] = s
        result = store["s"]
        tm.assert_series_equal(result, s)


def test_fixed_offset_tz(setup_path):
    rng = date_range("1/1/2000 00:00:00-07:00", "1/30/2000 00:00:00-07:00")
    frame = DataFrame(
        np.random.default_rng(2).standard_normal((len(rng), 4)), index=rng
    )

    with ensure_clean_store(setup_path) as store:
        store["frame"] = frame
        recons = store["frame"]
        tm.assert_index_equal(recons.index, rng)
        assert rng.tz == recons.index.tz


@td.skip_if_windows
def test_store_timezone(setup_path):
    # GH2852
    # issue storing datetime.date with a timezone as it resets when read
    # back in a new timezone

    # original method
    with ensure_clean_store(setup_path) as store:
        today = date(2013, 9, 10)
        df = DataFrame([1, 2, 3], index=[today, today, today])
        store["obj1"] = df
        result = store["obj1"]
        tm.assert_frame_equal(result, df)

    # with tz setting
    with ensure_clean_store(setup_path) as store:
        with tm.set_timezone("EST5EDT"):
            today = date(2013, 9, 10)
            df = DataFrame([1, 2, 3], index=[today, today, today])
            store["obj1"] = df

        with tm.set_timezone("CST6CDT"):
            result = store["obj1"]

        tm.assert_frame_equal(result, df)


def test_legacy_datetimetz_object(datapath):
    # legacy from < 0.17.0
    # 8260
    expected = DataFrame(
        {
            "A": Timestamp("20130102", tz="US/Eastern").as_unit("ns"),
            "B": Timestamp("20130603", tz="CET").as_unit("ns"),
        },
        index=range(5),
    )
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf", "datetimetz_object.h5"), mode="r"
    ) as store:
        result = store["df"]
        tm.assert_frame_equal(result, expected)


def test_dst_transitions(setup_path):
    # make sure we are not failing on transitions
    with ensure_clean_store(setup_path) as store:
        times = date_range(
            "2013-10-26 23:00",
            "2013-10-27 01:00",
            tz="Europe/London",
            freq="h",
            ambiguous="infer",
        )
        times = times._with_freq(None)  # freq doesn't round-trip

        for i in [times, times + pd.Timedelta("10min")]:
            _maybe_remove(store, "df")
            df = DataFrame({"A": range(len(i)), "B": i}, index=i)
            store.append("df", df)
            result = store.select("df")
            tm.assert_frame_equal(result, df)


def test_read_with_where_tz_aware_index(tmp_path, setup_path):
    # GH 11926
    periods = 10
    dts = date_range("20151201", periods=periods, freq="D", tz="UTC")
    mi = pd.MultiIndex.from_arrays([dts, range(periods)], names=["DATE", "NO"])
    expected = DataFrame({"MYCOL": 0}, index=mi)

    key = "mykey"
    path = tmp_path / setup_path
    with pd.HDFStore(path) as store:
        store.append(key, expected, format="table", append=True)
    result = pd.read_hdf(path, key, where="DATE > 20151130")
    tm.assert_frame_equal(result, expected)


def test_py2_created_with_datetimez(datapath):
    # The test HDF5 file was created in Python 2, but could not be read in
    # Python 3.
    #
    # GH26443
    index = DatetimeIndex(["2019-01-01T18:00"], dtype="M8[ns, America/New_York]")
    expected = DataFrame({"data": 123}, index=index)
    with ensure_clean_store(
        datapath("io", "data", "legacy_hdf", "gh26443.h5"), mode="r"
    ) as store:
        result = store["key"]
        tm.assert_frame_equal(result, expected)
