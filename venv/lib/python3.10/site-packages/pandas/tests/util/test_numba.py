import pytest

import pandas.util._test_decorators as td

from pandas import option_context


@td.skip_if_installed("numba")
def test_numba_not_installed_option_context():
    with pytest.raises(ImportError, match="Missing optional"):
        with option_context("compute.use_numba", True):
            pass
