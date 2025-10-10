"""Simplified split-apply-combine paradigm on dataframes for internal use."""
from __future__ import annotations

from typing import cast, Iterable

import pandas as pd

from seaborn._core.rules import categorical_order

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Callable
    from pandas import DataFrame, MultiIndex, Index


class GroupBy:
    """
    Interface for Pandas GroupBy operations allowing specified group order.

    Writing our own class to do this has a few advantages:
    - It constrains the interface between Plot and Stat/Move objects
    - It allows control over the row order of the GroupBy result, which is
      important when using in the context of some Move operations (dodge, stack, ...)
    - It simplifies some complexities regarding the return type and Index contents
      one encounters with Pandas, especially for DataFrame -> DataFrame applies
    - It increases future flexibility regarding alternate DataFrame libraries

    """
    def __init__(self, order: list[str] | dict[str, list | None]):
        """
        Initialize the GroupBy from grouping variables and optional level orders.

        Parameters
        ----------
        order
            List of variable names or dict mapping names to desired level orders.
            Level order values can be None to use default ordering rules. The
            variables can include names that are not expected to appear in the
            data; these will be dropped before the groups are defined.

        """
        if not order:
            raise ValueError("GroupBy requires at least one grouping variable")

        if isinstance(order, list):
            order = {k: None for k in order}
        self.order = order

    def _get_groups(
        self, data: DataFrame
    ) -> tuple[str | list[str], Index | MultiIndex]:
        """Return index with Cartesian product of ordered grouping variable levels."""
        levels = {}
        for var, order in self.order.items():
            if var in data:
                if order is None:
                    order = categorical_order(data[var])
                levels[var] = order

        grouper: str | list[str]
        groups: Index | MultiIndex
        if not levels:
            grouper = []
            groups = pd.Index([])
        elif len(levels) > 1:
            grouper = list(levels)
            groups = pd.MultiIndex.from_product(levels.values(), names=grouper)
        else:
            grouper, = list(levels)
            groups = pd.Index(levels[grouper], name=grouper)
        return grouper, groups

    def _reorder_columns(self, res, data):
        """Reorder result columns to match original order with new columns appended."""
        cols = [c for c in data if c in res]
        cols += [c for c in res if c not in data]
        return res.reindex(columns=pd.Index(cols))

    def agg(self, data: DataFrame, *args, **kwargs) -> DataFrame:
        """
        Reduce each group to a single row in the output.

        The output will have a row for each unique combination of the grouping
        variable levels with null values for the aggregated variable(s) where
        those combinations do not appear in the dataset.

        """
        grouper, groups = self._get_groups(data)

        if not grouper:
            # We will need to see whether there are valid usecases that end up here
            raise ValueError("No grouping variables are present in dataframe")

        res = (
            data
            .groupby(grouper, sort=False, observed=False)
            .agg(*args, **kwargs)
            .reindex(groups)
            .reset_index()
            .pipe(self._reorder_columns, data)
        )

        return res

    def apply(
        self, data: DataFrame, func: Callable[..., DataFrame],
        *args, **kwargs,
    ) -> DataFrame:
        """Apply a DataFrame -> DataFrame mapping to each group."""
        grouper, groups = self._get_groups(data)

        if not grouper:
            return self._reorder_columns(func(data, *args, **kwargs), data)

        parts = {}
        for key, part_df in data.groupby(grouper, sort=False, observed=False):
            parts[key] = func(part_df, *args, **kwargs)
        stack = []
        for key in groups:
            if key in parts:
                if isinstance(grouper, list):
                    # Implies that we had a MultiIndex so key is iterable
                    group_ids = dict(zip(grouper, cast(Iterable, key)))
                else:
                    group_ids = {grouper: key}
                stack.append(parts[key].assign(**group_ids))

        res = pd.concat(stack, ignore_index=True)
        return self._reorder_columns(res, data)
