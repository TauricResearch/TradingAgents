import numpy as np

import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm


def test_shares_memory_interval():
    obj = pd.interval_range(1, 5)

    assert tm.shares_memory(obj, obj)
    assert tm.shares_memory(obj, obj._data)
    assert tm.shares_memory(obj, obj[::-1])
    assert tm.shares_memory(obj, obj[:2])

    assert not tm.shares_memory(obj, obj._data.copy())


@td.skip_if_no("pyarrow")
def test_shares_memory_string():
    # GH#55823
    import pyarrow as pa

    obj = pd.array(["a", "b"], dtype=pd.StringDtype("pyarrow", na_value=pd.NA))
    assert tm.shares_memory(obj, obj)

    obj = pd.array(["a", "b"], dtype=pd.StringDtype("pyarrow", na_value=np.nan))
    assert tm.shares_memory(obj, obj)

    obj = pd.array(["a", "b"], dtype=pd.ArrowDtype(pa.string()))
    assert tm.shares_memory(obj, obj)
