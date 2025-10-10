import re

import numpy as np
import pytest

import pandas as pd


class TestSetitemValidation:
    def _check_setitem_invalid(self, arr, invalid):
        msg = f"Invalid value '{invalid!s}' for dtype '{arr.dtype}'"
        msg = re.escape(msg)
        with pytest.raises(TypeError, match=msg):
            arr[0] = invalid

        with pytest.raises(TypeError, match=msg):
            arr[:] = invalid

        with pytest.raises(TypeError, match=msg):
            arr[[0]] = invalid

        # FIXME: don't leave commented-out
        # with pytest.raises(TypeError):
        #    arr[[0]] = [invalid]

        # with pytest.raises(TypeError):
        #    arr[[0]] = np.array([invalid], dtype=object)

        # Series non-coercion, behavior subject to change
        ser = pd.Series(arr)
        with pytest.raises(TypeError, match=msg):
            ser[0] = invalid
            # TODO: so, so many other variants of this...

    _invalid_scalars = [
        1 + 2j,
        "True",
        "1",
        "1.0",
        pd.NaT,
        np.datetime64("NaT"),
        np.timedelta64("NaT"),
    ]

    @pytest.mark.parametrize(
        "invalid", _invalid_scalars + [1, 1.0, np.int64(1), np.float64(1)]
    )
    def test_setitem_validation_scalar_bool(self, invalid):
        arr = pd.array([True, False, None], dtype="boolean")
        self._check_setitem_invalid(arr, invalid)

    @pytest.mark.parametrize("invalid", _invalid_scalars + [True, 1.5, np.float64(1.5)])
    def test_setitem_validation_scalar_int(self, invalid, any_int_ea_dtype):
        arr = pd.array([1, 2, None], dtype=any_int_ea_dtype)
        self._check_setitem_invalid(arr, invalid)

    @pytest.mark.parametrize("invalid", _invalid_scalars + [True])
    def test_setitem_validation_scalar_float(self, invalid, float_ea_dtype):
        arr = pd.array([1, 2, None], dtype=float_ea_dtype)
        self._check_setitem_invalid(arr, invalid)
