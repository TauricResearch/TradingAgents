import numpy as np
import pytest

from pandas import (
    DatetimeIndex,
    Index,
    date_range,
    factorize,
)
import pandas._testing as tm


class TestDatetimeIndexFactorize:
    def test_factorize(self):
        idx1 = DatetimeIndex(
            ["2014-01", "2014-01", "2014-02", "2014-02", "2014-03", "2014-03"]
        )

        exp_arr = np.array([0, 0, 1, 1, 2, 2], dtype=np.intp)
        exp_idx = DatetimeIndex(["2014-01", "2014-02", "2014-03"])

        arr, idx = idx1.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

        arr, idx = idx1.factorize(sort=True)
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

        # tz must be preserved
        idx1 = idx1.tz_localize("Asia/Tokyo")
        exp_idx = exp_idx.tz_localize("Asia/Tokyo")

        arr, idx = idx1.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

        idx2 = DatetimeIndex(
            ["2014-03", "2014-03", "2014-02", "2014-01", "2014-03", "2014-01"]
        )

        exp_arr = np.array([2, 2, 1, 0, 2, 0], dtype=np.intp)
        exp_idx = DatetimeIndex(["2014-01", "2014-02", "2014-03"])
        arr, idx = idx2.factorize(sort=True)
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

        exp_arr = np.array([0, 0, 1, 2, 0, 2], dtype=np.intp)
        exp_idx = DatetimeIndex(["2014-03", "2014-02", "2014-01"])
        arr, idx = idx2.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, exp_idx)
        assert idx.freq == exp_idx.freq

    def test_factorize_preserves_freq(self):
        # GH#38120 freq should be preserved
        idx3 = date_range("2000-01", periods=4, freq="ME", tz="Asia/Tokyo")
        exp_arr = np.array([0, 1, 2, 3], dtype=np.intp)

        arr, idx = idx3.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, idx3)
        assert idx.freq == idx3.freq

        arr, idx = factorize(idx3)
        tm.assert_numpy_array_equal(arr, exp_arr)
        tm.assert_index_equal(idx, idx3)
        assert idx.freq == idx3.freq

    def test_factorize_tz(self, tz_naive_fixture, index_or_series):
        tz = tz_naive_fixture
        # GH#13750
        base = date_range("2016-11-05", freq="h", periods=100, tz=tz)
        idx = base.repeat(5)

        exp_arr = np.arange(100, dtype=np.intp).repeat(5)

        obj = index_or_series(idx)

        arr, res = obj.factorize()
        tm.assert_numpy_array_equal(arr, exp_arr)
        expected = base._with_freq(None)
        tm.assert_index_equal(res, expected)
        assert res.freq == expected.freq

    def test_factorize_dst(self, index_or_series):
        # GH#13750
        idx = date_range("2016-11-06", freq="h", periods=12, tz="US/Eastern")
        obj = index_or_series(idx)

        arr, res = obj.factorize()
        tm.assert_numpy_array_equal(arr, np.arange(12, dtype=np.intp))
        tm.assert_index_equal(res, idx)
        if index_or_series is Index:
            assert res.freq == idx.freq

        idx = date_range("2016-06-13", freq="h", periods=12, tz="US/Eastern")
        obj = index_or_series(idx)

        arr, res = obj.factorize()
        tm.assert_numpy_array_equal(arr, np.arange(12, dtype=np.intp))
        tm.assert_index_equal(res, idx)
        if index_or_series is Index:
            assert res.freq == idx.freq

    @pytest.mark.parametrize("sort", [True, False])
    def test_factorize_no_freq_non_nano(self, tz_naive_fixture, sort):
        # GH#51978 case that does not go through the fastpath based on
        #  non-None freq
        tz = tz_naive_fixture
        idx = date_range("2016-11-06", freq="h", periods=5, tz=tz)[[0, 4, 1, 3, 2]]
        exp_codes, exp_uniques = idx.factorize(sort=sort)

        res_codes, res_uniques = idx.as_unit("s").factorize(sort=sort)

        tm.assert_numpy_array_equal(res_codes, exp_codes)
        tm.assert_index_equal(res_uniques, exp_uniques.as_unit("s"))

        res_codes, res_uniques = idx.as_unit("s").to_series().factorize(sort=sort)
        tm.assert_numpy_array_equal(res_codes, exp_codes)
        tm.assert_index_equal(res_uniques, exp_uniques.as_unit("s"))
