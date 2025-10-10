from functools import partial
import warnings

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.cbook import normalize_kwargs

from ._base import (
    VectorPlotter,
)
from .utils import (
    adjust_legend_subtitles,
    _default_color,
    _deprecate_ci,
    _get_transform_functions,
    _scatter_legend_artist,
)
from ._compat import groupby_apply_include_groups
from ._statistics import EstimateAggregator, WeightedAggregator
from .axisgrid import FacetGrid, _facet_docs
from ._docstrings import DocstringComponents, _core_docs


__all__ = ["relplot", "scatterplot", "lineplot"]


_relational_narrative = DocstringComponents(dict(

    # ---  Introductory prose
    main_api="""
The relationship between `x` and `y` can be shown for different subsets
of the data using the `hue`, `size`, and `style` parameters. These
parameters control what visual semantics are used to identify the different
subsets. It is possible to show up to three dimensions independently by
using all three semantic types, but this style of plot can be hard to
interpret and is often ineffective. Using redundant semantics (i.e. both
`hue` and `style` for the same variable) can be helpful for making
graphics more accessible.

See the :ref:`tutorial <relational_tutorial>` for more information.
    """,

    relational_semantic="""
The default treatment of the `hue` (and to a lesser extent, `size`)
semantic, if present, depends on whether the variable is inferred to
represent "numeric" or "categorical" data. In particular, numeric variables
are represented with a sequential colormap by default, and the legend
entries show regular "ticks" with values that may or may not exist in the
data. This behavior can be controlled through various parameters, as
described and illustrated below.
    """,
))

_relational_docs = dict(

    # --- Shared function parameters
    data_vars="""
x, y : names of variables in `data` or vector data
    Input data variables; must be numeric. Can pass data directly or
    reference columns in `data`.
    """,
    data="""
data : DataFrame, array, or list of arrays
    Input data structure. If `x` and `y` are specified as names, this
    should be a "long-form" DataFrame containing those columns. Otherwise
    it is treated as "wide-form" data and grouping variables are ignored.
    See the examples for the various ways this parameter can be specified
    and the different effects of each.
    """,
    palette="""
palette : string, list, dict, or matplotlib colormap
    An object that determines how colors are chosen when `hue` is used.
    It can be the name of a seaborn palette or matplotlib colormap, a list
    of colors (anything matplotlib understands), a dict mapping levels
    of the `hue` variable to colors, or a matplotlib colormap object.
    """,
    hue_order="""
hue_order : list
    Specified order for the appearance of the `hue` variable levels,
    otherwise they are determined from the data. Not relevant when the
    `hue` variable is numeric.
    """,
    hue_norm="""
hue_norm : tuple or :class:`matplotlib.colors.Normalize` object
    Normalization in data units for colormap applied to the `hue`
    variable when it is numeric. Not relevant if `hue` is categorical.
    """,
    sizes="""
sizes : list, dict, or tuple
    An object that determines how sizes are chosen when `size` is used.
    List or dict arguments should provide a size for each unique data value,
    which forces a categorical interpretation. The argument may also be a
    min, max tuple.
    """,
    size_order="""
size_order : list
    Specified order for appearance of the `size` variable levels,
    otherwise they are determined from the data. Not relevant when the
    `size` variable is numeric.
    """,
    size_norm="""
size_norm : tuple or Normalize object
    Normalization in data units for scaling plot objects when the
    `size` variable is numeric.
    """,
    dashes="""
dashes : boolean, list, or dictionary
    Object determining how to draw the lines for different levels of the
    `style` variable. Setting to `True` will use default dash codes, or
    you can pass a list of dash codes or a dictionary mapping levels of the
    `style` variable to dash codes. Setting to `False` will use solid
    lines for all subsets. Dashes are specified as in matplotlib: a tuple
    of `(segment, gap)` lengths, or an empty string to draw a solid line.
    """,
    markers="""
markers : boolean, list, or dictionary
    Object determining how to draw the markers for different levels of the
    `style` variable. Setting to `True` will use default markers, or
    you can pass a list of markers or a dictionary mapping levels of the
    `style` variable to markers. Setting to `False` will draw
    marker-less lines.  Markers are specified as in matplotlib.
    """,
    style_order="""
style_order : list
    Specified order for appearance of the `style` variable levels
    otherwise they are determined from the data. Not relevant when the
    `style` variable is numeric.
    """,
    units="""
units : vector or key in `data`
    Grouping variable identifying sampling units. When used, a separate
    line will be drawn for each unit with appropriate semantics, but no
    legend entry will be added. Useful for showing distribution of
    experimental replicates when exact identities are not needed.
    """,
    estimator="""
estimator : name of pandas method or callable or None
    Method for aggregating across multiple observations of the `y`
    variable at the same `x` level. If `None`, all observations will
    be drawn.
    """,
    ci="""
ci : int or "sd" or None
    Size of the confidence interval to draw when aggregating.

    .. deprecated:: 0.12.0
        Use the new `errorbar` parameter for more flexibility.

    """,
    n_boot="""
n_boot : int
    Number of bootstraps to use for computing the confidence interval.
    """,
    seed="""
seed : int, numpy.random.Generator, or numpy.random.RandomState
    Seed or random number generator for reproducible bootstrapping.
    """,
    legend="""
legend : "auto", "brief", "full", or False
    How to draw the legend. If "brief", numeric `hue` and `size`
    variables will be represented with a sample of evenly spaced values.
    If "full", every group will get an entry in the legend. If "auto",
    choose between brief or full representation based on number of levels.
    If `False`, no legend data is added and no legend is drawn.
    """,
    ax_in="""
ax : matplotlib Axes
    Axes object to draw the plot onto, otherwise uses the current Axes.
    """,
    ax_out="""
ax : matplotlib Axes
    Returns the Axes object with the plot drawn onto it.
    """,

)


_param_docs = DocstringComponents.from_nested_components(
    core=_core_docs["params"],
    facets=DocstringComponents(_facet_docs),
    rel=DocstringComponents(_relational_docs),
    stat=DocstringComponents.from_function_params(EstimateAggregator.__init__),
)


class _RelationalPlotter(VectorPlotter):

    wide_structure = {
        "x": "@index", "y": "@values", "hue": "@columns", "style": "@columns",
    }

    # TODO where best to define default parameters?
    sort = True


class _LinePlotter(_RelationalPlotter):

    _legend_attributes = ["color", "linewidth", "marker", "dashes"]

    def __init__(
        self, *,
        data=None, variables={},
        estimator=None, n_boot=None, seed=None, errorbar=None,
        sort=True, orient="x", err_style=None, err_kws=None, legend=None
    ):

        # TODO this is messy, we want the mapping to be agnostic about
        # the kind of plot to draw, but for the time being we need to set
        # this information so the SizeMapping can use it
        self._default_size_range = (
            np.r_[.5, 2] * mpl.rcParams["lines.linewidth"]
        )

        super().__init__(data=data, variables=variables)

        self.estimator = estimator
        self.errorbar = errorbar
        self.n_boot = n_boot
        self.seed = seed
        self.sort = sort
        self.orient = orient
        self.err_style = err_style
        self.err_kws = {} if err_kws is None else err_kws

        self.legend = legend

    def plot(self, ax, kws):
        """Draw the plot onto an axes, passing matplotlib kwargs."""

        # Draw a test plot, using the passed in kwargs. The goal here is to
        # honor both (a) the current state of the plot cycler and (b) the
        # specified kwargs on all the lines we will draw, overriding when
        # relevant with the data semantics. Note that we won't cycle
        # internally; in other words, if `hue` is not used, all elements will
        # have the same color, but they will have the color that you would have
        # gotten from the corresponding matplotlib function, and calling the
        # function will advance the axes property cycle.

        kws = normalize_kwargs(kws, mpl.lines.Line2D)
        kws.setdefault("markeredgewidth", 0.75)
        kws.setdefault("markeredgecolor", "w")

        # Set default error kwargs
        err_kws = self.err_kws.copy()
        if self.err_style == "band":
            err_kws.setdefault("alpha", .2)
        elif self.err_style == "bars":
            pass
        elif self.err_style is not None:
            err = "`err_style` must be 'band' or 'bars', not {}"
            raise ValueError(err.format(self.err_style))

        # Initialize the aggregation object
        weighted = "weight" in self.plot_data
        agg = (WeightedAggregator if weighted else EstimateAggregator)(
            self.estimator, self.errorbar, n_boot=self.n_boot, seed=self.seed,
        )

        # TODO abstract variable to aggregate over here-ish. Better name?
        orient = self.orient
        if orient not in {"x", "y"}:
            err = f"`orient` must be either 'x' or 'y', not {orient!r}."
            raise ValueError(err)
        other = {"x": "y", "y": "x"}[orient]

        # TODO How to handle NA? We don't want NA to propagate through to the
        # estimate/CI when some values are present, but we would also like
        # matplotlib to show "gaps" in the line when all values are missing.
        # This is straightforward absent aggregation, but complicated with it.
        # If we want to use nas, we need to conditionalize dropna in iter_data.

        # Loop over the semantic subsets and add to the plot
        grouping_vars = "hue", "size", "style"
        for sub_vars, sub_data in self.iter_data(grouping_vars, from_comp_data=True):

            if self.sort:
                sort_vars = ["units", orient, other]
                sort_cols = [var for var in sort_vars if var in self.variables]
                sub_data = sub_data.sort_values(sort_cols)

            if (
                self.estimator is not None
                and sub_data[orient].value_counts().max() > 1
            ):
                if "units" in self.variables:
                    # TODO eventually relax this constraint
                    err = "estimator must be None when specifying units"
                    raise ValueError(err)
                grouped = sub_data.groupby(orient, sort=self.sort)
                # Could pass as_index=False instead of reset_index,
                # but that fails on a corner case with older pandas.
                sub_data = (
                    grouped
                    .apply(agg, other, **groupby_apply_include_groups(False))
                    .reset_index()
                )
            else:
                sub_data[f"{other}min"] = np.nan
                sub_data[f"{other}max"] = np.nan

            # Apply inverse axis scaling
            for var in "xy":
                _, inv = _get_transform_functions(ax, var)
                for col in sub_data.filter(regex=f"^{var}"):
                    sub_data[col] = inv(sub_data[col])

            # --- Draw the main line(s)

            if "units" in self.variables:   # XXX why not add to grouping variables?
                lines = []
                for _, unit_data in sub_data.groupby("units"):
                    lines.extend(ax.plot(unit_data["x"], unit_data["y"], **kws))
            else:
                lines = ax.plot(sub_data["x"], sub_data["y"], **kws)

            for line in lines:

                if "hue" in sub_vars:
                    line.set_color(self._hue_map(sub_vars["hue"]))

                if "size" in sub_vars:
                    line.set_linewidth(self._size_map(sub_vars["size"]))

                if "style" in sub_vars:
                    attributes = self._style_map(sub_vars["style"])
                    if "dashes" in attributes:
                        line.set_dashes(attributes["dashes"])
                    if "marker" in attributes:
                        line.set_marker(attributes["marker"])

            line_color = line.get_color()
            line_alpha = line.get_alpha()
            line_capstyle = line.get_solid_capstyle()

            # --- Draw the confidence intervals

            if self.estimator is not None and self.errorbar is not None:

                # TODO handling of orientation will need to happen here

                if self.err_style == "band":

                    func = {"x": ax.fill_between, "y": ax.fill_betweenx}[orient]
                    func(
                        sub_data[orient],
                        sub_data[f"{other}min"], sub_data[f"{other}max"],
                        color=line_color, **err_kws
                    )

                elif self.err_style == "bars":

                    error_param = {
                        f"{other}err": (
                            sub_data[other] - sub_data[f"{other}min"],
                            sub_data[f"{other}max"] - sub_data[other],
                        )
                    }
                    ebars = ax.errorbar(
                        sub_data["x"], sub_data["y"], **error_param,
                        linestyle="", color=line_color, alpha=line_alpha,
                        **err_kws
                    )

                    # Set the capstyle properly on the error bars
                    for obj in ebars.get_children():
                        if isinstance(obj, mpl.collections.LineCollection):
                            obj.set_capstyle(line_capstyle)

        # Finalize the axes details
        self._add_axis_labels(ax)
        if self.legend:
            legend_artist = partial(mpl.lines.Line2D, xdata=[], ydata=[])
            attrs = {"hue": "color", "size": "linewidth", "style": None}
            self.add_legend_data(ax, legend_artist, kws, attrs)
            handles, _ = ax.get_legend_handles_labels()
            if handles:
                legend = ax.legend(title=self.legend_title)
                adjust_legend_subtitles(legend)


class _ScatterPlotter(_RelationalPlotter):

    _legend_attributes = ["color", "s", "marker"]

    def __init__(self, *, data=None, variables={}, legend=None):

        # TODO this is messy, we want the mapping to be agnostic about
        # the kind of plot to draw, but for the time being we need to set
        # this information so the SizeMapping can use it
        self._default_size_range = (
            np.r_[.5, 2] * np.square(mpl.rcParams["lines.markersize"])
        )

        super().__init__(data=data, variables=variables)

        self.legend = legend

    def plot(self, ax, kws):

        # --- Determine the visual attributes of the plot

        data = self.comp_data.dropna()
        if data.empty:
            return

        kws = normalize_kwargs(kws, mpl.collections.PathCollection)

        # Define the vectors of x and y positions
        empty = np.full(len(data), np.nan)
        x = data.get("x", empty)
        y = data.get("y", empty)

        # Apply inverse scaling to the coordinate variables
        _, inv_x = _get_transform_functions(ax, "x")
        _, inv_y = _get_transform_functions(ax, "y")
        x, y = inv_x(x), inv_y(y)

        if "style" in self.variables:
            # Use a representative marker so scatter sets the edgecolor
            # properly for line art markers. We currently enforce either
            # all or none line art so this works.
            example_level = self._style_map.levels[0]
            example_marker = self._style_map(example_level, "marker")
            kws.setdefault("marker", example_marker)

        # Conditionally set the marker edgecolor based on whether the marker is "filled"
        # See https://github.com/matplotlib/matplotlib/issues/17849 for context
        m = kws.get("marker", mpl.rcParams.get("marker", "o"))
        if not isinstance(m, mpl.markers.MarkerStyle):
            # TODO in more recent matplotlib (which?) can pass a MarkerStyle here
            m = mpl.markers.MarkerStyle(m)
        if m.is_filled():
            kws.setdefault("edgecolor", "w")

        # Draw the scatter plot
        points = ax.scatter(x=x, y=y, **kws)

        # Apply the mapping from semantic variables to artist attributes

        if "hue" in self.variables:
            points.set_facecolors(self._hue_map(data["hue"]))

        if "size" in self.variables:
            points.set_sizes(self._size_map(data["size"]))

        if "style" in self.variables:
            p = [self._style_map(val, "path") for val in data["style"]]
            points.set_paths(p)

        # Apply dependent default attributes

        if "linewidth" not in kws:
            sizes = points.get_sizes()
            linewidth = .08 * np.sqrt(np.percentile(sizes, 10))
            points.set_linewidths(linewidth)
            kws["linewidth"] = linewidth

        # Finalize the axes details
        self._add_axis_labels(ax)
        if self.legend:
            attrs = {"hue": "color", "size": "s", "style": None}
            self.add_legend_data(ax, _scatter_legend_artist, kws, attrs)
            handles, _ = ax.get_legend_handles_labels()
            if handles:
                legend = ax.legend(title=self.legend_title)
                adjust_legend_subtitles(legend)


def lineplot(
    data=None, *,
    x=None, y=None, hue=None, size=None, style=None, units=None, weights=None,
    palette=None, hue_order=None, hue_norm=None,
    sizes=None, size_order=None, size_norm=None,
    dashes=True, markers=None, style_order=None,
    estimator="mean", errorbar=("ci", 95), n_boot=1000, seed=None,
    orient="x", sort=True, err_style="band", err_kws=None,
    legend="auto", ci="deprecated", ax=None, **kwargs
):

    # Handle deprecation of ci parameter
    errorbar = _deprecate_ci(errorbar, ci)

    p = _LinePlotter(
        data=data,
        variables=dict(
            x=x, y=y, hue=hue, size=size, style=style, units=units, weight=weights
        ),
        estimator=estimator, n_boot=n_boot, seed=seed, errorbar=errorbar,
        sort=sort, orient=orient, err_style=err_style, err_kws=err_kws,
        legend=legend,
    )

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)
    p.map_size(sizes=sizes, order=size_order, norm=size_norm)
    p.map_style(markers=markers, dashes=dashes, order=style_order)

    if ax is None:
        ax = plt.gca()

    if "style" not in p.variables and not {"ls", "linestyle"} & set(kwargs):  # XXX
        kwargs["dashes"] = "" if dashes is None or isinstance(dashes, bool) else dashes

    if not p.has_xy_data:
        return ax

    p._attach(ax)

    # Other functions have color as an explicit param,
    # and we should probably do that here too
    color = kwargs.pop("color", kwargs.pop("c", None))
    kwargs["color"] = _default_color(ax.plot, hue, color, kwargs)

    p.plot(ax, kwargs)
    return ax


lineplot.__doc__ = """\
Draw a line plot with possibility of several semantic groupings.

{narrative.main_api}

{narrative.relational_semantic}

By default, the plot aggregates over multiple `y` values at each value of
`x` and shows an estimate of the central tendency and a confidence
interval for that estimate.

Parameters
----------
{params.core.data}
{params.core.xy}
hue : vector or key in `data`
    Grouping variable that will produce lines with different colors.
    Can be either categorical or numeric, although color mapping will
    behave differently in latter case.
size : vector or key in `data`
    Grouping variable that will produce lines with different widths.
    Can be either categorical or numeric, although size mapping will
    behave differently in latter case.
style : vector or key in `data`
    Grouping variable that will produce lines with different dashes
    and/or markers. Can have a numeric dtype but will always be treated
    as categorical.
{params.rel.units}
weights : vector or key in `data`
    Data values or column used to compute weighted estimation.
    Note that use of weights currently limits the choice of statistics
    to a 'mean' estimator and 'ci' errorbar.
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.rel.sizes}
{params.rel.size_order}
{params.rel.size_norm}
{params.rel.dashes}
{params.rel.markers}
{params.rel.style_order}
{params.rel.estimator}
{params.stat.errorbar}
{params.rel.n_boot}
{params.rel.seed}
orient : "x" or "y"
    Dimension along which the data are sorted / aggregated. Equivalently,
    the "independent variable" of the resulting function.
sort : boolean
    If True, the data will be sorted by the x and y variables, otherwise
    lines will connect points in the order they appear in the dataset.
err_style : "band" or "bars"
    Whether to draw the confidence intervals with translucent error bands
    or discrete error bars.
err_kws : dict of keyword arguments
    Additional parameters to control the aesthetics of the error bars. The
    kwargs are passed either to :meth:`matplotlib.axes.Axes.fill_between`
    or :meth:`matplotlib.axes.Axes.errorbar`, depending on `err_style`.
{params.rel.legend}
{params.rel.ci}
{params.core.ax}
kwargs : key, value mappings
    Other keyword arguments are passed down to
    :meth:`matplotlib.axes.Axes.plot`.

Returns
-------
{returns.ax}

See Also
--------
{seealso.scatterplot}
{seealso.pointplot}

Examples
--------

.. include:: ../docstrings/lineplot.rst

""".format(
    narrative=_relational_narrative,
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)


def scatterplot(
    data=None, *,
    x=None, y=None, hue=None, size=None, style=None,
    palette=None, hue_order=None, hue_norm=None,
    sizes=None, size_order=None, size_norm=None,
    markers=True, style_order=None, legend="auto", ax=None,
    **kwargs
):

    p = _ScatterPlotter(
        data=data,
        variables=dict(x=x, y=y, hue=hue, size=size, style=style),
        legend=legend
    )

    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)
    p.map_size(sizes=sizes, order=size_order, norm=size_norm)
    p.map_style(markers=markers, order=style_order)

    if ax is None:
        ax = plt.gca()

    if not p.has_xy_data:
        return ax

    p._attach(ax)

    color = kwargs.pop("color", None)
    kwargs["color"] = _default_color(ax.scatter, hue, color, kwargs)

    p.plot(ax, kwargs)

    return ax


scatterplot.__doc__ = """\
Draw a scatter plot with possibility of several semantic groupings.

{narrative.main_api}

{narrative.relational_semantic}

Parameters
----------
{params.core.data}
{params.core.xy}
hue : vector or key in `data`
    Grouping variable that will produce points with different colors.
    Can be either categorical or numeric, although color mapping will
    behave differently in latter case.
size : vector or key in `data`
    Grouping variable that will produce points with different sizes.
    Can be either categorical or numeric, although size mapping will
    behave differently in latter case.
style : vector or key in `data`
    Grouping variable that will produce points with different markers.
    Can have a numeric dtype but will always be treated as categorical.
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.rel.sizes}
{params.rel.size_order}
{params.rel.size_norm}
{params.rel.markers}
{params.rel.style_order}
{params.rel.legend}
{params.core.ax}
kwargs : key, value mappings
    Other keyword arguments are passed down to
    :meth:`matplotlib.axes.Axes.scatter`.

Returns
-------
{returns.ax}

See Also
--------
{seealso.lineplot}
{seealso.stripplot}
{seealso.swarmplot}

Examples
--------

.. include:: ../docstrings/scatterplot.rst

""".format(
    narrative=_relational_narrative,
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)


def relplot(
    data=None, *,
    x=None, y=None, hue=None, size=None, style=None, units=None, weights=None,
    row=None, col=None, col_wrap=None, row_order=None, col_order=None,
    palette=None, hue_order=None, hue_norm=None,
    sizes=None, size_order=None, size_norm=None,
    markers=None, dashes=None, style_order=None,
    legend="auto", kind="scatter", height=5, aspect=1, facet_kws=None,
    **kwargs
):

    if kind == "scatter":

        Plotter = _ScatterPlotter
        func = scatterplot
        markers = True if markers is None else markers

    elif kind == "line":

        Plotter = _LinePlotter
        func = lineplot
        dashes = True if dashes is None else dashes

    else:
        err = f"Plot kind {kind} not recognized"
        raise ValueError(err)

    # Check for attempt to plot onto specific axes and warn
    if "ax" in kwargs:
        msg = (
            "relplot is a figure-level function and does not accept "
            "the `ax` parameter. You may wish to try {}".format(kind + "plot")
        )
        warnings.warn(msg, UserWarning)
        kwargs.pop("ax")

    # Use the full dataset to map the semantics
    variables = dict(x=x, y=y, hue=hue, size=size, style=style)
    if kind == "line":
        variables["units"] = units
        variables["weight"] = weights
    else:
        if units is not None:
            msg = "The `units` parameter has no effect with kind='scatter'."
            warnings.warn(msg, stacklevel=2)
        if weights is not None:
            msg = "The `weights` parameter has no effect with kind='scatter'."
            warnings.warn(msg, stacklevel=2)
    p = Plotter(
        data=data,
        variables=variables,
        legend=legend,
    )
    p.map_hue(palette=palette, order=hue_order, norm=hue_norm)
    p.map_size(sizes=sizes, order=size_order, norm=size_norm)
    p.map_style(markers=markers, dashes=dashes, order=style_order)

    # Extract the semantic mappings
    if "hue" in p.variables:
        palette = p._hue_map.lookup_table
        hue_order = p._hue_map.levels
        hue_norm = p._hue_map.norm
    else:
        palette = hue_order = hue_norm = None

    if "size" in p.variables:
        sizes = p._size_map.lookup_table
        size_order = p._size_map.levels
        size_norm = p._size_map.norm

    if "style" in p.variables:
        style_order = p._style_map.levels
        if markers:
            markers = {k: p._style_map(k, "marker") for k in style_order}
        else:
            markers = None
        if dashes:
            dashes = {k: p._style_map(k, "dashes") for k in style_order}
        else:
            dashes = None
    else:
        markers = dashes = style_order = None

    # Now extract the data that would be used to draw a single plot
    variables = p.variables
    plot_data = p.plot_data

    # Define the common plotting parameters
    plot_kws = dict(
        palette=palette, hue_order=hue_order, hue_norm=hue_norm,
        sizes=sizes, size_order=size_order, size_norm=size_norm,
        markers=markers, dashes=dashes, style_order=style_order,
        legend=False,
    )
    plot_kws.update(kwargs)
    if kind == "scatter":
        plot_kws.pop("dashes")

    # Add the grid semantics onto the plotter
    grid_variables = dict(
        x=x, y=y, row=row, col=col, hue=hue, size=size, style=style,
    )
    if kind == "line":
        grid_variables.update(units=units, weights=weights)
    p.assign_variables(data, grid_variables)

    # Define the named variables for plotting on each facet
    # Rename the variables with a leading underscore to avoid
    # collisions with faceting variable names
    plot_variables = {v: f"_{v}" for v in variables}
    if "weight" in plot_variables:
        plot_variables["weights"] = plot_variables.pop("weight")
    plot_kws.update(plot_variables)

    # Pass the row/col variables to FacetGrid with their original
    # names so that the axes titles render correctly
    for var in ["row", "col"]:
        # Handle faceting variables that lack name information
        if var in p.variables and p.variables[var] is None:
            p.variables[var] = f"_{var}_"
    grid_kws = {v: p.variables.get(v) for v in ["row", "col"]}

    # Rename the columns of the plot_data structure appropriately
    new_cols = plot_variables.copy()
    new_cols.update(grid_kws)
    full_data = p.plot_data.rename(columns=new_cols)

    # Set up the FacetGrid object
    facet_kws = {} if facet_kws is None else facet_kws.copy()
    g = FacetGrid(
        data=full_data.dropna(axis=1, how="all"),
        **grid_kws,
        col_wrap=col_wrap, row_order=row_order, col_order=col_order,
        height=height, aspect=aspect, dropna=False,
        **facet_kws
    )

    # Draw the plot
    g.map_dataframe(func, **plot_kws)

    # Label the axes, using the original variables
    # Pass "" when the variable name is None to overwrite internal variables
    g.set_axis_labels(variables.get("x") or "", variables.get("y") or "")

    if legend:
        # Replace the original plot data so the legend uses numeric data with
        # the correct type, since we force a categorical mapping above.
        p.plot_data = plot_data

        # Handle the additional non-semantic keyword arguments out here.
        # We're selective because some kwargs may be seaborn function specific
        # and not relevant to the matplotlib artists going into the legend.
        # Ideally, we will have a better solution where we don't need to re-make
        # the legend out here and will have parity with the axes-level functions.
        keys = ["c", "color", "alpha", "m", "marker"]
        if kind == "scatter":
            legend_artist = _scatter_legend_artist
            keys += ["s", "facecolor", "fc", "edgecolor", "ec", "linewidth", "lw"]
        else:
            legend_artist = partial(mpl.lines.Line2D, xdata=[], ydata=[])
            keys += [
                "markersize", "ms",
                "markeredgewidth", "mew",
                "markeredgecolor", "mec",
                "linestyle", "ls",
                "linewidth", "lw",
            ]

        common_kws = {k: v for k, v in kwargs.items() if k in keys}
        attrs = {"hue": "color", "style": None}
        if kind == "scatter":
            attrs["size"] = "s"
        elif kind == "line":
            attrs["size"] = "linewidth"
        p.add_legend_data(g.axes.flat[0], legend_artist, common_kws, attrs)
        if p.legend_data:
            g.add_legend(legend_data=p.legend_data,
                         label_order=p.legend_order,
                         title=p.legend_title,
                         adjust_subtitles=True)

    # Rename the columns of the FacetGrid's `data` attribute
    # to match the original column names
    orig_cols = {
        f"_{k}": f"_{k}_" if v is None else v for k, v in variables.items()
    }
    grid_data = g.data.rename(columns=orig_cols)
    if data is not None and (x is not None or y is not None):
        if not isinstance(data, pd.DataFrame):
            data = pd.DataFrame(data)
        g.data = pd.merge(
            data,
            grid_data[grid_data.columns.difference(data.columns)],
            left_index=True,
            right_index=True,
        )
    else:
        g.data = grid_data

    return g


relplot.__doc__ = """\
Figure-level interface for drawing relational plots onto a FacetGrid.

This function provides access to several different axes-level functions
that show the relationship between two variables with semantic mappings
of subsets. The `kind` parameter selects the underlying axes-level
function to use:

- :func:`scatterplot` (with `kind="scatter"`; the default)
- :func:`lineplot` (with `kind="line"`)

Extra keyword arguments are passed to the underlying function, so you
should refer to the documentation for each to see kind-specific options.

{narrative.main_api}

{narrative.relational_semantic}

After plotting, the :class:`FacetGrid` with the plot is returned and can
be used directly to tweak supporting plot details or add other layers.

Parameters
----------
{params.core.data}
{params.core.xy}
hue : vector or key in `data`
    Grouping variable that will produce elements with different colors.
    Can be either categorical or numeric, although color mapping will
    behave differently in latter case.
size : vector or key in `data`
    Grouping variable that will produce elements with different sizes.
    Can be either categorical or numeric, although size mapping will
    behave differently in latter case.
style : vector or key in `data`
    Grouping variable that will produce elements with different styles.
    Can have a numeric dtype but will always be treated as categorical.
{params.rel.units}
weights : vector or key in `data`
    Data values or column used to compute weighted estimation.
    Note that use of weights currently limits the choice of statistics
    to a 'mean' estimator and 'ci' errorbar.
{params.facets.rowcol}
{params.facets.col_wrap}
row_order, col_order : lists of strings
    Order to organize the rows and/or columns of the grid in, otherwise the
    orders are inferred from the data objects.
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
{params.rel.sizes}
{params.rel.size_order}
{params.rel.size_norm}
{params.rel.style_order}
{params.rel.dashes}
{params.rel.markers}
{params.rel.legend}
kind : string
    Kind of plot to draw, corresponding to a seaborn relational plot.
    Options are `"scatter"` or `"line"`.
{params.facets.height}
{params.facets.aspect}
facet_kws : dict
    Dictionary of other keyword arguments to pass to :class:`FacetGrid`.
kwargs : key, value pairings
    Other keyword arguments are passed through to the underlying plotting
    function.

Returns
-------
{returns.facetgrid}

Examples
--------

.. include:: ../docstrings/relplot.rst

""".format(
    narrative=_relational_narrative,
    params=_param_docs,
    returns=_core_docs["returns"],
)
