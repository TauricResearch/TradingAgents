import operator

import pytest

from pandas._config.config import _get_option

from pandas import (
    Series,
    options,
)


@pytest.fixture
def dtype():
    """A fixture providing the ExtensionDtype to validate."""
    raise NotImplementedError


@pytest.fixture
def data():
    """
    Length-100 array for this type.

    * data[0] and data[1] should both be non missing
    * data[0] and data[1] should not be equal
    """
    raise NotImplementedError


@pytest.fixture
def data_for_twos(dtype):
    """
    Length-100 array in which all the elements are two.

    Call pytest.skip in your fixture if the dtype does not support divmod.
    """
    if not (dtype._is_numeric or dtype.kind == "m"):
        # Object-dtypes may want to allow this, but for the most part
        #  only numeric and timedelta-like dtypes will need to implement this.
        pytest.skip(f"{dtype} is not a numeric dtype")

    raise NotImplementedError


@pytest.fixture
def data_missing():
    """Length-2 array with [NA, Valid]"""
    raise NotImplementedError


@pytest.fixture(params=["data", "data_missing"])
def all_data(request, data, data_missing):
    """Parametrized fixture giving 'data' and 'data_missing'"""
    if request.param == "data":
        return data
    elif request.param == "data_missing":
        return data_missing


@pytest.fixture
def data_repeated(data):
    """
    Generate many datasets.

    Parameters
    ----------
    data : fixture implementing `data`

    Returns
    -------
    Callable[[int], Generator]:
        A callable that takes a `count` argument and
        returns a generator yielding `count` datasets.
    """

    def gen(count):
        for _ in range(count):
            yield data

    return gen


@pytest.fixture
def data_for_sorting():
    """
    Length-3 array with a known sort order.

    This should be three items [B, C, A] with
    A < B < C

    For boolean dtypes (for which there are only 2 values available),
    set B=C=True
    """
    raise NotImplementedError


@pytest.fixture
def data_missing_for_sorting():
    """
    Length-3 array with a known sort order.

    This should be three items [B, NA, A] with
    A < B and NA missing.
    """
    raise NotImplementedError


@pytest.fixture
def na_cmp():
    """
    Binary operator for comparing NA values.

    Should return a function of two arguments that returns
    True if both arguments are (scalar) NA for your type.

    By default, uses ``operator.is_``
    """
    return operator.is_


@pytest.fixture
def na_value(dtype):
    """
    The scalar missing value for this type. Default dtype.na_value.

    TODO: can be removed in 3.x (see https://github.com/pandas-dev/pandas/pull/54930)
    """
    return dtype.na_value


@pytest.fixture
def data_for_grouping():
    """
    Data for factorization, grouping, and unique tests.

    Expected to be like [B, B, NA, NA, A, A, B, C]

    Where A < B < C and NA is missing.

    If a dtype has _is_boolean = True, i.e. only 2 unique non-NA entries,
    then set C=B.
    """
    raise NotImplementedError


@pytest.fixture(params=[True, False])
def box_in_series(request):
    """Whether to box the data in a Series"""
    return request.param


@pytest.fixture(
    params=[
        lambda x: 1,
        lambda x: [1] * len(x),
        lambda x: Series([1] * len(x)),
        lambda x: x,
    ],
    ids=["scalar", "list", "series", "object"],
)
def groupby_apply_op(request):
    """
    Functions to test groupby.apply().
    """
    return request.param


@pytest.fixture(params=[True, False])
def as_frame(request):
    """
    Boolean fixture to support Series and Series.to_frame() comparison testing.
    """
    return request.param


@pytest.fixture(params=[True, False])
def as_series(request):
    """
    Boolean fixture to support arr and Series(arr) comparison testing.
    """
    return request.param


@pytest.fixture(params=[True, False])
def use_numpy(request):
    """
    Boolean fixture to support comparison testing of ExtensionDtype array
    and numpy array.
    """
    return request.param


@pytest.fixture(params=["ffill", "bfill"])
def fillna_method(request):
    """
    Parametrized fixture giving method parameters 'ffill' and 'bfill' for
    Series.fillna(method=<method>) testing.
    """
    return request.param


@pytest.fixture(params=[True, False])
def as_array(request):
    """
    Boolean fixture to support ExtensionDtype _from_sequence method testing.
    """
    return request.param


@pytest.fixture
def invalid_scalar(data):
    """
    A scalar that *cannot* be held by this ExtensionArray.

    The default should work for most subclasses, but is not guaranteed.

    If the array can hold any item (i.e. object dtype), then use pytest.skip.
    """
    return object.__new__(object)


@pytest.fixture
def using_copy_on_write() -> bool:
    """
    Fixture to check if Copy-on-Write is enabled.
    """
    return (
        options.mode.copy_on_write is True
        and _get_option("mode.data_manager", silent=True) == "block"
    )
