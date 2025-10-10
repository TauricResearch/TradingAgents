import pandas as pd
import pandas._testing as tm


class TestUnaryOps:
    def test_invert(self):
        a = pd.array([True, False, None], dtype="boolean")
        expected = pd.array([False, True, None], dtype="boolean")
        tm.assert_extension_array_equal(~a, expected)

        expected = pd.Series(expected, index=["a", "b", "c"], name="name")
        result = ~pd.Series(a, index=["a", "b", "c"], name="name")
        tm.assert_series_equal(result, expected)

        df = pd.DataFrame({"A": a, "B": [True, False, False]}, index=["a", "b", "c"])
        result = ~df
        expected = pd.DataFrame(
            {"A": expected, "B": [False, True, True]}, index=["a", "b", "c"]
        )
        tm.assert_frame_equal(result, expected)

    def test_abs(self):
        # matching numpy behavior, abs is the identity function
        arr = pd.array([True, False, None], dtype="boolean")
        result = abs(arr)

        tm.assert_extension_array_equal(result, arr)
