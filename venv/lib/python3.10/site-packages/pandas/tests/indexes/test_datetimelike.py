""" generic datetimelike tests """

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm


class TestDatetimeLike:
    @pytest.fixture(
        params=[
            pd.period_range("20130101", periods=5, freq="D"),
            pd.TimedeltaIndex(
                [
                    "0 days 01:00:00",
                    "1 days 01:00:00",
                    "2 days 01:00:00",
                    "3 days 01:00:00",
                    "4 days 01:00:00",
                ],
                dtype="timedelta64[ns]",
                freq="D",
            ),
            pd.DatetimeIndex(
                ["2013-01-01", "2013-01-02", "2013-01-03", "2013-01-04", "2013-01-05"],
                dtype="datetime64[ns]",
                freq="D",
            ),
        ]
    )
    def simple_index(self, request):
        return request.param

    def test_isin(self, simple_index):
        index = simple_index[:4]
        result = index.isin(index)
        assert result.all()

        result = index.isin(list(index))
        assert result.all()

        result = index.isin([index[2], 5])
        expected = np.array([False, False, True, False])
        tm.assert_numpy_array_equal(result, expected)

    def test_argsort_matches_array(self, simple_index):
        idx = simple_index
        idx = idx.insert(1, pd.NaT)

        result = idx.argsort()
        expected = idx._data.argsort()
        tm.assert_numpy_array_equal(result, expected)

    def test_can_hold_identifiers(self, simple_index):
        idx = simple_index
        key = idx[0]
        assert idx._can_hold_identifiers_and_holds_name(key) is False

    def test_shift_identity(self, simple_index):
        idx = simple_index
        tm.assert_index_equal(idx, idx.shift(0))

    def test_shift_empty(self, simple_index):
        # GH#14811
        idx = simple_index[:0]
        tm.assert_index_equal(idx, idx.shift(1))

    def test_str(self, simple_index):
        # test the string repr
        idx = simple_index.copy()
        idx.name = "foo"
        assert f"length={len(idx)}" not in str(idx)
        assert "'foo'" in str(idx)
        assert type(idx).__name__ in str(idx)

        if hasattr(idx, "tz"):
            if idx.tz is not None:
                assert idx.tz in str(idx)
        if isinstance(idx, pd.PeriodIndex):
            assert f"dtype='period[{idx.freqstr}]'" in str(idx)
        else:
            assert f"freq='{idx.freqstr}'" in str(idx)

    def test_view(self, simple_index):
        idx = simple_index

        idx_view = idx.view("i8")
        result = type(simple_index)(idx)
        tm.assert_index_equal(result, idx)

        msg = "Passing a type in .*Index.view is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            idx_view = idx.view(type(simple_index))
        result = type(simple_index)(idx)
        tm.assert_index_equal(result, idx_view)

    def test_map_callable(self, simple_index):
        index = simple_index
        expected = index + index.freq
        result = index.map(lambda x: x + index.freq)
        tm.assert_index_equal(result, expected)

        # map to NaT
        result = index.map(lambda x: pd.NaT if x == index[0] else x)
        expected = pd.Index([pd.NaT] + index[1:].tolist())
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize(
        "mapper",
        [
            lambda values, index: {i: e for e, i in zip(values, index)},
            lambda values, index: pd.Series(values, index, dtype=object),
        ],
    )
    @pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
    def test_map_dictlike(self, mapper, simple_index):
        index = simple_index
        expected = index + index.freq

        # don't compare the freqs
        if isinstance(expected, (pd.DatetimeIndex, pd.TimedeltaIndex)):
            expected = expected._with_freq(None)

        result = index.map(mapper(expected, index))
        tm.assert_index_equal(result, expected)

        expected = pd.Index([pd.NaT] + index[1:].tolist())
        result = index.map(mapper(expected, index))
        tm.assert_index_equal(result, expected)

        # empty map; these map to np.nan because we cannot know
        # to re-infer things
        expected = pd.Index([np.nan] * len(index))
        result = index.map(mapper([], []))
        tm.assert_index_equal(result, expected)

    def test_getitem_preserves_freq(self, simple_index):
        index = simple_index
        assert index.freq is not None

        result = index[:]
        assert result.freq == index.freq

    def test_where_cast_str(self, simple_index):
        index = simple_index

        mask = np.ones(len(index), dtype=bool)
        mask[-1] = False

        result = index.where(mask, str(index[0]))
        expected = index.where(mask, index[0])
        tm.assert_index_equal(result, expected)

        result = index.where(mask, [str(index[0])])
        tm.assert_index_equal(result, expected)

        expected = index.astype(object).where(mask, "foo")
        result = index.where(mask, "foo")
        tm.assert_index_equal(result, expected)

        result = index.where(mask, ["foo"])
        tm.assert_index_equal(result, expected)

    @pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
    def test_diff(self, unit):
        # GH 55080
        dti = pd.to_datetime([10, 20, 30], unit=unit).as_unit(unit)
        result = dti.diff(1)
        expected = pd.to_timedelta([pd.NaT, 10, 10], unit=unit).as_unit(unit)
        tm.assert_index_equal(result, expected)
