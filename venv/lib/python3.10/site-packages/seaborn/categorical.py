from collections import namedtuple
from textwrap import dedent
import warnings
from colorsys import rgb_to_hls
from functools import partial

import numpy as np
import pandas as pd

import matplotlib as mpl
from matplotlib.cbook import normalize_kwargs
from matplotlib.collections import PatchCollection
from matplotlib.markers import MarkerStyle
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt

from seaborn._core.typing import default, deprecated
from seaborn._base import VectorPlotter, infer_orient, categorical_order
from seaborn._stats.density import KDE
from seaborn import utils
from seaborn.utils import (
    desaturate,
    _check_argument,
    _draw_figure,
    _default_color,
    _get_patch_legend_artist,
    _get_transform_functions,
    _scatter_legend_artist,
    _version_predates,
)
from seaborn._compat import groupby_apply_include_groups
from seaborn._statistics import (
    EstimateAggregator,
    LetterValues,
    WeightedAggregator,
)
from seaborn.palettes import light_palette
from seaborn.axisgrid import FacetGrid, _facet_docs


__all__ = [
    "catplot",
    "stripplot", "swarmplot",
    "boxplot", "violinplot", "boxenplot",
    "pointplot", "barplot", "countplot",
]


class _CategoricalPlotter(VectorPlotter):

    wide_structure = {"x": "@columns", "y": "@values", "hue": "@columns"}
    flat_structure = {"y": "@values"}

    _legend_attributes = ["color"]

    def __init__(
        self,
        data=None,
        variables={},
        order=None,
        orient=None,
        require_numeric=False,
        color=None,
        legend="auto",
    ):

        super().__init__(data=data, variables=variables)

        # This method takes care of some bookkeeping that is necessary because the
        # original categorical plots (prior to the 2021 refactor) had some rules that
        # don't fit exactly into VectorPlotter logic. It may be wise to have a second
        # round of refactoring that moves the logic deeper, but this will keep things
        # relatively sensible for now.

        # For wide data, orient determines assignment to x/y differently from the
        # default VectorPlotter rules. If we do decide to make orient part of the
        # _base variable assignment, we'll want to figure out how to express that.
        if self.input_format == "wide" and orient in ["h", "y"]:
            self.plot_data = self.plot_data.rename(columns={"x": "y", "y": "x"})
            orig_variables = set(self.variables)
            orig_x = self.variables.pop("x", None)
            orig_y = self.variables.pop("y", None)
            orig_x_type = self.var_types.pop("x", None)
            orig_y_type = self.var_types.pop("y", None)
            if "x" in orig_variables:
                self.variables["y"] = orig_x
                self.var_types["y"] = orig_x_type
            if "y" in orig_variables:
                self.variables["x"] = orig_y
                self.var_types["x"] = orig_y_type

        # Initially there was more special code for wide-form data where plots were
        # multi-colored by default and then either palette or color could be used.
        # We want to provide backwards compatibility for this behavior in a relatively
        # simply way, so we delete the hue information when color is specified.
        if (
            self.input_format == "wide"
            and "hue" in self.variables
            and color is not None
        ):
            self.plot_data.drop("hue", axis=1)
            self.variables.pop("hue")

        # The concept of an "orientation" is important to the original categorical
        # plots, but there's no provision for it in VectorPlotter, so we need it here.
        # Note that it could be useful for the other functions in at least two ways
        # (orienting a univariate distribution plot from long-form data and selecting
        # the aggregation axis in lineplot), so we may want to eventually refactor it.
        self.orient = infer_orient(
            x=self.plot_data.get("x", None),
            y=self.plot_data.get("y", None),
            orient=orient,
            require_numeric=False,
        )

        self.legend = legend

        # Short-circuit in the case of an empty plot
        if not self.has_xy_data:
            return

        # Categorical plots can be "univariate" in which case they get an anonymous
        # category label on the opposite axis. Note: this duplicates code in the core
        # scale_categorical function. We need to do it here because of the next line.
        if self.orient not in self.variables:
            self.variables[self.orient] = None
            self.var_types[self.orient] = "categorical"
            self.plot_data[self.orient] = ""

        # Categorical variables have discrete levels that we need to track
        cat_levels = categorical_order(self.plot_data[self.orient], order)
        self.var_levels[self.orient] = cat_levels

    def _hue_backcompat(self, color, palette, hue_order, force_hue=False):
        """Implement backwards compatibility for hue parametrization.

        Note: the force_hue parameter is used so that functions can be shown to
        pass existing tests during refactoring and then tested for new behavior.
        It can be removed after completion of the work.

        """
        # The original categorical functions applied a palette to the categorical axis
        # by default. We want to require an explicit hue mapping, to be more consistent
        # with how things work elsewhere now. I don't think there's any good way to
        # do this gently -- because it's triggered by the default value of hue=None,
        # users would always get a warning, unless we introduce some sentinel "default"
        # argument for this change. That's possible, but asking users to set `hue=None`
        # on every call is annoying.
        # We are keeping the logic for implementing the old behavior in with the current
        # system so that (a) we can punt on that decision and (b) we can ensure that
        # refactored code passes old tests.
        default_behavior = color is None or palette is not None
        if force_hue and "hue" not in self.variables and default_behavior:
            self._redundant_hue = True
            self.plot_data["hue"] = self.plot_data[self.orient]
            self.variables["hue"] = self.variables[self.orient]
            self.var_types["hue"] = "categorical"
            hue_order = self.var_levels[self.orient]

            # Because we convert the categorical axis variable to string,
            # we need to update a dictionary palette too
            if isinstance(palette, dict):
                palette = {str(k): v for k, v in palette.items()}

        else:
            if "hue" in self.variables:
                redundant = (self.plot_data["hue"] == self.plot_data[self.orient]).all()
            else:
                redundant = False
            self._redundant_hue = redundant

        # Previously, categorical plots had a trick where color= could seed the palette.
        # Because that's an explicit parameterization, we are going to give it one
        # release cycle with a warning before removing.
        if "hue" in self.variables and palette is None and color is not None:
            if not isinstance(color, str):
                color = mpl.colors.to_hex(color)
            palette = f"dark:{color}"
            msg = (
                "\n\nSetting a gradient palette using color= is deprecated and will be "
                f"removed in v0.14.0. Set `palette='{palette}'` for the same effect.\n"
            )
            warnings.warn(msg, FutureWarning, stacklevel=3)

        return palette, hue_order

    def _palette_without_hue_backcompat(self, palette, hue_order):
        """Provide one cycle where palette= implies hue= when not provided"""
        if "hue" not in self.variables and palette is not None:
            msg = (
                "\n\nPassing `palette` without assigning `hue` is deprecated "
                f"and will be removed in v0.14.0. Assign the `{self.orient}` variable "
                "to `hue` and set `legend=False` for the same effect.\n"
            )
            warnings.warn(msg, FutureWarning, stacklevel=3)

            self.legend = False
            self.plot_data["hue"] = self.plot_data[self.orient]
            self.variables["hue"] = self.variables.get(self.orient)
            self.var_types["hue"] = self.var_types.get(self.orient)

            hue_order = self.var_levels.get(self.orient)
            self._var_levels.pop("hue", None)

        return hue_order

    def _point_kwargs_backcompat(self, scale, join, kwargs):
        """Provide two cycles where scale= and join= work, but redirect to kwargs."""
        if scale is not deprecated:
            lw = mpl.rcParams["lines.linewidth"] * 1.8 * scale
            mew = lw * .75
            ms = lw * 2

            msg = (
                "\n\n"
                "The `scale` parameter is deprecated and will be removed in v0.15.0. "
                "You can now control the size of each plot element using matplotlib "
                "`Line2D` parameters (e.g., `linewidth`, `markersize`, etc.)."
                "\n"
            )
            warnings.warn(msg, stacklevel=3)
            kwargs.update(linewidth=lw, markeredgewidth=mew, markersize=ms)

        if join is not deprecated:
            msg = (
                "\n\n"
                "The `join` parameter is deprecated and will be removed in v0.15.0."
            )
            if not join:
                msg += (
                    " You can remove the line between points with `linestyle='none'`."
                )
                kwargs.update(linestyle="")
            msg += "\n"
            warnings.warn(msg, stacklevel=3)

    def _err_kws_backcompat(self, err_kws, errcolor, errwidth, capsize):
        """Provide two cycles where existing signature-level err_kws are handled."""
        def deprecate_err_param(name, key, val):
            if val is deprecated:
                return
            suggest = f"err_kws={{'{key}': {val!r}}}"
            msg = (
                f"\n\nThe `{name}` parameter is deprecated. And will be removed "
                f"in v0.15.0. Pass `{suggest}` instead.\n"
            )
            warnings.warn(msg, FutureWarning, stacklevel=4)
            err_kws[key] = val

        if errcolor is not None:
            deprecate_err_param("errcolor", "color", errcolor)
        deprecate_err_param("errwidth", "linewidth", errwidth)

        if capsize is None:
            capsize = 0
            msg = (
                "\n\nPassing `capsize=None` is deprecated and will be removed "
                "in v0.15.0. Pass `capsize=0` to disable caps.\n"
            )
            warnings.warn(msg, FutureWarning, stacklevel=3)

        return err_kws, capsize

    def _violin_scale_backcompat(self, scale, scale_hue, density_norm, common_norm):
        """Provide two cycles of backcompat for scale kwargs"""
        if scale is not deprecated:
            density_norm = scale
            msg = (
                "\n\nThe `scale` parameter has been renamed and will be removed "
                f"in v0.15.0. Pass `density_norm={scale!r}` for the same effect."
            )
            warnings.warn(msg, FutureWarning, stacklevel=3)

        if scale_hue is not deprecated:
            common_norm = scale_hue
            msg = (
                "\n\nThe `scale_hue` parameter has been replaced and will be removed "
                f"in v0.15.0. Pass `common_norm={not scale_hue}` for the same effect."
            )
            warnings.warn(msg, FutureWarning, stacklevel=3)

        return density_norm, common_norm

    def _violin_bw_backcompat(self, bw, bw_method):
        """Provide two cycles of backcompat for violin bandwidth parameterization."""
        if bw is not deprecated:
            bw_method = bw
            msg = dedent(f"""\n
                The `bw` parameter is deprecated in favor of `bw_method`/`bw_adjust`.
                Setting `bw_method={bw!r}`, but please see docs for the new parameters
                and update your code. This will become an error in seaborn v0.15.0.
            """)
            warnings.warn(msg, FutureWarning, stacklevel=3)
        return bw_method

    def _boxen_scale_backcompat(self, scale, width_method):
        """Provide two cycles of backcompat for scale kwargs"""
        if scale is not deprecated:
            width_method = scale
            msg = (
                "\n\nThe `scale` parameter has been renamed to `width_method` and "
                f"will be removed in v0.15. Pass `width_method={scale!r}"
            )
            if scale == "area":
                msg += ", but note that the result for 'area' will appear different."
            else:
                msg += " for the same effect."
            warnings.warn(msg, FutureWarning, stacklevel=3)

        return width_method

    def _complement_color(self, color, base_color, hue_map):
        """Allow a color to be set automatically using a basis of comparison."""
        if color == "gray":
            msg = (
                'Use "auto" to set automatic grayscale colors. From v0.14.0, '
                '"gray" will default to matplotlib\'s definition.'
            )
            warnings.warn(msg, FutureWarning, stacklevel=3)
            color = "auto"
        elif color is None or color is default:
            color = "auto"

        if color != "auto":
            return color

        if hue_map.lookup_table is None:
            if base_color is None:
                return None
            basis = [mpl.colors.to_rgb(base_color)]
        else:
            basis = [mpl.colors.to_rgb(c) for c in hue_map.lookup_table.values()]
        unique_colors = np.unique(basis, axis=0)
        light_vals = [rgb_to_hls(*rgb[:3])[1] for rgb in unique_colors]
        lum = min(light_vals) * .6
        return (lum, lum, lum)

    def _map_prop_with_hue(self, name, value, fallback, plot_kws):
        """Support pointplot behavior of modifying the marker/linestyle with hue."""
        if value is default:
            value = plot_kws.pop(name, fallback)

        if "hue" in self.variables:
            levels = self._hue_map.levels
            if isinstance(value, list):
                mapping = {k: v for k, v in zip(levels, value)}
            else:
                mapping = {k: value for k in levels}
        else:
            mapping = {None: value}

        return mapping

    def _adjust_cat_axis(self, ax, axis):
        """Set ticks and limits for a categorical variable."""
        # Note: in theory, this could happen in _attach for all categorical axes
        # But two reasons not to do that:
        # - If it happens before plotting, autoscaling messes up the plot limits
        # - It would change existing plots from other seaborn functions
        if self.var_types[axis] != "categorical":
            return

        # If both x/y data are empty, the correct way to set up the plot is
        # somewhat undefined; because we don't add null category data to the plot in
        # this case we don't *have* a categorical axis (yet), so best to just bail.
        if self.plot_data[axis].empty:
            return

        # We can infer the total number of categories (including those from previous
        # plots that are not part of the plot we are currently making) from the number
        # of ticks, which matplotlib sets up while doing unit conversion. This feels
        # slightly risky, as if we are relying on something that may be a matplotlib
        # implementation detail. But I cannot think of a better way to keep track of
        # the state from previous categorical calls (see GH2516 for context)
        n = len(getattr(ax, f"get_{axis}ticks")())

        if axis == "x":
            ax.xaxis.grid(False)
            ax.set_xlim(-.5, n - .5, auto=None)
        else:
            ax.yaxis.grid(False)
            # Note limits that correspond to previously-inverted y axis
            ax.set_ylim(n - .5, -.5, auto=None)

    def _dodge_needed(self):
        """Return True when use of `hue` would cause overlaps."""
        groupers = list({self.orient, "col", "row"} & set(self.variables))
        if "hue" in self.variables:
            orient = self.plot_data[groupers].value_counts()
            paired = self.plot_data[[*groupers, "hue"]].value_counts()
            return orient.size != paired.size
        return False

    def _dodge(self, keys, data):
        """Apply a dodge transform to coordinates in place."""
        if "hue" not in self.variables:
            # Short-circuit if hue variable was not assigned
            # We could potentially warn when hue=None, dodge=True, user may be confused
            # But I think it's fine to just treat it as a no-op.
            return
        hue_idx = self._hue_map.levels.index(keys["hue"])
        n = len(self._hue_map.levels)
        data["width"] /= n

        full_width = data["width"] * n
        offset = data["width"] * hue_idx + data["width"] / 2 - full_width / 2
        data[self.orient] += offset

    def _invert_scale(self, ax, data, vars=("x", "y")):
        """Undo scaling after computation so data are plotted correctly."""
        for var in vars:
            _, inv = _get_transform_functions(ax, var[0])
            if var == self.orient and "width" in data:
                hw = data["width"] / 2
                data["edge"] = inv(data[var] - hw)
                data["width"] = inv(data[var] + hw) - data["edge"].to_numpy()
            for suf in ["", "min", "max"]:
                if (col := f"{var}{suf}") in data:
                    data[col] = inv(data[col])

    def _configure_legend(self, ax, func, common_kws=None, semantic_kws=None):
        if self.legend == "auto":
            show_legend = not self._redundant_hue and self.input_format != "wide"
        else:
            show_legend = bool(self.legend)
        if show_legend:
            self.add_legend_data(ax, func, common_kws, semantic_kws=semantic_kws)
            handles, _ = ax.get_legend_handles_labels()
            if handles:
                ax.legend(title=self.legend_title)

    @property
    def _native_width(self):
        """Return unit of width separating categories on native numeric scale."""
        # Categorical data always have a unit width
        if self.var_types[self.orient] == "categorical":
            return 1

        # Otherwise, define the width as the smallest space between observations
        unique_values = np.unique(self.comp_data[self.orient])
        if len(unique_values) > 1:
            native_width = np.nanmin(np.diff(unique_values))
        else:
            native_width = 1
        return native_width

    def _nested_offsets(self, width, dodge):
        """Return offsets for each hue level for dodged plots."""
        offsets = None
        if "hue" in self.variables and self._hue_map.levels is not None:
            n_levels = len(self._hue_map.levels)
            if dodge:
                each_width = width / n_levels
                offsets = np.linspace(0, width - each_width, n_levels)
                offsets -= offsets.mean()
            else:
                offsets = np.zeros(n_levels)
        return offsets

    # Note that the plotting methods here aim (in most cases) to produce the
    # exact same artists as the original (pre 0.12) version of the code, so
    # there is some weirdness that might not otherwise be clean or make sense in
    # this context, such as adding empty artists for combinations of variables
    # with no observations

    def plot_strips(
        self,
        jitter,
        dodge,
        color,
        plot_kws,
    ):

        width = .8 * self._native_width
        offsets = self._nested_offsets(width, dodge)

        if jitter is True:
            jlim = 0.1
        else:
            jlim = float(jitter)
        if "hue" in self.variables and dodge and self._hue_map.levels is not None:
            jlim /= len(self._hue_map.levels)
        jlim *= self._native_width
        jitterer = partial(np.random.uniform, low=-jlim, high=+jlim)

        iter_vars = [self.orient]
        if dodge:
            iter_vars.append("hue")

        ax = self.ax
        dodge_move = jitter_move = 0

        if "marker" in plot_kws and not MarkerStyle(plot_kws["marker"]).is_filled():
            plot_kws.pop("edgecolor", None)

        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=True):

            ax = self._get_axes(sub_vars)

            if offsets is not None and (offsets != 0).any():
                dodge_move = offsets[sub_data["hue"].map(self._hue_map.levels.index)]

            jitter_move = jitterer(size=len(sub_data)) if len(sub_data) > 1 else 0

            adjusted_data = sub_data[self.orient] + dodge_move + jitter_move
            sub_data[self.orient] = adjusted_data
            self._invert_scale(ax, sub_data)

            points = ax.scatter(sub_data["x"], sub_data["y"], color=color, **plot_kws)
            if "hue" in self.variables:
                points.set_facecolors(self._hue_map(sub_data["hue"]))

        self._configure_legend(ax, _scatter_legend_artist, common_kws=plot_kws)

    def plot_swarms(
        self,
        dodge,
        color,
        warn_thresh,
        plot_kws,
    ):

        width = .8 * self._native_width
        offsets = self._nested_offsets(width, dodge)

        iter_vars = [self.orient]
        if dodge:
            iter_vars.append("hue")

        ax = self.ax
        point_collections = {}
        dodge_move = 0

        if "marker" in plot_kws and not MarkerStyle(plot_kws["marker"]).is_filled():
            plot_kws.pop("edgecolor", None)

        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=True):

            ax = self._get_axes(sub_vars)

            if offsets is not None:
                dodge_move = offsets[sub_data["hue"].map(self._hue_map.levels.index)]

            if not sub_data.empty:
                sub_data[self.orient] = sub_data[self.orient] + dodge_move

            self._invert_scale(ax, sub_data)

            points = ax.scatter(sub_data["x"], sub_data["y"], color=color, **plot_kws)
            if "hue" in self.variables:
                points.set_facecolors(self._hue_map(sub_data["hue"]))

            if not sub_data.empty:
                point_collections[(ax, sub_data[self.orient].iloc[0])] = points

        beeswarm = Beeswarm(width=width, orient=self.orient, warn_thresh=warn_thresh)
        for (ax, center), points in point_collections.items():
            if points.get_offsets().shape[0] > 1:

                def draw(points, renderer, *, center=center):

                    beeswarm(points, center)

                    if self.orient == "y":
                        scalex = False
                        scaley = ax.get_autoscaley_on()
                    else:
                        scalex = ax.get_autoscalex_on()
                        scaley = False

                    # This prevents us from undoing the nice categorical axis limits
                    # set in _adjust_cat_axis, because that method currently leave
                    # the autoscale flag in its original setting. It may be better
                    # to disable autoscaling there to avoid needing to do this.
                    fixed_scale = self.var_types[self.orient] == "categorical"
                    ax.update_datalim(points.get_datalim(ax.transData))
                    if not fixed_scale and (scalex or scaley):
                        ax.autoscale_view(scalex=scalex, scaley=scaley)

                    super(points.__class__, points).draw(renderer)

                points.draw = draw.__get__(points)

        _draw_figure(ax.figure)
        self._configure_legend(ax, _scatter_legend_artist, plot_kws)

    def plot_boxes(
        self,
        width,
        dodge,
        gap,
        fill,
        whis,
        color,
        linecolor,
        linewidth,
        fliersize,
        plot_kws,  # TODO rename user_kws?
    ):

        iter_vars = ["hue"]
        value_var = {"x": "y", "y": "x"}[self.orient]

        def get_props(element, artist=mpl.lines.Line2D):
            return normalize_kwargs(plot_kws.pop(f"{element}props", {}), artist)

        if not fill and linewidth is None:
            linewidth = mpl.rcParams["lines.linewidth"]
        bootstrap = plot_kws.pop("bootstrap", mpl.rcParams["boxplot.bootstrap"])
        plot_kws.setdefault("shownotches", plot_kws.pop("notch", False))

        box_artist = mpl.patches.Rectangle if fill else mpl.lines.Line2D
        props = {
            "box": get_props("box", box_artist),
            "median": get_props("median"),
            "whisker": get_props("whisker"),
            "flier": get_props("flier"),
            "cap": get_props("cap"),
        }

        props["median"].setdefault("solid_capstyle", "butt")
        props["whisker"].setdefault("solid_capstyle", "butt")
        props["flier"].setdefault("markersize", fliersize)

        ax = self.ax

        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=False):

            ax = self._get_axes(sub_vars)

            grouped = sub_data.groupby(self.orient)[value_var]
            positions = sorted(sub_data[self.orient].unique().astype(float))
            value_data = [x.to_numpy() for _, x in grouped]
            stats = pd.DataFrame(mpl.cbook.boxplot_stats(value_data, whis=whis,
                                                         bootstrap=bootstrap))

            orig_width = width * self._native_width
            data = pd.DataFrame({self.orient: positions, "width": orig_width})
            if dodge:
                self._dodge(sub_vars, data)
            if gap:
                data["width"] *= 1 - gap
            capwidth = plot_kws.get("capwidths", 0.5 * data["width"])

            self._invert_scale(ax, data)
            _, inv = _get_transform_functions(ax, value_var)
            for stat in ["mean", "med", "q1", "q3", "cilo", "cihi", "whislo", "whishi"]:
                stats[stat] = inv(stats[stat])
            stats["fliers"] = stats["fliers"].map(inv)

            linear_orient_scale = getattr(ax, f"get_{self.orient}scale")() == "linear"

            maincolor = self._hue_map(sub_vars["hue"]) if "hue" in sub_vars else color
            if fill:
                boxprops = {
                    "facecolor": maincolor, "edgecolor": linecolor, **props["box"]
                }
                medianprops = {"color": linecolor, **props["median"]}
                whiskerprops = {"color": linecolor, **props["whisker"]}
                flierprops = {"markeredgecolor": linecolor, **props["flier"]}
                capprops = {"color": linecolor, **props["cap"]}
            else:
                boxprops = {"color": maincolor, **props["box"]}
                medianprops = {"color": maincolor, **props["median"]}
                whiskerprops = {"color": maincolor, **props["whisker"]}
                flierprops = {"markeredgecolor": maincolor, **props["flier"]}
                capprops = {"color": maincolor, **props["cap"]}

            if linewidth is not None:
                for prop_dict in [boxprops, medianprops, whiskerprops, capprops]:
                    prop_dict.setdefault("linewidth", linewidth)

            default_kws = dict(
                bxpstats=stats.to_dict("records"),
                positions=data[self.orient],
                # Set width to 0 to avoid going out of domain
                widths=data["width"] if linear_orient_scale else 0,
                patch_artist=fill,
                vert=self.orient == "x",
                manage_ticks=False,
                boxprops=boxprops,
                medianprops=medianprops,
                whiskerprops=whiskerprops,
                flierprops=flierprops,
                capprops=capprops,
                # Added in matplotlib 3.6.0; see below
                # capwidths=capwidth,
                **(
                    {} if _version_predates(mpl, "3.6.0")
                    else {"capwidths": capwidth}
                )
            )
            boxplot_kws = {**default_kws, **plot_kws}
            artists = ax.bxp(**boxplot_kws)

            # Reset artist widths after adding so everything stays positive
            ori_idx = ["x", "y"].index(self.orient)

            if not linear_orient_scale:
                for i, box in enumerate(data.to_dict("records")):
                    p0 = box["edge"]
                    p1 = box["edge"] + box["width"]

                    if artists["boxes"]:
                        box_artist = artists["boxes"][i]
                        if fill:
                            box_verts = box_artist.get_path().vertices.T
                        else:
                            box_verts = box_artist.get_data()
                        box_verts[ori_idx][0] = p0
                        box_verts[ori_idx][3:] = p0
                        box_verts[ori_idx][1:3] = p1
                        if not fill:
                            # When fill is True, the data get changed in place
                            box_artist.set_data(box_verts)
                        ax.update_datalim(
                            np.transpose(box_verts),
                            updatex=self.orient == "x",
                            updatey=self.orient == "y",
                        )

                    if artists["medians"]:
                        verts = artists["medians"][i].get_xydata().T
                        verts[ori_idx][:] = p0, p1
                        artists["medians"][i].set_data(verts)

                    if artists["caps"]:
                        f_fwd, f_inv = _get_transform_functions(ax, self.orient)
                        for line in artists["caps"][2 * i:2 * i + 2]:
                            p0 = f_inv(f_fwd(box[self.orient]) - capwidth[i] / 2)
                            p1 = f_inv(f_fwd(box[self.orient]) + capwidth[i] / 2)
                            verts = line.get_xydata().T
                            verts[ori_idx][:] = p0, p1
                            line.set_data(verts)

            ax.add_container(BoxPlotContainer(artists))

        legend_artist = _get_patch_legend_artist(fill)
        self._configure_legend(ax, legend_artist, boxprops)

    def plot_boxens(
        self,
        width,
        dodge,
        gap,
        fill,
        color,
        linecolor,
        linewidth,
        width_method,
        k_depth,
        outlier_prop,
        trust_alpha,
        showfliers,
        box_kws,
        flier_kws,
        line_kws,
        plot_kws,
    ):

        iter_vars = [self.orient, "hue"]
        value_var = {"x": "y", "y": "x"}[self.orient]

        estimator = LetterValues(k_depth, outlier_prop, trust_alpha)

        width_method_options = ["exponential", "linear", "area"]
        _check_argument("width_method", width_method_options, width_method)

        box_kws = plot_kws if box_kws is None else {**plot_kws, **box_kws}
        flier_kws = {} if flier_kws is None else flier_kws.copy()
        line_kws = {} if line_kws is None else line_kws.copy()

        if linewidth is None:
            if fill:
                linewidth = 0.5 * mpl.rcParams["lines.linewidth"]
            else:
                linewidth = mpl.rcParams["lines.linewidth"]

        ax = self.ax

        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=False):

            ax = self._get_axes(sub_vars)
            _, inv_ori = _get_transform_functions(ax, self.orient)
            _, inv_val = _get_transform_functions(ax, value_var)

            # Statistics
            lv_data = estimator(sub_data[value_var])
            n = lv_data["k"] * 2 - 1
            vals = lv_data["values"]

            pos_data = pd.DataFrame({
                self.orient: [sub_vars[self.orient]],
                "width": [width * self._native_width],
            })
            if dodge:
                self._dodge(sub_vars, pos_data)
            if gap:
                pos_data["width"] *= 1 - gap

            # Letter-value boxes
            levels = lv_data["levels"]
            exponent = (levels - 1 - lv_data["k"]).astype(float)
            if width_method == "linear":
                rel_widths = levels + 1
            elif width_method == "exponential":
                rel_widths = 2 ** exponent
            elif width_method == "area":
                tails = levels < (lv_data["k"] - 1)
                rel_widths = 2 ** (exponent - tails) / np.diff(lv_data["values"])

            center = pos_data[self.orient].item()
            widths = rel_widths / rel_widths.max() * pos_data["width"].item()

            box_vals = inv_val(vals)
            box_pos = inv_ori(center - widths / 2)
            box_heights = inv_val(vals[1:]) - inv_val(vals[:-1])
            box_widths = inv_ori(center + widths / 2) - inv_ori(center - widths / 2)

            maincolor = self._hue_map(sub_vars["hue"]) if "hue" in sub_vars else color
            flier_colors = {
                "facecolor": "none", "edgecolor": ".45" if fill else maincolor
            }
            if fill:
                cmap = light_palette(maincolor, as_cmap=True)
                boxcolors = cmap(2 ** ((exponent + 2) / 3))
            else:
                boxcolors = maincolor

            boxen = []
            for i in range(n):
                if self.orient == "x":
                    xy = (box_pos[i], box_vals[i])
                    w, h = (box_widths[i], box_heights[i])
                else:
                    xy = (box_vals[i], box_pos[i])
                    w, h = (box_heights[i], box_widths[i])
                boxen.append(Rectangle(xy, w, h))

            if fill:
                box_colors = {"facecolors": boxcolors, "edgecolors": linecolor}
            else:
                box_colors = {"facecolors": "none", "edgecolors": boxcolors}

            collection_kws = {**box_colors, "linewidth": linewidth, **box_kws}
            ax.add_collection(PatchCollection(boxen, **collection_kws), autolim=False)
            ax.update_datalim(
                np.column_stack([box_vals, box_vals]),
                updatex=self.orient == "y",
                updatey=self.orient == "x",
            )

            # Median line
            med = lv_data["median"]
            hw = pos_data["width"].item() / 2
            if self.orient == "x":
                x, y = inv_ori([center - hw, center + hw]), inv_val([med, med])
            else:
                x, y = inv_val([med, med]), inv_ori([center - hw, center + hw])
            default_kws = {
                "color": linecolor if fill else maincolor,
                "solid_capstyle": "butt",
                "linewidth": 1.25 * linewidth,
            }
            ax.plot(x, y, **{**default_kws, **line_kws})

            # Outliers ("fliers")
            if showfliers:
                vals = inv_val(lv_data["fliers"])
                pos = np.full(len(vals), inv_ori(pos_data[self.orient].item()))
                x, y = (pos, vals) if self.orient == "x" else (vals, pos)
                ax.scatter(x, y, **{**flier_colors, "s": 25, **flier_kws})

        ax.autoscale_view(scalex=self.orient == "y", scaley=self.orient == "x")

        legend_artist = _get_patch_legend_artist(fill)
        common_kws = {**box_kws, "linewidth": linewidth, "edgecolor": linecolor}
        self._configure_legend(ax, legend_artist, common_kws)

    def plot_violins(
        self,
        width,
        dodge,
        gap,
        split,
        color,
        fill,
        linecolor,
        linewidth,
        inner,
        density_norm,
        common_norm,
        kde_kws,
        inner_kws,
        plot_kws,
    ):

        iter_vars = [self.orient, "hue"]
        value_var = {"x": "y", "y": "x"}[self.orient]

        inner_options = ["box", "quart", "stick", "point", None]
        _check_argument("inner", inner_options, inner, prefix=True)
        _check_argument("density_norm", ["area", "count", "width"], density_norm)

        if linewidth is None:
            if fill:
                linewidth = 1.25 * mpl.rcParams["patch.linewidth"]
            else:
                linewidth = mpl.rcParams["lines.linewidth"]

        if inner is not None and inner.startswith("box"):
            box_width = inner_kws.pop("box_width", linewidth * 4.5)
            whis_width = inner_kws.pop("whis_width", box_width / 3)
            marker = inner_kws.pop("marker", "_" if self.orient == "x" else "|")

        kde = KDE(**kde_kws)
        ax = self.ax
        violin_data = []

        # Iterate through all the data splits once to compute the KDEs
        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=False):

            sub_data["weight"] = sub_data.get("weights", 1)
            stat_data = kde._transform(sub_data, value_var, [])

            maincolor = self._hue_map(sub_vars["hue"]) if "hue" in sub_vars else color
            if not fill:
                linecolor = maincolor
                maincolor = "none"
            default_kws = dict(
                facecolor=maincolor,
                edgecolor=linecolor,
                linewidth=linewidth,
            )

            violin_data.append({
                "position": sub_vars[self.orient],
                "observations": sub_data[value_var],
                "density": stat_data["density"],
                "support": stat_data[value_var],
                "kwargs": {**default_kws, **plot_kws},
                "sub_vars": sub_vars,
                "ax": self._get_axes(sub_vars),
            })

        # Once we've computed all the KDEs, get statistics for normalization
        def vars_to_key(sub_vars):
            return tuple((k, v) for k, v in sub_vars.items() if k != self.orient)

        norm_keys = [vars_to_key(violin["sub_vars"]) for violin in violin_data]
        if common_norm:
            common_max_density = np.nanmax([v["density"].max() for v in violin_data])
            common_max_count = np.nanmax([len(v["observations"]) for v in violin_data])
            max_density = {key: common_max_density for key in norm_keys}
            max_count = {key: common_max_count for key in norm_keys}
        else:
            with warnings.catch_warnings():
                # Ignore warning when all violins are singular; it's not important
                warnings.filterwarnings('ignore', "All-NaN (slice|axis) encountered")
                max_density = {
                    key: np.nanmax([
                        v["density"].max() for v in violin_data
                        if vars_to_key(v["sub_vars"]) == key
                    ]) for key in norm_keys
                }
            max_count = {
                key: np.nanmax([
                    len(v["observations"]) for v in violin_data
                    if vars_to_key(v["sub_vars"]) == key
                ]) for key in norm_keys
            }

        real_width = width * self._native_width

        # Now iterate through the violins again to apply the normalization and plot
        for violin in violin_data:

            index = pd.RangeIndex(0, max(len(violin["support"]), 1))
            data = pd.DataFrame({
                self.orient: violin["position"],
                value_var: violin["support"],
                "density": violin["density"],
                "width": real_width,
            }, index=index)

            if dodge:
                self._dodge(violin["sub_vars"], data)
            if gap:
                data["width"] *= 1 - gap

            # Normalize the density across the distribution(s) and relative to the width
            norm_key = vars_to_key(violin["sub_vars"])
            hw = data["width"] / 2
            peak_density = violin["density"].max()
            if np.isnan(peak_density):
                span = 1
            elif density_norm == "area":
                span = data["density"] / max_density[norm_key]
            elif density_norm == "count":
                count = len(violin["observations"])
                span = data["density"] / peak_density * (count / max_count[norm_key])
            elif density_norm == "width":
                span = data["density"] / peak_density
            span = span * hw * (2 if split else 1)

            # Handle split violins (i.e. asymmetric spans)
            right_side = (
                0 if "hue" not in self.variables
                else self._hue_map.levels.index(violin["sub_vars"]["hue"]) % 2
            )
            if split:
                offsets = (hw, span - hw) if right_side else (span - hw, hw)
            else:
                offsets = span, span

            ax = violin["ax"]
            _, invx = _get_transform_functions(ax, "x")
            _, invy = _get_transform_functions(ax, "y")
            inv_pos = {"x": invx, "y": invy}[self.orient]
            inv_val = {"x": invx, "y": invy}[value_var]

            linecolor = violin["kwargs"]["edgecolor"]

            # Handle singular datasets (one or more observations with no variance
            if np.isnan(peak_density):
                pos = data[self.orient].iloc[0]
                val = violin["observations"].mean()
                if self.orient == "x":
                    x, y = [pos - offsets[0], pos + offsets[1]], [val, val]
                else:
                    x, y = [val, val], [pos - offsets[0], pos + offsets[1]]
                ax.plot(invx(x), invy(y), color=linecolor, linewidth=linewidth)
                continue

            # Plot the main violin body
            plot_func = {"x": ax.fill_betweenx, "y": ax.fill_between}[self.orient]
            plot_func(
                inv_val(data[value_var]),
                inv_pos(data[self.orient] - offsets[0]),
                inv_pos(data[self.orient] + offsets[1]),
                **violin["kwargs"]
            )

            # Adjust the observation data
            obs = violin["observations"]
            pos_dict = {self.orient: violin["position"], "width": real_width}
            if dodge:
                self._dodge(violin["sub_vars"], pos_dict)
            if gap:
                pos_dict["width"] *= (1 - gap)

            # --- Plot the inner components
            if inner is None:
                continue

            elif inner.startswith("point"):
                pos = np.array([pos_dict[self.orient]] * len(obs))
                if split:
                    pos += (-1 if right_side else 1) * pos_dict["width"] / 2
                x, y = (pos, obs) if self.orient == "x" else (obs, pos)
                kws = {
                    "color": linecolor,
                    "edgecolor": linecolor,
                    "s": (linewidth * 2) ** 2,
                    "zorder": violin["kwargs"].get("zorder", 2) + 1,
                    **inner_kws,
                }
                ax.scatter(invx(x), invy(y), **kws)

            elif inner.startswith("stick"):
                pos0 = np.interp(obs, data[value_var], data[self.orient] - offsets[0])
                pos1 = np.interp(obs, data[value_var], data[self.orient] + offsets[1])
                pos_pts = np.stack([inv_pos(pos0), inv_pos(pos1)])
                val_pts = np.stack([inv_val(obs), inv_val(obs)])
                segments = np.stack([pos_pts, val_pts]).transpose(2, 1, 0)
                if self.orient == "y":
                    segments = segments[:, :, ::-1]
                kws = {
                    "color": linecolor,
                    "linewidth": linewidth / 2,
                    **inner_kws,
                }
                lines = mpl.collections.LineCollection(segments, **kws)
                ax.add_collection(lines, autolim=False)

            elif inner.startswith("quart"):
                stats = np.percentile(obs, [25, 50, 75])
                pos0 = np.interp(stats, data[value_var], data[self.orient] - offsets[0])
                pos1 = np.interp(stats, data[value_var], data[self.orient] + offsets[1])
                pos_pts = np.stack([inv_pos(pos0), inv_pos(pos1)])
                val_pts = np.stack([inv_val(stats), inv_val(stats)])
                segments = np.stack([pos_pts, val_pts]).transpose(2, 0, 1)
                if self.orient == "y":
                    segments = segments[:, ::-1, :]
                dashes = [(1.25, .75), (2.5, 1), (1.25, .75)]
                for i, segment in enumerate(segments):
                    kws = {
                        "color": linecolor,
                        "linewidth": linewidth,
                        "dashes": dashes[i],
                        **inner_kws,
                    }
                    ax.plot(*segment, **kws)

            elif inner.startswith("box"):
                stats = mpl.cbook.boxplot_stats(obs)[0]
                pos = np.array(pos_dict[self.orient])
                if split:
                    pos += (-1 if right_side else 1) * pos_dict["width"] / 2
                pos = [pos, pos], [pos, pos], [pos]
                val = (
                    [stats["whislo"], stats["whishi"]],
                    [stats["q1"], stats["q3"]],
                    [stats["med"]]
                )
                if self.orient == "x":
                    (x0, x1, x2), (y0, y1, y2) = pos, val
                else:
                    (x0, x1, x2), (y0, y1, y2) = val, pos

                if split:
                    offset = (1 if right_side else -1) * box_width / 72 / 2
                    dx, dy = (offset, 0) if self.orient == "x" else (0, -offset)
                    trans = ax.transData + mpl.transforms.ScaledTranslation(
                        dx, dy, ax.figure.dpi_scale_trans,
                    )
                else:
                    trans = ax.transData
                line_kws = {
                    "color": linecolor,
                    "transform": trans,
                    **inner_kws,
                    "linewidth": whis_width,
                }
                ax.plot(invx(x0), invy(y0), **line_kws)
                line_kws["linewidth"] = box_width
                ax.plot(invx(x1), invy(y1), **line_kws)
                dot_kws = {
                    "marker": marker,
                    "markersize": box_width / 1.2,
                    "markeredgewidth": box_width / 5,
                    "transform": trans,
                    **inner_kws,
                    "markeredgecolor": "w",
                    "markerfacecolor": "w",
                    "color": linecolor,  # simplify tests
                }
                ax.plot(invx(x2), invy(y2), **dot_kws)

        legend_artist = _get_patch_legend_artist(fill)
        common_kws = {**plot_kws, "linewidth": linewidth, "edgecolor": linecolor}
        self._configure_legend(ax, legend_artist, common_kws)

    def plot_points(
        self,
        aggregator,
        markers,
        linestyles,
        dodge,
        color,
        capsize,
        err_kws,
        plot_kws,
    ):

        agg_var = {"x": "y", "y": "x"}[self.orient]
        iter_vars = ["hue"]

        plot_kws = normalize_kwargs(plot_kws, mpl.lines.Line2D)
        plot_kws.setdefault("linewidth", mpl.rcParams["lines.linewidth"] * 1.8)
        plot_kws.setdefault("markeredgewidth", plot_kws["linewidth"] * 0.75)
        plot_kws.setdefault("markersize", plot_kws["linewidth"] * np.sqrt(2 * np.pi))

        markers = self._map_prop_with_hue("marker", markers, "o", plot_kws)
        linestyles = self._map_prop_with_hue("linestyle", linestyles, "-", plot_kws)

        base_positions = self.var_levels[self.orient]
        if self.var_types[self.orient] == "categorical":
            min_cat_val = int(self.comp_data[self.orient].min())
            max_cat_val = int(self.comp_data[self.orient].max())
            base_positions = [i for i in range(min_cat_val, max_cat_val + 1)]

        n_hue_levels = 0 if self._hue_map.levels is None else len(self._hue_map.levels)
        if dodge is True:
            dodge = .025 * n_hue_levels

        ax = self.ax

        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=True):

            ax = self._get_axes(sub_vars)

            ori_axis = getattr(ax, f"{self.orient}axis")
            transform, _ = _get_transform_functions(ax, self.orient)
            positions = transform(ori_axis.convert_units(base_positions))
            agg_data = sub_data if sub_data.empty else (
                sub_data
                .groupby(self.orient)
                .apply(aggregator, agg_var, **groupby_apply_include_groups(False))
                .reindex(pd.Index(positions, name=self.orient))
                .reset_index()
            )

            if dodge:
                hue_idx = self._hue_map.levels.index(sub_vars["hue"])
                step_size = dodge / (n_hue_levels - 1)
                offset = -dodge / 2 + step_size * hue_idx
                agg_data[self.orient] += offset * self._native_width

            self._invert_scale(ax, agg_data)

            sub_kws = plot_kws.copy()
            sub_kws.update(
                marker=markers[sub_vars.get("hue")],
                linestyle=linestyles[sub_vars.get("hue")],
                color=self._hue_map(sub_vars["hue"]) if "hue" in sub_vars else color,
            )

            line, = ax.plot(agg_data["x"], agg_data["y"], **sub_kws)

            sub_err_kws = err_kws.copy()
            line_props = line.properties()
            for prop in ["color", "linewidth", "alpha", "zorder"]:
                sub_err_kws.setdefault(prop, line_props[prop])
            if aggregator.error_method is not None:
                self.plot_errorbars(ax, agg_data, capsize, sub_err_kws)

        legend_artist = partial(mpl.lines.Line2D, [], [])
        semantic_kws = {"hue": {"marker": markers, "linestyle": linestyles}}
        self._configure_legend(ax, legend_artist, sub_kws, semantic_kws)

    def plot_bars(
        self,
        aggregator,
        dodge,
        gap,
        width,
        fill,
        color,
        capsize,
        err_kws,
        plot_kws,
    ):

        agg_var = {"x": "y", "y": "x"}[self.orient]
        iter_vars = ["hue"]

        ax = self.ax

        if self._hue_map.levels is None:
            dodge = False

        if dodge and capsize is not None:
            capsize = capsize / len(self._hue_map.levels)

        if not fill:
            plot_kws.setdefault("linewidth", 1.5 * mpl.rcParams["lines.linewidth"])

        err_kws.setdefault("linewidth", 1.5 * mpl.rcParams["lines.linewidth"])

        for sub_vars, sub_data in self.iter_data(iter_vars,
                                                 from_comp_data=True,
                                                 allow_empty=True):

            ax = self._get_axes(sub_vars)

            agg_data = sub_data if sub_data.empty else (
                sub_data
                .groupby(self.orient)
                .apply(aggregator, agg_var, **groupby_apply_include_groups(False))
                .reset_index()
            )

            agg_data["width"] = width * self._native_width
            if dodge:
                self._dodge(sub_vars, agg_data)
            if gap:
                agg_data["width"] *= 1 - gap

            agg_data["edge"] = agg_data[self.orient] - agg_data["width"] / 2
            self._invert_scale(ax, agg_data)

            if self.orient == "x":
                bar_func = ax.bar
                kws = dict(
                    x=agg_data["edge"], height=agg_data["y"], width=agg_data["width"]
                )
            else:
                bar_func = ax.barh
                kws = dict(
                    y=agg_data["edge"], width=agg_data["x"], height=agg_data["width"]
                )

            main_color = self._hue_map(sub_vars["hue"]) if "hue" in sub_vars else color

            # Set both color and facecolor for property cycle logic
            kws["align"] = "edge"
            if fill:
                kws.update(color=main_color, facecolor=main_color)
            else:
                kws.update(color=main_color, edgecolor=main_color, facecolor="none")

            bar_func(**{**kws, **plot_kws})

            if aggregator.error_method is not None:
                self.plot_errorbars(
                    ax, agg_data, capsize,
                    {"color": ".26" if fill else main_color, **err_kws}
                )

        legend_artist = _get_patch_legend_artist(fill)
        self._configure_legend(ax, legend_artist, plot_kws)

    def plot_errorbars(self, ax, data, capsize, err_kws):

        var = {"x": "y", "y": "x"}[self.orient]
        for row in data.to_dict("records"):

            row = dict(row)
            pos = np.array([row[self.orient], row[self.orient]])
            val = np.array([row[f"{var}min"], row[f"{var}max"]])

            if capsize:

                cw = capsize * self._native_width / 2
                scl, inv = _get_transform_functions(ax, self.orient)
                cap = inv(scl(pos[0]) - cw), inv(scl(pos[1]) + cw)

                pos = np.concatenate([
                    [*cap, np.nan], pos, [np.nan, *cap]
                ])
                val = np.concatenate([
                    [val[0], val[0], np.nan], val, [np.nan, val[-1], val[-1]],
                ])

            if self.orient == "x":
                args = pos, val
            else:
                args = val, pos
            ax.plot(*args, **err_kws)


class _CategoricalAggPlotter(_CategoricalPlotter):

    flat_structure = {"x": "@index", "y": "@values"}


_categorical_docs = dict(

    # Shared narrative docs
    categorical_narrative=dedent("""\
    See the :ref:`tutorial <categorical_tutorial>` for more information.

    .. note::
        By default, this function treats one of the variables as categorical
        and draws data at ordinal positions (0, 1, ... n) on the relevant axis.
        As of version 0.13.0, this can be disabled by setting `native_scale=True`.
    """),

    # Shared function parameters
    input_params=dedent("""\
    x, y, hue : names of variables in `data` or vector data
        Inputs for plotting long-form data. See examples for interpretation.\
    """),
    categorical_data=dedent("""\
    data : DataFrame, Series, dict, array, or list of arrays
        Dataset for plotting. If `x` and `y` are absent, this is
        interpreted as wide-form. Otherwise it is expected to be long-form.\
    """),
    order_vars=dedent("""\
    order, hue_order : lists of strings
        Order to plot the categorical levels in; otherwise the levels are
        inferred from the data objects.\
    """),
    stat_api_params=dedent("""\
    estimator : string or callable that maps vector -> scalar
        Statistical function to estimate within each categorical bin.
    errorbar : string, (string, number) tuple, callable or None
        Name of errorbar method (either "ci", "pi", "se", or "sd"), or a tuple
        with a method name and a level parameter, or a function that maps from a
        vector to a (min, max) interval, or None to hide errorbar. See the
        :doc:`errorbar tutorial </tutorial/error_bars>` for more information.

        .. versionadded:: v0.12.0
    n_boot : int
        Number of bootstrap samples used to compute confidence intervals.
    seed : int, `numpy.random.Generator`, or `numpy.random.RandomState`
        Seed or random number generator for reproducible bootstrapping.
    units : name of variable in `data` or vector data
        Identifier of sampling units; used by the errorbar function to
        perform a multilevel bootstrap and account for repeated measures
    weights : name of variable in `data` or vector data
        Data values or column used to compute weighted statistics.
        Note that the use of weights may limit other statistical options.

        .. versionadded:: v0.13.1\
    """),
    ci=dedent("""\
    ci : float
        Level of the confidence interval to show, in [0, 100].

        .. deprecated:: v0.12.0
            Use `errorbar=("ci", ...)`.\
    """),
    orient=dedent("""\
    orient : "v" | "h" | "x" | "y"
        Orientation of the plot (vertical or horizontal). This is usually
        inferred based on the type of the input variables, but it can be used
        to resolve ambiguity when both `x` and `y` are numeric or when
        plotting wide-form data.

        .. versionchanged:: v0.13.0
            Added 'x'/'y' as options, equivalent to 'v'/'h'.\
    """),
    color=dedent("""\
    color : matplotlib color
        Single color for the elements in the plot.\
    """),
    palette=dedent("""\
    palette : palette name, list, dict, or :class:`matplotlib.colors.Colormap`
        Color palette that maps the hue variable. If the palette is a dictionary,
        keys should be names of levels and values should be matplotlib colors.
        The type/value will sometimes force a qualitative/quantitative mapping.\
    """),
    hue_norm=dedent("""\
    hue_norm : tuple or :class:`matplotlib.colors.Normalize` object
        Normalization in data units for colormap applied to the `hue`
        variable when it is numeric. Not relevant if `hue` is categorical.

        .. versionadded:: v0.12.0\
    """),
    saturation=dedent("""\
    saturation : float
        Proportion of the original saturation to draw fill colors in. Large
        patches often look better with desaturated colors, but set this to
        `1` if you want the colors to perfectly match the input values.\
    """),
    capsize=dedent("""\
    capsize : float
        Width of the "caps" on error bars, relative to bar spacing.\
    """),
    errcolor=dedent("""\
    errcolor : matplotlib color
        Color used for the error bar lines.

        .. deprecated:: 0.13.0
            Use `err_kws={'color': ...}`.\
    """),
    errwidth=dedent("""\
    errwidth : float
        Thickness of error bar lines (and caps), in points.

        .. deprecated:: 0.13.0
            Use `err_kws={'linewidth': ...}`.\
    """),
    fill=dedent("""\
    fill : bool
        If True, use a solid patch. Otherwise, draw as line art.

        .. versionadded:: v0.13.0\
    """),
    gap=dedent("""\
    gap : float
        Shrink on the orient axis by this factor to add a gap between dodged elements.

        .. versionadded:: 0.13.0\
    """),
    width=dedent("""\
    width : float
        Width allotted to each element on the orient axis. When `native_scale=True`,
        it is relative to the minimum distance between two values in the native scale.\
    """),
    dodge=dedent("""\
    dodge : "auto" or bool
        When hue mapping is used, whether elements should be narrowed and shifted along
        the orient axis to eliminate overlap. If `"auto"`, set to `True` when the
        orient variable is crossed with the categorical variable or `False` otherwise.

        .. versionchanged:: 0.13.0

            Added `"auto"` mode as a new default.\
    """),
    linewidth=dedent("""\
    linewidth : float
        Width of the lines that frame the plot elements.\
    """),
    linecolor=dedent("""\
    linecolor : color
        Color to use for line elements, when `fill` is True.

        .. versionadded:: v0.13.0\
    """),
    log_scale=dedent("""\
    log_scale : bool or number, or pair of bools or numbers
        Set axis scale(s) to log. A single value sets the data axis for any numeric
        axes in the plot. A pair of values sets each axis independently.
        Numeric values are interpreted as the desired base (default 10).
        When `None` or `False`, seaborn defers to the existing Axes scale.

        .. versionadded:: v0.13.0\
    """),
    native_scale=dedent("""\
    native_scale : bool
        When True, numeric or datetime values on the categorical axis will maintain
        their original scaling rather than being converted to fixed indices.

        .. versionadded:: v0.13.0\
    """),
    formatter=dedent("""\
    formatter : callable
        Function for converting categorical data into strings. Affects both grouping
        and tick labels.

        .. versionadded:: v0.13.0\
    """),
    legend=dedent("""\
    legend : "auto", "brief", "full", or False
        How to draw the legend. If "brief", numeric `hue` and `size`
        variables will be represented with a sample of evenly spaced values.
        If "full", every group will get an entry in the legend. If "auto",
        choose between brief or full representation based on number of levels.
        If `False`, no legend data is added and no legend is drawn.

        .. versionadded:: v0.13.0\
    """),
    err_kws=dedent("""\
    err_kws : dict
        Parameters of :class:`matplotlib.lines.Line2D`, for the error bar artists.

        .. versionadded:: v0.13.0\
    """),
    ax_in=dedent("""\
    ax : matplotlib Axes
        Axes object to draw the plot onto, otherwise uses the current Axes.\
    """),
    ax_out=dedent("""\
    ax : matplotlib Axes
        Returns the Axes object with the plot drawn onto it.\
    """),

    # Shared see also
    boxplot=dedent("""\
    boxplot : A traditional box-and-whisker plot with a similar API.\
    """),
    violinplot=dedent("""\
    violinplot : A combination of boxplot and kernel density estimation.\
    """),
    stripplot=dedent("""\
    stripplot : A scatterplot where one variable is categorical. Can be used
                in conjunction with other plots to show each observation.\
    """),
    swarmplot=dedent("""\
    swarmplot : A categorical scatterplot where the points do not overlap. Can
                be used with other plots to show each observation.\
    """),
    barplot=dedent("""\
    barplot : Show point estimates and confidence intervals using bars.\
    """),
    countplot=dedent("""\
    countplot : Show the counts of observations in each categorical bin.\
    """),
    pointplot=dedent("""\
    pointplot : Show point estimates and confidence intervals using dots.\
    """),
    catplot=dedent("""\
    catplot : Combine a categorical plot with a :class:`FacetGrid`.\
    """),
    boxenplot=dedent("""\
    boxenplot : An enhanced boxplot for larger datasets.\
    """),

)

_categorical_docs.update(_facet_docs)


def boxplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    orient=None, color=None, palette=None, saturation=.75, fill=True,
    dodge="auto", width=.8, gap=0, whis=1.5, linecolor="auto", linewidth=None,
    fliersize=None, hue_norm=None, native_scale=False, log_scale=None, formatter=None,
    legend="auto", ax=None, **kwargs
):

    p = _CategoricalPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if dodge == "auto":
        # Needs to be before scale_categorical changes the coordinate series dtype
        dodge = p._dodge_needed()

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    saturation = saturation if fill else 1
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm, saturation=saturation)
    color = _default_color(
        ax.fill_between, hue, color,
        {k: v for k, v in kwargs.items() if k in ["c", "color", "fc", "facecolor"]},
        saturation=saturation,
    )
    linecolor = p._complement_color(linecolor, color, p._hue_map)

    p.plot_boxes(
        width=width,
        dodge=dodge,
        gap=gap,
        fill=fill,
        whis=whis,
        color=color,
        linecolor=linecolor,
        linewidth=linewidth,
        fliersize=fliersize,
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


boxplot.__doc__ = dedent("""\
    Draw a box plot to show distributions with respect to categories.

    A box plot (or box-and-whisker plot) shows the distribution of quantitative
    data in a way that facilitates comparisons between variables or across
    levels of a categorical variable. The box shows the quartiles of the
    dataset while the whiskers extend to show the rest of the distribution,
    except for points that are determined to be "outliers" using a method
    that is a function of the inter-quartile range.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    {orient}
    {color}
    {palette}
    {saturation}
    {fill}
    {dodge}
    {width}
    {gap}
    whis : float or pair of floats
        Paramater that controls whisker length. If scalar, whiskers are drawn
        to the farthest datapoint within *whis * IQR* from the nearest hinge.
        If a tuple, it is interpreted as percentiles that whiskers represent.
    {linecolor}
    {linewidth}
    fliersize : float
        Size of the markers used to indicate outlier observations.
    {hue_norm}
    {log_scale}
    {native_scale}
    {formatter}
    {legend}
    {ax_in}
    kwargs : key, value mappings
        Other keyword arguments are passed through to
        :meth:`matplotlib.axes.Axes.boxplot`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    {violinplot}
    {stripplot}
    {swarmplot}
    {catplot}

    Examples
    --------
    .. include:: ../docstrings/boxplot.rst

    """).format(**_categorical_docs)


def violinplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    orient=None, color=None, palette=None, saturation=.75, fill=True,
    inner="box", split=False, width=.8, dodge="auto", gap=0,
    linewidth=None, linecolor="auto", cut=2, gridsize=100,
    bw_method="scott", bw_adjust=1, density_norm="area", common_norm=False,
    hue_norm=None, formatter=None, log_scale=None, native_scale=False,
    legend="auto", scale=deprecated, scale_hue=deprecated, bw=deprecated,
    inner_kws=None, ax=None, **kwargs,
):

    p = _CategoricalPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if dodge == "auto":
        # Needs to be before scale_categorical changes the coordinate series dtype
        dodge = p._dodge_needed()

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    saturation = saturation if fill else 1
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm, saturation=saturation)
    color = _default_color(
        ax.fill_between, hue, color,
        {k: v for k, v in kwargs.items() if k in ["c", "color", "fc", "facecolor"]},
        saturation=saturation,
    )
    linecolor = p._complement_color(linecolor, color, p._hue_map)

    density_norm, common_norm = p._violin_scale_backcompat(
        scale, scale_hue, density_norm, common_norm,
    )

    bw_method = p._violin_bw_backcompat(bw, bw_method)
    kde_kws = dict(cut=cut, gridsize=gridsize, bw_method=bw_method, bw_adjust=bw_adjust)
    inner_kws = {} if inner_kws is None else inner_kws.copy()

    p.plot_violins(
        width=width,
        dodge=dodge,
        gap=gap,
        split=split,
        color=color,
        fill=fill,
        linecolor=linecolor,
        linewidth=linewidth,
        inner=inner,
        density_norm=density_norm,
        common_norm=common_norm,
        kde_kws=kde_kws,
        inner_kws=inner_kws,
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


violinplot.__doc__ = dedent("""\
    Draw a patch representing a KDE and add observations or box plot statistics.

    A violin plot plays a similar role as a box-and-whisker plot. It shows the
    distribution of data points after grouping by one (or more) variables.
    Unlike a box plot, each violin is drawn using a kernel density estimate
    of the underlying distribution.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    {orient}
    {color}
    {palette}
    {saturation}
    {fill}
    inner : {{"box", "quart", "point", "stick", None}}
        Representation of the data in the violin interior. One of the following:

        - `"box"`: draw a miniature box-and-whisker plot
        - `"quart"`: show the quartiles of the data
        - `"point"` or `"stick"`: show each observation
    split : bool
        Show an un-mirrored distribution, alternating sides when using `hue`.

        .. versionchanged:: v0.13.0
            Previously, this option required a `hue` variable with exactly two levels.
    {width}
    {dodge}
    {gap}
    {linewidth}
    {linecolor}
    cut : float
        Distance, in units of bandwidth, to extend the density past extreme
        datapoints. Set to 0 to limit the violin within the data range.
    gridsize : int
        Number of points in the discrete grid used to evaluate the KDE.
    bw_method : {{"scott", "silverman", float}}
        Either the name of a reference rule or the scale factor to use when
        computing the kernel bandwidth. The actual kernel size will be
        determined by multiplying the scale factor by the standard deviation of
        the data within each group.

        .. versionadded:: v0.13.0
    bw_adjust: float
        Factor that scales the bandwidth to use more or less smoothing.

        .. versionadded:: v0.13.0
    density_norm : {{"area", "count", "width"}}
        Method that normalizes each density to determine the violin's width.
        If `area`, each violin will have the same area. If `count`, the width
        will be proportional to the number of observations. If `width`, each
        violin will have the same width.

        .. versionadded:: v0.13.0
    common_norm : bool
        When `True`, normalize the density across all violins.

        .. versionadded:: v0.13.0
    {hue_norm}
    {formatter}
    {log_scale}
    {native_scale}
    {legend}
    scale : {{"area", "count", "width"}}
        .. deprecated:: v0.13.0
            See `density_norm`.
    scale_hue : bool
        .. deprecated:: v0.13.0
            See `common_norm`.
    bw : {{'scott', 'silverman', float}}
        .. deprecated:: v0.13.0
            See `bw_method` and `bw_adjust`.
    inner_kws : dict of key, value mappings
        Keyword arguments for the "inner" plot, passed to one of:

        - :class:`matplotlib.collections.LineCollection` (with `inner="stick"`)
        - :meth:`matplotlib.axes.Axes.scatter` (with `inner="point"`)
        - :meth:`matplotlib.axes.Axes.plot` (with `inner="quart"` or `inner="box"`)

        Additionally, with `inner="box"`, the keywords `box_width`, `whis_width`,
        and `marker` receive special handling for the components of the "box" plot.

        .. versionadded:: v0.13.0
    {ax_in}
    kwargs : key, value mappings
        Keyword arguments for the violin patches, passsed through to
        :meth:`matplotlib.axes.Axes.fill_between`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    {boxplot}
    {stripplot}
    {swarmplot}
    {catplot}

    Examples
    --------
    .. include:: ../docstrings/violinplot.rst

    """).format(**_categorical_docs)


def boxenplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    orient=None, color=None, palette=None, saturation=.75, fill=True,
    dodge="auto", width=.8, gap=0, linewidth=None, linecolor=None,
    width_method="exponential", k_depth="tukey", outlier_prop=0.007, trust_alpha=0.05,
    showfliers=True, hue_norm=None, log_scale=None, native_scale=False, formatter=None,
    legend="auto", scale=deprecated, box_kws=None, flier_kws=None, line_kws=None,
    ax=None, **kwargs,
):

    p = _CategoricalPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if dodge == "auto":
        # Needs to be before scale_categorical changes the coordinate series dtype
        dodge = p._dodge_needed()

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    # Longer-term deprecations
    width_method = p._boxen_scale_backcompat(scale, width_method)

    saturation = saturation if fill else 1
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm, saturation=saturation)
    color = _default_color(
        ax.fill_between, hue, color,
        {},  # TODO how to get default color?
        # {k: v for k, v in kwargs.items() if k in ["c", "color", "fc", "facecolor"]},
        saturation=saturation,
    )
    linecolor = p._complement_color(linecolor, color, p._hue_map)

    p.plot_boxens(
        width=width,
        dodge=dodge,
        gap=gap,
        fill=fill,
        color=color,
        linecolor=linecolor,
        linewidth=linewidth,
        width_method=width_method,
        k_depth=k_depth,
        outlier_prop=outlier_prop,
        trust_alpha=trust_alpha,
        showfliers=showfliers,
        box_kws=box_kws,
        flier_kws=flier_kws,
        line_kws=line_kws,
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


boxenplot.__doc__ = dedent("""\
    Draw an enhanced box plot for larger datasets.

    This style of plot was originally named a "letter value" plot because it
    shows a large number of quantiles that are defined as "letter values".  It
    is similar to a box plot in plotting a nonparametric representation of a
    distribution in which all features correspond to actual observations. By
    plotting more quantiles, it provides more information about the shape of
    the distribution, particularly in the tails.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    {orient}
    {color}
    {palette}
    {saturation}
    {fill}
    {dodge}
    {width}
    {gap}
    {linewidth}
    {linecolor}
    width_method : {{"exponential", "linear", "area"}}
        Method to use for the width of the letter value boxes:

        - `"exponential"`: Represent the corresponding percentile
        - `"linear"`: Decrease by a constant amount for each box
        - `"area"`: Represent the density of data points in that box
    k_depth : {{"tukey", "proportion", "trustworthy", "full"}} or int
        The number of levels to compute and draw in each tail:

        - `"tukey"`: Use log2(n) - 3 levels, covering similar range as boxplot whiskers
        - `"proportion"`: Leave approximately `outlier_prop` fliers
        - `"trusthworthy"`: Extend to level with confidence of at least `trust_alpha`
        - `"full"`: Use log2(n) + 1 levels and extend to most extreme points
    outlier_prop : float
        Proportion of data expected to be outliers; used when `k_depth="proportion"`.
    trust_alpha : float
        Confidence threshold for most extreme level; used when `k_depth="trustworthy"`.
    showfliers : bool
        If False, suppress the plotting of outliers.
    {hue_norm}
    {log_scale}
    {native_scale}
    {formatter}
    {legend}
    box_kws: dict
        Keyword arguments for the box artists; passed to
        :class:`matplotlib.patches.Rectangle`.

        .. versionadded:: v0.12.0
    line_kws: dict
        Keyword arguments for the line denoting the median; passed to
        :meth:`matplotlib.axes.Axes.plot`.

        .. versionadded:: v0.12.0
    flier_kws: dict
        Keyword arguments for the scatter denoting the outlier observations;
        passed to :meth:`matplotlib.axes.Axes.scatter`.

        .. versionadded:: v0.12.0
    {ax_in}
    kwargs : key, value mappings
        Other keyword arguments are passed to :class:`matplotlib.patches.Rectangle`,
        superceded by those in `box_kws`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    {violinplot}
    {boxplot}
    {catplot}

    Notes
    -----

    For a more extensive explanation, you can read the paper that introduced the plot:
    https://vita.had.co.nz/papers/letter-value-plot.html

    Examples
    --------
    .. include:: ../docstrings/boxenplot.rst

    """).format(**_categorical_docs)


def stripplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    jitter=True, dodge=False, orient=None, color=None, palette=None,
    size=5, edgecolor=default, linewidth=0,
    hue_norm=None, log_scale=None, native_scale=False, formatter=None, legend="auto",
    ax=None, **kwargs
):

    p = _CategoricalPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)
    color = _default_color(ax.scatter, hue, color, kwargs)
    edgecolor = p._complement_color(edgecolor, color, p._hue_map)

    kwargs.setdefault("zorder", 3)
    size = kwargs.get("s", size)

    kwargs.update(
        s=size ** 2,
        edgecolor=edgecolor,
        linewidth=linewidth,
    )

    p.plot_strips(
        jitter=jitter,
        dodge=dodge,
        color=color,
        plot_kws=kwargs,
    )

    # XXX this happens inside a plotting method in the distribution plots
    # but maybe it's better out here? Alternatively, we have an open issue
    # suggesting that _attach could add default axes labels, which seems smart.
    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


stripplot.__doc__ = dedent("""\
    Draw a categorical scatterplot using jitter to reduce overplotting.

    A strip plot can be drawn on its own, but it is also a good complement
    to a box or violin plot in cases where you want to show all observations
    along with some representation of the underlying distribution.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    jitter : float, `True`/`1` is special-cased
        Amount of jitter (only along the categorical axis) to apply. This
        can be useful when you have many points and they overlap, so that
        it is easier to see the distribution. You can specify the amount
        of jitter (half the width of the uniform random variable support),
        or use `True` for a good default.
    dodge : bool
        When a `hue` variable is assigned, setting this to `True` will
        separate the strips for different hue levels along the categorical
        axis and narrow the amount of space allotedto each strip. Otherwise,
        the points for each level will be plotted in the same strip.
    {orient}
    {color}
    {palette}
    size : float
        Radius of the markers, in points.
    edgecolor : matplotlib color, "gray" is special-cased
        Color of the lines around each point. If you pass `"gray"`, the
        brightness is determined by the color palette used for the body
        of the points. Note that `stripplot` has `linewidth=0` by default,
        so edge colors are only visible with nonzero line width.
    {linewidth}
    {hue_norm}
    {log_scale}
    {native_scale}
    {formatter}
    {legend}
    {ax_in}
    kwargs : key, value mappings
        Other keyword arguments are passed through to
        :meth:`matplotlib.axes.Axes.scatter`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    {swarmplot}
    {boxplot}
    {violinplot}
    {catplot}

    Examples
    --------
    .. include:: ../docstrings/stripplot.rst

    """).format(**_categorical_docs)


def swarmplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    dodge=False, orient=None, color=None, palette=None,
    size=5, edgecolor=None, linewidth=0, hue_norm=None, log_scale=None,
    native_scale=False, formatter=None, legend="auto", warn_thresh=.05,
    ax=None, **kwargs
):

    p = _CategoricalPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    if not p.has_xy_data:
        return ax

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)
    color = _default_color(ax.scatter, hue, color, kwargs)
    edgecolor = p._complement_color(edgecolor, color, p._hue_map)

    kwargs.setdefault("zorder", 3)
    size = kwargs.get("s", size)

    if linewidth is None:
        linewidth = size / 10

    kwargs.update(dict(
        s=size ** 2,
        edgecolor=edgecolor,
        linewidth=linewidth,
    ))

    p.plot_swarms(
        dodge=dodge,
        color=color,
        warn_thresh=warn_thresh,
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


swarmplot.__doc__ = dedent("""\
    Draw a categorical scatterplot with points adjusted to be non-overlapping.

    This function is similar to :func:`stripplot`, but the points are adjusted
    (only along the categorical axis) so that they don't overlap. This gives a
    better representation of the distribution of values, but it does not scale
    well to large numbers of observations. This style of plot is sometimes
    called a "beeswarm".

    A swarm plot can be drawn on its own, but it is also a good complement
    to a box or violin plot in cases where you want to show all observations
    along with some representation of the underlying distribution.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    dodge : bool
        When a `hue` variable is assigned, setting this to `True` will
        separate the swarms for different hue levels along the categorical
        axis and narrow the amount of space allotedto each strip. Otherwise,
        the points for each level will be plotted in the same swarm.
    {orient}
    {color}
    {palette}
    size : float
        Radius of the markers, in points.
    edgecolor : matplotlib color, "gray" is special-cased
        Color of the lines around each point. If you pass `"gray"`, the
        brightness is determined by the color palette used for the body
        of the points.
    {linewidth}
    {log_scale}
    {native_scale}
    {formatter}
    {legend}
    {ax_in}
    kwargs : key, value mappings
        Other keyword arguments are passed through to
        :meth:`matplotlib.axes.Axes.scatter`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    {boxplot}
    {violinplot}
    {stripplot}
    {catplot}

    Examples
    --------
    .. include:: ../docstrings/swarmplot.rst

    """).format(**_categorical_docs)


def barplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    estimator="mean", errorbar=("ci", 95), n_boot=1000, seed=None, units=None,
    weights=None, orient=None, color=None, palette=None, saturation=.75,
    fill=True, hue_norm=None, width=.8, dodge="auto", gap=0, log_scale=None,
    native_scale=False, formatter=None, legend="auto", capsize=0, err_kws=None,
    ci=deprecated, errcolor=deprecated, errwidth=deprecated, ax=None, **kwargs,
):

    errorbar = utils._deprecate_ci(errorbar, ci)

    # Be backwards compatible with len passed directly, which
    # does not work in Series.agg (maybe a pandas bug?)
    if estimator is len:
        estimator = "size"

    p = _CategoricalAggPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, units=units, weight=weights),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if dodge == "auto":
        # Needs to be before scale_categorical changes the coordinate series dtype
        dodge = p._dodge_needed()

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    saturation = saturation if fill else 1
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm, saturation=saturation)
    color = _default_color(ax.bar, hue, color, kwargs, saturation=saturation)

    agg_cls = WeightedAggregator if "weight" in p.plot_data else EstimateAggregator
    aggregator = agg_cls(estimator, errorbar, n_boot=n_boot, seed=seed)
    err_kws = {} if err_kws is None else normalize_kwargs(err_kws, mpl.lines.Line2D)

    # Deprecations to remove in v0.15.0.
    err_kws, capsize = p._err_kws_backcompat(err_kws, errcolor, errwidth, capsize)

    p.plot_bars(
        aggregator=aggregator,
        dodge=dodge,
        width=width,
        gap=gap,
        color=color,
        fill=fill,
        capsize=capsize,
        err_kws=err_kws,
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


barplot.__doc__ = dedent("""\
    Show point estimates and errors as rectangular bars.

    A bar plot represents an aggregate or statistical estimate for a numeric
    variable with the height of each rectangle and indicates the uncertainty
    around that estimate using an error bar. Bar plots include 0 in the
    axis range, and they are a good choice when 0 is a meaningful value
    for the variable to take.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    {stat_api_params}
    {orient}
    {color}
    {palette}
    {saturation}
    {fill}
    {hue_norm}
    {width}
    {dodge}
    {gap}
    {log_scale}
    {native_scale}
    {formatter}
    {legend}
    {capsize}
    {err_kws}
    {ci}
    {errcolor}
    {errwidth}
    {ax_in}
    kwargs : key, value mappings
        Other parameters are passed through to :class:`matplotlib.patches.Rectangle`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    {countplot}
    {pointplot}
    {catplot}

    Notes
    -----

    For datasets where 0 is not a meaningful value, a :func:`pointplot` will
    allow you to focus on differences between levels of one or more categorical
    variables.

    It is also important to keep in mind that a bar plot shows only the mean (or
    other aggregate) value, but it is often more informative to show the
    distribution of values at each level of the categorical variables. In those
    cases, approaches such as a :func:`boxplot` or :func:`violinplot` may be
    more appropriate.

    Examples
    --------
    .. include:: ../docstrings/barplot.rst

    """).format(**_categorical_docs)


def pointplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    estimator="mean", errorbar=("ci", 95), n_boot=1000, seed=None, units=None,
    weights=None, color=None, palette=None, hue_norm=None, markers=default,
    linestyles=default, dodge=False, log_scale=None, native_scale=False,
    orient=None, capsize=0, formatter=None, legend="auto", err_kws=None,
    ci=deprecated, errwidth=deprecated, join=deprecated, scale=deprecated,
    ax=None, **kwargs,
):

    errorbar = utils._deprecate_ci(errorbar, ci)

    p = _CategoricalAggPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, units=units, weight=weights),
        order=order,
        orient=orient,
        # Handle special backwards compatibility where pointplot originally
        # did *not* default to multi-colored unless a palette was specified.
        color="C0" if (color is None and palette is None) else color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)
    color = _default_color(ax.plot, hue, color, kwargs)

    agg_cls = WeightedAggregator if "weight" in p.plot_data else EstimateAggregator
    aggregator = agg_cls(estimator, errorbar, n_boot=n_boot, seed=seed)
    err_kws = {} if err_kws is None else normalize_kwargs(err_kws, mpl.lines.Line2D)

    # Deprecations to remove in v0.15.0.
    p._point_kwargs_backcompat(scale, join, kwargs)
    err_kws, capsize = p._err_kws_backcompat(err_kws, None, errwidth, capsize)

    p.plot_points(
        aggregator=aggregator,
        markers=markers,
        linestyles=linestyles,
        dodge=dodge,
        color=color,
        capsize=capsize,
        err_kws=err_kws,
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


pointplot.__doc__ = dedent("""\
    Show point estimates and errors using lines with markers.

    A point plot represents an estimate of central tendency for a numeric
    variable by the position of the dot and provides some indication of the
    uncertainty around that estimate using error bars.

    Point plots can be more useful than bar plots for focusing comparisons
    between different levels of one or more categorical variables. They are
    particularly adept at showing interactions: how the relationship between
    levels of one categorical variable changes across levels of a second
    categorical variable. The lines that join each point from the same `hue`
    level allow interactions to be judged by differences in slope, which is
    easier for the eyes than comparing the heights of several groups of points
    or bars.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    {stat_api_params}
    {color}
    {palette}
    markers : string or list of strings
        Markers to use for each of the `hue` levels.
    linestyles : string or list of strings
        Line styles to use for each of the `hue` levels.
    dodge : bool or float
        Amount to separate the points for each level of the `hue` variable along
        the categorical axis. Setting to `True` will apply a small default.
    {log_scale}
    {native_scale}
    {orient}
    {capsize}
    {formatter}
    {legend}
    {err_kws}
    {ci}
    {errwidth}
    join : bool
        If `True`, connect point estimates with a line.

        .. deprecated:: v0.13.0
            Set `linestyle="none"` to remove the lines between the points.
    scale : float
        Scale factor for the plot elements.

        .. deprecated:: v0.13.0
            Control element sizes with :class:`matplotlib.lines.Line2D` parameters.
    {ax_in}
    kwargs : key, value mappings
        Other parameters are passed through to :class:`matplotlib.lines.Line2D`.

        .. versionadded:: v0.13.0

    Returns
    -------
    {ax_out}

    See Also
    --------
    {barplot}
    {catplot}

    Notes
    -----
    It is important to keep in mind that a point plot shows only the mean (or
    other estimator) value, but in many cases it may be more informative to
    show the distribution of values at each level of the categorical variables.
    In that case, other approaches such as a box or violin plot may be more
    appropriate.

    Examples
    --------
    .. include:: ../docstrings/pointplot.rst

    """).format(**_categorical_docs)


def countplot(
    data=None, *, x=None, y=None, hue=None, order=None, hue_order=None,
    orient=None, color=None, palette=None, saturation=.75, fill=True, hue_norm=None,
    stat="count", width=.8, dodge="auto", gap=0, log_scale=None, native_scale=False,
    formatter=None, legend="auto", ax=None, **kwargs
):

    if x is None and y is not None:
        orient = "y"
        x = 1 if list(y) else None
    elif x is not None and y is None:
        orient = "x"
        y = 1 if list(x) else None
    elif x is not None and y is not None:
        raise TypeError("Cannot pass values for both `x` and `y`.")

    p = _CategoricalAggPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
        order=order,
        orient=orient,
        color=color,
        legend=legend,
    )

    if ax is None:
        ax = plt.gca()

    if p.plot_data.empty:
        return ax

    if dodge == "auto":
        # Needs to be before scale_categorical changes the coordinate series dtype
        dodge = p._dodge_needed()

    if p.var_types.get(p.orient) == "categorical" or not native_scale:
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(ax, log_scale=log_scale)

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    saturation = saturation if fill else 1
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm, saturation=saturation)
    color = _default_color(ax.bar, hue, color, kwargs, saturation)

    count_axis = {"x": "y", "y": "x"}[p.orient]
    if p.input_format == "wide":
        p.plot_data[count_axis] = 1

    _check_argument("stat", ["count", "percent", "probability", "proportion"], stat)
    p.variables[count_axis] = stat
    if stat != "count":
        denom = 100 if stat == "percent" else 1
        p.plot_data[count_axis] /= len(p.plot_data) / denom

    aggregator = EstimateAggregator("sum", errorbar=None)

    p.plot_bars(
        aggregator=aggregator,
        dodge=dodge,
        width=width,
        gap=gap,
        color=color,
        fill=fill,
        capsize=0,
        err_kws={},
        plot_kws=kwargs,
    )

    p._add_axis_labels(ax)
    p._adjust_cat_axis(ax, axis=p.orient)

    return ax


countplot.__doc__ = dedent("""\
    Show the counts of observations in each categorical bin using bars.

    A count plot can be thought of as a histogram across a categorical, instead
    of quantitative, variable. The basic API and options are identical to those
    for :func:`barplot`, so you can compare counts across nested variables.

    Note that :func:`histplot` function offers similar functionality with additional
    features (e.g. bar stacking), although its default behavior is somewhat different.

    {categorical_narrative}

    Parameters
    ----------
    {categorical_data}
    {input_params}
    {order_vars}
    {orient}
    {color}
    {palette}
    {saturation}
    {hue_norm}
    stat : {{'count', 'percent', 'proportion', 'probability'}}
        Statistic to compute; when not `'count'`, bar heights will be normalized so that
        they sum to 100 (for `'percent'`) or 1 (otherwise) across the plot.

        .. versionadded:: v0.13.0
    {width}
    {dodge}
    {log_scale}
    {native_scale}
    {formatter}
    {legend}
    {ax_in}
    kwargs : key, value mappings
        Other parameters are passed through to :class:`matplotlib.patches.Rectangle`.

    Returns
    -------
    {ax_out}

    See Also
    --------
    histplot : Bin and count observations with additional options.
    {barplot}
    {catplot}

    Examples
    --------
    .. include:: ../docstrings/countplot.rst

    """).format(**_categorical_docs)


def catplot(
    data=None, *, x=None, y=None, hue=None, row=None, col=None, kind="strip",
    estimator="mean", errorbar=("ci", 95), n_boot=1000, seed=None, units=None,
    weights=None, order=None, hue_order=None, row_order=None, col_order=None,
    col_wrap=None, height=5, aspect=1, log_scale=None, native_scale=False,
    formatter=None, orient=None, color=None, palette=None, hue_norm=None,
    legend="auto", legend_out=True, sharex=True, sharey=True,
    margin_titles=False, facet_kws=None, ci=deprecated, **kwargs
):

    # Check for attempt to plot onto specific axes and warn
    if "ax" in kwargs:
        msg = ("catplot is a figure-level function and does not accept "
               f"target axes. You may wish to try {kind}plot")
        warnings.warn(msg, UserWarning)
        kwargs.pop("ax")

    desaturated_kinds = ["bar", "count", "box", "violin", "boxen"]
    undodged_kinds = ["strip", "swarm", "point"]

    if kind in ["bar", "point", "count"]:
        Plotter = _CategoricalAggPlotter
    else:
        Plotter = _CategoricalPlotter

    if kind == "count":
        if x is None and y is not None:
            orient = "y"
            x = 1
        elif x is not None and y is None:
            orient = "x"
            y = 1
        elif x is not None and y is not None:
            raise ValueError("Cannot pass values for both `x` and `y`.")

    p = Plotter(
        data=data,
        variables=dict(
            x=x, y=y, hue=hue, row=row, col=col, units=units, weight=weights
        ),
        order=order,
        orient=orient,
        # Handle special backwards compatibility where pointplot originally
        # did *not* default to multi-colored unless a palette was specified.
        color="C0" if kind == "point" and palette is None and color is None else color,
        legend=legend,
    )

    for var in ["row", "col"]:
        # Handle faceting variables that lack name information
        if var in p.variables and p.variables[var] is None:
            p.variables[var] = f"_{var}_"

    # Adapt the plot_data dataframe for use with FacetGrid
    facet_data = p.plot_data.rename(columns=p.variables)
    facet_data = facet_data.loc[:, ~facet_data.columns.duplicated()]

    col_name = p.variables.get("col", None)
    row_name = p.variables.get("row", None)

    if facet_kws is None:
        facet_kws = {}

    g = FacetGrid(
        data=facet_data, row=row_name, col=col_name, col_wrap=col_wrap,
        row_order=row_order, col_order=col_order, sharex=sharex, sharey=sharey,
        legend_out=legend_out, margin_titles=margin_titles,
        height=height, aspect=aspect,
        **facet_kws,
    )

    # Capture this here because scale_categorical is going to insert a (null)
    # x variable even if it is empty. It's not clear whether that needs to
    # happen or if disabling that is the cleaner solution.
    has_xy_data = p.has_xy_data

    if not native_scale or p.var_types[p.orient] == "categorical":
        p.scale_categorical(p.orient, order=order, formatter=formatter)

    p._attach(g, log_scale=log_scale)

    if not has_xy_data:
        return g

    # Deprecations to remove in v0.14.0.
    hue_order = p._palette_without_hue_backcompat(palette, hue_order)
    palette, hue_order = p._hue_backcompat(color, palette, hue_order)

    # Othe deprecations
    errorbar = utils._deprecate_ci(errorbar, ci)

    saturation = kwargs.pop(
        "saturation",
        0.75 if kind in desaturated_kinds and kwargs.get("fill", True) else 1
    )
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm, saturation=saturation)

    # Set a default color
    # Otherwise each artist will be plotted separately and trip the color cycle
    if hue is None:
        color = "C0" if color is None else color
        if saturation < 1:
            color = desaturate(color, saturation)

    if kind in ["strip", "swarm"]:
        kwargs = normalize_kwargs(kwargs, mpl.collections.PathCollection)
        kwargs["edgecolor"] = p._complement_color(
            kwargs.pop("edgecolor", default), color, p._hue_map
        )

    width = kwargs.pop("width", 0.8)
    dodge = kwargs.pop("dodge", False if kind in undodged_kinds else "auto")
    if dodge == "auto":
        dodge = p._dodge_needed()

    if "weight" in p.plot_data:
        if kind not in ["bar", "point"]:
            msg = f"The `weights` parameter has no effect with kind={kind!r}."
            warnings.warn(msg, stacklevel=2)
        agg_cls = WeightedAggregator
    else:
        agg_cls = EstimateAggregator

    if kind == "strip":

        jitter = kwargs.pop("jitter", True)
        plot_kws = kwargs.copy()
        plot_kws.setdefault("zorder", 3)
        plot_kws.setdefault("linewidth", 0)
        if "s" not in plot_kws:
            plot_kws["s"] = plot_kws.pop("size", 5) ** 2

        p.plot_strips(
            jitter=jitter,
            dodge=dodge,
            color=color,
            plot_kws=plot_kws,
        )

    elif kind == "swarm":

        warn_thresh = kwargs.pop("warn_thresh", .05)
        plot_kws = kwargs.copy()
        plot_kws.setdefault("zorder", 3)
        if "s" not in plot_kws:
            plot_kws["s"] = plot_kws.pop("size", 5) ** 2

        if plot_kws.setdefault("linewidth", 0) is None:
            plot_kws["linewidth"] = np.sqrt(plot_kws["s"]) / 10

        p.plot_swarms(
            dodge=dodge,
            color=color,
            warn_thresh=warn_thresh,
            plot_kws=plot_kws,
        )

    elif kind == "box":

        plot_kws = kwargs.copy()
        gap = plot_kws.pop("gap", 0)
        fill = plot_kws.pop("fill", True)
        whis = plot_kws.pop("whis", 1.5)
        linewidth = plot_kws.pop("linewidth", None)
        fliersize = plot_kws.pop("fliersize", 5)
        linecolor = p._complement_color(
            plot_kws.pop("linecolor", "auto"), color, p._hue_map
        )

        p.plot_boxes(
            width=width,
            dodge=dodge,
            gap=gap,
            fill=fill,
            whis=whis,
            color=color,
            linecolor=linecolor,
            linewidth=linewidth,
            fliersize=fliersize,
            plot_kws=plot_kws,
        )

    elif kind == "violin":

        plot_kws = kwargs.copy()
        gap = plot_kws.pop("gap", 0)
        fill = plot_kws.pop("fill", True)
        split = plot_kws.pop("split", False)
        inner = plot_kws.pop("inner", "box")
        density_norm = plot_kws.pop("density_norm", "area")
        common_norm = plot_kws.pop("common_norm", False)

        scale = plot_kws.pop("scale", deprecated)
        scale_hue = plot_kws.pop("scale_hue", deprecated)
        density_norm, common_norm = p._violin_scale_backcompat(
            scale, scale_hue, density_norm, common_norm,
        )

        bw_method = p._violin_bw_backcompat(
            plot_kws.pop("bw", deprecated), plot_kws.pop("bw_method", "scott")
        )
        kde_kws = dict(
            cut=plot_kws.pop("cut", 2),
            gridsize=plot_kws.pop("gridsize", 100),
            bw_adjust=plot_kws.pop("bw_adjust", 1),
            bw_method=bw_method,
        )

        inner_kws = plot_kws.pop("inner_kws", {}).copy()
        linewidth = plot_kws.pop("linewidth", None)
        linecolor = plot_kws.pop("linecolor", "auto")
        linecolor = p._complement_color(linecolor, color, p._hue_map)

        p.plot_violins(
            width=width,
            dodge=dodge,
            gap=gap,
            split=split,
            color=color,
            fill=fill,
            linecolor=linecolor,
            linewidth=linewidth,
            inner=inner,
            density_norm=density_norm,
            common_norm=common_norm,
            kde_kws=kde_kws,
            inner_kws=inner_kws,
            plot_kws=plot_kws,
        )

    elif kind == "boxen":

        plot_kws = kwargs.copy()
        gap = plot_kws.pop("gap", 0)
        fill = plot_kws.pop("fill", True)
        linecolor = plot_kws.pop("linecolor", "auto")
        linewidth = plot_kws.pop("linewidth", None)
        k_depth = plot_kws.pop("k_depth", "tukey")
        width_method = plot_kws.pop("width_method", "exponential")
        outlier_prop = plot_kws.pop("outlier_prop", 0.007)
        trust_alpha = plot_kws.pop("trust_alpha", 0.05)
        showfliers = plot_kws.pop("showfliers", True)
        box_kws = plot_kws.pop("box_kws", {})
        flier_kws = plot_kws.pop("flier_kws", {})
        line_kws = plot_kws.pop("line_kws", {})
        if "scale" in plot_kws:
            width_method = p._boxen_scale_backcompat(
                plot_kws["scale"], width_method
            )
        linecolor = p._complement_color(linecolor, color, p._hue_map)

        p.plot_boxens(
            width=width,
            dodge=dodge,
            gap=gap,
            fill=fill,
            color=color,
            linecolor=linecolor,
            linewidth=linewidth,
            width_method=width_method,
            k_depth=k_depth,
            outlier_prop=outlier_prop,
            trust_alpha=trust_alpha,
            showfliers=showfliers,
            box_kws=box_kws,
            flier_kws=flier_kws,
            line_kws=line_kws,
            plot_kws=plot_kws,
        )

    elif kind == "point":

        aggregator = agg_cls(estimator, errorbar, n_boot=n_boot, seed=seed)

        markers = kwargs.pop("markers", default)
        linestyles = kwargs.pop("linestyles", default)

        # Deprecations to remove in v0.15.0.
        # TODO Uncomment when removing deprecation backcompat
        # capsize = kwargs.pop("capsize", 0)
        # err_kws = normalize_kwargs(kwargs.pop("err_kws", {}), mpl.lines.Line2D)
        p._point_kwargs_backcompat(
            kwargs.pop("scale", deprecated),
            kwargs.pop("join", deprecated),
            kwargs
        )
        err_kws, capsize = p._err_kws_backcompat(
            normalize_kwargs(kwargs.pop("err_kws", {}), mpl.lines.Line2D),
            None,
            errwidth=kwargs.pop("errwidth", deprecated),
            capsize=kwargs.pop("capsize", 0),
        )

        p.plot_points(
            aggregator=aggregator,
            markers=markers,
            linestyles=linestyles,
            dodge=dodge,
            color=color,
            capsize=capsize,
            err_kws=err_kws,
            plot_kws=kwargs,
        )

    elif kind == "bar":

        aggregator = agg_cls(estimator, errorbar, n_boot=n_boot, seed=seed)

        err_kws, capsize = p._err_kws_backcompat(
            normalize_kwargs(kwargs.pop("err_kws", {}), mpl.lines.Line2D),
            errcolor=kwargs.pop("errcolor", deprecated),
            errwidth=kwargs.pop("errwidth", deprecated),
            capsize=kwargs.pop("capsize", 0),
        )
        gap = kwargs.pop("gap", 0)
        fill = kwargs.pop("fill", True)

        p.plot_bars(
            aggregator=aggregator,
            dodge=dodge,
            width=width,
            gap=gap,
            color=color,
            fill=fill,
            capsize=capsize,
            err_kws=err_kws,
            plot_kws=kwargs,
        )

    elif kind == "count":

        aggregator = EstimateAggregator("sum", errorbar=None)

        count_axis = {"x": "y", "y": "x"}[p.orient]
        p.plot_data[count_axis] = 1

        stat_options = ["count", "percent", "probability", "proportion"]
        stat = _check_argument("stat", stat_options, kwargs.pop("stat", "count"))
        p.variables[count_axis] = stat
        if stat != "count":
            denom = 100 if stat == "percent" else 1
            p.plot_data[count_axis] /= len(p.plot_data) / denom

        gap = kwargs.pop("gap", 0)
        fill = kwargs.pop("fill", True)

        p.plot_bars(
            aggregator=aggregator,
            dodge=dodge,
            width=width,
            gap=gap,
            color=color,
            fill=fill,
            capsize=0,
            err_kws={},
            plot_kws=kwargs,
        )

    else:
        msg = (
            f"Invalid `kind`: {kind!r}. Options are 'strip', 'swarm', "
            "'box', 'boxen', 'violin', 'bar', 'count', and 'point'."
        )
        raise ValueError(msg)

    for ax in g.axes.flat:
        p._adjust_cat_axis(ax, axis=p.orient)

    g.set_axis_labels(p.variables.get("x"), p.variables.get("y"))
    g.set_titles()
    g.tight_layout()

    for ax in g.axes.flat:
        g._update_legend_data(ax)
        ax.legend_ = None

    if legend == "auto":
        show_legend = not p._redundant_hue and p.input_format != "wide"
    else:
        show_legend = bool(legend)
    if show_legend:
        g.add_legend(title=p.variables.get("hue"), label_order=hue_order)

    if data is not None:
        # Replace the dataframe on the FacetGrid for any subsequent maps
        g.data = data

    return g


catplot.__doc__ = dedent("""\
    Figure-level interface for drawing categorical plots onto a FacetGrid.

    This function provides access to several axes-level functions that
    show the relationship between a numerical and one or more categorical
    variables using one of several visual representations. The `kind`
    parameter selects the underlying axes-level function to use.

    Categorical scatterplots:

    - :func:`stripplot` (with `kind="strip"`; the default)
    - :func:`swarmplot` (with `kind="swarm"`)

    Categorical distribution plots:

    - :func:`boxplot` (with `kind="box"`)
    - :func:`violinplot` (with `kind="violin"`)
    - :func:`boxenplot` (with `kind="boxen"`)

    Categorical estimate plots:

    - :func:`pointplot` (with `kind="point"`)
    - :func:`barplot` (with `kind="bar"`)
    - :func:`countplot` (with `kind="count"`)

    Extra keyword arguments are passed to the underlying function, so you
    should refer to the documentation for each to see kind-specific options.

    {categorical_narrative}

    After plotting, the :class:`FacetGrid` with the plot is returned and can
    be used directly to tweak supporting plot details or add other layers.

    Parameters
    ----------
    {categorical_data}
    {input_params}
    row, col : names of variables in `data` or vector data
        Categorical variables that will determine the faceting of the grid.
    kind : str
        The kind of plot to draw, corresponds to the name of a categorical
        axes-level plotting function. Options are: "strip", "swarm", "box", "violin",
        "boxen", "point", "bar", or "count".
    {stat_api_params}
    {order_vars}
    row_order, col_order : lists of strings
        Order to organize the rows and/or columns of the grid in; otherwise the
        orders are inferred from the data objects.
    {col_wrap}
    {height}
    {aspect}
    {native_scale}
    {formatter}
    {orient}
    {color}
    {palette}
    {hue_norm}
    {legend}
    {legend_out}
    {share_xy}
    {margin_titles}
    facet_kws : dict
        Dictionary of other keyword arguments to pass to :class:`FacetGrid`.
    kwargs : key, value pairings
        Other keyword arguments are passed through to the underlying plotting
        function.

    Returns
    -------
    :class:`FacetGrid`
        Returns the :class:`FacetGrid` object with the plot on it for further
        tweaking.

    Examples
    --------
    .. include:: ../docstrings/catplot.rst

    """).format(**_categorical_docs)


class Beeswarm:
    """Modifies a scatterplot artist to show a beeswarm plot."""
    def __init__(self, orient="x", width=0.8, warn_thresh=.05):

        self.orient = orient
        self.width = width
        self.warn_thresh = warn_thresh

    def __call__(self, points, center):
        """Swarm `points`, a PathCollection, around the `center` position."""
        # Convert from point size (area) to diameter

        ax = points.axes
        dpi = ax.figure.dpi

        # Get the original positions of the points
        orig_xy_data = points.get_offsets()

        # Reset the categorical positions to the center line
        cat_idx = 1 if self.orient == "y" else 0
        orig_xy_data[:, cat_idx] = center

        # Transform the data coordinates to point coordinates.
        # We'll figure out the swarm positions in the latter
        # and then convert back to data coordinates and replot
        orig_x_data, orig_y_data = orig_xy_data.T
        orig_xy = ax.transData.transform(orig_xy_data)

        # Order the variables so that x is the categorical axis
        if self.orient == "y":
            orig_xy = orig_xy[:, [1, 0]]

        # Add a column with each point's radius
        sizes = points.get_sizes()
        if sizes.size == 1:
            sizes = np.repeat(sizes, orig_xy.shape[0])
        edge = points.get_linewidth().item()
        radii = (np.sqrt(sizes) + edge) / 2 * (dpi / 72)
        orig_xy = np.c_[orig_xy, radii]

        # Sort along the value axis to facilitate the beeswarm
        sorter = np.argsort(orig_xy[:, 1])
        orig_xyr = orig_xy[sorter]

        # Adjust points along the categorical axis to prevent overlaps
        new_xyr = np.empty_like(orig_xyr)
        new_xyr[sorter] = self.beeswarm(orig_xyr)

        # Transform the point coordinates back to data coordinates
        if self.orient == "y":
            new_xy = new_xyr[:, [1, 0]]
        else:
            new_xy = new_xyr[:, :2]
        new_x_data, new_y_data = ax.transData.inverted().transform(new_xy).T

        # Add gutters
        t_fwd, t_inv = _get_transform_functions(ax, self.orient)
        if self.orient == "y":
            self.add_gutters(new_y_data, center, t_fwd, t_inv)
        else:
            self.add_gutters(new_x_data, center, t_fwd, t_inv)

        # Reposition the points so they do not overlap
        if self.orient == "y":
            points.set_offsets(np.c_[orig_x_data, new_y_data])
        else:
            points.set_offsets(np.c_[new_x_data, orig_y_data])

    def beeswarm(self, orig_xyr):
        """Adjust x position of points to avoid overlaps."""
        # In this method, `x` is always the categorical axis
        # Center of the swarm, in point coordinates
        midline = orig_xyr[0, 0]

        # Start the swarm with the first point
        swarm = np.atleast_2d(orig_xyr[0])

        # Loop over the remaining points
        for xyr_i in orig_xyr[1:]:

            # Find the points in the swarm that could possibly
            # overlap with the point we are currently placing
            neighbors = self.could_overlap(xyr_i, swarm)

            # Find positions that would be valid individually
            # with respect to each of the swarm neighbors
            candidates = self.position_candidates(xyr_i, neighbors)

            # Sort candidates by their centrality
            offsets = np.abs(candidates[:, 0] - midline)
            candidates = candidates[np.argsort(offsets)]

            # Find the first candidate that does not overlap any neighbors
            new_xyr_i = self.first_non_overlapping_candidate(candidates, neighbors)

            # Place it into the swarm
            swarm = np.vstack([swarm, new_xyr_i])

        return swarm

    def could_overlap(self, xyr_i, swarm):
        """Return a list of all swarm points that could overlap with target."""
        # Because we work backwards through the swarm and can short-circuit,
        # the for-loop is faster than vectorization
        _, y_i, r_i = xyr_i
        neighbors = []
        for xyr_j in reversed(swarm):
            _, y_j, r_j = xyr_j
            if (y_i - y_j) < (r_i + r_j):
                neighbors.append(xyr_j)
            else:
                break
        return np.array(neighbors)[::-1]

    def position_candidates(self, xyr_i, neighbors):
        """Return a list of coordinates that might be valid by adjusting x."""
        candidates = [xyr_i]
        x_i, y_i, r_i = xyr_i
        left_first = True
        for x_j, y_j, r_j in neighbors:
            dy = y_i - y_j
            dx = np.sqrt(max((r_i + r_j) ** 2 - dy ** 2, 0)) * 1.05
            cl, cr = (x_j - dx, y_i, r_i), (x_j + dx, y_i, r_i)
            if left_first:
                new_candidates = [cl, cr]
            else:
                new_candidates = [cr, cl]
            candidates.extend(new_candidates)
            left_first = not left_first
        return np.array(candidates)

    def first_non_overlapping_candidate(self, candidates, neighbors):
        """Find the first candidate that does not overlap with the swarm."""

        # If we have no neighbors, all candidates are good.
        if len(neighbors) == 0:
            return candidates[0]

        neighbors_x = neighbors[:, 0]
        neighbors_y = neighbors[:, 1]
        neighbors_r = neighbors[:, 2]

        for xyr_i in candidates:

            x_i, y_i, r_i = xyr_i

            dx = neighbors_x - x_i
            dy = neighbors_y - y_i
            sq_distances = np.square(dx) + np.square(dy)

            sep_needed = np.square(neighbors_r + r_i)

            # Good candidate does not overlap any of neighbors which means that
            # squared distance between candidate and any of the neighbors has
            # to be at least square of the summed radii
            good_candidate = np.all(sq_distances >= sep_needed)

            if good_candidate:
                return xyr_i

        raise RuntimeError(
            "No non-overlapping candidates found. This should not happen."
        )

    def add_gutters(self, points, center, trans_fwd, trans_inv):
        """Stop points from extending beyond their territory."""
        half_width = self.width / 2
        low_gutter = trans_inv(trans_fwd(center) - half_width)
        off_low = points < low_gutter
        if off_low.any():
            points[off_low] = low_gutter
        high_gutter = trans_inv(trans_fwd(center) + half_width)
        off_high = points > high_gutter
        if off_high.any():
            points[off_high] = high_gutter

        gutter_prop = (off_high + off_low).sum() / len(points)
        if gutter_prop > self.warn_thresh:
            msg = (
                "{:.1%} of the points cannot be placed; you may want "
                "to decrease the size of the markers or use stripplot."
            ).format(gutter_prop)
            warnings.warn(msg, UserWarning)

        return points


BoxPlotArtists = namedtuple("BoxPlotArtists", "box median whiskers caps fliers mean")


class BoxPlotContainer:

    def __init__(self, artist_dict):

        self.boxes = artist_dict["boxes"]
        self.medians = artist_dict["medians"]
        self.whiskers = artist_dict["whiskers"]
        self.caps = artist_dict["caps"]
        self.fliers = artist_dict["fliers"]
        self.means = artist_dict["means"]

        self._label = None
        self._children = [
            *self.boxes,
            *self.medians,
            *self.whiskers,
            *self.caps,
            *self.fliers,
            *self.means,
        ]

    def __repr__(self):
        return f"<BoxPlotContainer object with {len(self.boxes)} boxes>"

    def __getitem__(self, idx):
        pair_slice = slice(2 * idx, 2 * idx + 2)
        return BoxPlotArtists(
            self.boxes[idx] if self.boxes else [],
            self.medians[idx] if self.medians else [],
            self.whiskers[pair_slice] if self.whiskers else [],
            self.caps[pair_slice] if self.caps else [],
            self.fliers[idx] if self.fliers else [],
            self.means[idx]if self.means else [],
        )

    def __iter__(self):
        yield from (self[i] for i in range(len(self.boxes)))

    def get_label(self):
        return self._label

    def set_label(self, value):
        self._label = value

    def get_children(self):
        return self._children

    def remove(self):
        for child in self._children:
            child.remove()
