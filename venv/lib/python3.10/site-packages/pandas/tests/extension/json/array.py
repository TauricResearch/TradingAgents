"""
Test extension array for storing nested data in a pandas container.

The JSONArray stores lists of dictionaries. The storage mechanism is a list,
not an ndarray.

Note
----
We currently store lists of UserDicts. Pandas has a few places
internally that specifically check for dicts, and does non-scalar things
in that case. We *want* the dictionaries to be treated as scalars, so we
hack around pandas by using UserDicts.
"""
from __future__ import annotations

from collections import (
    UserDict,
    abc,
)
import itertools
import numbers
import string
import sys
from typing import (
    TYPE_CHECKING,
    Any,
)
import warnings

import numpy as np

from pandas.util._exceptions import find_stack_level

from pandas.core.dtypes.cast import construct_1d_object_array_from_listlike
from pandas.core.dtypes.common import (
    is_bool_dtype,
    is_list_like,
    pandas_dtype,
)

import pandas as pd
from pandas.api.extensions import (
    ExtensionArray,
    ExtensionDtype,
)
from pandas.core.indexers import unpack_tuple_and_ellipses

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pandas._typing import type_t


class JSONDtype(ExtensionDtype):
    type = abc.Mapping
    name = "json"
    na_value: Mapping[str, Any] = UserDict()

    @classmethod
    def construct_array_type(cls) -> type_t[JSONArray]:
        """
        Return the array type associated with this dtype.

        Returns
        -------
        type
        """
        return JSONArray


class JSONArray(ExtensionArray):
    dtype = JSONDtype()
    __array_priority__ = 1000

    def __init__(self, values, dtype=None, copy=False) -> None:
        for val in values:
            if not isinstance(val, self.dtype.type):
                raise TypeError("All values must be of type " + str(self.dtype.type))
        self.data = values

        # Some aliases for common attribute names to ensure pandas supports
        # these
        self._items = self._data = self.data
        # those aliases are currently not working due to assumptions
        # in internal code (GH-20735)
        # self._values = self.values = self.data

    @classmethod
    def _from_sequence(cls, scalars, *, dtype=None, copy=False):
        return cls(scalars)

    @classmethod
    def _from_factorized(cls, values, original):
        return cls([UserDict(x) for x in values if x != ()])

    def __getitem__(self, item):
        if isinstance(item, tuple):
            item = unpack_tuple_and_ellipses(item)

        if isinstance(item, numbers.Integral):
            return self.data[item]
        elif isinstance(item, slice) and item == slice(None):
            # Make sure we get a view
            return type(self)(self.data)
        elif isinstance(item, slice):
            # slice
            return type(self)(self.data[item])
        elif not is_list_like(item):
            # e.g. "foo" or 2.5
            # exception message copied from numpy
            raise IndexError(
                r"only integers, slices (`:`), ellipsis (`...`), numpy.newaxis "
                r"(`None`) and integer or boolean arrays are valid indices"
            )
        else:
            item = pd.api.indexers.check_array_indexer(self, item)
            if is_bool_dtype(item.dtype):
                return type(self)._from_sequence(
                    [x for x, m in zip(self, item) if m], dtype=self.dtype
                )
            # integer
            return type(self)([self.data[i] for i in item])

    def __setitem__(self, key, value) -> None:
        if isinstance(key, numbers.Integral):
            self.data[key] = value
        else:
            if not isinstance(value, (type(self), abc.Sequence)):
                # broadcast value
                value = itertools.cycle([value])

            if isinstance(key, np.ndarray) and key.dtype == "bool":
                # masking
                for i, (k, v) in enumerate(zip(key, value)):
                    if k:
                        assert isinstance(v, self.dtype.type)
                        self.data[i] = v
            else:
                for k, v in zip(key, value):
                    assert isinstance(v, self.dtype.type)
                    self.data[k] = v

    def __len__(self) -> int:
        return len(self.data)

    def __eq__(self, other):
        return NotImplemented

    def __ne__(self, other):
        return NotImplemented

    def __array__(self, dtype=None, copy=None):
        if copy is False:
            warnings.warn(
                "Starting with NumPy 2.0, the behavior of the 'copy' keyword has "
                "changed and passing 'copy=False' raises an error when returning "
                "a zero-copy NumPy array is not possible. pandas will follow "
                "this behavior starting with pandas 3.0.\nThis conversion to "
                "NumPy requires a copy, but 'copy=False' was passed. Consider "
                "using 'np.asarray(..)' instead.",
                FutureWarning,
                stacklevel=find_stack_level(),
            )

        if dtype is None:
            dtype = object
        if dtype == object:
            # on py38 builds it looks like numpy is inferring to a non-1D array
            return construct_1d_object_array_from_listlike(list(self))
        if copy is None:
            # Note: branch avoids `copy=None` for NumPy 1.x support
            return np.asarray(self.data, dtype=dtype)
        return np.asarray(self.data, dtype=dtype, copy=copy)

    @property
    def nbytes(self) -> int:
        return sys.getsizeof(self.data)

    def isna(self):
        return np.array([x == self.dtype.na_value for x in self.data], dtype=bool)

    def take(self, indexer, allow_fill=False, fill_value=None):
        # re-implement here, since NumPy has trouble setting
        # sized objects like UserDicts into scalar slots of
        # an ndarary.
        indexer = np.asarray(indexer)
        msg = (
            "Index is out of bounds or cannot do a "
            "non-empty take from an empty array."
        )

        if allow_fill:
            if fill_value is None:
                fill_value = self.dtype.na_value
            # bounds check
            if (indexer < -1).any():
                raise ValueError
            try:
                output = [
                    self.data[loc] if loc != -1 else fill_value for loc in indexer
                ]
            except IndexError as err:
                raise IndexError(msg) from err
        else:
            try:
                output = [self.data[loc] for loc in indexer]
            except IndexError as err:
                raise IndexError(msg) from err

        return type(self)._from_sequence(output, dtype=self.dtype)

    def copy(self):
        return type(self)(self.data[:])

    def astype(self, dtype, copy=True):
        # NumPy has issues when all the dicts are the same length.
        # np.array([UserDict(...), UserDict(...)]) fails,
        # but np.array([{...}, {...}]) works, so cast.
        from pandas.core.arrays.string_ import StringDtype

        dtype = pandas_dtype(dtype)
        # needed to add this check for the Series constructor
        if isinstance(dtype, type(self.dtype)) and dtype == self.dtype:
            if copy:
                return self.copy()
            return self
        elif isinstance(dtype, StringDtype):
            arr_cls = dtype.construct_array_type()
            return arr_cls._from_sequence(self, dtype=dtype, copy=False)
        elif not copy:
            return np.asarray([dict(x) for x in self], dtype=dtype)
        else:
            return np.array([dict(x) for x in self], dtype=dtype, copy=copy)

    def unique(self):
        # Parent method doesn't work since np.array will try to infer
        # a 2-dim object.
        return type(self)([dict(x) for x in {tuple(d.items()) for d in self.data}])

    @classmethod
    def _concat_same_type(cls, to_concat):
        data = list(itertools.chain.from_iterable(x.data for x in to_concat))
        return cls(data)

    def _values_for_factorize(self):
        frozen = self._values_for_argsort()
        if len(frozen) == 0:
            # factorize_array expects 1-d array, this is a len-0 2-d array.
            frozen = frozen.ravel()
        return frozen, ()

    def _values_for_argsort(self):
        # Bypass NumPy's shape inference to get a (N,) array of tuples.
        frozen = [tuple(x.items()) for x in self]
        return construct_1d_object_array_from_listlike(frozen)

    def _pad_or_backfill(self, *, method, limit=None, copy=True):
        # GH#56616 - test EA method without limit_area argument
        return super()._pad_or_backfill(method=method, limit=limit, copy=copy)


def make_data():
    # TODO: Use a regular dict. See _NDFrameIndexer._setitem_with_indexer
    rng = np.random.default_rng(2)
    return [
        UserDict(
            [
                (rng.choice(list(string.ascii_letters)), rng.integers(0, 100))
                for _ in range(rng.integers(0, 10))
            ]
        )
        for _ in range(100)
    ]
