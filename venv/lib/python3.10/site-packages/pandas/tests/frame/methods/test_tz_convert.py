import numpy as np
import pytest

from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
    date_range,
)
import pandas._testing as tm


class TestTZConvert:
    def test_tz_convert(self, frame_or_series):
        rng = date_range("1/1/2011", periods=200, freq="D", tz="US/Eastern")

        obj = DataFrame({"a": 1}, index=rng)
        obj = tm.get_obj(obj, frame_or_series)

        result = obj.tz_convert("Europe/Berlin")
        expected = DataFrame({"a": 1}, rng.tz_convert("Europe/Berlin"))
        expected = tm.get_obj(expected, frame_or_series)

        assert result.index.tz.zone == "Europe/Berlin"
        tm.assert_equal(result, expected)

    def test_tz_convert_axis1(self):
        rng = date_range("1/1/2011", periods=200, freq="D", tz="US/Eastern")

        obj = DataFrame({"a": 1}, index=rng)

        obj = obj.T
        result = obj.tz_convert("Europe/Berlin", axis=1)
        assert result.columns.tz.zone == "Europe/Berlin"

        expected = DataFrame({"a": 1}, rng.tz_convert("Europe/Berlin"))

        tm.assert_equal(result, expected.T)

    def test_tz_convert_naive(self, frame_or_series):
        # can't convert tz-naive
        rng = date_range("1/1/2011", periods=200, freq="D")
        ts = Series(1, index=rng)
        ts = frame_or_series(ts)

        with pytest.raises(TypeError, match="Cannot convert tz-naive"):
            ts.tz_convert("US/Eastern")

    @pytest.mark.parametrize("fn", ["tz_localize", "tz_convert"])
    def test_tz_convert_and_localize(self, fn):
        l0 = date_range("20140701", periods=5, freq="D")
        l1 = date_range("20140701", periods=5, freq="D")

        int_idx = Index(range(5))

        if fn == "tz_convert":
            l0 = l0.tz_localize("UTC")
            l1 = l1.tz_localize("UTC")

        for idx in [l0, l1]:
            l0_expected = getattr(idx, fn)("US/Pacific")
            l1_expected = getattr(idx, fn)("US/Pacific")

            df1 = DataFrame(np.ones(5), index=l0)
            df1 = getattr(df1, fn)("US/Pacific")
            tm.assert_index_equal(df1.index, l0_expected)

            # MultiIndex
            # GH7846
            df2 = DataFrame(np.ones(5), MultiIndex.from_arrays([l0, l1]))

            # freq is not preserved in MultiIndex construction
            l1_expected = l1_expected._with_freq(None)
            l0_expected = l0_expected._with_freq(None)
            l1 = l1._with_freq(None)
            l0 = l0._with_freq(None)

            df3 = getattr(df2, fn)("US/Pacific", level=0)
            assert not df3.index.levels[0].equals(l0)
            tm.assert_index_equal(df3.index.levels[0], l0_expected)
            tm.assert_index_equal(df3.index.levels[1], l1)
            assert not df3.index.levels[1].equals(l1_expected)

            df3 = getattr(df2, fn)("US/Pacific", level=1)
            tm.assert_index_equal(df3.index.levels[0], l0)
            assert not df3.index.levels[0].equals(l0_expected)
            tm.assert_index_equal(df3.index.levels[1], l1_expected)
            assert not df3.index.levels[1].equals(l1)

            df4 = DataFrame(np.ones(5), MultiIndex.from_arrays([int_idx, l0]))

            # TODO: untested
            getattr(df4, fn)("US/Pacific", level=1)

            tm.assert_index_equal(df3.index.levels[0], l0)
            assert not df3.index.levels[0].equals(l0_expected)
            tm.assert_index_equal(df3.index.levels[1], l1_expected)
            assert not df3.index.levels[1].equals(l1)

        # Bad Inputs

        # Not DatetimeIndex / PeriodIndex
        with pytest.raises(TypeError, match="DatetimeIndex"):
            df = DataFrame(index=int_idx)
            getattr(df, fn)("US/Pacific")

        # Not DatetimeIndex / PeriodIndex
        with pytest.raises(TypeError, match="DatetimeIndex"):
            df = DataFrame(np.ones(5), MultiIndex.from_arrays([int_idx, l0]))
            getattr(df, fn)("US/Pacific", level=0)

        # Invalid level
        with pytest.raises(ValueError, match="not valid"):
            df = DataFrame(index=l0)
            getattr(df, fn)("US/Pacific", level=1)

    @pytest.mark.parametrize("copy", [True, False])
    def test_tz_convert_copy_inplace_mutate(self, copy, frame_or_series):
        # GH#6326
        obj = frame_or_series(
            np.arange(0, 5),
            index=date_range("20131027", periods=5, freq="h", tz="Europe/Berlin"),
        )
        orig = obj.copy()
        result = obj.tz_convert("UTC", copy=copy)
        expected = frame_or_series(np.arange(0, 5), index=obj.index.tz_convert("UTC"))
        tm.assert_equal(result, expected)
        tm.assert_equal(obj, orig)
        assert result.index is not obj.index
        assert result is not obj
