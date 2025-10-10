"""Plotting functions for visualizing distributions."""
from numbers import Number
from functools import partial
import math
import textwrap
import warnings

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.transforms as tx
from matplotlib.cbook import normalize_kwargs
from matplotlib.colors import to_rgba
from matplotlib.collections import LineCollection

from ._base import VectorPlotter

# We have moved univariate histogram computation over to the new Hist class,
# but still use the older Histogram for bivariate computation.
from ._statistics import ECDF, Histogram, KDE
from ._stats.counting import Hist

from .axisgrid import (
    FacetGrid,
    _facet_docs,
)
from .utils import (
    remove_na,
    _get_transform_functions,
    _kde_support,
    _check_argument,
    _assign_default_kwargs,
    _default_color,
)
from .palettes import color_palette
from .external import husl
from .external.kde import gaussian_kde
from ._docstrings import (
    DocstringComponents,
    _core_docs,
)


__all__ = ["displot", "histplot", "kdeplot", "ecdfplot", "rugplot", "distplot"]

# ==================================================================================== #
# Module documentation
# ==================================================================================== #

_dist_params = dict(

    multiple="""
multiple : {{"layer", "stack", "fill"}}
    Method for drawing multiple elements when semantic mapping creates subsets.
    Only relevant with univariate data.
    """,
    log_scale="""
log_scale : bool or number, or pair of bools or numbers
    Set axis scale(s) to log. A single value sets the data axis for any numeric
    axes in the plot. A pair of values sets each axis independently.
    Numeric values are interpreted as the desired base (default 10).
    When `None` or `False`, seaborn defers to the existing Axes scale.
    """,
    legend="""
legend : bool
    If False, suppress the legend for semantic variables.
    """,
    cbar="""
cbar : bool
    If True, add a colorbar to annotate the color mapping in a bivariate plot.
    Note: Does not currently support plots with a ``hue`` variable well.
    """,
    cbar_ax="""
cbar_ax : :class:`matplotlib.axes.Axes`
    Pre-existing axes for the colorbar.
    """,
    cbar_kws="""
cbar_kws : dict
    Additional parameters passed to :meth:`matplotlib.figure.Figure.colorbar`.
    """,
)

_param_docs = DocstringComponents.from_nested_components(
    core=_core_docs["params"],
    facets=DocstringComponents(_facet_docs),
    dist=DocstringComponents(_dist_params),
    kde=DocstringComponents.from_function_params(KDE.__init__),
    hist=DocstringComponents.from_function_params(Histogram.__init__),
    ecdf=DocstringComponents.from_function_params(ECDF.__init__),
)


# ==================================================================================== #
# Internal API
# ==================================================================================== #


class _DistributionPlotter(VectorPlotter):

    wide_structure = {"x": "@values", "hue": "@columns"}
    flat_structure = {"x": "@values"}

    def __init__(
        self,
        data=None,
        variables={},
    ):

        super().__init__(data=data, variables=variables)

    @property
    def univariate(self):
        """Return True if only x or y are used."""
        # TODO this could go down to core, but putting it here now.
        # We'd want to be conceptually clear that univariate only applies
        # to x/y and not to other semantics, which can exist.
        # We haven't settled on a good conceptual name for x/y.
        return bool({"x", "y"} - set(self.variables))

    @property
    def data_variable(self):
        """Return the variable with data for univariate plots."""
        # TODO This could also be in core, but it should have a better name.
        if not self.univariate:
            raise AttributeError("This is not a univariate plot")
        return {"x", "y"}.intersection(self.variables).pop()

    @property
    def has_xy_data(self):
        """Return True at least one of x or y is defined."""
        # TODO see above points about where this should go
        return bool({"x", "y"} & set(self.variables))

    def _add_legend(
        self,
        ax_obj, artist, fill, element, multiple, alpha, artist_kws, legend_kws,
    ):
        """Add artists that reflect semantic mappings and put then in a legend."""
        # TODO note that this doesn't handle numeric mappings like the relational plots
        handles = []
        labels = []
        for level in self._hue_map.levels:
            color = self._hue_map(level)

            kws = self._artist_kws(
                artist_kws, fill, element, multiple, color, alpha
            )

            # color gets added to the kws to workaround an issue with barplot's color
            # cycle integration but it causes problems in this context where we are
            # setting artist properties directly, so pop it off here
            if "facecolor" in kws:
                kws.pop("color", None)

            handles.append(artist(**kws))
            labels.append(level)

        if isinstance(ax_obj, mpl.axes.Axes):
            ax_obj.legend(handles, labels, title=self.variables["hue"], **legend_kws)
        else:  # i.e. a FacetGrid. TODO make this better
            legend_data = dict(zip(labels, handles))
            ax_obj.add_legend(
                legend_data,
                title=self.variables["hue"],
                label_order=self.var_levels["hue"],
                **legend_kws
            )

    def _artist_kws(self, kws, fill, element, multiple, color, alpha):
        """Handle differences between artists in filled/unfilled plots."""
        kws = kws.copy()
        if fill:
            kws = normalize_kwargs(kws, mpl.collections.PolyCollection)
            kws.setdefault("facecolor", to_rgba(color, alpha))

            if element == "bars":
                # Make bar() interface with property cycle correctly
                # https://github.com/matplotlib/matplotlib/issues/19385
                kws["color"] = "none"

            if multiple in ["stack", "fill"] or element == "bars":
                kws.setdefault("edgecolor", mpl.rcParams["patch.edgecolor"])
            else:
                kws.setdefault("edgecolor", to_rgba(color, 1))
        elif element == "bars":
            kws["facecolor"] = "none"
            kws["edgecolor"] = to_rgba(color, alpha)
        else:
            kws["color"] = to_rgba(color, alpha)
        return kws

    def _quantile_to_level(self, data, quantile):
        """Return data levels corresponding to quantile cuts of mass."""
        isoprop = np.asarray(quantile)
        values = np.ravel(data)
        sorted_values = np.sort(values)[::-1]
        normalized_values = np.cumsum(sorted_values) / values.sum()
        idx = np.searchsorted(normalized_values, 1 - isoprop)
        levels = np.take(sorted_values, idx, mode="clip")
        return levels

    def _cmap_from_color(self, color):
        """Return a sequential colormap given a color seed."""
        # Like so much else here, this is broadly useful, but keeping it
        # in this class to signify that I haven't thought overly hard about it...
        r, g, b, _ = to_rgba(color)
        h, s, _ = husl.rgb_to_husl(r, g, b)
        xx = np.linspace(-1, 1, int(1.15 * 256))[:256]
        ramp = np.zeros((256, 3))
        ramp[:, 0] = h
        ramp[:, 1] = s * np.cos(xx)
        ramp[:, 2] = np.linspace(35, 80, 256)
        colors = np.clip([husl.husl_to_rgb(*hsl) for hsl in ramp], 0, 1)
        return mpl.colors.ListedColormap(colors[::-1])

    def _default_discrete(self):
        """Find default values for discrete hist estimation based on variable type."""
        if self.univariate:
            discrete = self.var_types[self.data_variable] == "categorical"
        else:
            discrete_x = self.var_types["x"] == "categorical"
            discrete_y = self.var_types["y"] == "categorical"
            discrete = discrete_x, discrete_y
        return discrete

    def _resolve_multiple(self, curves, multiple):
        """Modify the density data structure to handle multiple densities."""

        # Default baselines have all densities starting at 0
        baselines = {k: np.zeros_like(v) for k, v in curves.items()}

        # TODO we should have some central clearinghouse for checking if any
        # "grouping" (terminnology?) semantics have been assigned
        if "hue" not in self.variables:
            return curves, baselines

        if multiple in ("stack", "fill"):

            # Setting stack or fill means that the curves share a
            # support grid / set of bin edges, so we can make a dataframe
            # Reverse the column order to plot from top to bottom
            curves = pd.DataFrame(curves).iloc[:, ::-1]

            # Find column groups that are nested within col/row variables
            column_groups = {}
            for i, keyd in enumerate(map(dict, curves.columns)):
                facet_key = keyd.get("col", None), keyd.get("row", None)
                column_groups.setdefault(facet_key, [])
                column_groups[facet_key].append(i)

            baselines = curves.copy()

            for col_idxs in column_groups.values():
                cols = curves.columns[col_idxs]

                norm_constant = curves[cols].sum(axis="columns")

                # Take the cumulative sum to stack
                curves[cols] = curves[cols].cumsum(axis="columns")

                # Normalize by row sum to fill
                if multiple == "fill":
                    curves[cols] = curves[cols].div(norm_constant, axis="index")

                # Define where each segment starts
                baselines[cols] = curves[cols].shift(1, axis=1).fillna(0)

        if multiple == "dodge":

            # Account for the unique semantic (non-faceting) levels
            # This will require rethiniking if we add other semantics!
            hue_levels = self.var_levels["hue"]
            n = len(hue_levels)
            f_fwd, f_inv = self._get_scale_transforms(self.data_variable)
            for key in curves:

                level = dict(key)["hue"]
                hist = curves[key].reset_index(name="heights")
                level_idx = hue_levels.index(level)

                a = f_fwd(hist["edges"])
                b = f_fwd(hist["edges"] + hist["widths"])
                w = (b - a) / n
                new_min = f_inv(a + level_idx * w)
                new_max = f_inv(a + (level_idx + 1) * w)
                hist["widths"] = new_max - new_min
                hist["edges"] = new_min

                curves[key] = hist.set_index(["edges", "widths"])["heights"]

        return curves, baselines

    # -------------------------------------------------------------------------------- #
    # Computation
    # -------------------------------------------------------------------------------- #

    def _compute_univariate_density(
        self,
        data_variable,
        common_norm,
        common_grid,
        estimate_kws,
        warn_singular=True,
    ):

        # Initialize the estimator object
        estimator = KDE(**estimate_kws)

        if set(self.variables) - {"x", "y"}:
            if common_grid:
                all_observations = self.comp_data.dropna()
                estimator.define_support(all_observations[data_variable])
        else:
            common_norm = False

        all_data = self.plot_data.dropna()
        if common_norm and "weights" in all_data:
            whole_weight = all_data["weights"].sum()
        else:
            whole_weight = len(all_data)

        densities = {}

        for sub_vars, sub_data in self.iter_data("hue", from_comp_data=True):

            # Extract the data points from this sub set and remove nulls
            observations = sub_data[data_variable]

            # Extract the weights for this subset of observations
            if "weights" in self.variables:
                weights = sub_data["weights"]
                part_weight = weights.sum()
            else:
                weights = None
                part_weight = len(sub_data)

            # Estimate the density of observations at this level
            variance = np.nan_to_num(observations.var())
            singular = len(observations) < 2 or math.isclose(variance, 0)
            try:
                if not singular:
                    # Convoluted approach needed because numerical failures
                    # can manifest in a few different ways.
                    density, support = estimator(observations, weights=weights)
            except np.linalg.LinAlgError:
                singular = True

            if singular:
                msg = (
                    "Dataset has 0 variance; skipping density estimate. "
                    "Pass `warn_singular=False` to disable this warning."
                )
                if warn_singular:
                    warnings.warn(msg, UserWarning, stacklevel=4)
                continue

            # Invert the scaling of the support points
            _, f_inv = self._get_scale_transforms(self.data_variable)
            support = f_inv(support)

            # Apply a scaling factor so that the integral over all subsets is 1
            if common_norm:
                density *= part_weight / whole_weight

            # Store the density for this level
            key = tuple(sub_vars.items())
            densities[key] = pd.Series(density, index=support)

        return densities

    # -------------------------------------------------------------------------------- #
    # Plotting
    # -------------------------------------------------------------------------------- #

    def plot_univariate_histogram(
        self,
        multiple,
        element,
        fill,
        common_norm,
        common_bins,
        shrink,
        kde,
        kde_kws,
        color,
        legend,
        line_kws,
        estimate_kws,
        **plot_kws,
    ):

        # -- Default keyword dicts
        kde_kws = {} if kde_kws is None else kde_kws.copy()
        line_kws = {} if line_kws is None else line_kws.copy()
        estimate_kws = {} if estimate_kws is None else estimate_kws.copy()

        # --  Input checking
        _check_argument("multiple", ["layer", "stack", "fill", "dodge"], multiple)
        _check_argument("element", ["bars", "step", "poly"], element)

        auto_bins_with_weights = (
            "weights" in self.variables
            and estimate_kws["bins"] == "auto"
            and estimate_kws["binwidth"] is None
            and not estimate_kws["discrete"]
        )
        if auto_bins_with_weights:
            msg = (
                "`bins` cannot be 'auto' when using weights. "
                "Setting `bins=10`, but you will likely want to adjust."
            )
            warnings.warn(msg, UserWarning)
            estimate_kws["bins"] = 10

        # Simplify downstream code if we are not normalizing
        if estimate_kws["stat"] == "count":
            common_norm = False

        orient = self.data_variable

        # Now initialize the Histogram estimator
        estimator = Hist(**estimate_kws)
        histograms = {}

        # Do pre-compute housekeeping related to multiple groups
        all_data = self.comp_data.dropna()
        all_weights = all_data.get("weights", None)

        multiple_histograms = set(self.variables) - {"x", "y"}
        if multiple_histograms:
            if common_bins:
                bin_kws = estimator._define_bin_params(all_data, orient, None)
        else:
            common_norm = False

        if common_norm and all_weights is not None:
            whole_weight = all_weights.sum()
        else:
            whole_weight = len(all_data)

        # Estimate the smoothed kernel densities, for use later
        if kde:
            # TODO alternatively, clip at min/max bins?
            kde_kws.setdefault("cut", 0)
            kde_kws["cumulative"] = estimate_kws["cumulative"]
            densities = self._compute_univariate_density(
                self.data_variable,
                common_norm,
                common_bins,
                kde_kws,
                warn_singular=False,
            )

        # First pass through the data to compute the histograms
        for sub_vars, sub_data in self.iter_data("hue", from_comp_data=True):

            # Prepare the relevant data
            key = tuple(sub_vars.items())
            orient = self.data_variable

            if "weights" in self.variables:
                sub_data["weight"] = sub_data.pop("weights")
                part_weight = sub_data["weight"].sum()
            else:
                part_weight = len(sub_data)

            # Do the histogram computation
            if not (multiple_histograms and common_bins):
                bin_kws = estimator._define_bin_params(sub_data, orient, None)
            res = estimator._normalize(estimator._eval(sub_data, orient, bin_kws))
            heights = res[estimator.stat].to_numpy()
            widths = res["space"].to_numpy()
            edges = res[orient].to_numpy() - widths / 2

            # Rescale the smoothed curve to match the histogram
            if kde and key in densities:
                density = densities[key]
                if estimator.cumulative:
                    hist_norm = heights.max()
                else:
                    hist_norm = (heights * widths).sum()
                densities[key] *= hist_norm

            # Convert edges back to original units for plotting
            ax = self._get_axes(sub_vars)
            _, inv = _get_transform_functions(ax, self.data_variable)
            widths = inv(edges + widths) - inv(edges)
            edges = inv(edges)

            # Pack the histogram data and metadata together
            edges = edges + (1 - shrink) / 2 * widths
            widths *= shrink
            index = pd.MultiIndex.from_arrays([
                pd.Index(edges, name="edges"),
                pd.Index(widths, name="widths"),
            ])
            hist = pd.Series(heights, index=index, name="heights")

            # Apply scaling to normalize across groups
            if common_norm:
                hist *= part_weight / whole_weight

            # Store the finalized histogram data for future plotting
            histograms[key] = hist

        # Modify the histogram and density data to resolve multiple groups
        histograms, baselines = self._resolve_multiple(histograms, multiple)
        if kde:
            densities, _ = self._resolve_multiple(
                densities, None if multiple == "dodge" else multiple
            )

        # Set autoscaling-related meta
        sticky_stat = (0, 1) if multiple == "fill" else (0, np.inf)
        if multiple == "fill":
            # Filled plots should not have any margins
            bin_vals = histograms.index.to_frame()
            edges = bin_vals["edges"]
            widths = bin_vals["widths"]
            sticky_data = (
                edges.min(),
                edges.max() + widths.loc[edges.idxmax()]
            )
        else:
            sticky_data = []

        # --- Handle default visual attributes

        # Note: default linewidth is determined after plotting

        # Default alpha should depend on other parameters
        if fill:
            # Note: will need to account for other grouping semantics if added
            if "hue" in self.variables and multiple == "layer":
                default_alpha = .5 if element == "bars" else .25
            elif kde:
                default_alpha = .5
            else:
                default_alpha = .75
        else:
            default_alpha = 1
        alpha = plot_kws.pop("alpha", default_alpha)  # TODO make parameter?

        hist_artists = []

        # Go back through the dataset and draw the plots
        for sub_vars, _ in self.iter_data("hue", reverse=True):

            key = tuple(sub_vars.items())
            hist = histograms[key].rename("heights").reset_index()
            bottom = np.asarray(baselines[key])

            ax = self._get_axes(sub_vars)

            # Define the matplotlib attributes that depend on semantic mapping
            if "hue" in self.variables:
                sub_color = self._hue_map(sub_vars["hue"])
            else:
                sub_color = color

            artist_kws = self._artist_kws(
                plot_kws, fill, element, multiple, sub_color, alpha
            )

            if element == "bars":

                # Use matplotlib bar plotting

                plot_func = ax.bar if self.data_variable == "x" else ax.barh
                artists = plot_func(
                    hist["edges"],
                    hist["heights"] - bottom,
                    hist["widths"],
                    bottom,
                    align="edge",
                    **artist_kws,
                )

                for bar in artists:
                    if self.data_variable == "x":
                        bar.sticky_edges.x[:] = sticky_data
                        bar.sticky_edges.y[:] = sticky_stat
                    else:
                        bar.sticky_edges.x[:] = sticky_stat
                        bar.sticky_edges.y[:] = sticky_data

                hist_artists.extend(artists)

            else:

                # Use either fill_between or plot to draw hull of histogram
                if element == "step":

                    final = hist.iloc[-1]
                    x = np.append(hist["edges"], final["edges"] + final["widths"])
                    y = np.append(hist["heights"], final["heights"])
                    b = np.append(bottom, bottom[-1])

                    if self.data_variable == "x":
                        step = "post"
                        drawstyle = "steps-post"
                    else:
                        step = "post"  # fillbetweenx handles mapping internally
                        drawstyle = "steps-pre"

                elif element == "poly":

                    x = hist["edges"] + hist["widths"] / 2
                    y = hist["heights"]
                    b = bottom

                    step = None
                    drawstyle = None

                if self.data_variable == "x":
                    if fill:
                        artist = ax.fill_between(x, b, y, step=step, **artist_kws)
                    else:
                        artist, = ax.plot(x, y, drawstyle=drawstyle, **artist_kws)
                    artist.sticky_edges.x[:] = sticky_data
                    artist.sticky_edges.y[:] = sticky_stat
                else:
                    if fill:
                        artist = ax.fill_betweenx(x, b, y, step=step, **artist_kws)
                    else:
                        artist, = ax.plot(y, x, drawstyle=drawstyle, **artist_kws)
                    artist.sticky_edges.x[:] = sticky_stat
                    artist.sticky_edges.y[:] = sticky_data

                hist_artists.append(artist)

            if kde:

                # Add in the density curves

                try:
                    density = densities[key]
                except KeyError:
                    continue
                support = density.index

                if "x" in self.variables:
                    line_args = support, density
                    sticky_x, sticky_y = None, (0, np.inf)
                else:
                    line_args = density, support
                    sticky_x, sticky_y = (0, np.inf), None

                line_kws["color"] = to_rgba(sub_color, 1)
                line, = ax.plot(
                    *line_args, **line_kws,
                )

                if sticky_x is not None:
                    line.sticky_edges.x[:] = sticky_x
                if sticky_y is not None:
                    line.sticky_edges.y[:] = sticky_y

        if element == "bars" and "linewidth" not in plot_kws:

            # Now we handle linewidth, which depends on the scaling of the plot

            # We will base everything on the minimum bin width
            hist_metadata = pd.concat([
                # Use .items for generality over dict or df
                h.index.to_frame() for _, h in histograms.items()
            ]).reset_index(drop=True)
            thin_bar_idx = hist_metadata["widths"].idxmin()
            binwidth = hist_metadata.loc[thin_bar_idx, "widths"]
            left_edge = hist_metadata.loc[thin_bar_idx, "edges"]

            # Set initial value
            default_linewidth = math.inf

            # Loop through subsets based only on facet variables
            for sub_vars, _ in self.iter_data():

                ax = self._get_axes(sub_vars)

                # Needed in some cases to get valid transforms.
                # Innocuous in other cases?
                ax.autoscale_view()

                # Convert binwidth from data coordinates to pixels
                pts_x, pts_y = 72 / ax.figure.dpi * abs(
                    ax.transData.transform([left_edge + binwidth] * 2)
                    - ax.transData.transform([left_edge] * 2)
                )
                if self.data_variable == "x":
                    binwidth_points = pts_x
                else:
                    binwidth_points = pts_y

                # The relative size of the lines depends on the appearance
                # This is a provisional value and may need more tweaking
                default_linewidth = min(.1 * binwidth_points, default_linewidth)

            # Set the attributes
            for bar in hist_artists:

                # Don't let the lines get too thick
                max_linewidth = bar.get_linewidth()
                if not fill:
                    max_linewidth *= 1.5

                linewidth = min(default_linewidth, max_linewidth)

                # If not filling, don't let lines disappear
                if not fill:
                    min_linewidth = .5
                    linewidth = max(linewidth, min_linewidth)

                bar.set_linewidth(linewidth)

        # --- Finalize the plot ----

        # Axis labels
        ax = self.ax if self.ax is not None else self.facets.axes.flat[0]
        default_x = default_y = ""
        if self.data_variable == "x":
            default_y = estimator.stat.capitalize()
        if self.data_variable == "y":
            default_x = estimator.stat.capitalize()
        self._add_axis_labels(ax, default_x, default_y)

        # Legend for semantic variables
        if "hue" in self.variables and legend:

            if fill or element == "bars":
                artist = partial(mpl.patches.Patch)
            else:
                artist = partial(mpl.lines.Line2D, [], [])

            ax_obj = self.ax if self.ax is not None else self.facets
            self._add_legend(
                ax_obj, artist, fill, element, multiple, alpha, plot_kws, {},
            )

    def plot_bivariate_histogram(
        self,
        common_bins, common_norm,
        thresh, pthresh, pmax,
        color, legend,
        cbar, cbar_ax, cbar_kws,
        estimate_kws,
        **plot_kws,
    ):

        # Default keyword dicts
        cbar_kws = {} if cbar_kws is None else cbar_kws.copy()

        # Now initialize the Histogram estimator
        estimator = Histogram(**estimate_kws)

        # Do pre-compute housekeeping related to multiple groups
        if set(self.variables) - {"x", "y"}:
            all_data = self.comp_data.dropna()
            if common_bins:
                estimator.define_bin_params(
                    all_data["x"],
                    all_data["y"],
                    all_data.get("weights", None),
                )
        else:
            common_norm = False

        # -- Determine colormap threshold and norm based on the full data

        full_heights = []
        for _, sub_data in self.iter_data(from_comp_data=True):
            sub_heights, _ = estimator(
                sub_data["x"], sub_data["y"], sub_data.get("weights", None)
            )
            full_heights.append(sub_heights)

        common_color_norm = not set(self.variables) - {"x", "y"} or common_norm

        if pthresh is not None and common_color_norm:
            thresh = self._quantile_to_level(full_heights, pthresh)

        plot_kws.setdefault("vmin", 0)
        if common_color_norm:
            if pmax is not None:
                vmax = self._quantile_to_level(full_heights, pmax)
            else:
                vmax = plot_kws.pop("vmax", max(map(np.max, full_heights)))
        else:
            vmax = None

        # Get a default color
        # (We won't follow the color cycle here, as multiple plots are unlikely)
        if color is None:
            color = "C0"

        # --- Loop over data (subsets) and draw the histograms
        for sub_vars, sub_data in self.iter_data("hue", from_comp_data=True):

            if sub_data.empty:
                continue

            # Do the histogram computation
            heights, (x_edges, y_edges) = estimator(
                sub_data["x"],
                sub_data["y"],
                weights=sub_data.get("weights", None),
            )

            # Get the axes for this plot
            ax = self._get_axes(sub_vars)

            # Invert the scale for the edges
            _, inv_x = _get_transform_functions(ax, "x")
            _, inv_y = _get_transform_functions(ax, "y")
            x_edges = inv_x(x_edges)
            y_edges = inv_y(y_edges)

            # Apply scaling to normalize across groups
            if estimator.stat != "count" and common_norm:
                heights *= len(sub_data) / len(all_data)

            # Define the specific kwargs for this artist
            artist_kws = plot_kws.copy()
            if "hue" in self.variables:
                color = self._hue_map(sub_vars["hue"])
                cmap = self._cmap_from_color(color)
                artist_kws["cmap"] = cmap
            else:
                cmap = artist_kws.pop("cmap", None)
                if isinstance(cmap, str):
                    cmap = color_palette(cmap, as_cmap=True)
                elif cmap is None:
                    cmap = self._cmap_from_color(color)
                artist_kws["cmap"] = cmap

            # Set the upper norm on the colormap
            if not common_color_norm and pmax is not None:
                vmax = self._quantile_to_level(heights, pmax)
            if vmax is not None:
                artist_kws["vmax"] = vmax

            # Make cells at or below the threshold transparent
            if not common_color_norm and pthresh:
                thresh = self._quantile_to_level(heights, pthresh)
            if thresh is not None:
                heights = np.ma.masked_less_equal(heights, thresh)

            # pcolormesh is going to turn the grid off, but we want to keep it
            # I'm not sure if there's a better way to get the grid state
            x_grid = any([l.get_visible() for l in ax.xaxis.get_gridlines()])
            y_grid = any([l.get_visible() for l in ax.yaxis.get_gridlines()])

            mesh = ax.pcolormesh(
                x_edges,
                y_edges,
                heights.T,
                **artist_kws,
            )

            # pcolormesh sets sticky edges, but we only want them if not thresholding
            if thresh is not None:
                mesh.sticky_edges.x[:] = []
                mesh.sticky_edges.y[:] = []

            # Add an optional colorbar
            # Note, we want to improve this. When hue is used, it will stack
            # multiple colorbars with redundant ticks in an ugly way.
            # But it's going to take some work to have multiple colorbars that
            # share ticks nicely.
            if cbar:
                ax.figure.colorbar(mesh, cbar_ax, ax, **cbar_kws)

            # Reset the grid state
            if x_grid:
                ax.grid(True, axis="x")
            if y_grid:
                ax.grid(True, axis="y")

        # --- Finalize the plot

        ax = self.ax if self.ax is not None else self.facets.axes.flat[0]
        self._add_axis_labels(ax)

        if "hue" in self.variables and legend:

            # TODO if possible, I would like to move the contour
            # intensity information into the legend too and label the
            # iso proportions rather than the raw density values

            artist_kws = {}
            artist = partial(mpl.patches.Patch)
            ax_obj = self.ax if self.ax is not None else self.facets
            self._add_legend(
                ax_obj, artist, True, False, "layer", 1, artist_kws, {},
            )

    def plot_univariate_density(
        self,
        multiple,
        common_norm,
        common_grid,
        warn_singular,
        fill,
        color,
        legend,
        estimate_kws,
        **plot_kws,
    ):

        # Handle conditional defaults
        if fill is None:
            fill = multiple in ("stack", "fill")

        # Preprocess the matplotlib keyword dictionaries
        if fill:
            artist = mpl.collections.PolyCollection
        else:
            artist = mpl.lines.Line2D
        plot_kws = normalize_kwargs(plot_kws, artist)

        # Input checking
        _check_argument("multiple", ["layer", "stack", "fill"], multiple)

        # Always share the evaluation grid when stacking
        subsets = bool(set(self.variables) - {"x", "y"})
        if subsets and multiple in ("stack", "fill"):
            common_grid = True

        # Do the computation
        densities = self._compute_univariate_density(
            self.data_variable,
            common_norm,
            common_grid,
            estimate_kws,
            warn_singular,
        )

        # Adjust densities based on the `multiple` rule
        densities, baselines = self._resolve_multiple(densities, multiple)

        # Control the interaction with autoscaling by defining sticky_edges
        # i.e. we don't want autoscale margins below the density curve
        sticky_density = (0, 1) if multiple == "fill" else (0, np.inf)

        if multiple == "fill":
            # Filled plots should not have any margins
            sticky_support = densities.index.min(), densities.index.max()
        else:
            sticky_support = []

        if fill:
            if multiple == "layer":
                default_alpha = .25
            else:
                default_alpha = .75
        else:
            default_alpha = 1
        alpha = plot_kws.pop("alpha", default_alpha)  # TODO make parameter?

        # Now iterate through the subsets and draw the densities
        # We go backwards so stacked densities read from top-to-bottom
        for sub_vars, _ in self.iter_data("hue", reverse=True):

            # Extract the support grid and density curve for this level
            key = tuple(sub_vars.items())
            try:
                density = densities[key]
            except KeyError:
                continue
            support = density.index
            fill_from = baselines[key]

            ax = self._get_axes(sub_vars)

            if "hue" in self.variables:
                sub_color = self._hue_map(sub_vars["hue"])
            else:
                sub_color = color

            artist_kws = self._artist_kws(
                plot_kws, fill, False, multiple, sub_color, alpha
            )

            # Either plot a curve with observation values on the x axis
            if "x" in self.variables:

                if fill:
                    artist = ax.fill_between(support, fill_from, density, **artist_kws)

                else:
                    artist, = ax.plot(support, density, **artist_kws)

                artist.sticky_edges.x[:] = sticky_support
                artist.sticky_edges.y[:] = sticky_density

            # Or plot a curve with observation values on the y axis
            else:
                if fill:
                    artist = ax.fill_betweenx(support, fill_from, density, **artist_kws)
                else:
                    artist, = ax.plot(density, support, **artist_kws)

                artist.sticky_edges.x[:] = sticky_density
                artist.sticky_edges.y[:] = sticky_support

        # --- Finalize the plot ----

        ax = self.ax if self.ax is not None else self.facets.axes.flat[0]
        default_x = default_y = ""
        if self.data_variable == "x":
            default_y = "Density"
        if self.data_variable == "y":
            default_x = "Density"
        self._add_axis_labels(ax, default_x, default_y)

        if "hue" in self.variables and legend:

            if fill:
                artist = partial(mpl.patches.Patch)
            else:
                artist = partial(mpl.lines.Line2D, [], [])

            ax_obj = self.ax if self.ax is not None else self.facets
            self._add_legend(
                ax_obj, artist, fill, False, multiple, alpha, plot_kws, {},
            )

    def plot_bivariate_density(
        self,
        common_norm,
        fill,
        levels,
        thresh,
        color,
        legend,
        cbar,
        warn_singular,
        cbar_ax,
        cbar_kws,
        estimate_kws,
        **contour_kws,
    ):

        contour_kws = contour_kws.copy()

        estimator = KDE(**estimate_kws)

        if not set(self.variables) - {"x", "y"}:
            common_norm = False

        all_data = self.plot_data.dropna()

        # Loop through the subsets and estimate the KDEs
        densities, supports = {}, {}

        for sub_vars, sub_data in self.iter_data("hue", from_comp_data=True):

            # Extract the data points from this sub set
            observations = sub_data[["x", "y"]]
            min_variance = observations.var().fillna(0).min()
            observations = observations["x"], observations["y"]

            # Extract the weights for this subset of observations
            if "weights" in self.variables:
                weights = sub_data["weights"]
            else:
                weights = None

            # Estimate the density of observations at this level
            singular = math.isclose(min_variance, 0)
            try:
                if not singular:
                    density, support = estimator(*observations, weights=weights)
            except np.linalg.LinAlgError:
                # Testing for 0 variance doesn't catch all cases where scipy raises,
                # but we can also get a ValueError, so we need this convoluted approach
                singular = True

            if singular:
                msg = (
                    "KDE cannot be estimated (0 variance or perfect covariance). "
                    "Pass `warn_singular=False` to disable this warning."
                )
                if warn_singular:
                    warnings.warn(msg, UserWarning, stacklevel=3)
                continue

            # Transform the support grid back to the original scale
            ax = self._get_axes(sub_vars)
            _, inv_x = _get_transform_functions(ax, "x")
            _, inv_y = _get_transform_functions(ax, "y")
            support = inv_x(support[0]), inv_y(support[1])

            # Apply a scaling factor so that the integral over all subsets is 1
            if common_norm:
                density *= len(sub_data) / len(all_data)

            key = tuple(sub_vars.items())
            densities[key] = density
            supports[key] = support

        # Define a grid of iso-proportion levels
        if thresh is None:
            thresh = 0
        if isinstance(levels, Number):
            levels = np.linspace(thresh, 1, levels)
        else:
            if min(levels) < 0 or max(levels) > 1:
                raise ValueError("levels must be in [0, 1]")

        # Transform from iso-proportions to iso-densities
        if common_norm:
            common_levels = self._quantile_to_level(
                list(densities.values()), levels,
            )
            draw_levels = {k: common_levels for k in densities}
        else:
            draw_levels = {
                k: self._quantile_to_level(d, levels)
                for k, d in densities.items()
            }

        # Define the coloring of the contours
        if "hue" in self.variables:
            for param in ["cmap", "colors"]:
                if param in contour_kws:
                    msg = f"{param} parameter ignored when using hue mapping."
                    warnings.warn(msg, UserWarning)
                    contour_kws.pop(param)
        else:

            # Work out a default coloring of the contours
            coloring_given = set(contour_kws) & {"cmap", "colors"}
            if fill and not coloring_given:
                cmap = self._cmap_from_color(color)
                contour_kws["cmap"] = cmap
            if not fill and not coloring_given:
                contour_kws["colors"] = [color]

            # Use our internal colormap lookup
            cmap = contour_kws.pop("cmap", None)
            if isinstance(cmap, str):
                cmap = color_palette(cmap, as_cmap=True)
            if cmap is not None:
                contour_kws["cmap"] = cmap

        # Loop through the subsets again and plot the data
        for sub_vars, _ in self.iter_data("hue"):

            if "hue" in sub_vars:
                color = self._hue_map(sub_vars["hue"])
                if fill:
                    contour_kws["cmap"] = self._cmap_from_color(color)
                else:
                    contour_kws["colors"] = [color]

            ax = self._get_axes(sub_vars)

            # Choose the function to plot with
            # TODO could add a pcolormesh based option as well
            # Which would look something like element="raster"
            if fill:
                contour_func = ax.contourf
            else:
                contour_func = ax.contour

            key = tuple(sub_vars.items())
            if key not in densities:
                continue
            density = densities[key]
            xx, yy = supports[key]

            # Pop the label kwarg which is unused by contour_func (but warns)
            contour_kws.pop("label", None)

            cset = contour_func(
                xx, yy, density,
                levels=draw_levels[key],
                **contour_kws,
            )

            # Add a color bar representing the contour heights
            # Note: this shows iso densities, not iso proportions
            # See more notes in histplot about how this could be improved
            if cbar:
                cbar_kws = {} if cbar_kws is None else cbar_kws
                ax.figure.colorbar(cset, cbar_ax, ax, **cbar_kws)

        # --- Finalize the plot
        ax = self.ax if self.ax is not None else self.facets.axes.flat[0]
        self._add_axis_labels(ax)

        if "hue" in self.variables and legend:

            # TODO if possible, I would like to move the contour
            # intensity information into the legend too and label the
            # iso proportions rather than the raw density values

            artist_kws = {}
            if fill:
                artist = partial(mpl.patches.Patch)
            else:
                artist = partial(mpl.lines.Line2D, [], [])

            ax_obj = self.ax if self.ax is not None else self.facets
            self._add_legend(
                ax_obj, artist, fill, False, "layer", 1, artist_kws, {},
            )

    def plot_univariate_ecdf(self, estimate_kws, legend, **plot_kws):

        estimator = ECDF(**estimate_kws)

        # Set the draw style to step the right way for the data variable
        drawstyles = dict(x="steps-post", y="steps-pre")
        plot_kws["drawstyle"] = drawstyles[self.data_variable]

        # Loop through the subsets, transform and plot the data
        for sub_vars, sub_data in self.iter_data(
            "hue", reverse=True, from_comp_data=True,
        ):

            # Compute the ECDF
            if sub_data.empty:
                continue

            observations = sub_data[self.data_variable]
            weights = sub_data.get("weights", None)
            stat, vals = estimator(observations, weights=weights)

            # Assign attributes based on semantic mapping
            artist_kws = plot_kws.copy()
            if "hue" in self.variables:
                artist_kws["color"] = self._hue_map(sub_vars["hue"])

            # Return the data variable to the linear domain
            ax = self._get_axes(sub_vars)
            _, inv = _get_transform_functions(ax, self.data_variable)
            vals = inv(vals)

            # Manually set the minimum value on a "log" scale
            if isinstance(inv.__self__, mpl.scale.LogTransform):
                vals[0] = -np.inf

            # Work out the orientation of the plot
            if self.data_variable == "x":
                plot_args = vals, stat
                stat_variable = "y"
            else:
                plot_args = stat, vals
                stat_variable = "x"

            if estimator.stat == "count":
                top_edge = len(observations)
            else:
                top_edge = 1

            # Draw the line for this subset
            artist, = ax.plot(*plot_args, **artist_kws)
            sticky_edges = getattr(artist.sticky_edges, stat_variable)
            sticky_edges[:] = 0, top_edge

        # --- Finalize the plot ----
        ax = self.ax if self.ax is not None else self.facets.axes.flat[0]
        stat = estimator.stat.capitalize()
        default_x = default_y = ""
        if self.data_variable == "x":
            default_y = stat
        if self.data_variable == "y":
            default_x = stat
        self._add_axis_labels(ax, default_x, default_y)

        if "hue" in self.variables and legend:
            artist = partial(mpl.lines.Line2D, [], [])
            alpha = plot_kws.get("alpha", 1)
            ax_obj = self.ax if self.ax is not None else self.facets
            self._add_legend(
                ax_obj, artist, False, False, None, alpha, plot_kws, {},
            )

    def plot_rug(self, height, expand_margins, legend, **kws):

        for sub_vars, sub_data, in self.iter_data(from_comp_data=True):

            ax = self._get_axes(sub_vars)

            kws.setdefault("linewidth", 1)

            if expand_margins:
                xmarg, ymarg = ax.margins()
                if "x" in self.variables:
                    ymarg += height * 2
                if "y" in self.variables:
                    xmarg += height * 2
                ax.margins(x=xmarg, y=ymarg)

            if "hue" in self.variables:
                kws.pop("c", None)
                kws.pop("color", None)

            if "x" in self.variables:
                self._plot_single_rug(sub_data, "x", height, ax, kws)
            if "y" in self.variables:
                self._plot_single_rug(sub_data, "y", height, ax, kws)

            # --- Finalize the plot
            self._add_axis_labels(ax)
            if "hue" in self.variables and legend:
                # TODO ideally i'd like the legend artist to look like a rug
                legend_artist = partial(mpl.lines.Line2D, [], [])
                self._add_legend(
                    ax, legend_artist, False, False, None, 1, {}, {},
                )

    def _plot_single_rug(self, sub_data, var, height, ax, kws):
        """Draw a rugplot along one axis of the plot."""
        vector = sub_data[var]
        n = len(vector)

        # Return data to linear domain
        _, inv = _get_transform_functions(ax, var)
        vector = inv(vector)

        # We'll always add a single collection with varying colors
        if "hue" in self.variables:
            colors = self._hue_map(sub_data["hue"])
        else:
            colors = None

        # Build the array of values for the LineCollection
        if var == "x":

            trans = tx.blended_transform_factory(ax.transData, ax.transAxes)
            xy_pairs = np.column_stack([
                np.repeat(vector, 2), np.tile([0, height], n)
            ])

        if var == "y":

            trans = tx.blended_transform_factory(ax.transAxes, ax.transData)
            xy_pairs = np.column_stack([
                np.tile([0, height], n), np.repeat(vector, 2)
            ])

        # Draw the lines on the plot
        line_segs = xy_pairs.reshape([n, 2, 2])
        ax.add_collection(LineCollection(
            line_segs, transform=trans, colors=colors, **kws
        ))

        ax.autoscale_view(scalex=var == "x", scaley=var == "y")


# ==================================================================================== #
# External API
# ==================================================================================== #

def histplot(
    data=None, *,
    # Vector variables
    x=None, y=None, hue=None, weights=None,
    # Histogram computation parameters
    stat="count", bins="auto", binwidth=None, binrange=None,
    discrete=None, cumulative=False, common_bins=True, common_norm=True,
    # Histogram appearance parameters
    multiple="layer", element="bars", fill=True, shrink=1,
    # Histogram smoothing with a kernel density estimate
    kde=False, kde_kws=None, line_kws=None,
    # Bivariate histogram parameters
    thresh=0, pthresh=None, pmax=None, cbar=False, cbar_ax=None, cbar_kws=None,
    # Hue mapping parameters
    palette=None, hue_order=None, hue_norm=None, color=None,
    # Axes information
    log_scale=None, legend=True, ax=None,
    # Other appearance keywords
    **kwargs,
):

    p = _DistributionPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, weights=weights),
    )

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)

    if ax is None:
        ax = plt.gca()

    p._attach(ax, log_scale=log_scale)

    if p.univariate:  # Note, bivariate plots won't cycle
        if fill:
            method = ax.bar if element == "bars" else ax.fill_between
        else:
            method = ax.plot
        color = _default_color(method, hue, color, kwargs)

    if not p.has_xy_data:
        return ax

    # Default to discrete bins for categorical variables
    if discrete is None:
        discrete = p._default_discrete()

    estimate_kws = dict(
        stat=stat,
        bins=bins,
        binwidth=binwidth,
        binrange=binrange,
        discrete=discrete,
        cumulative=cumulative,
    )

    if p.univariate:

        p.plot_univariate_histogram(
            multiple=multiple,
            element=element,
            fill=fill,
            shrink=shrink,
            common_norm=common_norm,
            common_bins=common_bins,
            kde=kde,
            kde_kws=kde_kws,
            color=color,
            legend=legend,
            estimate_kws=estimate_kws,
            line_kws=line_kws,
            **kwargs,
        )

    else:

        p.plot_bivariate_histogram(
            common_bins=common_bins,
            common_norm=common_norm,
            thresh=thresh,
            pthresh=pthresh,
            pmax=pmax,
            color=color,
            legend=legend,
            cbar=cbar,
            cbar_ax=cbar_ax,
            cbar_kws=cbar_kws,
            estimate_kws=estimate_kws,
            **kwargs,
        )

    return ax


histplot.__doc__ = """\
Plot univariate or bivariate histograms to show distributions of datasets.

A histogram is a classic visualization tool that represents the distribution
of one or more variables by counting the number of observations that fall within
discrete bins.

This function can normalize the statistic computed within each bin to estimate
frequency, density or probability mass, and it can add a smooth curve obtained
using a kernel density estimate, similar to :func:`kdeplot`.

More information is provided in the :ref:`user guide <tutorial_hist>`.

Parameters
----------
{params.core.data}
{params.core.xy}
{params.core.hue}
weights : vector or key in ``data``
    If provided, weight the contribution of the corresponding data points
    towards the count in each bin by these factors.
{params.hist.stat}
{params.hist.bins}
{params.hist.binwidth}
{params.hist.binrange}
discrete : bool
    If True, default to ``binwidth=1`` and draw the bars so that they are
    centered on their corresponding data points. This avoids "gaps" that may
    otherwise appear when using discrete (integer) data.
cumulative : bool
    If True, plot the cumulative counts as bins increase.
common_bins : bool
    If True, use the same bins when semantic variables produce multiple
    plots. If using a reference rule to determine the bins, it will be computed
    with the full dataset.
common_norm : bool
    If True and using a normalized statistic, the normalization will apply over
    the full dataset. Otherwise, normalize each histogram independently.
multiple : {{"layer", "dodge", "stack", "fill"}}
    Approach to resolving multiple elements when semantic mapping creates subsets.
    Only relevant with univariate data.
element : {{"bars", "step", "poly"}}
    Visual representation of the histogram statistic.
    Only relevant with univariate data.
fill : bool
    If True, fill in the space under the histogram.
    Only relevant with univariate data.
shrink : number
    Scale the width of each bar relative to the binwidth by this factor.
    Only relevant with univariate data.
kde : bool
    If True, compute a kernel density estimate to smooth the distribution
    and show on the plot as (one or more) line(s).
    Only relevant with univariate data.
kde_kws : dict
    Parameters that control the KDE computation, as in :func:`kdeplot`.
line_kws : dict
    Parameters that control the KDE visualization, passed to
    :meth:`matplotlib.axes.Axes.plot`.
thresh : number or None
    Cells with a statistic less than or equal to this value will be transparent.
    Only relevant with bivariate data.
pthresh : number or None
    Like ``thresh``, but a value in [0, 1] such that cells with aggregate counts
    (or other statistics, when used) up to this proportion of the total will be
    transparent.
pmax : number or None
    A value in [0, 1] that sets that saturation point for the colormap at a value
    such that cells below constitute this proportion of the total count (or
    other statistic, when used).
{params.dist.cbar}
{params.dist.cbar_ax}
{params.dist.cbar_kws}
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.core.color}
{params.dist.log_scale}
{params.dist.legend}
{params.core.ax}
kwargs
    Other keyword arguments are passed to one of the following matplotlib
    functions:

    - :meth:`matplotlib.axes.Axes.bar` (univariate, element="bars")
    - :meth:`matplotlib.axes.Axes.fill_between` (univariate, other element, fill=True)
    - :meth:`matplotlib.axes.Axes.plot` (univariate, other element, fill=False)
    - :meth:`matplotlib.axes.Axes.pcolormesh` (bivariate)

Returns
-------
{returns.ax}

See Also
--------
{seealso.displot}
{seealso.kdeplot}
{seealso.rugplot}
{seealso.ecdfplot}
{seealso.jointplot}

Notes
-----

The choice of bins for computing and plotting a histogram can exert
substantial influence on the insights that one is able to draw from the
visualization. If the bins are too large, they may erase important features.
On the other hand, bins that are too small may be dominated by random
variability, obscuring the shape of the true underlying distribution. The
default bin size is determined using a reference rule that depends on the
sample size and variance. This works well in many cases, (i.e., with
"well-behaved" data) but it fails in others. It is always a good to try
different bin sizes to be sure that you are not missing something important.
This function allows you to specify bins in several different ways, such as
by setting the total number of bins to use, the width of each bin, or the
specific locations where the bins should break.

Examples
--------

.. include:: ../docstrings/histplot.rst

""".format(
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)


def kdeplot(
    data=None, *, x=None, y=None, hue=None, weights=None,
    palette=None, hue_order=None, hue_norm=None, color=None, fill=None,
    multiple="layer", common_norm=True, common_grid=False, cumulative=False,
    bw_method="scott", bw_adjust=1, warn_singular=True, log_scale=None,
    levels=10, thresh=.05, gridsize=200, cut=3, clip=None,
    legend=True, cbar=False, cbar_ax=None, cbar_kws=None, ax=None,
    **kwargs,
):

    # --- Start with backwards compatability for versions < 0.11.0 ----------------

    # Handle (past) deprecation of `data2`
    if "data2" in kwargs:
        msg = "`data2` has been removed (replaced by `y`); please update your code."
        raise TypeError(msg)

    # Handle deprecation of `vertical`
    vertical = kwargs.pop("vertical", None)
    if vertical is not None:
        if vertical:
            action_taken = "assigning data to `y`."
            if x is None:
                data, y = y, data
            else:
                x, y = y, x
        else:
            action_taken = "assigning data to `x`."
        msg = textwrap.dedent(f"""\n
        The `vertical` parameter is deprecated; {action_taken}
        This will become an error in seaborn v0.14.0; please update your code.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)

    # Handle deprecation of `bw`
    bw = kwargs.pop("bw", None)
    if bw is not None:
        msg = textwrap.dedent(f"""\n
        The `bw` parameter is deprecated in favor of `bw_method` and `bw_adjust`.
        Setting `bw_method={bw}`, but please see the docs for the new parameters
        and update your code. This will become an error in seaborn v0.14.0.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)
        bw_method = bw

    # Handle deprecation of `kernel`
    if kwargs.pop("kernel", None) is not None:
        msg = textwrap.dedent("""\n
        Support for alternate kernels has been removed; using Gaussian kernel.
        This will become an error in seaborn v0.14.0; please update your code.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)

    # Handle deprecation of shade_lowest
    shade_lowest = kwargs.pop("shade_lowest", None)
    if shade_lowest is not None:
        if shade_lowest:
            thresh = 0
        msg = textwrap.dedent(f"""\n
        `shade_lowest` has been replaced by `thresh`; setting `thresh={thresh}.
        This will become an error in seaborn v0.14.0; please update your code.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)

    # Handle "soft" deprecation of shade `shade` is not really the right
    # terminology here, but unlike some of the other deprecated parameters it
    # is probably very commonly used and much hard to remove. This is therefore
    # going to be a longer process where, first, `fill` will be introduced and
    # be used throughout the documentation. In 0.12, when kwarg-only
    # enforcement hits, we can remove the shade/shade_lowest out of the
    # function signature all together and pull them out of the kwargs. Then we
    # can actually fire a FutureWarning, and eventually remove.
    shade = kwargs.pop("shade", None)
    if shade is not None:
        fill = shade
        msg = textwrap.dedent(f"""\n
        `shade` is now deprecated in favor of `fill`; setting `fill={shade}`.
        This will become an error in seaborn v0.14.0; please update your code.
        """)
        warnings.warn(msg, FutureWarning, stacklevel=2)

    # Handle `n_levels`
    # This was never in the formal API but it was processed, and appeared in an
    # example. We can treat as an alias for `levels` now and deprecate later.
    levels = kwargs.pop("n_levels", levels)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

    p = _DistributionPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, weights=weights),
    )

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)

    if ax is None:
        ax = plt.gca()

    p._attach(ax, allowed_types=["numeric", "datetime"], log_scale=log_scale)

    method = ax.fill_between if fill else ax.plot
    color = _default_color(method, hue, color, kwargs)

    if not p.has_xy_data:
        return ax

    # Pack the kwargs for statistics.KDE
    estimate_kws = dict(
        bw_method=bw_method,
        bw_adjust=bw_adjust,
        gridsize=gridsize,
        cut=cut,
        clip=clip,
        cumulative=cumulative,
    )

    if p.univariate:

        plot_kws = kwargs.copy()

        p.plot_univariate_density(
            multiple=multiple,
            common_norm=common_norm,
            common_grid=common_grid,
            fill=fill,
            color=color,
            legend=legend,
            warn_singular=warn_singular,
            estimate_kws=estimate_kws,
            **plot_kws,
        )

    else:

        p.plot_bivariate_density(
            common_norm=common_norm,
            fill=fill,
            levels=levels,
            thresh=thresh,
            legend=legend,
            color=color,
            warn_singular=warn_singular,
            cbar=cbar,
            cbar_ax=cbar_ax,
            cbar_kws=cbar_kws,
            estimate_kws=estimate_kws,
            **kwargs,
        )

    return ax


kdeplot.__doc__ = """\
Plot univariate or bivariate distributions using kernel density estimation.

A kernel density estimate (KDE) plot is a method for visualizing the
distribution of observations in a dataset, analogous to a histogram. KDE
represents the data using a continuous probability density curve in one or
more dimensions.

The approach is explained further in the :ref:`user guide <tutorial_kde>`.

Relative to a histogram, KDE can produce a plot that is less cluttered and
more interpretable, especially when drawing multiple distributions. But it
has the potential to introduce distortions if the underlying distribution is
bounded or not smooth. Like a histogram, the quality of the representation
also depends on the selection of good smoothing parameters.

Parameters
----------
{params.core.data}
{params.core.xy}
{params.core.hue}
weights : vector or key in ``data``
    If provided, weight the kernel density estimation using these values.
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.core.color}
fill : bool or None
    If True, fill in the area under univariate density curves or between
    bivariate contours. If None, the default depends on ``multiple``.
{params.dist.multiple}
common_norm : bool
    If True, scale each conditional density by the number of observations
    such that the total area under all densities sums to 1. Otherwise,
    normalize each density independently.
common_grid : bool
    If True, use the same evaluation grid for each kernel density estimate.
    Only relevant with univariate data.
{params.kde.cumulative}
{params.kde.bw_method}
{params.kde.bw_adjust}
warn_singular : bool
    If True, issue a warning when trying to estimate the density of data
    with zero variance.
{params.dist.log_scale}
levels : int or vector
    Number of contour levels or values to draw contours at. A vector argument
    must have increasing values in [0, 1]. Levels correspond to iso-proportions
    of the density: e.g., 20% of the probability mass will lie below the
    contour drawn for 0.2. Only relevant with bivariate data.
thresh : number in [0, 1]
    Lowest iso-proportion level at which to draw a contour line. Ignored when
    ``levels`` is a vector. Only relevant with bivariate data.
gridsize : int
    Number of points on each dimension of the evaluation grid.
{params.kde.cut}
{params.kde.clip}
{params.dist.legend}
{params.dist.cbar}
{params.dist.cbar_ax}
{params.dist.cbar_kws}
{params.core.ax}
kwargs
    Other keyword arguments are passed to one of the following matplotlib
    functions:

    - :meth:`matplotlib.axes.Axes.plot` (univariate, ``fill=False``),
    - :meth:`matplotlib.axes.Axes.fill_between` (univariate, ``fill=True``),
    - :meth:`matplotlib.axes.Axes.contour` (bivariate, ``fill=False``),
    - :meth:`matplotlib.axes.contourf` (bivariate, ``fill=True``).

Returns
-------
{returns.ax}

See Also
--------
{seealso.displot}
{seealso.histplot}
{seealso.ecdfplot}
{seealso.jointplot}
{seealso.violinplot}

Notes
-----

The *bandwidth*, or standard deviation of the smoothing kernel, is an
important parameter. Misspecification of the bandwidth can produce a
distorted representation of the data. Much like the choice of bin width in a
histogram, an over-smoothed curve can erase true features of a
distribution, while an under-smoothed curve can create false features out of
random variability. The rule-of-thumb that sets the default bandwidth works
best when the true distribution is smooth, unimodal, and roughly bell-shaped.
It is always a good idea to check the default behavior by using ``bw_adjust``
to increase or decrease the amount of smoothing.

Because the smoothing algorithm uses a Gaussian kernel, the estimated density
curve can extend to values that do not make sense for a particular dataset.
For example, the curve may be drawn over negative values when smoothing data
that are naturally positive. The ``cut`` and ``clip`` parameters can be used
to control the extent of the curve, but datasets that have many observations
close to a natural boundary may be better served by a different visualization
method.

Similar considerations apply when a dataset is naturally discrete or "spiky"
(containing many repeated observations of the same value). Kernel density
estimation will always produce a smooth curve, which would be misleading
in these situations.

The units on the density axis are a common source of confusion. While kernel
density estimation produces a probability distribution, the height of the curve
at each point gives a density, not a probability. A probability can be obtained
only by integrating the density across a range. The curve is normalized so
that the integral over all possible values is 1, meaning that the scale of
the density axis depends on the data values.

Examples
--------

.. include:: ../docstrings/kdeplot.rst

""".format(
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)


def ecdfplot(
    data=None, *,
    # Vector variables
    x=None, y=None, hue=None, weights=None,
    # Computation parameters
    stat="proportion", complementary=False,
    # Hue mapping parameters
    palette=None, hue_order=None, hue_norm=None,
    # Axes information
    log_scale=None, legend=True, ax=None,
    # Other appearance keywords
    **kwargs,
):

    p = _DistributionPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, weights=weights),
    )

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)

    # We could support other semantics (size, style) here fairly easily
    # But it would make distplot a bit more complicated.
    # It's always possible to add features like that later, so I am going to defer.
    # It will be even easier to wait until after there is a more general/abstract
    # way to go from semantic specs to artist attributes.

    if ax is None:
        ax = plt.gca()

    p._attach(ax, log_scale=log_scale)

    color = kwargs.pop("color", kwargs.pop("c", None))
    kwargs["color"] = _default_color(ax.plot, hue, color, kwargs)

    if not p.has_xy_data:
        return ax

    # We could add this one day, but it's of dubious value
    if not p.univariate:
        raise NotImplementedError("Bivariate ECDF plots are not implemented")

    estimate_kws = dict(
        stat=stat,
        complementary=complementary,
    )

    p.plot_univariate_ecdf(
        estimate_kws=estimate_kws,
        legend=legend,
        **kwargs,
    )

    return ax


ecdfplot.__doc__ = """\
Plot empirical cumulative distribution functions.

An ECDF represents the proportion or count of observations falling below each
unique value in a dataset. Compared to a histogram or density plot, it has the
advantage that each observation is visualized directly, meaning that there are
no binning or smoothing parameters that need to be adjusted. It also aids direct
comparisons between multiple distributions. A downside is that the relationship
between the appearance of the plot and the basic properties of the distribution
(such as its central tendency, variance, and the presence of any bimodality)
may not be as intuitive.

More information is provided in the :ref:`user guide <tutorial_ecdf>`.

Parameters
----------
{params.core.data}
{params.core.xy}
{params.core.hue}
weights : vector or key in ``data``
    If provided, weight the contribution of the corresponding data points
    towards the cumulative distribution using these values.
{params.ecdf.stat}
{params.ecdf.complementary}
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.dist.log_scale}
{params.dist.legend}
{params.core.ax}
kwargs
    Other keyword arguments are passed to :meth:`matplotlib.axes.Axes.plot`.

Returns
-------
{returns.ax}

See Also
--------
{seealso.displot}
{seealso.histplot}
{seealso.kdeplot}
{seealso.rugplot}

Examples
--------

.. include:: ../docstrings/ecdfplot.rst

""".format(
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)


def rugplot(
    data=None, *, x=None, y=None, hue=None, height=.025, expand_margins=True,
    palette=None, hue_order=None, hue_norm=None, legend=True, ax=None, **kwargs
):

    # A note: I think it would make sense to add multiple= to rugplot and allow
    # rugs for different hue variables to be shifted orthogonal to the data axis
    # But is this stacking, or dodging?

    # A note: if we want to add a style semantic to rugplot,
    # we could make an option that draws the rug using scatterplot

    # A note, it would also be nice to offer some kind of histogram/density
    # rugplot, since alpha blending doesn't work great in the large n regime

    # --- Start with backwards compatability for versions < 0.11.0 ----------------

    a = kwargs.pop("a", None)
    axis = kwargs.pop("axis", None)

    if a is not None:
        data = a
        msg = textwrap.dedent("""\n
        The `a` parameter has been replaced; use `x`, `y`, and/or `data` instead.
        Please update your code; This will become an error in seaborn v0.14.0.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)

    if axis is not None:
        if axis == "x":
            x = data
        elif axis == "y":
            y = data
        data = None
        msg = textwrap.dedent(f"""\n
        The `axis` parameter has been deprecated; use the `{axis}` parameter instead.
        Please update your code; this will become an error in seaborn v0.14.0.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)

    vertical = kwargs.pop("vertical", None)
    if vertical is not None:
        if vertical:
            action_taken = "assigning data to `y`."
            if x is None:
                data, y = y, data
            else:
                x, y = y, x
        else:
            action_taken = "assigning data to `x`."
        msg = textwrap.dedent(f"""\n
        The `vertical` parameter is deprecated; {action_taken}
        This will become an error in seaborn v0.14.0; please update your code.
        """)
        warnings.warn(msg, UserWarning, stacklevel=2)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

    p = _DistributionPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue),
    )
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)

    if ax is None:
        ax = plt.gca()

    p._attach(ax)

    color = kwargs.pop("color", kwargs.pop("c", None))
    kwargs["color"] = _default_color(ax.plot, hue, color, kwargs)

    if not p.has_xy_data:
        return ax

    p.plot_rug(height, expand_margins, legend, **kwargs)

    return ax


rugplot.__doc__ = """\
Plot marginal distributions by drawing ticks along the x and y axes.

This function is intended to complement other plots by showing the location
of individual observations in an unobtrusive way.

Parameters
----------
{params.core.data}
{params.core.xy}
{params.core.hue}
height : float
    Proportion of axes extent covered by each rug element. Can be negative.
expand_margins : bool
    If True, increase the axes margins by the height of the rug to avoid
    overlap with other elements.
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
legend : bool
    If False, do not add a legend for semantic variables.
{params.core.ax}
kwargs
    Other keyword arguments are passed to
    :meth:`matplotlib.collections.LineCollection`

Returns
-------
{returns.ax}

Examples
--------

.. include:: ../docstrings/rugplot.rst

""".format(
    params=_param_docs,
    returns=_core_docs["returns"],
)


def displot(
    data=None, *,
    # Vector variables
    x=None, y=None, hue=None, row=None, col=None, weights=None,
    # Other plot parameters
    kind="hist", rug=False, rug_kws=None, log_scale=None, legend=True,
    # Hue-mapping parameters
    palette=None, hue_order=None, hue_norm=None, color=None,
    # Faceting parameters
    col_wrap=None, row_order=None, col_order=None,
    height=5, aspect=1, facet_kws=None,
    **kwargs,
):

    p = _DistributionPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, weights=weights, row=row, col=col),
    )

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)

    _check_argument("kind", ["hist", "kde", "ecdf"], kind)

    # --- Initialize the FacetGrid object

    # Check for attempt to plot onto specific axes and warn
    if "ax" in kwargs:
        msg = (
            "`displot` is a figure-level function and does not accept "
            "the ax= parameter. You may wish to try {}plot.".format(kind)
        )
        warnings.warn(msg, UserWarning)
        kwargs.pop("ax")

    for var in ["row", "col"]:
        # Handle faceting variables that lack name information
        if var in p.variables and p.variables[var] is None:
            p.variables[var] = f"_{var}_"

    # Adapt the plot_data dataframe for use with FacetGrid
    grid_data = p.plot_data.rename(columns=p.variables)
    grid_data = grid_data.loc[:, ~grid_data.columns.duplicated()]

    col_name = p.variables.get("col")
    row_name = p.variables.get("row")

    if facet_kws is None:
        facet_kws = {}

    g = FacetGrid(
        data=grid_data, row=row_name, col=col_name,
        col_wrap=col_wrap, row_order=row_order,
        col_order=col_order, height=height,
        aspect=aspect,
        **facet_kws,
    )

    # Now attach the axes object to the plotter object
    if kind == "kde":
        allowed_types = ["numeric", "datetime"]
    else:
        allowed_types = None
    p._attach(g, allowed_types=allowed_types, log_scale=log_scale)

    # Check for a specification that lacks x/y data and return early
    if not p.has_xy_data:
        return g

    if color is None and hue is None:
        color = "C0"
    # XXX else warn if hue is not None?

    kwargs["legend"] = legend

    # --- Draw the plots

    if kind == "hist":

        hist_kws = kwargs.copy()

        # Extract the parameters that will go directly to Histogram
        estimate_defaults = {}
        _assign_default_kwargs(estimate_defaults, Histogram.__init__, histplot)

        estimate_kws = {}
        for key, default_val in estimate_defaults.items():
            estimate_kws[key] = hist_kws.pop(key, default_val)

        # Handle derivative defaults
        if estimate_kws["discrete"] is None:
            estimate_kws["discrete"] = p._default_discrete()

        hist_kws["estimate_kws"] = estimate_kws

        hist_kws.setdefault("color", color)

        if p.univariate:

            _assign_default_kwargs(hist_kws, p.plot_univariate_histogram, histplot)
            p.plot_univariate_histogram(**hist_kws)

        else:

            _assign_default_kwargs(hist_kws, p.plot_bivariate_histogram, histplot)
            p.plot_bivariate_histogram(**hist_kws)

    elif kind == "kde":

        kde_kws = kwargs.copy()

        # Extract the parameters that will go directly to KDE
        estimate_defaults = {}
        _assign_default_kwargs(estimate_defaults, KDE.__init__, kdeplot)

        estimate_kws = {}
        for key, default_val in estimate_defaults.items():
            estimate_kws[key] = kde_kws.pop(key, default_val)

        kde_kws["estimate_kws"] = estimate_kws
        kde_kws["color"] = color

        if p.univariate:

            _assign_default_kwargs(kde_kws, p.plot_univariate_density, kdeplot)
            p.plot_univariate_density(**kde_kws)

        else:

            _assign_default_kwargs(kde_kws, p.plot_bivariate_density, kdeplot)
            p.plot_bivariate_density(**kde_kws)

    elif kind == "ecdf":

        ecdf_kws = kwargs.copy()

        # Extract the parameters that will go directly to the estimator
        estimate_kws = {}
        estimate_defaults = {}
        _assign_default_kwargs(estimate_defaults, ECDF.__init__, ecdfplot)
        for key, default_val in estimate_defaults.items():
            estimate_kws[key] = ecdf_kws.pop(key, default_val)

        ecdf_kws["estimate_kws"] = estimate_kws
        ecdf_kws["color"] = color

        if p.univariate:

            _assign_default_kwargs(ecdf_kws, p.plot_univariate_ecdf, ecdfplot)
            p.plot_univariate_ecdf(**ecdf_kws)

        else:

            raise NotImplementedError("Bivariate ECDF plots are not implemented")

    # All plot kinds can include a rug
    if rug:
        # TODO with expand_margins=True, each facet expands margins... annoying!
        if rug_kws is None:
            rug_kws = {}
        _assign_default_kwargs(rug_kws, p.plot_rug, rugplot)
        rug_kws["legend"] = False
        if color is not None:
            rug_kws["color"] = color
        p.plot_rug(**rug_kws)

    # Call FacetGrid annotation methods
    # Note that the legend is currently set inside the plotting method
    g.set_axis_labels(
        x_var=p.variables.get("x", g.axes.flat[0].get_xlabel()),
        y_var=p.variables.get("y", g.axes.flat[0].get_ylabel()),
    )
    g.set_titles()
    g.tight_layout()

    if data is not None and (x is not None or y is not None):
        if not isinstance(data, pd.DataFrame):
            data = pd.DataFrame(data)
        g.data = pd.merge(
            data,
            g.data[g.data.columns.difference(data.columns)],
            left_index=True,
            right_index=True,
        )
    else:
        wide_cols = {
            k: f"_{k}_" if v is None else v for k, v in p.variables.items()
        }
        g.data = p.plot_data.rename(columns=wide_cols)

    return g


displot.__doc__ = """\
Figure-level interface for drawing distribution plots onto a FacetGrid.

This function provides access to several approaches for visualizing the
univariate or bivariate distribution of data, including subsets of data
defined by semantic mapping and faceting across multiple subplots. The
``kind`` parameter selects the approach to use:

- :func:`histplot` (with ``kind="hist"``; the default)
- :func:`kdeplot` (with ``kind="kde"``)
- :func:`ecdfplot` (with ``kind="ecdf"``; univariate-only)

Additionally, a :func:`rugplot` can be added to any kind of plot to show
individual observations.

Extra keyword arguments are passed to the underlying function, so you should
refer to the documentation for each to understand the complete set of options
for making plots with this interface.

See the :doc:`distribution plots tutorial <../tutorial/distributions>` for a more
in-depth discussion of the relative strengths and weaknesses of each approach.
The distinction between figure-level and axes-level functions is explained
further in the :doc:`user guide <../tutorial/function_overview>`.

Parameters
----------
{params.core.data}
{params.core.xy}
{params.core.hue}
{params.facets.rowcol}
weights : vector or key in ``data``
    Observation weights used for computing the distribution function.
kind : {{"hist", "kde", "ecdf"}}
    Approach for visualizing the data. Selects the underlying plotting function
    and determines the additional set of valid parameters.
rug : bool
    If True, show each observation with marginal ticks (as in :func:`rugplot`).
rug_kws : dict
    Parameters to control the appearance of the rug plot.
{params.dist.log_scale}
{params.dist.legend}
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.core.color}
{params.facets.col_wrap}
{params.facets.rowcol_order}
{params.facets.height}
{params.facets.aspect}
{params.facets.facet_kws}
kwargs
    Other keyword arguments are documented with the relevant axes-level function:

    - :func:`histplot` (with ``kind="hist"``)
    - :func:`kdeplot` (with ``kind="kde"``)
    - :func:`ecdfplot` (with ``kind="ecdf"``)

Returns
-------
{returns.facetgrid}

See Also
--------
{seealso.histplot}
{seealso.kdeplot}
{seealso.rugplot}
{seealso.ecdfplot}
{seealso.jointplot}

Examples
--------

See the API documentation for the axes-level functions for more details
about the breadth of options available for each plot kind.

.. include:: ../docstrings/displot.rst

""".format(
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)


# =========================================================================== #
# DEPRECATED FUNCTIONS LIVE BELOW HERE
# =========================================================================== #


def _freedman_diaconis_bins(a):
    """Calculate number of hist bins using Freedman-Diaconis rule."""
    # From https://stats.stackexchange.com/questions/798/
    a = np.asarray(a)
    if len(a) < 2:
        return 1
    iqr = np.subtract.reduce(np.nanpercentile(a, [75, 25]))
    h = 2 * iqr / (len(a) ** (1 / 3))
    # fall back to sqrt(a) bins if iqr is 0
    if h == 0:
        return int(np.sqrt(a.size))
    else:
        return int(np.ceil((a.max() - a.min()) / h))


def distplot(a=None, bins=None, hist=True, kde=True, rug=False, fit=None,
             hist_kws=None, kde_kws=None, rug_kws=None, fit_kws=None,
             color=None, vertical=False, norm_hist=False, axlabel=None,
             label=None, ax=None, x=None):
    """
    DEPRECATED

    This function has been deprecated and will be removed in seaborn v0.14.0.
    It has been replaced by :func:`histplot` and :func:`displot`, two functions
    with a modern API and many more capabilities.

    For a guide to updating, please see this notebook:

    https://gist.github.com/mwaskom/de44147ed2974457ad6372750bbe5751

    """

    if kde and not hist:
        axes_level_suggestion = (
            "`kdeplot` (an axes-level function for kernel density plots)"
        )
    else:
        axes_level_suggestion = (
            "`histplot` (an axes-level function for histograms)"
        )

    msg = textwrap.dedent(f"""

    `distplot` is a deprecated function and will be removed in seaborn v0.14.0.

    Please adapt your code to use either `displot` (a figure-level function with
    similar flexibility) or {axes_level_suggestion}.

    For a guide to updating your code to use the new functions, please see
    https://gist.github.com/mwaskom/de44147ed2974457ad6372750bbe5751
    """)
    warnings.warn(msg, UserWarning, stacklevel=2)

    if ax is None:
        ax = plt.gca()

    # Intelligently label the support axis
    label_ax = bool(axlabel)
    if axlabel is None and hasattr(a, "name"):
        axlabel = a.name
        if axlabel is not None:
            label_ax = True

    # Support new-style API
    if x is not None:
        a = x

    # Make a a 1-d float array
    a = np.asarray(a, float)
    if a.ndim > 1:
        a = a.squeeze()

    # Drop null values from array
    a = remove_na(a)

    # Decide if the hist is normed
    norm_hist = norm_hist or kde or (fit is not None)

    # Handle dictionary defaults
    hist_kws = {} if hist_kws is None else hist_kws.copy()
    kde_kws = {} if kde_kws is None else kde_kws.copy()
    rug_kws = {} if rug_kws is None else rug_kws.copy()
    fit_kws = {} if fit_kws is None else fit_kws.copy()

    # Get the color from the current color cycle
    if color is None:
        if vertical:
            line, = ax.plot(0, a.mean())
        else:
            line, = ax.plot(a.mean(), 0)
        color = line.get_color()
        line.remove()

    # Plug the label into the right kwarg dictionary
    if label is not None:
        if hist:
            hist_kws["label"] = label
        elif kde:
            kde_kws["label"] = label
        elif rug:
            rug_kws["label"] = label
        elif fit:
            fit_kws["label"] = label

    if hist:
        if bins is None:
            bins = min(_freedman_diaconis_bins(a), 50)
        hist_kws.setdefault("alpha", 0.4)
        hist_kws.setdefault("density", norm_hist)

        orientation = "horizontal" if vertical else "vertical"
        hist_color = hist_kws.pop("color", color)
        ax.hist(a, bins, orientation=orientation,
                color=hist_color, **hist_kws)
        if hist_color != color:
            hist_kws["color"] = hist_color

    axis = "y" if vertical else "x"

    if kde:
        kde_color = kde_kws.pop("color", color)
        kdeplot(**{axis: a}, ax=ax, color=kde_color, **kde_kws)
        if kde_color != color:
            kde_kws["color"] = kde_color

    if rug:
        rug_color = rug_kws.pop("color", color)
        rugplot(**{axis: a}, ax=ax, color=rug_color, **rug_kws)
        if rug_color != color:
            rug_kws["color"] = rug_color

    if fit is not None:

        def pdf(x):
            return fit.pdf(x, *params)

        fit_color = fit_kws.pop("color", "#282828")
        gridsize = fit_kws.pop("gridsize", 200)
        cut = fit_kws.pop("cut", 3)
        clip = fit_kws.pop("clip", (-np.inf, np.inf))
        bw = gaussian_kde(a).scotts_factor() * a.std(ddof=1)
        x = _kde_support(a, bw, gridsize, cut, clip)
        params = fit.fit(a)
        y = pdf(x)
        if vertical:
            x, y = y, x
        ax.plot(x, y, color=fit_color, **fit_kws)
        if fit_color != "#282828":
            fit_kws["color"] = fit_color

    if label_ax:
        if vertical:
            ax.set_ylabel(axlabel)
        else:
            ax.set_xlabel(axlabel)

    return ax
