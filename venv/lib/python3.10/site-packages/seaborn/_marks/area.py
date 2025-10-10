from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import matplotlib as mpl

from seaborn._marks.base import (
    Mark,
    Mappable,
    MappableBool,
    MappableFloat,
    MappableColor,
    MappableStyle,
    resolve_properties,
    resolve_color,
    document_properties,
)


class AreaBase:

    def _plot(self, split_gen, scales, orient):

        patches = defaultdict(list)

        for keys, data, ax in split_gen():

            kws = {}
            data = self._standardize_coordinate_parameters(data, orient)
            resolved = resolve_properties(self, keys, scales)
            verts = self._get_verts(data, orient)
            ax.update_datalim(verts)

            # TODO should really move this logic into resolve_color
            fc = resolve_color(self, keys, "", scales)
            if not resolved["fill"]:
                fc = mpl.colors.to_rgba(fc, 0)

            kws["facecolor"] = fc
            kws["edgecolor"] = resolve_color(self, keys, "edge", scales)
            kws["linewidth"] = resolved["edgewidth"]
            kws["linestyle"] = resolved["edgestyle"]

            patches[ax].append(mpl.patches.Polygon(verts, **kws))

        for ax, ax_patches in patches.items():

            for patch in ax_patches:
                self._postprocess_artist(patch, ax, orient)
                ax.add_patch(patch)

    def _standardize_coordinate_parameters(self, data, orient):
        return data

    def _postprocess_artist(self, artist, ax, orient):
        pass

    def _get_verts(self, data, orient):

        dv = {"x": "y", "y": "x"}[orient]
        data = data.sort_values(orient, kind="mergesort")
        verts = np.concatenate([
            data[[orient, f"{dv}min"]].to_numpy(),
            data[[orient, f"{dv}max"]].to_numpy()[::-1],
        ])
        if orient == "y":
            verts = verts[:, ::-1]
        return verts

    def _legend_artist(self, variables, value, scales):

        keys = {v: value for v in variables}
        resolved = resolve_properties(self, keys, scales)

        fc = resolve_color(self, keys, "", scales)
        if not resolved["fill"]:
            fc = mpl.colors.to_rgba(fc, 0)

        return mpl.patches.Patch(
            facecolor=fc,
            edgecolor=resolve_color(self, keys, "edge", scales),
            linewidth=resolved["edgewidth"],
            linestyle=resolved["edgestyle"],
            **self.artist_kws,
        )


@document_properties
@dataclass
class Area(AreaBase, Mark):
    """
    A fill mark drawn from a baseline to data values.

    See also
    --------
    Band : A fill mark representing an interval between values.

    Examples
    --------
    .. include:: ../docstrings/objects.Area.rst

    """
    color: MappableColor = Mappable("C0", )
    alpha: MappableFloat = Mappable(.2, )
    fill: MappableBool = Mappable(True, )
    edgecolor: MappableColor = Mappable(depend="color")
    edgealpha: MappableFloat = Mappable(1, )
    edgewidth: MappableFloat = Mappable(rc="patch.linewidth", )
    edgestyle: MappableStyle = Mappable("-", )

    # TODO should this be settable / mappable?
    baseline: MappableFloat = Mappable(0, grouping=False)

    def _standardize_coordinate_parameters(self, data, orient):
        dv = {"x": "y", "y": "x"}[orient]
        return data.rename(columns={"baseline": f"{dv}min", dv: f"{dv}max"})

    def _postprocess_artist(self, artist, ax, orient):

        # TODO copying a lot of code from Bar, let's abstract this
        # See comments there, I am not going to repeat them too

        artist.set_linewidth(artist.get_linewidth() * 2)

        linestyle = artist.get_linestyle()
        if linestyle[1]:
            linestyle = (linestyle[0], tuple(x / 2 for x in linestyle[1]))
        artist.set_linestyle(linestyle)

        artist.set_clip_path(artist.get_path(), artist.get_transform() + ax.transData)
        if self.artist_kws.get("clip_on", True):
            artist.set_clip_box(ax.bbox)

        val_idx = ["y", "x"].index(orient)
        artist.sticky_edges[val_idx][:] = (0, np.inf)


@document_properties
@dataclass
class Band(AreaBase, Mark):
    """
    A fill mark representing an interval between values.

    See also
    --------
    Area : A fill mark drawn from a baseline to data values.

    Examples
    --------
    .. include:: ../docstrings/objects.Band.rst

    """
    color: MappableColor = Mappable("C0", )
    alpha: MappableFloat = Mappable(.2, )
    fill: MappableBool = Mappable(True, )
    edgecolor: MappableColor = Mappable(depend="color", )
    edgealpha: MappableFloat = Mappable(1, )
    edgewidth: MappableFloat = Mappable(0, )
    edgestyle: MappableFloat = Mappable("-", )

    def _standardize_coordinate_parameters(self, data, orient):
        # dv = {"x": "y", "y": "x"}[orient]
        # TODO assert that all(ymax >= ymin)?
        # TODO what if only one exist?
        other = {"x": "y", "y": "x"}[orient]
        if not set(data.columns) & {f"{other}min", f"{other}max"}:
            agg = {f"{other}min": (other, "min"), f"{other}max": (other, "max")}
            data = data.groupby(orient).agg(**agg).reset_index()
        return data
