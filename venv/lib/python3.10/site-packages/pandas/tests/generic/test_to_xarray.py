import numpy as np
import pytest

from pandas import (
    Categorical,
    DataFrame,
    MultiIndex,
    Series,
    StringDtype,
    date_range,
)
import pandas._testing as tm
from pandas.util.version import Version

xarray = pytest.importorskip("xarray")


class TestDataFrameToXArray:
    @pytest.fixture
    def df(self):
        return DataFrame(
            {
                "a": list("abcd"),
                "b": list(range(1, 5)),
                "c": np.arange(3, 7).astype("u1"),
                "d": np.arange(4.0, 8.0, dtype="float64"),
                "e": [True, False, True, False],
                "f": Categorical(list("abcd")),
                "g": date_range("20130101", periods=4),
                "h": date_range("20130101", periods=4, tz="US/Eastern"),
            }
        )

    def test_to_xarray_index_types(self, index_flat, df, using_infer_string):
        index = index_flat
        # MultiIndex is tested in test_to_xarray_with_multiindex
        if len(index) == 0:
            pytest.skip("Test doesn't make sense for empty index")

        from xarray import Dataset

        df.index = index[:4]
        df.index.name = "foo"
        df.columns.name = "bar"
        result = df.to_xarray()
        assert result.sizes["foo"] == 4
        assert len(result.coords) == 1
        assert len(result.data_vars) == 8
        tm.assert_almost_equal(list(result.coords.keys()), ["foo"])
        assert isinstance(result, Dataset)

        # idempotency
        # datetimes w/tz are preserved
        # column names are lost
        expected = df.copy()
        expected["f"] = expected["f"].astype(
            object if not using_infer_string else "str"
        )
        expected.columns.name = None
        tm.assert_frame_equal(result.to_dataframe(), expected)

    def test_to_xarray_empty(self, df):
        from xarray import Dataset

        df.index.name = "foo"
        result = df[0:0].to_xarray()
        assert result.sizes["foo"] == 0
        assert isinstance(result, Dataset)

    def test_to_xarray_with_multiindex(self, df, using_infer_string):
        from xarray import Dataset

        # MultiIndex
        df.index = MultiIndex.from_product([["a"], range(4)], names=["one", "two"])
        result = df.to_xarray()
        assert result.sizes["one"] == 1
        assert result.sizes["two"] == 4
        assert len(result.coords) == 2
        assert len(result.data_vars) == 8
        tm.assert_almost_equal(list(result.coords.keys()), ["one", "two"])
        assert isinstance(result, Dataset)

        result = result.to_dataframe()
        expected = df.copy()
        expected["f"] = expected["f"].astype(
            object if not using_infer_string else "str"
        )
        expected.columns.name = None
        tm.assert_frame_equal(result, expected)


class TestSeriesToXArray:
    def test_to_xarray_index_types(self, index_flat, request):
        index = index_flat
        if (
            isinstance(index.dtype, StringDtype)
            and index.dtype.storage == "pyarrow"
            and Version(xarray.__version__) > Version("2024.9.0")
            and Version(xarray.__version__) < Version("2025.6.0")
        ):
            request.applymarker(
                pytest.mark.xfail(
                    reason="xarray calling reshape of ArrowExtensionArray",
                    raises=NotImplementedError,
                )
            )
        # MultiIndex is tested in test_to_xarray_with_multiindex

        from xarray import DataArray

        ser = Series(range(len(index)), index=index, dtype="int64")
        ser.index.name = "foo"
        result = ser.to_xarray()
        repr(result)
        assert len(result) == len(index)
        assert len(result.coords) == 1
        tm.assert_almost_equal(list(result.coords.keys()), ["foo"])
        assert isinstance(result, DataArray)

        # idempotency
        tm.assert_series_equal(result.to_series(), ser)

    def test_to_xarray_empty(self):
        from xarray import DataArray

        ser = Series([], dtype=object)
        ser.index.name = "foo"
        result = ser.to_xarray()
        assert len(result) == 0
        assert len(result.coords) == 1
        tm.assert_almost_equal(list(result.coords.keys()), ["foo"])
        assert isinstance(result, DataArray)

    def test_to_xarray_with_multiindex(self):
        from xarray import DataArray

        mi = MultiIndex.from_product([["a", "b"], range(3)], names=["one", "two"])
        ser = Series(range(6), dtype="int64", index=mi)
        result = ser.to_xarray()
        assert len(result) == 2
        tm.assert_almost_equal(list(result.coords.keys()), ["one", "two"])
        assert isinstance(result, DataArray)
        res = result.to_series()
        tm.assert_series_equal(res, ser)
