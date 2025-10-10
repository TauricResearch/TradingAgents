"""
The Colorizer class which handles the data to color pipeline via a
normalization and a colormap.

.. admonition:: Provisional status of colorizer

    The ``colorizer`` module and classes in this file are considered
    provisional and may change at any time without a deprecation period.

.. seealso::

  :doc:`/gallery/color/colormap_reference` for a list of builtin colormaps.

  :ref:`colormap-manipulation` for examples of how to make colormaps.

  :ref:`colormaps` for an in-depth discussion of choosing colormaps.

  :ref:`colormapnorms` for more details about data normalization.

"""

import functools

import numpy as np
from numpy import ma

from matplotlib import _api, colors, cbook, scale, artist
import matplotlib as mpl

mpl._docstring.interpd.register(
    colorizer_doc="""\
colorizer : `~matplotlib.colorizer.Colorizer` or None, default: None
    The Colorizer object used to map color to data. If None, a Colorizer
    object is created from a *norm* and *cmap*.""",
    )


class Colorizer:
    """
    Data to color pipeline.

    This pipeline is accessible via `.Colorizer.to_rgba` and executed via
    the `.Colorizer.norm` and `.Colorizer.cmap` attributes.

    Parameters
    ----------
    cmap: colorbar.Colorbar or str or None, default: None
        The colormap used to color data.

    norm: colors.Normalize or str or None, default: None
        The normalization used to normalize the data
    """
    def __init__(self, cmap=None, norm=None):

        self._cmap = None
        self._set_cmap(cmap)

        self._id_norm = None
        self._norm = None
        self.norm = norm

        self.callbacks = cbook.CallbackRegistry(signals=["changed"])
        self.colorbar = None

    def _scale_norm(self, norm, vmin, vmax, A):
        """
        Helper for initial scaling.

        Used by public functions that create a ScalarMappable and support
        parameters *vmin*, *vmax* and *norm*. This makes sure that a *norm*
        will take precedence over *vmin*, *vmax*.

        Note that this method does not set the norm.
        """
        if vmin is not None or vmax is not None:
            self.set_clim(vmin, vmax)
            if isinstance(norm, colors.Normalize):
                raise ValueError(
                    "Passing a Normalize instance simultaneously with "
                    "vmin/vmax is not supported.  Please pass vmin/vmax "
                    "directly to the norm when creating it.")

        # always resolve the autoscaling so we have concrete limits
        # rather than deferring to draw time.
        self.autoscale_None(A)

    @property
    def norm(self):
        return self._norm

    @norm.setter
    def norm(self, norm):
        _api.check_isinstance((colors.Normalize, str, None), norm=norm)
        if norm is None:
            norm = colors.Normalize()
        elif isinstance(norm, str):
            try:
                scale_cls = scale._scale_mapping[norm]
            except KeyError:
                raise ValueError(
                    "Invalid norm str name; the following values are "
                    f"supported: {', '.join(scale._scale_mapping)}"
                ) from None
            norm = _auto_norm_from_scale(scale_cls)()

        if norm is self.norm:
            # We aren't updating anything
            return

        in_init = self.norm is None
        # Remove the current callback and connect to the new one
        if not in_init:
            self.norm.callbacks.disconnect(self._id_norm)
        self._norm = norm
        self._id_norm = self.norm.callbacks.connect('changed',
                                                    self.changed)
        if not in_init:
            self.changed()

    def to_rgba(self, x, alpha=None, bytes=False, norm=True):
        """
        Return a normalized RGBA array corresponding to *x*.

        In the normal case, *x* is a 1D or 2D sequence of scalars, and
        the corresponding `~numpy.ndarray` of RGBA values will be returned,
        based on the norm and colormap set for this Colorizer.

        There is one special case, for handling images that are already
        RGB or RGBA, such as might have been read from an image file.
        If *x* is an `~numpy.ndarray` with 3 dimensions,
        and the last dimension is either 3 or 4, then it will be
        treated as an RGB or RGBA array, and no mapping will be done.
        The array can be `~numpy.uint8`, or it can be floats with
        values in the 0-1 range; otherwise a ValueError will be raised.
        Any NaNs or masked elements will be set to 0 alpha.
        If the last dimension is 3, the *alpha* kwarg (defaulting to 1)
        will be used to fill in the transparency.  If the last dimension
        is 4, the *alpha* kwarg is ignored; it does not
        replace the preexisting alpha.  A ValueError will be raised
        if the third dimension is other than 3 or 4.

        In either case, if *bytes* is *False* (default), the RGBA
        array will be floats in the 0-1 range; if it is *True*,
        the returned RGBA array will be `~numpy.uint8` in the 0 to 255 range.

        If norm is False, no normalization of the input data is
        performed, and it is assumed to be in the range (0-1).

        """
        # First check for special case, image input:
        if isinstance(x, np.ndarray) and x.ndim == 3:
            return self._pass_image_data(x, alpha, bytes, norm)

        # Otherwise run norm -> colormap pipeline
        x = ma.asarray(x)
        if norm:
            x = self.norm(x)
        rgba = self.cmap(x, alpha=alpha, bytes=bytes)
        return rgba

    @staticmethod
    def _pass_image_data(x, alpha=None, bytes=False, norm=True):
        """
        Helper function to pass ndarray of shape (...,3) or (..., 4)
        through `to_rgba()`, see `to_rgba()` for docstring.
        """
        if x.shape[2] == 3:
            if alpha is None:
                alpha = 1
            if x.dtype == np.uint8:
                alpha = np.uint8(alpha * 255)
            m, n = x.shape[:2]
            xx = np.empty(shape=(m, n, 4), dtype=x.dtype)
            xx[:, :, :3] = x
            xx[:, :, 3] = alpha
        elif x.shape[2] == 4:
            xx = x
        else:
            raise ValueError("Third dimension must be 3 or 4")
        if xx.dtype.kind == 'f':
            # If any of R, G, B, or A is nan, set to 0
            if np.any(nans := np.isnan(x)):
                if x.shape[2] == 4:
                    xx = xx.copy()
                xx[np.any(nans, axis=2), :] = 0

            if norm and (xx.max() > 1 or xx.min() < 0):
                raise ValueError("Floating point image RGB values "
                                 "must be in the 0..1 range.")
            if bytes:
                xx = (xx * 255).astype(np.uint8)
        elif xx.dtype == np.uint8:
            if not bytes:
                xx = xx.astype(np.float32) / 255
        else:
            raise ValueError("Image RGB array must be uint8 or "
                             "floating point; found %s" % xx.dtype)
        # Account for any masked entries in the original array
        # If any of R, G, B, or A are masked for an entry, we set alpha to 0
        if np.ma.is_masked(x):
            xx[np.any(np.ma.getmaskarray(x), axis=2), 3] = 0
        return xx

    def autoscale(self, A):
        """
        Autoscale the scalar limits on the norm instance using the
        current array
        """
        if A is None:
            raise TypeError('You must first set_array for mappable')
        # If the norm's limits are updated self.changed() will be called
        # through the callbacks attached to the norm
        self.norm.autoscale(A)

    def autoscale_None(self, A):
        """
        Autoscale the scalar limits on the norm instance using the
        current array, changing only limits that are None
        """
        if A is None:
            raise TypeError('You must first set_array for mappable')
        # If the norm's limits are updated self.changed() will be called
        # through the callbacks attached to the norm
        self.norm.autoscale_None(A)

    def _set_cmap(self, cmap):
        """
        Set the colormap for luminance data.

        Parameters
        ----------
        cmap : `.Colormap` or str or None
        """
        # bury import to avoid circular imports
        from matplotlib import cm
        in_init = self._cmap is None
        self._cmap = cm._ensure_cmap(cmap)
        if not in_init:
            self.changed()  # Things are not set up properly yet.

    @property
    def cmap(self):
        return self._cmap

    @cmap.setter
    def cmap(self, cmap):
        self._set_cmap(cmap)

    def set_clim(self, vmin=None, vmax=None):
        """
        Set the norm limits for image scaling.

        Parameters
        ----------
        vmin, vmax : float
             The limits.

             The limits may also be passed as a tuple (*vmin*, *vmax*) as a
             single positional argument.

             .. ACCEPTS: (vmin: float, vmax: float)
        """
        # If the norm's limits are updated self.changed() will be called
        # through the callbacks attached to the norm, this causes an inconsistent
        # state, to prevent this blocked context manager is used
        if vmax is None:
            try:
                vmin, vmax = vmin
            except (TypeError, ValueError):
                pass

        orig_vmin_vmax = self.norm.vmin, self.norm.vmax

        # Blocked context manager prevents callbacks from being triggered
        # until both vmin and vmax are updated
        with self.norm.callbacks.blocked(signal='changed'):
            if vmin is not None:
                self.norm.vmin = colors._sanitize_extrema(vmin)
            if vmax is not None:
                self.norm.vmax = colors._sanitize_extrema(vmax)

        # emit a update signal if the limits are changed
        if orig_vmin_vmax != (self.norm.vmin, self.norm.vmax):
            self.norm.callbacks.process('changed')

    def get_clim(self):
        """
        Return the values (min, max) that are mapped to the colormap limits.
        """
        return self.norm.vmin, self.norm.vmax

    def changed(self):
        """
        Call this whenever the mappable is changed to notify all the
        callbackSM listeners to the 'changed' signal.
        """
        self.callbacks.process('changed')
        self.stale = True

    @property
    def vmin(self):
        return self.get_clim()[0]

    @vmin.setter
    def vmin(self, vmin):
        self.set_clim(vmin=vmin)

    @property
    def vmax(self):
        return self.get_clim()[1]

    @vmax.setter
    def vmax(self, vmax):
        self.set_clim(vmax=vmax)

    @property
    def clip(self):
        return self.norm.clip

    @clip.setter
    def clip(self, clip):
        self.norm.clip = clip


class _ColorizerInterface:
    """
    Base class that contains the interface to `Colorizer` objects from
    a `ColorizingArtist` or `.cm.ScalarMappable`.

    Note: This class only contain functions that interface the .colorizer
    attribute. Other functions that as shared between `.ColorizingArtist`
    and `.cm.ScalarMappable` are not included.
    """
    def _scale_norm(self, norm, vmin, vmax):
        self._colorizer._scale_norm(norm, vmin, vmax, self._A)

    def to_rgba(self, x, alpha=None, bytes=False, norm=True):
        """
        Return a normalized RGBA array corresponding to *x*.

        In the normal case, *x* is a 1D or 2D sequence of scalars, and
        the corresponding `~numpy.ndarray` of RGBA values will be returned,
        based on the norm and colormap set for this Colorizer.

        There is one special case, for handling images that are already
        RGB or RGBA, such as might have been read from an image file.
        If *x* is an `~numpy.ndarray` with 3 dimensions,
        and the last dimension is either 3 or 4, then it will be
        treated as an RGB or RGBA array, and no mapping will be done.
        The array can be `~numpy.uint8`, or it can be floats with
        values in the 0-1 range; otherwise a ValueError will be raised.
        Any NaNs or masked elements will be set to 0 alpha.
        If the last dimension is 3, the *alpha* kwarg (defaulting to 1)
        will be used to fill in the transparency.  If the last dimension
        is 4, the *alpha* kwarg is ignored; it does not
        replace the preexisting alpha.  A ValueError will be raised
        if the third dimension is other than 3 or 4.

        In either case, if *bytes* is *False* (default), the RGBA
        array will be floats in the 0-1 range; if it is *True*,
        the returned RGBA array will be `~numpy.uint8` in the 0 to 255 range.

        If norm is False, no normalization of the input data is
        performed, and it is assumed to be in the range (0-1).

        """
        return self._colorizer.to_rgba(x, alpha=alpha, bytes=bytes, norm=norm)

    def get_clim(self):
        """
        Return the values (min, max) that are mapped to the colormap limits.
        """
        return self._colorizer.get_clim()

    def set_clim(self, vmin=None, vmax=None):
        """
        Set the norm limits for image scaling.

        Parameters
        ----------
        vmin, vmax : float
             The limits.

             For scalar data, the limits may also be passed as a
             tuple (*vmin*, *vmax*) as a single positional argument.

             .. ACCEPTS: (vmin: float, vmax: float)
        """
        # If the norm's limits are updated self.changed() will be called
        # through the callbacks attached to the norm
        self._colorizer.set_clim(vmin, vmax)

    def get_alpha(self):
        try:
            return super().get_alpha()
        except AttributeError:
            return 1

    @property
    def cmap(self):
        return self._colorizer.cmap

    @cmap.setter
    def cmap(self, cmap):
        self._colorizer.cmap = cmap

    def get_cmap(self):
        """Return the `.Colormap` instance."""
        return self._colorizer.cmap

    def set_cmap(self, cmap):
        """
        Set the colormap for luminance data.

        Parameters
        ----------
        cmap : `.Colormap` or str or None
        """
        self.cmap = cmap

    @property
    def norm(self):
        return self._colorizer.norm

    @norm.setter
    def norm(self, norm):
        self._colorizer.norm = norm

    def set_norm(self, norm):
        """
        Set the normalization instance.

        Parameters
        ----------
        norm : `.Normalize` or str or None

        Notes
        -----
        If there are any colorbars using the mappable for this norm, setting
        the norm of the mappable will reset the norm, locator, and formatters
        on the colorbar to default.
        """
        self.norm = norm

    def autoscale(self):
        """
        Autoscale the scalar limits on the norm instance using the
        current array
        """
        self._colorizer.autoscale(self._A)

    def autoscale_None(self):
        """
        Autoscale the scalar limits on the norm instance using the
        current array, changing only limits that are None
        """
        self._colorizer.autoscale_None(self._A)

    @property
    def colorbar(self):
        """
        The last colorbar associated with this object. May be None
        """
        return self._colorizer.colorbar

    @colorbar.setter
    def colorbar(self, colorbar):
        self._colorizer.colorbar = colorbar

    def _format_cursor_data_override(self, data):
        # This function overwrites Artist.format_cursor_data(). We cannot
        # implement cm.ScalarMappable.format_cursor_data() directly, because
        # most cm.ScalarMappable subclasses inherit from Artist first and from
        # cm.ScalarMappable second, so Artist.format_cursor_data would always
        # have precedence over cm.ScalarMappable.format_cursor_data.

        # Note if cm.ScalarMappable is depreciated, this functionality should be
        # implemented as format_cursor_data() on ColorizingArtist.
        n = self.cmap.N
        if np.ma.getmask(data):
            return "[]"
        normed = self.norm(data)
        if np.isfinite(normed):
            if isinstance(self.norm, colors.BoundaryNorm):
                # not an invertible normalization mapping
                cur_idx = np.argmin(np.abs(self.norm.boundaries - data))
                neigh_idx = max(0, cur_idx - 1)
                # use max diff to prevent delta == 0
                delta = np.diff(
                    self.norm.boundaries[neigh_idx:cur_idx + 2]
                ).max()
            elif self.norm.vmin == self.norm.vmax:
                # singular norms, use delta of 10% of only value
                delta = np.abs(self.norm.vmin * .1)
            else:
                # Midpoints of neighboring color intervals.
                neighbors = self.norm.inverse(
                    (int(normed * n) + np.array([0, 1])) / n)
                delta = abs(neighbors - data).max()
            g_sig_digits = cbook._g_sig_digits(data, delta)
        else:
            g_sig_digits = 3  # Consistent with default below.
        return f"[{data:-#.{g_sig_digits}g}]"


class _ScalarMappable(_ColorizerInterface):
    """
    A mixin class to map one or multiple sets of scalar data to RGBA.

    The ScalarMappable applies data normalization before returning RGBA colors from
    the given `~matplotlib.colors.Colormap`.
    """

    # _ScalarMappable exists for compatibility with
    # code written before the introduction of the Colorizer
    # and ColorizingArtist classes.

    # _ScalarMappable can be depreciated so that ColorizingArtist
    # inherits directly from _ColorizerInterface.
    # in this case, the following changes should occur:
    # __init__() has its functionality moved to ColorizingArtist.
    # set_array(), get_array(), _get_colorizer() and
    # _check_exclusionary_keywords() are moved to ColorizingArtist.
    # changed() can be removed so long as colorbar.Colorbar
    # is changed to connect to the colorizer instead of the
    # ScalarMappable/ColorizingArtist,
    # otherwise changed() can be moved to ColorizingArtist.
    def __init__(self, norm=None, cmap=None, *, colorizer=None, **kwargs):
        """
        Parameters
        ----------
        norm : `.Normalize` (or subclass thereof) or str or None
            The normalizing object which scales data, typically into the
            interval ``[0, 1]``.
            If a `str`, a `.Normalize` subclass is dynamically generated based
            on the scale with the corresponding name.
            If *None*, *norm* defaults to a *colors.Normalize* object which
            initializes its scaling based on the first data processed.
        cmap : str or `~matplotlib.colors.Colormap`
            The colormap used to map normalized data values to RGBA colors.
        """
        super().__init__(**kwargs)
        self._A = None
        self._colorizer = self._get_colorizer(colorizer=colorizer, norm=norm, cmap=cmap)

        self.colorbar = None
        self._id_colorizer = self._colorizer.callbacks.connect('changed', self.changed)
        self.callbacks = cbook.CallbackRegistry(signals=["changed"])

    def set_array(self, A):
        """
        Set the value array from array-like *A*.

        Parameters
        ----------
        A : array-like or None
            The values that are mapped to colors.

            The base class `.ScalarMappable` does not make any assumptions on
            the dimensionality and shape of the value array *A*.
        """
        if A is None:
            self._A = None
            return

        A = cbook.safe_masked_invalid(A, copy=True)
        if not np.can_cast(A.dtype, float, "same_kind"):
            raise TypeError(f"Image data of dtype {A.dtype} cannot be "
                            "converted to float")

        self._A = A
        if not self.norm.scaled():
            self._colorizer.autoscale_None(A)

    def get_array(self):
        """
        Return the array of values, that are mapped to colors.

        The base class `.ScalarMappable` does not make any assumptions on
        the dimensionality and shape of the array.
        """
        return self._A

    def changed(self):
        """
        Call this whenever the mappable is changed to notify all the
        callbackSM listeners to the 'changed' signal.
        """
        self.callbacks.process('changed', self)
        self.stale = True

    @staticmethod
    def _check_exclusionary_keywords(colorizer, **kwargs):
        """
        Raises a ValueError if any kwarg is not None while colorizer is not None
        """
        if colorizer is not None:
            if any([val is not None for val in kwargs.values()]):
                raise ValueError("The `colorizer` keyword cannot be used simultaneously"
                                 " with any of the following keywords: "
                                 + ", ".join(f'`{key}`' for key in kwargs.keys()))

    @staticmethod
    def _get_colorizer(cmap, norm, colorizer):
        if isinstance(colorizer, Colorizer):
            _ScalarMappable._check_exclusionary_keywords(
                Colorizer, cmap=cmap, norm=norm
            )
            return colorizer
        return Colorizer(cmap, norm)

# The docstrings here must be generic enough to apply to all relevant methods.
mpl._docstring.interpd.register(
    cmap_doc="""\
cmap : str or `~matplotlib.colors.Colormap`, default: :rc:`image.cmap`
    The Colormap instance or registered colormap name used to map scalar data
    to colors.""",
    norm_doc="""\
norm : str or `~matplotlib.colors.Normalize`, optional
    The normalization method used to scale scalar data to the [0, 1] range
    before mapping to colors using *cmap*. By default, a linear scaling is
    used, mapping the lowest value to 0 and the highest to 1.

    If given, this can be one of the following:

    - An instance of `.Normalize` or one of its subclasses
      (see :ref:`colormapnorms`).
    - A scale name, i.e. one of "linear", "log", "symlog", "logit", etc.  For a
      list of available scales, call `matplotlib.scale.get_scale_names()`.
      In that case, a suitable `.Normalize` subclass is dynamically generated
      and instantiated.""",
    vmin_vmax_doc="""\
vmin, vmax : float, optional
    When using scalar data and no explicit *norm*, *vmin* and *vmax* define
    the data range that the colormap covers. By default, the colormap covers
    the complete value range of the supplied data. It is an error to use
    *vmin*/*vmax* when a *norm* instance is given (but using a `str` *norm*
    name together with *vmin*/*vmax* is acceptable).""",
)


class ColorizingArtist(_ScalarMappable, artist.Artist):
    """
    Base class for artists that make map data to color using a `.colorizer.Colorizer`.

    The `.colorizer.Colorizer` applies data normalization before
    returning RGBA colors from a `~matplotlib.colors.Colormap`.

    """
    def __init__(self, colorizer, **kwargs):
        """
        Parameters
        ----------
        colorizer : `.colorizer.Colorizer`
        """
        _api.check_isinstance(Colorizer, colorizer=colorizer)
        super().__init__(colorizer=colorizer, **kwargs)

    @property
    def colorizer(self):
        return self._colorizer

    @colorizer.setter
    def colorizer(self, cl):
        _api.check_isinstance(Colorizer, colorizer=cl)
        self._colorizer.callbacks.disconnect(self._id_colorizer)
        self._colorizer = cl
        self._id_colorizer = cl.callbacks.connect('changed', self.changed)

    def _set_colorizer_check_keywords(self, colorizer, **kwargs):
        """
        Raises a ValueError if any kwarg is not None while colorizer is not None.
        """
        self._check_exclusionary_keywords(colorizer, **kwargs)
        self.colorizer = colorizer


def _auto_norm_from_scale(scale_cls):
    """
    Automatically generate a norm class from *scale_cls*.

    This differs from `.colors.make_norm_from_scale` in the following points:

    - This function is not a class decorator, but directly returns a norm class
      (as if decorating `.Normalize`).
    - The scale is automatically constructed with ``nonpositive="mask"``, if it
      supports such a parameter, to work around the difference in defaults
      between standard scales (which use "clip") and norms (which use "mask").

    Note that ``make_norm_from_scale`` caches the generated norm classes
    (not the instances) and reuses them for later calls.  For example,
    ``type(_auto_norm_from_scale("log")) == LogNorm``.
    """
    # Actually try to construct an instance, to verify whether
    # ``nonpositive="mask"`` is supported.
    try:
        norm = colors.make_norm_from_scale(
            functools.partial(scale_cls, nonpositive="mask"))(
            colors.Normalize)()
    except TypeError:
        norm = colors.make_norm_from_scale(scale_cls)(
            colors.Normalize)()
    return type(norm)
