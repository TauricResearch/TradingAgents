from hypothesis import (
    assume,
    example,
    given,
    strategies as st,
)
import numpy as np
import pytest

from pandas._libs.byteswap import (
    read_double_with_byteswap,
    read_float_with_byteswap,
    read_uint16_with_byteswap,
    read_uint32_with_byteswap,
    read_uint64_with_byteswap,
)

import pandas._testing as tm


@given(read_offset=st.integers(0, 11), number=st.integers(min_value=0))
@example(number=2**16, read_offset=0)
@example(number=2**32, read_offset=0)
@example(number=2**64, read_offset=0)
@pytest.mark.parametrize("int_type", [np.uint16, np.uint32, np.uint64])
@pytest.mark.parametrize("should_byteswap", [True, False])
def test_int_byteswap(read_offset, number, int_type, should_byteswap):
    assume(number < 2 ** (8 * int_type(0).itemsize))
    _test(number, int_type, read_offset, should_byteswap)


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")
@given(read_offset=st.integers(0, 11), number=st.floats())
@pytest.mark.parametrize("float_type", [np.float32, np.float64])
@pytest.mark.parametrize("should_byteswap", [True, False])
def test_float_byteswap(read_offset, number, float_type, should_byteswap):
    _test(number, float_type, read_offset, should_byteswap)


def _test(number, number_type, read_offset, should_byteswap):
    number = number_type(number)
    data = np.random.default_rng(2).integers(0, 256, size=20, dtype="uint8")
    data[read_offset : read_offset + number.itemsize] = number[None].view("uint8")
    swap_func = {
        np.float32: read_float_with_byteswap,
        np.float64: read_double_with_byteswap,
        np.uint16: read_uint16_with_byteswap,
        np.uint32: read_uint32_with_byteswap,
        np.uint64: read_uint64_with_byteswap,
    }[type(number)]
    output_number = number_type(swap_func(bytes(data), read_offset, should_byteswap))
    if should_byteswap:
        tm.assert_equal(output_number, number.byteswap())
    else:
        tm.assert_equal(output_number, number)
