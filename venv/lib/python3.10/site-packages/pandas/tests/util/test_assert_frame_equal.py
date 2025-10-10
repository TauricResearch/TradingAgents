import pytest

import pandas as pd
from pandas import DataFrame
import pandas._testing as tm


@pytest.fixture(params=[True, False])
def by_blocks_fixture(request):
    return request.param


@pytest.fixture(params=["DataFrame", "Series"])
def obj_fixture(request):
    return request.param


def _assert_frame_equal_both(a, b, **kwargs):
    """
    Check that two DataFrame equal.

    This check is performed commutatively.

    Parameters
    ----------
    a : DataFrame
        The first DataFrame to compare.
    b : DataFrame
        The second DataFrame to compare.
    kwargs : dict
        The arguments passed to `tm.assert_frame_equal`.
    """
    tm.assert_frame_equal(a, b, **kwargs)
    tm.assert_frame_equal(b, a, **kwargs)


@pytest.mark.parametrize("check_like", [True, False])
def test_frame_equal_row_order_mismatch(check_like, obj_fixture):
    df1 = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}, index=["a", "b", "c"])
    df2 = DataFrame({"A": [3, 2, 1], "B": [6, 5, 4]}, index=["c", "b", "a"])

    if not check_like:  # Do not ignore row-column orderings.
        msg = f"{obj_fixture}.index are different"
        with pytest.raises(AssertionError, match=msg):
            tm.assert_frame_equal(df1, df2, check_like=check_like, obj=obj_fixture)
    else:
        _assert_frame_equal_both(df1, df2, check_like=check_like, obj=obj_fixture)


@pytest.mark.parametrize(
    "df1,df2",
    [
        (DataFrame({"A": [1, 2, 3]}), DataFrame({"A": [1, 2, 3, 4]})),
        (DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}), DataFrame({"A": [1, 2, 3]})),
    ],
)
def test_frame_equal_shape_mismatch(df1, df2, obj_fixture):
    msg = f"{obj_fixture} are different"

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2, obj=obj_fixture)


@pytest.mark.parametrize(
    "df1,df2,msg",
    [
        # Index
        (
            DataFrame.from_records({"a": [1, 2], "c": ["l1", "l2"]}, index=["a"]),
            DataFrame.from_records({"a": [1.0, 2.0], "c": ["l1", "l2"]}, index=["a"]),
            "DataFrame\\.index are different",
        ),
        # MultiIndex
        (
            DataFrame.from_records(
                {"a": [1, 2], "b": [2.1, 1.5], "c": ["l1", "l2"]}, index=["a", "b"]
            ),
            DataFrame.from_records(
                {"a": [1.0, 2.0], "b": [2.1, 1.5], "c": ["l1", "l2"]}, index=["a", "b"]
            ),
            "MultiIndex level \\[0\\] are different",
        ),
    ],
)
def test_frame_equal_index_dtype_mismatch(df1, df2, msg, check_index_type):
    kwargs = {"check_index_type": check_index_type}

    if check_index_type:
        with pytest.raises(AssertionError, match=msg):
            tm.assert_frame_equal(df1, df2, **kwargs)
    else:
        tm.assert_frame_equal(df1, df2, **kwargs)


def test_empty_dtypes(check_dtype):
    columns = ["col1", "col2"]
    df1 = DataFrame(columns=columns)
    df2 = DataFrame(columns=columns)

    kwargs = {"check_dtype": check_dtype}
    df1["col1"] = df1["col1"].astype("int64")

    if check_dtype:
        msg = r"Attributes of DataFrame\..* are different"
        with pytest.raises(AssertionError, match=msg):
            tm.assert_frame_equal(df1, df2, **kwargs)
    else:
        tm.assert_frame_equal(df1, df2, **kwargs)


@pytest.mark.parametrize("check_like", [True, False])
def test_frame_equal_index_mismatch(check_like, obj_fixture, using_infer_string):
    if using_infer_string:
        dtype = "str"
    else:
        dtype = "object"
    msg = f"""{obj_fixture}\\.index are different

{obj_fixture}\\.index values are different \\(33\\.33333 %\\)
\\[left\\]:  Index\\(\\['a', 'b', 'c'\\], dtype='{dtype}'\\)
\\[right\\]: Index\\(\\['a', 'b', 'd'\\], dtype='{dtype}'\\)
At positional index 2, first diff: c != d"""

    df1 = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}, index=["a", "b", "c"])
    df2 = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}, index=["a", "b", "d"])

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2, check_like=check_like, obj=obj_fixture)


@pytest.mark.parametrize("check_like", [True, False])
def test_frame_equal_columns_mismatch(check_like, obj_fixture, using_infer_string):
    if using_infer_string:
        dtype = "str"
    else:
        dtype = "object"
    msg = f"""{obj_fixture}\\.columns are different

{obj_fixture}\\.columns values are different \\(50\\.0 %\\)
\\[left\\]:  Index\\(\\['A', 'B'\\], dtype='{dtype}'\\)
\\[right\\]: Index\\(\\['A', 'b'\\], dtype='{dtype}'\\)"""

    df1 = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]}, index=["a", "b", "c"])
    df2 = DataFrame({"A": [1, 2, 3], "b": [4, 5, 6]}, index=["a", "b", "c"])

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2, check_like=check_like, obj=obj_fixture)


def test_frame_equal_block_mismatch(by_blocks_fixture, obj_fixture):
    obj = obj_fixture
    msg = f"""{obj}\\.iloc\\[:, 1\\] \\(column name="B"\\) are different

{obj}\\.iloc\\[:, 1\\] \\(column name="B"\\) values are different \\(33\\.33333 %\\)
\\[index\\]: \\[0, 1, 2\\]
\\[left\\]:  \\[4, 5, 6\\]
\\[right\\]: \\[4, 5, 7\\]"""

    df1 = DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    df2 = DataFrame({"A": [1, 2, 3], "B": [4, 5, 7]})

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2, by_blocks=by_blocks_fixture, obj=obj_fixture)


@pytest.mark.parametrize(
    "df1,df2,msg",
    [
        (
            DataFrame({"A": ["á", "à", "ä"], "E": ["é", "è", "ë"]}),
            DataFrame({"A": ["á", "à", "ä"], "E": ["é", "è", "e̊"]}),
            """{obj}\\.iloc\\[:, 1\\] \\(column name="E"\\) are different

{obj}\\.iloc\\[:, 1\\] \\(column name="E"\\) values are different \\(33\\.33333 %\\)
\\[index\\]: \\[0, 1, 2\\]
\\[left\\]:  \\[é, è, ë\\]
\\[right\\]: \\[é, è, e̊\\]""",
        ),
        (
            DataFrame({"A": ["á", "à", "ä"], "E": ["é", "è", "ë"]}),
            DataFrame({"A": ["a", "a", "a"], "E": ["e", "e", "e"]}),
            """{obj}\\.iloc\\[:, 0\\] \\(column name="A"\\) are different

{obj}\\.iloc\\[:, 0\\] \\(column name="A"\\) values are different \\(100\\.0 %\\)
\\[index\\]: \\[0, 1, 2\\]
\\[left\\]:  \\[á, à, ä\\]
\\[right\\]: \\[a, a, a\\]""",
        ),
    ],
)
def test_frame_equal_unicode(df1, df2, msg, by_blocks_fixture, obj_fixture):
    # see gh-20503
    #
    # Test ensures that `tm.assert_frame_equals` raises the right exception
    # when comparing DataFrames containing differing unicode objects.
    msg = msg.format(obj=obj_fixture)
    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2, by_blocks=by_blocks_fixture, obj=obj_fixture)


def test_assert_frame_equal_extension_dtype_mismatch():
    # https://github.com/pandas-dev/pandas/issues/32747
    left = DataFrame({"a": [1, 2, 3]}, dtype="Int64")
    right = left.astype(int)

    msg = (
        "Attributes of DataFrame\\.iloc\\[:, 0\\] "
        '\\(column name="a"\\) are different\n\n'
        'Attribute "dtype" are different\n'
        "\\[left\\]:  Int64\n"
        "\\[right\\]: int[32|64]"
    )

    tm.assert_frame_equal(left, right, check_dtype=False)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(left, right, check_dtype=True)


def test_assert_frame_equal_interval_dtype_mismatch():
    # https://github.com/pandas-dev/pandas/issues/32747
    left = DataFrame({"a": [pd.Interval(0, 1)]}, dtype="interval")
    right = left.astype(object)

    msg = (
        "Attributes of DataFrame\\.iloc\\[:, 0\\] "
        '\\(column name="a"\\) are different\n\n'
        'Attribute "dtype" are different\n'
        "\\[left\\]:  interval\\[int64, right\\]\n"
        "\\[right\\]: object"
    )

    tm.assert_frame_equal(left, right, check_dtype=False)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(left, right, check_dtype=True)


def test_assert_frame_equal_ignore_extension_dtype_mismatch():
    # https://github.com/pandas-dev/pandas/issues/35715
    left = DataFrame({"a": [1, 2, 3]}, dtype="Int64")
    right = DataFrame({"a": [1, 2, 3]}, dtype="Int32")
    tm.assert_frame_equal(left, right, check_dtype=False)


def test_assert_frame_equal_ignore_extension_dtype_mismatch_cross_class():
    # https://github.com/pandas-dev/pandas/issues/35715
    left = DataFrame({"a": [1, 2, 3]}, dtype="Int64")
    right = DataFrame({"a": [1, 2, 3]}, dtype="int64")
    tm.assert_frame_equal(left, right, check_dtype=False)


@pytest.mark.parametrize(
    "dtype",
    [
        ("timedelta64[ns]"),
        ("datetime64[ns, UTC]"),
        ("Period[D]"),
    ],
)
def test_assert_frame_equal_datetime_like_dtype_mismatch(dtype):
    df1 = DataFrame({"a": []}, dtype=dtype)
    df2 = DataFrame({"a": []})
    tm.assert_frame_equal(df1, df2, check_dtype=False)


def test_allows_duplicate_labels():
    left = DataFrame()
    right = DataFrame().set_flags(allows_duplicate_labels=False)
    tm.assert_frame_equal(left, left)
    tm.assert_frame_equal(right, right)
    tm.assert_frame_equal(left, right, check_flags=False)
    tm.assert_frame_equal(right, left, check_flags=False)

    with pytest.raises(AssertionError, match="<Flags"):
        tm.assert_frame_equal(left, right)

    with pytest.raises(AssertionError, match="<Flags"):
        tm.assert_frame_equal(left, right)


def test_assert_frame_equal_columns_mixed_dtype():
    # GH#39168
    df = DataFrame([[0, 1, 2]], columns=["foo", "bar", 42], index=[1, "test", 2])
    tm.assert_frame_equal(df, df, check_like=True)


def test_frame_equal_extension_dtype(frame_or_series, any_numeric_ea_dtype):
    # GH#39410
    obj = frame_or_series([1, 2], dtype=any_numeric_ea_dtype)
    tm.assert_equal(obj, obj, check_exact=True)


@pytest.mark.parametrize("indexer", [(0, 1), (1, 0)])
def test_frame_equal_mixed_dtypes(frame_or_series, any_numeric_ea_dtype, indexer):
    dtypes = (any_numeric_ea_dtype, "int64")
    obj1 = frame_or_series([1, 2], dtype=dtypes[indexer[0]])
    obj2 = frame_or_series([1, 2], dtype=dtypes[indexer[1]])
    tm.assert_equal(obj1, obj2, check_exact=True, check_dtype=False)


def test_assert_frame_equal_check_like_different_indexes():
    # GH#39739
    df1 = DataFrame(index=pd.Index([], dtype="object"))
    df2 = DataFrame(index=pd.RangeIndex(start=0, stop=0, step=1))
    with pytest.raises(AssertionError, match="DataFrame.index are different"):
        tm.assert_frame_equal(df1, df2, check_like=True)


def test_assert_frame_equal_checking_allow_dups_flag():
    # GH#45554
    left = DataFrame([[1, 2], [3, 4]])
    left.flags.allows_duplicate_labels = False

    right = DataFrame([[1, 2], [3, 4]])
    right.flags.allows_duplicate_labels = True
    tm.assert_frame_equal(left, right, check_flags=False)

    with pytest.raises(AssertionError, match="allows_duplicate_labels"):
        tm.assert_frame_equal(left, right, check_flags=True)


def test_assert_frame_equal_check_like_categorical_midx():
    # GH#48975
    left = DataFrame(
        [[1], [2], [3]],
        index=pd.MultiIndex.from_arrays(
            [
                pd.Categorical(["a", "b", "c"]),
                pd.Categorical(["a", "b", "c"]),
            ]
        ),
    )
    right = DataFrame(
        [[3], [2], [1]],
        index=pd.MultiIndex.from_arrays(
            [
                pd.Categorical(["c", "b", "a"]),
                pd.Categorical(["c", "b", "a"]),
            ]
        ),
    )
    tm.assert_frame_equal(left, right, check_like=True)


def test_assert_frame_equal_ea_column_definition_in_exception_mask():
    # GH#50323
    df1 = DataFrame({"a": pd.Series([pd.NA, 1], dtype="Int64")})
    df2 = DataFrame({"a": pd.Series([1, 1], dtype="Int64")})

    msg = r'DataFrame.iloc\[:, 0\] \(column name="a"\) NA mask values are different'
    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2)


def test_assert_frame_equal_ea_column_definition_in_exception():
    # GH#50323
    df1 = DataFrame({"a": pd.Series([pd.NA, 1], dtype="Int64")})
    df2 = DataFrame({"a": pd.Series([pd.NA, 2], dtype="Int64")})

    msg = r'DataFrame.iloc\[:, 0\] \(column name="a"\) values are different'
    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2)

    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2, check_exact=True)


def test_assert_frame_equal_ts_column():
    # GH#50323
    df1 = DataFrame({"a": [pd.Timestamp("2019-12-31"), pd.Timestamp("2020-12-31")]})
    df2 = DataFrame({"a": [pd.Timestamp("2020-12-31"), pd.Timestamp("2020-12-31")]})

    msg = r'DataFrame.iloc\[:, 0\] \(column name="a"\) values are different'
    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2)


def test_assert_frame_equal_set():
    # GH#51727
    df1 = DataFrame({"set_column": [{1, 2, 3}, {4, 5, 6}]})
    df2 = DataFrame({"set_column": [{1, 2, 3}, {4, 5, 6}]})
    tm.assert_frame_equal(df1, df2)


def test_assert_frame_equal_set_mismatch():
    # GH#51727
    df1 = DataFrame({"set_column": [{1, 2, 3}, {4, 5, 6}]})
    df2 = DataFrame({"set_column": [{1, 2, 3}, {4, 5, 7}]})

    msg = r'DataFrame.iloc\[:, 0\] \(column name="set_column"\) values are different'
    with pytest.raises(AssertionError, match=msg):
        tm.assert_frame_equal(df1, df2)
