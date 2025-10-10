"""Functions to visualize matrices of data."""
import warnings

import matplotlib as mpl
from matplotlib.collections import LineCollection
import matplotlib.pyplot as plt
from matplotlib import gridspec
import numpy as np
import pandas as pd
try:
    from scipy.cluster import hierarchy
    _no_scipy = False
except ImportError:
    _no_scipy = True

from . import cm
from .axisgrid import Grid
from ._compat import get_colormap
from .utils import (
    despine,
    axis_ticklabels_overlap,
    relative_luminance,
    to_utf8,
    _draw_figure,
)


__all__ = ["heatmap", "clustermap"]


def _index_to_label(index):
    """Convert a pandas index or multiindex to an axis label."""
    if isinstance(index, pd.MultiIndex):
        return "-".join(map(to_utf8, index.names))
    else:
        return index.name


def _index_to_ticklabels(index):
    """Convert a pandas index or multiindex into ticklabels."""
    if isinstance(index, pd.MultiIndex):
        return ["-".join(map(to_utf8, i)) for i in index.values]
    else:
        return index.values


def _convert_colors(colors):
    """Convert either a list of colors or nested lists of colors to RGB."""
    to_rgb = mpl.colors.to_rgb

    try:
        to_rgb(colors[0])
        # If this works, there is only one level of colors
        return list(map(to_rgb, colors))
    except ValueError:
        # If we get here, we have nested lists
        return [list(map(to_rgb, color_list)) for color_list in colors]


def _matrix_mask(data, mask):
    """Ensure that data and mask are compatible and add missing values.

    Values will be plotted for cells where ``mask`` is ``False``.

    ``data`` is expected to be a DataFrame; ``mask`` can be an array or
    a DataFrame.

    """
    if mask is None:
        mask = np.zeros(data.shape, bool)

    if isinstance(mask, np.ndarray):
        # For array masks, ensure that shape matches data then convert
        if mask.shape != data.shape:
            raise ValueError("Mask must have the same shape as data.")

        mask = pd.DataFrame(mask,
                            index=data.index,
                            columns=data.columns,
                            dtype=bool)

    elif isinstance(mask, pd.DataFrame):
        # For DataFrame masks, ensure that semantic labels match data
        if not mask.index.equals(data.index) \
           and mask.columns.equals(data.columns):
            err = "Mask must have the same index and columns as data."
            raise ValueError(err)

    # Add any cells with missing data to the mask
    # This works around an issue where `plt.pcolormesh` doesn't represent
    # missing data properly
    mask = mask | pd.isnull(data)

    return mask


class _HeatMapper:
    """Draw a heatmap plot of a matrix with nice labels and colormaps."""

    def __init__(self, data, vmin, vmax, cmap, center, robust, annot, fmt,
                 annot_kws, cbar, cbar_kws,
                 xticklabels=True, yticklabels=True, mask=None):
        """Initialize the plotting object."""
        # We always want to have a DataFrame with semantic information
        # and an ndarray to pass to matplotlib
        if isinstance(data, pd.DataFrame):
            plot_data = data.values
        else:
            plot_data = np.asarray(data)
            data = pd.DataFrame(plot_data)

        # Validate the mask and convert to DataFrame
        mask = _matrix_mask(data, mask)

        plot_data = np.ma.masked_where(np.asarray(mask), plot_data)

        # Get good names for the rows and columns
        xtickevery = 1
        if isinstance(xticklabels, int):
            xtickevery = xticklabels
            xticklabels = _index_to_ticklabels(data.columns)
        elif xticklabels is True:
            xticklabels = _index_to_ticklabels(data.columns)
        elif xticklabels is False:
            xticklabels = []

        ytickevery = 1
        if isinstance(yticklabels, int):
            ytickevery = yticklabels
            yticklabels = _index_to_ticklabels(data.index)
        elif yticklabels is True:
            yticklabels = _index_to_ticklabels(data.index)
        elif yticklabels is False:
            yticklabels = []

        if not len(xticklabels):
            self.xticks = []
            self.xticklabels = []
        elif isinstance(xticklabels, str) and xticklabels == "auto":
            self.xticks = "auto"
            self.xticklabels = _index_to_ticklabels(data.columns)
        else:
            self.xticks, self.xticklabels = self._skip_ticks(xticklabels,
                                                             xtickevery)

        if not len(yticklabels):
            self.yticks = []
            self.yticklabels = []
        elif isinstance(yticklabels, str) and yticklabels == "auto":
            self.yticks = "auto"
            self.yticklabels = _index_to_ticklabels(data.index)
        else:
            self.yticks, self.yticklabels = self._skip_ticks(yticklabels,
                                                             ytickevery)

        # Get good names for the axis labels
        xlabel = _index_to_label(data.columns)
        ylabel = _index_to_label(data.index)
        self.xlabel = xlabel if xlabel is not None else ""
        self.ylabel = ylabel if ylabel is not None else ""

        # Determine good default values for the colormapping
        self._determine_cmap_params(plot_data, vmin, vmax,
                                    cmap, center, robust)

        # Sort out the annotations
        if annot is None or annot is False:
            annot = False
            annot_data = None
        else:
            if isinstance(annot, bool):
                annot_data = plot_data
            else:
                annot_data = np.asarray(annot)
                if annot_data.shape != plot_data.shape:
                    err = "`data` and `annot` must have same shape."
                    raise ValueError(err)
            annot = True

        # Save other attributes to the object
        self.data = data
        self.plot_data = plot_data

        self.annot = annot
        self.annot_data = annot_data

        self.fmt = fmt
        self.annot_kws = {} if annot_kws is None else annot_kws.copy()
        self.cbar = cbar
        self.cbar_kws = {} if cbar_kws is None else cbar_kws.copy()

    def _determine_cmap_params(self, plot_data, vmin, vmax,
                               cmap, center, robust):
        """Use some heuristics to set good defaults for colorbar and range."""

        # plot_data is a np.ma.array instance
        calc_data = plot_data.astype(float).filled(np.nan)
        if vmin is None:
            if robust:
                vmin = np.nanpercentile(calc_data, 2)
            else:
                vmin = np.nanmin(calc_data)
        if vmax is None:
            if robust:
                vmax = np.nanpercentile(calc_data, 98)
            else:
                vmax = np.nanmax(calc_data)
        self.vmin, self.vmax = vmin, vmax

        # Choose default colormaps if not provided
        if cmap is None:
            if center is None:
                self.cmap = cm.rocket
            else:
                self.cmap = cm.icefire
        elif isinstance(cmap, str):
            self.cmap = get_colormap(cmap)
        elif isinstance(cmap, list):
            self.cmap = mpl.colors.ListedColormap(cmap)
        else:
            self.cmap = cmap

        # Recenter a divergent colormap
        if center is not None:

            # Copy bad values
            # in mpl<3.2 only masked values are honored with "bad" color spec
            # (see https://github.com/matplotlib/matplotlib/pull/14257)
            bad = self.cmap(np.ma.masked_invalid([np.nan]))[0]

            # under/over values are set for sure when cmap extremes
            # do not map to the same color as +-inf
            under = self.cmap(-np.inf)
            over = self.cmap(np.inf)
            under_set = under != self.cmap(0)
            over_set = over != self.cmap(self.cmap.N - 1)

            vrange = max(vmax - center, center - vmin)
            normlize = mpl.colors.Normalize(center - vrange, center + vrange)
            cmin, cmax = normlize([vmin, vmax])
            cc = np.linspace(cmin, cmax, 256)
            self.cmap = mpl.colors.ListedColormap(self.cmap(cc))
            self.cmap.set_bad(bad)
            if under_set:
                self.cmap.set_under(under)
            if over_set:
                self.cmap.set_over(over)

    def _annotate_heatmap(self, ax, mesh):
        """Add textual labels with the value in each cell."""
        mesh.update_scalarmappable()
        height, width = self.annot_data.shape
        xpos, ypos = np.meshgrid(np.arange(width) + .5, np.arange(height) + .5)
        for x, y, m, color, val in zip(xpos.flat, ypos.flat,
                                       mesh.get_array().flat, mesh.get_facecolors(),
                                       self.annot_data.flat):
            if m is not np.ma.masked:
                lum = relative_luminance(color)
                text_color = ".15" if lum > .408 else "w"
                annotation = ("{:" + self.fmt + "}").format(val)
                text_kwargs = dict(color=text_color, ha="center", va="center")
                text_kwargs.update(self.annot_kws)
                ax.text(x, y, annotation, **text_kwargs)

    def _skip_ticks(self, labels, tickevery):
        """Return ticks and labels at evenly spaced intervals."""
        n = len(labels)
        if tickevery == 0:
            ticks, labels = [], []
        elif tickevery == 1:
            ticks, labels = np.arange(n) + .5, labels
        else:
            start, end, step = 0, n, tickevery
            ticks = np.arange(start, end, step) + .5
            labels = labels[start:end:step]
        return ticks, labels

    def _auto_ticks(self, ax, labels, axis):
        """Determine ticks and ticklabels that minimize overlap."""
        transform = ax.figure.dpi_scale_trans.inverted()
        bbox = ax.get_window_extent().transformed(transform)
        size = [bbox.width, bbox.height][axis]
        axis = [ax.xaxis, ax.yaxis][axis]
        tick, = axis.set_ticks([0])
        fontsize = tick.label1.get_size()
        max_ticks = int(size // (fontsize / 72))
        if max_ticks < 1:
            return [], []
        tick_every = len(labels) // max_ticks + 1
        tick_every = 1 if tick_every == 0 else tick_every
        ticks, labels = self._skip_ticks(labels, tick_every)
        return ticks, labels

    def plot(self, ax, cax, kws):
        """Draw the heatmap on the provided Axes."""
        # Remove all the Axes spines
        despine(ax=ax, left=True, bottom=True)

        # setting vmin/vmax in addition to norm is deprecated
        # so avoid setting if norm is set
        if kws.get("norm") is None:
            kws.setdefault("vmin", self.vmin)
            kws.setdefault("vmax", self.vmax)

        # Draw the heatmap
        mesh = ax.pcolormesh(self.plot_data, cmap=self.cmap, **kws)

        # Set the axis limits
        ax.set(xlim=(0, self.data.shape[1]), ylim=(0, self.data.shape[0]))

        # Invert the y axis to show the plot in matrix form
        ax.invert_yaxis()

        # Possibly add a colorbar
        if self.cbar:
            cb = ax.figure.colorbar(mesh, cax, ax, **self.cbar_kws)
            cb.outline.set_linewidth(0)
            # If rasterized is passed to pcolormesh, also rasterize the
            # colorbar to avoid white lines on the PDF rendering
            if kws.get('rasterized', False):
                cb.solids.set_rasterized(True)

        # Add row and column labels
        if isinstance(self.xticks, str) and self.xticks == "auto":
            xticks, xticklabels = self._auto_ticks(ax, self.xticklabels, 0)
        else:
            xticks, xticklabels = self.xticks, self.xticklabels

        if isinstance(self.yticks, str) and self.yticks == "auto":
            yticks, yticklabels = self._auto_ticks(ax, self.yticklabels, 1)
        else:
            yticks, yticklabels = self.yticks, self.yticklabels

        ax.set(xticks=xticks, yticks=yticks)
        xtl = ax.set_xticklabels(xticklabels)
        ytl = ax.set_yticklabels(yticklabels, rotation="vertical")
        plt.setp(ytl, va="center")  # GH2484

        # Possibly rotate them if they overlap
        _draw_figure(ax.figure)

        if axis_ticklabels_overlap(xtl):
            plt.setp(xtl, rotation="vertical")
        if axis_ticklabels_overlap(ytl):
            plt.setp(ytl, rotation="horizontal")

        # Add the axis labels
        ax.set(xlabel=self.xlabel, ylabel=self.ylabel)

        # Annotate the cells with the formatted values
        if self.annot:
            self._annotate_heatmap(ax, mesh)


def heatmap(
    data, *,
    vmin=None, vmax=None, cmap=None, center=None, robust=False,
    annot=None, fmt=".2g", annot_kws=None,
    linewidths=0, linecolor="white",
    cbar=True, cbar_kws=None, cbar_ax=None,
    square=False, xticklabels="auto", yticklabels="auto",
    mask=None, ax=None,
    **kwargs
):
    """Plot rectangular data as a color-encoded matrix.

    This is an Axes-level function and will draw the heatmap into the
    currently-active Axes if none is provided to the ``ax`` argument.  Part of
    this Axes space will be taken and used to plot a colormap, unless ``cbar``
    is False or a separate Axes is provided to ``cbar_ax``.

    Parameters
    ----------
    data : rectangular dataset
        2D dataset that can be coerced into an ndarray. If a Pandas DataFrame
        is provided, the index/column information will be used to label the
        columns and rows.
    vmin, vmax : floats, optional
        Values to anchor the colormap, otherwise they are inferred from the
        data and other keyword arguments.
    cmap : matplotlib colormap name or object, or list of colors, optional
        The mapping from data values to color space. If not provided, the
        default will depend on whether ``center`` is set.
    center : float, optional
        The value at which to center the colormap when plotting divergent data.
        Using this parameter will change the default ``cmap`` if none is
        specified.
    robust : bool, optional
        If True and ``vmin`` or ``vmax`` are absent, the colormap range is
        computed with robust quantiles instead of the extreme values.
    annot : bool or rectangular dataset, optional
        If True, write the data value in each cell. If an array-like with the
        same shape as ``data``, then use this to annotate the heatmap instead
        of the data. Note that DataFrames will match on position, not index.
    fmt : str, optional
        String formatting code to use when adding annotations.
    annot_kws : dict of key, value mappings, optional
        Keyword arguments for :meth:`matplotlib.axes.Axes.text` when ``annot``
        is True.
    linewidths : float, optional
        Width of the lines that will divide each cell.
    linecolor : color, optional
        Color of the lines that will divide each cell.
    cbar : bool, optional
        Whether to draw a colorbar.
    cbar_kws : dict of key, value mappings, optional
        Keyword arguments for :meth:`matplotlib.figure.Figure.colorbar`.
    cbar_ax : matplotlib Axes, optional
        Axes in which to draw the colorbar, otherwise take space from the
        main Axes.
    square : bool, optional
        If True, set the Axes aspect to "equal" so each cell will be
        square-shaped.
    xticklabels, yticklabels : "auto", bool, list-like, or int, optional
        If True, plot the column names of the dataframe. If False, don't plot
        the column names. If list-like, plot these alternate labels as the
        xticklabels. If an integer, use the column names but plot only every
        n label. If "auto", try to densely plot non-overlapping labels.
    mask : bool array or DataFrame, optional
        If passed, data will not be shown in cells where ``mask`` is True.
        Cells with missing values are automatically masked.
    ax : matplotlib Axes, optional
        Axes in which to draw the plot, otherwise use the currently-active
        Axes.
    kwargs : other keyword arguments
        All other keyword arguments are passed to
        :meth:`matplotlib.axes.Axes.pcolormesh`.

    Returns
    -------
    ax : matplotlib Axes
        Axes object with the heatmap.

    See Also
    --------
    clustermap : Plot a matrix using hierarchical clustering to arrange the
                 rows and columns.

    Examples
    --------

    .. include:: ../docstrings/heatmap.rst

    """
    # Initialize the plotter object
    plotter = _HeatMapper(data, vmin, vmax, cmap, center, robust, annot, fmt,
                          annot_kws, cbar, cbar_kws, xticklabels,
                          yticklabels, mask)

    # Add the pcolormesh kwargs here
    kwargs["linewidths"] = linewidths
    kwargs["edgecolor"] = linecolor

    # Draw the plot and return the Axes
    if ax is None:
        ax = plt.gca()
    if square:
        ax.set_aspect("equal")
    plotter.plot(ax, cbar_ax, kwargs)
    return ax


class _DendrogramPlotter:
    """Object for drawing tree of similarities between data rows/columns"""

    def __init__(self, data, linkage, metric, method, axis, label, rotate):
        """Plot a dendrogram of the relationships between the columns of data

        Parameters
        ----------
        data : pandas.DataFrame
            Rectangular data
        """
        self.axis = axis
        if self.axis == 1:
            data = data.T

        if isinstance(data, pd.DataFrame):
            array = data.values
        else:
            array = np.asarray(data)
            data = pd.DataFrame(array)

        self.array = array
        self.data = data

        self.shape = self.data.shape
        self.metric = metric
        self.method = method
        self.axis = axis
        self.label = label
        self.rotate = rotate

        if linkage is None:
            self.linkage = self.calculated_linkage
        else:
            self.linkage = linkage
        self.dendrogram = self.calculate_dendrogram()

        # Dendrogram ends are always at multiples of 5, who knows why
        ticks = 10 * np.arange(self.data.shape[0]) + 5

        if self.label:
            ticklabels = _index_to_ticklabels(self.data.index)
            ticklabels = [ticklabels[i] for i in self.reordered_ind]
            if self.rotate:
                self.xticks = []
                self.yticks = ticks
                self.xticklabels = []

                self.yticklabels = ticklabels
                self.ylabel = _index_to_label(self.data.index)
                self.xlabel = ''
            else:
                self.xticks = ticks
                self.yticks = []
                self.xticklabels = ticklabels
                self.yticklabels = []
                self.ylabel = ''
                self.xlabel = _index_to_label(self.data.index)
        else:
            self.xticks, self.yticks = [], []
            self.yticklabels, self.xticklabels = [], []
            self.xlabel, self.ylabel = '', ''

        self.dependent_coord = self.dendrogram['dcoord']
        self.independent_coord = self.dendrogram['icoord']

    def _calculate_linkage_scipy(self):
        linkage = hierarchy.linkage(self.array, method=self.method,
                                    metric=self.metric)
        return linkage

    def _calculate_linkage_fastcluster(self):
        import fastcluster
        # Fastcluster has a memory-saving vectorized version, but only
        # with certain linkage methods, and mostly with euclidean metric
        # vector_methods = ('single', 'centroid', 'median', 'ward')
        euclidean_methods = ('centroid', 'median', 'ward')
        euclidean = self.metric == 'euclidean' and self.method in \
            euclidean_methods
        if euclidean or self.method == 'single':
            return fastcluster.linkage_vector(self.array,
                                              method=self.method,
                                              metric=self.metric)
        else:
            linkage = fastcluster.linkage(self.array, method=self.method,
                                          metric=self.metric)
            return linkage

    @property
    def calculated_linkage(self):

        try:
            return self._calculate_linkage_fastcluster()
        except ImportError:
            if np.prod(self.shape) >= 10000:
                msg = ("Clustering large matrix with scipy. Installing "
                       "`fastcluster` may give better performance.")
                warnings.warn(msg)

        return self._calculate_linkage_scipy()

    def calculate_dendrogram(self):
        """Calculates a dendrogram based on the linkage matrix

        Made a separate function, not a property because don't want to
        recalculate the dendrogram every time it is accessed.

        Returns
        -------
        dendrogram : dict
            Dendrogram dictionary as returned by scipy.cluster.hierarchy
            .dendrogram. The important key-value pairing is
            "reordered_ind" which indicates the re-ordering of the matrix
        """
        return hierarchy.dendrogram(self.linkage, no_plot=True,
                                    color_threshold=-np.inf)

    @property
    def reordered_ind(self):
        """Indices of the matrix, reordered by the dendrogram"""
        return self.dendrogram['leaves']

    def plot(self, ax, tree_kws):
        """Plots a dendrogram of the similarities between data on the axes

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            Axes object upon which the dendrogram is plotted

        """
        tree_kws = {} if tree_kws is None else tree_kws.copy()
        tree_kws.setdefault("linewidths", .5)
        tree_kws.setdefault("colors", tree_kws.pop("color", (.2, .2, .2)))

        if self.rotate and self.axis == 0:
            coords = zip(self.dependent_coord, self.independent_coord)
        else:
            coords = zip(self.independent_coord, self.dependent_coord)
        lines = LineCollection([list(zip(x, y)) for x, y in coords],
                               **tree_kws)

        ax.add_collection(lines)
        number_of_leaves = len(self.reordered_ind)
        max_dependent_coord = max(map(max, self.dependent_coord))

        if self.rotate:
            ax.yaxis.set_ticks_position('right')

            # Constants 10 and 1.05 come from
            # `scipy.cluster.hierarchy._plot_dendrogram`
            ax.set_ylim(0, number_of_leaves * 10)
            ax.set_xlim(0, max_dependent_coord * 1.05)

            ax.invert_xaxis()
            ax.invert_yaxis()
        else:
            # Constants 10 and 1.05 come from
            # `scipy.cluster.hierarchy._plot_dendrogram`
            ax.set_xlim(0, number_of_leaves * 10)
            ax.set_ylim(0, max_dependent_coord * 1.05)

        despine(ax=ax, bottom=True, left=True)

        ax.set(xticks=self.xticks, yticks=self.yticks,
               xlabel=self.xlabel, ylabel=self.ylabel)
        xtl = ax.set_xticklabels(self.xticklabels)
        ytl = ax.set_yticklabels(self.yticklabels, rotation='vertical')

        # Force a draw of the plot to avoid matplotlib window error
        _draw_figure(ax.figure)

        if len(ytl) > 0 and axis_ticklabels_overlap(ytl):
            plt.setp(ytl, rotation="horizontal")
        if len(xtl) > 0 and axis_ticklabels_overlap(xtl):
            plt.setp(xtl, rotation="vertical")
        return self


def dendrogram(
    data, *,
    linkage=None, axis=1, label=True, metric='euclidean',
    method='average', rotate=False, tree_kws=None, ax=None
):
    """Draw a tree diagram of relationships within a matrix

    Parameters
    ----------
    data : pandas.DataFrame
        Rectangular data
    linkage : numpy.array, optional
        Linkage matrix
    axis : int, optional
        Which axis to use to calculate linkage. 0 is rows, 1 is columns.
    label : bool, optional
        If True, label the dendrogram at leaves with column or row names
    metric : str, optional
        Distance metric. Anything valid for scipy.spatial.distance.pdist
    method : str, optional
        Linkage method to use. Anything valid for
        scipy.cluster.hierarchy.linkage
    rotate : bool, optional
        When plotting the matrix, whether to rotate it 90 degrees
        counter-clockwise, so the leaves face right
    tree_kws : dict, optional
        Keyword arguments for the ``matplotlib.collections.LineCollection``
        that is used for plotting the lines of the dendrogram tree.
    ax : matplotlib axis, optional
        Axis to plot on, otherwise uses current axis

    Returns
    -------
    dendrogramplotter : _DendrogramPlotter
        A Dendrogram plotter object.

    Notes
    -----
    Access the reordered dendrogram indices with
    dendrogramplotter.reordered_ind

    """
    if _no_scipy:
        raise RuntimeError("dendrogram requires scipy to be installed")

    plotter = _DendrogramPlotter(data, linkage=linkage, axis=axis,
                                 metric=metric, method=method,
                                 label=label, rotate=rotate)
    if ax is None:
        ax = plt.gca()

    return plotter.plot(ax=ax, tree_kws=tree_kws)


class ClusterGrid(Grid):

    def __init__(self, data, pivot_kws=None, z_score=None, standard_scale=None,
                 figsize=None, row_colors=None, col_colors=None, mask=None,
                 dendrogram_ratio=None, colors_ratio=None, cbar_pos=None):
        """Grid object for organizing clustered heatmap input on to axes"""
        if _no_scipy:
            raise RuntimeError("ClusterGrid requires scipy to be available")

        if isinstance(data, pd.DataFrame):
            self.data = data
        else:
            self.data = pd.DataFrame(data)

        self.data2d = self.format_data(self.data, pivot_kws, z_score,
                                       standard_scale)

        self.mask = _matrix_mask(self.data2d, mask)

        self._figure = plt.figure(figsize=figsize)

        self.row_colors, self.row_color_labels = \
            self._preprocess_colors(data, row_colors, axis=0)
        self.col_colors, self.col_color_labels = \
            self._preprocess_colors(data, col_colors, axis=1)

        try:
            row_dendrogram_ratio, col_dendrogram_ratio = dendrogram_ratio
        except TypeError:
            row_dendrogram_ratio = col_dendrogram_ratio = dendrogram_ratio

        try:
            row_colors_ratio, col_colors_ratio = colors_ratio
        except TypeError:
            row_colors_ratio = col_colors_ratio = colors_ratio

        width_ratios = self.dim_ratios(self.row_colors,
                                       row_dendrogram_ratio,
                                       row_colors_ratio)
        height_ratios = self.dim_ratios(self.col_colors,
                                        col_dendrogram_ratio,
                                        col_colors_ratio)

        nrows = 2 if self.col_colors is None else 3
        ncols = 2 if self.row_colors is None else 3

        self.gs = gridspec.GridSpec(nrows, ncols,
                                    width_ratios=width_ratios,
                                    height_ratios=height_ratios)

        self.ax_row_dendrogram = self._figure.add_subplot(self.gs[-1, 0])
        self.ax_col_dendrogram = self._figure.add_subplot(self.gs[0, -1])
        self.ax_row_dendrogram.set_axis_off()
        self.ax_col_dendrogram.set_axis_off()

        self.ax_row_colors = None
        self.ax_col_colors = None

        if self.row_colors is not None:
            self.ax_row_colors = self._figure.add_subplot(
                self.gs[-1, 1])
        if self.col_colors is not None:
            self.ax_col_colors = self._figure.add_subplot(
                self.gs[1, -1])

        self.ax_heatmap = self._figure.add_subplot(self.gs[-1, -1])
        if cbar_pos is None:
            self.ax_cbar = self.cax = None
        else:
            # Initialize the colorbar axes in the gridspec so that tight_layout
            # works. We will move it where it belongs later. This is a hack.
            self.ax_cbar = self._figure.add_subplot(self.gs[0, 0])
            self.cax = self.ax_cbar  # Backwards compatibility
        self.cbar_pos = cbar_pos

        self.dendrogram_row = None
        self.dendrogram_col = None

    def _preprocess_colors(self, data, colors, axis):
        """Preprocess {row/col}_colors to extract labels and convert colors."""
        labels = None

        if colors is not None:
            if isinstance(colors, (pd.DataFrame, pd.Series)):

                # If data is unindexed, raise
                if (not hasattr(data, "index") and axis == 0) or (
                    not hasattr(data, "columns") and axis == 1
                ):
                    axis_name = "col" if axis else "row"
                    msg = (f"{axis_name}_colors indices can't be matched with data "
                           f"indices. Provide {axis_name}_colors as a non-indexed "
                           "datatype, e.g. by using `.to_numpy()``")
                    raise TypeError(msg)

                # Ensure colors match data indices
                if axis == 0:
                    colors = colors.reindex(data.index)
                else:
                    colors = colors.reindex(data.columns)

                # Replace na's with white color
                # TODO We should set these to transparent instead
                colors = colors.astype(object).fillna('white')

                # Extract color values and labels from frame/series
                if isinstance(colors, pd.DataFrame):
                    labels = list(colors.columns)
                    colors = colors.T.values
                else:
                    if colors.name is None:
                        labels = [""]
                    else:
                        labels = [colors.name]
                    colors = colors.values

            colors = _convert_colors(colors)

        return colors, labels

    def format_data(self, data, pivot_kws, z_score=None,
                    standard_scale=None):
        """Extract variables from data or use directly."""

        # Either the data is already in 2d matrix format, or need to do a pivot
        if pivot_kws is not None:
            data2d = data.pivot(**pivot_kws)
        else:
            data2d = data

        if z_score is not None and standard_scale is not None:
            raise ValueError(
                'Cannot perform both z-scoring and standard-scaling on data')

        if z_score is not None:
            data2d = self.z_score(data2d, z_score)
        if standard_scale is not None:
            data2d = self.standard_scale(data2d, standard_scale)
        return data2d

    @staticmethod
    def z_score(data2d, axis=1):
        """Standarize the mean and variance of the data axis

        Parameters
        ----------
        data2d : pandas.DataFrame
            Data to normalize
        axis : int
            Which axis to normalize across. If 0, normalize across rows, if 1,
            normalize across columns.

        Returns
        -------
        normalized : pandas.DataFrame
            Noramlized data with a mean of 0 and variance of 1 across the
            specified axis.
        """
        if axis == 1:
            z_scored = data2d
        else:
            z_scored = data2d.T

        z_scored = (z_scored - z_scored.mean()) / z_scored.std()

        if axis == 1:
            return z_scored
        else:
            return z_scored.T

    @staticmethod
    def standard_scale(data2d, axis=1):
        """Divide the data by the difference between the max and min

        Parameters
        ----------
        data2d : pandas.DataFrame
            Data to normalize
        axis : int
            Which axis to normalize across. If 0, normalize across rows, if 1,
            normalize across columns.

        Returns
        -------
        standardized : pandas.DataFrame
            Noramlized data with a mean of 0 and variance of 1 across the
            specified axis.

        """
        # Normalize these values to range from 0 to 1
        if axis == 1:
            standardized = data2d
        else:
            standardized = data2d.T

        subtract = standardized.min()
        standardized = (standardized - subtract) / (
            standardized.max() - standardized.min())

        if axis == 1:
            return standardized
        else:
            return standardized.T

    def dim_ratios(self, colors, dendrogram_ratio, colors_ratio):
        """Get the proportions of the figure taken up by each axes."""
        ratios = [dendrogram_ratio]

        if colors is not None:
            # Colors are encoded as rgb, so there is an extra dimension
            if np.ndim(colors) > 2:
                n_colors = len(colors)
            else:
                n_colors = 1

            ratios += [n_colors * colors_ratio]

        # Add the ratio for the heatmap itself
        ratios.append(1 - sum(ratios))

        return ratios

    @staticmethod
    def color_list_to_matrix_and_cmap(colors, ind, axis=0):
        """Turns a list of colors into a numpy matrix and matplotlib colormap

        These arguments can now be plotted using heatmap(matrix, cmap)
        and the provided colors will be plotted.

        Parameters
        ----------
        colors : list of matplotlib colors
            Colors to label the rows or columns of a dataframe.
        ind : list of ints
            Ordering of the rows or columns, to reorder the original colors
            by the clustered dendrogram order
        axis : int
            Which axis this is labeling

        Returns
        -------
        matrix : numpy.array
            A numpy array of integer values, where each indexes into the cmap
        cmap : matplotlib.colors.ListedColormap

        """
        try:
            mpl.colors.to_rgb(colors[0])
        except ValueError:
            # We have a 2D color structure
            m, n = len(colors), len(colors[0])
            if not all(len(c) == n for c in colors[1:]):
                raise ValueError("Multiple side color vectors must have same size")
        else:
            # We have one vector of colors
            m, n = 1, len(colors)
            colors = [colors]

        # Map from unique colors to colormap index value
        unique_colors = {}
        matrix = np.zeros((m, n), int)
        for i, inner in enumerate(colors):
            for j, color in enumerate(inner):
                idx = unique_colors.setdefault(color, len(unique_colors))
                matrix[i, j] = idx

        # Reorder for clustering and transpose for axis
        matrix = matrix[:, ind]
        if axis == 0:
            matrix = matrix.T

        cmap = mpl.colors.ListedColormap(list(unique_colors))
        return matrix, cmap

    def plot_dendrograms(self, row_cluster, col_cluster, metric, method,
                         row_linkage, col_linkage, tree_kws):
        # Plot the row dendrogram
        if row_cluster:
            self.dendrogram_row = dendrogram(
                self.data2d, metric=metric, method=method, label=False, axis=0,
                ax=self.ax_row_dendrogram, rotate=True, linkage=row_linkage,
                tree_kws=tree_kws
            )
        else:
            self.ax_row_dendrogram.set_xticks([])
            self.ax_row_dendrogram.set_yticks([])
        # PLot the column dendrogram
        if col_cluster:
            self.dendrogram_col = dendrogram(
                self.data2d, metric=metric, method=method, label=False,
                axis=1, ax=self.ax_col_dendrogram, linkage=col_linkage,
                tree_kws=tree_kws
            )
        else:
            self.ax_col_dendrogram.set_xticks([])
            self.ax_col_dendrogram.set_yticks([])
        despine(ax=self.ax_row_dendrogram, bottom=True, left=True)
        despine(ax=self.ax_col_dendrogram, bottom=True, left=True)

    def plot_colors(self, xind, yind, **kws):
        """Plots color labels between the dendrogram and the heatmap

        Parameters
        ----------
        heatmap_kws : dict
            Keyword arguments heatmap

        """
        # Remove any custom colormap and centering
        # TODO this code has consistently caused problems when we
        # have missed kwargs that need to be excluded that it might
        # be better to rewrite *in*clusively.
        kws = kws.copy()
        kws.pop('cmap', None)
        kws.pop('norm', None)
        kws.pop('center', None)
        kws.pop('annot', None)
        kws.pop('vmin', None)
        kws.pop('vmax', None)
        kws.pop('robust', None)
        kws.pop('xticklabels', None)
        kws.pop('yticklabels', None)

        # Plot the row colors
        if self.row_colors is not None:
            matrix, cmap = self.color_list_to_matrix_and_cmap(
                self.row_colors, yind, axis=0)

            # Get row_color labels
            if self.row_color_labels is not None:
                row_color_labels = self.row_color_labels
            else:
                row_color_labels = False

            heatmap(matrix, cmap=cmap, cbar=False, ax=self.ax_row_colors,
                    xticklabels=row_color_labels, yticklabels=False, **kws)

            # Adjust rotation of labels
            if row_color_labels is not False:
                plt.setp(self.ax_row_colors.get_xticklabels(), rotation=90)
        else:
            despine(self.ax_row_colors, left=True, bottom=True)

        # Plot the column colors
        if self.col_colors is not None:
            matrix, cmap = self.color_list_to_matrix_and_cmap(
                self.col_colors, xind, axis=1)

            # Get col_color labels
            if self.col_color_labels is not None:
                col_color_labels = self.col_color_labels
            else:
                col_color_labels = False

            heatmap(matrix, cmap=cmap, cbar=False, ax=self.ax_col_colors,
                    xticklabels=False, yticklabels=col_color_labels, **kws)

            # Adjust rotation of labels, place on right side
            if col_color_labels is not False:
                self.ax_col_colors.yaxis.tick_right()
                plt.setp(self.ax_col_colors.get_yticklabels(), rotation=0)
        else:
            despine(self.ax_col_colors, left=True, bottom=True)

    def plot_matrix(self, colorbar_kws, xind, yind, **kws):
        self.data2d = self.data2d.iloc[yind, xind]
        self.mask = self.mask.iloc[yind, xind]

        # Try to reorganize specified tick labels, if provided
        xtl = kws.pop("xticklabels", "auto")
        try:
            xtl = np.asarray(xtl)[xind]
        except (TypeError, IndexError):
            pass
        ytl = kws.pop("yticklabels", "auto")
        try:
            ytl = np.asarray(ytl)[yind]
        except (TypeError, IndexError):
            pass

        # Reorganize the annotations to match the heatmap
        annot = kws.pop("annot", None)
        if annot is None or annot is False:
            pass
        else:
            if isinstance(annot, bool):
                annot_data = self.data2d
            else:
                annot_data = np.asarray(annot)
                if annot_data.shape != self.data2d.shape:
                    err = "`data` and `annot` must have same shape."
                    raise ValueError(err)
                annot_data = annot_data[yind][:, xind]
            annot = annot_data

        # Setting ax_cbar=None in clustermap call implies no colorbar
        kws.setdefault("cbar", self.ax_cbar is not None)
        heatmap(self.data2d, ax=self.ax_heatmap, cbar_ax=self.ax_cbar,
                cbar_kws=colorbar_kws, mask=self.mask,
                xticklabels=xtl, yticklabels=ytl, annot=annot, **kws)

        ytl = self.ax_heatmap.get_yticklabels()
        ytl_rot = None if not ytl else ytl[0].get_rotation()
        self.ax_heatmap.yaxis.set_ticks_position('right')
        self.ax_heatmap.yaxis.set_label_position('right')
        if ytl_rot is not None:
            ytl = self.ax_heatmap.get_yticklabels()
            plt.setp(ytl, rotation=ytl_rot)

        tight_params = dict(h_pad=.02, w_pad=.02)
        if self.ax_cbar is None:
            self._figure.tight_layout(**tight_params)
        else:
            # Turn the colorbar axes off for tight layout so that its
            # ticks don't interfere with the rest of the plot layout.
            # Then move it.
            self.ax_cbar.set_axis_off()
            self._figure.tight_layout(**tight_params)
            self.ax_cbar.set_axis_on()
            self.ax_cbar.set_position(self.cbar_pos)

    def plot(self, metric, method, colorbar_kws, row_cluster, col_cluster,
             row_linkage, col_linkage, tree_kws, **kws):

        # heatmap square=True sets the aspect ratio on the axes, but that is
        # not compatible with the multi-axes layout of clustergrid
        if kws.get("square", False):
            msg = "``square=True`` ignored in clustermap"
            warnings.warn(msg)
            kws.pop("square")

        colorbar_kws = {} if colorbar_kws is None else colorbar_kws

        self.plot_dendrograms(row_cluster, col_cluster, metric, method,
                              row_linkage=row_linkage, col_linkage=col_linkage,
                              tree_kws=tree_kws)
        try:
            xind = self.dendrogram_col.reordered_ind
        except AttributeError:
            xind = np.arange(self.data2d.shape[1])
        try:
            yind = self.dendrogram_row.reordered_ind
        except AttributeError:
            yind = np.arange(self.data2d.shape[0])

        self.plot_colors(xind, yind, **kws)
        self.plot_matrix(colorbar_kws, xind, yind, **kws)
        return self


def clustermap(
    data, *,
    pivot_kws=None, method='average', metric='euclidean',
    z_score=None, standard_scale=None, figsize=(10, 10),
    cbar_kws=None, row_cluster=True, col_cluster=True,
    row_linkage=None, col_linkage=None,
    row_colors=None, col_colors=None, mask=None,
    dendrogram_ratio=.2, colors_ratio=0.03,
    cbar_pos=(.02, .8, .05, .18), tree_kws=None,
    **kwargs
):
    """
    Plot a matrix dataset as a hierarchically-clustered heatmap.

    This function requires scipy to be available.

    Parameters
    ----------
    data : 2D array-like
        Rectangular data for clustering. Cannot contain NAs.
    pivot_kws : dict, optional
        If `data` is a tidy dataframe, can provide keyword arguments for
        pivot to create a rectangular dataframe.
    method : str, optional
        Linkage method to use for calculating clusters. See
        :func:`scipy.cluster.hierarchy.linkage` documentation for more
        information.
    metric : str, optional
        Distance metric to use for the data. See
        :func:`scipy.spatial.distance.pdist` documentation for more options.
        To use different metrics (or methods) for rows and columns, you may
        construct each linkage matrix yourself and provide them as
        `{row,col}_linkage`.
    z_score : int or None, optional
        Either 0 (rows) or 1 (columns). Whether or not to calculate z-scores
        for the rows or the columns. Z scores are: z = (x - mean)/std, so
        values in each row (column) will get the mean of the row (column)
        subtracted, then divided by the standard deviation of the row (column).
        This ensures that each row (column) has mean of 0 and variance of 1.
    standard_scale : int or None, optional
        Either 0 (rows) or 1 (columns). Whether or not to standardize that
        dimension, meaning for each row or column, subtract the minimum and
        divide each by its maximum.
    figsize : tuple of (width, height), optional
        Overall size of the figure.
    cbar_kws : dict, optional
        Keyword arguments to pass to `cbar_kws` in :func:`heatmap`, e.g. to
        add a label to the colorbar.
    {row,col}_cluster : bool, optional
        If ``True``, cluster the {rows, columns}.
    {row,col}_linkage : :class:`numpy.ndarray`, optional
        Precomputed linkage matrix for the rows or columns. See
        :func:`scipy.cluster.hierarchy.linkage` for specific formats.
    {row,col}_colors : list-like or pandas DataFrame/Series, optional
        List of colors to label for either the rows or columns. Useful to evaluate
        whether samples within a group are clustered together. Can use nested lists or
        DataFrame for multiple color levels of labeling. If given as a
        :class:`pandas.DataFrame` or :class:`pandas.Series`, labels for the colors are
        extracted from the DataFrames column names or from the name of the Series.
        DataFrame/Series colors are also matched to the data by their index, ensuring
        colors are drawn in the correct order.
    mask : bool array or DataFrame, optional
        If passed, data will not be shown in cells where `mask` is True.
        Cells with missing values are automatically masked. Only used for
        visualizing, not for calculating.
    {dendrogram,colors}_ratio : float, or pair of floats, optional
        Proportion of the figure size devoted to the two marginal elements. If
        a pair is given, they correspond to (row, col) ratios.
    cbar_pos : tuple of (left, bottom, width, height), optional
        Position of the colorbar axes in the figure. Setting to ``None`` will
        disable the colorbar.
    tree_kws : dict, optional
        Parameters for the :class:`matplotlib.collections.LineCollection`
        that is used to plot the lines of the dendrogram tree.
    kwargs : other keyword arguments
        All other keyword arguments are passed to :func:`heatmap`.

    Returns
    -------
    :class:`ClusterGrid`
        A :class:`ClusterGrid` instance.

    See Also
    --------
    heatmap : Plot rectangular data as a color-encoded matrix.

    Notes
    -----
    The returned object has a ``savefig`` method that should be used if you
    want to save the figure object without clipping the dendrograms.

    To access the reordered row indices, use:
    ``clustergrid.dendrogram_row.reordered_ind``

    Column indices, use:
    ``clustergrid.dendrogram_col.reordered_ind``

    Examples
    --------

    .. include:: ../docstrings/clustermap.rst

    """
    if _no_scipy:
        raise RuntimeError("clustermap requires scipy to be available")

    plotter = ClusterGrid(data, pivot_kws=pivot_kws, figsize=figsize,
                          row_colors=row_colors, col_colors=col_colors,
                          z_score=z_score, standard_scale=standard_scale,
                          mask=mask, dendrogram_ratio=dendrogram_ratio,
                          colors_ratio=colors_ratio, cbar_pos=cbar_pos)

    return plotter.plot(metric=metric, method=method,
                        colorbar_kws=cbar_kws,
                        row_cluster=row_cluster, col_cluster=col_cluster,
                        row_linkage=row_linkage, col_linkage=col_linkage,
                        tree_kws=tree_kws, **kwargs)
