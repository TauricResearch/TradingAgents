import numpy as np
import pytest

from pandas.errors import (
    IndexingError,
    PerformanceWarning,
)

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    Series,
)
import pandas._testing as tm


@pytest.fixture
def single_level_multiindex():
    """single level MultiIndex"""
    return MultiIndex(
        levels=[["foo", "bar", "baz", "qux"]], codes=[[0, 1, 2, 3]], names=["first"]
    )


@pytest.fixture
def frame_random_data_integer_multi_index():
    levels = [[0, 1], [0, 1, 2]]
    codes = [[0, 0, 0, 1, 1, 1], [0, 1, 2, 0, 1, 2]]
    index = MultiIndex(levels=levels, codes=codes)
    return DataFrame(np.random.default_rng(2).standard_normal((6, 2)), index=index)


class TestMultiIndexLoc:
    @pytest.mark.filterwarnings("ignore:Setting a value on a view:FutureWarning")
    @pytest.mark.parametrize("has_ref", [True, False])
    def test_loc_setitem_frame_with_multiindex(
        self, multiindex_dataframe_random_data, has_ref
    ):
        frame = multiindex_dataframe_random_data
        if has_ref:
            view = frame[:]
        frame.loc[("bar", "two"), "B"] = 5
        assert frame.loc[("bar", "two"), "B"] == 5

        # with integer labels
        df = frame.copy()
        df.columns = list(range(3))
        if has_ref:
            view = df[:]  # noqa: F841
        df.loc[("bar", "two"), 1] = 7
        assert df.loc[("bar", "two"), 1] == 7

    def test_loc_getitem_general(self, any_real_numpy_dtype):
        # GH#2817
        dtype = any_real_numpy_dtype
        data = {
            "amount": {0: 700, 1: 600, 2: 222, 3: 333, 4: 444},
            "col": {0: 3.5, 1: 3.5, 2: 4.0, 3: 4.0, 4: 4.0},
            "num": {0: 12, 1: 11, 2: 12, 3: 12, 4: 12},
        }
        df = DataFrame(data)
        df = df.astype({"col": dtype, "num": dtype})
        df = df.set_index(keys=["col", "num"])
        key = 4.0, 12

        # emits a PerformanceWarning, ok
        with tm.assert_produces_warning(PerformanceWarning):
            tm.assert_frame_equal(df.loc[key], df.iloc[2:])

        # this is ok
        return_value = df.sort_index(inplace=True)
        assert return_value is None
        res = df.loc[key]

        # col has float dtype, result should be float64 Index
        col_arr = np.array([4.0] * 3, dtype=dtype)
        year_arr = np.array([12] * 3, dtype=dtype)
        index = MultiIndex.from_arrays([col_arr, year_arr], names=["col", "num"])
        expected = DataFrame({"amount": [222, 333, 444]}, index=index)
        tm.assert_frame_equal(res, expected)

    def test_loc_getitem_multiindex_missing_label_raises(self):
        # GH#21593
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=[[2, 2, 4], [6, 8, 10]],
            index=[[4, 4, 8], [8, 10, 12]],
        )

        with pytest.raises(KeyError, match=r"^2$"):
            df.loc[2]

    def test_loc_getitem_list_of_tuples_with_multiindex(
        self, multiindex_year_month_day_dataframe_random_data
    ):
        ser = multiindex_year_month_day_dataframe_random_data["A"]
        expected = ser.reindex(ser.index[49:51])
        result = ser.loc[[(2000, 3, 10), (2000, 3, 13)]]
        tm.assert_series_equal(result, expected)

    def test_loc_getitem_series(self):
        # GH14730
        # passing a series as a key with a MultiIndex
        index = MultiIndex.from_product([[1, 2, 3], ["A", "B", "C"]])
        x = Series(index=index, data=range(9), dtype=np.float64)
        y = Series([1, 3])
        expected = Series(
            data=[0, 1, 2, 6, 7, 8],
            index=MultiIndex.from_product([[1, 3], ["A", "B", "C"]]),
            dtype=np.float64,
        )
        result = x.loc[y]
        tm.assert_series_equal(result, expected)

        result = x.loc[[1, 3]]
        tm.assert_series_equal(result, expected)

        # GH15424
        y1 = Series([1, 3], index=[1, 2])
        result = x.loc[y1]
        tm.assert_series_equal(result, expected)

        empty = Series(data=[], dtype=np.float64)
        expected = Series(
            [],
            index=MultiIndex(levels=index.levels, codes=[[], []], dtype=np.float64),
            dtype=np.float64,
        )
        result = x.loc[empty]
        tm.assert_series_equal(result, expected)

    def test_loc_getitem_array(self):
        # GH15434
        # passing an array as a key with a MultiIndex
        index = MultiIndex.from_product([[1, 2, 3], ["A", "B", "C"]])
        x = Series(index=index, data=range(9), dtype=np.float64)
        y = np.array([1, 3])
        expected = Series(
            data=[0, 1, 2, 6, 7, 8],
            index=MultiIndex.from_product([[1, 3], ["A", "B", "C"]]),
            dtype=np.float64,
        )
        result = x.loc[y]
        tm.assert_series_equal(result, expected)

        # empty array:
        empty = np.array([])
        expected = Series(
            [],
            index=MultiIndex(levels=index.levels, codes=[[], []], dtype=np.float64),
            dtype="float64",
        )
        result = x.loc[empty]
        tm.assert_series_equal(result, expected)

        # 0-dim array (scalar):
        scalar = np.int64(1)
        expected = Series(data=[0, 1, 2], index=["A", "B", "C"], dtype=np.float64)
        result = x.loc[scalar]
        tm.assert_series_equal(result, expected)

    def test_loc_multiindex_labels(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=[["i", "i", "j"], ["A", "A", "B"]],
            index=[["i", "i", "j"], ["X", "X", "Y"]],
        )

        # the first 2 rows
        expected = df.iloc[[0, 1]].droplevel(0)
        result = df.loc["i"]
        tm.assert_frame_equal(result, expected)

        # 2nd (last) column
        expected = df.iloc[:, [2]].droplevel(0, axis=1)
        result = df.loc[:, "j"]
        tm.assert_frame_equal(result, expected)

        # bottom right corner
        expected = df.iloc[[2], [2]].droplevel(0).droplevel(0, axis=1)
        result = df.loc["j"].loc[:, "j"]
        tm.assert_frame_equal(result, expected)

        # with a tuple
        expected = df.iloc[[0, 1]]
        result = df.loc[("i", "X")]
        tm.assert_frame_equal(result, expected)

    def test_loc_multiindex_ints(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=[[2, 2, 4], [6, 8, 10]],
            index=[[4, 4, 8], [8, 10, 12]],
        )
        expected = df.iloc[[0, 1]].droplevel(0)
        result = df.loc[4]
        tm.assert_frame_equal(result, expected)

    def test_loc_multiindex_missing_label_raises(self):
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=[[2, 2, 4], [6, 8, 10]],
            index=[[4, 4, 8], [8, 10, 12]],
        )

        with pytest.raises(KeyError, match=r"^2$"):
            df.loc[2]

    @pytest.mark.parametrize("key, pos", [([2, 4], [0, 1]), ([2], []), ([2, 3], [])])
    def test_loc_multiindex_list_missing_label(self, key, pos):
        # GH 27148 - lists with missing labels _do_ raise
        df = DataFrame(
            np.random.default_rng(2).standard_normal((3, 3)),
            columns=[[2, 2, 4], [6, 8, 10]],
            index=[[4, 4, 8], [8, 10, 12]],
        )

        with pytest.raises(KeyError, match="not in index"):
            df.loc[key]

    def test_loc_multiindex_too_many_dims_raises(self):
        # GH 14885
        s = Series(
            range(8),
            index=MultiIndex.from_product([["a", "b"], ["c", "d"], ["e", "f"]]),
        )

        with pytest.raises(KeyError, match=r"^\('a', 'b'\)$"):
            s.loc["a", "b"]
        with pytest.raises(KeyError, match=r"^\('a', 'd', 'g'\)$"):
            s.loc["a", "d", "g"]
        with pytest.raises(IndexingError, match="Too many indexers"):
            s.loc["a", "d", "g", "j"]

    def test_loc_multiindex_indexer_none(self):
        # GH6788
        # multi-index indexer is None (meaning take all)
        attributes = ["Attribute" + str(i) for i in range(1)]
        attribute_values = ["Value" + str(i) for i in range(5)]

        index = MultiIndex.from_product([attributes, attribute_values])
        df = 0.1 * np.random.default_rng(2).standard_normal((10, 1 * 5)) + 0.5
        df = DataFrame(df, columns=index)
        result = df[attributes]
        tm.assert_frame_equal(result, df)

        # GH 7349
        # loc with a multi-index seems to be doing fallback
        df = DataFrame(
            np.arange(12).reshape(-1, 1),
            index=MultiIndex.from_product([[1, 2, 3, 4], [1, 2, 3]]),
        )

        expected = df.loc[([1, 2],), :]
        result = df.loc[[1, 2]]
        tm.assert_frame_equal(result, expected)

    def test_loc_multiindex_incomplete(self):
        # GH 7399
        # incomplete indexers
        s = Series(
            np.arange(15, dtype="int64"),
            MultiIndex.from_product([range(5), ["a", "b", "c"]]),
        )
        expected = s.loc[:, "a":"c"]

        result = s.loc[0:4, "a":"c"]
        tm.assert_series_equal(result, expected)

        result = s.loc[:4, "a":"c"]
        tm.assert_series_equal(result, expected)

        result = s.loc[0:, "a":"c"]
        tm.assert_series_equal(result, expected)

        # GH 7400
        # multiindexer getitem with list of indexers skips wrong element
        s = Series(
            np.arange(15, dtype="int64"),
            MultiIndex.from_product([range(5), ["a", "b", "c"]]),
        )
        expected = s.iloc[[6, 7, 8, 12, 13, 14]]
        result = s.loc[2:4:2, "a":"c"]
        tm.assert_series_equal(result, expected)

    def test_get_loc_single_level(self, single_level_multiindex):
        single_level = single_level_multiindex
        s = Series(
            np.random.default_rng(2).standard_normal(len(single_level)),
            index=single_level,
        )
        for k in single_level.values:
            s[k]

    def test_loc_getitem_int_slice(self):
        # GH 3053
        # loc should treat integer slices like label slices

        index = MultiIndex.from_product([[6, 7, 8], ["a", "b"]])
        df = DataFrame(np.random.default_rng(2).standard_normal((6, 6)), index, index)
        result = df.loc[6:8, :]
        expected = df
        tm.assert_frame_equal(result, expected)

        index = MultiIndex.from_product([[10, 20, 30], ["a", "b"]])
        df = DataFrame(np.random.default_rng(2).standard_normal((6, 6)), index, index)
        result = df.loc[20:30, :]
        expected = df.iloc[2:]
        tm.assert_frame_equal(result, expected)

        # doc examples
        result = df.loc[10, :]
        expected = df.iloc[0:2]
        expected.index = ["a", "b"]
        tm.assert_frame_equal(result, expected)

        result = df.loc[:, 10]
        expected = df[10]
        tm.assert_frame_equal(result, expected)

    @pytest.mark.parametrize(
        "indexer_type_1", (list, tuple, set, slice, np.ndarray, Series, Index)
    )
    @pytest.mark.parametrize(
        "indexer_type_2", (list, tuple, set, slice, np.ndarray, Series, Index)
    )
    def test_loc_getitem_nested_indexer(self, indexer_type_1, indexer_type_2):
        # GH #19686
        # .loc should work with nested indexers which can be
        # any list-like objects (see `is_list_like` (`pandas.api.types`)) or slices

        def convert_nested_indexer(indexer_type, keys):
            if indexer_type == np.ndarray:
                return np.array(keys)
            if indexer_type == slice:
                return slice(*keys)
            return indexer_type(keys)

        a = [10, 20, 30]
        b = [1, 2, 3]
        index = MultiIndex.from_product([a, b])
        df = DataFrame(
            np.arange(len(index), dtype="int64"), index=index, columns=["Data"]
        )

        keys = ([10, 20], [2, 3])
        types = (indexer_type_1, indexer_type_2)

        # check indexers with all the combinations of nested objects
        # of all the valid types
        indexer = tuple(
            convert_nested_indexer(indexer_type, k)
            for indexer_type, k in zip(types, keys)
        )
        if indexer_type_1 is set or indexer_type_2 is set:
            with pytest.raises(TypeError, match="as an indexer is not supported"):
                df.loc[indexer, "Data"]

            return
        else:
            result = df.loc[indexer, "Data"]
        expected = Series(
            [1, 2, 4, 5], name="Data", index=MultiIndex.from_product(keys)
        )

        tm.assert_series_equal(result, expected)

    def test_multiindex_loc_one_dimensional_tuple(self, frame_or_series):
        # GH#37711
        mi = MultiIndex.from_tuples([("a", "A"), ("b", "A")])
        obj = frame_or_series([1, 2], index=mi)
        obj.loc[("a",)] = 0
        expected = frame_or_series([0, 2], index=mi)
        tm.assert_equal(obj, expected)

    @pytest.mark.parametrize("indexer", [("a",), ("a")])
    def test_multiindex_one_dimensional_tuple_columns(self, indexer):
        # GH#37711
        mi = MultiIndex.from_tuples([("a", "A"), ("b", "A")])
        obj = DataFrame([1, 2], index=mi)
        obj.loc[indexer, :] = 0
        expected = DataFrame([0, 2], index=mi)
        tm.assert_frame_equal(obj, expected)

    @pytest.mark.parametrize(
        "indexer, exp_value", [(slice(None), 1.0), ((1, 2), np.nan)]
    )
    def test_multiindex_setitem_columns_enlarging(self, indexer, exp_value):
        # GH#39147
        mi = MultiIndex.from_tuples([(1, 2), (3, 4)])
        df = DataFrame([[1, 2], [3, 4]], index=mi, columns=["a", "b"])
        df.loc[indexer, ["c", "d"]] = 1.0
        expected = DataFrame(
            [[1, 2, 1.0, 1.0], [3, 4, exp_value, exp_value]],
            index=mi,
            columns=["a", "b", "c", "d"],
        )
        tm.assert_frame_equal(df, expected)

    def test_sorted_multiindex_after_union(self):
        # GH#44752
        midx = MultiIndex.from_product(
            [pd.date_range("20110101", periods=2), Index(["a", "b"])]
        )
        ser1 = Series(1, index=midx)
        ser2 = Series(1, index=midx[:2])
        df = pd.concat([ser1, ser2], axis=1)
        expected = df.copy()
        result = df.loc["2011-01-01":"2011-01-02"]
        tm.assert_frame_equal(result, expected)

        df = DataFrame({0: ser1, 1: ser2})
        result = df.loc["2011-01-01":"2011-01-02"]
        tm.assert_frame_equal(result, expected)

        df = pd.concat([ser1, ser2.reindex(ser1.index)], axis=1)
        result = df.loc["2011-01-01":"2011-01-02"]
        tm.assert_frame_equal(result, expected)

    def test_loc_no_second_level_index(self):
        # GH#43599
        df = DataFrame(
            index=MultiIndex.from_product([list("ab"), list("cd"), list("e")]),
            columns=["Val"],
        )
        res = df.loc[np.s_[:, "c", :]]
        expected = DataFrame(
            index=MultiIndex.from_product([list("ab"), list("e")]), columns=["Val"]
        )
        tm.assert_frame_equal(res, expected)

    def test_loc_multi_index_key_error(self):
        # GH 51892
        df = DataFrame(
            {
                (1, 2): ["a", "b", "c"],
                (1, 3): ["d", "e", "f"],
                (2, 2): ["g", "h", "i"],
                (2, 4): ["j", "k", "l"],
            }
        )
        with pytest.raises(KeyError, match=r"(1, 4)"):
            df.loc[0, (1, 4)]


@pytest.mark.parametrize(
    "indexer, pos",
    [
        ([], []),  # empty ok
        (["A"], slice(3)),
        (["A", "D"], []),  # "D" isn't present -> raise
        (["D", "E"], []),  # no values found -> raise
        (["D"], []),  # same, with single item list: GH 27148
        (pd.IndexSlice[:, ["foo"]], slice(2, None, 3)),
        (pd.IndexSlice[:, ["foo", "bah"]], slice(2, None, 3)),
    ],
)
def test_loc_getitem_duplicates_multiindex_missing_indexers(indexer, pos):
    # GH 7866
    # multi-index slicing with missing indexers
    idx = MultiIndex.from_product(
        [["A", "B", "C"], ["foo", "bar", "baz"]], names=["one", "two"]
    )
    ser = Series(np.arange(9, dtype="int64"), index=idx).sort_index()
    expected = ser.iloc[pos]

    if expected.size == 0 and indexer != []:
        with pytest.raises(KeyError, match=str(indexer)):
            ser.loc[indexer]
    elif indexer == (slice(None), ["foo", "bah"]):
        # "bah" is not in idx.levels[1], raising KeyError enforced in 2.0
        with pytest.raises(KeyError, match="'bah'"):
            ser.loc[indexer]
    else:
        result = ser.loc[indexer]
        tm.assert_series_equal(result, expected)


@pytest.mark.parametrize("columns_indexer", [([], slice(None)), (["foo"], [])])
def test_loc_getitem_duplicates_multiindex_empty_indexer(columns_indexer):
    # GH 8737
    # empty indexer
    multi_index = MultiIndex.from_product((["foo", "bar", "baz"], ["alpha", "beta"]))
    df = DataFrame(
        np.random.default_rng(2).standard_normal((5, 6)),
        index=range(5),
        columns=multi_index,
    )
    df = df.sort_index(level=0, axis=1)

    expected = DataFrame(index=range(5), columns=multi_index.reindex([])[0])
    result = df.loc[:, columns_indexer]
    tm.assert_frame_equal(result, expected)


def test_loc_getitem_duplicates_multiindex_non_scalar_type_object():
    # regression from < 0.14.0
    # GH 7914
    df = DataFrame(
        [[np.mean, np.median], ["mean", "median"]],
        columns=MultiIndex.from_tuples([("functs", "mean"), ("functs", "median")]),
        index=["function", "name"],
    )
    result = df.loc["function", ("functs", "mean")]
    expected = np.mean
    assert result == expected


def test_loc_getitem_tuple_plus_slice():
    # GH 671
    df = DataFrame(
        {
            "a": np.arange(10),
            "b": np.arange(10),
            "c": np.random.default_rng(2).standard_normal(10),
            "d": np.random.default_rng(2).standard_normal(10),
        }
    ).set_index(["a", "b"])
    expected = df.loc[0, 0]
    result = df.loc[(0, 0), :]
    tm.assert_series_equal(result, expected)


def test_loc_getitem_int(frame_random_data_integer_multi_index):
    df = frame_random_data_integer_multi_index
    result = df.loc[1]
    expected = df[-3:]
    expected.index = expected.index.droplevel(0)
    tm.assert_frame_equal(result, expected)


def test_loc_getitem_int_raises_exception(frame_random_data_integer_multi_index):
    df = frame_random_data_integer_multi_index
    with pytest.raises(KeyError, match=r"^3$"):
        df.loc[3]


def test_loc_getitem_lowerdim_corner(multiindex_dataframe_random_data):
    df = multiindex_dataframe_random_data

    # test setup - check key not in dataframe
    with pytest.raises(KeyError, match=r"^\('bar', 'three'\)$"):
        df.loc[("bar", "three"), "B"]

    # in theory should be inserting in a sorted space????
    df.loc[("bar", "three"), "B"] = 0
    expected = 0
    result = df.sort_index().loc[("bar", "three"), "B"]
    assert result == expected


def test_loc_setitem_single_column_slice():
    # case from https://github.com/pandas-dev/pandas/issues/27841
    df = DataFrame(
        "string",
        index=list("abcd"),
        columns=MultiIndex.from_product([["Main"], ("another", "one")]),
    )
    df["labels"] = "a"
    df.loc[:, "labels"] = df.index
    tm.assert_numpy_array_equal(np.asarray(df["labels"]), np.asarray(df.index))

    # test with non-object block
    df = DataFrame(
        np.nan,
        index=range(4),
        columns=MultiIndex.from_tuples([("A", "1"), ("A", "2"), ("B", "1")]),
    )
    expected = df.copy()
    df.loc[:, "B"] = np.arange(4)
    expected.iloc[:, 2] = np.arange(4)
    tm.assert_frame_equal(df, expected)


def test_loc_nan_multiindex(using_infer_string):
    # GH 5286
    tups = [
        ("Good Things", "C", np.nan),
        ("Good Things", "R", np.nan),
        ("Bad Things", "C", np.nan),
        ("Bad Things", "T", np.nan),
        ("Okay Things", "N", "B"),
        ("Okay Things", "N", "D"),
        ("Okay Things", "B", np.nan),
        ("Okay Things", "D", np.nan),
    ]
    df = DataFrame(
        np.ones((8, 4)),
        columns=Index(["d1", "d2", "d3", "d4"]),
        index=MultiIndex.from_tuples(tups, names=["u1", "u2", "u3"]),
    )
    result = df.loc["Good Things"].loc["C"]
    expected = DataFrame(
        np.ones((1, 4)),
        index=Index(
            [np.nan],
            dtype="object" if not using_infer_string else "str",
            name="u3",
        ),
        columns=Index(["d1", "d2", "d3", "d4"]),
    )
    tm.assert_frame_equal(result, expected)


def test_loc_period_string_indexing():
    # GH 9892
    a = pd.period_range("2013Q1", "2013Q4", freq="Q")
    i = (1111, 2222, 3333)
    idx = MultiIndex.from_product((a, i), names=("Period", "CVR"))
    df = DataFrame(
        index=idx,
        columns=(
            "OMS",
            "OMK",
            "RES",
            "DRIFT_IND",
            "OEVRIG_IND",
            "FIN_IND",
            "VARE_UD",
            "LOEN_UD",
            "FIN_UD",
        ),
    )
    result = df.loc[("2013Q1", 1111), "OMS"]

    alt = df.loc[(a[0], 1111), "OMS"]
    assert np.isnan(alt)

    # Because the resolution of the string matches, it is an exact lookup,
    #  not a slice
    assert np.isnan(result)

    alt = df.loc[("2013Q1", 1111), "OMS"]
    assert np.isnan(alt)


def test_loc_datetime_mask_slicing():
    # GH 16699
    dt_idx = pd.to_datetime(["2017-05-04", "2017-05-05"])
    m_idx = MultiIndex.from_product([dt_idx, dt_idx], names=["Idx1", "Idx2"])
    df = DataFrame(
        data=[[1, 2], [3, 4], [5, 6], [7, 6]], index=m_idx, columns=["C1", "C2"]
    )
    result = df.loc[(dt_idx[0], (df.index.get_level_values(1) > "2017-05-04")), "C1"]
    expected = Series(
        [3],
        name="C1",
        index=MultiIndex.from_tuples(
            [(pd.Timestamp("2017-05-04"), pd.Timestamp("2017-05-05"))],
            names=["Idx1", "Idx2"],
        ),
    )
    tm.assert_series_equal(result, expected)


def test_loc_datetime_series_tuple_slicing():
    # https://github.com/pandas-dev/pandas/issues/35858
    date = pd.Timestamp("2000")
    ser = Series(
        1,
        index=MultiIndex.from_tuples([("a", date)], names=["a", "b"]),
        name="c",
    )
    result = ser.loc[:, [date]]
    tm.assert_series_equal(result, ser)


def test_loc_with_mi_indexer():
    # https://github.com/pandas-dev/pandas/issues/35351
    df = DataFrame(
        data=[["a", 1], ["a", 0], ["b", 1], ["c", 2]],
        index=MultiIndex.from_tuples(
            [(0, 1), (1, 0), (1, 1), (1, 1)], names=["index", "date"]
        ),
        columns=["author", "price"],
    )
    idx = MultiIndex.from_tuples([(0, 1), (1, 1)], names=["index", "date"])
    result = df.loc[idx, :]
    expected = DataFrame(
        [["a", 1], ["b", 1], ["c", 2]],
        index=MultiIndex.from_tuples([(0, 1), (1, 1), (1, 1)], names=["index", "date"]),
        columns=["author", "price"],
    )
    tm.assert_frame_equal(result, expected)


def test_loc_mi_with_level1_named_0():
    # GH#37194
    dti = pd.date_range("2016-01-01", periods=3, tz="US/Pacific")

    ser = Series(range(3), index=dti)
    df = ser.to_frame()
    df[1] = dti

    df2 = df.set_index(0, append=True)
    assert df2.index.names == (None, 0)
    df2.index.get_loc(dti[0])  # smoke test

    result = df2.loc[dti[0]]
    expected = df2.iloc[[0]].droplevel(None)
    tm.assert_frame_equal(result, expected)

    ser2 = df2[1]
    assert ser2.index.names == (None, 0)

    result = ser2.loc[dti[0]]
    expected = ser2.iloc[[0]].droplevel(None)
    tm.assert_series_equal(result, expected)


def test_getitem_str_slice():
    # GH#15928
    df = DataFrame(
        [
            ["20160525 13:30:00.023", "MSFT", "51.95", "51.95"],
            ["20160525 13:30:00.048", "GOOG", "720.50", "720.93"],
            ["20160525 13:30:00.076", "AAPL", "98.55", "98.56"],
            ["20160525 13:30:00.131", "AAPL", "98.61", "98.62"],
            ["20160525 13:30:00.135", "MSFT", "51.92", "51.95"],
            ["20160525 13:30:00.135", "AAPL", "98.61", "98.62"],
        ],
        columns="time,ticker,bid,ask".split(","),
    )
    df2 = df.set_index(["ticker", "time"]).sort_index()

    res = df2.loc[("AAPL", slice("2016-05-25 13:30:00")), :].droplevel(0)
    expected = df2.loc["AAPL"].loc[slice("2016-05-25 13:30:00"), :]
    tm.assert_frame_equal(res, expected)


def test_3levels_leading_period_index():
    # GH#24091
    pi = pd.PeriodIndex(
        ["20181101 1100", "20181101 1200", "20181102 1300", "20181102 1400"],
        name="datetime",
        freq="D",
    )
    lev2 = ["A", "A", "Z", "W"]
    lev3 = ["B", "C", "Q", "F"]
    mi = MultiIndex.from_arrays([pi, lev2, lev3])

    ser = Series(range(4), index=mi, dtype=np.float64)
    result = ser.loc[(pi[0], "A", "B")]
    assert result == 0.0


class TestKeyErrorsWithMultiIndex:
    def test_missing_keys_raises_keyerror(self):
        # GH#27420 KeyError, not TypeError
        df = DataFrame(np.arange(12).reshape(4, 3), columns=["A", "B", "C"])
        df2 = df.set_index(["A", "B"])

        with pytest.raises(KeyError, match="1"):
            df2.loc[(1, 6)]

    def test_missing_key_raises_keyerror2(self):
        # GH#21168 KeyError, not "IndexingError: Too many indexers"
        ser = Series(-1, index=MultiIndex.from_product([[0, 1]] * 2))

        with pytest.raises(KeyError, match=r"\(0, 3\)"):
            ser.loc[0, 3]

    def test_missing_key_combination(self):
        # GH: 19556
        mi = MultiIndex.from_arrays(
            [
                np.array(["a", "a", "b", "b"]),
                np.array(["1", "2", "2", "3"]),
                np.array(["c", "d", "c", "d"]),
            ],
            names=["one", "two", "three"],
        )
        df = DataFrame(np.random.default_rng(2).random((4, 3)), index=mi)
        msg = r"\('b', '1', slice\(None, None, None\)\)"
        with pytest.raises(KeyError, match=msg):
            df.loc[("b", "1", slice(None)), :]
        with pytest.raises(KeyError, match=msg):
            df.index.get_locs(("b", "1", slice(None)))
        with pytest.raises(KeyError, match=r"\('b', '1'\)"):
            df.loc[("b", "1"), :]


def test_getitem_loc_commutability(multiindex_year_month_day_dataframe_random_data):
    df = multiindex_year_month_day_dataframe_random_data
    ser = df["A"]
    result = ser[2000, 5]
    expected = df.loc[2000, 5]["A"]
    tm.assert_series_equal(result, expected)


def test_loc_with_nan():
    # GH: 27104
    df = DataFrame(
        {"col": [1, 2, 5], "ind1": ["a", "d", np.nan], "ind2": [1, 4, 5]}
    ).set_index(["ind1", "ind2"])
    result = df.loc[["a"]]
    expected = DataFrame(
        {"col": [1]}, index=MultiIndex.from_tuples([("a", 1)], names=["ind1", "ind2"])
    )
    tm.assert_frame_equal(result, expected)

    result = df.loc["a"]
    expected = DataFrame({"col": [1]}, index=Index([1], name="ind2"))
    tm.assert_frame_equal(result, expected)


def test_getitem_non_found_tuple():
    # GH: 25236
    df = DataFrame([[1, 2, 3, 4]], columns=["a", "b", "c", "d"]).set_index(
        ["a", "b", "c"]
    )
    with pytest.raises(KeyError, match=r"\(2\.0, 2\.0, 3\.0\)"):
        df.loc[(2.0, 2.0, 3.0)]


def test_get_loc_datetime_index():
    # GH#24263
    index = pd.date_range("2001-01-01", periods=100)
    mi = MultiIndex.from_arrays([index])
    # Check if get_loc matches for Index and MultiIndex
    assert mi.get_loc("2001-01") == slice(0, 31, None)
    assert index.get_loc("2001-01") == slice(0, 31, None)

    loc = mi[::2].get_loc("2001-01")
    expected = index[::2].get_loc("2001-01")
    assert loc == expected

    loc = mi.repeat(2).get_loc("2001-01")
    expected = index.repeat(2).get_loc("2001-01")
    assert loc == expected

    loc = mi.append(mi).get_loc("2001-01")
    expected = index.append(index).get_loc("2001-01")
    # TODO: standardize return type for MultiIndex.get_loc
    tm.assert_numpy_array_equal(loc.nonzero()[0], expected)


def test_loc_setitem_indexer_differently_ordered():
    # GH#34603
    mi = MultiIndex.from_product([["a", "b"], [0, 1]])
    df = DataFrame([[1, 2], [3, 4], [5, 6], [7, 8]], index=mi)

    indexer = ("a", [1, 0])
    df.loc[indexer, :] = np.array([[9, 10], [11, 12]])
    expected = DataFrame([[11, 12], [9, 10], [5, 6], [7, 8]], index=mi)
    tm.assert_frame_equal(df, expected)


def test_loc_getitem_index_differently_ordered_slice_none():
    # GH#31330
    df = DataFrame(
        [[1, 2], [3, 4], [5, 6], [7, 8]],
        index=[["a", "a", "b", "b"], [1, 2, 1, 2]],
        columns=["a", "b"],
    )
    result = df.loc[(slice(None), [2, 1]), :]
    expected = DataFrame(
        [[3, 4], [7, 8], [1, 2], [5, 6]],
        index=[["a", "b", "a", "b"], [2, 2, 1, 1]],
        columns=["a", "b"],
    )
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("indexer", [[1, 2, 7, 6, 2, 3, 8, 7], [1, 2, 7, 6, 3, 8]])
def test_loc_getitem_index_differently_ordered_slice_none_duplicates(indexer):
    # GH#40978
    df = DataFrame(
        [1] * 8,
        index=MultiIndex.from_tuples(
            [(1, 1), (1, 2), (1, 7), (1, 6), (2, 2), (2, 3), (2, 8), (2, 7)]
        ),
        columns=["a"],
    )
    result = df.loc[(slice(None), indexer), :]
    expected = DataFrame(
        [1] * 8,
        index=[[1, 1, 2, 1, 2, 1, 2, 2], [1, 2, 2, 7, 7, 6, 3, 8]],
        columns=["a"],
    )
    tm.assert_frame_equal(result, expected)

    result = df.loc[df.index.isin(indexer, level=1), :]
    tm.assert_frame_equal(result, df)


def test_loc_getitem_drops_levels_for_one_row_dataframe():
    # GH#10521 "x" and "z" are both scalar indexing, so those levels are dropped
    mi = MultiIndex.from_arrays([["x"], ["y"], ["z"]], names=["a", "b", "c"])
    df = DataFrame({"d": [0]}, index=mi)
    expected = df.droplevel([0, 2])
    result = df.loc["x", :, "z"]
    tm.assert_frame_equal(result, expected)

    ser = Series([0], index=mi)
    result = ser.loc["x", :, "z"]
    expected = Series([0], index=Index(["y"], name="b"))
    tm.assert_series_equal(result, expected)


def test_mi_columns_loc_list_label_order():
    # GH 10710
    cols = MultiIndex.from_product([["A", "B", "C"], [1, 2]])
    df = DataFrame(np.zeros((5, 6)), columns=cols)
    result = df.loc[:, ["B", "A"]]
    expected = DataFrame(
        np.zeros((5, 4)),
        columns=MultiIndex.from_tuples([("B", 1), ("B", 2), ("A", 1), ("A", 2)]),
    )
    tm.assert_frame_equal(result, expected)


def test_mi_partial_indexing_list_raises():
    # GH 13501
    frame = DataFrame(
        np.arange(12).reshape((4, 3)),
        index=[["a", "a", "b", "b"], [1, 2, 1, 2]],
        columns=[["Ohio", "Ohio", "Colorado"], ["Green", "Red", "Green"]],
    )
    frame.index.names = ["key1", "key2"]
    frame.columns.names = ["state", "color"]
    with pytest.raises(KeyError, match="\\[2\\] not in index"):
        frame.loc[["b", 2], "Colorado"]


def test_mi_indexing_list_nonexistent_raises():
    # GH 15452
    s = Series(range(4), index=MultiIndex.from_product([[1, 2], ["a", "b"]]))
    with pytest.raises(KeyError, match="\\['not' 'found'\\] not in index"):
        s.loc[["not", "found"]]


def test_mi_add_cell_missing_row_non_unique():
    # GH 16018
    result = DataFrame(
        [[1, 2, 5, 6], [3, 4, 7, 8]],
        index=["a", "a"],
        columns=MultiIndex.from_product([[1, 2], ["A", "B"]]),
    )
    result.loc["c"] = -1
    result.loc["c", (1, "A")] = 3
    result.loc["d", (1, "A")] = 3
    expected = DataFrame(
        [
            [1.0, 2.0, 5.0, 6.0],
            [3.0, 4.0, 7.0, 8.0],
            [3.0, -1.0, -1, -1],
            [3.0, np.nan, np.nan, np.nan],
        ],
        index=["a", "a", "c", "d"],
        columns=MultiIndex.from_product([[1, 2], ["A", "B"]]),
    )
    tm.assert_frame_equal(result, expected)


def test_loc_get_scalar_casting_to_float():
    # GH#41369
    df = DataFrame(
        {"a": 1.0, "b": 2}, index=MultiIndex.from_arrays([[3], [4]], names=["c", "d"])
    )
    result = df.loc[(3, 4), "b"]
    assert result == 2
    assert isinstance(result, np.int64)
    result = df.loc[[(3, 4)], "b"].iloc[0]
    assert result == 2
    assert isinstance(result, np.int64)


def test_loc_empty_single_selector_with_names():
    # GH 19517
    idx = MultiIndex.from_product([["a", "b"], ["A", "B"]], names=[1, 0])
    s2 = Series(index=idx, dtype=np.float64)
    result = s2.loc["a"]
    expected = Series([np.nan, np.nan], index=Index(["A", "B"], name=0))
    tm.assert_series_equal(result, expected)


def test_loc_keyerror_rightmost_key_missing():
    # GH 20951

    df = DataFrame(
        {
            "A": [100, 100, 200, 200, 300, 300],
            "B": [10, 10, 20, 21, 31, 33],
            "C": range(6),
        }
    )
    df = df.set_index(["A", "B"])
    with pytest.raises(KeyError, match="^1$"):
        df.loc[(100, 1)]


def test_multindex_series_loc_with_tuple_label():
    # GH#43908
    mi = MultiIndex.from_tuples([(1, 2), (3, (4, 5))])
    ser = Series([1, 2], index=mi)
    result = ser.loc[(3, (4, 5))]
    assert result == 2
