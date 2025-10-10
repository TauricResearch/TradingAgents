import datetime

import numpy as np
import pytest

from pandas.compat import (
    IS64,
    is_platform_windows,
)

from pandas import (
    Categorical,
    DataFrame,
    Series,
    date_range,
)
import pandas._testing as tm


class TestIteration:
    def test_keys(self, float_frame):
        assert float_frame.keys() is float_frame.columns

    def test_iteritems(self):
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=["a", "a", "b"])
        for k, v in df.items():
            assert isinstance(v, DataFrame._constructor_sliced)

    def test_items(self):
        # GH#17213, GH#13918
        cols = ["a", "b", "c"]
        df = DataFrame([[1, 2, 3], [4, 5, 6]], columns=cols)
        for c, (k, v) in zip(cols, df.items()):
            assert c == k
            assert isinstance(v, Series)
            assert (df[k] == v).all()

    def test_items_names(self, float_string_frame):
        for k, v in float_string_frame.items():
            assert v.name == k

    def test_iter(self, float_frame):
        assert list(float_frame) == list(float_frame.columns)

    def test_iterrows(self, float_frame, float_string_frame):
        for k, v in float_frame.iterrows():
            exp = float_frame.loc[k]
            tm.assert_series_equal(v, exp)

        for k, v in float_string_frame.iterrows():
            exp = float_string_frame.loc[k]
            tm.assert_series_equal(v, exp)

    def test_iterrows_iso8601(self):
        # GH#19671
        s = DataFrame(
            {
                "non_iso8601": ["M1701", "M1802", "M1903", "M2004"],
                "iso8601": date_range("2000-01-01", periods=4, freq="ME"),
            }
        )
        for k, v in s.iterrows():
            exp = s.loc[k]
            tm.assert_series_equal(v, exp)

    def test_iterrows_corner(self):
        # GH#12222
        df = DataFrame(
            {
                "a": [datetime.datetime(2015, 1, 1)],
                "b": [None],
                "c": [None],
                "d": [""],
                "e": [[]],
                "f": [set()],
                "g": [{}],
            }
        )
        expected = Series(
            [datetime.datetime(2015, 1, 1), None, None, "", [], set(), {}],
            index=list("abcdefg"),
            name=0,
            dtype="object",
        )
        _, result = next(df.iterrows())
        tm.assert_series_equal(result, expected)

    def test_itertuples(self, float_frame):
        for i, tup in enumerate(float_frame.itertuples()):
            ser = DataFrame._constructor_sliced(tup[1:])
            ser.name = tup[0]
            expected = float_frame.iloc[i, :].reset_index(drop=True)
            tm.assert_series_equal(ser, expected)

    def test_itertuples_index_false(self):
        df = DataFrame(
            {"floats": np.random.default_rng(2).standard_normal(5), "ints": range(5)},
            columns=["floats", "ints"],
        )

        for tup in df.itertuples(index=False):
            assert isinstance(tup[1], int)

    def test_itertuples_duplicate_cols(self):
        df = DataFrame(data={"a": [1, 2, 3], "b": [4, 5, 6]})
        dfaa = df[["a", "a"]]

        assert list(dfaa.itertuples()) == [(0, 1, 1), (1, 2, 2), (2, 3, 3)]

        # repr with int on 32-bit/windows
        if not (is_platform_windows() or not IS64):
            assert (
                repr(list(df.itertuples(name=None)))
                == "[(0, 1, 4), (1, 2, 5), (2, 3, 6)]"
            )

    def test_itertuples_tuple_name(self):
        df = DataFrame(data={"a": [1, 2, 3], "b": [4, 5, 6]})
        tup = next(df.itertuples(name="TestName"))
        assert tup._fields == ("Index", "a", "b")
        assert (tup.Index, tup.a, tup.b) == tup
        assert type(tup).__name__ == "TestName"

    def test_itertuples_disallowed_col_labels(self):
        df = DataFrame(data={"def": [1, 2, 3], "return": [4, 5, 6]})
        tup2 = next(df.itertuples(name="TestName"))
        assert tup2 == (0, 1, 4)
        assert tup2._fields == ("Index", "_1", "_2")

    @pytest.mark.parametrize("limit", [254, 255, 1024])
    @pytest.mark.parametrize("index", [True, False])
    def test_itertuples_py2_3_field_limit_namedtuple(self, limit, index):
        # GH#28282
        df = DataFrame([{f"foo_{i}": f"bar_{i}" for i in range(limit)}])
        result = next(df.itertuples(index=index))
        assert isinstance(result, tuple)
        assert hasattr(result, "_fields")

    def test_sequence_like_with_categorical(self):
        # GH#7839
        # make sure can iterate
        df = DataFrame(
            {"id": [1, 2, 3, 4, 5, 6], "raw_grade": ["a", "b", "b", "a", "a", "e"]}
        )
        df["grade"] = Categorical(df["raw_grade"])

        # basic sequencing testing
        result = list(df.grade.values)
        expected = np.array(df.grade.values).tolist()
        tm.assert_almost_equal(result, expected)

        # iteration
        for t in df.itertuples(index=False):
            str(t)

        for row, s in df.iterrows():
            str(s)

        for c, col in df.items():
            str(col)
