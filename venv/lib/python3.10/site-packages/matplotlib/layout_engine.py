"""
Classes to layout elements in a `.Figure`.

Figures have a ``layout_engine`` property that holds a subclass of
`~.LayoutEngine` defined here (or *None* for no layout).  At draw time
``figure.get_layout_engine().execute()`` is called, the goal of which is
usually to rearrange Axes on the figure to produce a pleasing layout. This is
like a ``draw`` callback but with two differences.  First, when printing we
disable the layout engine for the final draw. Second, it is useful to know the
layout engine while the figure is being created.  In particular, colorbars are
made differently with different layout engines (for historical reasons).

Matplotlib has two built-in layout engines:

- `.TightLayoutEngine` was the first layout engine added to Matplotlib.
  See also :ref:`tight_layout_guide`.
- `.ConstrainedLayoutEngine` is more modern and generally gives better results.
  See also :ref:`constrainedlayout_guide`.

Third parties can create their own layout engine by subclassing `.LayoutEngine`.
"""

from contextlib import nullcontext

import matplotlib as mpl

from matplotlib._constrained_layout import do_constrained_layout
from matplotlib._tight_layout import (get_subplotspec_list,
                                      get_tight_layout_figure)


class LayoutEngine:
    """
    Base class for Matplotlib layout engines.

    A layout engine can be passed to a figure at instantiation or at any time
    with `~.figure.Figure.set_layout_engine`.  Once attached to a figure, the
    layout engine ``execute`` function is called at draw time by
    `~.figure.Figure.draw`, providing a special draw-time hook.

    .. note::

       However, note that layout engines affect the creation of colorbars, so
       `~.figure.Figure.set_layout_engine` should be called before any
       colorbars are created.

    Currently, there are two properties of `LayoutEngine` classes that are
    consulted while manipulating the figure:

    - ``engine.colorbar_gridspec`` tells `.Figure.colorbar` whether to make the
       axes using the gridspec method (see `.colorbar.make_axes_gridspec`) or
       not (see `.colorbar.make_axes`);
    - ``engine.adjust_compatible`` stops `.Figure.subplots_adjust` from being
        run if it is not compatible with the layout engine.

    To implement a custom `LayoutEngine`:

    1. override ``_adjust_compatible`` and ``_colorbar_gridspec``
    2. override `LayoutEngine.set` to update *self._params*
    3. override `LayoutEngine.execute` with your implementation

    """
    # override these in subclass
    _adjust_compatible = None
    _colorbar_gridspec = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._params = {}

    def set(self, **kwargs):
        """
        Set the parameters for the layout engine.
        """
        raise NotImplementedError

    @property
    def colorbar_gridspec(self):
        """
        Return a boolean if the layout engine creates colorbars using a
        gridspec.
        """
        if self._colorbar_gridspec is None:
            raise NotImplementedError
        return self._colorbar_gridspec

    @property
    def adjust_compatible(self):
        """
        Return a boolean if the layout engine is compatible with
        `~.Figure.subplots_adjust`.
        """
        if self._adjust_compatible is None:
            raise NotImplementedError
        return self._adjust_compatible

    def get(self):
        """
        Return copy of the parameters for the layout engine.
        """
        return dict(self._params)

    def execute(self, fig):
        """
        Execute the layout on the figure given by *fig*.
        """
        # subclasses must implement this.
        raise NotImplementedError


class PlaceHolderLayoutEngine(LayoutEngine):
    """
    This layout engine does not adjust the figure layout at all.

    The purpose of this `.LayoutEngine` is to act as a placeholder when the user removes
    a layout engine to ensure an incompatible `.LayoutEngine` cannot be set later.

    Parameters
    ----------
    adjust_compatible, colorbar_gridspec : bool
        Allow the PlaceHolderLayoutEngine to mirror the behavior of whatever
        layout engine it is replacing.

    """
    def __init__(self, adjust_compatible, colorbar_gridspec, **kwargs):
        self._adjust_compatible = adjust_compatible
        self._colorbar_gridspec = colorbar_gridspec
        super().__init__(**kwargs)

    def execute(self, fig):
        """
        Do nothing.
        """
        return


class TightLayoutEngine(LayoutEngine):
    """
    Implements the ``tight_layout`` geometry management.  See
    :ref:`tight_layout_guide` for details.
    """
    _adjust_compatible = True
    _colorbar_gridspec = True

    def __init__(self, *, pad=1.08, h_pad=None, w_pad=None,
                 rect=(0, 0, 1, 1), **kwargs):
        """
        Initialize tight_layout engine.

        Parameters
        ----------
        pad : float, default: 1.08
            Padding between the figure edge and the edges of subplots, as a
            fraction of the font size.
        h_pad, w_pad : float
            Padding (height/width) between edges of adjacent subplots.
            Defaults to *pad*.
        rect : tuple (left, bottom, right, top), default: (0, 0, 1, 1).
            rectangle in normalized figure coordinates that the subplots
            (including labels) will fit into.
        """
        super().__init__(**kwargs)
        for td in ['pad', 'h_pad', 'w_pad', 'rect']:
            # initialize these in case None is passed in above:
            self._params[td] = None
        self.set(pad=pad, h_pad=h_pad, w_pad=w_pad, rect=rect)

    def execute(self, fig):
        """
        Execute tight_layout.

        This decides the subplot parameters given the padding that
        will allow the Axes labels to not be covered by other labels
        and Axes.

        Parameters
        ----------
        fig : `.Figure` to perform layout on.

        See Also
        --------
        .figure.Figure.tight_layout
        .pyplot.tight_layout
        """
        info = self._params
        renderer = fig._get_renderer()
        with getattr(renderer, "_draw_disabled", nullcontext)():
            kwargs = get_tight_layout_figure(
                fig, fig.axes, get_subplotspec_list(fig.axes), renderer,
                pad=info['pad'], h_pad=info['h_pad'], w_pad=info['w_pad'],
                rect=info['rect'])
        if kwargs:
            fig.subplots_adjust(**kwargs)

    def set(self, *, pad=None, w_pad=None, h_pad=None, rect=None):
        """
        Set the pads for tight_layout.

        Parameters
        ----------
        pad : float
            Padding between the figure edge and the edges of subplots, as a
            fraction of the font size.
        w_pad, h_pad : float
            Padding (width/height) between edges of adjacent subplots.
            Defaults to *pad*.
        rect : tuple (left, bottom, right, top)
            rectangle in normalized figure coordinates that the subplots
            (including labels) will fit into.
        """
        for td in self.set.__kwdefaults__:
            if locals()[td] is not None:
                self._params[td] = locals()[td]


class ConstrainedLayoutEngine(LayoutEngine):
    """
    Implements the ``constrained_layout`` geometry management.  See
    :ref:`constrainedlayout_guide` for details.
    """

    _adjust_compatible = False
    _colorbar_gridspec = False

    def __init__(self, *, h_pad=None, w_pad=None,
                 hspace=None, wspace=None, rect=(0, 0, 1, 1),
                 compress=False, **kwargs):
        """
        Initialize ``constrained_layout`` settings.

        Parameters
        ----------
        h_pad, w_pad : float
            Padding around the Axes elements in inches.
            Default to :rc:`figure.constrained_layout.h_pad` and
            :rc:`figure.constrained_layout.w_pad`.
        hspace, wspace : float
            Fraction of the figure to dedicate to space between the
            axes.  These are evenly spread between the gaps between the Axes.
            A value of 0.2 for a three-column layout would have a space
            of 0.1 of the figure width between each column.
            If h/wspace < h/w_pad, then the pads are used instead.
            Default to :rc:`figure.constrained_layout.hspace` and
            :rc:`figure.constrained_layout.wspace`.
        rect : tuple of 4 floats
            Rectangle in figure coordinates to perform constrained layout in
            (left, bottom, width, height), each from 0-1.
        compress : bool
            Whether to shift Axes so that white space in between them is
            removed. This is useful for simple grids of fixed-aspect Axes (e.g.
            a grid of images).  See :ref:`compressed_layout`.
        """
        super().__init__(**kwargs)
        # set the defaults:
        self.set(w_pad=mpl.rcParams['figure.constrained_layout.w_pad'],
                 h_pad=mpl.rcParams['figure.constrained_layout.h_pad'],
                 wspace=mpl.rcParams['figure.constrained_layout.wspace'],
                 hspace=mpl.rcParams['figure.constrained_layout.hspace'],
                 rect=(0, 0, 1, 1))
        # set anything that was passed in (None will be ignored):
        self.set(w_pad=w_pad, h_pad=h_pad, wspace=wspace, hspace=hspace,
                 rect=rect)
        self._compress = compress

    def execute(self, fig):
        """
        Perform constrained_layout and move and resize Axes accordingly.

        Parameters
        ----------
        fig : `.Figure` to perform layout on.
        """
        width, height = fig.get_size_inches()
        # pads are relative to the current state of the figure...
        w_pad = self._params['w_pad'] / width
        h_pad = self._params['h_pad'] / height

        return do_constrained_layout(fig, w_pad=w_pad, h_pad=h_pad,
                                     wspace=self._params['wspace'],
                                     hspace=self._params['hspace'],
                                     rect=self._params['rect'],
                                     compress=self._compress)

    def set(self, *, h_pad=None, w_pad=None,
            hspace=None, wspace=None, rect=None):
        """
        Set the pads for constrained_layout.

        Parameters
        ----------
        h_pad, w_pad : float
            Padding around the Axes elements in inches.
            Default to :rc:`figure.constrained_layout.h_pad` and
            :rc:`figure.constrained_layout.w_pad`.
        hspace, wspace : float
            Fraction of the figure to dedicate to space between the
            axes.  These are evenly spread between the gaps between the Axes.
            A value of 0.2 for a three-column layout would have a space
            of 0.1 of the figure width between each column.
            If h/wspace < h/w_pad, then the pads are used instead.
            Default to :rc:`figure.constrained_layout.hspace` and
            :rc:`figure.constrained_layout.wspace`.
        rect : tuple of 4 floats
            Rectangle in figure coordinates to perform constrained layout in
            (left, bottom, width, height), each from 0-1.
        """
        for td in self.set.__kwdefaults__:
            if locals()[td] is not None:
                self._params[td] = locals()[td]
