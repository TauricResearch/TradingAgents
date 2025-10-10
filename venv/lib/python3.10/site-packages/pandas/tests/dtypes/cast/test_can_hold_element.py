import numpy as np

from pandas.core.dtypes.cast import can_hold_element


def test_can_hold_element_range(any_int_numpy_dtype):
    # GH#44261
    dtype = np.dtype(any_int_numpy_dtype)
    arr = np.array([], dtype=dtype)

    rng = range(2, 127)
    assert can_hold_element(arr, rng)

    # negatives -> can't be held by uint dtypes
    rng = range(-2, 127)
    if dtype.kind == "i":
        assert can_hold_element(arr, rng)
    else:
        assert not can_hold_element(arr, rng)

    rng = range(2, 255)
    if dtype == "int8":
        assert not can_hold_element(arr, rng)
    else:
        assert can_hold_element(arr, rng)

    rng = range(-255, 65537)
    if dtype.kind == "u":
        assert not can_hold_element(arr, rng)
    elif dtype.itemsize < 4:
        assert not can_hold_element(arr, rng)
    else:
        assert can_hold_element(arr, rng)

    # empty
    rng = range(-(10**10), -(10**10))
    assert len(rng) == 0
    # assert can_hold_element(arr, rng)

    rng = range(10**10, 10**10)
    assert len(rng) == 0
    assert can_hold_element(arr, rng)


def test_can_hold_element_int_values_float_ndarray():
    arr = np.array([], dtype=np.int64)

    element = np.array([1.0, 2.0])
    assert can_hold_element(arr, element)

    assert not can_hold_element(arr, element + 0.5)

    # integer but not losslessly castable to int64
    element = np.array([3, 2**65], dtype=np.float64)
    assert not can_hold_element(arr, element)


def test_can_hold_element_int8_int():
    arr = np.array([], dtype=np.int8)

    element = 2
    assert can_hold_element(arr, element)
    assert can_hold_element(arr, np.int8(element))
    assert can_hold_element(arr, np.uint8(element))
    assert can_hold_element(arr, np.int16(element))
    assert can_hold_element(arr, np.uint16(element))
    assert can_hold_element(arr, np.int32(element))
    assert can_hold_element(arr, np.uint32(element))
    assert can_hold_element(arr, np.int64(element))
    assert can_hold_element(arr, np.uint64(element))

    element = 2**9
    assert not can_hold_element(arr, element)
    assert not can_hold_element(arr, np.int16(element))
    assert not can_hold_element(arr, np.uint16(element))
    assert not can_hold_element(arr, np.int32(element))
    assert not can_hold_element(arr, np.uint32(element))
    assert not can_hold_element(arr, np.int64(element))
    assert not can_hold_element(arr, np.uint64(element))
