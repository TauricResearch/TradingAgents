import io

import pytest

import pandas as pd


class BasePrintingTests:
    """Tests checking the formatting of your EA when printed."""

    @pytest.mark.parametrize("size", ["big", "small"])
    def test_array_repr(self, data, size):
        if size == "small":
            data = data[:5]
        else:
            data = type(data)._concat_same_type([data] * 5)

        result = repr(data)
        assert type(data).__name__ in result
        assert f"Length: {len(data)}" in result
        assert str(data.dtype) in result
        if size == "big":
            assert "..." in result

    def test_array_repr_unicode(self, data):
        result = str(data)
        assert isinstance(result, str)

    def test_series_repr(self, data):
        ser = pd.Series(data)
        assert data.dtype.name in repr(ser)

    def test_dataframe_repr(self, data):
        df = pd.DataFrame({"A": data})
        repr(df)

    def test_dtype_name_in_info(self, data):
        buf = io.StringIO()
        pd.DataFrame({"A": data}).info(buf=buf)
        result = buf.getvalue()
        assert data.dtype.name in result
