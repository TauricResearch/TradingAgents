from datetime import datetime

from pandas import DataFrame
import pandas._testing as tm


class TestInferObjects:
    def test_infer_objects(self):
        # GH#11221
        df = DataFrame(
            {
                "a": ["a", 1, 2, 3],
                "b": ["b", 2.0, 3.0, 4.1],
                "c": [
                    "c",
                    datetime(2016, 1, 1),
                    datetime(2016, 1, 2),
                    datetime(2016, 1, 3),
                ],
                "d": [1, 2, 3, "d"],
            },
            columns=["a", "b", "c", "d"],
        )
        df = df.iloc[1:].infer_objects()

        assert df["a"].dtype == "int64"
        assert df["b"].dtype == "float64"
        assert df["c"].dtype == "M8[ns]"
        assert df["d"].dtype == "object"

        expected = DataFrame(
            {
                "a": [1, 2, 3],
                "b": [2.0, 3.0, 4.1],
                "c": [datetime(2016, 1, 1), datetime(2016, 1, 2), datetime(2016, 1, 3)],
                "d": [2, 3, "d"],
            },
            columns=["a", "b", "c", "d"],
        )
        # reconstruct frame to verify inference is same
        result = df.reset_index(drop=True)
        tm.assert_frame_equal(result, expected)
