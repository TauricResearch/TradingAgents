"""
Tests for Indexes backed by arbitrary ExtensionArrays.
"""
import pandas as pd


class BaseIndexTests:
    """Tests for Index object backed by an ExtensionArray"""

    def test_index_from_array(self, data):
        idx = pd.Index(data)
        assert data.dtype == idx.dtype

    def test_index_from_listlike_with_dtype(self, data):
        idx = pd.Index(data, dtype=data.dtype)
        assert idx.dtype == data.dtype

        idx = pd.Index(list(data), dtype=data.dtype)
        assert idx.dtype == data.dtype
