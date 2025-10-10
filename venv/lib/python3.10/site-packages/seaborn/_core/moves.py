from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar, Callable, Optional, Union, cast

import numpy as np
from pandas import DataFrame

from seaborn._core.groupby import GroupBy
from seaborn._core.scales import Scale
from seaborn._core.typing import Default

default = Default()


@dataclass
class Move:
    """Base class for objects that apply simple positional transforms."""

    group_by_orient: ClassVar[bool] = True

    def __call__(
        self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale],
    ) -> DataFrame:
        raise NotImplementedError


@dataclass
class Jitter(Move):
    """
    Random displacement along one or both axes to reduce overplotting.

    Parameters
    ----------
    width : float
        Magnitude of jitter, relative to mark width, along the orientation axis.
        If not provided, the default value will be 0 when `x` or `y` are set, otherwise
        there will be a small amount of jitter applied by default.
    x : float
        Magnitude of jitter, in data units, along the x axis.
    y : float
        Magnitude of jitter, in data units, along the y axis.

    Examples
    --------
    .. include:: ../docstrings/objects.Jitter.rst

    """
    width: float | Default = default
    x: float = 0
    y: float = 0
    seed: int | None = None

    def __call__(
        self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale],
    ) -> DataFrame:

        data = data.copy()
        rng = np.random.default_rng(self.seed)

        def jitter(data, col, scale):
            noise = rng.uniform(-.5, +.5, len(data))
            offsets = noise * scale
            return data[col] + offsets

        if self.width is default:
            width = 0.0 if self.x or self.y else 0.2
        else:
            width = cast(float, self.width)

        if self.width:
            data[orient] = jitter(data, orient, width * data["width"])
        if self.x:
            data["x"] = jitter(data, "x", self.x)
        if self.y:
            data["y"] = jitter(data, "y", self.y)

        return data


@dataclass
class Dodge(Move):
    """
    Displacement and narrowing of overlapping marks along orientation axis.

    Parameters
    ----------
    empty : {'keep', 'drop', 'fill'}
    gap : float
        Size of gap between dodged marks.
    by : list of variable names
        Variables to apply the movement to, otherwise use all.

    Examples
    --------
    .. include:: ../docstrings/objects.Dodge.rst

    """
    empty: str = "keep"  # Options: keep, drop, fill
    gap: float = 0

    # TODO accept just a str here?
    # TODO should this always be present?
    # TODO should the default be an "all" singleton?
    by: Optional[list[str]] = None

    def __call__(
        self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale],
    ) -> DataFrame:

        grouping_vars = [v for v in groupby.order if v in data]
        groups = groupby.agg(data, {"width": "max"})
        if self.empty == "fill":
            groups = groups.dropna()

        def groupby_pos(s):
            grouper = [groups[v] for v in [orient, "col", "row"] if v in data]
            return s.groupby(grouper, sort=False, observed=True)

        def scale_widths(w):
            # TODO what value to fill missing widths??? Hard problem...
            # TODO short circuit this if outer widths has no variance?
            empty = 0 if self.empty == "fill" else w.mean()
            filled = w.fillna(empty)
            scale = filled.max()
            norm = filled.sum()
            if self.empty == "keep":
                w = filled
            return w / norm * scale

        def widths_to_offsets(w):
            return w.shift(1).fillna(0).cumsum() + (w - w.sum()) / 2

        new_widths = groupby_pos(groups["width"]).transform(scale_widths)
        offsets = groupby_pos(new_widths).transform(widths_to_offsets)

        if self.gap:
            new_widths *= 1 - self.gap

        groups["_dodged"] = groups[orient] + offsets
        groups["width"] = new_widths

        out = (
            data
            .drop("width", axis=1)
            .merge(groups, on=grouping_vars, how="left")
            .drop(orient, axis=1)
            .rename(columns={"_dodged": orient})
        )

        return out


@dataclass
class Stack(Move):
    """
    Displacement of overlapping bar or area marks along the value axis.

    Examples
    --------
    .. include:: ../docstrings/objects.Stack.rst

    """
    # TODO center? (or should this be a different move, eg. Stream())

    def _stack(self, df, orient):

        # TODO should stack do something with ymin/ymax style marks?
        # Should there be an upstream conversion to baseline/height parameterization?

        if df["baseline"].nunique() > 1:
            err = "Stack move cannot be used when baselines are already heterogeneous"
            raise RuntimeError(err)

        other = {"x": "y", "y": "x"}[orient]
        stacked_lengths = (df[other] - df["baseline"]).dropna().cumsum()
        offsets = stacked_lengths.shift(1).fillna(0)

        df[other] = stacked_lengths
        df["baseline"] = df["baseline"] + offsets

        return df

    def __call__(
        self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale],
    ) -> DataFrame:

        # TODO where to ensure that other semantic variables are sorted properly?
        # TODO why are we not using the passed in groupby here?
        groupers = ["col", "row", orient]
        return GroupBy(groupers).apply(data, self._stack, orient)


@dataclass
class Shift(Move):
    """
    Displacement of all marks with the same magnitude / direction.

    Parameters
    ----------
    x, y : float
        Magnitude of shift, in data units, along each axis.

    Examples
    --------
    .. include:: ../docstrings/objects.Shift.rst

    """
    x: float = 0
    y: float = 0

    def __call__(
        self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale],
    ) -> DataFrame:

        data = data.copy(deep=False)
        data["x"] = data["x"] + self.x
        data["y"] = data["y"] + self.y
        return data


@dataclass
class Norm(Move):
    """
    Divisive scaling on the value axis after aggregating within groups.

    Parameters
    ----------
    func : str or callable
        Function called on each group to define the comparison value.
    where : str
        Query string defining the subset used to define the comparison values.
    by : list of variables
        Variables used to define aggregation groups.
    percent : bool
        If True, multiply the result by 100.

    Examples
    --------
    .. include:: ../docstrings/objects.Norm.rst

    """

    func: Union[Callable, str] = "max"
    where: Optional[str] = None
    by: Optional[list[str]] = None
    percent: bool = False

    group_by_orient: ClassVar[bool] = False

    def _norm(self, df, var):

        if self.where is None:
            denom_data = df[var]
        else:
            denom_data = df.query(self.where)[var]
        df[var] = df[var] / denom_data.agg(self.func)

        if self.percent:
            df[var] = df[var] * 100

        return df

    def __call__(
        self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale],
    ) -> DataFrame:

        other = {"x": "y", "y": "x"}[orient]
        return groupby.apply(data, self._norm, other)


# TODO
# @dataclass
# class Ridge(Move):
#     ...
