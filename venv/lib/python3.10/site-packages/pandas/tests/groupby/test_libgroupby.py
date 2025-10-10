import numpy as np
import pytest

from pandas._libs import groupby as libgroupby
from pandas._libs.groupby import (
    group_cumprod,
    group_cumsum,
    group_mean,
    group_sum,
    group_var,
)

from pandas.core.dtypes.common import ensure_platform_int

from pandas import isna
import pandas._testing as tm


class GroupVarTestMixin:
    def test_group_var_generic_1d(self):
        prng = np.random.default_rng(2)

        out = (np.nan * np.ones((5, 1))).astype(self.dtype)
        counts = np.zeros(5, dtype="int64")
        values = 10 * prng.random((15, 1)).astype(self.dtype)
        labels = np.tile(np.arange(5), (3,)).astype("intp")

        expected_out = (
            np.squeeze(values).reshape((5, 3), order="F").std(axis=1, ddof=1) ** 2
        )[:, np.newaxis]
        expected_counts = counts + 3

        self.algo(out, counts, values, labels)
        assert np.allclose(out, expected_out, self.rtol)
        tm.assert_numpy_array_equal(counts, expected_counts)

    def test_group_var_generic_1d_flat_labels(self):
        prng = np.random.default_rng(2)

        out = (np.nan * np.ones((1, 1))).astype(self.dtype)
        counts = np.zeros(1, dtype="int64")
        values = 10 * prng.random((5, 1)).astype(self.dtype)
        labels = np.zeros(5, dtype="intp")

        expected_out = np.array([[values.std(ddof=1) ** 2]])
        expected_counts = counts + 5

        self.algo(out, counts, values, labels)

        assert np.allclose(out, expected_out, self.rtol)
        tm.assert_numpy_array_equal(counts, expected_counts)

    def test_group_var_generic_2d_all_finite(self):
        prng = np.random.default_rng(2)

        out = (np.nan * np.ones((5, 2))).astype(self.dtype)
        counts = np.zeros(5, dtype="int64")
        values = 10 * prng.random((10, 2)).astype(self.dtype)
        labels = np.tile(np.arange(5), (2,)).astype("intp")

        expected_out = np.std(values.reshape(2, 5, 2), ddof=1, axis=0) ** 2
        expected_counts = counts + 2

        self.algo(out, counts, values, labels)
        assert np.allclose(out, expected_out, self.rtol)
        tm.assert_numpy_array_equal(counts, expected_counts)

    def test_group_var_generic_2d_some_nan(self):
        prng = np.random.default_rng(2)

        out = (np.nan * np.ones((5, 2))).astype(self.dtype)
        counts = np.zeros(5, dtype="int64")
        values = 10 * prng.random((10, 2)).astype(self.dtype)
        values[:, 1] = np.nan
        labels = np.tile(np.arange(5), (2,)).astype("intp")

        expected_out = np.vstack(
            [
                values[:, 0].reshape(5, 2, order="F").std(ddof=1, axis=1) ** 2,
                np.nan * np.ones(5),
            ]
        ).T.astype(self.dtype)
        expected_counts = counts + 2

        self.algo(out, counts, values, labels)
        tm.assert_almost_equal(out, expected_out, rtol=0.5e-06)
        tm.assert_numpy_array_equal(counts, expected_counts)

    def test_group_var_constant(self):
        # Regression test from GH 10448.

        out = np.array([[np.nan]], dtype=self.dtype)
        counts = np.array([0], dtype="int64")
        values = 0.832845131556193 * np.ones((3, 1), dtype=self.dtype)
        labels = np.zeros(3, dtype="intp")

        self.algo(out, counts, values, labels)

        assert counts[0] == 3
        assert out[0, 0] >= 0
        tm.assert_almost_equal(out[0, 0], 0.0)


class TestGroupVarFloat64(GroupVarTestMixin):
    __test__ = True

    algo = staticmethod(group_var)
    dtype = np.float64
    rtol = 1e-5

    def test_group_var_large_inputs(self):
        prng = np.random.default_rng(2)

        out = np.array([[np.nan]], dtype=self.dtype)
        counts = np.array([0], dtype="int64")
        values = (prng.random(10**6) + 10**12).astype(self.dtype)
        values.shape = (10**6, 1)
        labels = np.zeros(10**6, dtype="intp")

        self.algo(out, counts, values, labels)

        assert counts[0] == 10**6
        tm.assert_almost_equal(out[0, 0], 1.0 / 12, rtol=0.5e-3)


class TestGroupVarFloat32(GroupVarTestMixin):
    __test__ = True

    algo = staticmethod(group_var)
    dtype = np.float32
    rtol = 1e-2


@pytest.mark.parametrize("dtype", ["float32", "float64"])
def test_group_ohlc(dtype):
    obj = np.array(np.random.default_rng(2).standard_normal(20), dtype=dtype)

    bins = np.array([6, 12, 20])
    out = np.zeros((3, 4), dtype)
    counts = np.zeros(len(out), dtype=np.int64)
    labels = ensure_platform_int(np.repeat(np.arange(3), np.diff(np.r_[0, bins])))

    func = libgroupby.group_ohlc
    func(out, counts, obj[:, None], labels)

    def _ohlc(group):
        if isna(group).all():
            return np.repeat(np.nan, 4)
        return [group[0], group.max(), group.min(), group[-1]]

    expected = np.array([_ohlc(obj[:6]), _ohlc(obj[6:12]), _ohlc(obj[12:])])

    tm.assert_almost_equal(out, expected)
    tm.assert_numpy_array_equal(counts, np.array([6, 6, 8], dtype=np.int64))

    obj[:6] = np.nan
    func(out, counts, obj[:, None], labels)
    expected[0] = np.nan
    tm.assert_almost_equal(out, expected)


def _check_cython_group_transform_cumulative(pd_op, np_op, dtype):
    """
    Check a group transform that executes a cumulative function.

    Parameters
    ----------
    pd_op : callable
        The pandas cumulative function.
    np_op : callable
        The analogous one in NumPy.
    dtype : type
        The specified dtype of the data.
    """
    is_datetimelike = False

    data = np.array([[1], [2], [3], [4]], dtype=dtype)
    answer = np.zeros_like(data)

    labels = np.array([0, 0, 0, 0], dtype=np.intp)
    ngroups = 1
    pd_op(answer, data, labels, ngroups, is_datetimelike)

    tm.assert_numpy_array_equal(np_op(data), answer[:, 0], check_dtype=False)


@pytest.mark.parametrize("np_dtype", ["int64", "uint64", "float32", "float64"])
def test_cython_group_transform_cumsum(np_dtype):
    # see gh-4095
    dtype = np.dtype(np_dtype).type
    pd_op, np_op = group_cumsum, np.cumsum
    _check_cython_group_transform_cumulative(pd_op, np_op, dtype)


def test_cython_group_transform_cumprod():
    # see gh-4095
    dtype = np.float64
    pd_op, np_op = group_cumprod, np.cumprod
    _check_cython_group_transform_cumulative(pd_op, np_op, dtype)


def test_cython_group_transform_algos():
    # see gh-4095
    is_datetimelike = False

    # with nans
    labels = np.array([0, 0, 0, 0, 0], dtype=np.intp)
    ngroups = 1

    data = np.array([[1], [2], [3], [np.nan], [4]], dtype="float64")
    actual = np.zeros_like(data)
    actual.fill(np.nan)
    group_cumprod(actual, data, labels, ngroups, is_datetimelike)
    expected = np.array([1, 2, 6, np.nan, 24], dtype="float64")
    tm.assert_numpy_array_equal(actual[:, 0], expected)

    actual = np.zeros_like(data)
    actual.fill(np.nan)
    group_cumsum(actual, data, labels, ngroups, is_datetimelike)
    expected = np.array([1, 3, 6, np.nan, 10], dtype="float64")
    tm.assert_numpy_array_equal(actual[:, 0], expected)

    # timedelta
    is_datetimelike = True
    data = np.array([np.timedelta64(1, "ns")] * 5, dtype="m8[ns]")[:, None]
    actual = np.zeros_like(data, dtype="int64")
    group_cumsum(actual, data.view("int64"), labels, ngroups, is_datetimelike)
    expected = np.array(
        [
            np.timedelta64(1, "ns"),
            np.timedelta64(2, "ns"),
            np.timedelta64(3, "ns"),
            np.timedelta64(4, "ns"),
            np.timedelta64(5, "ns"),
        ]
    )
    tm.assert_numpy_array_equal(actual[:, 0].view("m8[ns]"), expected)


def test_cython_group_mean_datetimelike():
    actual = np.zeros(shape=(1, 1), dtype="float64")
    counts = np.array([0], dtype="int64")
    data = (
        np.array(
            [np.timedelta64(2, "ns"), np.timedelta64(4, "ns"), np.timedelta64("NaT")],
            dtype="m8[ns]",
        )[:, None]
        .view("int64")
        .astype("float64")
    )
    labels = np.zeros(len(data), dtype=np.intp)

    group_mean(actual, counts, data, labels, is_datetimelike=True)

    tm.assert_numpy_array_equal(actual[:, 0], np.array([3], dtype="float64"))


def test_cython_group_mean_wrong_min_count():
    actual = np.zeros(shape=(1, 1), dtype="float64")
    counts = np.zeros(1, dtype="int64")
    data = np.zeros(1, dtype="float64")[:, None]
    labels = np.zeros(1, dtype=np.intp)

    with pytest.raises(AssertionError, match="min_count"):
        group_mean(actual, counts, data, labels, is_datetimelike=True, min_count=0)


def test_cython_group_mean_not_datetimelike_but_has_NaT_values():
    actual = np.zeros(shape=(1, 1), dtype="float64")
    counts = np.array([0], dtype="int64")
    data = (
        np.array(
            [np.timedelta64("NaT"), np.timedelta64("NaT")],
            dtype="m8[ns]",
        )[:, None]
        .view("int64")
        .astype("float64")
    )
    labels = np.zeros(len(data), dtype=np.intp)

    group_mean(actual, counts, data, labels, is_datetimelike=False)

    tm.assert_numpy_array_equal(
        actual[:, 0], np.array(np.divide(np.add(data[0], data[1]), 2), dtype="float64")
    )


def test_cython_group_mean_Inf_at_begining_and_end():
    # GH 50367
    actual = np.array([[np.nan, np.nan], [np.nan, np.nan]], dtype="float64")
    counts = np.array([0, 0], dtype="int64")
    data = np.array(
        [[np.inf, 1.0], [1.0, 2.0], [2.0, 3.0], [3.0, 4.0], [4.0, 5.0], [5, np.inf]],
        dtype="float64",
    )
    labels = np.array([0, 1, 0, 1, 0, 1], dtype=np.intp)

    group_mean(actual, counts, data, labels, is_datetimelike=False)

    expected = np.array([[np.inf, 3], [3, np.inf]], dtype="float64")

    tm.assert_numpy_array_equal(
        actual,
        expected,
    )


@pytest.mark.parametrize(
    "values, out",
    [
        ([[np.inf], [np.inf], [np.inf]], [[np.inf], [np.inf]]),
        ([[np.inf], [np.inf], [-np.inf]], [[np.inf], [np.nan]]),
        ([[np.inf], [-np.inf], [np.inf]], [[np.inf], [np.nan]]),
        ([[np.inf], [-np.inf], [-np.inf]], [[np.inf], [-np.inf]]),
    ],
)
def test_cython_group_sum_Inf_at_begining_and_end(values, out):
    # GH #53606
    actual = np.array([[np.nan], [np.nan]], dtype="float64")
    counts = np.array([0, 0], dtype="int64")
    data = np.array(values, dtype="float64")
    labels = np.array([0, 1, 1], dtype=np.intp)

    group_sum(actual, counts, data, labels, None, is_datetimelike=False)

    expected = np.array(out, dtype="float64")

    tm.assert_numpy_array_equal(
        actual,
        expected,
    )
