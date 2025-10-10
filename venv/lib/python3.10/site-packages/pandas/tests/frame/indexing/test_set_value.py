import numpy as np

from pandas.core.dtypes.common import is_float_dtype

from pandas import (
    DataFrame,
    isna,
)
import pandas._testing as tm


class TestSetValue:
    def test_set_value(self, float_frame):
        for idx in float_frame.index:
            for col in float_frame.columns:
                float_frame._set_value(idx, col, 1)
                assert float_frame[col][idx] == 1

    def test_set_value_resize(self, float_frame, using_infer_string):
        res = float_frame._set_value("foobar", "B", 0)
        assert res is None
        assert float_frame.index[-1] == "foobar"
        assert float_frame._get_value("foobar", "B") == 0

        float_frame.loc["foobar", "qux"] = 0
        assert float_frame._get_value("foobar", "qux") == 0

        res = float_frame.copy()
        res._set_value("foobar", "baz", "sam")
        if using_infer_string:
            assert res["baz"].dtype == "str"
        else:
            assert res["baz"].dtype == np.object_
        res = float_frame.copy()
        res._set_value("foobar", "baz", True)
        assert res["baz"].dtype == np.object_

        res = float_frame.copy()
        res._set_value("foobar", "baz", 5)
        assert is_float_dtype(res["baz"])
        assert isna(res["baz"].drop(["foobar"])).all()

        with tm.assert_produces_warning(
            FutureWarning, match="Setting an item of incompatible dtype"
        ):
            res._set_value("foobar", "baz", "sam")
        assert res.loc["foobar", "baz"] == "sam"

    def test_set_value_with_index_dtype_change(self):
        df_orig = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            index=range(3),
            columns=list("ABC"),
        )

        # this is actually ambiguous as the 2 is interpreted as a positional
        # so column is not created
        df = df_orig.copy()
        df._set_value("C", 2, 1.0)
        assert list(df.index) == list(df_orig.index) + ["C"]
        # assert list(df.columns) == list(df_orig.columns) + [2]

        df = df_orig.copy()
        df.loc["C", 2] = 1.0
        assert list(df.index) == list(df_orig.index) + ["C"]
        # assert list(df.columns) == list(df_orig.columns) + [2]

        # create both new
        df = df_orig.copy()
        df._set_value("C", "D", 1.0)
        assert list(df.index) == list(df_orig.index) + ["C"]
        assert list(df.columns) == list(df_orig.columns) + ["D"]

        df = df_orig.copy()
        df.loc["C", "D"] = 1.0
        assert list(df.index) == list(df_orig.index) + ["C"]
        assert list(df.columns) == list(df_orig.columns) + ["D"]
