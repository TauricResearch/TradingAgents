from datetime import (
    datetime,
    timezone,
)

import numpy as np
import pytest

from pandas._libs.tslibs import iNaT
from pandas.compat import (
    is_ci_environment,
    is_platform_windows,
)
from pandas.compat.numpy import np_version_lt1p23

import pandas as pd
import pandas._testing as tm
from pandas.core.interchange.column import PandasColumn
from pandas.core.interchange.dataframe_protocol import (
    ColumnNullType,
    DtypeKind,
)
from pandas.core.interchange.from_dataframe import from_dataframe
from pandas.core.interchange.utils import ArrowCTypes


@pytest.fixture
def data_categorical():
    return {
        "ordered": pd.Categorical(list("testdata") * 30, ordered=True),
        "unordered": pd.Categorical(list("testdata") * 30, ordered=False),
    }


@pytest.fixture
def string_data():
    return {
        "separator data": [
            "abC|DeF,Hik",
            "234,3245.67",
            "gSaf,qWer|Gre",
            "asd3,4sad|",
            np.nan,
        ]
    }


@pytest.mark.parametrize("data", [("ordered", True), ("unordered", False)])
def test_categorical_dtype(data, data_categorical):
    df = pd.DataFrame({"A": (data_categorical[data[0]])})

    col = df.__dataframe__().get_column_by_name("A")
    assert col.dtype[0] == DtypeKind.CATEGORICAL
    assert col.null_count == 0
    assert col.describe_null == (ColumnNullType.USE_SENTINEL, -1)
    assert col.num_chunks() == 1
    desc_cat = col.describe_categorical
    assert desc_cat["is_ordered"] == data[1]
    assert desc_cat["is_dictionary"] is True
    assert isinstance(desc_cat["categories"], PandasColumn)
    tm.assert_series_equal(
        desc_cat["categories"]._col, pd.Series(["a", "d", "e", "s", "t"])
    )

    tm.assert_frame_equal(df, from_dataframe(df.__dataframe__()))


def test_categorical_pyarrow():
    # GH 49889
    pa = pytest.importorskip("pyarrow", "11.0.0")

    arr = ["Mon", "Tue", "Mon", "Wed", "Mon", "Thu", "Fri", "Sat", "Sun"]
    table = pa.table({"weekday": pa.array(arr).dictionary_encode()})
    exchange_df = table.__dataframe__()
    result = from_dataframe(exchange_df)
    weekday = pd.Categorical(
        arr, categories=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    )
    expected = pd.DataFrame({"weekday": weekday})
    tm.assert_frame_equal(result, expected)


def test_empty_categorical_pyarrow():
    # https://github.com/pandas-dev/pandas/issues/53077
    pa = pytest.importorskip("pyarrow", "11.0.0")

    arr = [None]
    table = pa.table({"arr": pa.array(arr, "float64").dictionary_encode()})
    exchange_df = table.__dataframe__()
    result = pd.api.interchange.from_dataframe(exchange_df)
    expected = pd.DataFrame({"arr": pd.Categorical([np.nan])})
    tm.assert_frame_equal(result, expected)


def test_large_string_pyarrow():
    # GH 52795
    pa = pytest.importorskip("pyarrow", "11.0.0")

    arr = ["Mon", "Tue"]
    table = pa.table({"weekday": pa.array(arr, "large_string")})
    exchange_df = table.__dataframe__()
    result = from_dataframe(exchange_df)
    expected = pd.DataFrame({"weekday": ["Mon", "Tue"]})
    tm.assert_frame_equal(result, expected)

    # check round-trip
    assert pa.Table.equals(pa.interchange.from_dataframe(result), table)


@pytest.mark.parametrize(
    ("offset", "length", "expected_values"),
    [
        (0, None, [3.3, float("nan"), 2.1]),
        (1, None, [float("nan"), 2.1]),
        (2, None, [2.1]),
        (0, 2, [3.3, float("nan")]),
        (0, 1, [3.3]),
        (1, 1, [float("nan")]),
    ],
)
def test_bitmasks_pyarrow(offset, length, expected_values):
    # GH 52795
    pa = pytest.importorskip("pyarrow", "11.0.0")

    arr = [3.3, None, 2.1]
    table = pa.table({"arr": arr}).slice(offset, length)
    exchange_df = table.__dataframe__()
    result = from_dataframe(exchange_df)
    expected = pd.DataFrame({"arr": expected_values})
    tm.assert_frame_equal(result, expected)

    # check round-trip
    assert pa.Table.equals(pa.interchange.from_dataframe(result), table)


@pytest.mark.parametrize(
    "data",
    [
        lambda: np.random.default_rng(2).integers(-100, 100),
        lambda: np.random.default_rng(2).integers(1, 100),
        lambda: np.random.default_rng(2).random(),
        lambda: np.random.default_rng(2).choice([True, False]),
        lambda: datetime(
            year=np.random.default_rng(2).integers(1900, 2100),
            month=np.random.default_rng(2).integers(1, 12),
            day=np.random.default_rng(2).integers(1, 20),
        ),
    ],
)
def test_dataframe(data):
    NCOLS, NROWS = 10, 20
    data = {
        f"col{int((i - NCOLS / 2) % NCOLS + 1)}": [data() for _ in range(NROWS)]
        for i in range(NCOLS)
    }
    df = pd.DataFrame(data)

    df2 = df.__dataframe__()

    assert df2.num_columns() == NCOLS
    assert df2.num_rows() == NROWS

    assert list(df2.column_names()) == list(data.keys())

    indices = (0, 2)
    names = tuple(list(data.keys())[idx] for idx in indices)

    result = from_dataframe(df2.select_columns(indices))
    expected = from_dataframe(df2.select_columns_by_name(names))
    tm.assert_frame_equal(result, expected)

    assert isinstance(result.attrs["_INTERCHANGE_PROTOCOL_BUFFERS"], list)
    assert isinstance(expected.attrs["_INTERCHANGE_PROTOCOL_BUFFERS"], list)


def test_missing_from_masked():
    df = pd.DataFrame(
        {
            "x": np.array([1.0, 2.0, 3.0, 4.0, 0.0]),
            "y": np.array([1.5, 2.5, 3.5, 4.5, 0]),
            "z": np.array([1.0, 0.0, 1.0, 1.0, 1.0]),
        }
    )

    rng = np.random.default_rng(2)
    dict_null = {col: rng.integers(low=0, high=len(df)) for col in df.columns}
    for col, num_nulls in dict_null.items():
        null_idx = df.index[
            rng.choice(np.arange(len(df)), size=num_nulls, replace=False)
        ]
        df.loc[null_idx, col] = None

    df2 = df.__dataframe__()

    assert df2.get_column_by_name("x").null_count == dict_null["x"]
    assert df2.get_column_by_name("y").null_count == dict_null["y"]
    assert df2.get_column_by_name("z").null_count == dict_null["z"]


@pytest.mark.parametrize(
    "data",
    [
        {"x": [1.5, 2.5, 3.5], "y": [9.2, 10.5, 11.8]},
        {"x": [1, 2, 0], "y": [9.2, 10.5, 11.8]},
        {
            "x": np.array([True, True, False]),
            "y": np.array([1, 2, 0]),
            "z": np.array([9.2, 10.5, 11.8]),
        },
    ],
)
def test_mixed_data(data):
    df = pd.DataFrame(data)
    df2 = df.__dataframe__()

    for col_name in df.columns:
        assert df2.get_column_by_name(col_name).null_count == 0


def test_mixed_missing():
    df = pd.DataFrame(
        {
            "x": np.array([True, None, False, None, True]),
            "y": np.array([None, 2, None, 1, 2]),
            "z": np.array([9.2, 10.5, None, 11.8, None]),
        }
    )

    df2 = df.__dataframe__()

    for col_name in df.columns:
        assert df2.get_column_by_name(col_name).null_count == 2


def test_string(string_data):
    test_str_data = string_data["separator data"] + [""]
    df = pd.DataFrame({"A": test_str_data})
    col = df.__dataframe__().get_column_by_name("A")

    assert col.size() == 6
    assert col.null_count == 1
    assert col.dtype[0] == DtypeKind.STRING
    assert col.describe_null == (ColumnNullType.USE_BYTEMASK, 0)

    df_sliced = df[1:]
    col = df_sliced.__dataframe__().get_column_by_name("A")
    assert col.size() == 5
    assert col.null_count == 1
    assert col.dtype[0] == DtypeKind.STRING
    assert col.describe_null == (ColumnNullType.USE_BYTEMASK, 0)


def test_nonstring_object():
    df = pd.DataFrame({"A": ["a", 10, 1.0, ()]})
    col = df.__dataframe__().get_column_by_name("A")
    with pytest.raises(NotImplementedError, match="not supported yet"):
        col.dtype


def test_datetime():
    df = pd.DataFrame({"A": [pd.Timestamp("2022-01-01"), pd.NaT]})
    col = df.__dataframe__().get_column_by_name("A")

    assert col.size() == 2
    assert col.null_count == 1
    assert col.dtype[0] == DtypeKind.DATETIME
    assert col.describe_null == (ColumnNullType.USE_SENTINEL, iNaT)

    tm.assert_frame_equal(df, from_dataframe(df.__dataframe__()))


@pytest.mark.skipif(np_version_lt1p23, reason="Numpy > 1.23 required")
def test_categorical_to_numpy_dlpack():
    # https://github.com/pandas-dev/pandas/issues/48393
    df = pd.DataFrame({"A": pd.Categorical(["a", "b", "a"])})
    col = df.__dataframe__().get_column_by_name("A")
    result = np.from_dlpack(col.get_buffers()["data"][0])
    expected = np.array([0, 1, 0], dtype="int8")
    tm.assert_numpy_array_equal(result, expected)


@pytest.mark.parametrize("data", [{}, {"a": []}])
def test_empty_pyarrow(data):
    # GH 53155
    pytest.importorskip("pyarrow", "11.0.0")
    from pyarrow.interchange import from_dataframe as pa_from_dataframe

    expected = pd.DataFrame(data)
    arrow_df = pa_from_dataframe(expected)
    result = from_dataframe(arrow_df)
    tm.assert_frame_equal(result, expected, check_column_type=False)


def test_multi_chunk_pyarrow() -> None:
    pa = pytest.importorskip("pyarrow", "11.0.0")
    n_legs = pa.chunked_array([[2, 2, 4], [4, 5, 100]])
    names = ["n_legs"]
    table = pa.table([n_legs], names=names)
    with pytest.raises(
        RuntimeError,
        match="Cannot do zero copy conversion into multi-column DataFrame block",
    ):
        pd.api.interchange.from_dataframe(table, allow_copy=False)


def test_multi_chunk_column() -> None:
    pytest.importorskip("pyarrow", "11.0.0")
    ser = pd.Series([1, 2, None], dtype="Int64[pyarrow]")
    df = pd.concat([ser, ser], ignore_index=True).to_frame("a")
    df_orig = df.copy()
    with pytest.raises(
        RuntimeError, match="Found multi-chunk pyarrow array, but `allow_copy` is False"
    ):
        pd.api.interchange.from_dataframe(df.__dataframe__(allow_copy=False))
    result = pd.api.interchange.from_dataframe(df.__dataframe__(allow_copy=True))
    # Interchange protocol defaults to creating numpy-backed columns, so currently this
    # is 'float64'.
    expected = pd.DataFrame({"a": [1.0, 2.0, None, 1.0, 2.0, None]}, dtype="float64")
    tm.assert_frame_equal(result, expected)

    # Check that the rechunking we did didn't modify the original DataFrame.
    tm.assert_frame_equal(df, df_orig)
    assert len(df["a"].array._pa_array.chunks) == 2
    assert len(df_orig["a"].array._pa_array.chunks) == 2


def test_timestamp_ns_pyarrow():
    # GH 56712
    pytest.importorskip("pyarrow", "11.0.0")
    timestamp_args = {
        "year": 2000,
        "month": 1,
        "day": 1,
        "hour": 1,
        "minute": 1,
        "second": 1,
    }
    df = pd.Series(
        [datetime(**timestamp_args)],
        dtype="timestamp[ns][pyarrow]",
        name="col0",
    ).to_frame()

    dfi = df.__dataframe__()
    result = pd.api.interchange.from_dataframe(dfi)["col0"].item()

    expected = pd.Timestamp(**timestamp_args)
    assert result == expected


@pytest.mark.parametrize("tz", ["UTC", "US/Pacific"])
@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_datetimetzdtype(tz, unit):
    # GH 54239
    tz_data = (
        pd.date_range("2018-01-01", periods=5, freq="D").tz_localize(tz).as_unit(unit)
    )
    df = pd.DataFrame({"ts_tz": tz_data})
    tm.assert_frame_equal(df, from_dataframe(df.__dataframe__()))


def test_interchange_from_non_pandas_tz_aware(request):
    # GH 54239, 54287
    pa = pytest.importorskip("pyarrow", "11.0.0")
    import pyarrow.compute as pc

    if is_platform_windows() and is_ci_environment():
        mark = pytest.mark.xfail(
            raises=pa.ArrowInvalid,
            reason=(
                "TODO: Set ARROW_TIMEZONE_DATABASE environment variable "
                "on CI to path to the tzdata for pyarrow."
            ),
        )
        request.applymarker(mark)

    arr = pa.array([datetime(2020, 1, 1), None, datetime(2020, 1, 2)])
    arr = pc.assume_timezone(arr, "Asia/Kathmandu")
    table = pa.table({"arr": arr})
    exchange_df = table.__dataframe__()
    result = from_dataframe(exchange_df)

    expected = pd.DataFrame(
        ["2020-01-01 00:00:00+05:45", "NaT", "2020-01-02 00:00:00+05:45"],
        columns=["arr"],
        dtype="datetime64[us, Asia/Kathmandu]",
    )
    tm.assert_frame_equal(expected, result)


def test_interchange_from_corrected_buffer_dtypes(monkeypatch) -> None:
    # https://github.com/pandas-dev/pandas/issues/54781
    df = pd.DataFrame({"a": ["foo", "bar"]}).__dataframe__()
    interchange = df.__dataframe__()
    column = interchange.get_column_by_name("a")
    buffers = column.get_buffers()
    buffers_data = buffers["data"]
    buffer_dtype = buffers_data[1]
    buffer_dtype = (
        DtypeKind.UINT,
        8,
        ArrowCTypes.UINT8,
        buffer_dtype[3],
    )
    buffers["data"] = (buffers_data[0], buffer_dtype)
    column.get_buffers = lambda: buffers
    interchange.get_column_by_name = lambda _: column
    monkeypatch.setattr(df, "__dataframe__", lambda allow_copy: interchange)
    pd.api.interchange.from_dataframe(df)


def test_empty_string_column():
    # https://github.com/pandas-dev/pandas/issues/56703
    df = pd.DataFrame({"a": []}, dtype=str)
    df2 = df.__dataframe__()
    result = pd.api.interchange.from_dataframe(df2)
    tm.assert_frame_equal(df, result)


def test_large_string():
    # GH#56702
    pytest.importorskip("pyarrow")
    df = pd.DataFrame({"a": ["x"]}, dtype="large_string[pyarrow]")
    result = pd.api.interchange.from_dataframe(df.__dataframe__())
    expected = pd.DataFrame({"a": ["x"]}, dtype="str")
    tm.assert_frame_equal(result, expected)


def test_non_str_names():
    # https://github.com/pandas-dev/pandas/issues/56701
    df = pd.Series([1, 2, 3], name=0).to_frame()
    names = df.__dataframe__().column_names()
    assert names == ["0"]


def test_non_str_names_w_duplicates():
    # https://github.com/pandas-dev/pandas/issues/56701
    df = pd.DataFrame({"0": [1, 2, 3], 0: [4, 5, 6]})
    dfi = df.__dataframe__()
    with pytest.raises(
        TypeError,
        match=(
            "Expected a Series, got a DataFrame. This likely happened because you "
            "called __dataframe__ on a DataFrame which, after converting column "
            r"names to string, resulted in duplicated names: Index\(\['0', '0'\], "
            r"dtype='(str|object)'\). Please rename these columns before using the "
            "interchange protocol."
        ),
    ):
        pd.api.interchange.from_dataframe(dfi, allow_copy=False)


@pytest.mark.parametrize(
    ("data", "dtype", "expected_dtype"),
    [
        ([1, 2, None], "Int64", "int64"),
        ([1, 2, None], "Int64[pyarrow]", "int64"),
        ([1, 2, None], "Int8", "int8"),
        ([1, 2, None], "Int8[pyarrow]", "int8"),
        (
            [1, 2, None],
            "UInt64",
            "uint64",
        ),
        (
            [1, 2, None],
            "UInt64[pyarrow]",
            "uint64",
        ),
        ([1.0, 2.25, None], "Float32", "float32"),
        ([1.0, 2.25, None], "Float32[pyarrow]", "float32"),
        ([True, False, None], "boolean", "bool"),
        ([True, False, None], "boolean[pyarrow]", "bool"),
        (["much ado", "about", None], pd.StringDtype(na_value=np.nan), "large_string"),
        (["much ado", "about", None], "string[pyarrow]", "large_string"),
        (
            [datetime(2020, 1, 1), datetime(2020, 1, 2), None],
            "timestamp[ns][pyarrow]",
            "timestamp[ns]",
        ),
        (
            [datetime(2020, 1, 1), datetime(2020, 1, 2), None],
            "timestamp[us][pyarrow]",
            "timestamp[us]",
        ),
        (
            [
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(2020, 1, 2, tzinfo=timezone.utc),
                None,
            ],
            "timestamp[us, Asia/Kathmandu][pyarrow]",
            "timestamp[us, tz=Asia/Kathmandu]",
        ),
    ],
)
def test_pandas_nullable_with_missing_values(
    data: list, dtype: str, expected_dtype: str
) -> None:
    # https://github.com/pandas-dev/pandas/issues/57643
    # https://github.com/pandas-dev/pandas/issues/57664
    pa = pytest.importorskip("pyarrow", "11.0.0")
    import pyarrow.interchange as pai

    if expected_dtype == "timestamp[us, tz=Asia/Kathmandu]":
        expected_dtype = pa.timestamp("us", "Asia/Kathmandu")

    df = pd.DataFrame({"a": data}, dtype=dtype)
    result = pai.from_dataframe(df.__dataframe__())["a"]
    assert result.type == expected_dtype
    assert result[0].as_py() == data[0]
    assert result[1].as_py() == data[1]
    assert result[2].as_py() is None


@pytest.mark.parametrize(
    ("data", "dtype", "expected_dtype"),
    [
        ([1, 2, 3], "Int64", "int64"),
        ([1, 2, 3], "Int64[pyarrow]", "int64"),
        ([1, 2, 3], "Int8", "int8"),
        ([1, 2, 3], "Int8[pyarrow]", "int8"),
        (
            [1, 2, 3],
            "UInt64",
            "uint64",
        ),
        (
            [1, 2, 3],
            "UInt64[pyarrow]",
            "uint64",
        ),
        ([1.0, 2.25, 5.0], "Float32", "float32"),
        ([1.0, 2.25, 5.0], "Float32[pyarrow]", "float32"),
        ([True, False, False], "boolean", "bool"),
        ([True, False, False], "boolean[pyarrow]", "bool"),
        (
            ["much ado", "about", "nothing"],
            pd.StringDtype(na_value=np.nan),
            "large_string",
        ),
        (["much ado", "about", "nothing"], "string[pyarrow]", "large_string"),
        (
            [datetime(2020, 1, 1), datetime(2020, 1, 2), datetime(2020, 1, 3)],
            "timestamp[ns][pyarrow]",
            "timestamp[ns]",
        ),
        (
            [datetime(2020, 1, 1), datetime(2020, 1, 2), datetime(2020, 1, 3)],
            "timestamp[us][pyarrow]",
            "timestamp[us]",
        ),
        (
            [
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(2020, 1, 2, tzinfo=timezone.utc),
                datetime(2020, 1, 3, tzinfo=timezone.utc),
            ],
            "timestamp[us, Asia/Kathmandu][pyarrow]",
            "timestamp[us, tz=Asia/Kathmandu]",
        ),
    ],
)
def test_pandas_nullable_without_missing_values(
    data: list, dtype: str, expected_dtype: str
) -> None:
    # https://github.com/pandas-dev/pandas/issues/57643
    pa = pytest.importorskip("pyarrow", "11.0.0")
    import pyarrow.interchange as pai

    if expected_dtype == "timestamp[us, tz=Asia/Kathmandu]":
        expected_dtype = pa.timestamp("us", "Asia/Kathmandu")

    df = pd.DataFrame({"a": data}, dtype=dtype)
    result = pai.from_dataframe(df.__dataframe__())["a"]
    assert result.type == expected_dtype
    assert result[0].as_py() == data[0]
    assert result[1].as_py() == data[1]
    assert result[2].as_py() == data[2]


def test_string_validity_buffer() -> None:
    # https://github.com/pandas-dev/pandas/issues/57761
    pytest.importorskip("pyarrow", "11.0.0")
    df = pd.DataFrame({"a": ["x"]}, dtype="large_string[pyarrow]")
    result = df.__dataframe__().get_column_by_name("a").get_buffers()["validity"]
    assert result is None


def test_string_validity_buffer_no_missing() -> None:
    # https://github.com/pandas-dev/pandas/issues/57762
    pytest.importorskip("pyarrow", "11.0.0")
    df = pd.DataFrame({"a": ["x", None]}, dtype="large_string[pyarrow]")
    validity = df.__dataframe__().get_column_by_name("a").get_buffers()["validity"]
    assert validity is not None
    result = validity[1]
    expected = (DtypeKind.BOOL, 1, ArrowCTypes.BOOL, "=")
    assert result == expected


def test_empty_dataframe():
    # https://github.com/pandas-dev/pandas/issues/56700
    df = pd.DataFrame({"a": []}, dtype="int8")
    dfi = df.__dataframe__()
    result = pd.api.interchange.from_dataframe(dfi, allow_copy=False)
    expected = pd.DataFrame({"a": []}, dtype="int8")
    tm.assert_frame_equal(result, expected)


def test_from_dataframe_list_dtype():
    pa = pytest.importorskip("pyarrow", "14.0.0")
    data = {"a": [[1, 2], [4, 5, 6]]}
    tbl = pa.table(data)
    result = from_dataframe(tbl)
    expected = pd.DataFrame(data)
    tm.assert_frame_equal(result, expected)
