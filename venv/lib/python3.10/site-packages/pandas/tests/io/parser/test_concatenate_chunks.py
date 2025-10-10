import numpy as np
import pytest

from pandas.errors import DtypeWarning

import pandas._testing as tm
from pandas.core.arrays import ArrowExtensionArray

from pandas.io.parsers.c_parser_wrapper import _concatenate_chunks


def test_concatenate_chunks_pyarrow():
    # GH#51876
    pa = pytest.importorskip("pyarrow")
    chunks = [
        {0: ArrowExtensionArray(pa.array([1.5, 2.5]))},
        {0: ArrowExtensionArray(pa.array([1, 2]))},
    ]
    result = _concatenate_chunks(chunks)
    expected = ArrowExtensionArray(pa.array([1.5, 2.5, 1.0, 2.0]))
    tm.assert_extension_array_equal(result[0], expected)


def test_concatenate_chunks_pyarrow_strings():
    # GH#51876
    pa = pytest.importorskip("pyarrow")
    chunks = [
        {0: ArrowExtensionArray(pa.array([1.5, 2.5]))},
        {0: ArrowExtensionArray(pa.array(["a", "b"]))},
    ]
    with tm.assert_produces_warning(DtypeWarning, match="have mixed types"):
        result = _concatenate_chunks(chunks)
    expected = np.concatenate(
        [np.array([1.5, 2.5], dtype=object), np.array(["a", "b"])]
    )
    tm.assert_numpy_array_equal(result[0], expected)
