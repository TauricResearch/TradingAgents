from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import matplotlib as mpl

from seaborn._marks.base import (
    Mark,
    Mappable,
    MappableFloat,
    MappableString,
    MappableColor,
    resolve_properties,
    resolve_color,
    document_properties,
)


@document_properties
@dataclass
class Path(Mark):
    """
    A mark connecting data points in the order they appear.

    See also
    --------
    Line : A mark connecting data points with sorting along the orientation axis.
    Paths : A faster but less-flexible mark for drawing many paths.

    Examples
    --------
    .. include:: ../docstrings/objects.Path.rst

    """
    color: MappableColor = Mappable("C0")
    alpha: MappableFloat = Mappable(1)
    linewidth: MappableFloat = Mappable(rc="lines.linewidth")
    linestyle: MappableString = Mappable(rc="lines.linestyle")
    marker: MappableString = Mappable(rc="lines.marker")
    pointsize: MappableFloat = Mappable(rc="lines.markersize")
    fillcolor: MappableColor = Mappable(depend="color")
    edgecolor: MappableColor = Mappable(depend="color")
    edgewidth: MappableFloat = Mappable(rc="lines.markeredgewidth")

    _sort: ClassVar[bool] = False

    def _plot(self, split_gen, scales, orient):

        for keys, data, ax in split_gen(keep_na=not self._sort):

            vals = resolve_properties(self, keys, scales)
            vals["color"] = resolve_color(self, keys, scales=scales)
            vals["fillcolor"] = resolve_color(self, keys, prefix="fill", scales=scales)
            vals["edgecolor"] = resolve_color(self, keys, prefix="edge", scales=scales)

            if self._sort:
                data = data.sort_values(orient, kind="mergesort")

            artist_kws = self.artist_kws.copy()
            self._handle_capstyle(artist_kws, vals)

            line = mpl.lines.Line2D(
                data["x"].to_numpy(),
                data["y"].to_numpy(),
                color=vals["color"],
                linewidth=vals["linewidth"],
                linestyle=vals["linestyle"],
                marker=vals["marker"],
                markersize=vals["pointsize"],
                markerfacecolor=vals["fillcolor"],
                markeredgecolor=vals["edgecolor"],
                markeredgewidth=vals["edgewidth"],
                **artist_kws,
            )
            ax.add_line(line)

    def _legend_artist(self, variables, value, scales):

        keys = {v: value for v in variables}
        vals = resolve_properties(self, keys, scales)
        vals["color"] = resolve_color(self, keys, scales=scales)
        vals["fillcolor"] = resolve_color(self, keys, prefix="fill", scales=scales)
        vals["edgecolor"] = resolve_color(self, keys, prefix="edge", scales=scales)

        artist_kws = self.artist_kws.copy()
        self._handle_capstyle(artist_kws, vals)

        return mpl.lines.Line2D(
            [], [],
            color=vals["color"],
            linewidth=vals["linewidth"],
            linestyle=vals["linestyle"],
            marker=vals["marker"],
            markersize=vals["pointsize"],
            markerfacecolor=vals["fillcolor"],
            markeredgecolor=vals["edgecolor"],
            markeredgewidth=vals["edgewidth"],
            **artist_kws,
        )

    def _handle_capstyle(self, kws, vals):

        # Work around for this matplotlib issue:
        # https://github.com/matplotlib/matplotlib/issues/23437
        if vals["linestyle"][1] is None:
            capstyle = kws.get("solid_capstyle", mpl.rcParams["lines.solid_capstyle"])
            kws["dash_capstyle"] = capstyle


@document_properties
@dataclass
class Line(Path):
    """
    A mark connecting data points with sorting along the orientation axis.

    See also
    --------
    Path : A mark connecting data points in the order they appear.
    Lines : A faster but less-flexible mark for drawing many lines.

    Examples
    --------
    .. include:: ../docstrings/objects.Line.rst

    """
    _sort: ClassVar[bool] = True


@document_properties
@dataclass
class Paths(Mark):
    """
    A faster but less-flexible mark for drawing many paths.

    See also
    --------
    Path : A mark connecting data points in the order they appear.

    Examples
    --------
    .. include:: ../docstrings/objects.Paths.rst

    """
    color: MappableColor = Mappable("C0")
    alpha: MappableFloat = Mappable(1)
    linewidth: MappableFloat = Mappable(rc="lines.linewidth")
    linestyle: MappableString = Mappable(rc="lines.linestyle")

    _sort: ClassVar[bool] = False

    def __post_init__(self):

        # LineCollection artists have a capstyle property but don't source its value
        # from the rc, so we do that manually here. Unfortunately, because we add
        # only one LineCollection, we have the use the same capstyle for all lines
        # even when they are dashed. It's a slight inconsistency, but looks fine IMO.
        self.artist_kws.setdefault("capstyle", mpl.rcParams["lines.solid_capstyle"])

    def _plot(self, split_gen, scales, orient):

        line_data = {}
        for keys, data, ax in split_gen(keep_na=not self._sort):

            if ax not in line_data:
                line_data[ax] = {
                    "segments": [],
                    "colors": [],
                    "linewidths": [],
                    "linestyles": [],
                }

            segments = self._setup_segments(data, orient)
            line_data[ax]["segments"].extend(segments)
            n = len(segments)

            vals = resolve_properties(self, keys, scales)
            vals["color"] = resolve_color(self, keys, scales=scales)

            line_data[ax]["colors"].extend([vals["color"]] * n)
            line_data[ax]["linewidths"].extend([vals["linewidth"]] * n)
            line_data[ax]["linestyles"].extend([vals["linestyle"]] * n)

        for ax, ax_data in line_data.items():
            lines = mpl.collections.LineCollection(**ax_data, **self.artist_kws)
            # Handle datalim update manually
            # https://github.com/matplotlib/matplotlib/issues/23129
            ax.add_collection(lines, autolim=False)
            if ax_data["segments"]:
                xy = np.concatenate(ax_data["segments"])
                ax.update_datalim(xy)

    def _legend_artist(self, variables, value, scales):

        key = resolve_properties(self, {v: value for v in variables}, scales)

        artist_kws = self.artist_kws.copy()
        capstyle = artist_kws.pop("capstyle")
        artist_kws["solid_capstyle"] = capstyle
        artist_kws["dash_capstyle"] = capstyle

        return mpl.lines.Line2D(
            [], [],
            color=key["color"],
            linewidth=key["linewidth"],
            linestyle=key["linestyle"],
            **artist_kws,
        )

    def _setup_segments(self, data, orient):

        if self._sort:
            data = data.sort_values(orient, kind="mergesort")

        # Column stack to avoid block consolidation
        xy = np.column_stack([data["x"], data["y"]])

        return [xy]


@document_properties
@dataclass
class Lines(Paths):
    """
    A faster but less-flexible mark for drawing many lines.

    See also
    --------
    Line : A mark connecting data points with sorting along the orientation axis.

    Examples
    --------
    .. include:: ../docstrings/objects.Lines.rst

    """
    _sort: ClassVar[bool] = True


@document_properties
@dataclass
class Range(Paths):
    """
    An oriented line mark drawn between min/max values.

    Examples
    --------
    .. include:: ../docstrings/objects.Range.rst

    """
    def _setup_segments(self, data, orient):

        # TODO better checks on what variables we have
        # TODO what if only one exist?
        val = {"x": "y", "y": "x"}[orient]
        if not set(data.columns) & {f"{val}min", f"{val}max"}:
            agg = {f"{val}min": (val, "min"), f"{val}max": (val, "max")}
            data = data.groupby(orient).agg(**agg).reset_index()

        cols = [orient, f"{val}min", f"{val}max"]
        data = data[cols].melt(orient, value_name=val)[["x", "y"]]
        segments = [d.to_numpy() for _, d in data.groupby(orient)]
        return segments


@document_properties
@dataclass
class Dash(Paths):
    """
    A line mark drawn as an oriented segment for each datapoint.

    Examples
    --------
    .. include:: ../docstrings/objects.Dash.rst

    """
    width: MappableFloat = Mappable(.8, grouping=False)

    def _setup_segments(self, data, orient):

        ori = ["x", "y"].index(orient)
        xys = data[["x", "y"]].to_numpy().astype(float)
        segments = np.stack([xys, xys], axis=1)
        segments[:, 0, ori] -= data["width"] / 2
        segments[:, 1, ori] += data["width"] / 2
        return segments
