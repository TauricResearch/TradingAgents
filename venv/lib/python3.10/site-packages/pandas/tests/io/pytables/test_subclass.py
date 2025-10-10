import numpy as np
import pytest

from pandas import (
    DataFrame,
    Series,
)
import pandas._testing as tm

from pandas.io.pytables import (
    HDFStore,
    read_hdf,
)

pytest.importorskip("tables")


class TestHDFStoreSubclass:
    # GH 33748
    def test_supported_for_subclass_dataframe(self, tmp_path):
        data = {"a": [1, 2], "b": [3, 4]}
        sdf = tm.SubclassedDataFrame(data, dtype=np.intp)

        expected = DataFrame(data, dtype=np.intp)

        path = tmp_path / "temp.h5"
        sdf.to_hdf(path, key="df")
        result = read_hdf(path, "df")
        tm.assert_frame_equal(result, expected)

        path = tmp_path / "temp.h5"
        with HDFStore(path) as store:
            store.put("df", sdf)
        result = read_hdf(path, "df")
        tm.assert_frame_equal(result, expected)

    def test_supported_for_subclass_series(self, tmp_path):
        data = [1, 2, 3]
        sser = tm.SubclassedSeries(data, dtype=np.intp)

        expected = Series(data, dtype=np.intp)

        path = tmp_path / "temp.h5"
        sser.to_hdf(path, key="ser")
        result = read_hdf(path, "ser")
        tm.assert_series_equal(result, expected)

        path = tmp_path / "temp.h5"
        with HDFStore(path) as store:
            store.put("ser", sser)
        result = read_hdf(path, "ser")
        tm.assert_series_equal(result, expected)
