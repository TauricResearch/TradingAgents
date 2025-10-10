from datetime import datetime

import numpy as np
import pytest

from pandas.core.dtypes.cast import maybe_box_native

from pandas import (
    Interval,
    Period,
    Timedelta,
    Timestamp,
)


@pytest.mark.parametrize(
    "obj,expected_dtype",
    [
        (b"\x00\x10", bytes),
        (int(4), int),
        (np.uint(4), int),
        (np.int32(-4), int),
        (np.uint8(4), int),
        (float(454.98), float),
        (np.float16(0.4), float),
        (np.float64(1.4), float),
        (np.bool_(False), bool),
        (datetime(2005, 2, 25), datetime),
        (np.datetime64("2005-02-25"), Timestamp),
        (Timestamp("2005-02-25"), Timestamp),
        (np.timedelta64(1, "D"), Timedelta),
        (Timedelta(1, "D"), Timedelta),
        (Interval(0, 1), Interval),
        (Period("4Q2005"), Period),
    ],
)
def test_maybe_box_native(obj, expected_dtype):
    boxed_obj = maybe_box_native(obj)
    result_dtype = type(boxed_obj)
    assert result_dtype is expected_dtype
