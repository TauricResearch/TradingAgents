from datetime import datetime

import numpy as np
import pytest
import pytz

from pandas import (
    NA,
    DatetimeIndex,
    Index,
    NaT,
    Timestamp,
    date_range,
)
import pandas._testing as tm


class TestInsert:
    @pytest.mark.parametrize("null", [None, np.nan, np.datetime64("NaT"), NaT, NA])
    @pytest.mark.parametrize("tz", [None, "UTC", "US/Eastern"])
    def test_insert_nat(self, tz, null):
        # GH#16537, GH#18295 (test missing)

        idx = DatetimeIndex(["2017-01-01"], tz=tz)
        expected = DatetimeIndex(["NaT", "2017-01-01"], tz=tz)
        if tz is not None and isinstance(null, np.datetime64):
            expected = Index([null, idx[0]], dtype=object)

        res = idx.insert(0, null)
        tm.assert_index_equal(res, expected)

    @pytest.mark.parametrize("tz", [None, "UTC", "US/Eastern"])
    def test_insert_invalid_na(self, tz):
        idx = DatetimeIndex(["2017-01-01"], tz=tz)

        item = np.timedelta64("NaT")
        result = idx.insert(0, item)
        expected = Index([item] + list(idx), dtype=object)
        tm.assert_index_equal(result, expected)

    def test_insert_empty_preserves_freq(self, tz_naive_fixture):
        # GH#33573
        tz = tz_naive_fixture
        dti = DatetimeIndex([], tz=tz, freq="D")
        item = Timestamp("2017-04-05").tz_localize(tz)

        result = dti.insert(0, item)
        assert result.freq == dti.freq

        # But not when we insert an item that doesn't conform to freq
        dti = DatetimeIndex([], tz=tz, freq="W-THU")
        result = dti.insert(0, item)
        assert result.freq is None

    def test_insert(self, unit):
        idx = DatetimeIndex(
            ["2000-01-04", "2000-01-01", "2000-01-02"], name="idx"
        ).as_unit(unit)

        result = idx.insert(2, datetime(2000, 1, 5))
        exp = DatetimeIndex(
            ["2000-01-04", "2000-01-01", "2000-01-05", "2000-01-02"], name="idx"
        ).as_unit(unit)
        tm.assert_index_equal(result, exp)

        # insertion of non-datetime should coerce to object index
        result = idx.insert(1, "inserted")
        expected = Index(
            [
                datetime(2000, 1, 4),
                "inserted",
                datetime(2000, 1, 1),
                datetime(2000, 1, 2),
            ],
            name="idx",
        )
        assert not isinstance(result, DatetimeIndex)
        tm.assert_index_equal(result, expected)
        assert result.name == expected.name

    def test_insert2(self, unit):
        idx = date_range("1/1/2000", periods=3, freq="ME", name="idx", unit=unit)

        # preserve freq
        expected_0 = DatetimeIndex(
            ["1999-12-31", "2000-01-31", "2000-02-29", "2000-03-31"],
            name="idx",
            freq="ME",
        ).as_unit(unit)
        expected_3 = DatetimeIndex(
            ["2000-01-31", "2000-02-29", "2000-03-31", "2000-04-30"],
            name="idx",
            freq="ME",
        ).as_unit(unit)

        # reset freq to None
        expected_1_nofreq = DatetimeIndex(
            ["2000-01-31", "2000-01-31", "2000-02-29", "2000-03-31"],
            name="idx",
            freq=None,
        ).as_unit(unit)
        expected_3_nofreq = DatetimeIndex(
            ["2000-01-31", "2000-02-29", "2000-03-31", "2000-01-02"],
            name="idx",
            freq=None,
        ).as_unit(unit)

        cases = [
            (0, datetime(1999, 12, 31), expected_0),
            (-3, datetime(1999, 12, 31), expected_0),
            (3, datetime(2000, 4, 30), expected_3),
            (1, datetime(2000, 1, 31), expected_1_nofreq),
            (3, datetime(2000, 1, 2), expected_3_nofreq),
        ]

        for n, d, expected in cases:
            result = idx.insert(n, d)
            tm.assert_index_equal(result, expected)
            assert result.name == expected.name
            assert result.freq == expected.freq

    def test_insert3(self, unit):
        idx = date_range("1/1/2000", periods=3, freq="ME", name="idx", unit=unit)

        # reset freq to None
        result = idx.insert(3, datetime(2000, 1, 2))
        expected = DatetimeIndex(
            ["2000-01-31", "2000-02-29", "2000-03-31", "2000-01-02"],
            name="idx",
            freq=None,
        ).as_unit(unit)
        tm.assert_index_equal(result, expected)
        assert result.name == expected.name
        assert result.freq is None

    def test_insert4(self, unit):
        for tz in ["US/Pacific", "Asia/Singapore"]:
            idx = date_range(
                "1/1/2000 09:00", periods=6, freq="h", tz=tz, name="idx", unit=unit
            )
            # preserve freq
            expected = date_range(
                "1/1/2000 09:00", periods=7, freq="h", tz=tz, name="idx", unit=unit
            )
            for d in [
                Timestamp("2000-01-01 15:00", tz=tz),
                pytz.timezone(tz).localize(datetime(2000, 1, 1, 15)),
            ]:
                result = idx.insert(6, d)
                tm.assert_index_equal(result, expected)
                assert result.name == expected.name
                assert result.freq == expected.freq
                assert result.tz == expected.tz

            expected = DatetimeIndex(
                [
                    "2000-01-01 09:00",
                    "2000-01-01 10:00",
                    "2000-01-01 11:00",
                    "2000-01-01 12:00",
                    "2000-01-01 13:00",
                    "2000-01-01 14:00",
                    "2000-01-01 10:00",
                ],
                name="idx",
                tz=tz,
                freq=None,
            ).as_unit(unit)
            # reset freq to None
            for d in [
                Timestamp("2000-01-01 10:00", tz=tz),
                pytz.timezone(tz).localize(datetime(2000, 1, 1, 10)),
            ]:
                result = idx.insert(6, d)
                tm.assert_index_equal(result, expected)
                assert result.name == expected.name
                assert result.tz == expected.tz
                assert result.freq is None

    # TODO: also changes DataFrame.__setitem__ with expansion
    def test_insert_mismatched_tzawareness(self):
        # see GH#7299
        idx = date_range("1/1/2000", periods=3, freq="D", tz="Asia/Tokyo", name="idx")

        # mismatched tz-awareness
        item = Timestamp("2000-01-04")
        result = idx.insert(3, item)
        expected = Index(
            list(idx[:3]) + [item] + list(idx[3:]), dtype=object, name="idx"
        )
        tm.assert_index_equal(result, expected)

        # mismatched tz-awareness
        item = datetime(2000, 1, 4)
        result = idx.insert(3, item)
        expected = Index(
            list(idx[:3]) + [item] + list(idx[3:]), dtype=object, name="idx"
        )
        tm.assert_index_equal(result, expected)

    # TODO: also changes DataFrame.__setitem__ with expansion
    def test_insert_mismatched_tz(self):
        # see GH#7299
        # pre-2.0 with mismatched tzs we would cast to object
        idx = date_range("1/1/2000", periods=3, freq="D", tz="Asia/Tokyo", name="idx")

        # mismatched tz -> cast to object (could reasonably cast to same tz or UTC)
        item = Timestamp("2000-01-04", tz="US/Eastern")
        result = idx.insert(3, item)
        expected = Index(
            list(idx[:3]) + [item.tz_convert(idx.tz)] + list(idx[3:]),
            name="idx",
        )
        assert expected.dtype == idx.dtype
        tm.assert_index_equal(result, expected)

        item = datetime(2000, 1, 4, tzinfo=pytz.timezone("US/Eastern"))
        result = idx.insert(3, item)
        expected = Index(
            list(idx[:3]) + [item.astimezone(idx.tzinfo)] + list(idx[3:]),
            name="idx",
        )
        assert expected.dtype == idx.dtype
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "item", [0, np.int64(0), np.float64(0), np.array(0), np.timedelta64(456)]
    )
    def test_insert_mismatched_types_raises(self, tz_aware_fixture, item):
        # GH#33703 dont cast these to dt64
        tz = tz_aware_fixture
        dti = date_range("2019-11-04", periods=9, freq="-1D", name=9, tz=tz)

        result = dti.insert(1, item)

        if isinstance(item, np.ndarray):
            assert item.item() == 0
            expected = Index([dti[0], 0] + list(dti[1:]), dtype=object, name=9)
        else:
            expected = Index([dti[0], item] + list(dti[1:]), dtype=object, name=9)

        tm.assert_index_equal(result, expected)

    def test_insert_castable_str(self, tz_aware_fixture):
        # GH#33703
        tz = tz_aware_fixture
        dti = date_range("2019-11-04", periods=3, freq="-1D", name=9, tz=tz)

        value = "2019-11-05"
        result = dti.insert(0, value)

        ts = Timestamp(value).tz_localize(tz)
        expected = DatetimeIndex([ts] + list(dti), dtype=dti.dtype, name=9)
        tm.assert_index_equal(result, expected)

    def test_insert_non_castable_str(self, tz_aware_fixture):
        # GH#33703
        tz = tz_aware_fixture
        dti = date_range("2019-11-04", periods=3, freq="-1D", name=9, tz=tz)

        value = "foo"
        result = dti.insert(0, value)

        expected = Index(["foo"] + list(dti), dtype=object, name=9)
        tm.assert_index_equal(result, expected)
