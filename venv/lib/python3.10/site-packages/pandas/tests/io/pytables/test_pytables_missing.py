import pytest

import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm


@td.skip_if_installed("tables")
def test_pytables_raises():
    df = pd.DataFrame({"A": [1, 2]})
    with pytest.raises(ImportError, match="tables"):
        with tm.ensure_clean("foo.h5") as path:
            df.to_hdf(path, key="df")
