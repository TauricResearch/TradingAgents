from datetime import datetime
import sys

import numpy as np
import pytest

from pandas.compat import PYPY

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    Series,
)
import pandas._testing as tm
from pandas.core.accessor import PandasDelegate
from pandas.core.base import (
    NoNewAttributesMixin,
    PandasObject,
)


def series_via_frame_from_dict(x, **kwargs):
    return DataFrame({"a": x}, **kwargs)["a"]


def series_via_frame_from_scalar(x, **kwargs):
    return DataFrame(x, **kwargs)[0]


@pytest.fixture(
    params=[
        Series,
        series_via_frame_from_dict,
        series_via_frame_from_scalar,
        Index,
    ],
    ids=["Series", "DataFrame-dict", "DataFrame-array", "Index"],
)
def constructor(request):
    return request.param


class TestPandasDelegate:
    class Delegator:
        _properties = ["prop"]
        _methods = ["test_method"]

        def _set_prop(self, value):
            self.prop = value

        def _get_prop(self):
            return self.prop

        prop = property(_get_prop, _set_prop, doc="foo property")

        def test_method(self, *args, **kwargs):
            """a test method"""

    class Delegate(PandasDelegate, PandasObject):
        def __init__(self, obj) -> None:
            self.obj = obj

    def test_invalid_delegation(self):
        # these show that in order for the delegation to work
        # the _delegate_* methods need to be overridden to not raise
        # a TypeError

        self.Delegate._add_delegate_accessors(
            delegate=self.Delegator,
            accessors=self.Delegator._properties,
            typ="property",
        )
        self.Delegate._add_delegate_accessors(
            delegate=self.Delegator, accessors=self.Delegator._methods, typ="method"
        )

        delegate = self.Delegate(self.Delegator())

        msg = "You cannot access the property prop"
        with pytest.raises(TypeError, match=msg):
            delegate.prop

        msg = "The property prop cannot be set"
        with pytest.raises(TypeError, match=msg):
            delegate.prop = 5

        msg = "You cannot access the property prop"
        with pytest.raises(TypeError, match=msg):
            delegate.prop

    @pytest.mark.skipif(PYPY, reason="not relevant for PyPy")
    def test_memory_usage(self):
        # Delegate does not implement memory_usage.
        # Check that we fall back to in-built `__sizeof__`
        # GH 12924
        delegate = self.Delegate(self.Delegator())
        sys.getsizeof(delegate)


class TestNoNewAttributesMixin:
    def test_mixin(self):
        class T(NoNewAttributesMixin):
            pass

        t = T()
        assert not hasattr(t, "__frozen")

        t.a = "test"
        assert t.a == "test"

        t._freeze()
        assert "__frozen" in dir(t)
        assert getattr(t, "__frozen")
        msg = "You cannot add any new attribute"
        with pytest.raises(AttributeError, match=msg):
            t.b = "test"

        assert not hasattr(t, "b")


class TestConstruction:
    # test certain constructor behaviours on dtype inference across Series,
    # Index and DataFrame

    @pytest.mark.parametrize(
        "a",
        [
            np.array(["2263-01-01"], dtype="datetime64[D]"),
            np.array([datetime(2263, 1, 1)], dtype=object),
            np.array([np.datetime64("2263-01-01", "D")], dtype=object),
            np.array(["2263-01-01"], dtype=object),
        ],
        ids=[
            "datetime64[D]",
            "object-datetime.datetime",
            "object-numpy-scalar",
            "object-string",
        ],
    )
    def test_constructor_datetime_outofbound(
        self, a, constructor, request, using_infer_string
    ):
        # GH-26853 (+ bug GH-26206 out of bound non-ns unit)

        # No dtype specified (dtype inference)
        # datetime64[non-ns] raise error, other cases result in object dtype
        # and preserve original data
        if a.dtype.kind == "M":
            # Can't fit in nanosecond bounds -> get the nearest supported unit
            result = constructor(a)
            assert result.dtype == "M8[s]"
        else:
            result = constructor(a)
            if using_infer_string and "object-string" in request.node.callspec.id:
                assert result.dtype == "string"
            else:
                assert result.dtype == "object"
            tm.assert_numpy_array_equal(result.to_numpy(), a)

        # Explicit dtype specified
        # Forced conversion fails for all -> all cases raise error
        msg = "Out of bounds|Out of bounds .* present at position 0"
        with pytest.raises(pd.errors.OutOfBoundsDatetime, match=msg):
            constructor(a, dtype="datetime64[ns]")

    def test_constructor_datetime_nonns(self, constructor):
        arr = np.array(["2020-01-01T00:00:00.000000"], dtype="datetime64[us]")
        dta = pd.core.arrays.DatetimeArray._simple_new(arr, dtype=arr.dtype)
        expected = constructor(dta)
        assert expected.dtype == arr.dtype

        result = constructor(arr)
        tm.assert_equal(result, expected)

        # https://github.com/pandas-dev/pandas/issues/34843
        arr.flags.writeable = False
        result = constructor(arr)
        tm.assert_equal(result, expected)

    def test_constructor_from_dict_keys(self, constructor, using_infer_string):
        # https://github.com/pandas-dev/pandas/issues/60343
        d = {"a": 1, "b": 2}
        result = constructor(d.keys(), dtype="str")
        if using_infer_string:
            assert result.dtype == "str"
        else:
            assert result.dtype == "object"
        expected = constructor(list(d.keys()), dtype="str")
        tm.assert_equal(result, expected)
