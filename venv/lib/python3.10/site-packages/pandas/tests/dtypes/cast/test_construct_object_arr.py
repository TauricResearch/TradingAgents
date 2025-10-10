import pytest

from pandas.core.dtypes.cast import construct_1d_object_array_from_listlike


@pytest.mark.parametrize("datum1", [1, 2.0, "3", (4, 5), [6, 7], None])
@pytest.mark.parametrize("datum2", [8, 9.0, "10", (11, 12), [13, 14], None])
def test_cast_1d_array(datum1, datum2):
    data = [datum1, datum2]
    result = construct_1d_object_array_from_listlike(data)

    # Direct comparison fails: https://github.com/numpy/numpy/issues/10218
    assert result.dtype == "object"
    assert list(result) == data


@pytest.mark.parametrize("val", [1, 2.0, None])
def test_cast_1d_array_invalid_scalar(val):
    with pytest.raises(TypeError, match="has no len()"):
        construct_1d_object_array_from_listlike(val)
