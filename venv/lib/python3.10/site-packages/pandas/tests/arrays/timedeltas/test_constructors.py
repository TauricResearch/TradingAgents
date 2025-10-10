import numpy as np
import pytest

import pandas._testing as tm
from pandas.core.arrays import TimedeltaArray


class TestTimedeltaArrayConstructor:
    def test_only_1dim_accepted(self):
        # GH#25282
        arr = np.array([0, 1, 2, 3], dtype="m8[h]").astype("m8[ns]")

        depr_msg = "TimedeltaArray.__init__ is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            with pytest.raises(ValueError, match="Only 1-dimensional"):
                # 3-dim, we allow 2D to sneak in for ops purposes GH#29853
                TimedeltaArray(arr.reshape(2, 2, 1))

        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            with pytest.raises(ValueError, match="Only 1-dimensional"):
                # 0-dim
                TimedeltaArray(arr[[0]].squeeze())

    def test_freq_validation(self):
        # ensure that the public constructor cannot create an invalid instance
        arr = np.array([0, 0, 1], dtype=np.int64) * 3600 * 10**9

        msg = (
            "Inferred frequency None from passed values does not "
            "conform to passed frequency D"
        )
        depr_msg = "TimedeltaArray.__init__ is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            with pytest.raises(ValueError, match=msg):
                TimedeltaArray(arr.view("timedelta64[ns]"), freq="D")

    def test_non_array_raises(self):
        depr_msg = "TimedeltaArray.__init__ is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            with pytest.raises(ValueError, match="list"):
                TimedeltaArray([1, 2, 3])

    def test_other_type_raises(self):
        msg = r"dtype bool cannot be converted to timedelta64\[ns\]"
        with pytest.raises(TypeError, match=msg):
            TimedeltaArray._from_sequence(np.array([1, 2, 3], dtype="bool"))

    def test_incorrect_dtype_raises(self):
        msg = "dtype 'category' is invalid, should be np.timedelta64 dtype"
        with pytest.raises(ValueError, match=msg):
            TimedeltaArray._from_sequence(
                np.array([1, 2, 3], dtype="i8"), dtype="category"
            )

        msg = "dtype 'int64' is invalid, should be np.timedelta64 dtype"
        with pytest.raises(ValueError, match=msg):
            TimedeltaArray._from_sequence(
                np.array([1, 2, 3], dtype="i8"), dtype=np.dtype("int64")
            )

        msg = r"dtype 'datetime64\[ns\]' is invalid, should be np.timedelta64 dtype"
        with pytest.raises(ValueError, match=msg):
            TimedeltaArray._from_sequence(
                np.array([1, 2, 3], dtype="i8"), dtype=np.dtype("M8[ns]")
            )

        msg = (
            r"dtype 'datetime64\[us, UTC\]' is invalid, should be np.timedelta64 dtype"
        )
        with pytest.raises(ValueError, match=msg):
            TimedeltaArray._from_sequence(
                np.array([1, 2, 3], dtype="i8"), dtype="M8[us, UTC]"
            )

        msg = "Supported timedelta64 resolutions are 's', 'ms', 'us', 'ns'"
        with pytest.raises(ValueError, match=msg):
            TimedeltaArray._from_sequence(
                np.array([1, 2, 3], dtype="i8"), dtype=np.dtype("m8[Y]")
            )

    def test_mismatched_values_dtype_units(self):
        arr = np.array([1, 2, 3], dtype="m8[s]")
        dtype = np.dtype("m8[ns]")
        msg = r"Values resolution does not match dtype"
        depr_msg = "TimedeltaArray.__init__ is deprecated"

        with tm.assert_produces_warning(FutureWarning, match=depr_msg):
            with pytest.raises(ValueError, match=msg):
                TimedeltaArray(arr, dtype=dtype)

    def test_copy(self):
        data = np.array([1, 2, 3], dtype="m8[ns]")
        arr = TimedeltaArray._from_sequence(data, copy=False)
        assert arr._ndarray is data

        arr = TimedeltaArray._from_sequence(data, copy=True)
        assert arr._ndarray is not data
        assert arr._ndarray.base is not data

    def test_from_sequence_dtype(self):
        msg = "dtype 'object' is invalid, should be np.timedelta64 dtype"
        with pytest.raises(ValueError, match=msg):
            TimedeltaArray._from_sequence([], dtype=object)
