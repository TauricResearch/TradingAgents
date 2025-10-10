from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Any, Optional, Union, Tuple, List, Dict

from numpy import ndarray  # TODO use ArrayLike?
from pandas import Series, Index, Timestamp, Timedelta
from matplotlib.colors import Colormap, Normalize


ColumnName = Union[
    str, bytes, date, datetime, timedelta, bool, complex, Timestamp, Timedelta
]
Vector = Union[Series, Index, ndarray]

VariableSpec = Union[ColumnName, Vector, None]
VariableSpecList = Union[List[VariableSpec], Index, None]

# A DataSource can be an object implementing __dataframe__, or a Mapping
# (and is optional in all contexts where it is used).
# I don't think there's an abc for "has __dataframe__", so we type as object
# but keep the (slightly odd) Union alias for better user-facing annotations.
DataSource = Union[object, Mapping, None]

OrderSpec = Union[Iterable, None]  # TODO technically str is iterable
NormSpec = Union[Tuple[Optional[float], Optional[float]], Normalize, None]

# TODO for discrete mappings, it would be ideal to use a parameterized type
# as the dict values / list entries should be of specific type(s) for each method
PaletteSpec = Union[str, list, dict, Colormap, None]
DiscreteValueSpec = Union[dict, list, None]
ContinuousValueSpec = Union[
    Tuple[float, float], List[float], Dict[Any, float], None,
]


class Default:
    def __repr__(self):
        return "<default>"


class Deprecated:
    def __repr__(self):
        return "<deprecated>"


default = Default()
deprecated = Deprecated()
