"""Base module for statistical transformations."""
from __future__ import annotations
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Any
import warnings

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pandas import DataFrame
    from seaborn._core.groupby import GroupBy
    from seaborn._core.scales import Scale


@dataclass
class Stat:
    """Base class for objects that apply statistical transformations."""

    # The class supports a partial-function application pattern. The object is
    # initialized with desired parameters and the result is a callable that
    # accepts and returns dataframes.

    # The statistical transformation logic should not add any state to the instance
    # beyond what is defined with the initialization parameters.

    # Subclasses can declare whether the orient dimension should be used in grouping
    # TODO consider whether this should be a parameter. Motivating example:
    # use the same KDE class violin plots and univariate density estimation.
    # In the former case, we would expect separate densities for each unique
    # value on the orient axis, but we would not in the latter case.
    group_by_orient: ClassVar[bool] = False

    def _check_param_one_of(self, param: str, options: Iterable[Any]) -> None:
        """Raise when parameter value is not one of a specified set."""
        value = getattr(self, param)
        if value not in options:
            *most, last = options
            option_str = ", ".join(f"{x!r}" for x in most[:-1]) + f" or {last!r}"
            err = " ".join([
                f"The `{param}` parameter for `{self.__class__.__name__}` must be",
                f"one of {option_str}; not {value!r}.",
            ])
            raise ValueError(err)

    def _check_grouping_vars(
        self, param: str, data_vars: list[str], stacklevel: int = 2,
    ) -> None:
        """Warn if vars are named in parameter without being present in the data."""
        param_vars = getattr(self, param)
        undefined = set(param_vars) - set(data_vars)
        if undefined:
            param = f"{self.__class__.__name__}.{param}"
            names = ", ".join(f"{x!r}" for x in undefined)
            msg = f"Undefined variable(s) passed for {param}: {names}."
            warnings.warn(msg, stacklevel=stacklevel)

    def __call__(
        self,
        data: DataFrame,
        groupby: GroupBy,
        orient: str,
        scales: dict[str, Scale],
    ) -> DataFrame:
        """Apply statistical transform to data subgroups and return combined result."""
        return data
