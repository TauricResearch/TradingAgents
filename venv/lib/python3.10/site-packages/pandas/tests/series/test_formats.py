from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

import pandas as pd
from pandas import (
    Categorical,
    DataFrame,
    Index,
    Series,
    date_range,
    option_context,
    period_range,
    timedelta_range,
)
import pandas._testing as tm


class TestSeriesRepr:
    def test_multilevel_name_print_0(self):
        # GH#55415 None does not get printed, but 0 does
        # (matching DataFrame and flat index behavior)
        mi = pd.MultiIndex.from_product([range(2, 3), range(3, 4)], names=[0, None])
        ser = Series(1.5, index=mi)

        res = repr(ser)
        expected = "0   \n2  3    1.5\ndtype: float64"
        assert res == expected

    def test_multilevel_name_print(self, lexsorted_two_level_string_multiindex):
        index = lexsorted_two_level_string_multiindex
        ser = Series(range(len(index)), index=index, name="sth")
        expected = [
            "first  second",
            "foo    one       0",
            "       two       1",
            "       three     2",
            "bar    one       3",
            "       two       4",
            "baz    two       5",
            "       three     6",
            "qux    one       7",
            "       two       8",
            "       three     9",
            "Name: sth, dtype: int64",
        ]
        expected = "\n".join(expected)
        assert repr(ser) == expected

    def test_small_name_printing(self):
        # Test small Series.
        s = Series([0, 1, 2])

        s.name = "test"
        assert "Name: test" in repr(s)

        s.name = None
        assert "Name:" not in repr(s)

    def test_big_name_printing(self):
        # Test big Series (diff code path).
        s = Series(range(1000))

        s.name = "test"
        assert "Name: test" in repr(s)

        s.name = None
        assert "Name:" not in repr(s)

    def test_empty_name_printing(self):
        s = Series(index=date_range("20010101", "20020101"), name="test", dtype=object)
        assert "Name: test" in repr(s)

    @pytest.mark.parametrize("args", [(), (0, -1)])
    def test_float_range(self, args):
        str(
            Series(
                np.random.default_rng(2).standard_normal(1000),
                index=np.arange(1000, *args),
            )
        )

    def test_empty_object(self):
        # empty
        str(Series(dtype=object))

    def test_string(self, string_series):
        str(string_series)
        str(string_series.astype(int))

        # with NaNs
        string_series[5:7] = np.nan
        str(string_series)

    def test_object(self, object_series):
        str(object_series)

    def test_datetime(self, datetime_series):
        str(datetime_series)
        # with Nones
        ots = datetime_series.astype("O")
        ots[::2] = None
        repr(ots)

    @pytest.mark.parametrize(
        "name",
        [
            "",
            1,
            1.2,
            "foo",
            "\u03B1\u03B2\u03B3",
            "loooooooooooooooooooooooooooooooooooooooooooooooooooong",
            ("foo", "bar", "baz"),
            (1, 2),
            ("foo", 1, 2.3),
            ("\u03B1", "\u03B2", "\u03B3"),
            ("\u03B1", "bar"),
        ],
    )
    def test_various_names(self, name, string_series):
        # various names
        string_series.name = name
        repr(string_series)

    def test_tuple_name(self):
        biggie = Series(
            np.random.default_rng(2).standard_normal(1000),
            index=np.arange(1000),
            name=("foo", "bar", "baz"),
        )
        repr(biggie)

    @pytest.mark.parametrize("arg", [100, 1001])
    def test_tidy_repr_name_0(self, arg):
        # tidy repr
        ser = Series(np.random.default_rng(2).standard_normal(arg), name=0)
        rep_str = repr(ser)
        assert "Name: 0" in rep_str

    def test_newline(self, any_string_dtype):
        ser = Series(
            ["a\n\r\tb"],
            name="a\n\r\td",
            index=Index(["a\n\r\tf"], dtype=any_string_dtype),
            dtype=any_string_dtype,
        )
        assert "\t" not in repr(ser)
        assert "\r" not in repr(ser)
        assert "a\n" not in repr(ser)

    @pytest.mark.parametrize(
        "name, expected",
        [
            ["foo", "Series([], Name: foo, dtype: int64)"],
            [None, "Series([], dtype: int64)"],
        ],
    )
    def test_empty_int64(self, name, expected):
        # with empty series (#4651)
        s = Series([], dtype=np.int64, name=name)
        assert repr(s) == expected

    def test_repr_bool_fails(self, capsys):
        s = Series(
            [
                DataFrame(np.random.default_rng(2).standard_normal((2, 2)))
                for i in range(5)
            ]
        )

        # It works (with no Cython exception barf)!
        repr(s)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_repr_name_iterable_indexable(self):
        s = Series([1, 2, 3], name=np.int64(3))

        # it works!
        repr(s)

        s.name = ("\u05d0",) * 2
        repr(s)

    def test_repr_max_rows(self):
        # GH 6863
        with option_context("display.max_rows", None):
            str(Series(range(1001)))  # should not raise exception

    def test_unicode_string_with_unicode(self):
        df = Series(["\u05d0"], name="\u05d1")
        str(df)

        ser = Series(["\u03c3"] * 10)
        repr(ser)

        ser2 = Series(["\u05d0"] * 1000)
        ser2.name = "title1"
        repr(ser2)

    def test_str_to_bytes_raises(self):
        # GH 26447
        df = Series(["abc"], name="abc")
        msg = "^'str' object cannot be interpreted as an integer$"
        with pytest.raises(TypeError, match=msg):
            bytes(df)

    def test_timeseries_repr_object_dtype(self):
        index = Index(
            [datetime(2000, 1, 1) + timedelta(i) for i in range(1000)], dtype=object
        )
        ts = Series(np.random.default_rng(2).standard_normal(len(index)), index)
        repr(ts)

        ts = Series(
            np.arange(20, dtype=np.float64), index=date_range("2020-01-01", periods=20)
        )
        assert repr(ts).splitlines()[-1].startswith("Freq:")

        ts2 = ts.iloc[np.random.default_rng(2).integers(0, len(ts) - 1, 400)]
        repr(ts2).splitlines()[-1]

    def test_latex_repr(self):
        pytest.importorskip("jinja2")  # uses Styler implementation
        result = r"""\begin{tabular}{ll}
\toprule
 & 0 \\
\midrule
0 & $\alpha$ \\
1 & b \\
2 & c \\
\bottomrule
\end{tabular}
"""
        with option_context(
            "styler.format.escape", None, "styler.render.repr", "latex"
        ):
            s = Series([r"$\alpha$", "b", "c"])
            assert result == s._repr_latex_()

        assert s._repr_latex_() is None

    def test_index_repr_in_frame_with_nan(self):
        # see gh-25061
        i = Index([1, np.nan])
        s = Series([1, 2], index=i)
        exp = """1.0    1\nNaN    2\ndtype: int64"""

        assert repr(s) == exp

    def test_format_pre_1900_dates(self):
        rng = date_range("1/1/1850", "1/1/1950", freq="YE-DEC")
        msg = "DatetimeIndex.format is deprecated"
        with tm.assert_produces_warning(FutureWarning, match=msg):
            rng.format()
        ts = Series(1, index=rng)
        repr(ts)

    def test_series_repr_nat(self):
        series = Series([0, 1000, 2000, pd.NaT._value], dtype="M8[ns]")

        result = repr(series)
        expected = (
            "0   1970-01-01 00:00:00.000000\n"
            "1   1970-01-01 00:00:00.000001\n"
            "2   1970-01-01 00:00:00.000002\n"
            "3                          NaT\n"
            "dtype: datetime64[ns]"
        )
        assert result == expected

    def test_float_repr(self):
        # GH#35603
        # check float format when cast to object
        ser = Series([1.0]).astype(object)
        expected = "0    1.0\ndtype: object"
        assert repr(ser) == expected

    def test_different_null_objects(self):
        # GH#45263
        ser = Series([1, 2, 3, 4], [True, None, np.nan, pd.NaT])
        result = repr(ser)
        expected = "True    1\nNone    2\nNaN     3\nNaT     4\ndtype: int64"
        assert result == expected


class TestCategoricalRepr:
    def test_categorical_repr_unicode(self):
        # see gh-21002

        class County:
            name = "San Sebastián"
            state = "PR"

            def __repr__(self) -> str:
                return self.name + ", " + self.state

        cat = Categorical([County() for _ in range(61)])
        idx = Index(cat)
        ser = idx.to_series()

        repr(ser)
        str(ser)

    def test_categorical_repr(self, using_infer_string):
        a = Series(Categorical([1, 2, 3, 4]))
        exp = (
            "0    1\n1    2\n2    3\n3    4\n"
            "dtype: category\nCategories (4, int64): [1, 2, 3, 4]"
        )

        assert exp == a.__str__()

        a = Series(Categorical(["a", "b"] * 25))
        exp = (
            "0     a\n1     b\n"
            "     ..\n"
            "48    a\n49    b\n"
            "Length: 50, dtype: category\nCategories (2, object): ['a', 'b']"
        )
        if using_infer_string:
            exp = exp.replace("object", "str")
        with option_context("display.max_rows", 5):
            assert exp == repr(a)

        levs = list("abcdefghijklmnopqrstuvwxyz")
        a = Series(Categorical(["a", "b"], categories=levs, ordered=True))
        exp = (
            "0    a\n1    b\n"
            "dtype: category\n"
            "Categories (26, object): ['a' < 'b' < 'c' < 'd' ... "
            "'w' < 'x' < 'y' < 'z']"
        )
        if using_infer_string:
            exp = exp.replace("object", "str")
        assert exp == a.__str__()

    def test_categorical_series_repr(self):
        s = Series(Categorical([1, 2, 3]))
        exp = """0    1
1    2
2    3
dtype: category
Categories (3, int64): [1, 2, 3]"""

        assert repr(s) == exp

        s = Series(Categorical(np.arange(10)))
        exp = f"""0    0
1    1
2    2
3    3
4    4
5    5
6    6
7    7
8    8
9    9
dtype: category
Categories (10, {np.dtype(int)}): [0, 1, 2, 3, ..., 6, 7, 8, 9]"""

        assert repr(s) == exp

    def test_categorical_series_repr_ordered(self):
        s = Series(Categorical([1, 2, 3], ordered=True))
        exp = """0    1
1    2
2    3
dtype: category
Categories (3, int64): [1 < 2 < 3]"""

        assert repr(s) == exp

        s = Series(Categorical(np.arange(10), ordered=True))
        exp = f"""0    0
1    1
2    2
3    3
4    4
5    5
6    6
7    7
8    8
9    9
dtype: category
Categories (10, {np.dtype(int)}): [0 < 1 < 2 < 3 ... 6 < 7 < 8 < 9]"""

        assert repr(s) == exp

    def test_categorical_series_repr_datetime(self):
        idx = date_range("2011-01-01 09:00", freq="h", periods=5)
        s = Series(Categorical(idx))
        exp = """0   2011-01-01 09:00:00
1   2011-01-01 10:00:00
2   2011-01-01 11:00:00
3   2011-01-01 12:00:00
4   2011-01-01 13:00:00
dtype: category
Categories (5, datetime64[ns]): [2011-01-01 09:00:00, 2011-01-01 10:00:00, 2011-01-01 11:00:00,
                                 2011-01-01 12:00:00, 2011-01-01 13:00:00]"""  # noqa: E501

        assert repr(s) == exp

        idx = date_range("2011-01-01 09:00", freq="h", periods=5, tz="US/Eastern")
        s = Series(Categorical(idx))
        exp = """0   2011-01-01 09:00:00-05:00
1   2011-01-01 10:00:00-05:00
2   2011-01-01 11:00:00-05:00
3   2011-01-01 12:00:00-05:00
4   2011-01-01 13:00:00-05:00
dtype: category
Categories (5, datetime64[ns, US/Eastern]): [2011-01-01 09:00:00-05:00, 2011-01-01 10:00:00-05:00,
                                             2011-01-01 11:00:00-05:00, 2011-01-01 12:00:00-05:00,
                                             2011-01-01 13:00:00-05:00]"""  # noqa: E501

        assert repr(s) == exp

    def test_categorical_series_repr_datetime_ordered(self):
        idx = date_range("2011-01-01 09:00", freq="h", periods=5)
        s = Series(Categorical(idx, ordered=True))
        exp = """0   2011-01-01 09:00:00
1   2011-01-01 10:00:00
2   2011-01-01 11:00:00
3   2011-01-01 12:00:00
4   2011-01-01 13:00:00
dtype: category
Categories (5, datetime64[ns]): [2011-01-01 09:00:00 < 2011-01-01 10:00:00 < 2011-01-01 11:00:00 <
                                 2011-01-01 12:00:00 < 2011-01-01 13:00:00]"""  # noqa: E501

        assert repr(s) == exp

        idx = date_range("2011-01-01 09:00", freq="h", periods=5, tz="US/Eastern")
        s = Series(Categorical(idx, ordered=True))
        exp = """0   2011-01-01 09:00:00-05:00
1   2011-01-01 10:00:00-05:00
2   2011-01-01 11:00:00-05:00
3   2011-01-01 12:00:00-05:00
4   2011-01-01 13:00:00-05:00
dtype: category
Categories (5, datetime64[ns, US/Eastern]): [2011-01-01 09:00:00-05:00 < 2011-01-01 10:00:00-05:00 <
                                             2011-01-01 11:00:00-05:00 < 2011-01-01 12:00:00-05:00 <
                                             2011-01-01 13:00:00-05:00]"""  # noqa: E501

        assert repr(s) == exp

    def test_categorical_series_repr_period(self):
        idx = period_range("2011-01-01 09:00", freq="h", periods=5)
        s = Series(Categorical(idx))
        exp = """0    2011-01-01 09:00
1    2011-01-01 10:00
2    2011-01-01 11:00
3    2011-01-01 12:00
4    2011-01-01 13:00
dtype: category
Categories (5, period[h]): [2011-01-01 09:00, 2011-01-01 10:00, 2011-01-01 11:00, 2011-01-01 12:00,
                            2011-01-01 13:00]"""  # noqa: E501

        assert repr(s) == exp

        idx = period_range("2011-01", freq="M", periods=5)
        s = Series(Categorical(idx))
        exp = """0    2011-01
1    2011-02
2    2011-03
3    2011-04
4    2011-05
dtype: category
Categories (5, period[M]): [2011-01, 2011-02, 2011-03, 2011-04, 2011-05]"""

        assert repr(s) == exp

    def test_categorical_series_repr_period_ordered(self):
        idx = period_range("2011-01-01 09:00", freq="h", periods=5)
        s = Series(Categorical(idx, ordered=True))
        exp = """0    2011-01-01 09:00
1    2011-01-01 10:00
2    2011-01-01 11:00
3    2011-01-01 12:00
4    2011-01-01 13:00
dtype: category
Categories (5, period[h]): [2011-01-01 09:00 < 2011-01-01 10:00 < 2011-01-01 11:00 < 2011-01-01 12:00 <
                            2011-01-01 13:00]"""  # noqa: E501

        assert repr(s) == exp

        idx = period_range("2011-01", freq="M", periods=5)
        s = Series(Categorical(idx, ordered=True))
        exp = """0    2011-01
1    2011-02
2    2011-03
3    2011-04
4    2011-05
dtype: category
Categories (5, period[M]): [2011-01 < 2011-02 < 2011-03 < 2011-04 < 2011-05]"""

        assert repr(s) == exp

    def test_categorical_series_repr_timedelta(self):
        idx = timedelta_range("1 days", periods=5)
        s = Series(Categorical(idx))
        exp = """0   1 days
1   2 days
2   3 days
3   4 days
4   5 days
dtype: category
Categories (5, timedelta64[ns]): [1 days, 2 days, 3 days, 4 days, 5 days]"""

        assert repr(s) == exp

        idx = timedelta_range("1 hours", periods=10)
        s = Series(Categorical(idx))
        exp = """0   0 days 01:00:00
1   1 days 01:00:00
2   2 days 01:00:00
3   3 days 01:00:00
4   4 days 01:00:00
5   5 days 01:00:00
6   6 days 01:00:00
7   7 days 01:00:00
8   8 days 01:00:00
9   9 days 01:00:00
dtype: category
Categories (10, timedelta64[ns]): [0 days 01:00:00, 1 days 01:00:00, 2 days 01:00:00,
                                   3 days 01:00:00, ..., 6 days 01:00:00, 7 days 01:00:00,
                                   8 days 01:00:00, 9 days 01:00:00]"""  # noqa: E501

        assert repr(s) == exp

    def test_categorical_series_repr_timedelta_ordered(self):
        idx = timedelta_range("1 days", periods=5)
        s = Series(Categorical(idx, ordered=True))
        exp = """0   1 days
1   2 days
2   3 days
3   4 days
4   5 days
dtype: category
Categories (5, timedelta64[ns]): [1 days < 2 days < 3 days < 4 days < 5 days]"""

        assert repr(s) == exp

        idx = timedelta_range("1 hours", periods=10)
        s = Series(Categorical(idx, ordered=True))
        exp = """0   0 days 01:00:00
1   1 days 01:00:00
2   2 days 01:00:00
3   3 days 01:00:00
4   4 days 01:00:00
5   5 days 01:00:00
6   6 days 01:00:00
7   7 days 01:00:00
8   8 days 01:00:00
9   9 days 01:00:00
dtype: category
Categories (10, timedelta64[ns]): [0 days 01:00:00 < 1 days 01:00:00 < 2 days 01:00:00 <
                                   3 days 01:00:00 ... 6 days 01:00:00 < 7 days 01:00:00 <
                                   8 days 01:00:00 < 9 days 01:00:00]"""  # noqa: E501

        assert repr(s) == exp
