"""
Test extension array that has custom attribute information (not stored on the dtype).

"""
from __future__ import annotations

import numbers
from typing import TYPE_CHECKING

import numpy as np

from pandas.core.dtypes.base import ExtensionDtype

import pandas as pd
from pandas.core.arrays import ExtensionArray

if TYPE_CHECKING:
    from pandas._typing import type_t


class FloatAttrDtype(ExtensionDtype):
    type = float
    name = "float_attr"
    na_value = np.nan

    @classmethod
    def construct_array_type(cls) -> type_t[FloatAttrArray]:
        """
        Return the array type associated with this dtype.

        Returns
        -------
        type
        """
        return FloatAttrArray


class FloatAttrArray(ExtensionArray):
    dtype = FloatAttrDtype()
    __array_priority__ = 1000

    def __init__(self, values, attr=None) -> None:
        if not isinstance(values, np.ndarray):
            raise TypeError("Need to pass a numpy array of float64 dtype as values")
        if not values.dtype == "float64":
            raise TypeError("Need to pass a numpy array of float64 dtype as values")
        self.data = values
        self.attr = attr

    @classmethod
    def _from_sequence(cls, scalars, *, dtype=None, copy=False):
        if not copy:
            data = np.asarray(scalars, dtype="float64")
        else:
            data = np.array(scalars, dtype="float64", copy=copy)
        return cls(data)

    def __getitem__(self, item):
        if isinstance(item, numbers.Integral):
            return self.data[item]
        else:
            # slice, list-like, mask
            item = pd.api.indexers.check_array_indexer(self, item)
            return type(self)(self.data[item], self.attr)

    def __len__(self) -> int:
        return len(self.data)

    def isna(self):
        return np.isnan(self.data)

    def take(self, indexer, allow_fill=False, fill_value=None):
        from pandas.api.extensions import take

        data = self.data
        if allow_fill and fill_value is None:
            fill_value = self.dtype.na_value

        result = take(data, indexer, fill_value=fill_value, allow_fill=allow_fill)
        return type(self)(result, self.attr)

    def copy(self):
        return type(self)(self.data.copy(), self.attr)

    @classmethod
    def _concat_same_type(cls, to_concat):
        data = np.concatenate([x.data for x in to_concat])
        attr = to_concat[0].attr if len(to_concat) else None
        return cls(data, attr)
