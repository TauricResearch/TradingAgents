from io import StringIO

import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm
from pandas.core.arrays import ExtensionArray


class BaseParsingTests:
    @pytest.mark.parametrize("engine", ["c", "python"])
    def test_EA_types(self, engine, data, request):
        if isinstance(data.dtype, pd.CategoricalDtype):
            # in parsers.pyx _convert_with_dtype there is special-casing for
            #  Categorical that pre-empts _from_sequence_of_strings
            pass
        elif isinstance(data.dtype, pd.core.dtypes.dtypes.NumpyEADtype):
            # These get unwrapped internally so are treated as numpy dtypes
            #  in the parsers.pyx code
            pass
        elif (
            type(data)._from_sequence_of_strings.__func__
            is ExtensionArray._from_sequence_of_strings.__func__
        ):
            # i.e. the EA hasn't overridden _from_sequence_of_strings
            mark = pytest.mark.xfail(
                reason="_from_sequence_of_strings not implemented",
                raises=NotImplementedError,
            )
            request.node.add_marker(mark)

        df = pd.DataFrame({"with_dtype": pd.Series(data, dtype=str(data.dtype))})
        csv_output = df.to_csv(index=False, na_rep=np.nan)
        result = pd.read_csv(
            StringIO(csv_output), dtype={"with_dtype": str(data.dtype)}, engine=engine
        )
        expected = df
        tm.assert_frame_equal(result, expected)
