from __future__ import annotations
from itertools import product
from inspect import signature
import warnings
from textwrap import dedent

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt

from ._base import VectorPlotter, variable_type, categorical_order
from ._core.data import handle_data_source
from ._compat import share_axis, get_legend_handles
from . import utils
from .utils import (
    adjust_legend_subtitles,
    set_hls_values,
    _check_argument,
    _draw_figure,
    _disable_autolayout
)
from .palettes import color_palette, blend_palette
from ._docstrings import (
    DocstringComponents,
    _core_docs,
)

__all__ = ["FacetGrid", "PairGrid", "JointGrid", "pairplot", "jointplot"]


_param_docs = DocstringComponents.from_nested_components(
    core=_core_docs["params"],
)


class _BaseGrid:
    """Base class for grids of subplots."""

    def set(self, **kwargs):
        """Set attributes on each subplot Axes."""
        for ax in self.axes.flat:
            if ax is not None:  # Handle removed axes
                ax.set(**kwargs)
        return self

    @property
    def fig(self):
        """DEPRECATED: prefer the `figure` property."""
        # Grid.figure is preferred because it matches the Axes attribute name.
        # But as the maintanace burden on having this property is minimal,
        # let's be slow about formally deprecating it. For now just note its deprecation
        # in the docstring; add a warning in version 0.13, and eventually remove it.
        return self._figure

    @property
    def figure(self):
        """Access the :class:`matplotlib.figure.Figure` object underlying the grid."""
        return self._figure

    def apply(self, func, *args, **kwargs):
        """
        Pass the grid to a user-supplied function and return self.

        The `func` must accept an object of this type for its first
        positional argument. Additional arguments are passed through.
        The return value of `func` is ignored; this method returns self.
        See the `pipe` method if you want the return value.

        Added in v0.12.0.

        """
        func(self, *args, **kwargs)
        return self

    def pipe(self, func, *args, **kwargs):
        """
        Pass the grid to a user-supplied function and return its value.

        The `func` must accept an object of this type for its first
        positional argument. Additional arguments are passed through.
        The return value of `func` becomes the return value of this method.
        See the `apply` method if you want to return self instead.

        Added in v0.12.0.

        """
        return func(self, *args, **kwargs)

    def savefig(self, *args, **kwargs):
        """
        Save an image of the plot.

        This wraps :meth:`matplotlib.figure.Figure.savefig`, using bbox_inches="tight"
        by default. Parameters are passed through to the matplotlib function.

        """
        kwargs = kwargs.copy()
        kwargs.setdefault("bbox_inches", "tight")
        self.figure.savefig(*args, **kwargs)


class Grid(_BaseGrid):
    """A grid that can have multiple subplots and an external legend."""
    _margin_titles = False
    _legend_out = True

    def __init__(self):

        self._tight_layout_rect = [0, 0, 1, 1]
        self._tight_layout_pad = None

        # This attribute is set externally and is a hack to handle newer functions that
        # don't add proxy artists onto the Axes. We need an overall cleaner approach.
        self._extract_legend_handles = False

    def tight_layout(self, *args, **kwargs):
        """Call fig.tight_layout within rect that exclude the legend."""
        kwargs = kwargs.copy()
        kwargs.setdefault("rect", self._tight_layout_rect)
        if self._tight_layout_pad is not None:
            kwargs.setdefault("pad", self._tight_layout_pad)
        self._figure.tight_layout(*args, **kwargs)
        return self

    def add_legend(self, legend_data=None, title=None, label_order=None,
                   adjust_subtitles=False, **kwargs):
        """Draw a legend, maybe placing it outside axes and resizing the figure.

        Parameters
        ----------
        legend_data : dict
            Dictionary mapping label names (or two-element tuples where the
            second element is a label name) to matplotlib artist handles. The
            default reads from ``self._legend_data``.
        title : string
            Title for the legend. The default reads from ``self._hue_var``.
        label_order : list of labels
            The order that the legend entries should appear in. The default
            reads from ``self.hue_names``.
        adjust_subtitles : bool
            If True, modify entries with invisible artists to left-align
            the labels and set the font size to that of a title.
        kwargs : key, value pairings
            Other keyword arguments are passed to the underlying legend methods
            on the Figure or Axes object.

        Returns
        -------
        self : Grid instance
            Returns self for easy chaining.

        """
        # Find the data for the legend
        if legend_data is None:
            legend_data = self._legend_data
        if label_order is None:
            if self.hue_names is None:
                label_order = list(legend_data.keys())
            else:
                label_order = list(map(utils.to_utf8, self.hue_names))

        blank_handle = mpl.patches.Patch(alpha=0, linewidth=0)
        handles = [legend_data.get(lab, blank_handle) for lab in label_order]
        title = self._hue_var if title is None else title
        title_size = mpl.rcParams["legend.title_fontsize"]

        # Unpack nested labels from a hierarchical legend
        labels = []
        for entry in label_order:
            if isinstance(entry, tuple):
                _, label = entry
            else:
                label = entry
            labels.append(label)

        # Set default legend kwargs
        kwargs.setdefault("scatterpoints", 1)

        if self._legend_out:

            kwargs.setdefault("frameon", False)
            kwargs.setdefault("loc", "center right")

            # Draw a full-figure legend outside the grid
            figlegend = self._figure.legend(handles, labels, **kwargs)

            self._legend = figlegend
            figlegend.set_title(title, prop={"size": title_size})

            if adjust_subtitles:
                adjust_legend_subtitles(figlegend)

            # Draw the plot to set the bounding boxes correctly
            _draw_figure(self._figure)

            # Calculate and set the new width of the figure so the legend fits
            legend_width = figlegend.get_window_extent().width / self._figure.dpi
            fig_width, fig_height = self._figure.get_size_inches()
            self._figure.set_size_inches(fig_width + legend_width, fig_height)

            # Draw the plot again to get the new transformations
            _draw_figure(self._figure)

            # Now calculate how much space we need on the right side
            legend_width = figlegend.get_window_extent().width / self._figure.dpi
            space_needed = legend_width / (fig_width + legend_width)
            margin = .04 if self._margin_titles else .01
            self._space_needed = margin + space_needed
            right = 1 - self._space_needed

            # Place the subplot axes to give space for the legend
            self._figure.subplots_adjust(right=right)
            self._tight_layout_rect[2] = right

        else:
            # Draw a legend in the first axis
            ax = self.axes.flat[0]
            kwargs.setdefault("loc", "best")

            leg = ax.legend(handles, labels, **kwargs)
            leg.set_title(title, prop={"size": title_size})
            self._legend = leg

            if adjust_subtitles:
                adjust_legend_subtitles(leg)

        return self

    def _update_legend_data(self, ax):
        """Extract the legend data from an axes object and save it."""
        data = {}

        # Get data directly from the legend, which is necessary
        # for newer functions that don't add labeled proxy artists
        if ax.legend_ is not None and self._extract_legend_handles:
            handles = get_legend_handles(ax.legend_)
            labels = [t.get_text() for t in ax.legend_.texts]
            data.update({label: handle for handle, label in zip(handles, labels)})

        handles, labels = ax.get_legend_handles_labels()
        data.update({label: handle for handle, label in zip(handles, labels)})

        self._legend_data.update(data)

        # Now clear the legend
        ax.legend_ = None

    def _get_palette(self, data, hue, hue_order, palette):
        """Get a list of colors for the hue variable."""
        if hue is None:
            palette = color_palette(n_colors=1)

        else:
            hue_names = categorical_order(data[hue], hue_order)
            n_colors = len(hue_names)

            # By default use either the current color palette or HUSL
            if palette is None:
                current_palette = utils.get_color_cycle()
                if n_colors > len(current_palette):
                    colors = color_palette("husl", n_colors)
                else:
                    colors = color_palette(n_colors=n_colors)

            # Allow for palette to map from hue variable names
            elif isinstance(palette, dict):
                color_names = [palette[h] for h in hue_names]
                colors = color_palette(color_names, n_colors)

            # Otherwise act as if we just got a list of colors
            else:
                colors = color_palette(palette, n_colors)

            palette = color_palette(colors, n_colors)

        return palette

    @property
    def legend(self):
        """The :class:`matplotlib.legend.Legend` object, if present."""
        try:
            return self._legend
        except AttributeError:
            return None

    def tick_params(self, axis='both', **kwargs):
        """Modify the ticks, tick labels, and gridlines.

        Parameters
        ----------
        axis : {'x', 'y', 'both'}
            The axis on which to apply the formatting.
        kwargs : keyword arguments
            Additional keyword arguments to pass to
            :meth:`matplotlib.axes.Axes.tick_params`.

        Returns
        -------
        self : Grid instance
            Returns self for easy chaining.

        """
        for ax in self.figure.axes:
            ax.tick_params(axis=axis, **kwargs)
        return self


_facet_docs = dict(

    data=dedent("""\
    data : DataFrame
        Tidy ("long-form") dataframe where each column is a variable and each
        row is an observation.\
    """),
    rowcol=dedent("""\
    row, col : vectors or keys in ``data``
        Variables that define subsets to plot on different facets.\
    """),
    rowcol_order=dedent("""\
    {row,col}_order : vector of strings
        Specify the order in which levels of the ``row`` and/or ``col`` variables
        appear in the grid of subplots.\
    """),
    col_wrap=dedent("""\
    col_wrap : int
        "Wrap" the column variable at this width, so that the column facets
        span multiple rows. Incompatible with a ``row`` facet.\
    """),
    share_xy=dedent("""\
    share{x,y} : bool, 'col', or 'row' optional
        If true, the facets will share y axes across columns and/or x axes
        across rows.\
    """),
    height=dedent("""\
    height : scalar
        Height (in inches) of each facet. See also: ``aspect``.\
    """),
    aspect=dedent("""\
    aspect : scalar
        Aspect ratio of each facet, so that ``aspect * height`` gives the width
        of each facet in inches.\
    """),
    palette=dedent("""\
    palette : palette name, list, or dict
        Colors to use for the different levels of the ``hue`` variable. Should
        be something that can be interpreted by :func:`color_palette`, or a
        dictionary mapping hue levels to matplotlib colors.\
    """),
    legend_out=dedent("""\
    legend_out : bool
        If ``True``, the figure size will be extended, and the legend will be
        drawn outside the plot on the center right.\
    """),
    margin_titles=dedent("""\
    margin_titles : bool
        If ``True``, the titles for the row variable are drawn to the right of
        the last column. This option is experimental and may not work in all
        cases.\
    """),
    facet_kws=dedent("""\
    facet_kws : dict
        Additional parameters passed to :class:`FacetGrid`.
    """),
)


class FacetGrid(Grid):
    """Multi-plot grid for plotting conditional relationships."""

    def __init__(
        self, data, *,
        row=None, col=None, hue=None, col_wrap=None,
        sharex=True, sharey=True, height=3, aspect=1, palette=None,
        row_order=None, col_order=None, hue_order=None, hue_kws=None,
        dropna=False, legend_out=True, despine=True,
        margin_titles=False, xlim=None, ylim=None, subplot_kws=None,
        gridspec_kws=None,
    ):

        super().__init__()
        data = handle_data_source(data)

        # Determine the hue facet layer information
        hue_var = hue
        if hue is None:
            hue_names = None
        else:
            hue_names = categorical_order(data[hue], hue_order)

        colors = self._get_palette(data, hue, hue_order, palette)

        # Set up the lists of names for the row and column facet variables
        if row is None:
            row_names = []
        else:
            row_names = categorical_order(data[row], row_order)

        if col is None:
            col_names = []
        else:
            col_names = categorical_order(data[col], col_order)

        # Additional dict of kwarg -> list of values for mapping the hue var
        hue_kws = hue_kws if hue_kws is not None else {}

        # Make a boolean mask that is True anywhere there is an NA
        # value in one of the faceting variables, but only if dropna is True
        none_na = np.zeros(len(data), bool)
        if dropna:
            row_na = none_na if row is None else data[row].isnull()
            col_na = none_na if col is None else data[col].isnull()
            hue_na = none_na if hue is None else data[hue].isnull()
            not_na = ~(row_na | col_na | hue_na)
        else:
            not_na = ~none_na

        # Compute the grid shape
        ncol = 1 if col is None else len(col_names)
        nrow = 1 if row is None else len(row_names)
        self._n_facets = ncol * nrow

        self._col_wrap = col_wrap
        if col_wrap is not None:
            if row is not None:
                err = "Cannot use `row` and `col_wrap` together."
                raise ValueError(err)
            ncol = col_wrap
            nrow = int(np.ceil(len(col_names) / col_wrap))
        self._ncol = ncol
        self._nrow = nrow

        # Calculate the base figure size
        # This can get stretched later by a legend
        # TODO this doesn't account for axis labels
        figsize = (ncol * height * aspect, nrow * height)

        # Validate some inputs
        if col_wrap is not None:
            margin_titles = False

        # Build the subplot keyword dictionary
        subplot_kws = {} if subplot_kws is None else subplot_kws.copy()
        gridspec_kws = {} if gridspec_kws is None else gridspec_kws.copy()
        if xlim is not None:
            subplot_kws["xlim"] = xlim
        if ylim is not None:
            subplot_kws["ylim"] = ylim

        # --- Initialize the subplot grid

        with _disable_autolayout():
            fig = plt.figure(figsize=figsize)

        if col_wrap is None:

            kwargs = dict(squeeze=False,
                          sharex=sharex, sharey=sharey,
                          subplot_kw=subplot_kws,
                          gridspec_kw=gridspec_kws)

            axes = fig.subplots(nrow, ncol, **kwargs)

            if col is None and row is None:
                axes_dict = {}
            elif col is None:
                axes_dict = dict(zip(row_names, axes.flat))
            elif row is None:
                axes_dict = dict(zip(col_names, axes.flat))
            else:
                facet_product = product(row_names, col_names)
                axes_dict = dict(zip(facet_product, axes.flat))

        else:

            # If wrapping the col variable we need to make the grid ourselves
            if gridspec_kws:
                warnings.warn("`gridspec_kws` ignored when using `col_wrap`")

            n_axes = len(col_names)
            axes = np.empty(n_axes, object)
            axes[0] = fig.add_subplot(nrow, ncol, 1, **subplot_kws)
            if sharex:
                subplot_kws["sharex"] = axes[0]
            if sharey:
                subplot_kws["sharey"] = axes[0]
            for i in range(1, n_axes):
                axes[i] = fig.add_subplot(nrow, ncol, i + 1, **subplot_kws)

            axes_dict = dict(zip(col_names, axes))

        # --- Set up the class attributes

        # Attributes that are part of the public API but accessed through
        # a  property so that Sphinx adds them to the auto class doc
        self._figure = fig
        self._axes = axes
        self._axes_dict = axes_dict
        self._legend = None

        # Public attributes that aren't explicitly documented
        # (It's not obvious that having them be public was a good idea)
        self.data = data
        self.row_names = row_names
        self.col_names = col_names
        self.hue_names = hue_names
        self.hue_kws = hue_kws

        # Next the private variables
        self._nrow = nrow
        self._row_var = row
        self._ncol = ncol
        self._col_var = col

        self._margin_titles = margin_titles
        self._margin_titles_texts = []
        self._col_wrap = col_wrap
        self._hue_var = hue_var
        self._colors = colors
        self._legend_out = legend_out
        self._legend_data = {}
        self._x_var = None
        self._y_var = None
        self._sharex = sharex
        self._sharey = sharey
        self._dropna = dropna
        self._not_na = not_na

        # --- Make the axes look good

        self.set_titles()
        self.tight_layout()

        if despine:
            self.despine()

        if sharex in [True, 'col']:
            for ax in self._not_bottom_axes:
                for label in ax.get_xticklabels():
                    label.set_visible(False)
                ax.xaxis.offsetText.set_visible(False)
                ax.xaxis.label.set_visible(False)

        if sharey in [True, 'row']:
            for ax in self._not_left_axes:
                for label in ax.get_yticklabels():
                    label.set_visible(False)
                ax.yaxis.offsetText.set_visible(False)
                ax.yaxis.label.set_visible(False)

    __init__.__doc__ = dedent("""\
        Initialize the matplotlib figure and FacetGrid object.

        This class maps a dataset onto multiple axes arrayed in a grid of rows
        and columns that correspond to *levels* of variables in the dataset.
        The plots it produces are often called "lattice", "trellis", or
        "small-multiple" graphics.

        It can also represent levels of a third variable with the ``hue``
        parameter, which plots different subsets of data in different colors.
        This uses color to resolve elements on a third dimension, but only
        draws subsets on top of each other and will not tailor the ``hue``
        parameter for the specific visualization the way that axes-level
        functions that accept ``hue`` will.

        The basic workflow is to initialize the :class:`FacetGrid` object with
        the dataset and the variables that are used to structure the grid. Then
        one or more plotting functions can be applied to each subset by calling
        :meth:`FacetGrid.map` or :meth:`FacetGrid.map_dataframe`. Finally, the
        plot can be tweaked with other methods to do things like change the
        axis labels, use different ticks, or add a legend. See the detailed
        code examples below for more information.

        .. warning::

            When using seaborn functions that infer semantic mappings from a
            dataset, care must be taken to synchronize those mappings across
            facets (e.g., by defining the ``hue`` mapping with a palette dict or
            setting the data type of the variables to ``category``). In most cases,
            it will be better to use a figure-level function (e.g. :func:`relplot`
            or :func:`catplot`) than to use :class:`FacetGrid` directly.

        See the :ref:`tutorial <grid_tutorial>` for more information.

        Parameters
        ----------
        {data}
        row, col, hue : strings
            Variables that define subsets of the data, which will be drawn on
            separate facets in the grid. See the ``{{var}}_order`` parameters to
            control the order of levels of this variable.
        {col_wrap}
        {share_xy}
        {height}
        {aspect}
        {palette}
        {{row,col,hue}}_order : lists
            Order for the levels of the faceting variables. By default, this
            will be the order that the levels appear in ``data`` or, if the
            variables are pandas categoricals, the category order.
        hue_kws : dictionary of param -> list of values mapping
            Other keyword arguments to insert into the plotting call to let
            other plot attributes vary across levels of the hue variable (e.g.
            the markers in a scatterplot).
        {legend_out}
        despine : boolean
            Remove the top and right spines from the plots.
        {margin_titles}
        {{x, y}}lim: tuples
            Limits for each of the axes on each facet (only relevant when
            share{{x, y}} is True).
        subplot_kws : dict
            Dictionary of keyword arguments passed to matplotlib subplot(s)
            methods.
        gridspec_kws : dict
            Dictionary of keyword arguments passed to
            :class:`matplotlib.gridspec.GridSpec`
            (via :meth:`matplotlib.figure.Figure.subplots`).
            Ignored if ``col_wrap`` is not ``None``.

        See Also
        --------
        PairGrid : Subplot grid for plotting pairwise relationships
        relplot : Combine a relational plot and a :class:`FacetGrid`
        displot : Combine a distribution plot and a :class:`FacetGrid`
        catplot : Combine a categorical plot and a :class:`FacetGrid`
        lmplot : Combine a regression plot and a :class:`FacetGrid`

        Examples
        --------

        .. note::

            These examples use seaborn functions to demonstrate some of the
            advanced features of the class, but in most cases you will want
            to use figue-level functions (e.g. :func:`displot`, :func:`relplot`)
            to make the plots shown here.

        .. include:: ../docstrings/FacetGrid.rst

        """).format(**_facet_docs)

    def facet_data(self):
        """Generator for name indices and data subsets for each facet.

        Yields
        ------
        (i, j, k), data_ijk : tuple of ints, DataFrame
            The ints provide an index into the {row, col, hue}_names attribute,
            and the dataframe contains a subset of the full data corresponding
            to each facet. The generator yields subsets that correspond with
            the self.axes.flat iterator, or self.axes[i, j] when `col_wrap`
            is None.

        """
        data = self.data

        # Construct masks for the row variable
        if self.row_names:
            row_masks = [data[self._row_var] == n for n in self.row_names]
        else:
            row_masks = [np.repeat(True, len(self.data))]

        # Construct masks for the column variable
        if self.col_names:
            col_masks = [data[self._col_var] == n for n in self.col_names]
        else:
            col_masks = [np.repeat(True, len(self.data))]

        # Construct masks for the hue variable
        if self.hue_names:
            hue_masks = [data[self._hue_var] == n for n in self.hue_names]
        else:
            hue_masks = [np.repeat(True, len(self.data))]

        # Here is the main generator loop
        for (i, row), (j, col), (k, hue) in product(enumerate(row_masks),
                                                    enumerate(col_masks),
                                                    enumerate(hue_masks)):
            data_ijk = data[row & col & hue & self._not_na]
            yield (i, j, k), data_ijk

    def map(self, func, *args, **kwargs):
        """Apply a plotting function to each facet's subset of the data.

        Parameters
        ----------
        func : callable
            A plotting function that takes data and keyword arguments. It
            must plot to the currently active matplotlib Axes and take a
            `color` keyword argument. If faceting on the `hue` dimension,
            it must also take a `label` keyword argument.
        args : strings
            Column names in self.data that identify variables with data to
            plot. The data for each variable is passed to `func` in the
            order the variables are specified in the call.
        kwargs : keyword arguments
            All keyword arguments are passed to the plotting function.

        Returns
        -------
        self : object
            Returns self.

        """
        # If color was a keyword argument, grab it here
        kw_color = kwargs.pop("color", None)

        # How we use the function depends on where it comes from
        func_module = str(getattr(func, "__module__", ""))

        # Check for categorical plots without order information
        if func_module == "seaborn.categorical":
            if "order" not in kwargs:
                warning = ("Using the {} function without specifying "
                           "`order` is likely to produce an incorrect "
                           "plot.".format(func.__name__))
                warnings.warn(warning)
            if len(args) == 3 and "hue_order" not in kwargs:
                warning = ("Using the {} function without specifying "
                           "`hue_order` is likely to produce an incorrect "
                           "plot.".format(func.__name__))
                warnings.warn(warning)

        # Iterate over the data subsets
        for (row_i, col_j, hue_k), data_ijk in self.facet_data():

            # If this subset is null, move on
            if not data_ijk.values.size:
                continue

            # Get the current axis
            modify_state = not func_module.startswith("seaborn")
            ax = self.facet_axis(row_i, col_j, modify_state)

            # Decide what color to plot with
            kwargs["color"] = self._facet_color(hue_k, kw_color)

            # Insert the other hue aesthetics if appropriate
            for kw, val_list in self.hue_kws.items():
                kwargs[kw] = val_list[hue_k]

            # Insert a label in the keyword arguments for the legend
            if self._hue_var is not None:
                kwargs["label"] = utils.to_utf8(self.hue_names[hue_k])

            # Get the actual data we are going to plot with
            plot_data = data_ijk[list(args)]
            if self._dropna:
                plot_data = plot_data.dropna()
            plot_args = [v for k, v in plot_data.items()]

            # Some matplotlib functions don't handle pandas objects correctly
            if func_module.startswith("matplotlib"):
                plot_args = [v.values for v in plot_args]

            # Draw the plot
            self._facet_plot(func, ax, plot_args, kwargs)

        # Finalize the annotations and layout
        self._finalize_grid(args[:2])

        return self

    def map_dataframe(self, func, *args, **kwargs):
        """Like ``.map`` but passes args as strings and inserts data in kwargs.

        This method is suitable for plotting with functions that accept a
        long-form DataFrame as a `data` keyword argument and access the
        data in that DataFrame using string variable names.

        Parameters
        ----------
        func : callable
            A plotting function that takes data and keyword arguments. Unlike
            the `map` method, a function used here must "understand" Pandas
            objects. It also must plot to the currently active matplotlib Axes
            and take a `color` keyword argument. If faceting on the `hue`
            dimension, it must also take a `label` keyword argument.
        args : strings
            Column names in self.data that identify variables with data to
            plot. The data for each variable is passed to `func` in the
            order the variables are specified in the call.
        kwargs : keyword arguments
            All keyword arguments are passed to the plotting function.

        Returns
        -------
        self : object
            Returns self.

        """

        # If color was a keyword argument, grab it here
        kw_color = kwargs.pop("color", None)

        # Iterate over the data subsets
        for (row_i, col_j, hue_k), data_ijk in self.facet_data():

            # If this subset is null, move on
            if not data_ijk.values.size:
                continue

            # Get the current axis
            modify_state = not str(func.__module__).startswith("seaborn")
            ax = self.facet_axis(row_i, col_j, modify_state)

            # Decide what color to plot with
            kwargs["color"] = self._facet_color(hue_k, kw_color)

            # Insert the other hue aesthetics if appropriate
            for kw, val_list in self.hue_kws.items():
                kwargs[kw] = val_list[hue_k]

            # Insert a label in the keyword arguments for the legend
            if self._hue_var is not None:
                kwargs["label"] = self.hue_names[hue_k]

            # Stick the facet dataframe into the kwargs
            if self._dropna:
                data_ijk = data_ijk.dropna()
            kwargs["data"] = data_ijk

            # Draw the plot
            self._facet_plot(func, ax, args, kwargs)

        # For axis labels, prefer to use positional args for backcompat
        # but also extract the x/y kwargs and use if no corresponding arg
        axis_labels = [kwargs.get("x", None), kwargs.get("y", None)]
        for i, val in enumerate(args[:2]):
            axis_labels[i] = val
        self._finalize_grid(axis_labels)

        return self

    def _facet_color(self, hue_index, kw_color):

        color = self._colors[hue_index]
        if kw_color is not None:
            return kw_color
        elif color is not None:
            return color

    def _facet_plot(self, func, ax, plot_args, plot_kwargs):

        # Draw the plot
        if str(func.__module__).startswith("seaborn"):
            plot_kwargs = plot_kwargs.copy()
            semantics = ["x", "y", "hue", "size", "style"]
            for key, val in zip(semantics, plot_args):
                plot_kwargs[key] = val
            plot_args = []
            plot_kwargs["ax"] = ax
        func(*plot_args, **plot_kwargs)

        # Sort out the supporting information
        self._update_legend_data(ax)

    def _finalize_grid(self, axlabels):
        """Finalize the annotations and layout."""
        self.set_axis_labels(*axlabels)
        self.tight_layout()

    def facet_axis(self, row_i, col_j, modify_state=True):
        """Make the axis identified by these indices active and return it."""

        # Calculate the actual indices of the axes to plot on
        if self._col_wrap is not None:
            ax = self.axes.flat[col_j]
        else:
            ax = self.axes[row_i, col_j]

        # Get a reference to the axes object we want, and make it active
        if modify_state:
            plt.sca(ax)
        return ax

    def despine(self, **kwargs):
        """Remove axis spines from the facets."""
        utils.despine(self._figure, **kwargs)
        return self

    def set_axis_labels(self, x_var=None, y_var=None, clear_inner=True, **kwargs):
        """Set axis labels on the left column and bottom row of the grid."""
        if x_var is not None:
            self._x_var = x_var
            self.set_xlabels(x_var, clear_inner=clear_inner, **kwargs)
        if y_var is not None:
            self._y_var = y_var
            self.set_ylabels(y_var, clear_inner=clear_inner, **kwargs)

        return self

    def set_xlabels(self, label=None, clear_inner=True, **kwargs):
        """Label the x axis on the bottom row of the grid."""
        if label is None:
            label = self._x_var
        for ax in self._bottom_axes:
            ax.set_xlabel(label, **kwargs)
        if clear_inner:
            for ax in self._not_bottom_axes:
                ax.set_xlabel("")
        return self

    def set_ylabels(self, label=None, clear_inner=True, **kwargs):
        """Label the y axis on the left column of the grid."""
        if label is None:
            label = self._y_var
        for ax in self._left_axes:
            ax.set_ylabel(label, **kwargs)
        if clear_inner:
            for ax in self._not_left_axes:
                ax.set_ylabel("")
        return self

    def set_xticklabels(self, labels=None, step=None, **kwargs):
        """Set x axis tick labels of the grid."""
        for ax in self.axes.flat:
            curr_ticks = ax.get_xticks()
            ax.set_xticks(curr_ticks)
            if labels is None:
                curr_labels = [label.get_text() for label in ax.get_xticklabels()]
                if step is not None:
                    xticks = ax.get_xticks()[::step]
                    curr_labels = curr_labels[::step]
                    ax.set_xticks(xticks)
                ax.set_xticklabels(curr_labels, **kwargs)
            else:
                ax.set_xticklabels(labels, **kwargs)
        return self

    def set_yticklabels(self, labels=None, **kwargs):
        """Set y axis tick labels on the left column of the grid."""
        for ax in self.axes.flat:
            curr_ticks = ax.get_yticks()
            ax.set_yticks(curr_ticks)
            if labels is None:
                curr_labels = [label.get_text() for label in ax.get_yticklabels()]
                ax.set_yticklabels(curr_labels, **kwargs)
            else:
                ax.set_yticklabels(labels, **kwargs)
        return self

    def set_titles(self, template=None, row_template=None, col_template=None, **kwargs):
        """Draw titles either above each facet or on the grid margins.

        Parameters
        ----------
        template : string
            Template for all titles with the formatting keys {col_var} and
            {col_name} (if using a `col` faceting variable) and/or {row_var}
            and {row_name} (if using a `row` faceting variable).
        row_template:
            Template for the row variable when titles are drawn on the grid
            margins. Must have {row_var} and {row_name} formatting keys.
        col_template:
            Template for the column variable when titles are drawn on the grid
            margins. Must have {col_var} and {col_name} formatting keys.

        Returns
        -------
        self: object
            Returns self.

        """
        args = dict(row_var=self._row_var, col_var=self._col_var)
        kwargs["size"] = kwargs.pop("size", mpl.rcParams["axes.labelsize"])

        # Establish default templates
        if row_template is None:
            row_template = "{row_var} = {row_name}"
        if col_template is None:
            col_template = "{col_var} = {col_name}"
        if template is None:
            if self._row_var is None:
                template = col_template
            elif self._col_var is None:
                template = row_template
            else:
                template = " | ".join([row_template, col_template])

        row_template = utils.to_utf8(row_template)
        col_template = utils.to_utf8(col_template)
        template = utils.to_utf8(template)

        if self._margin_titles:

            # Remove any existing title texts
            for text in self._margin_titles_texts:
                text.remove()
            self._margin_titles_texts = []

            if self.row_names is not None:
                # Draw the row titles on the right edge of the grid
                for i, row_name in enumerate(self.row_names):
                    ax = self.axes[i, -1]
                    args.update(dict(row_name=row_name))
                    title = row_template.format(**args)
                    text = ax.annotate(
                        title, xy=(1.02, .5), xycoords="axes fraction",
                        rotation=270, ha="left", va="center",
                        **kwargs
                    )
                    self._margin_titles_texts.append(text)

            if self.col_names is not None:
                # Draw the column titles  as normal titles
                for j, col_name in enumerate(self.col_names):
                    args.update(dict(col_name=col_name))
                    title = col_template.format(**args)
                    self.axes[0, j].set_title(title, **kwargs)

            return self

        # Otherwise title each facet with all the necessary information
        if (self._row_var is not None) and (self._col_var is not None):
            for i, row_name in enumerate(self.row_names):
                for j, col_name in enumerate(self.col_names):
                    args.update(dict(row_name=row_name, col_name=col_name))
                    title = template.format(**args)
                    self.axes[i, j].set_title(title, **kwargs)
        elif self.row_names is not None and len(self.row_names):
            for i, row_name in enumerate(self.row_names):
                args.update(dict(row_name=row_name))
                title = template.format(**args)
                self.axes[i, 0].set_title(title, **kwargs)
        elif self.col_names is not None and len(self.col_names):
            for i, col_name in enumerate(self.col_names):
                args.update(dict(col_name=col_name))
                title = template.format(**args)
                # Index the flat array so col_wrap works
                self.axes.flat[i].set_title(title, **kwargs)
        return self

    def refline(self, *, x=None, y=None, color='.5', linestyle='--', **line_kws):
        """Add a reference line(s) to each facet.

        Parameters
        ----------
        x, y : numeric
            Value(s) to draw the line(s) at.
        color : :mod:`matplotlib color <matplotlib.colors>`
            Specifies the color of the reference line(s). Pass ``color=None`` to
            use ``hue`` mapping.
        linestyle : str
            Specifies the style of the reference line(s).
        line_kws : key, value mappings
            Other keyword arguments are passed to :meth:`matplotlib.axes.Axes.axvline`
            when ``x`` is not None and :meth:`matplotlib.axes.Axes.axhline` when ``y``
            is not None.

        Returns
        -------
        :class:`FacetGrid` instance
            Returns ``self`` for easy method chaining.

        """
        line_kws['color'] = color
        line_kws['linestyle'] = linestyle

        if x is not None:
            self.map(plt.axvline, x=x, **line_kws)

        if y is not None:
            self.map(plt.axhline, y=y, **line_kws)

        return self

    # ------ Properties that are part of the public API and documented by Sphinx

    @property
    def axes(self):
        """An array of the :class:`matplotlib.axes.Axes` objects in the grid."""
        return self._axes

    @property
    def ax(self):
        """The :class:`matplotlib.axes.Axes` when no faceting variables are assigned."""
        if self.axes.shape == (1, 1):
            return self.axes[0, 0]
        else:
            err = (
                "Use the `.axes` attribute when facet variables are assigned."
            )
            raise AttributeError(err)

    @property
    def axes_dict(self):
        """A mapping of facet names to corresponding :class:`matplotlib.axes.Axes`.

        If only one of ``row`` or ``col`` is assigned, each key is a string
        representing a level of that variable. If both facet dimensions are
        assigned, each key is a ``({row_level}, {col_level})`` tuple.

        """
        return self._axes_dict

    # ------ Private properties, that require some computation to get

    @property
    def _inner_axes(self):
        """Return a flat array of the inner axes."""
        if self._col_wrap is None:
            return self.axes[:-1, 1:].flat
        else:
            axes = []
            n_empty = self._nrow * self._ncol - self._n_facets
            for i, ax in enumerate(self.axes):
                append = (
                    i % self._ncol
                    and i < (self._ncol * (self._nrow - 1))
                    and i < (self._ncol * (self._nrow - 1) - n_empty)
                )
                if append:
                    axes.append(ax)
            return np.array(axes, object).flat

    @property
    def _left_axes(self):
        """Return a flat array of the left column of axes."""
        if self._col_wrap is None:
            return self.axes[:, 0].flat
        else:
            axes = []
            for i, ax in enumerate(self.axes):
                if not i % self._ncol:
                    axes.append(ax)
            return np.array(axes, object).flat

    @property
    def _not_left_axes(self):
        """Return a flat array of axes that aren't on the left column."""
        if self._col_wrap is None:
            return self.axes[:, 1:].flat
        else:
            axes = []
            for i, ax in enumerate(self.axes):
                if i % self._ncol:
                    axes.append(ax)
            return np.array(axes, object).flat

    @property
    def _bottom_axes(self):
        """Return a flat array of the bottom row of axes."""
        if self._col_wrap is None:
            return self.axes[-1, :].flat
        else:
            axes = []
            n_empty = self._nrow * self._ncol - self._n_facets
            for i, ax in enumerate(self.axes):
                append = (
                    i >= (self._ncol * (self._nrow - 1))
                    or i >= (self._ncol * (self._nrow - 1) - n_empty)
                )
                if append:
                    axes.append(ax)
            return np.array(axes, object).flat

    @property
    def _not_bottom_axes(self):
        """Return a flat array of axes that aren't on the bottom row."""
        if self._col_wrap is None:
            return self.axes[:-1, :].flat
        else:
            axes = []
            n_empty = self._nrow * self._ncol - self._n_facets
            for i, ax in enumerate(self.axes):
                append = (
                    i < (self._ncol * (self._nrow - 1))
                    and i < (self._ncol * (self._nrow - 1) - n_empty)
                )
                if append:
                    axes.append(ax)
            return np.array(axes, object).flat


class PairGrid(Grid):
    """Subplot grid for plotting pairwise relationships in a dataset.

    This object maps each variable in a dataset onto a column and row in a
    grid of multiple axes. Different axes-level plotting functions can be
    used to draw bivariate plots in the upper and lower triangles, and the
    marginal distribution of each variable can be shown on the diagonal.

    Several different common plots can be generated in a single line using
    :func:`pairplot`. Use :class:`PairGrid` when you need more flexibility.

    See the :ref:`tutorial <grid_tutorial>` for more information.

    """
    def __init__(
        self, data, *, hue=None, vars=None, x_vars=None, y_vars=None,
        hue_order=None, palette=None, hue_kws=None, corner=False, diag_sharey=True,
        height=2.5, aspect=1, layout_pad=.5, despine=True, dropna=False,
    ):
        """Initialize the plot figure and PairGrid object.

        Parameters
        ----------
        data : DataFrame
            Tidy (long-form) dataframe where each column is a variable and
            each row is an observation.
        hue : string (variable name)
            Variable in ``data`` to map plot aspects to different colors. This
            variable will be excluded from the default x and y variables.
        vars : list of variable names
            Variables within ``data`` to use, otherwise use every column with
            a numeric datatype.
        {x, y}_vars : lists of variable names
            Variables within ``data`` to use separately for the rows and
            columns of the figure; i.e. to make a non-square plot.
        hue_order : list of strings
            Order for the levels of the hue variable in the palette
        palette : dict or seaborn color palette
            Set of colors for mapping the ``hue`` variable. If a dict, keys
            should be values  in the ``hue`` variable.
        hue_kws : dictionary of param -> list of values mapping
            Other keyword arguments to insert into the plotting call to let
            other plot attributes vary across levels of the hue variable (e.g.
            the markers in a scatterplot).
        corner : bool
            If True, don't add axes to the upper (off-diagonal) triangle of the
            grid, making this a "corner" plot.
        height : scalar
            Height (in inches) of each facet.
        aspect : scalar
            Aspect * height gives the width (in inches) of each facet.
        layout_pad : scalar
            Padding between axes; passed to ``fig.tight_layout``.
        despine : boolean
            Remove the top and right spines from the plots.
        dropna : boolean
            Drop missing values from the data before plotting.

        See Also
        --------
        pairplot : Easily drawing common uses of :class:`PairGrid`.
        FacetGrid : Subplot grid for plotting conditional relationships.

        Examples
        --------

        .. include:: ../docstrings/PairGrid.rst

        """

        super().__init__()
        data = handle_data_source(data)

        # Sort out the variables that define the grid
        numeric_cols = self._find_numeric_cols(data)
        if hue in numeric_cols:
            numeric_cols.remove(hue)
        if vars is not None:
            x_vars = list(vars)
            y_vars = list(vars)
        if x_vars is None:
            x_vars = numeric_cols
        if y_vars is None:
            y_vars = numeric_cols

        if np.isscalar(x_vars):
            x_vars = [x_vars]
        if np.isscalar(y_vars):
            y_vars = [y_vars]

        self.x_vars = x_vars = list(x_vars)
        self.y_vars = y_vars = list(y_vars)
        self.square_grid = self.x_vars == self.y_vars

        if not x_vars:
            raise ValueError("No variables found for grid columns.")
        if not y_vars:
            raise ValueError("No variables found for grid rows.")

        # Create the figure and the array of subplots
        figsize = len(x_vars) * height * aspect, len(y_vars) * height

        with _disable_autolayout():
            fig = plt.figure(figsize=figsize)

        axes = fig.subplots(len(y_vars), len(x_vars),
                            sharex="col", sharey="row",
                            squeeze=False)

        # Possibly remove upper axes to make a corner grid
        # Note: setting up the axes is usually the most time-intensive part
        # of using the PairGrid. We are foregoing the speed improvement that
        # we would get by just not setting up the hidden axes so that we can
        # avoid implementing fig.subplots ourselves. But worth thinking about.
        self._corner = corner
        if corner:
            hide_indices = np.triu_indices_from(axes, 1)
            for i, j in zip(*hide_indices):
                axes[i, j].remove()
                axes[i, j] = None

        self._figure = fig
        self.axes = axes
        self.data = data

        # Save what we are going to do with the diagonal
        self.diag_sharey = diag_sharey
        self.diag_vars = None
        self.diag_axes = None

        self._dropna = dropna

        # Label the axes
        self._add_axis_labels()

        # Sort out the hue variable
        self._hue_var = hue
        if hue is None:
            self.hue_names = hue_order = ["_nolegend_"]
            self.hue_vals = pd.Series(["_nolegend_"] * len(data),
                                      index=data.index)
        else:
            # We need hue_order and hue_names because the former is used to control
            # the order of drawing and the latter is used to control the order of
            # the legend. hue_names can become string-typed while hue_order must
            # retain the type of the input data. This is messy but results from
            # the fact that PairGrid can implement the hue-mapping logic itself
            # (and was originally written exclusively that way) but now can delegate
            # to the axes-level functions, while always handling legend creation.
            # See GH2307
            hue_names = hue_order = categorical_order(data[hue], hue_order)
            if dropna:
                # Filter NA from the list of unique hue names
                hue_names = list(filter(pd.notnull, hue_names))
            self.hue_names = hue_names
            self.hue_vals = data[hue]

        # Additional dict of kwarg -> list of values for mapping the hue var
        self.hue_kws = hue_kws if hue_kws is not None else {}

        self._orig_palette = palette
        self._hue_order = hue_order
        self.palette = self._get_palette(data, hue, hue_order, palette)
        self._legend_data = {}

        # Make the plot look nice
        for ax in axes[:-1, :].flat:
            if ax is None:
                continue
            for label in ax.get_xticklabels():
                label.set_visible(False)
            ax.xaxis.offsetText.set_visible(False)
            ax.xaxis.label.set_visible(False)

        for ax in axes[:, 1:].flat:
            if ax is None:
                continue
            for label in ax.get_yticklabels():
                label.set_visible(False)
            ax.yaxis.offsetText.set_visible(False)
            ax.yaxis.label.set_visible(False)

        self._tight_layout_rect = [.01, .01, .99, .99]
        self._tight_layout_pad = layout_pad
        self._despine = despine
        if despine:
            utils.despine(fig=fig)
        self.tight_layout(pad=layout_pad)

    def map(self, func, **kwargs):
        """Plot with the same function in every subplot.

        Parameters
        ----------
        func : callable plotting function
            Must take x, y arrays as positional arguments and draw onto the
            "currently active" matplotlib Axes. Also needs to accept kwargs
            called ``color`` and  ``label``.

        """
        row_indices, col_indices = np.indices(self.axes.shape)
        indices = zip(row_indices.flat, col_indices.flat)
        self._map_bivariate(func, indices, **kwargs)

        return self

    def map_lower(self, func, **kwargs):
        """Plot with a bivariate function on the lower diagonal subplots.

        Parameters
        ----------
        func : callable plotting function
            Must take x, y arrays as positional arguments and draw onto the
            "currently active" matplotlib Axes. Also needs to accept kwargs
            called ``color`` and  ``label``.

        """
        indices = zip(*np.tril_indices_from(self.axes, -1))
        self._map_bivariate(func, indices, **kwargs)
        return self

    def map_upper(self, func, **kwargs):
        """Plot with a bivariate function on the upper diagonal subplots.

        Parameters
        ----------
        func : callable plotting function
            Must take x, y arrays as positional arguments and draw onto the
            "currently active" matplotlib Axes. Also needs to accept kwargs
            called ``color`` and  ``label``.

        """
        indices = zip(*np.triu_indices_from(self.axes, 1))
        self._map_bivariate(func, indices, **kwargs)
        return self

    def map_offdiag(self, func, **kwargs):
        """Plot with a bivariate function on the off-diagonal subplots.

        Parameters
        ----------
        func : callable plotting function
            Must take x, y arrays as positional arguments and draw onto the
            "currently active" matplotlib Axes. Also needs to accept kwargs
            called ``color`` and  ``label``.

        """
        if self.square_grid:
            self.map_lower(func, **kwargs)
            if not self._corner:
                self.map_upper(func, **kwargs)
        else:
            indices = []
            for i, (y_var) in enumerate(self.y_vars):
                for j, (x_var) in enumerate(self.x_vars):
                    if x_var != y_var:
                        indices.append((i, j))
            self._map_bivariate(func, indices, **kwargs)
        return self

    def map_diag(self, func, **kwargs):
        """Plot with a univariate function on each diagonal subplot.

        Parameters
        ----------
        func : callable plotting function
            Must take an x array as a positional argument and draw onto the
            "currently active" matplotlib Axes. Also needs to accept kwargs
            called ``color`` and  ``label``.

        """
        # Add special diagonal axes for the univariate plot
        if self.diag_axes is None:
            diag_vars = []
            diag_axes = []
            for i, y_var in enumerate(self.y_vars):
                for j, x_var in enumerate(self.x_vars):
                    if x_var == y_var:

                        # Make the density axes
                        diag_vars.append(x_var)
                        ax = self.axes[i, j]
                        diag_ax = ax.twinx()
                        diag_ax.set_axis_off()
                        diag_axes.append(diag_ax)

                        # Work around matplotlib bug
                        # https://github.com/matplotlib/matplotlib/issues/15188
                        if not plt.rcParams.get("ytick.left", True):
                            for tick in ax.yaxis.majorTicks:
                                tick.tick1line.set_visible(False)

                        # Remove main y axis from density axes in a corner plot
                        if self._corner:
                            ax.yaxis.set_visible(False)
                            if self._despine:
                                utils.despine(ax=ax, left=True)
                            # TODO add optional density ticks (on the right)
                            # when drawing a corner plot?

            if self.diag_sharey and diag_axes:
                for ax in diag_axes[1:]:
                    share_axis(diag_axes[0], ax, "y")

            self.diag_vars = diag_vars
            self.diag_axes = diag_axes

        if "hue" not in signature(func).parameters:
            return self._map_diag_iter_hue(func, **kwargs)

        # Loop over diagonal variables and axes, making one plot in each
        for var, ax in zip(self.diag_vars, self.diag_axes):

            plot_kwargs = kwargs.copy()
            if str(func.__module__).startswith("seaborn"):
                plot_kwargs["ax"] = ax
            else:
                plt.sca(ax)

            vector = self.data[var]
            if self._hue_var is not None:
                hue = self.data[self._hue_var]
            else:
                hue = None

            if self._dropna:
                not_na = vector.notna()
                if hue is not None:
                    not_na &= hue.notna()
                vector = vector[not_na]
                if hue is not None:
                    hue = hue[not_na]

            plot_kwargs.setdefault("hue", hue)
            plot_kwargs.setdefault("hue_order", self._hue_order)
            plot_kwargs.setdefault("palette", self._orig_palette)
            func(x=vector, **plot_kwargs)
            ax.legend_ = None

        self._add_axis_labels()
        return self

    def _map_diag_iter_hue(self, func, **kwargs):
        """Put marginal plot on each diagonal axes, iterating over hue."""
        # Plot on each of the diagonal axes
        fixed_color = kwargs.pop("color", None)

        for var, ax in zip(self.diag_vars, self.diag_axes):
            hue_grouped = self.data[var].groupby(self.hue_vals, observed=True)

            plot_kwargs = kwargs.copy()
            if str(func.__module__).startswith("seaborn"):
                plot_kwargs["ax"] = ax
            else:
                plt.sca(ax)

            for k, label_k in enumerate(self._hue_order):

                # Attempt to get data for this level, allowing for empty
                try:
                    data_k = hue_grouped.get_group(label_k)
                except KeyError:
                    data_k = pd.Series([], dtype=float)

                if fixed_color is None:
                    color = self.palette[k]
                else:
                    color = fixed_color

                if self._dropna:
                    data_k = utils.remove_na(data_k)

                if str(func.__module__).startswith("seaborn"):
                    func(x=data_k, label=label_k, color=color, **plot_kwargs)
                else:
                    func(data_k, label=label_k, color=color, **plot_kwargs)

        self._add_axis_labels()

        return self

    def _map_bivariate(self, func, indices, **kwargs):
        """Draw a bivariate plot on the indicated axes."""
        # This is a hack to handle the fact that new distribution plots don't add
        # their artists onto the axes. This is probably superior in general, but
        # we'll need a better way to handle it in the axisgrid functions.
        from .distributions import histplot, kdeplot
        if func is histplot or func is kdeplot:
            self._extract_legend_handles = True

        kws = kwargs.copy()  # Use copy as we insert other kwargs
        for i, j in indices:
            x_var = self.x_vars[j]
            y_var = self.y_vars[i]
            ax = self.axes[i, j]
            if ax is None:  # i.e. we are in corner mode
                continue
            self._plot_bivariate(x_var, y_var, ax, func, **kws)
        self._add_axis_labels()

        if "hue" in signature(func).parameters:
            self.hue_names = list(self._legend_data)

    def _plot_bivariate(self, x_var, y_var, ax, func, **kwargs):
        """Draw a bivariate plot on the specified axes."""
        if "hue" not in signature(func).parameters:
            self._plot_bivariate_iter_hue(x_var, y_var, ax, func, **kwargs)
            return

        kwargs = kwargs.copy()
        if str(func.__module__).startswith("seaborn"):
            kwargs["ax"] = ax
        else:
            plt.sca(ax)

        if x_var == y_var:
            axes_vars = [x_var]
        else:
            axes_vars = [x_var, y_var]

        if self._hue_var is not None and self._hue_var not in axes_vars:
            axes_vars.append(self._hue_var)

        data = self.data[axes_vars]
        if self._dropna:
            data = data.dropna()

        x = data[x_var]
        y = data[y_var]
        if self._hue_var is None:
            hue = None
        else:
            hue = data.get(self._hue_var)

        if "hue" not in kwargs:
            kwargs.update({
                "hue": hue, "hue_order": self._hue_order, "palette": self._orig_palette,
            })
        func(x=x, y=y, **kwargs)

        self._update_legend_data(ax)

    def _plot_bivariate_iter_hue(self, x_var, y_var, ax, func, **kwargs):
        """Draw a bivariate plot while iterating over hue subsets."""
        kwargs = kwargs.copy()
        if str(func.__module__).startswith("seaborn"):
            kwargs["ax"] = ax
        else:
            plt.sca(ax)

        if x_var == y_var:
            axes_vars = [x_var]
        else:
            axes_vars = [x_var, y_var]

        hue_grouped = self.data.groupby(self.hue_vals, observed=True)
        for k, label_k in enumerate(self._hue_order):

            kws = kwargs.copy()

            # Attempt to get data for this level, allowing for empty
            try:
                data_k = hue_grouped.get_group(label_k)
            except KeyError:
                data_k = pd.DataFrame(columns=axes_vars,
                                      dtype=float)

            if self._dropna:
                data_k = data_k[axes_vars].dropna()

            x = data_k[x_var]
            y = data_k[y_var]

            for kw, val_list in self.hue_kws.items():
                kws[kw] = val_list[k]
            kws.setdefault("color", self.palette[k])
            if self._hue_var is not None:
                kws["label"] = label_k

            if str(func.__module__).startswith("seaborn"):
                func(x=x, y=y, **kws)
            else:
                func(x, y, **kws)

        self._update_legend_data(ax)

    def _add_axis_labels(self):
        """Add labels to the left and bottom Axes."""
        for ax, label in zip(self.axes[-1, :], self.x_vars):
            ax.set_xlabel(label)
        for ax, label in zip(self.axes[:, 0], self.y_vars):
            ax.set_ylabel(label)

    def _find_numeric_cols(self, data):
        """Find which variables in a DataFrame are numeric."""
        numeric_cols = []
        for col in data:
            if variable_type(data[col]) == "numeric":
                numeric_cols.append(col)
        return numeric_cols


class JointGrid(_BaseGrid):
    """Grid for drawing a bivariate plot with marginal univariate plots.

    Many plots can be drawn by using the figure-level interface :func:`jointplot`.
    Use this class directly when you need more flexibility.

    """

    def __init__(
        self, data=None, *,
        x=None, y=None, hue=None,
        height=6, ratio=5, space=.2,
        palette=None, hue_order=None, hue_norm=None,
        dropna=False, xlim=None, ylim=None, marginal_ticks=False,
    ):

        # Set up the subplot grid
        f = plt.figure(figsize=(height, height))
        gs = plt.GridSpec(ratio + 1, ratio + 1)

        ax_joint = f.add_subplot(gs[1:, :-1])
        ax_marg_x = f.add_subplot(gs[0, :-1], sharex=ax_joint)
        ax_marg_y = f.add_subplot(gs[1:, -1], sharey=ax_joint)

        self._figure = f
        self.ax_joint = ax_joint
        self.ax_marg_x = ax_marg_x
        self.ax_marg_y = ax_marg_y

        # Turn off tick visibility for the measure axis on the marginal plots
        plt.setp(ax_marg_x.get_xticklabels(), visible=False)
        plt.setp(ax_marg_y.get_yticklabels(), visible=False)
        plt.setp(ax_marg_x.get_xticklabels(minor=True), visible=False)
        plt.setp(ax_marg_y.get_yticklabels(minor=True), visible=False)

        # Turn off the ticks on the density axis for the marginal plots
        if not marginal_ticks:
            plt.setp(ax_marg_x.yaxis.get_majorticklines(), visible=False)
            plt.setp(ax_marg_x.yaxis.get_minorticklines(), visible=False)
            plt.setp(ax_marg_y.xaxis.get_majorticklines(), visible=False)
            plt.setp(ax_marg_y.xaxis.get_minorticklines(), visible=False)
            plt.setp(ax_marg_x.get_yticklabels(), visible=False)
            plt.setp(ax_marg_y.get_xticklabels(), visible=False)
            plt.setp(ax_marg_x.get_yticklabels(minor=True), visible=False)
            plt.setp(ax_marg_y.get_xticklabels(minor=True), visible=False)
            ax_marg_x.yaxis.grid(False)
            ax_marg_y.xaxis.grid(False)

        # Process the input variables
        p = VectorPlotter(data=data, variables=dict(x=x, y=y, hue=hue))
        plot_data = p.plot_data.loc[:, p.plot_data.notna().any()]

        # Possibly drop NA
        if dropna:
            plot_data = plot_data.dropna()

        def get_var(var):
            vector = plot_data.get(var, None)
            if vector is not None:
                vector = vector.rename(p.variables.get(var, None))
            return vector

        self.x = get_var("x")
        self.y = get_var("y")
        self.hue = get_var("hue")

        for axis in "xy":
            name = p.variables.get(axis, None)
            if name is not None:
                getattr(ax_joint, f"set_{axis}label")(name)

        if xlim is not None:
            ax_joint.set_xlim(xlim)
        if ylim is not None:
            ax_joint.set_ylim(ylim)

        # Store the semantic mapping parameters for axes-level functions
        self._hue_params = dict(palette=palette, hue_order=hue_order, hue_norm=hue_norm)

        # Make the grid look nice
        utils.despine(f)
        if not marginal_ticks:
            utils.despine(ax=ax_marg_x, left=True)
            utils.despine(ax=ax_marg_y, bottom=True)
        for axes in [ax_marg_x, ax_marg_y]:
            for axis in [axes.xaxis, axes.yaxis]:
                axis.label.set_visible(False)
        f.tight_layout()
        f.subplots_adjust(hspace=space, wspace=space)

    def _inject_kwargs(self, func, kws, params):
        """Add params to kws if they are accepted by func."""
        func_params = signature(func).parameters
        for key, val in params.items():
            if key in func_params:
                kws.setdefault(key, val)

    def plot(self, joint_func, marginal_func, **kwargs):
        """Draw the plot by passing functions for joint and marginal axes.

        This method passes the ``kwargs`` dictionary to both functions. If you
        need more control, call :meth:`JointGrid.plot_joint` and
        :meth:`JointGrid.plot_marginals` directly with specific parameters.

        Parameters
        ----------
        joint_func, marginal_func : callables
            Functions to draw the bivariate and univariate plots. See methods
            referenced above for information about the required characteristics
            of these functions.
        kwargs
            Additional keyword arguments are passed to both functions.

        Returns
        -------
        :class:`JointGrid` instance
            Returns ``self`` for easy method chaining.

        """
        self.plot_marginals(marginal_func, **kwargs)
        self.plot_joint(joint_func, **kwargs)
        return self

    def plot_joint(self, func, **kwargs):
        """Draw a bivariate plot on the joint axes of the grid.

        Parameters
        ----------
        func : plotting callable
            If a seaborn function, it should accept ``x`` and ``y``. Otherwise,
            it must accept ``x`` and ``y`` vectors of data as the first two
            positional arguments, and it must plot on the "current" axes.
            If ``hue`` was defined in the class constructor, the function must
            accept ``hue`` as a parameter.
        kwargs
            Keyword argument are passed to the plotting function.

        Returns
        -------
        :class:`JointGrid` instance
            Returns ``self`` for easy method chaining.

        """
        kwargs = kwargs.copy()
        if str(func.__module__).startswith("seaborn"):
            kwargs["ax"] = self.ax_joint
        else:
            plt.sca(self.ax_joint)
        if self.hue is not None:
            kwargs["hue"] = self.hue
            self._inject_kwargs(func, kwargs, self._hue_params)

        if str(func.__module__).startswith("seaborn"):
            func(x=self.x, y=self.y, **kwargs)
        else:
            func(self.x, self.y, **kwargs)

        return self

    def plot_marginals(self, func, **kwargs):
        """Draw univariate plots on each marginal axes.

        Parameters
        ----------
        func : plotting callable
            If a seaborn function, it should  accept ``x`` and ``y`` and plot
            when only one of them is defined. Otherwise, it must accept a vector
            of data as the first positional argument and determine its orientation
            using the ``vertical`` parameter, and it must plot on the "current" axes.
            If ``hue`` was defined in the class constructor, it must accept ``hue``
            as a parameter.
        kwargs
            Keyword argument are passed to the plotting function.

        Returns
        -------
        :class:`JointGrid` instance
            Returns ``self`` for easy method chaining.

        """
        seaborn_func = (
            str(func.__module__).startswith("seaborn")
            # deprecated distplot has a legacy API, special case it
            and not func.__name__ == "distplot"
        )
        func_params = signature(func).parameters
        kwargs = kwargs.copy()
        if self.hue is not None:
            kwargs["hue"] = self.hue
            self._inject_kwargs(func, kwargs, self._hue_params)

        if "legend" in func_params:
            kwargs.setdefault("legend", False)

        if "orientation" in func_params:
            # e.g. plt.hist
            orient_kw_x = {"orientation": "vertical"}
            orient_kw_y = {"orientation": "horizontal"}
        elif "vertical" in func_params:
            # e.g. sns.distplot (also how did this get backwards?)
            orient_kw_x = {"vertical": False}
            orient_kw_y = {"vertical": True}

        if seaborn_func:
            func(x=self.x, ax=self.ax_marg_x, **kwargs)
        else:
            plt.sca(self.ax_marg_x)
            func(self.x, **orient_kw_x, **kwargs)

        if seaborn_func:
            func(y=self.y, ax=self.ax_marg_y, **kwargs)
        else:
            plt.sca(self.ax_marg_y)
            func(self.y, **orient_kw_y, **kwargs)

        self.ax_marg_x.yaxis.get_label().set_visible(False)
        self.ax_marg_y.xaxis.get_label().set_visible(False)

        return self

    def refline(
        self, *, x=None, y=None, joint=True, marginal=True,
        color='.5', linestyle='--', **line_kws
    ):
        """Add a reference line(s) to joint and/or marginal axes.

        Parameters
        ----------
        x, y : numeric
            Value(s) to draw the line(s) at.
        joint, marginal : bools
            Whether to add the reference line(s) to the joint/marginal axes.
        color : :mod:`matplotlib color <matplotlib.colors>`
            Specifies the color of the reference line(s).
        linestyle : str
            Specifies the style of the reference line(s).
        line_kws : key, value mappings
            Other keyword arguments are passed to :meth:`matplotlib.axes.Axes.axvline`
            when ``x`` is not None and :meth:`matplotlib.axes.Axes.axhline` when ``y``
            is not None.

        Returns
        -------
        :class:`JointGrid` instance
            Returns ``self`` for easy method chaining.

        """
        line_kws['color'] = color
        line_kws['linestyle'] = linestyle

        if x is not None:
            if joint:
                self.ax_joint.axvline(x, **line_kws)
            if marginal:
                self.ax_marg_x.axvline(x, **line_kws)

        if y is not None:
            if joint:
                self.ax_joint.axhline(y, **line_kws)
            if marginal:
                self.ax_marg_y.axhline(y, **line_kws)

        return self

    def set_axis_labels(self, xlabel="", ylabel="", **kwargs):
        """Set axis labels on the bivariate axes.

        Parameters
        ----------
        xlabel, ylabel : strings
            Label names for the x and y variables.
        kwargs : key, value mappings
            Other keyword arguments are passed to the following functions:

            - :meth:`matplotlib.axes.Axes.set_xlabel`
            - :meth:`matplotlib.axes.Axes.set_ylabel`

        Returns
        -------
        :class:`JointGrid` instance
            Returns ``self`` for easy method chaining.

        """
        self.ax_joint.set_xlabel(xlabel, **kwargs)
        self.ax_joint.set_ylabel(ylabel, **kwargs)
        return self


JointGrid.__init__.__doc__ = """\
Set up the grid of subplots and store data internally for easy plotting.

Parameters
----------
{params.core.data}
{params.core.xy}
height : number
    Size of each side of the figure in inches (it will be square).
ratio : number
    Ratio of joint axes height to marginal axes height.
space : number
    Space between the joint and marginal axes
dropna : bool
    If True, remove missing observations before plotting.
{{x, y}}lim : pairs of numbers
    Set axis limits to these values before plotting.
marginal_ticks : bool
    If False, suppress ticks on the count/density axis of the marginal plots.
{params.core.hue}
    Note: unlike in :class:`FacetGrid` or :class:`PairGrid`, the axes-level
    functions must support ``hue`` to use it in :class:`JointGrid`.
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}

See Also
--------
{seealso.jointplot}
{seealso.pairgrid}
{seealso.pairplot}

Examples
--------

.. include:: ../docstrings/JointGrid.rst

""".format(
    params=_param_docs,
    seealso=_core_docs["seealso"],
)


def pairplot(
    data, *,
    hue=None, hue_order=None, palette=None,
    vars=None, x_vars=None, y_vars=None,
    kind="scatter", diag_kind="auto", markers=None,
    height=2.5, aspect=1, corner=False, dropna=False,
    plot_kws=None, diag_kws=None, grid_kws=None, size=None,
):
    """Plot pairwise relationships in a dataset.

    By default, this function will create a grid of Axes such that each numeric
    variable in ``data`` will by shared across the y-axes across a single row and
    the x-axes across a single column. The diagonal plots are treated
    differently: a univariate distribution plot is drawn to show the marginal
    distribution of the data in each column.

    It is also possible to show a subset of variables or plot different
    variables on the rows and columns.

    This is a high-level interface for :class:`PairGrid` that is intended to
    make it easy to draw a few common styles. You should use :class:`PairGrid`
    directly if you need more flexibility.

    Parameters
    ----------
    data : `pandas.DataFrame`
        Tidy (long-form) dataframe where each column is a variable and
        each row is an observation.
    hue : name of variable in ``data``
        Variable in ``data`` to map plot aspects to different colors.
    hue_order : list of strings
        Order for the levels of the hue variable in the palette
    palette : dict or seaborn color palette
        Set of colors for mapping the ``hue`` variable. If a dict, keys
        should be values  in the ``hue`` variable.
    vars : list of variable names
        Variables within ``data`` to use, otherwise use every column with
        a numeric datatype.
    {x, y}_vars : lists of variable names
        Variables within ``data`` to use separately for the rows and
        columns of the figure; i.e. to make a non-square plot.
    kind : {'scatter', 'kde', 'hist', 'reg'}
        Kind of plot to make.
    diag_kind : {'auto', 'hist', 'kde', None}
        Kind of plot for the diagonal subplots. If 'auto', choose based on
        whether or not ``hue`` is used.
    markers : single matplotlib marker code or list
        Either the marker to use for all scatterplot points or a list of markers
        with a length the same as the number of levels in the hue variable so that
        differently colored points will also have different scatterplot
        markers.
    height : scalar
        Height (in inches) of each facet.
    aspect : scalar
        Aspect * height gives the width (in inches) of each facet.
    corner : bool
        If True, don't add axes to the upper (off-diagonal) triangle of the
        grid, making this a "corner" plot.
    dropna : boolean
        Drop missing values from the data before plotting.
    {plot, diag, grid}_kws : dicts
        Dictionaries of keyword arguments. ``plot_kws`` are passed to the
        bivariate plotting function, ``diag_kws`` are passed to the univariate
        plotting function, and ``grid_kws`` are passed to the :class:`PairGrid`
        constructor.

    Returns
    -------
    grid : :class:`PairGrid`
        Returns the underlying :class:`PairGrid` instance for further tweaking.

    See Also
    --------
    PairGrid : Subplot grid for more flexible plotting of pairwise relationships.
    JointGrid : Grid for plotting joint and marginal distributions of two variables.

    Examples
    --------

    .. include:: ../docstrings/pairplot.rst

    """
    # Avoid circular import
    from .distributions import histplot, kdeplot

    # Handle deprecations
    if size is not None:
        height = size
        msg = ("The `size` parameter has been renamed to `height`; "
               "please update your code.")
        warnings.warn(msg, UserWarning)

    if not isinstance(data, pd.DataFrame):
        raise TypeError(
            f"'data' must be pandas DataFrame object, not: {type(data)}")

    plot_kws = {} if plot_kws is None else plot_kws.copy()
    diag_kws = {} if diag_kws is None else diag_kws.copy()
    grid_kws = {} if grid_kws is None else grid_kws.copy()

    # Resolve "auto" diag kind
    if diag_kind == "auto":
        if hue is None:
            diag_kind = "kde" if kind == "kde" else "hist"
        else:
            diag_kind = "hist" if kind == "hist" else "kde"

    # Set up the PairGrid
    grid_kws.setdefault("diag_sharey", diag_kind == "hist")
    grid = PairGrid(data, vars=vars, x_vars=x_vars, y_vars=y_vars, hue=hue,
                    hue_order=hue_order, palette=palette, corner=corner,
                    height=height, aspect=aspect, dropna=dropna, **grid_kws)

    # Add the markers here as PairGrid has figured out how many levels of the
    # hue variable are needed and we don't want to duplicate that process
    if markers is not None:
        if kind == "reg":
            # Needed until regplot supports style
            if grid.hue_names is None:
                n_markers = 1
            else:
                n_markers = len(grid.hue_names)
            if not isinstance(markers, list):
                markers = [markers] * n_markers
            if len(markers) != n_markers:
                raise ValueError("markers must be a singleton or a list of "
                                 "markers for each level of the hue variable")
            grid.hue_kws = {"marker": markers}
        elif kind == "scatter":
            if isinstance(markers, str):
                plot_kws["marker"] = markers
            elif hue is not None:
                plot_kws["style"] = data[hue]
                plot_kws["markers"] = markers

    # Draw the marginal plots on the diagonal
    diag_kws = diag_kws.copy()
    diag_kws.setdefault("legend", False)
    if diag_kind == "hist":
        grid.map_diag(histplot, **diag_kws)
    elif diag_kind == "kde":
        diag_kws.setdefault("fill", True)
        diag_kws.setdefault("warn_singular", False)
        grid.map_diag(kdeplot, **diag_kws)

    # Maybe plot on the off-diagonals
    if diag_kind is not None:
        plotter = grid.map_offdiag
    else:
        plotter = grid.map

    if kind == "scatter":
        from .relational import scatterplot  # Avoid circular import
        plotter(scatterplot, **plot_kws)
    elif kind == "reg":
        from .regression import regplot  # Avoid circular import
        plotter(regplot, **plot_kws)
    elif kind == "kde":
        from .distributions import kdeplot  # Avoid circular import
        plot_kws.setdefault("warn_singular", False)
        plotter(kdeplot, **plot_kws)
    elif kind == "hist":
        from .distributions import histplot  # Avoid circular import
        plotter(histplot, **plot_kws)

    # Add a legend
    if hue is not None:
        grid.add_legend()

    grid.tight_layout()

    return grid


def jointplot(
    data=None, *, x=None, y=None, hue=None, kind="scatter",
    height=6, ratio=5, space=.2, dropna=False, xlim=None, ylim=None,
    color=None, palette=None, hue_order=None, hue_norm=None, marginal_ticks=False,
    joint_kws=None, marginal_kws=None,
    **kwargs
):
    # Avoid circular imports
    from .relational import scatterplot
    from .regression import regplot, residplot
    from .distributions import histplot, kdeplot, _freedman_diaconis_bins

    if kwargs.pop("ax", None) is not None:
        msg = "Ignoring `ax`; jointplot is a figure-level function."
        warnings.warn(msg, UserWarning, stacklevel=2)

    # Set up empty default kwarg dicts
    joint_kws = {} if joint_kws is None else joint_kws.copy()
    joint_kws.update(kwargs)
    marginal_kws = {} if marginal_kws is None else marginal_kws.copy()

    # Handle deprecations of distplot-specific kwargs
    distplot_keys = [
        "rug", "fit", "hist_kws", "norm_hist" "hist_kws", "rug_kws",
    ]
    unused_keys = []
    for key in distplot_keys:
        if key in marginal_kws:
            unused_keys.append(key)
            marginal_kws.pop(key)
    if unused_keys and kind != "kde":
        msg = (
            "The marginal plotting function has changed to `histplot`,"
            " which does not accept the following argument(s): {}."
        ).format(", ".join(unused_keys))
        warnings.warn(msg, UserWarning)

    # Validate the plot kind
    plot_kinds = ["scatter", "hist", "hex", "kde", "reg", "resid"]
    _check_argument("kind", plot_kinds, kind)

    # Raise early if using `hue` with a kind that does not support it
    if hue is not None and kind in ["hex", "reg", "resid"]:
        msg = f"Use of `hue` with `kind='{kind}'` is not currently supported."
        raise ValueError(msg)

    # Make a colormap based off the plot color
    # (Currently used only for kind="hex")
    if color is None:
        color = "C0"
    color_rgb = mpl.colors.colorConverter.to_rgb(color)
    colors = [set_hls_values(color_rgb, l=val) for val in np.linspace(1, 0, 12)]
    cmap = blend_palette(colors, as_cmap=True)

    # Matplotlib's hexbin plot is not na-robust
    if kind == "hex":
        dropna = True

    # Initialize the JointGrid object
    grid = JointGrid(
        data=data, x=x, y=y, hue=hue,
        palette=palette, hue_order=hue_order, hue_norm=hue_norm,
        dropna=dropna, height=height, ratio=ratio, space=space,
        xlim=xlim, ylim=ylim, marginal_ticks=marginal_ticks,
    )

    if grid.hue is not None:
        marginal_kws.setdefault("legend", False)

    # Plot the data using the grid
    if kind.startswith("scatter"):

        joint_kws.setdefault("color", color)
        grid.plot_joint(scatterplot, **joint_kws)

        if grid.hue is None:
            marg_func = histplot
        else:
            marg_func = kdeplot
            marginal_kws.setdefault("warn_singular", False)
            marginal_kws.setdefault("fill", True)

        marginal_kws.setdefault("color", color)
        grid.plot_marginals(marg_func, **marginal_kws)

    elif kind.startswith("hist"):

        # TODO process pair parameters for bins, etc. and pass
        # to both joint and marginal plots

        joint_kws.setdefault("color", color)
        grid.plot_joint(histplot, **joint_kws)

        marginal_kws.setdefault("kde", False)
        marginal_kws.setdefault("color", color)

        marg_x_kws = marginal_kws.copy()
        marg_y_kws = marginal_kws.copy()

        pair_keys = "bins", "binwidth", "binrange"
        for key in pair_keys:
            if isinstance(joint_kws.get(key), tuple):
                x_val, y_val = joint_kws[key]
                marg_x_kws.setdefault(key, x_val)
                marg_y_kws.setdefault(key, y_val)

        histplot(data=data, x=x, hue=hue, **marg_x_kws, ax=grid.ax_marg_x)
        histplot(data=data, y=y, hue=hue, **marg_y_kws, ax=grid.ax_marg_y)

    elif kind.startswith("kde"):

        joint_kws.setdefault("color", color)
        joint_kws.setdefault("warn_singular", False)
        grid.plot_joint(kdeplot, **joint_kws)

        marginal_kws.setdefault("color", color)
        if "fill" in joint_kws:
            marginal_kws.setdefault("fill", joint_kws["fill"])

        grid.plot_marginals(kdeplot, **marginal_kws)

    elif kind.startswith("hex"):

        x_bins = min(_freedman_diaconis_bins(grid.x), 50)
        y_bins = min(_freedman_diaconis_bins(grid.y), 50)
        gridsize = int(np.mean([x_bins, y_bins]))

        joint_kws.setdefault("gridsize", gridsize)
        joint_kws.setdefault("cmap", cmap)
        grid.plot_joint(plt.hexbin, **joint_kws)

        marginal_kws.setdefault("kde", False)
        marginal_kws.setdefault("color", color)
        grid.plot_marginals(histplot, **marginal_kws)

    elif kind.startswith("reg"):

        marginal_kws.setdefault("color", color)
        marginal_kws.setdefault("kde", True)
        grid.plot_marginals(histplot, **marginal_kws)

        joint_kws.setdefault("color", color)
        grid.plot_joint(regplot, **joint_kws)

    elif kind.startswith("resid"):

        joint_kws.setdefault("color", color)
        grid.plot_joint(residplot, **joint_kws)

        x, y = grid.ax_joint.collections[0].get_offsets().T
        marginal_kws.setdefault("color", color)
        histplot(x=x, hue=hue, ax=grid.ax_marg_x, **marginal_kws)
        histplot(y=y, hue=hue, ax=grid.ax_marg_y, **marginal_kws)

    # Make the main axes active in the matplotlib state machine
    plt.sca(grid.ax_joint)

    return grid


jointplot.__doc__ = """\
Draw a plot of two variables with bivariate and univariate graphs.

This function provides a convenient interface to the :class:`JointGrid`
class, with several canned plot kinds. This is intended to be a fairly
lightweight wrapper; if you need more flexibility, you should use
:class:`JointGrid` directly.

Parameters
----------
{params.core.data}
{params.core.xy}
{params.core.hue}
kind : {{ "scatter" | "kde" | "hist" | "hex" | "reg" | "resid" }}
    Kind of plot to draw. See the examples for references to the underlying functions.
height : numeric
    Size of the figure (it will be square).
ratio : numeric
    Ratio of joint axes height to marginal axes height.
space : numeric
    Space between the joint and marginal axes
dropna : bool
    If True, remove observations that are missing from ``x`` and ``y``.
{{x, y}}lim : pairs of numbers
    Axis limits to set before plotting.
{params.core.color}
{params.core.palette}
{params.core.hue_order}
{params.core.hue_norm}
marginal_ticks : bool
    If False, suppress ticks on the count/density axis of the marginal plots.
{{joint, marginal}}_kws : dicts
    Additional keyword arguments for the plot components.
kwargs
    Additional keyword arguments are passed to the function used to
    draw the plot on the joint Axes, superseding items in the
    ``joint_kws`` dictionary.

Returns
-------
{returns.jointgrid}

See Also
--------
{seealso.jointgrid}
{seealso.pairgrid}
{seealso.pairplot}

Examples
--------

.. include:: ../docstrings/jointplot.rst

""".format(
    params=_param_docs,
    returns=_core_docs["returns"],
    seealso=_core_docs["seealso"],
)
