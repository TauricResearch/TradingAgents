from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import numpy as np
import pytest
import pytz

from pandas._config import using_string_dtype

from pandas.compat import is_platform_little_endian

from pandas import (
    CategoricalIndex,
    DataFrame,
    Index,
    Interval,
    RangeIndex,
    Series,
    date_range,
)
import pandas._testing as tm


class TestFromRecords:
    def test_from_records_dt64tz_frame(self):
        # GH#51162 don't lose tz when calling from_records with DataFrame input
        dti = date_range("2016-01-01", periods=10, tz="US/Pacific")
        df = DataFrame({i: dti for i in range(4)})
        with tm.assert_produces_warning(FutureWarning):
            res = DataFrame.from_records(df)
        tm.assert_frame_equal(res, df)

    def test_from_records_with_datetimes(self):
        # this may fail on certain platforms because of a numpy issue
        # related GH#6140
        if not is_platform_little_endian():
            pytest.skip("known failure of test on non-little endian")

        # construction with a null in a recarray
        # GH#6140
        expected = DataFrame({"EXPIRY": [datetime(2005, 3, 1, 0, 0), None]})

        arrdata = [np.array([datetime(2005, 3, 1, 0, 0), None])]
        dtypes = [("EXPIRY", "<M8[ns]")]

        recarray = np.rec.fromarrays(arrdata, dtype=dtypes)

        result = DataFrame.from_records(recarray)
        tm.assert_frame_equal(result, expected)

        # coercion should work too
        arrdata = [np.array([datetime(2005, 3, 1, 0, 0), None])]
        dtypes = [("EXPIRY", "<M8[m]")]
        recarray = np.rec.fromarrays(arrdata, dtype=dtypes)
        result = DataFrame.from_records(recarray)
        # we get the closest supported unit, "s"
        expected["EXPIRY"] = expected["EXPIRY"].astype("M8[s]")
        tm.assert_frame_equal(result, expected)

    @pytest.mark.xfail(using_string_dtype(), reason="dtype checking logic doesn't work")
    def test_from_records_sequencelike(self):
        df = DataFrame(
            {
                "A": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float64
                ),
                "A1": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float64
                ),
                "B": np.array(np.arange(6), dtype=np.int64),
                "C": ["foo"] * 6,
                "D": np.array([True, False] * 3, dtype=bool),
                "E": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float32
                ),
                "E1": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float32
                ),
                "F": np.array(np.arange(6), dtype=np.int32),
            }
        )

        # this is actually tricky to create the recordlike arrays and
        # have the dtypes be intact
        blocks = df._to_dict_of_blocks()
        tuples = []
        columns = []
        dtypes = []
        for dtype, b in blocks.items():
            columns.extend(b.columns)
            dtypes.extend([(c, np.dtype(dtype).descr[0][1]) for c in b.columns])
        for i in range(len(df.index)):
            tup = []
            for _, b in blocks.items():
                tup.extend(b.iloc[i].values)
            tuples.append(tuple(tup))

        recarray = np.array(tuples, dtype=dtypes).view(np.rec.recarray)
        recarray2 = df.to_records()
        lists = [list(x) for x in tuples]

        # tuples (lose the dtype info)
        result = DataFrame.from_records(tuples, columns=columns).reindex(
            columns=df.columns
        )

        # created recarray and with to_records recarray (have dtype info)
        result2 = DataFrame.from_records(recarray, columns=columns).reindex(
            columns=df.columns
        )
        result3 = DataFrame.from_records(recarray2, columns=columns).reindex(
            columns=df.columns
        )

        # list of tuples (no dtype info)
        result4 = DataFrame.from_records(lists, columns=columns).reindex(
            columns=df.columns
        )

        tm.assert_frame_equal(result, df, check_dtype=False)
        tm.assert_frame_equal(result2, df)
        tm.assert_frame_equal(result3, df)
        tm.assert_frame_equal(result4, df, check_dtype=False)

        # tuples is in the order of the columns
        result = DataFrame.from_records(tuples)
        tm.assert_index_equal(result.columns, RangeIndex(8))

        # test exclude parameter & we are casting the results here (as we don't
        # have dtype info to recover)
        columns_to_test = [columns.index("C"), columns.index("E1")]

        exclude = list(set(range(8)) - set(columns_to_test))
        result = DataFrame.from_records(tuples, exclude=exclude)
        result.columns = [columns[i] for i in sorted(columns_to_test)]
        tm.assert_series_equal(result["C"], df["C"])
        tm.assert_series_equal(result["E1"], df["E1"])

    def test_from_records_sequencelike_empty(self):
        # empty case
        result = DataFrame.from_records([], columns=["foo", "bar", "baz"])
        assert len(result) == 0
        tm.assert_index_equal(result.columns, Index(["foo", "bar", "baz"]))

        result = DataFrame.from_records([])
        assert len(result) == 0
        assert len(result.columns) == 0

    def test_from_records_dictlike(self):
        # test the dict methods
        df = DataFrame(
            {
                "A": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float64
                ),
                "A1": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float64
                ),
                "B": np.array(np.arange(6), dtype=np.int64),
                "C": ["foo"] * 6,
                "D": np.array([True, False] * 3, dtype=bool),
                "E": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float32
                ),
                "E1": np.array(
                    np.random.default_rng(2).standard_normal(6), dtype=np.float32
                ),
                "F": np.array(np.arange(6), dtype=np.int32),
            }
        )

        # columns is in a different order here than the actual items iterated
        # from the dict
        blocks = df._to_dict_of_blocks()
        columns = []
        for b in blocks.values():
            columns.extend(b.columns)

        asdict = dict(df.items())
        asdict2 = {x: y.values for x, y in df.items()}

        # dict of series & dict of ndarrays (have dtype info)
        results = []
        results.append(DataFrame.from_records(asdict).reindex(columns=df.columns))
        results.append(
            DataFrame.from_records(asdict, columns=columns).reindex(columns=df.columns)
        )
        results.append(
            DataFrame.from_records(asdict2, columns=columns).reindex(columns=df.columns)
        )

        for r in results:
            tm.assert_frame_equal(r, df)

    def test_from_records_with_index_data(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=["A", "B", "C"]
        )

        data = np.random.default_rng(2).standard_normal(10)
        with tm.assert_produces_warning(FutureWarning):
            df1 = DataFrame.from_records(df, index=data)
        tm.assert_index_equal(df1.index, Index(data))

    def test_from_records_bad_index_column(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=["A", "B", "C"]
        )

        # should pass
        with tm.assert_produces_warning(FutureWarning):
            df1 = DataFrame.from_records(df, index=["C"])
        tm.assert_index_equal(df1.index, Index(df.C))

        with tm.assert_produces_warning(FutureWarning):
            df1 = DataFrame.from_records(df, index="C")
        tm.assert_index_equal(df1.index, Index(df.C))

        # should fail
        msg = "|".join(
            [
                r"'None of \[2\] are in the columns'",
            ]
        )
        with pytest.raises(KeyError, match=msg):
            with tm.assert_produces_warning(FutureWarning):
                DataFrame.from_records(df, index=[2])
        with pytest.raises(KeyError, match=msg):
            with tm.assert_produces_warning(FutureWarning):
                DataFrame.from_records(df, index=2)

    def test_from_records_non_tuple(self):
        class Record:
            def __init__(self, *args) -> None:
                self.args = args

            def __getitem__(self, i):
                return self.args[i]

            def __iter__(self) -> Iterator:
                return iter(self.args)

        recs = [Record(1, 2, 3), Record(4, 5, 6), Record(7, 8, 9)]
        tups = [tuple(rec) for rec in recs]

        result = DataFrame.from_records(recs)
        expected = DataFrame.from_records(tups)
        tm.assert_frame_equal(result, expected)

    def test_from_records_len0_with_columns(self):
        # GH#2633
        result = DataFrame.from_records([], index="foo", columns=["foo", "bar"])
        expected = Index(["bar"])

        assert len(result) == 0
        assert result.index.name == "foo"
        tm.assert_index_equal(result.columns, expected)

    def test_from_records_series_list_dict(self):
        # GH#27358
        expected = DataFrame([[{"a": 1, "b": 2}, {"a": 3, "b": 4}]]).T
        data = Series([[{"a": 1, "b": 2}], [{"a": 3, "b": 4}]])
        result = DataFrame.from_records(data)
        tm.assert_frame_equal(result, expected)

    def test_from_records_series_categorical_index(self):
        # GH#32805
        index = CategoricalIndex(
            [Interval(-20, -10), Interval(-10, 0), Interval(0, 10)]
        )
        series_of_dicts = Series([{"a": 1}, {"a": 2}, {"b": 3}], index=index)
        frame = DataFrame.from_records(series_of_dicts, index=index)
        expected = DataFrame(
            {"a": [1, 2, np.nan], "b": [np.nan, np.nan, 3]}, index=index
        )
        tm.assert_frame_equal(frame, expected)

    def test_frame_from_records_utc(self):
        rec = {"datum": 1.5, "begin_time": datetime(2006, 4, 27, tzinfo=pytz.utc)}

        # it works
        DataFrame.from_records([rec], index="begin_time")

    def test_from_records_to_records(self):
        # from numpy documentation
        arr = np.zeros((2,), dtype=("i4,f4,S10"))
        arr[:] = [(1, 2.0, "Hello"), (2, 3.0, "World")]

        DataFrame.from_records(arr)

        index = Index(np.arange(len(arr))[::-1])
        indexed_frame = DataFrame.from_records(arr, index=index)
        tm.assert_index_equal(indexed_frame.index, index)

        # without names, it should go to last ditch
        arr2 = np.zeros((2, 3))
        tm.assert_frame_equal(DataFrame.from_records(arr2), DataFrame(arr2))

        # wrong length
        msg = "|".join(
            [
                r"Length of values \(2\) does not match length of index \(1\)",
            ]
        )
        with pytest.raises(ValueError, match=msg):
            DataFrame.from_records(arr, index=index[:-1])

        indexed_frame = DataFrame.from_records(arr, index="f1")

        # what to do?
        records = indexed_frame.to_records()
        assert len(records.dtype.names) == 3

        records = indexed_frame.to_records(index=False)
        assert len(records.dtype.names) == 2
        assert "index" not in records.dtype.names

    def test_from_records_nones(self):
        tuples = [(1, 2, None, 3), (1, 2, None, 3), (None, 2, 5, 3)]

        df = DataFrame.from_records(tuples, columns=["a", "b", "c", "d"])
        assert np.isnan(df["c"][0])

    def test_from_records_iterator(self):
        arr = np.array(
            [(1.0, 1.0, 2, 2), (3.0, 3.0, 4, 4), (5.0, 5.0, 6, 6), (7.0, 7.0, 8, 8)],
            dtype=[
                ("x", np.float64),
                ("u", np.float32),
                ("y", np.int64),
                ("z", np.int32),
            ],
        )
        df = DataFrame.from_records(iter(arr), nrows=2)
        xp = DataFrame(
            {
                "x": np.array([1.0, 3.0], dtype=np.float64),
                "u": np.array([1.0, 3.0], dtype=np.float32),
                "y": np.array([2, 4], dtype=np.int64),
                "z": np.array([2, 4], dtype=np.int32),
            }
        )
        tm.assert_frame_equal(df.reindex_like(xp), xp)

        # no dtypes specified here, so just compare with the default
        arr = [(1.0, 2), (3.0, 4), (5.0, 6), (7.0, 8)]
        df = DataFrame.from_records(iter(arr), columns=["x", "y"], nrows=2)
        tm.assert_frame_equal(df, xp.reindex(columns=["x", "y"]), check_dtype=False)

    def test_from_records_tuples_generator(self):
        def tuple_generator(length):
            for i in range(length):
                letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                yield (i, letters[i % len(letters)], i / length)

        columns_names = ["Integer", "String", "Float"]
        columns = [
            [i[j] for i in tuple_generator(10)] for j in range(len(columns_names))
        ]
        data = {"Integer": columns[0], "String": columns[1], "Float": columns[2]}
        expected = DataFrame(data, columns=columns_names)

        generator = tuple_generator(10)
        result = DataFrame.from_records(generator, columns=columns_names)
        tm.assert_frame_equal(result, expected)

    def test_from_records_lists_generator(self):
        def list_generator(length):
            for i in range(length):
                letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                yield [i, letters[i % len(letters)], i / length]

        columns_names = ["Integer", "String", "Float"]
        columns = [
            [i[j] for i in list_generator(10)] for j in range(len(columns_names))
        ]
        data = {"Integer": columns[0], "String": columns[1], "Float": columns[2]}
        expected = DataFrame(data, columns=columns_names)

        generator = list_generator(10)
        result = DataFrame.from_records(generator, columns=columns_names)
        tm.assert_frame_equal(result, expected)

    def test_from_records_columns_not_modified(self):
        tuples = [(1, 2, 3), (1, 2, 3), (2, 5, 3)]

        columns = ["a", "b", "c"]
        original_columns = list(columns)

        DataFrame.from_records(tuples, columns=columns, index="a")

        assert columns == original_columns

    def test_from_records_decimal(self):
        tuples = [(Decimal("1.5"),), (Decimal("2.5"),), (None,)]

        df = DataFrame.from_records(tuples, columns=["a"])
        assert df["a"].dtype == object

        df = DataFrame.from_records(tuples, columns=["a"], coerce_float=True)
        assert df["a"].dtype == np.float64
        assert np.isnan(df["a"].values[-1])

    def test_from_records_duplicates(self):
        result = DataFrame.from_records([(1, 2, 3), (4, 5, 6)], columns=["a", "b", "a"])

        expected = DataFrame([(1, 2, 3), (4, 5, 6)], columns=["a", "b", "a"])

        tm.assert_frame_equal(result, expected)

    def test_from_records_set_index_name(self):
        def create_dict(order_id):
            return {
                "order_id": order_id,
                "quantity": np.random.default_rng(2).integers(1, 10),
                "price": np.random.default_rng(2).integers(1, 10),
            }

        documents = [create_dict(i) for i in range(10)]
        # demo missing data
        documents.append({"order_id": 10, "quantity": 5})

        result = DataFrame.from_records(documents, index="order_id")
        assert result.index.name == "order_id"

        # MultiIndex
        result = DataFrame.from_records(documents, index=["order_id", "quantity"])
        assert result.index.names == ("order_id", "quantity")

    def test_from_records_misc_brokenness(self):
        # GH#2179

        data = {1: ["foo"], 2: ["bar"]}

        result = DataFrame.from_records(data, columns=["a", "b"])
        exp = DataFrame(data, columns=["a", "b"])
        tm.assert_frame_equal(result, exp)

        # overlap in index/index_names

        data = {"a": [1, 2, 3], "b": [4, 5, 6]}

        result = DataFrame.from_records(data, index=["a", "b", "c"])
        exp = DataFrame(data, index=["a", "b", "c"])
        tm.assert_frame_equal(result, exp)

    def test_from_records_misc_brokenness2(self):
        # GH#2623
        rows = []
        rows.append([datetime(2010, 1, 1), 1])
        rows.append([datetime(2010, 1, 2), "hi"])  # test col upconverts to obj
        result = DataFrame.from_records(rows, columns=["date", "test"])
        expected = DataFrame(
            {"date": [row[0] for row in rows], "test": [row[1] for row in rows]}
        )
        tm.assert_frame_equal(result, expected)
        assert result.dtypes["test"] == np.dtype(object)

    def test_from_records_misc_brokenness3(self):
        rows = []
        rows.append([datetime(2010, 1, 1), 1])
        rows.append([datetime(2010, 1, 2), 1])
        result = DataFrame.from_records(rows, columns=["date", "test"])
        expected = DataFrame(
            {"date": [row[0] for row in rows], "test": [row[1] for row in rows]}
        )
        tm.assert_frame_equal(result, expected)

    def test_from_records_empty(self):
        # GH#3562
        result = DataFrame.from_records([], columns=["a", "b", "c"])
        expected = DataFrame(columns=["a", "b", "c"])
        tm.assert_frame_equal(result, expected)

        result = DataFrame.from_records([], columns=["a", "b", "b"])
        expected = DataFrame(columns=["a", "b", "b"])
        tm.assert_frame_equal(result, expected)

    def test_from_records_empty_with_nonempty_fields_gh3682(self):
        a = np.array([(1, 2)], dtype=[("id", np.int64), ("value", np.int64)])
        df = DataFrame.from_records(a, index="id")

        ex_index = Index([1], name="id")
        expected = DataFrame({"value": [2]}, index=ex_index, columns=["value"])
        tm.assert_frame_equal(df, expected)

        b = a[:0]
        df2 = DataFrame.from_records(b, index="id")
        tm.assert_frame_equal(df2, df.iloc[:0])

    def test_from_records_empty2(self):
        # GH#42456
        dtype = [("prop", int)]
        shape = (0, len(dtype))
        arr = np.empty(shape, dtype=dtype)

        result = DataFrame.from_records(arr)
        expected = DataFrame({"prop": np.array([], dtype=int)})
        tm.assert_frame_equal(result, expected)

        alt = DataFrame(arr)
        tm.assert_frame_equal(alt, expected)
