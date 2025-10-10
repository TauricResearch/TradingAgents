""" test parquet compat """
import datetime
from decimal import Decimal
from io import BytesIO
import os
import pathlib

import numpy as np
import pytest

from pandas._config import (
    using_copy_on_write,
    using_string_dtype,
)
from pandas._config.config import _get_option

from pandas.compat import is_platform_windows
from pandas.compat.pyarrow import (
    pa_version_under11p0,
    pa_version_under13p0,
    pa_version_under15p0,
    pa_version_under19p0,
    pa_version_under20p0,
)

import pandas as pd
import pandas._testing as tm
from pandas.util.version import Version

from pandas.io.parquet import (
    FastParquetImpl,
    PyArrowImpl,
    get_engine,
    read_parquet,
    to_parquet,
)

try:
    import pyarrow

    _HAVE_PYARROW = True
except ImportError:
    _HAVE_PYARROW = False

try:
    import fastparquet

    _HAVE_FASTPARQUET = True
except ImportError:
    _HAVE_FASTPARQUET = False


# TODO(ArrayManager) fastparquet relies on BlockManager internals

pytestmark = [
    pytest.mark.filterwarnings("ignore:DataFrame._data is deprecated:FutureWarning"),
    pytest.mark.filterwarnings(
        "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
    ),
]


# setup engines & skips
@pytest.fixture(
    params=[
        pytest.param(
            "fastparquet",
            marks=[
                pytest.mark.skipif(
                    not _HAVE_FASTPARQUET
                    or _get_option("mode.data_manager", silent=True) == "array",
                    reason="fastparquet is not installed or ArrayManager is used",
                ),
                pytest.mark.xfail(
                    using_string_dtype(),
                    reason="TODO(infer_string) fastparquet",
                    strict=False,
                ),
            ],
        ),
        pytest.param(
            "pyarrow",
            marks=pytest.mark.skipif(
                not _HAVE_PYARROW, reason="pyarrow is not installed"
            ),
        ),
    ]
)
def engine(request):
    return request.param


@pytest.fixture
def pa():
    if not _HAVE_PYARROW:
        pytest.skip("pyarrow is not installed")
    return "pyarrow"


@pytest.fixture
def fp(request):
    if not _HAVE_FASTPARQUET:
        pytest.skip("fastparquet is not installed")
    elif _get_option("mode.data_manager", silent=True) == "array":
        pytest.skip("ArrayManager is not supported with fastparquet")
    if using_string_dtype():
        request.applymarker(
            pytest.mark.xfail(reason="TODO(infer_string) fastparquet", strict=False)
        )
    return "fastparquet"


@pytest.fixture
def df_compat():
    return pd.DataFrame({"A": [1, 2, 3], "B": "foo"}, columns=pd.Index(["A", "B"]))


@pytest.fixture
def df_cross_compat():
    df = pd.DataFrame(
        {
            "a": list("abc"),
            "b": list(range(1, 4)),
            # 'c': np.arange(3, 6).astype('u1'),
            "d": np.arange(4.0, 7.0, dtype="float64"),
            "e": [True, False, True],
            "f": pd.date_range("20130101", periods=3),
            # 'g': pd.date_range('20130101', periods=3,
            #                    tz='US/Eastern'),
            # 'h': pd.date_range('20130101', periods=3, freq='ns')
        }
    )
    return df


@pytest.fixture
def df_full():
    return pd.DataFrame(
        {
            "string": list("abc"),
            "string_with_nan": ["a", np.nan, "c"],
            "string_with_none": ["a", None, "c"],
            "bytes": [b"foo", b"bar", b"baz"],
            "unicode": ["foo", "bar", "baz"],
            "int": list(range(1, 4)),
            "uint": np.arange(3, 6).astype("u1"),
            "float": np.arange(4.0, 7.0, dtype="float64"),
            "float_with_nan": [2.0, np.nan, 3.0],
            "bool": [True, False, True],
            "datetime": pd.date_range("20130101", periods=3),
            "datetime_with_nat": [
                pd.Timestamp("20130101"),
                pd.NaT,
                pd.Timestamp("20130103"),
            ],
        }
    )


@pytest.fixture(
    params=[
        datetime.datetime.now(datetime.timezone.utc),
        datetime.datetime.now(datetime.timezone.min),
        datetime.datetime.now(datetime.timezone.max),
        datetime.datetime.strptime("2019-01-04T16:41:24+0200", "%Y-%m-%dT%H:%M:%S%z"),
        datetime.datetime.strptime("2019-01-04T16:41:24+0215", "%Y-%m-%dT%H:%M:%S%z"),
        datetime.datetime.strptime("2019-01-04T16:41:24-0200", "%Y-%m-%dT%H:%M:%S%z"),
        datetime.datetime.strptime("2019-01-04T16:41:24-0215", "%Y-%m-%dT%H:%M:%S%z"),
    ]
)
def timezone_aware_date_list(request):
    return request.param


def check_round_trip(
    df,
    engine=None,
    path=None,
    write_kwargs=None,
    read_kwargs=None,
    expected=None,
    check_names=True,
    check_like=False,
    check_dtype=True,
    repeat=2,
):
    """Verify parquet serializer and deserializer produce the same results.

    Performs a pandas to disk and disk to pandas round trip,
    then compares the 2 resulting DataFrames to verify equality.

    Parameters
    ----------
    df: Dataframe
    engine: str, optional
        'pyarrow' or 'fastparquet'
    path: str, optional
    write_kwargs: dict of str:str, optional
    read_kwargs: dict of str:str, optional
    expected: DataFrame, optional
        Expected deserialization result, otherwise will be equal to `df`
    check_names: list of str, optional
        Closed set of column names to be compared
    check_like: bool, optional
        If True, ignore the order of index & columns.
    repeat: int, optional
        How many times to repeat the test
    """
    write_kwargs = write_kwargs or {"compression": None}
    read_kwargs = read_kwargs or {}

    if expected is None:
        expected = df

    if engine:
        write_kwargs["engine"] = engine
        read_kwargs["engine"] = engine

    def compare(repeat):
        for _ in range(repeat):
            df.to_parquet(path, **write_kwargs)
            actual = read_parquet(path, **read_kwargs)

            if "string_with_nan" in expected:
                expected.loc[1, "string_with_nan"] = None
            tm.assert_frame_equal(
                expected,
                actual,
                check_names=check_names,
                check_like=check_like,
                check_dtype=check_dtype,
            )

    if path is None:
        with tm.ensure_clean() as path:
            compare(repeat)
    else:
        compare(repeat)


def check_partition_names(path, expected):
    """Check partitions of a parquet file are as expected.

    Parameters
    ----------
    path: str
        Path of the dataset.
    expected: iterable of str
        Expected partition names.
    """
    import pyarrow.dataset as ds

    dataset = ds.dataset(path, partitioning="hive")
    assert dataset.partitioning.schema.names == expected


def test_invalid_engine(df_compat):
    msg = "engine must be one of 'pyarrow', 'fastparquet'"
    with pytest.raises(ValueError, match=msg):
        check_round_trip(df_compat, "foo", "bar")


def test_options_py(df_compat, pa, using_infer_string):
    # use the set option
    if using_infer_string and not pa_version_under19p0:
        df_compat.columns = df_compat.columns.astype("str")

    with pd.option_context("io.parquet.engine", "pyarrow"):
        check_round_trip(df_compat)


def test_options_fp(df_compat, fp):
    # use the set option

    with pd.option_context("io.parquet.engine", "fastparquet"):
        check_round_trip(df_compat)


def test_options_auto(df_compat, fp, pa):
    # use the set option

    with pd.option_context("io.parquet.engine", "auto"):
        check_round_trip(df_compat)


def test_options_get_engine(fp, pa):
    assert isinstance(get_engine("pyarrow"), PyArrowImpl)
    assert isinstance(get_engine("fastparquet"), FastParquetImpl)

    with pd.option_context("io.parquet.engine", "pyarrow"):
        assert isinstance(get_engine("auto"), PyArrowImpl)
        assert isinstance(get_engine("pyarrow"), PyArrowImpl)
        assert isinstance(get_engine("fastparquet"), FastParquetImpl)

    with pd.option_context("io.parquet.engine", "fastparquet"):
        assert isinstance(get_engine("auto"), FastParquetImpl)
        assert isinstance(get_engine("pyarrow"), PyArrowImpl)
        assert isinstance(get_engine("fastparquet"), FastParquetImpl)

    with pd.option_context("io.parquet.engine", "auto"):
        assert isinstance(get_engine("auto"), PyArrowImpl)
        assert isinstance(get_engine("pyarrow"), PyArrowImpl)
        assert isinstance(get_engine("fastparquet"), FastParquetImpl)


def test_get_engine_auto_error_message():
    # Expect different error messages from get_engine(engine="auto")
    # if engines aren't installed vs. are installed but bad version
    from pandas.compat._optional import VERSIONS

    # Do we have engines installed, but a bad version of them?
    pa_min_ver = VERSIONS.get("pyarrow")
    fp_min_ver = VERSIONS.get("fastparquet")
    have_pa_bad_version = (
        False
        if not _HAVE_PYARROW
        else Version(pyarrow.__version__) < Version(pa_min_ver)
    )
    have_fp_bad_version = (
        False
        if not _HAVE_FASTPARQUET
        else Version(fastparquet.__version__) < Version(fp_min_ver)
    )
    # Do we have usable engines installed?
    have_usable_pa = _HAVE_PYARROW and not have_pa_bad_version
    have_usable_fp = _HAVE_FASTPARQUET and not have_fp_bad_version

    if not have_usable_pa and not have_usable_fp:
        # No usable engines found.
        if have_pa_bad_version:
            match = f"Pandas requires version .{pa_min_ver}. or newer of .pyarrow."
            with pytest.raises(ImportError, match=match):
                get_engine("auto")
        else:
            match = "Missing optional dependency .pyarrow."
            with pytest.raises(ImportError, match=match):
                get_engine("auto")

        if have_fp_bad_version:
            match = f"Pandas requires version .{fp_min_ver}. or newer of .fastparquet."
            with pytest.raises(ImportError, match=match):
                get_engine("auto")
        else:
            match = "Missing optional dependency .fastparquet."
            with pytest.raises(ImportError, match=match):
                get_engine("auto")


def test_cross_engine_pa_fp(df_cross_compat, pa, fp):
    # cross-compat with differing reading/writing engines

    df = df_cross_compat
    with tm.ensure_clean() as path:
        df.to_parquet(path, engine=pa, compression=None)

        result = read_parquet(path, engine=fp)
        tm.assert_frame_equal(result, df)

        result = read_parquet(path, engine=fp, columns=["a", "d"])
        tm.assert_frame_equal(result, df[["a", "d"]])


def test_cross_engine_fp_pa(df_cross_compat, pa, fp):
    # cross-compat with differing reading/writing engines
    df = df_cross_compat
    with tm.ensure_clean() as path:
        df.to_parquet(path, engine=fp, compression=None)

        result = read_parquet(path, engine=pa)
        tm.assert_frame_equal(result, df)

        result = read_parquet(path, engine=pa, columns=["a", "d"])
        tm.assert_frame_equal(result, df[["a", "d"]])


def test_parquet_pos_args_deprecation(engine):
    # GH-54229
    df = pd.DataFrame({"a": [1, 2, 3]})
    msg = (
        r"Starting with pandas version 3.0 all arguments of to_parquet except for the "
        r"argument 'path' will be keyword-only."
    )
    with tm.ensure_clean() as path:
        with tm.assert_produces_warning(
            FutureWarning,
            match=msg,
            check_stacklevel=False,
            raise_on_extra_warnings=False,
        ):
            df.to_parquet(path, engine)


class Base:
    def check_error_on_write(self, df, engine, exc, err_msg):
        # check that we are raising the exception on writing
        with tm.ensure_clean() as path:
            with pytest.raises(exc, match=err_msg):
                to_parquet(df, path, engine, compression=None)

    def check_external_error_on_write(self, df, engine, exc):
        # check that an external library is raising the exception on writing
        with tm.ensure_clean() as path:
            with tm.external_error_raised(exc):
                to_parquet(df, path, engine, compression=None)


class TestBasic(Base):
    def test_error(self, engine):
        for obj in [
            pd.Series([1, 2, 3]),
            1,
            "foo",
            pd.Timestamp("20130101"),
            np.array([1, 2, 3]),
        ]:
            msg = "to_parquet only supports IO with DataFrames"
            self.check_error_on_write(obj, engine, ValueError, msg)

    def test_columns_dtypes(self, engine):
        df = pd.DataFrame({"string": list("abc"), "int": list(range(1, 4))})

        # unicode
        df.columns = ["foo", "bar"]
        check_round_trip(df, engine)

    @pytest.mark.parametrize("compression", [None, "gzip", "snappy", "brotli"])
    def test_compression(self, engine, compression):
        df = pd.DataFrame({"A": [1, 2, 3]})
        check_round_trip(df, engine, write_kwargs={"compression": compression})

    def test_read_columns(self, engine):
        # GH18154
        df = pd.DataFrame({"string": list("abc"), "int": list(range(1, 4))})

        expected = pd.DataFrame({"string": list("abc")})
        check_round_trip(
            df, engine, expected=expected, read_kwargs={"columns": ["string"]}
        )

    def test_read_filters(self, engine, tmp_path):
        df = pd.DataFrame(
            {
                "int": list(range(4)),
                "part": list("aabb"),
            }
        )

        expected = pd.DataFrame({"int": [0, 1]})
        check_round_trip(
            df,
            engine,
            path=tmp_path,
            expected=expected,
            write_kwargs={"partition_cols": ["part"]},
            read_kwargs={"filters": [("part", "==", "a")], "columns": ["int"]},
            repeat=1,
        )

    def test_write_index(self, engine):
        check_names = engine != "fastparquet"

        df = pd.DataFrame({"A": [1, 2, 3]})
        check_round_trip(df, engine)

        indexes = [
            [2, 3, 4],
            pd.date_range("20130101", periods=3),
            list("abc"),
            [1, 3, 4],
        ]
        # non-default index
        for index in indexes:
            df.index = index
            if isinstance(index, pd.DatetimeIndex):
                df.index = df.index._with_freq(None)  # freq doesn't round-trip
            check_round_trip(df, engine, check_names=check_names)

        # index with meta-data
        df.index = [0, 1, 2]
        df.index.name = "foo"
        check_round_trip(df, engine)

    def test_write_multiindex(self, pa):
        # Not supported in fastparquet as of 0.1.3 or older pyarrow version
        engine = pa

        df = pd.DataFrame({"A": [1, 2, 3]})
        index = pd.MultiIndex.from_tuples([("a", 1), ("a", 2), ("b", 1)])
        df.index = index
        check_round_trip(df, engine)

    def test_multiindex_with_columns(self, pa):
        engine = pa
        dates = pd.date_range("01-Jan-2018", "01-Dec-2018", freq="MS")
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((2 * len(dates), 3)),
            columns=list("ABC"),
        )
        index1 = pd.MultiIndex.from_product(
            [["Level1", "Level2"], dates], names=["level", "date"]
        )
        index2 = index1.copy(names=None)
        for index in [index1, index2]:
            df.index = index

            check_round_trip(df, engine)
            check_round_trip(
                df, engine, read_kwargs={"columns": ["A", "B"]}, expected=df[["A", "B"]]
            )

    def test_write_ignoring_index(self, engine):
        # ENH 20768
        # Ensure index=False omits the index from the written Parquet file.
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["q", "r", "s"]})

        write_kwargs = {"compression": None, "index": False}

        # Because we're dropping the index, we expect the loaded dataframe to
        # have the default integer index.
        expected = df.reset_index(drop=True)

        check_round_trip(df, engine, write_kwargs=write_kwargs, expected=expected)

        # Ignore custom index
        df = pd.DataFrame(
            {"a": [1, 2, 3], "b": ["q", "r", "s"]}, index=["zyx", "wvu", "tsr"]
        )

        check_round_trip(df, engine, write_kwargs=write_kwargs, expected=expected)

        # Ignore multi-indexes as well.
        arrays = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            ["one", "two", "one", "two", "one", "two", "one", "two"],
        ]
        df = pd.DataFrame(
            {"one": list(range(8)), "two": [-i for i in range(8)]}, index=arrays
        )

        expected = df.reset_index(drop=True)
        check_round_trip(df, engine, write_kwargs=write_kwargs, expected=expected)

    def test_write_column_multiindex(self, engine):
        # Not able to write column multi-indexes with non-string column names.
        mi_columns = pd.MultiIndex.from_tuples([("a", 1), ("a", 2), ("b", 1)])
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((4, 3)), columns=mi_columns
        )

        if engine == "fastparquet":
            self.check_error_on_write(
                df, engine, TypeError, "Column name must be a string"
            )
        elif engine == "pyarrow":
            check_round_trip(df, engine)

    def test_write_column_multiindex_nonstring(self, engine):
        # GH #34777

        # Not able to write column multi-indexes with non-string column names
        arrays = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            [1, 2, 1, 2, 1, 2, 1, 2],
        ]
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((8, 8)), columns=arrays
        )
        df.columns.names = ["Level1", "Level2"]
        if engine == "fastparquet":
            self.check_error_on_write(df, engine, ValueError, "Column name")
        elif engine == "pyarrow":
            check_round_trip(df, engine)

    def test_write_column_multiindex_string(self, pa):
        # GH #34777
        # Not supported in fastparquet as of 0.1.3
        engine = pa

        # Write column multi-indexes with string column names
        arrays = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            ["one", "two", "one", "two", "one", "two", "one", "two"],
        ]
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((8, 8)), columns=arrays
        )
        df.columns.names = ["ColLevel1", "ColLevel2"]

        check_round_trip(df, engine)

    def test_write_column_index_string(self, pa):
        # GH #34777
        # Not supported in fastparquet as of 0.1.3
        engine = pa

        # Write column indexes with string column names
        arrays = ["bar", "baz", "foo", "qux"]
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((8, 4)), columns=arrays
        )
        df.columns.name = "StringCol"

        check_round_trip(df, engine)

    def test_write_column_index_nonstring(self, engine):
        # GH #34777

        # Write column indexes with string column names
        arrays = [1, 2, 3, 4]
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((8, 4)), columns=arrays
        )
        df.columns.name = "NonStringCol"
        if engine == "fastparquet":
            self.check_error_on_write(
                df, engine, TypeError, "Column name must be a string"
            )
        else:
            check_round_trip(df, engine)

    def test_dtype_backend(self, engine, request):
        pq = pytest.importorskip("pyarrow.parquet")

        if engine == "fastparquet":
            # We are manually disabling fastparquet's
            # nullable dtype support pending discussion
            mark = pytest.mark.xfail(
                reason="Fastparquet nullable dtype support is disabled"
            )
            request.applymarker(mark)

        table = pyarrow.table(
            {
                "a": pyarrow.array([1, 2, 3, None], "int64"),
                "b": pyarrow.array([1, 2, 3, None], "uint8"),
                "c": pyarrow.array(["a", "b", "c", None]),
                "d": pyarrow.array([True, False, True, None]),
                # Test that nullable dtypes used even in absence of nulls
                "e": pyarrow.array([1, 2, 3, 4], "int64"),
                # GH 45694
                "f": pyarrow.array([1.0, 2.0, 3.0, None], "float32"),
                "g": pyarrow.array([1.0, 2.0, 3.0, None], "float64"),
            }
        )
        with tm.ensure_clean() as path:
            # write manually with pyarrow to write integers
            pq.write_table(table, path)
            result1 = read_parquet(path, engine=engine)
            result2 = read_parquet(path, engine=engine, dtype_backend="numpy_nullable")

        assert result1["a"].dtype == np.dtype("float64")
        expected = pd.DataFrame(
            {
                "a": pd.array([1, 2, 3, None], dtype="Int64"),
                "b": pd.array([1, 2, 3, None], dtype="UInt8"),
                "c": pd.array(["a", "b", "c", None], dtype="string"),
                "d": pd.array([True, False, True, None], dtype="boolean"),
                "e": pd.array([1, 2, 3, 4], dtype="Int64"),
                "f": pd.array([1.0, 2.0, 3.0, None], dtype="Float32"),
                "g": pd.array([1.0, 2.0, 3.0, None], dtype="Float64"),
            }
        )
        if engine == "fastparquet":
            # Fastparquet doesn't support string columns yet
            # Only int and boolean
            result2 = result2.drop("c", axis=1)
            expected = expected.drop("c", axis=1)
        tm.assert_frame_equal(result2, expected)

    @pytest.mark.parametrize(
        "dtype",
        [
            "Int64",
            "UInt8",
            "boolean",
            "object",
            "datetime64[ns, UTC]",
            "float",
            "period[D]",
            "Float64",
            "string",
        ],
    )
    def test_read_empty_array(self, pa, dtype):
        # GH #41241
        df = pd.DataFrame(
            {
                "value": pd.array([], dtype=dtype),
            }
        )
        # GH 45694
        expected = None
        if dtype == "float":
            expected = pd.DataFrame(
                {
                    "value": pd.array([], dtype="Float64"),
                }
            )
        check_round_trip(
            df, pa, read_kwargs={"dtype_backend": "numpy_nullable"}, expected=expected
        )

    @pytest.mark.network
    @pytest.mark.single_cpu
    def test_parquet_read_from_url(self, httpserver, datapath, df_compat, engine):
        if engine != "auto":
            pytest.importorskip(engine)
        with open(datapath("io", "data", "parquet", "simple.parquet"), mode="rb") as f:
            httpserver.serve_content(content=f.read())
            df = read_parquet(httpserver.url, engine=engine)
        tm.assert_frame_equal(df, df_compat)


class TestParquetPyArrow(Base):
    def test_basic(self, pa, df_full):
        df = df_full

        # additional supported types for pyarrow
        dti = pd.date_range("20130101", periods=3, tz="Europe/Brussels")
        dti = dti._with_freq(None)  # freq doesn't round-trip
        df["datetime_tz"] = dti
        df["bool_with_none"] = [True, None, True]

        check_round_trip(df, pa)

    def test_basic_subset_columns(self, pa, df_full):
        # GH18628

        df = df_full
        # additional supported types for pyarrow
        df["datetime_tz"] = pd.date_range("20130101", periods=3, tz="Europe/Brussels")

        check_round_trip(
            df,
            pa,
            expected=df[["string", "int"]],
            read_kwargs={"columns": ["string", "int"]},
        )

    def test_to_bytes_without_path_or_buf_provided(self, pa, df_full):
        # GH 37105
        buf_bytes = df_full.to_parquet(engine=pa)
        assert isinstance(buf_bytes, bytes)

        buf_stream = BytesIO(buf_bytes)
        res = read_parquet(buf_stream)

        expected = df_full.copy()
        expected.loc[1, "string_with_nan"] = None
        tm.assert_frame_equal(res, expected)

    def test_duplicate_columns(self, pa):
        # not currently able to handle duplicate columns
        df = pd.DataFrame(np.arange(12).reshape(4, 3), columns=list("aaa")).copy()
        self.check_error_on_write(df, pa, ValueError, "Duplicate column names found")

    def test_timedelta(self, pa):
        df = pd.DataFrame({"a": pd.timedelta_range("1 day", periods=3)})
        check_round_trip(df, pa)

    def test_unsupported(self, pa):
        # mixed python objects
        df = pd.DataFrame({"a": ["a", 1, 2.0]})
        # pyarrow 0.11 raises ArrowTypeError
        # older pyarrows raise ArrowInvalid
        self.check_external_error_on_write(df, pa, pyarrow.ArrowException)

    def test_unsupported_float16(self, pa):
        # #44847, #44914
        # Not able to write float 16 column using pyarrow.
        data = np.arange(2, 10, dtype=np.float16)
        df = pd.DataFrame(data=data, columns=["fp16"])
        if pa_version_under15p0:
            self.check_external_error_on_write(df, pa, pyarrow.ArrowException)
        else:
            check_round_trip(df, pa)

    @pytest.mark.xfail(
        is_platform_windows(),
        reason=(
            "PyArrow does not cleanup of partial files dumps when unsupported "
            "dtypes are passed to_parquet function in windows"
        ),
    )
    @pytest.mark.skipif(not pa_version_under15p0, reason="float16 works on 15")
    @pytest.mark.parametrize("path_type", [str, pathlib.Path])
    def test_unsupported_float16_cleanup(self, pa, path_type):
        # #44847, #44914
        # Not able to write float 16 column using pyarrow.
        # Tests cleanup by pyarrow in case of an error
        data = np.arange(2, 10, dtype=np.float16)
        df = pd.DataFrame(data=data, columns=["fp16"])

        with tm.ensure_clean() as path_str:
            path = path_type(path_str)
            with tm.external_error_raised(pyarrow.ArrowException):
                df.to_parquet(path=path, engine=pa)
            assert not os.path.isfile(path)

    def test_categorical(self, pa):
        # supported in >= 0.7.0
        df = pd.DataFrame(
            {
                "a": pd.Categorical(list("abcdef")),
                # test for null, out-of-order values, and unobserved category
                "b": pd.Categorical(
                    ["bar", "foo", "foo", "bar", None, "bar"],
                    dtype=pd.CategoricalDtype(["foo", "bar", "baz"]),
                ),
                # test for ordered flag
                "c": pd.Categorical(
                    ["a", "b", "c", "a", "c", "b"],
                    categories=["b", "c", "d"],
                    ordered=True,
                ),
            }
        )

        check_round_trip(df, pa)

    @pytest.mark.single_cpu
    def test_s3_roundtrip_explicit_fs(self, df_compat, s3_public_bucket, pa, s3so):
        s3fs = pytest.importorskip("s3fs")
        s3 = s3fs.S3FileSystem(**s3so)
        kw = {"filesystem": s3}
        check_round_trip(
            df_compat,
            pa,
            path=f"{s3_public_bucket.name}/pyarrow.parquet",
            read_kwargs=kw,
            write_kwargs=kw,
        )

    @pytest.mark.single_cpu
    def test_s3_roundtrip(self, df_compat, s3_public_bucket, pa, s3so):
        # GH #19134
        s3so = {"storage_options": s3so}
        check_round_trip(
            df_compat,
            pa,
            path=f"s3://{s3_public_bucket.name}/pyarrow.parquet",
            read_kwargs=s3so,
            write_kwargs=s3so,
        )

    @pytest.mark.single_cpu
    @pytest.mark.parametrize(
        "partition_col",
        [
            ["A"],
            [],
        ],
    )
    def test_s3_roundtrip_for_dir(
        self, df_compat, s3_public_bucket, pa, partition_col, s3so
    ):
        pytest.importorskip("s3fs")
        # GH #26388
        expected_df = df_compat.copy()

        # GH #35791
        if partition_col:
            expected_df = expected_df.astype(dict.fromkeys(partition_col, np.int32))
            partition_col_type = "category"

            expected_df[partition_col] = expected_df[partition_col].astype(
                partition_col_type
            )

        check_round_trip(
            df_compat,
            pa,
            expected=expected_df,
            path=f"s3://{s3_public_bucket.name}/parquet_dir",
            read_kwargs={"storage_options": s3so},
            write_kwargs={
                "partition_cols": partition_col,
                "compression": None,
                "storage_options": s3so,
            },
            check_like=True,
            repeat=1,
        )

    def test_read_file_like_obj_support(self, df_compat, using_infer_string):
        pytest.importorskip("pyarrow")
        buffer = BytesIO()
        df_compat.to_parquet(buffer)
        df_from_buf = read_parquet(buffer)
        if using_infer_string and not pa_version_under19p0:
            df_compat.columns = df_compat.columns.astype("str")
        tm.assert_frame_equal(df_compat, df_from_buf)

    def test_expand_user(self, df_compat, monkeypatch):
        pytest.importorskip("pyarrow")
        monkeypatch.setenv("HOME", "TestingUser")
        monkeypatch.setenv("USERPROFILE", "TestingUser")
        with pytest.raises(OSError, match=r".*TestingUser.*"):
            read_parquet("~/file.parquet")
        with pytest.raises(OSError, match=r".*TestingUser.*"):
            df_compat.to_parquet("~/file.parquet")

    def test_partition_cols_supported(self, tmp_path, pa, df_full):
        # GH #23283
        partition_cols = ["bool", "int"]
        df = df_full
        df.to_parquet(tmp_path, partition_cols=partition_cols, compression=None)
        check_partition_names(tmp_path, partition_cols)
        assert read_parquet(tmp_path).shape == df.shape

    def test_partition_cols_string(self, tmp_path, pa, df_full):
        # GH #27117
        partition_cols = "bool"
        partition_cols_list = [partition_cols]
        df = df_full
        df.to_parquet(tmp_path, partition_cols=partition_cols, compression=None)
        check_partition_names(tmp_path, partition_cols_list)
        assert read_parquet(tmp_path).shape == df.shape

    @pytest.mark.parametrize(
        "path_type", [str, lambda x: x], ids=["string", "pathlib.Path"]
    )
    def test_partition_cols_pathlib(self, tmp_path, pa, df_compat, path_type):
        # GH 35902

        partition_cols = "B"
        partition_cols_list = [partition_cols]
        df = df_compat

        path = path_type(tmp_path)
        df.to_parquet(path, partition_cols=partition_cols_list)
        assert read_parquet(path).shape == df.shape

    def test_empty_dataframe(self, pa):
        # GH #27339
        df = pd.DataFrame(index=[], columns=[])
        check_round_trip(df, pa)

    def test_write_with_schema(self, pa):
        import pyarrow

        df = pd.DataFrame({"x": [0, 1]})
        schema = pyarrow.schema([pyarrow.field("x", type=pyarrow.bool_())])
        out_df = df.astype(bool)
        check_round_trip(df, pa, write_kwargs={"schema": schema}, expected=out_df)

    def test_additional_extension_arrays(self, pa, using_infer_string):
        # test additional ExtensionArrays that are supported through the
        # __arrow_array__ protocol
        pytest.importorskip("pyarrow")
        df = pd.DataFrame(
            {
                "a": pd.Series([1, 2, 3], dtype="Int64"),
                "b": pd.Series([1, 2, 3], dtype="UInt32"),
                "c": pd.Series(["a", None, "c"], dtype="string"),
            }
        )
        if using_infer_string and pa_version_under19p0:
            check_round_trip(df, pa, expected=df.astype({"c": "str"}))
        else:
            check_round_trip(df, pa)

        df = pd.DataFrame({"a": pd.Series([1, 2, 3, None], dtype="Int64")})
        check_round_trip(df, pa)

    def test_pyarrow_backed_string_array(self, pa, string_storage, using_infer_string):
        # test ArrowStringArray supported through the __arrow_array__ protocol
        pytest.importorskip("pyarrow")
        df = pd.DataFrame({"a": pd.Series(["a", None, "c"], dtype="string[pyarrow]")})
        with pd.option_context("string_storage", string_storage):
            if using_infer_string:
                if pa_version_under19p0:
                    expected = df.astype("str")
                else:
                    expected = df.astype(f"string[{string_storage}]")
                expected.columns = expected.columns.astype("str")
            else:
                expected = df.astype(f"string[{string_storage}]")
            check_round_trip(df, pa, expected=expected)

    def test_additional_extension_types(self, pa):
        # test additional ExtensionArrays that are supported through the
        # __arrow_array__ protocol + by defining a custom ExtensionType
        pytest.importorskip("pyarrow")
        df = pd.DataFrame(
            {
                "c": pd.IntervalIndex.from_tuples([(0, 1), (1, 2), (3, 4)]),
                "d": pd.period_range("2012-01-01", periods=3, freq="D"),
                # GH-45881 issue with interval with datetime64[ns] subtype
                "e": pd.IntervalIndex.from_breaks(
                    pd.date_range("2012-01-01", periods=4, freq="D")
                ),
            }
        )
        check_round_trip(df, pa)

    def test_timestamp_nanoseconds(self, pa):
        # with version 2.6, pyarrow defaults to writing the nanoseconds, so
        # this should work without error
        # Note in previous pyarrows(<7.0.0), only the pseudo-version 2.0 was available
        ver = "2.6"
        df = pd.DataFrame({"a": pd.date_range("2017-01-01", freq="1ns", periods=10)})
        check_round_trip(df, pa, write_kwargs={"version": ver})

    def test_timezone_aware_index(self, pa, timezone_aware_date_list):
        pytest.importorskip("pyarrow", "11.0.0")

        idx = 5 * [timezone_aware_date_list]
        df = pd.DataFrame(index=idx, data={"index_as_col": idx})

        # see gh-36004
        # compare time(zone) values only, skip their class:
        # pyarrow always creates fixed offset timezones using pytz.FixedOffset()
        # even if it was datetime.timezone() originally
        #
        # technically they are the same:
        # they both implement datetime.tzinfo
        # they both wrap datetime.timedelta()
        # this use-case sets the resolution to 1 minute

        expected = df[:]
        if pa_version_under11p0:
            expected.index = expected.index.as_unit("ns")
        if timezone_aware_date_list.tzinfo != datetime.timezone.utc:
            # pyarrow returns pytz.FixedOffset while pandas constructs datetime.timezone
            # https://github.com/pandas-dev/pandas/issues/37286
            try:
                import pytz
            except ImportError:
                pass
            else:
                offset = df.index.tz.utcoffset(timezone_aware_date_list)
                tz = pytz.FixedOffset(offset.total_seconds() / 60)
                expected.index = expected.index.tz_convert(tz)
                expected["index_as_col"] = expected["index_as_col"].dt.tz_convert(tz)
        check_round_trip(df, pa, check_dtype=False, expected=expected)

    def test_filter_row_groups(self, pa):
        # https://github.com/pandas-dev/pandas/issues/26551
        pytest.importorskip("pyarrow")
        df = pd.DataFrame({"a": list(range(3))})
        with tm.ensure_clean() as path:
            df.to_parquet(path, engine=pa)
            result = read_parquet(path, pa, filters=[("a", "==", 0)])
        assert len(result) == 1

    def test_read_parquet_manager(self, pa, using_array_manager):
        # ensure that read_parquet honors the pandas.options.mode.data_manager option
        df = pd.DataFrame(
            np.random.default_rng(2).standard_normal((10, 3)), columns=["A", "B", "C"]
        )

        with tm.ensure_clean() as path:
            df.to_parquet(path, engine=pa)
            result = read_parquet(path, pa)
        if using_array_manager:
            assert isinstance(result._mgr, pd.core.internals.ArrayManager)
        else:
            assert isinstance(result._mgr, pd.core.internals.BlockManager)

    def test_read_dtype_backend_pyarrow_config(self, pa, df_full):
        import pyarrow

        df = df_full

        # additional supported types for pyarrow
        dti = pd.date_range("20130101", periods=3, tz="Europe/Brussels")
        dti = dti._with_freq(None)  # freq doesn't round-trip
        df["datetime_tz"] = dti
        df["bool_with_none"] = [True, None, True]

        pa_table = pyarrow.Table.from_pandas(df)
        expected = pa_table.to_pandas(types_mapper=pd.ArrowDtype)
        if pa_version_under13p0:
            # pyarrow infers datetimes as us instead of ns
            expected["datetime"] = expected["datetime"].astype("timestamp[us][pyarrow]")
            expected["datetime_with_nat"] = expected["datetime_with_nat"].astype(
                "timestamp[us][pyarrow]"
            )
            expected["datetime_tz"] = expected["datetime_tz"].astype(
                pd.ArrowDtype(pyarrow.timestamp(unit="us", tz="Europe/Brussels"))
            )

        check_round_trip(
            df,
            engine=pa,
            read_kwargs={"dtype_backend": "pyarrow"},
            expected=expected,
        )

    def test_read_dtype_backend_pyarrow_config_index(self, pa):
        df = pd.DataFrame(
            {"a": [1, 2]}, index=pd.Index([3, 4], name="test"), dtype="int64[pyarrow]"
        )
        expected = df.copy()
        import pyarrow

        if Version(pyarrow.__version__) > Version("11.0.0"):
            expected.index = expected.index.astype("int64[pyarrow]")
        check_round_trip(
            df,
            engine=pa,
            read_kwargs={"dtype_backend": "pyarrow"},
            expected=expected,
        )

    @pytest.mark.parametrize(
        "columns",
        [
            [0, 1],
            pytest.param(
                [b"foo", b"bar"],
                marks=pytest.mark.xfail(
                    pa_version_under20p0,
                    raises=NotImplementedError,
                    reason="https://github.com/apache/arrow/pull/44171",
                ),
            ),
            [
                datetime.datetime(2011, 1, 1, 0, 0),
                datetime.datetime(2011, 1, 1, 1, 1),
            ],
        ],
    )
    def test_columns_dtypes_not_invalid(self, pa, columns):
        df = pd.DataFrame({"string": list("abc"), "int": list(range(1, 4))})

        df.columns = columns
        check_round_trip(df, pa)

    def test_empty_columns(self, pa):
        # GH 52034
        df = pd.DataFrame(index=pd.Index(["a", "b", "c"], name="custom name"))
        check_round_trip(df, pa)

    def test_df_attrs_persistence(self, tmp_path, pa):
        path = tmp_path / "test_df_metadata.p"
        df = pd.DataFrame(data={1: [1]})
        df.attrs = {"test_attribute": 1}
        df.to_parquet(path, engine=pa)
        new_df = read_parquet(path, engine=pa)
        assert new_df.attrs == df.attrs

    def test_string_inference(self, tmp_path, pa, using_infer_string):
        # GH#54431
        path = tmp_path / "test_string_inference.p"
        df = pd.DataFrame(data={"a": ["x", "y"]}, index=["a", "b"])
        df.to_parquet(path, engine=pa)
        with pd.option_context("future.infer_string", True):
            result = read_parquet(path, engine=pa)
        dtype = pd.StringDtype(na_value=np.nan)
        expected = pd.DataFrame(
            data={"a": ["x", "y"]},
            dtype=dtype,
            index=pd.Index(["a", "b"], dtype=dtype),
            columns=pd.Index(
                ["a"],
                dtype=object
                if pa_version_under19p0 and not using_infer_string
                else dtype,
            ),
        )
        tm.assert_frame_equal(result, expected)

    @pytest.mark.skipif(pa_version_under11p0, reason="not supported before 11.0")
    def test_roundtrip_decimal(self, tmp_path, pa):
        # GH#54768
        import pyarrow as pa

        path = tmp_path / "decimal.p"
        df = pd.DataFrame({"a": [Decimal("123.00")]}, dtype="string[pyarrow]")
        df.to_parquet(path, schema=pa.schema([("a", pa.decimal128(5))]))
        result = read_parquet(path)
        if pa_version_under19p0:
            expected = pd.DataFrame({"a": ["123"]}, dtype="string[python]")
        else:
            expected = pd.DataFrame({"a": [Decimal("123.00")]}, dtype="object")
        tm.assert_frame_equal(result, expected)

    def test_infer_string_large_string_type(self, tmp_path, pa):
        # GH#54798
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = tmp_path / "large_string.p"

        table = pa.table({"a": pa.array([None, "b", "c"], pa.large_string())})
        pq.write_table(table, path)

        with pd.option_context("future.infer_string", True):
            result = read_parquet(path)
        expected = pd.DataFrame(
            data={"a": [None, "b", "c"]},
            dtype=pd.StringDtype(na_value=np.nan),
            columns=pd.Index(["a"], dtype=pd.StringDtype(na_value=np.nan)),
        )
        tm.assert_frame_equal(result, expected)

    # NOTE: this test is not run by default, because it requires a lot of memory (>5GB)
    # @pytest.mark.slow
    # def test_string_column_above_2GB(self, tmp_path, pa):
    #     # https://github.com/pandas-dev/pandas/issues/55606
    #     # above 2GB of string data
    #     v1 = b"x" * 100000000
    #     v2 = b"x" * 147483646
    #     df = pd.DataFrame({"strings": [v1] * 20 + [v2] + ["x"] * 20}, dtype="string")
    #     df.to_parquet(tmp_path / "test.parquet")
    #     result = read_parquet(tmp_path / "test.parquet")
    #     assert result["strings"].dtype == "string"


class TestParquetFastParquet(Base):
    def test_basic(self, fp, df_full):
        df = df_full

        dti = pd.date_range("20130101", periods=3, tz="US/Eastern")
        dti = dti._with_freq(None)  # freq doesn't round-trip
        df["datetime_tz"] = dti
        df["timedelta"] = pd.timedelta_range("1 day", periods=3)
        check_round_trip(df, fp)

    def test_columns_dtypes_invalid(self, fp):
        df = pd.DataFrame({"string": list("abc"), "int": list(range(1, 4))})

        err = TypeError
        msg = "Column name must be a string"

        # numeric
        df.columns = [0, 1]
        self.check_error_on_write(df, fp, err, msg)

        # bytes
        df.columns = [b"foo", b"bar"]
        self.check_error_on_write(df, fp, err, msg)

        # python object
        df.columns = [
            datetime.datetime(2011, 1, 1, 0, 0),
            datetime.datetime(2011, 1, 1, 1, 1),
        ]
        self.check_error_on_write(df, fp, err, msg)

    def test_duplicate_columns(self, fp):
        # not currently able to handle duplicate columns
        df = pd.DataFrame(np.arange(12).reshape(4, 3), columns=list("aaa")).copy()
        msg = "Cannot create parquet dataset with duplicate column names"
        self.check_error_on_write(df, fp, ValueError, msg)

    def test_bool_with_none(self, fp, request):
        import fastparquet

        if Version(fastparquet.__version__) < Version("2024.11.0") and Version(
            np.__version__
        ) >= Version("2.0.0"):
            request.applymarker(
                pytest.mark.xfail(
                    reason=("fastparquet uses np.float_ in numpy2"),
                )
            )
        df = pd.DataFrame({"a": [True, None, False]})
        expected = pd.DataFrame({"a": [1.0, np.nan, 0.0]}, dtype="float16")
        # Fastparquet bug in 0.7.1 makes it so that this dtype becomes
        # float64
        check_round_trip(df, fp, expected=expected, check_dtype=False)

    def test_unsupported(self, fp):
        # period
        df = pd.DataFrame({"a": pd.period_range("2013", freq="M", periods=3)})
        # error from fastparquet -> don't check exact error message
        self.check_error_on_write(df, fp, ValueError, None)

        # mixed
        df = pd.DataFrame({"a": ["a", 1, 2.0]})
        msg = "Can't infer object conversion type"
        self.check_error_on_write(df, fp, ValueError, msg)

    def test_categorical(self, fp):
        df = pd.DataFrame({"a": pd.Categorical(list("abc"))})
        check_round_trip(df, fp)

    def test_filter_row_groups(self, fp):
        d = {"a": list(range(3))}
        df = pd.DataFrame(d)
        with tm.ensure_clean() as path:
            df.to_parquet(path, engine=fp, compression=None, row_group_offsets=1)
            result = read_parquet(path, fp, filters=[("a", "==", 0)])
        assert len(result) == 1

    @pytest.mark.single_cpu
    def test_s3_roundtrip(self, df_compat, s3_public_bucket, fp, s3so):
        # GH #19134
        check_round_trip(
            df_compat,
            fp,
            path=f"s3://{s3_public_bucket.name}/fastparquet.parquet",
            read_kwargs={"storage_options": s3so},
            write_kwargs={"compression": None, "storage_options": s3so},
        )

    def test_partition_cols_supported(self, tmp_path, fp, df_full):
        # GH #23283
        partition_cols = ["bool", "int"]
        df = df_full
        df.to_parquet(
            tmp_path,
            engine="fastparquet",
            partition_cols=partition_cols,
            compression=None,
        )
        assert os.path.exists(tmp_path)
        import fastparquet

        actual_partition_cols = fastparquet.ParquetFile(str(tmp_path), False).cats
        assert len(actual_partition_cols) == 2

    def test_partition_cols_string(self, tmp_path, fp, df_full):
        # GH #27117
        partition_cols = "bool"
        df = df_full
        df.to_parquet(
            tmp_path,
            engine="fastparquet",
            partition_cols=partition_cols,
            compression=None,
        )
        assert os.path.exists(tmp_path)
        import fastparquet

        actual_partition_cols = fastparquet.ParquetFile(str(tmp_path), False).cats
        assert len(actual_partition_cols) == 1

    def test_partition_on_supported(self, tmp_path, fp, df_full):
        # GH #23283
        partition_cols = ["bool", "int"]
        df = df_full
        df.to_parquet(
            tmp_path,
            engine="fastparquet",
            compression=None,
            partition_on=partition_cols,
        )
        assert os.path.exists(tmp_path)
        import fastparquet

        actual_partition_cols = fastparquet.ParquetFile(str(tmp_path), False).cats
        assert len(actual_partition_cols) == 2

    def test_error_on_using_partition_cols_and_partition_on(
        self, tmp_path, fp, df_full
    ):
        # GH #23283
        partition_cols = ["bool", "int"]
        df = df_full
        msg = (
            "Cannot use both partition_on and partition_cols. Use partition_cols for "
            "partitioning data"
        )
        with pytest.raises(ValueError, match=msg):
            df.to_parquet(
                tmp_path,
                engine="fastparquet",
                compression=None,
                partition_on=partition_cols,
                partition_cols=partition_cols,
            )

    @pytest.mark.skipif(using_copy_on_write(), reason="fastparquet writes into Index")
    def test_empty_dataframe(self, fp):
        # GH #27339
        df = pd.DataFrame()
        expected = df.copy()
        check_round_trip(df, fp, expected=expected)

    def test_timezone_aware_index(self, fp, timezone_aware_date_list, request):
        import fastparquet

        if Version(fastparquet.__version__) > Version("2022.12") and Version(
            fastparquet.__version__
        ) < Version("2024.11.0"):
            request.applymarker(
                pytest.mark.xfail(
                    reason=(
                        "fastparquet bug, see "
                        "https://github.com/dask/fastparquet/issues/929"
                    ),
                )
            )

        idx = 5 * [timezone_aware_date_list]

        df = pd.DataFrame(index=idx, data={"index_as_col": idx})

        expected = df.copy()
        expected.index.name = "index"
        check_round_trip(df, fp, expected=expected)

    def test_use_nullable_dtypes_not_supported(self, fp):
        df = pd.DataFrame({"a": [1, 2]})

        with tm.ensure_clean() as path:
            df.to_parquet(path)
            with pytest.raises(ValueError, match="not supported for the fastparquet"):
                with tm.assert_produces_warning(FutureWarning):
                    read_parquet(path, engine="fastparquet", use_nullable_dtypes=True)
            with pytest.raises(ValueError, match="not supported for the fastparquet"):
                read_parquet(path, engine="fastparquet", dtype_backend="pyarrow")

    def test_close_file_handle_on_read_error(self):
        with tm.ensure_clean("test.parquet") as path:
            pathlib.Path(path).write_bytes(b"breakit")
            with pytest.raises(Exception, match=""):  # Not important which exception
                read_parquet(path, engine="fastparquet")
            # The next line raises an error on Windows if the file is still open
            pathlib.Path(path).unlink(missing_ok=False)

    def test_bytes_file_name(self, engine):
        # GH#48944
        df = pd.DataFrame(data={"A": [0, 1], "B": [1, 0]})
        with tm.ensure_clean("test.parquet") as path:
            with open(path.encode(), "wb") as f:
                df.to_parquet(f)

            result = read_parquet(path, engine=engine)
        tm.assert_frame_equal(result, df)

    def test_filesystem_notimplemented(self):
        pytest.importorskip("fastparquet")
        df = pd.DataFrame(data={"A": [0, 1], "B": [1, 0]})
        with tm.ensure_clean() as path:
            with pytest.raises(
                NotImplementedError, match="filesystem is not implemented"
            ):
                df.to_parquet(path, engine="fastparquet", filesystem="foo")

        with tm.ensure_clean() as path:
            pathlib.Path(path).write_bytes(b"foo")
            with pytest.raises(
                NotImplementedError, match="filesystem is not implemented"
            ):
                read_parquet(path, engine="fastparquet", filesystem="foo")

    def test_invalid_filesystem(self):
        pytest.importorskip("pyarrow")
        df = pd.DataFrame(data={"A": [0, 1], "B": [1, 0]})
        with tm.ensure_clean() as path:
            with pytest.raises(
                ValueError, match="filesystem must be a pyarrow or fsspec FileSystem"
            ):
                df.to_parquet(path, engine="pyarrow", filesystem="foo")

        with tm.ensure_clean() as path:
            pathlib.Path(path).write_bytes(b"foo")
            with pytest.raises(
                ValueError, match="filesystem must be a pyarrow or fsspec FileSystem"
            ):
                read_parquet(path, engine="pyarrow", filesystem="foo")

    def test_unsupported_pa_filesystem_storage_options(self):
        pa_fs = pytest.importorskip("pyarrow.fs")
        df = pd.DataFrame(data={"A": [0, 1], "B": [1, 0]})
        with tm.ensure_clean() as path:
            with pytest.raises(
                NotImplementedError,
                match="storage_options not supported with a pyarrow FileSystem.",
            ):
                df.to_parquet(
                    path,
                    engine="pyarrow",
                    filesystem=pa_fs.LocalFileSystem(),
                    storage_options={"foo": "bar"},
                )

        with tm.ensure_clean() as path:
            pathlib.Path(path).write_bytes(b"foo")
            with pytest.raises(
                NotImplementedError,
                match="storage_options not supported with a pyarrow FileSystem.",
            ):
                read_parquet(
                    path,
                    engine="pyarrow",
                    filesystem=pa_fs.LocalFileSystem(),
                    storage_options={"foo": "bar"},
                )

    def test_invalid_dtype_backend(self, engine):
        msg = (
            "dtype_backend numpy is invalid, only 'numpy_nullable' and "
            "'pyarrow' are allowed."
        )
        df = pd.DataFrame({"int": list(range(1, 4))})
        with tm.ensure_clean("tmp.parquet") as path:
            df.to_parquet(path)
            with pytest.raises(ValueError, match=msg):
                read_parquet(path, dtype_backend="numpy")

    @pytest.mark.skipif(using_copy_on_write(), reason="fastparquet writes into Index")
    def test_empty_columns(self, fp):
        # GH 52034
        df = pd.DataFrame(index=pd.Index(["a", "b", "c"], name="custom name"))
        expected = pd.DataFrame(index=pd.Index(["a", "b", "c"], name="custom name"))
        check_round_trip(df, fp, expected=expected)
