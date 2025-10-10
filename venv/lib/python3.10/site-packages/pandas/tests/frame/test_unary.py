from decimal import Decimal

import numpy as np
import pytest

from pandas.compat.numpy import np_version_gte1p25

import pandas as pd
import pandas._testing as tm


class TestDataFrameUnaryOperators:
    # __pos__, __neg__, __invert__

    @pytest.mark.parametrize(
        "df,expected",
        [
            (pd.DataFrame({"a": [-1, 1]}), pd.DataFrame({"a": [1, -1]})),
            (pd.DataFrame({"a": [False, True]}), pd.DataFrame({"a": [True, False]})),
            (
                pd.DataFrame({"a": pd.Series(pd.to_timedelta([-1, 1]))}),
                pd.DataFrame({"a": pd.Series(pd.to_timedelta([1, -1]))}),
            ),
        ],
    )
    def test_neg_numeric(self, df, expected):
        tm.assert_frame_equal(-df, expected)
        tm.assert_series_equal(-df["a"], expected["a"])

    @pytest.mark.parametrize(
        "df, expected",
        [
            (np.array([1, 2], dtype=object), np.array([-1, -2], dtype=object)),
            ([Decimal("1.0"), Decimal("2.0")], [Decimal("-1.0"), Decimal("-2.0")]),
        ],
    )
    def test_neg_object(self, df, expected):
        # GH#21380
        df = pd.DataFrame({"a": df})
        expected = pd.DataFrame({"a": expected})
        tm.assert_frame_equal(-df, expected)
        tm.assert_series_equal(-df["a"], expected["a"])

    @pytest.mark.parametrize(
        "df",
        [
            pd.DataFrame({"a": ["a", "b"]}),
            pd.DataFrame({"a": pd.to_datetime(["2017-01-22", "1970-01-01"])}),
        ],
    )
    def test_neg_raises(self, df, using_infer_string):
        msg = (
            "bad operand type for unary -: 'str'|"
            r"bad operand type for unary -: 'DatetimeArray'|"
            "unary '-' not supported for dtype"
        )
        with pytest.raises(TypeError, match=msg):
            (-df)
        with pytest.raises(TypeError, match=msg):
            (-df["a"])

    def test_invert(self, float_frame):
        df = float_frame

        tm.assert_frame_equal(-(df < 0), ~(df < 0))

    def test_invert_mixed(self):
        shape = (10, 5)
        df = pd.concat(
            [
                pd.DataFrame(np.zeros(shape, dtype="bool")),
                pd.DataFrame(np.zeros(shape, dtype=int)),
            ],
            axis=1,
            ignore_index=True,
        )
        result = ~df
        expected = pd.concat(
            [
                pd.DataFrame(np.ones(shape, dtype="bool")),
                pd.DataFrame(-np.ones(shape, dtype=int)),
            ],
            axis=1,
            ignore_index=True,
        )
        tm.assert_frame_equal(result, expected)

    def test_invert_empty_not_input(self):
        # GH#51032
        df = pd.DataFrame()
        result = ~df
        tm.assert_frame_equal(df, result)
        assert df is not result

    @pytest.mark.parametrize(
        "df",
        [
            pd.DataFrame({"a": [-1, 1]}),
            pd.DataFrame({"a": [False, True]}),
            pd.DataFrame({"a": pd.Series(pd.to_timedelta([-1, 1]))}),
        ],
    )
    def test_pos_numeric(self, df):
        # GH#16073
        tm.assert_frame_equal(+df, df)
        tm.assert_series_equal(+df["a"], df["a"])

    @pytest.mark.parametrize(
        "df",
        [
            pd.DataFrame({"a": np.array([-1, 2], dtype=object)}),
            pd.DataFrame({"a": [Decimal("-1.0"), Decimal("2.0")]}),
        ],
    )
    def test_pos_object(self, df):
        # GH#21380
        tm.assert_frame_equal(+df, df)
        tm.assert_series_equal(+df["a"], df["a"])

    @pytest.mark.parametrize(
        "df",
        [
            pytest.param(
                pd.DataFrame({"a": ["a", "b"]}),
                # filterwarnings removable once min numpy version is 1.25
                marks=[
                    pytest.mark.filterwarnings("ignore:Applying:DeprecationWarning")
                ],
            ),
        ],
    )
    def test_pos_object_raises(self, df):
        # GH#21380
        if np_version_gte1p25:
            with pytest.raises(
                TypeError, match=r"^bad operand type for unary \+: \'str\'$"
            ):
                tm.assert_frame_equal(+df, df)
        else:
            tm.assert_series_equal(+df["a"], df["a"])

    @pytest.mark.parametrize(
        "df", [pd.DataFrame({"a": pd.to_datetime(["2017-01-22", "1970-01-01"])})]
    )
    def test_pos_raises(self, df):
        msg = r"bad operand type for unary \+: 'DatetimeArray'"
        with pytest.raises(TypeError, match=msg):
            (+df)
        with pytest.raises(TypeError, match=msg):
            (+df["a"])

    def test_unary_nullable(self):
        df = pd.DataFrame(
            {
                "a": pd.array([1, -2, 3, pd.NA], dtype="Int64"),
                "b": pd.array([4.0, -5.0, 6.0, pd.NA], dtype="Float32"),
                "c": pd.array([True, False, False, pd.NA], dtype="boolean"),
                # include numpy bool to make sure bool-vs-boolean behavior
                #  is consistent in non-NA locations
                "d": np.array([True, False, False, True]),
            }
        )

        result = +df
        res_ufunc = np.positive(df)
        expected = df
        # TODO: assert that we have copies?
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(res_ufunc, expected)

        result = -df
        res_ufunc = np.negative(df)
        expected = pd.DataFrame(
            {
                "a": pd.array([-1, 2, -3, pd.NA], dtype="Int64"),
                "b": pd.array([-4.0, 5.0, -6.0, pd.NA], dtype="Float32"),
                "c": pd.array([False, True, True, pd.NA], dtype="boolean"),
                "d": np.array([False, True, True, False]),
            }
        )
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(res_ufunc, expected)

        result = abs(df)
        res_ufunc = np.abs(df)
        expected = pd.DataFrame(
            {
                "a": pd.array([1, 2, 3, pd.NA], dtype="Int64"),
                "b": pd.array([4.0, 5.0, 6.0, pd.NA], dtype="Float32"),
                "c": pd.array([True, False, False, pd.NA], dtype="boolean"),
                "d": np.array([True, False, False, True]),
            }
        )
        tm.assert_frame_equal(result, expected)
        tm.assert_frame_equal(res_ufunc, expected)
