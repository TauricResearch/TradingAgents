"""
Testing that we work in the downstream packages
"""
import array
import subprocess
import sys

import numpy as np
import pytest

from pandas.errors import IntCastingNaNError
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    DataFrame,
    DatetimeIndex,
    Series,
    TimedeltaIndex,
)
import pandas._testing as tm
from pandas.core.arrays import (
    DatetimeArray,
    TimedeltaArray,
)
from pandas.util.version import Version


@pytest.fixture
def df():
    return DataFrame({"A": [1, 2, 3]})


def test_dask(df):
    # dask sets "compute.use_numexpr" to False, so catch the current value
    # and ensure to reset it afterwards to avoid impacting other tests
    olduse = pd.get_option("compute.use_numexpr")

    try:
        pytest.importorskip("toolz")
        dd = pytest.importorskip("dask.dataframe")

        ddf = dd.from_pandas(df, npartitions=3)
        assert ddf.A is not None
        assert ddf.compute() is not None
    finally:
        pd.set_option("compute.use_numexpr", olduse)


def test_dask_ufunc():
    # dask sets "compute.use_numexpr" to False, so catch the current value
    # and ensure to reset it afterwards to avoid impacting other tests
    olduse = pd.get_option("compute.use_numexpr")

    try:
        da = pytest.importorskip("dask.array")
        dd = pytest.importorskip("dask.dataframe")

        s = Series([1.5, 2.3, 3.7, 4.0])
        ds = dd.from_pandas(s, npartitions=2)

        result = da.fix(ds).compute()
        expected = np.fix(s)
        tm.assert_series_equal(result, expected)
    finally:
        pd.set_option("compute.use_numexpr", olduse)


def test_construct_dask_float_array_int_dtype_match_ndarray():
    # GH#40110 make sure we treat a float-dtype dask array with the same
    #  rules we would for an ndarray
    dd = pytest.importorskip("dask.dataframe")

    arr = np.array([1, 2.5, 3])
    darr = dd.from_array(arr)

    res = Series(darr)
    expected = Series(arr)
    tm.assert_series_equal(res, expected)

    # GH#49599 in 2.0 we raise instead of silently ignoring the dtype
    msg = "Trying to coerce float values to integers"
    with pytest.raises(ValueError, match=msg):
        Series(darr, dtype="i8")

    msg = r"Cannot convert non-finite values \(NA or inf\) to integer"
    arr[2] = np.nan
    with pytest.raises(IntCastingNaNError, match=msg):
        Series(darr, dtype="i8")
    # which is the same as we get with a numpy input
    with pytest.raises(IntCastingNaNError, match=msg):
        Series(arr, dtype="i8")


def test_xarray(df):
    pytest.importorskip("xarray")

    assert df.to_xarray() is not None


def test_xarray_cftimeindex_nearest():
    # https://github.com/pydata/xarray/issues/3751
    cftime = pytest.importorskip("cftime")
    xarray = pytest.importorskip("xarray")

    times = xarray.cftime_range("0001", periods=2)
    key = cftime.DatetimeGregorian(2000, 1, 1)
    result = times.get_indexer([key], method="nearest")
    expected = 1
    assert result == expected


@pytest.mark.single_cpu
def test_oo_optimizable():
    # GH 21071
    subprocess.check_call([sys.executable, "-OO", "-c", "import pandas"])


@pytest.mark.single_cpu
def test_oo_optimized_datetime_index_unpickle():
    # GH 42866
    subprocess.check_call(
        [
            sys.executable,
            "-OO",
            "-c",
            (
                "import pandas as pd, pickle; "
                "pickle.loads(pickle.dumps(pd.date_range('2021-01-01', periods=1)))"
            ),
        ]
    )


def test_statsmodels():
    smf = pytest.importorskip("statsmodels.formula.api")

    df = DataFrame(
        {"Lottery": range(5), "Literacy": range(5), "Pop1831": range(100, 105)}
    )
    smf.ols("Lottery ~ Literacy + np.log(Pop1831)", data=df).fit()


def test_scikit_learn():
    pytest.importorskip("sklearn")
    from sklearn import (
        datasets,
        svm,
    )

    digits = datasets.load_digits()
    clf = svm.SVC(gamma=0.001, C=100.0)
    clf.fit(digits.data[:-1], digits.target[:-1])
    clf.predict(digits.data[-1:])


def test_seaborn():
    seaborn = pytest.importorskip("seaborn")
    tips = DataFrame(
        {"day": pd.date_range("2023", freq="D", periods=5), "total_bill": range(5)}
    )
    seaborn.stripplot(x="day", y="total_bill", data=tips)


def test_pandas_datareader():
    pytest.importorskip("pandas_datareader")


@pytest.mark.filterwarnings("ignore:Passing a BlockManager:DeprecationWarning")
def test_pyarrow(df):
    pyarrow = pytest.importorskip("pyarrow")
    table = pyarrow.Table.from_pandas(df)
    result = table.to_pandas()
    tm.assert_frame_equal(result, df)


def test_yaml_dump(df):
    # GH#42748
    yaml = pytest.importorskip("yaml")

    dumped = yaml.dump(df)

    loaded = yaml.load(dumped, Loader=yaml.Loader)
    tm.assert_frame_equal(df, loaded)

    loaded2 = yaml.load(dumped, Loader=yaml.UnsafeLoader)
    tm.assert_frame_equal(df, loaded2)


@pytest.mark.single_cpu
def test_missing_required_dependency():
    # GH 23868
    # To ensure proper isolation, we pass these flags
    # -S : disable site-packages
    # -s : disable user site-packages
    # -E : disable PYTHON* env vars, especially PYTHONPATH
    # https://github.com/MacPython/pandas-wheels/pull/50

    pyexe = sys.executable.replace("\\", "/")

    # We skip this test if pandas is installed as a site package. We first
    # import the package normally and check the path to the module before
    # executing the test which imports pandas with site packages disabled.
    call = [pyexe, "-c", "import pandas;print(pandas.__file__)"]
    output = subprocess.check_output(call).decode()
    if "site-packages" in output:
        pytest.skip("pandas installed as site package")

    # This test will fail if pandas is installed as a site package. The flags
    # prevent pandas being imported and the test will report Failed: DID NOT
    # RAISE <class 'subprocess.CalledProcessError'>
    call = [pyexe, "-sSE", "-c", "import pandas"]

    msg = (
        rf"Command '\['{pyexe}', '-sSE', '-c', 'import pandas'\]' "
        "returned non-zero exit status 1."
    )

    with pytest.raises(subprocess.CalledProcessError, match=msg) as exc:
        subprocess.check_output(call, stderr=subprocess.STDOUT)

    output = exc.value.stdout.decode()
    for name in ["numpy", "pytz", "dateutil"]:
        assert name in output


def test_frame_setitem_dask_array_into_new_col(request):
    # GH#47128

    # dask sets "compute.use_numexpr" to False, so catch the current value
    # and ensure to reset it afterwards to avoid impacting other tests
    olduse = pd.get_option("compute.use_numexpr")

    try:
        dask = pytest.importorskip("dask")
        da = pytest.importorskip("dask.array")
        if Version(dask.__version__) <= Version("2025.1.0") and Version(
            np.__version__
        ) >= Version("2.1"):
            request.applymarker(
                pytest.mark.xfail(reason="loc.__setitem__ incorrectly mutated column c")
            )

        dda = da.array([1, 2])
        df = DataFrame({"a": ["a", "b"]})
        df["b"] = dda
        df["c"] = dda
        df.loc[[False, True], "b"] = 100
        result = df.loc[[1], :]
        expected = DataFrame({"a": ["b"], "b": [100], "c": [2]}, index=[1])
        tm.assert_frame_equal(result, expected)
    finally:
        pd.set_option("compute.use_numexpr", olduse)


def test_pandas_priority():
    # GH#48347

    class MyClass:
        __pandas_priority__ = 5000

        def __radd__(self, other):
            return self

    left = MyClass()
    right = Series(range(3))

    assert right.__add__(left) is NotImplemented
    assert right + left is left


@pytest.fixture(
    params=[
        "memoryview",
        "array",
        pytest.param("dask", marks=td.skip_if_no("dask.array")),
        pytest.param("xarray", marks=td.skip_if_no("xarray")),
    ]
)
def array_likes(request):
    """
    Fixture giving a numpy array and a parametrized 'data' object, which can
    be a memoryview, array, dask or xarray object created from the numpy array.
    """
    # GH#24539 recognize e.g xarray, dask, ...
    arr = np.array([1, 2, 3], dtype=np.int64)

    name = request.param
    if name == "memoryview":
        data = memoryview(arr)
    elif name == "array":
        data = array.array("i", arr)
    elif name == "dask":
        import dask.array

        data = dask.array.array(arr)
    elif name == "xarray":
        import xarray as xr

        data = xr.DataArray(arr)

    return arr, data


@pytest.mark.parametrize("dtype", ["M8[ns]", "m8[ns]"])
def test_from_obscure_array(dtype, array_likes):
    # GH#24539 recognize e.g xarray, dask, ...
    # Note: we dont do this for PeriodArray bc _from_sequence won't accept
    #  an array of integers
    # TODO: could check with arraylike of Period objects
    arr, data = array_likes

    cls = {"M8[ns]": DatetimeArray, "m8[ns]": TimedeltaArray}[dtype]

    depr_msg = f"{cls.__name__}.__init__ is deprecated"
    with tm.assert_produces_warning(FutureWarning, match=depr_msg):
        expected = cls(arr)
    result = cls._from_sequence(data, dtype=dtype)
    tm.assert_extension_array_equal(result, expected)

    if not isinstance(data, memoryview):
        # FIXME(GH#44431) these raise on memoryview and attempted fix
        #  fails on py3.10
        func = {"M8[ns]": pd.to_datetime, "m8[ns]": pd.to_timedelta}[dtype]
        result = func(arr).array
        expected = func(data).array
        tm.assert_equal(result, expected)

    # Let's check the Indexes while we're here
    idx_cls = {"M8[ns]": DatetimeIndex, "m8[ns]": TimedeltaIndex}[dtype]
    result = idx_cls(arr)
    expected = idx_cls(data)
    tm.assert_index_equal(result, expected)


def test_dataframe_consortium() -> None:
    """
    Test some basic methods of the dataframe consortium standard.

    Full testing is done at https://github.com/data-apis/dataframe-api-compat,
    this is just to check that the entry point works as expected.
    """
    pytest.importorskip("dataframe_api_compat")
    df_pd = DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    df = df_pd.__dataframe_consortium_standard__()
    result_1 = df.get_column_names()
    expected_1 = ["a", "b"]
    assert result_1 == expected_1

    ser = Series([1, 2, 3], name="a")
    col = ser.__column_consortium_standard__()
    assert col.name == "a"


def test_xarray_coerce_unit():
    # GH44053
    xr = pytest.importorskip("xarray")

    arr = xr.DataArray([1, 2, 3])
    result = pd.to_datetime(arr, unit="ns")
    expected = DatetimeIndex(
        [
            "1970-01-01 00:00:00.000000001",
            "1970-01-01 00:00:00.000000002",
            "1970-01-01 00:00:00.000000003",
        ],
        dtype="datetime64[ns]",
        freq=None,
    )
    tm.assert_index_equal(result, expected)
