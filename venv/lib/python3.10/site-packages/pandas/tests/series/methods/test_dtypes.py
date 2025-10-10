import numpy as np


class TestSeriesDtypes:
    def test_dtype(self, datetime_series):
        assert datetime_series.dtype == np.dtype("float64")
        assert datetime_series.dtypes == np.dtype("float64")
