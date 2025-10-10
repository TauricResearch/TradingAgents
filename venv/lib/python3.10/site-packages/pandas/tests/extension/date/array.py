from __future__ import annotations

import datetime as dt
from typing import (
    TYPE_CHECKING,
    Any,
    cast,
)

import numpy as np

from pandas.core.dtypes.dtypes import register_extension_dtype

from pandas.api.extensions import (
    ExtensionArray,
    ExtensionDtype,
)
from pandas.api.types import pandas_dtype

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pandas._typing import (
        Dtype,
        PositionalIndexer,
    )


@register_extension_dtype
class DateDtype(ExtensionDtype):
    @property
    def type(self):
        return dt.date

    @property
    def name(self):
        return "DateDtype"

    @classmethod
    def construct_from_string(cls, string: str):
        if not isinstance(string, str):
            raise TypeError(
                f"'construct_from_string' expects a string, got {type(string)}"
            )

        if string == cls.__name__:
            return cls()
        else:
            raise TypeError(f"Cannot construct a '{cls.__name__}' from '{string}'")

    @classmethod
    def construct_array_type(cls):
        return DateArray

    @property
    def na_value(self):
        return dt.date.min

    def __repr__(self) -> str:
        return self.name


class DateArray(ExtensionArray):
    def __init__(
        self,
        dates: (
            dt.date
            | Sequence[dt.date]
            | tuple[np.ndarray, np.ndarray, np.ndarray]
            | np.ndarray
        ),
    ) -> None:
        if isinstance(dates, dt.date):
            self._year = np.array([dates.year])
            self._month = np.array([dates.month])
            self._day = np.array([dates.year])
            return

        ldates = len(dates)
        if isinstance(dates, list):
            # pre-allocate the arrays since we know the size before hand
            self._year = np.zeros(ldates, dtype=np.uint16)  # 65535 (0, 9999)
            self._month = np.zeros(ldates, dtype=np.uint8)  # 255 (1, 31)
            self._day = np.zeros(ldates, dtype=np.uint8)  # 255 (1, 12)
            # populate them
            for i, (y, m, d) in enumerate(
                (date.year, date.month, date.day) for date in dates
            ):
                self._year[i] = y
                self._month[i] = m
                self._day[i] = d

        elif isinstance(dates, tuple):
            # only support triples
            if ldates != 3:
                raise ValueError("only triples are valid")
            # check if all elements have the same type
            if any(not isinstance(x, np.ndarray) for x in dates):
                raise TypeError("invalid type")
            ly, lm, ld = (len(cast(np.ndarray, d)) for d in dates)
            if not ly == lm == ld:
                raise ValueError(
                    f"tuple members must have the same length: {(ly, lm, ld)}"
                )
            self._year = dates[0].astype(np.uint16)
            self._month = dates[1].astype(np.uint8)
            self._day = dates[2].astype(np.uint8)

        elif isinstance(dates, np.ndarray) and dates.dtype == "U10":
            self._year = np.zeros(ldates, dtype=np.uint16)  # 65535 (0, 9999)
            self._month = np.zeros(ldates, dtype=np.uint8)  # 255 (1, 31)
            self._day = np.zeros(ldates, dtype=np.uint8)  # 255 (1, 12)

            # error: "object_" object is not iterable
            obj = np.char.split(dates, sep="-")
            for (i,), (y, m, d) in np.ndenumerate(obj):  # type: ignore[misc]
                self._year[i] = int(y)
                self._month[i] = int(m)
                self._day[i] = int(d)

        else:
            raise TypeError(f"{type(dates)} is not supported")

    @property
    def dtype(self) -> ExtensionDtype:
        return DateDtype()

    def astype(self, dtype, copy=True):
        dtype = pandas_dtype(dtype)

        if isinstance(dtype, DateDtype):
            data = self.copy() if copy else self
        else:
            data = self.to_numpy(dtype=dtype, copy=copy, na_value=dt.date.min)

        return data

    @property
    def nbytes(self) -> int:
        return self._year.nbytes + self._month.nbytes + self._day.nbytes

    def __len__(self) -> int:
        return len(self._year)  # all 3 arrays are enforced to have the same length

    def __getitem__(self, item: PositionalIndexer):
        if isinstance(item, int):
            return dt.date(self._year[item], self._month[item], self._day[item])
        else:
            raise NotImplementedError("only ints are supported as indexes")

    def __setitem__(self, key: int | slice | np.ndarray, value: Any) -> None:
        if not isinstance(key, int):
            raise NotImplementedError("only ints are supported as indexes")

        if not isinstance(value, dt.date):
            raise TypeError("you can only set datetime.date types")

        self._year[key] = value.year
        self._month[key] = value.month
        self._day[key] = value.day

    def __repr__(self) -> str:
        return f"DateArray{list(zip(self._year, self._month, self._day))}"

    def copy(self) -> DateArray:
        return DateArray((self._year.copy(), self._month.copy(), self._day.copy()))

    def isna(self) -> np.ndarray:
        return np.logical_and(
            np.logical_and(
                self._year == dt.date.min.year, self._month == dt.date.min.month
            ),
            self._day == dt.date.min.day,
        )

    @classmethod
    def _from_sequence(cls, scalars, *, dtype: Dtype | None = None, copy=False):
        if isinstance(scalars, dt.date):
            raise TypeError
        elif isinstance(scalars, DateArray):
            if dtype is not None:
                return scalars.astype(dtype, copy=copy)
            if copy:
                return scalars.copy()
            return scalars[:]
        elif isinstance(scalars, np.ndarray):
            scalars = scalars.astype("U10")  # 10 chars for yyyy-mm-dd
            return DateArray(scalars)
