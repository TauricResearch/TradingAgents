import pytest

from pandas import DataFrame
import pandas._testing as tm


class TestAssign:
    def test_assign(self):
        df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        original = df.copy()
        result = df.assign(C=df.B / df.A)
        expected = df.copy()
        expected["C"] = [4, 2.5, 2]
        tm.assert_frame_equal(result, expected)

        # lambda syntax
        result = df.assign(C=lambda x: x.B / x.A)
        tm.assert_frame_equal(result, expected)

        # original is unmodified
        tm.assert_frame_equal(df, original)

        # Non-Series array-like
        result = df.assign(C=[4, 2.5, 2])
        tm.assert_frame_equal(result, expected)
        # original is unmodified
        tm.assert_frame_equal(df, original)

        result = df.assign(B=df.B / df.A)
        expected = expected.drop("B", axis=1).rename(columns={"C": "B"})
        tm.assert_frame_equal(result, expected)

        # overwrite
        result = df.assign(A=df.A + df.B)
        expected = df.copy()
        expected["A"] = [5, 7, 9]
        tm.assert_frame_equal(result, expected)

        # lambda
        result = df.assign(A=lambda x: x.A + x.B)
        tm.assert_frame_equal(result, expected)

    def test_assign_multiple(self):
        df = DataFrame([[1, 4], [2, 5], [3, 6]], columns=["A", "B"])
        result = df.assign(C=[7, 8, 9], D=df.A, E=lambda x: x.B)
        expected = DataFrame(
            [[1, 4, 7, 1, 4], [2, 5, 8, 2, 5], [3, 6, 9, 3, 6]], columns=list("ABCDE")
        )
        tm.assert_frame_equal(result, expected)

    def test_assign_order(self):
        # GH 9818
        df = DataFrame([[1, 2], [3, 4]], columns=["A", "B"])
        result = df.assign(D=df.A + df.B, C=df.A - df.B)

        expected = DataFrame([[1, 2, 3, -1], [3, 4, 7, -1]], columns=list("ABDC"))
        tm.assert_frame_equal(result, expected)
        result = df.assign(C=df.A - df.B, D=df.A + df.B)

        expected = DataFrame([[1, 2, -1, 3], [3, 4, -1, 7]], columns=list("ABCD"))

        tm.assert_frame_equal(result, expected)

    def test_assign_bad(self):
        df = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})

        # non-keyword argument
        msg = r"assign\(\) takes 1 positional argument but 2 were given"
        with pytest.raises(TypeError, match=msg):
            df.assign(lambda x: x.A)
        msg = "'DataFrame' object has no attribute 'C'"
        with pytest.raises(AttributeError, match=msg):
            df.assign(C=df.A, D=df.A + df.C)

    def test_assign_dependent(self):
        df = DataFrame({"A": [1, 2], "B": [3, 4]})

        result = df.assign(C=df.A, D=lambda x: x["A"] + x["C"])
        expected = DataFrame([[1, 3, 1, 2], [2, 4, 2, 4]], columns=list("ABCD"))
        tm.assert_frame_equal(result, expected)

        result = df.assign(C=lambda df: df.A, D=lambda df: df["A"] + df["C"])
        expected = DataFrame([[1, 3, 1, 2], [2, 4, 2, 4]], columns=list("ABCD"))
        tm.assert_frame_equal(result, expected)
