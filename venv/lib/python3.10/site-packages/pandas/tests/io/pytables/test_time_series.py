import datetime

import numpy as np
import pytest

from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    _testing as tm,
    date_range,
    period_range,
)
from pandas.tests.io.pytables.common import ensure_clean_store

pytestmark = pytest.mark.single_cpu


@pytest.mark.parametrize("unit", ["us", "ns"])
def test_store_datetime_fractional_secs(setup_path, unit):
    dt = datetime.datetime(2012, 1, 2, 3, 4, 5, 123456)
    dti = DatetimeIndex([dt], dtype=f"M8[{unit}]")
    series = Series([0], index=dti)
    with ensure_clean_store(setup_path) as store:
        store["a"] = series
        assert store["a"].index[0] == dt


@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
def test_tseries_indices_series(setup_path):
    with ensure_clean_store(setup_path) as store:
        idx = date_range("2020-01-01", periods=10)
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        store["a"] = ser
        result = store["a"]

        tm.assert_series_equal(result, ser)
        assert result.index.freq == ser.index.freq
        tm.assert_class_equal(result.index, ser.index, obj="series index")

        idx = period_range("2020-01-01", periods=10, freq="D")
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        store["a"] = ser
        result = store["a"]

        tm.assert_series_equal(result, ser)
        assert result.index.freq == ser.index.freq
        tm.assert_class_equal(result.index, ser.index, obj="series index")


@pytest.mark.filterwarnings(r"ignore:PeriodDtype\[B\] is deprecated:FutureWarning")
def test_tseries_indices_frame(setup_path):
    with ensure_clean_store(setup_path) as store:
        idx = date_range("2020-01-01", periods=10)
        df = DataFrame(
            np.random.default_rng(2).standard_normal((len(idx), 3)), index=idx
        )
        store["a"] = df
        result = store["a"]

        tm.assert_frame_equal(result, df)
        assert result.index.freq == df.index.freq
        tm.assert_class_equal(result.index, df.index, obj="dataframe index")

        idx = period_range("2020-01-01", periods=10, freq="D")
        df = DataFrame(np.random.default_rng(2).standard_normal((len(idx), 3)), idx)
        store["a"] = df
        result = store["a"]

        tm.assert_frame_equal(result, df)
        assert result.index.freq == df.index.freq
        tm.assert_class_equal(result.index, df.index, obj="dataframe index")
