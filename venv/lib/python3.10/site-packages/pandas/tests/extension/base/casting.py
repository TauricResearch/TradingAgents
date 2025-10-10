import numpy as np
import pytest

import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm
from pandas.core.internals.blocks import NumpyBlock


class BaseCastingTests:
    """Casting to and from ExtensionDtypes"""

    def test_astype_object_series(self, all_data):
        ser = pd.Series(all_data, name="A")
        result = ser.astype(object)
        assert result.dtype == np.dtype(object)
        if hasattr(result._mgr, "blocks"):
            blk = result._mgr.blocks[0]
            assert isinstance(blk, NumpyBlock)
            assert blk.is_object
        assert isinstance(result._mgr.array, np.ndarray)
        assert result._mgr.array.dtype == np.dtype(object)

    def test_astype_object_frame(self, all_data):
        df = pd.DataFrame({"A": all_data})

        result = df.astype(object)
        if hasattr(result._mgr, "blocks"):
            blk = result._mgr.blocks[0]
            assert isinstance(blk, NumpyBlock), type(blk)
            assert blk.is_object
        assert isinstance(result._mgr.arrays[0], np.ndarray)
        assert result._mgr.arrays[0].dtype == np.dtype(object)

        # check that we can compare the dtypes
        comp = result.dtypes == df.dtypes
        assert not comp.any()

    def test_tolist(self, data):
        result = pd.Series(data).tolist()
        expected = list(data)
        assert result == expected

    def test_astype_str(self, data):
        result = pd.Series(data[:2]).astype(str)
        expected = pd.Series([str(x) for x in data[:2]], dtype=str)
        tm.assert_series_equal(result, expected)

    @pytest.mark.parametrize(
        "nullable_string_dtype",
        [
            "string[python]",
            pytest.param("string[pyarrow]", marks=td.skip_if_no("pyarrow")),
        ],
    )
    def test_astype_string(self, data, nullable_string_dtype):
        # GH-33465, GH#45326 as of 2.0 we decode bytes instead of calling str(obj)
        result = pd.Series(data[:5]).astype(nullable_string_dtype)
        expected = pd.Series(
            [str(x) if not isinstance(x, bytes) else x.decode() for x in data[:5]],
            dtype=nullable_string_dtype,
        )
        tm.assert_series_equal(result, expected)

    def test_to_numpy(self, data):
        expected = np.asarray(data)

        result = data.to_numpy()
        tm.assert_equal(result, expected)

        result = pd.Series(data).to_numpy()
        tm.assert_equal(result, expected)

    def test_astype_empty_dataframe(self, dtype):
        # https://github.com/pandas-dev/pandas/issues/33113
        df = pd.DataFrame()
        result = df.astype(dtype)
        tm.assert_frame_equal(result, df)

    @pytest.mark.parametrize("copy", [True, False])
    def test_astype_own_type(self, data, copy):
        # ensure that astype returns the original object for equal dtype and copy=False
        # https://github.com/pandas-dev/pandas/issues/28488
        result = data.astype(data.dtype, copy=copy)
        assert (result is data) is (not copy)
        tm.assert_extension_array_equal(result, data)
