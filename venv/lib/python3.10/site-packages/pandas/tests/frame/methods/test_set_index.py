"""
See also: test_reindex.py:TestReindexSetIndex
"""

from datetime import (
    datetime,
    timedelta,
)

import numpy as np
import pytest

from pandas import (
    Categorical,
    CategoricalIndex,
    DataFrame,
    DatetimeIndex,
    Index,
    MultiIndex,
    Series,
    date_range,
    period_range,
    to_datetime,
)
import pandas._testing as tm


@pytest.fixture
def frame_of_index_cols():
    """
    Fixture for DataFrame of columns that can be used for indexing

    Columns are ['A', 'B', 'C', 'D', 'E', ('tuple', 'as', 'label')];
    'A' & 'B' contain duplicates (but are jointly unique), the rest are unique.

         A      B  C         D         E  (tuple, as, label)
    0  foo    one  a  0.608477 -0.012500           -1.664297
    1  foo    two  b -0.633460  0.249614           -0.364411
    2  foo  three  c  0.615256  2.154968           -0.834666
    3  bar    one  d  0.234246  1.085675            0.718445
    4  bar    two  e  0.533841 -0.005702           -3.533912
    """
    df = DataFrame(
        {
            "A": ["foo", "foo", "foo", "bar", "bar"],
            "B": ["one", "two", "three", "one", "two"],
            "C": ["a", "b", "c", "d", "e"],
            "D": np.random.default_rng(2).standard_normal(5),
            "E": np.random.default_rng(2).standard_normal(5),
            ("tuple", "as", "label"): np.random.default_rng(2).standard_normal(5),
        }
    )
    return df


class TestSetIndex:
    def test_set_index_multiindex(self):
        # segfault in GH#3308
        d = {"t1": [2, 2.5, 3], "t2": [4, 5, 6]}
        df = DataFrame(d)
        tuples = [(0, 1), (0, 2), (1, 2)]
        df["tuples"] = tuples

        index = MultiIndex.from_tuples(df["tuples"])
        # it works!
        df.set_index(index)

    def test_set_index_empty_column(self):
        # GH#1971
        df = DataFrame(
            [
                {"a": 1, "p": 0},
                {"a": 2, "m": 10},
                {"a": 3, "m": 11, "p": 20},
                {"a": 4, "m": 12, "p": 21},
            ],
            columns=["a", "m", "p", "x"],
        )

        result = df.set_index(["a", "x"])

        expected = df[["m", "p"]]
        expected.index = MultiIndex.from_arrays([df["a"], df["x"]], names=["a", "x"])
        tm.assert_frame_equal(result, expected)

    def test_set_index_empty_dataframe(self):
        # GH#38419
        df1 = DataFrame(
            {"a": Series(dtype="datetime64[ns]"), "b": Series(dtype="int64"), "c": []}
        )

        df2 = df1.set_index(["a", "b"])
        result = df2.index.to_frame().dtypes
        expected = df1[["a", "b"]].dtypes
        tm.assert_series_equal(result, expected)

    def test_set_index_multiindexcolumns(self):
        columns = MultiIndex.from_tuples([("foo", 1), ("foo", 2), ("bar", 1)])
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)), columns=columns
        )

        result = df.set_index(df.columns[0])

        expected = df.iloc[:, 1:]
        expected.index = df.iloc[:, 0].values
        expected.index.names = [df.columns[0]]
        tm.assert_frame_equal(result, expected)

    def test_set_index_timezone(self):
        # GH#12358
        # tz-aware Series should retain the tz
        idx = DatetimeIndex(["2014-01-01 10:10:10"], tz="UTC").tz_convert("Europe/Rome")
        df = DataFrame({"A": idx})
        assert df.set_index(idx).index[0].hour == 11
        assert DatetimeIndex(Series(df.A))[0].hour == 11
        assert df.set_index(df.A).index[0].hour == 11

    def test_set_index_cast_datetimeindex(self):
        df = DataFrame(
            {
                "A": [datetime(2000, 1, 1) + timedelta(i) for i in range(1000)],
                "B": np.random.default_rng(2).standard_normal(1000),
            }
        )

        idf = df.set_index("A")
        assert isinstance(idf.index, DatetimeIndex)

    def test_set_index_dst(self):
        di = date_range("2006-10-29 00:00:00", periods=3, freq="h", tz="US/Pacific")

        df = DataFrame(data={"a": [0, 1, 2], "b": [3, 4, 5]}, index=di).reset_index()
        # single level
        res = df.set_index("index")
        exp = DataFrame(
            data={"a": [0, 1, 2], "b": [3, 4, 5]},
            index=Index(di, name="index"),
        )
        exp.index = exp.index._with_freq(None)
        tm.assert_frame_equal(res, exp)

        # GH#12920
        res = df.set_index(["index", "a"])
        exp_index = MultiIndex.from_arrays([di, [0, 1, 2]], names=["index", "a"])
        exp = DataFrame({"b": [3, 4, 5]}, index=exp_index)
        tm.assert_frame_equal(res, exp)

    def test_set_index(self, float_string_frame):
        df = float_string_frame
        idx = Index(np.arange(len(df))[::-1])

        df = df.set_index(idx)
        tm.assert_index_equal(df.index, idx)
        with pytest.raises(ValueError, match="Length mismatch"):
            df.set_index(idx[::2])

    def test_set_index_names(self):
        df = DataFrame(
            np.ones((10, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(10)]),
        )
        df.index.name = "name"

        assert df.set_index(df.index).index.names == ["name"]

        mi = MultiIndex.from_arrays(df[["A", "B"]].T.values, names=["A", "B"])
        mi2 = MultiIndex.from_arrays(
            df[["A", "B", "A", "B"]].T.values, names=["A", "B", "C", "D"]
        )

        df = df.set_index(["A", "B"])

        assert df.set_index(df.index).index.names == ["A", "B"]

        # Check that set_index isn't converting a MultiIndex into an Index
        assert isinstance(df.set_index(df.index).index, MultiIndex)

        # Check actual equality
        tm.assert_index_equal(df.set_index(df.index).index, mi)

        idx2 = df.index.rename(["C", "D"])

        # Check that [MultiIndex, MultiIndex] yields a MultiIndex rather
        # than a pair of tuples
        assert isinstance(df.set_index([df.index, idx2]).index, MultiIndex)

        # Check equality
        tm.assert_index_equal(df.set_index([df.index, idx2]).index, mi2)

    # A has duplicate values, C does not
    @pytest.mark.parametrize("keys", ["A", "C", ["A", "B"], ("tuple", "as", "label")])
    @pytest.mark.parametrize("inplace", [True, False])
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_drop_inplace(self, frame_of_index_cols, drop, inplace, keys):
        df = frame_of_index_cols

        if isinstance(keys, list):
            idx = MultiIndex.from_arrays([df[x] for x in keys], names=keys)
        else:
            idx = Index(df[keys], name=keys)
        expected = df.drop(keys, axis=1) if drop else df
        expected.index = idx

        if inplace:
            result = df.copy()
            return_value = result.set_index(keys, drop=drop, inplace=True)
            assert return_value is None
        else:
            result = df.set_index(keys, drop=drop)

        tm.assert_frame_equal(result, expected)

    # A has duplicate values, C does not
    @pytest.mark.parametrize("keys", ["A", "C", ["A", "B"], ("tuple", "as", "label")])
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_append(self, frame_of_index_cols, drop, keys):
        df = frame_of_index_cols

        keys = keys if isinstance(keys, list) else [keys]
        idx = MultiIndex.from_arrays(
            [df.index] + [df[x] for x in keys], names=[None] + keys
        )
        expected = df.drop(keys, axis=1) if drop else df.copy()
        expected.index = idx

        result = df.set_index(keys, drop=drop, append=True)

        tm.assert_frame_equal(result, expected)

    # A has duplicate values, C does not
    @pytest.mark.parametrize("keys", ["A", "C", ["A", "B"], ("tuple", "as", "label")])
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_append_to_multiindex(self, frame_of_index_cols, drop, keys):
        # append to existing multiindex
        df = frame_of_index_cols.set_index(["D"], drop=drop, append=True)

        keys = keys if isinstance(keys, list) else [keys]
        expected = frame_of_index_cols.set_index(["D"] + keys, drop=drop, append=True)

        result = df.set_index(keys, drop=drop, append=True)

        tm.assert_frame_equal(result, expected)

    def test_set_index_after_mutation(self):
        # GH#1590
        df = DataFrame({"val": [0, 1, 2], "key": ["a", "b", "c"]})
        expected = DataFrame({"val": [1, 2]}, Index(["b", "c"], name="key"))

        df2 = df.loc[df.index.map(lambda indx: indx >= 1)]
        result = df2.set_index("key")
        tm.assert_frame_equal(result, expected)

    # MultiIndex constructor does not work directly on Series -> lambda
    # Add list-of-list constructor because list is ambiguous -> lambda
    # also test index name if append=True (name is duplicate here for B)
    @pytest.mark.parametrize(
        "box",
        [
            Series,
            Index,
            np.array,
            list,
            lambda x: [list(x)],
            lambda x: MultiIndex.from_arrays([x]),
        ],
    )
    @pytest.mark.parametrize(
        "append, index_name", [(True, None), (True, "B"), (True, "test"), (False, None)]
    )
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_pass_single_array(
        self, frame_of_index_cols, drop, append, index_name, box
    ):
        df = frame_of_index_cols
        df.index.name = index_name

        key = box(df["B"])
        if box == list:
            # list of strings gets interpreted as list of keys
            msg = "['one', 'two', 'three', 'one', 'two']"
            with pytest.raises(KeyError, match=msg):
                df.set_index(key, drop=drop, append=append)
        else:
            # np.array/list-of-list "forget" the name of B
            name_mi = getattr(key, "names", None)
            name = [getattr(key, "name", None)] if name_mi is None else name_mi

            result = df.set_index(key, drop=drop, append=append)

            # only valid column keys are dropped
            # since B is always passed as array above, nothing is dropped
            expected = df.set_index(["B"], drop=False, append=append)
            expected.index.names = [index_name] + name if append else name

            tm.assert_frame_equal(result, expected)

    # MultiIndex constructor does not work directly on Series -> lambda
    # also test index name if append=True (name is duplicate here for A & B)
    @pytest.mark.parametrize(
        "box", [Series, Index, np.array, list, lambda x: MultiIndex.from_arrays([x])]
    )
    @pytest.mark.parametrize(
        "append, index_name",
        [(True, None), (True, "A"), (True, "B"), (True, "test"), (False, None)],
    )
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_pass_arrays(
        self, frame_of_index_cols, drop, append, index_name, box
    ):
        df = frame_of_index_cols
        df.index.name = index_name

        keys = ["A", box(df["B"])]
        # np.array/list "forget" the name of B
        names = ["A", None if box in [np.array, list, tuple, iter] else "B"]

        result = df.set_index(keys, drop=drop, append=append)

        # only valid column keys are dropped
        # since B is always passed as array above, only A is dropped, if at all
        expected = df.set_index(["A", "B"], drop=False, append=append)
        expected = expected.drop("A", axis=1) if drop else expected
        expected.index.names = [index_name] + names if append else names

        tm.assert_frame_equal(result, expected)

    # MultiIndex constructor does not work directly on Series -> lambda
    # We also emulate a "constructor" for the label -> lambda
    # also test index name if append=True (name is duplicate here for A)
    @pytest.mark.parametrize(
        "box2",
        [
            Series,
            Index,
            np.array,
            list,
            iter,
            lambda x: MultiIndex.from_arrays([x]),
            lambda x: x.name,
        ],
    )
    @pytest.mark.parametrize(
        "box1",
        [
            Series,
            Index,
            np.array,
            list,
            iter,
            lambda x: MultiIndex.from_arrays([x]),
            lambda x: x.name,
        ],
    )
    @pytest.mark.parametrize(
        "append, index_name", [(True, None), (True, "A"), (True, "test"), (False, None)]
    )
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_pass_arrays_duplicate(
        self, frame_of_index_cols, drop, append, index_name, box1, box2
    ):
        df = frame_of_index_cols
        df.index.name = index_name

        keys = [box1(df["A"]), box2(df["A"])]
        result = df.set_index(keys, drop=drop, append=append)

        # if either box is iter, it has been consumed; re-read
        keys = [box1(df["A"]), box2(df["A"])]

        # need to adapt first drop for case that both keys are 'A' --
        # cannot drop the same column twice;
        # plain == would give ambiguous Boolean error for containers
        first_drop = (
            False
            if (
                isinstance(keys[0], str)
                and keys[0] == "A"
                and isinstance(keys[1], str)
                and keys[1] == "A"
            )
            else drop
        )
        # to test against already-tested behaviour, we add sequentially,
        # hence second append always True; must wrap keys in list, otherwise
        # box = list would be interpreted as keys
        expected = df.set_index([keys[0]], drop=first_drop, append=append)
        expected = expected.set_index([keys[1]], drop=drop, append=True)
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize("append", [True, False])
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_pass_multiindex(self, frame_of_index_cols, drop, append):
        df = frame_of_index_cols
        keys = MultiIndex.from_arrays([df["A"], df["B"]], names=["A", "B"])

        result = df.set_index(keys, drop=drop, append=append)

        # setting with a MultiIndex will never drop columns
        expected = df.set_index(["A", "B"], drop=False, append=append)

        tm.assert_frame_equal(result, expected)

    def test_construction_with_categorical_index(self):
        ci = CategoricalIndex(list("ab") * 5, name="B")

        # with Categorical
        df = DataFrame(
            {"A": np.random.default_rng(2).standard_normal(10), "B": ci.values}
        )
        idf = df.set_index("B")
        tm.assert_index_equal(idf.index, ci)

        # from a CategoricalIndex
        df = DataFrame({"A": np.random.default_rng(2).standard_normal(10), "B": ci})
        idf = df.set_index("B")
        tm.assert_index_equal(idf.index, ci)

        # round-trip
        idf = idf.reset_index().set_index("B")
        tm.assert_index_equal(idf.index, ci)

    def test_set_index_preserve_categorical_dtype(self):
        # GH#13743, GH#13854
        df = DataFrame(
            {
                "A": [1, 2, 1, 1, 2],
                "B": [10, 16, 22, 28, 34],
                "C1": Categorical(list("abaab"), categories=list("bac"), ordered=False),
                "C2": Categorical(list("abaab"), categories=list("bac"), ordered=True),
            }
        )
        for cols in ["C1", "C2", ["A", "C1"], ["A", "C2"], ["C1", "C2"]]:
            result = df.set_index(cols).reset_index()
            result = result.reindex(columns=df.columns)
            tm.assert_frame_equal(result, df)

    def test_set_index_datetime(self):
        # GH#3950
        df = DataFrame(
            {
                "label": ["a", "a", "a", "b", "b", "b"],
                "datetime": [
                    "2011-07-19 07:00:00",
                    "2011-07-19 08:00:00",
                    "2011-07-19 09:00:00",
                    "2011-07-19 07:00:00",
                    "2011-07-19 08:00:00",
                    "2011-07-19 09:00:00",
                ],
                "value": range(6),
            }
        )
        df.index = to_datetime(df.pop("datetime"), utc=True)
        df.index = df.index.tz_convert("US/Pacific")

        expected = DatetimeIndex(
            ["2011-07-19 07:00:00", "2011-07-19 08:00:00", "2011-07-19 09:00:00"],
            name="datetime",
        )
        expected = expected.tz_localize("UTC").tz_convert("US/Pacific")

        df = df.set_index("label", append=True)
        tm.assert_index_equal(df.index.levels[0], expected)
        tm.assert_index_equal(df.index.levels[1], Index(["a", "b"], name="label"))
        assert df.index.names == ["datetime", "label"]

        df = df.swaplevel(0, 1)
        tm.assert_index_equal(df.index.levels[0], Index(["a", "b"], name="label"))
        tm.assert_index_equal(df.index.levels[1], expected)
        assert df.index.names == ["label", "datetime"]

        df = DataFrame(np.random.default_rng(2).random(6))
        idx1 = DatetimeIndex(
            [
                "2011-07-19 07:00:00",
                "2011-07-19 08:00:00",
                "2011-07-19 09:00:00",
                "2011-07-19 07:00:00",
                "2011-07-19 08:00:00",
                "2011-07-19 09:00:00",
            ],
            tz="US/Eastern",
        )
        idx2 = DatetimeIndex(
            [
                "2012-04-01 09:00",
                "2012-04-01 09:00",
                "2012-04-01 09:00",
                "2012-04-02 09:00",
                "2012-04-02 09:00",
                "2012-04-02 09:00",
            ],
            tz="US/Eastern",
        )
        idx3 = date_range("2011-01-01 09:00", periods=6, tz="Asia/Tokyo")
        idx3 = idx3._with_freq(None)

        df = df.set_index(idx1)
        df = df.set_index(idx2, append=True)
        df = df.set_index(idx3, append=True)

        expected1 = DatetimeIndex(
            ["2011-07-19 07:00:00", "2011-07-19 08:00:00", "2011-07-19 09:00:00"],
            tz="US/Eastern",
        )
        expected2 = DatetimeIndex(
            ["2012-04-01 09:00", "2012-04-02 09:00"], tz="US/Eastern"
        )

        tm.assert_index_equal(df.index.levels[0], expected1)
        tm.assert_index_equal(df.index.levels[1], expected2)
        tm.assert_index_equal(df.index.levels[2], idx3)

        # GH#7092
        tm.assert_index_equal(df.index.get_level_values(0), idx1)
        tm.assert_index_equal(df.index.get_level_values(1), idx2)
        tm.assert_index_equal(df.index.get_level_values(2), idx3)

    def test_set_index_period(self):
        # GH#6631
        df = DataFrame(np.random.default_rng(2).random(6))
        idx1 = period_range("2011-01-01", periods=3, freq="M")
        idx1 = idx1.append(idx1)
        idx2 = period_range("2013-01-01 09:00", periods=2, freq="h")
        idx2 = idx2.append(idx2).append(idx2)
        idx3 = period_range("2005", periods=6, freq="Y")

        df = df.set_index(idx1)
        df = df.set_index(idx2, append=True)
        df = df.set_index(idx3, append=True)

        expected1 = period_range("2011-01-01", periods=3, freq="M")
        expected2 = period_range("2013-01-01 09:00", periods=2, freq="h")

        tm.assert_index_equal(df.index.levels[0], expected1)
        tm.assert_index_equal(df.index.levels[1], expected2)
        tm.assert_index_equal(df.index.levels[2], idx3)

        tm.assert_index_equal(df.index.get_level_values(0), idx1)
        tm.assert_index_equal(df.index.get_level_values(1), idx2)
        tm.assert_index_equal(df.index.get_level_values(2), idx3)


class TestSetIndexInvalid:
    def test_set_index_verify_integrity(self, frame_of_index_cols):
        df = frame_of_index_cols

        with pytest.raises(ValueError, match="Index has duplicate keys"):
            df.set_index("A", verify_integrity=True)
        # with MultiIndex
        with pytest.raises(ValueError, match="Index has duplicate keys"):
            df.set_index([df["A"], df["A"]], verify_integrity=True)

    @pytest.mark.parametrize("append", [True, False])
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_raise_keys(self, frame_of_index_cols, drop, append):
        df = frame_of_index_cols

        with pytest.raises(KeyError, match="['foo', 'bar', 'baz']"):
            # column names are A-E, as well as one tuple
            df.set_index(["foo", "bar", "baz"], drop=drop, append=append)

        # non-existent key in list with arrays
        with pytest.raises(KeyError, match="X"):
            df.set_index([df["A"], df["B"], "X"], drop=drop, append=append)

        msg = "[('foo', 'foo', 'foo', 'bar', 'bar')]"
        # tuples always raise KeyError
        with pytest.raises(KeyError, match=msg):
            df.set_index(tuple(df["A"]), drop=drop, append=append)

        # also within a list
        with pytest.raises(KeyError, match=msg):
            df.set_index(["A", df["A"], tuple(df["A"])], drop=drop, append=append)

    @pytest.mark.parametrize("append", [True, False])
    @pytest.mark.parametrize("drop", [True, False])
    @pytest.mark.parametrize("box", [set], ids=["set"])
    def test_set_index_raise_on_type(self, frame_of_index_cols, box, drop, append):
        df = frame_of_index_cols

        msg = 'The parameter "keys" may be a column key, .*'
        # forbidden type, e.g. set
        with pytest.raises(TypeError, match=msg):
            df.set_index(box(df["A"]), drop=drop, append=append)

        # forbidden type in list, e.g. set
        with pytest.raises(TypeError, match=msg):
            df.set_index(["A", df["A"], box(df["A"])], drop=drop, append=append)

    # MultiIndex constructor does not work directly on Series -> lambda
    @pytest.mark.parametrize(
        "box",
        [Series, Index, np.array, iter, lambda x: MultiIndex.from_arrays([x])],
        ids=["Series", "Index", "np.array", "iter", "MultiIndex"],
    )
    @pytest.mark.parametrize("length", [4, 6], ids=["too_short", "too_long"])
    @pytest.mark.parametrize("append", [True, False])
    @pytest.mark.parametrize("drop", [True, False])
    def test_set_index_raise_on_len(
        self, frame_of_index_cols, box, length, drop, append
    ):
        # GH 24984
        df = frame_of_index_cols  # has length 5

        values = np.random.default_rng(2).integers(0, 10, (length,))

        msg = "Length mismatch: Expected 5 rows, received array of length.*"

        # wrong length directly
        with pytest.raises(ValueError, match=msg):
            df.set_index(box(values), drop=drop, append=append)

        # wrong length in list
        with pytest.raises(ValueError, match=msg):
            df.set_index(["A", df.A, box(values)], drop=drop, append=append)


class TestSetIndexCustomLabelType:
    def test_set_index_custom_label_type(self):
        # GH#24969

        class Thing:
            def __init__(self, name, color) -> None:
                self.name = name
                self.color = color

            def __str__(self) -> str:
                return f"<Thing {repr(self.name)}>"

            # necessary for pretty KeyError
            __repr__ = __str__

        thing1 = Thing("One", "red")
        thing2 = Thing("Two", "blue")
        df = DataFrame({thing1: [0, 1], thing2: [2, 3]})
        expected = DataFrame({thing1: [0, 1]}, index=Index([2, 3], name=thing2))

        # use custom label directly
        result = df.set_index(thing2)
        tm.assert_frame_equal(result, expected)

        # custom label wrapped in list
        result = df.set_index([thing2])
        tm.assert_frame_equal(result, expected)

        # missing key
        thing3 = Thing("Three", "pink")
        msg = "<Thing 'Three'>"
        with pytest.raises(KeyError, match=msg):
            # missing label directly
            df.set_index(thing3)

        with pytest.raises(KeyError, match=msg):
            # missing label in list
            df.set_index([thing3])

    def test_set_index_custom_label_hashable_iterable(self):
        # GH#24969

        # actual example discussed in GH 24984 was e.g. for shapely.geometry
        # objects (e.g. a collection of Points) that can be both hashable and
        # iterable; using frozenset as a stand-in for testing here

        class Thing(frozenset):
            # need to stabilize repr for KeyError (due to random order in sets)
            def __repr__(self) -> str:
                tmp = sorted(self)
                joined_reprs = ", ".join(map(repr, tmp))
                # double curly brace prints one brace in format string
                return f"frozenset({{{joined_reprs}}})"

        thing1 = Thing(["One", "red"])
        thing2 = Thing(["Two", "blue"])
        df = DataFrame({thing1: [0, 1], thing2: [2, 3]})
        expected = DataFrame({thing1: [0, 1]}, index=Index([2, 3], name=thing2))

        # use custom label directly
        result = df.set_index(thing2)
        tm.assert_frame_equal(result, expected)

        # custom label wrapped in list
        result = df.set_index([thing2])
        tm.assert_frame_equal(result, expected)

        # missing key
        thing3 = Thing(["Three", "pink"])
        msg = r"frozenset\(\{'Three', 'pink'\}\)"
        with pytest.raises(KeyError, match=msg):
            # missing label directly
            df.set_index(thing3)

        with pytest.raises(KeyError, match=msg):
            # missing label in list
            df.set_index([thing3])

    def test_set_index_custom_label_type_raises(self):
        # GH#24969

        # purposefully inherit from something unhashable
        class Thing(set):
            def __init__(self, name, color) -> None:
                self.name = name
                self.color = color

            def __str__(self) -> str:
                return f"<Thing {repr(self.name)}>"

        thing1 = Thing("One", "red")
        thing2 = Thing("Two", "blue")
        df = DataFrame([[0, 2], [1, 3]], columns=[thing1, thing2])

        msg = 'The parameter "keys" may be a column key, .*'

        with pytest.raises(TypeError, match=msg):
            # use custom label directly
            df.set_index(thing2)

        with pytest.raises(TypeError, match=msg):
            # custom label wrapped in list
            df.set_index([thing2])

    def test_set_index_periodindex(self):
        # GH#6631
        df = DataFrame(np.random.default_rng(2).random(6))
        idx1 = period_range("2011/01/01", periods=6, freq="M")
        idx2 = period_range("2013", periods=6, freq="Y")

        df = df.set_index(idx1)
        tm.assert_index_equal(df.index, idx1)
        df = df.set_index(idx2)
        tm.assert_index_equal(df.index, idx2)
