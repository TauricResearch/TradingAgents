from pandas import Series


class TestSparseAccessor:
    def test_sparse_accessor_updates_on_inplace(self):
        ser = Series([1, 1, 2, 3], dtype="Sparse[int]")
        return_value = ser.drop([0, 1], inplace=True)
        assert return_value is None
        assert ser.sparse.density == 1.0
