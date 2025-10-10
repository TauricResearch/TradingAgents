import numpy as np

import pandas as pd


def is_object_or_nan_string_dtype(dtype):
    """
    Check if string-like dtype is following NaN semantics, i.e. is object
    dtype or a NaN-variant of the StringDtype.
    """
    return (isinstance(dtype, np.dtype) and dtype == "object") or (
        dtype.na_value is np.nan
    )


def _convert_na_value(ser, expected):
    if ser.dtype != object:
        if ser.dtype.na_value is np.nan:
            expected = expected.fillna(np.nan)
        else:
            # GH#18463
            expected = expected.fillna(pd.NA)
    return expected
