from types import MethodType

import numpy as np

from .axes_divider import make_axes_locatable, Size
from .mpl_axes import Axes, SimpleAxisArtist


def make_rgb_axes(ax, pad=0.01, axes_class=None, **kwargs):
    """
    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        Axes instance to create the RGB Axes in.
    pad : float, optional
        Fraction of the Axes height to pad.
    axes_class : `matplotlib.axes.Axes` or None, optional
        Axes class to use for the R, G, and B Axes. If None, use
        the same class as *ax*.
    **kwargs
        Forwarded to *axes_class* init for the R, G, and B Axes.
    """

    divider = make_axes_locatable(ax)

    pad_size = pad * Size.AxesY(ax)

    xsize = ((1-2*pad)/3) * Size.AxesX(ax)
    ysize = ((1-2*pad)/3) * Size.AxesY(ax)

    divider.set_horizontal([Size.AxesX(ax), pad_size, xsize])
    divider.set_vertical([ysize, pad_size, ysize, pad_size, ysize])

    ax.set_axes_locator(divider.new_locator(0, 0, ny1=-1))

    ax_rgb = []
    if axes_class is None:
        axes_class = type(ax)

    for ny in [4, 2, 0]:
        ax1 = axes_class(ax.get_figure(), ax.get_position(original=True),
                         sharex=ax, sharey=ax, **kwargs)
        locator = divider.new_locator(nx=2, ny=ny)
        ax1.set_axes_locator(locator)
        for t in ax1.yaxis.get_ticklabels() + ax1.xaxis.get_ticklabels():
            t.set_visible(False)
        try:
            for axis in ax1.axis.values():
                axis.major_ticklabels.set_visible(False)
        except AttributeError:
            pass

        ax_rgb.append(ax1)

    fig = ax.get_figure()
    for ax1 in ax_rgb:
        fig.add_axes(ax1)

    return ax_rgb


class RGBAxes:
    """
    4-panel `~.Axes.imshow` (RGB, R, G, B).

    Layout::

        ┌───────────────┬─────┐
        │               │  R  │
        │               ├─────┤
        │      RGB      │  G  │
        │               ├─────┤
        │               │  B  │
        └───────────────┴─────┘

    Subclasses can override the ``_defaultAxesClass`` attribute.
    By default RGBAxes uses `.mpl_axes.Axes`.

    Attributes
    ----------
    RGB : ``_defaultAxesClass``
        The Axes object for the three-channel `~.Axes.imshow`.
    R : ``_defaultAxesClass``
        The Axes object for the red channel `~.Axes.imshow`.
    G : ``_defaultAxesClass``
        The Axes object for the green channel `~.Axes.imshow`.
    B : ``_defaultAxesClass``
        The Axes object for the blue channel `~.Axes.imshow`.
    """

    _defaultAxesClass = Axes

    def __init__(self, *args, pad=0, **kwargs):
        """
        Parameters
        ----------
        pad : float, default: 0
            Fraction of the Axes height to put as padding.
        axes_class : `~matplotlib.axes.Axes`
            Axes class to use. If not provided, ``_defaultAxesClass`` is used.
        *args
            Forwarded to *axes_class* init for the RGB Axes
        **kwargs
            Forwarded to *axes_class* init for the RGB, R, G, and B Axes
        """
        axes_class = kwargs.pop("axes_class", self._defaultAxesClass)
        self.RGB = ax = axes_class(*args, **kwargs)
        ax.get_figure().add_axes(ax)
        self.R, self.G, self.B = make_rgb_axes(
            ax, pad=pad, axes_class=axes_class, **kwargs)
        # Set the line color and ticks for the axes.
        for ax1 in [self.RGB, self.R, self.G, self.B]:
            if isinstance(ax1.axis, MethodType):
                ad = Axes.AxisDict(self)
                ad.update(
                    bottom=SimpleAxisArtist(ax1.xaxis, 1, ax1.spines["bottom"]),
                    top=SimpleAxisArtist(ax1.xaxis, 2, ax1.spines["top"]),
                    left=SimpleAxisArtist(ax1.yaxis, 1, ax1.spines["left"]),
                    right=SimpleAxisArtist(ax1.yaxis, 2, ax1.spines["right"]))
            else:
                ad = ax1.axis
            ad[:].line.set_color("w")
            ad[:].major_ticks.set_markeredgecolor("w")

    def imshow_rgb(self, r, g, b, **kwargs):
        """
        Create the four images {rgb, r, g, b}.

        Parameters
        ----------
        r, g, b : array-like
            The red, green, and blue arrays.
        **kwargs
            Forwarded to `~.Axes.imshow` calls for the four images.

        Returns
        -------
        rgb : `~matplotlib.image.AxesImage`
        r : `~matplotlib.image.AxesImage`
        g : `~matplotlib.image.AxesImage`
        b : `~matplotlib.image.AxesImage`
        """
        if not (r.shape == g.shape == b.shape):
            raise ValueError(
                f'Input shapes ({r.shape}, {g.shape}, {b.shape}) do not match')
        RGB = np.dstack([r, g, b])
        R = np.zeros_like(RGB)
        R[:, :, 0] = r
        G = np.zeros_like(RGB)
        G[:, :, 1] = g
        B = np.zeros_like(RGB)
        B[:, :, 2] = b
        im_rgb = self.RGB.imshow(RGB, **kwargs)
        im_r = self.R.imshow(R, **kwargs)
        im_g = self.G.imshow(G, **kwargs)
        im_b = self.B.imshow(B, **kwargs)
        return im_rgb, im_r, im_g, im_b
