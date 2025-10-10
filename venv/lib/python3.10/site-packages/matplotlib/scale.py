"""
Scales define the distribution of data values on an axis, e.g. a log scaling.

The mapping is implemented through `.Transform` subclasses.

The following scales are built-in:

.. _builtin_scales:

============= ===================== ================================ =================================
Name          Class                 Transform                        Inverted transform
============= ===================== ================================ =================================
"asinh"       `AsinhScale`          `AsinhTransform`                 `InvertedAsinhTransform`
"function"    `FuncScale`           `FuncTransform`                  `FuncTransform`
"functionlog" `FuncScaleLog`        `FuncTransform` + `LogTransform` `InvertedLogTransform` + `FuncTransform`
"linear"      `LinearScale`         `.IdentityTransform`             `.IdentityTransform`
"log"         `LogScale`            `LogTransform`                   `InvertedLogTransform`
"logit"       `LogitScale`          `LogitTransform`                 `LogisticTransform`
"symlog"      `SymmetricalLogScale` `SymmetricalLogTransform`        `InvertedSymmetricalLogTransform`
============= ===================== ================================ =================================

A user will often only use the scale name, e.g. when setting the scale through
`~.Axes.set_xscale`: ``ax.set_xscale("log")``.

See also the :ref:`scales examples <sphx_glr_gallery_scales>` in the documentation.

Custom scaling can be achieved through `FuncScale`, or by creating your own
`ScaleBase` subclass and corresponding transforms (see :doc:`/gallery/scales/custom_scale`).
Third parties can register their scales by name through `register_scale`.
"""  # noqa: E501

import inspect
import textwrap

import numpy as np

import matplotlib as mpl
from matplotlib import _api, _docstring
from matplotlib.ticker import (
    NullFormatter, ScalarFormatter, LogFormatterSciNotation, LogitFormatter,
    NullLocator, LogLocator, AutoLocator, AutoMinorLocator,
    SymmetricalLogLocator, AsinhLocator, LogitLocator)
from matplotlib.transforms import Transform, IdentityTransform


class ScaleBase:
    """
    The base class for all scales.

    Scales are separable transformations, working on a single dimension.

    Subclasses should override

    :attr:`name`
        The scale's name.
    :meth:`get_transform`
        A method returning a `.Transform`, which converts data coordinates to
        scaled coordinates.  This transform should be invertible, so that e.g.
        mouse positions can be converted back to data coordinates.
    :meth:`set_default_locators_and_formatters`
        A method that sets default locators and formatters for an `~.axis.Axis`
        that uses this scale.
    :meth:`limit_range_for_scale`
        An optional method that "fixes" the axis range to acceptable values,
        e.g. restricting log-scaled axes to positive values.
    """

    def __init__(self, axis):
        r"""
        Construct a new scale.

        Notes
        -----
        The following note is for scale implementers.

        For back-compatibility reasons, scales take an `~matplotlib.axis.Axis`
        object as first argument.  However, this argument should not
        be used: a single scale object should be usable by multiple
        `~matplotlib.axis.Axis`\es at the same time.
        """

    def get_transform(self):
        """
        Return the `.Transform` object associated with this scale.
        """
        raise NotImplementedError()

    def set_default_locators_and_formatters(self, axis):
        """
        Set the locators and formatters of *axis* to instances suitable for
        this scale.
        """
        raise NotImplementedError()

    def limit_range_for_scale(self, vmin, vmax, minpos):
        """
        Return the range *vmin*, *vmax*, restricted to the
        domain supported by this scale (if any).

        *minpos* should be the minimum positive value in the data.
        This is used by log scales to determine a minimum value.
        """
        return vmin, vmax


class LinearScale(ScaleBase):
    """
    The default linear scale.
    """

    name = 'linear'

    def __init__(self, axis):
        # This method is present only to prevent inheritance of the base class'
        # constructor docstring, which would otherwise end up interpolated into
        # the docstring of Axis.set_scale.
        """
        """  # noqa: D419

    def set_default_locators_and_formatters(self, axis):
        # docstring inherited
        axis.set_major_locator(AutoLocator())
        axis.set_major_formatter(ScalarFormatter())
        axis.set_minor_formatter(NullFormatter())
        # update the minor locator for x and y axis based on rcParams
        if (axis.axis_name == 'x' and mpl.rcParams['xtick.minor.visible'] or
                axis.axis_name == 'y' and mpl.rcParams['ytick.minor.visible']):
            axis.set_minor_locator(AutoMinorLocator())
        else:
            axis.set_minor_locator(NullLocator())

    def get_transform(self):
        """
        Return the transform for linear scaling, which is just the
        `~matplotlib.transforms.IdentityTransform`.
        """
        return IdentityTransform()


class FuncTransform(Transform):
    """
    A simple transform that takes and arbitrary function for the
    forward and inverse transform.
    """

    input_dims = output_dims = 1

    def __init__(self, forward, inverse):
        """
        Parameters
        ----------
        forward : callable
            The forward function for the transform.  This function must have
            an inverse and, for best behavior, be monotonic.
            It must have the signature::

               def forward(values: array-like) -> array-like

        inverse : callable
            The inverse of the forward function.  Signature as ``forward``.
        """
        super().__init__()
        if callable(forward) and callable(inverse):
            self._forward = forward
            self._inverse = inverse
        else:
            raise ValueError('arguments to FuncTransform must be functions')

    def transform_non_affine(self, values):
        return self._forward(values)

    def inverted(self):
        return FuncTransform(self._inverse, self._forward)


class FuncScale(ScaleBase):
    """
    Provide an arbitrary scale with user-supplied function for the axis.
    """

    name = 'function'

    def __init__(self, axis, functions):
        """
        Parameters
        ----------
        axis : `~matplotlib.axis.Axis`
            The axis for the scale.
        functions : (callable, callable)
            two-tuple of the forward and inverse functions for the scale.
            The forward function must be monotonic.

            Both functions must have the signature::

               def forward(values: array-like) -> array-like
        """
        forward, inverse = functions
        transform = FuncTransform(forward, inverse)
        self._transform = transform

    def get_transform(self):
        """Return the `.FuncTransform` associated with this scale."""
        return self._transform

    def set_default_locators_and_formatters(self, axis):
        # docstring inherited
        axis.set_major_locator(AutoLocator())
        axis.set_major_formatter(ScalarFormatter())
        axis.set_minor_formatter(NullFormatter())
        # update the minor locator for x and y axis based on rcParams
        if (axis.axis_name == 'x' and mpl.rcParams['xtick.minor.visible'] or
                axis.axis_name == 'y' and mpl.rcParams['ytick.minor.visible']):
            axis.set_minor_locator(AutoMinorLocator())
        else:
            axis.set_minor_locator(NullLocator())


class LogTransform(Transform):
    input_dims = output_dims = 1

    def __init__(self, base, nonpositive='clip'):
        super().__init__()
        if base <= 0 or base == 1:
            raise ValueError('The log base cannot be <= 0 or == 1')
        self.base = base
        self._clip = _api.check_getitem(
            {"clip": True, "mask": False}, nonpositive=nonpositive)

    def __str__(self):
        return "{}(base={}, nonpositive={!r})".format(
            type(self).__name__, self.base, "clip" if self._clip else "mask")

    def transform_non_affine(self, values):
        # Ignore invalid values due to nans being passed to the transform.
        with np.errstate(divide="ignore", invalid="ignore"):
            log = {np.e: np.log, 2: np.log2, 10: np.log10}.get(self.base)
            if log:  # If possible, do everything in a single call to NumPy.
                out = log(values)
            else:
                out = np.log(values)
                out /= np.log(self.base)
            if self._clip:
                # SVG spec says that conforming viewers must support values up
                # to 3.4e38 (C float); however experiments suggest that
                # Inkscape (which uses cairo for rendering) runs into cairo's
                # 24-bit limit (which is apparently shared by Agg).
                # Ghostscript (used for pdf rendering appears to overflow even
                # earlier, with the max value around 2 ** 15 for the tests to
                # pass. On the other hand, in practice, we want to clip beyond
                #     np.log10(np.nextafter(0, 1)) ~ -323
                # so 1000 seems safe.
                out[values <= 0] = -1000
        return out

    def inverted(self):
        return InvertedLogTransform(self.base)


class InvertedLogTransform(Transform):
    input_dims = output_dims = 1

    def __init__(self, base):
        super().__init__()
        self.base = base

    def __str__(self):
        return f"{type(self).__name__}(base={self.base})"

    def transform_non_affine(self, values):
        return np.power(self.base, values)

    def inverted(self):
        return LogTransform(self.base)


class LogScale(ScaleBase):
    """
    A standard logarithmic scale.  Care is taken to only plot positive values.
    """
    name = 'log'

    def __init__(self, axis, *, base=10, subs=None, nonpositive="clip"):
        """
        Parameters
        ----------
        axis : `~matplotlib.axis.Axis`
            The axis for the scale.
        base : float, default: 10
            The base of the logarithm.
        nonpositive : {'clip', 'mask'}, default: 'clip'
            Determines the behavior for non-positive values. They can either
            be masked as invalid, or clipped to a very small positive number.
        subs : sequence of int, default: None
            Where to place the subticks between each major tick.  For example,
            in a log10 scale, ``[2, 3, 4, 5, 6, 7, 8, 9]`` will place 8
            logarithmically spaced minor ticks between each major tick.
        """
        self._transform = LogTransform(base, nonpositive)
        self.subs = subs

    base = property(lambda self: self._transform.base)

    def set_default_locators_and_formatters(self, axis):
        # docstring inherited
        axis.set_major_locator(LogLocator(self.base))
        axis.set_major_formatter(LogFormatterSciNotation(self.base))
        axis.set_minor_locator(LogLocator(self.base, self.subs))
        axis.set_minor_formatter(
            LogFormatterSciNotation(self.base,
                                    labelOnlyBase=(self.subs is not None)))

    def get_transform(self):
        """Return the `.LogTransform` associated with this scale."""
        return self._transform

    def limit_range_for_scale(self, vmin, vmax, minpos):
        """Limit the domain to positive values."""
        if not np.isfinite(minpos):
            minpos = 1e-300  # Should rarely (if ever) have a visible effect.

        return (minpos if vmin <= 0 else vmin,
                minpos if vmax <= 0 else vmax)


class FuncScaleLog(LogScale):
    """
    Provide an arbitrary scale with user-supplied function for the axis and
    then put on a logarithmic axes.
    """

    name = 'functionlog'

    def __init__(self, axis, functions, base=10):
        """
        Parameters
        ----------
        axis : `~matplotlib.axis.Axis`
            The axis for the scale.
        functions : (callable, callable)
            two-tuple of the forward and inverse functions for the scale.
            The forward function must be monotonic.

            Both functions must have the signature::

                def forward(values: array-like) -> array-like

        base : float, default: 10
            Logarithmic base of the scale.
        """
        forward, inverse = functions
        self.subs = None
        self._transform = FuncTransform(forward, inverse) + LogTransform(base)

    @property
    def base(self):
        return self._transform._b.base  # Base of the LogTransform.

    def get_transform(self):
        """Return the `.Transform` associated with this scale."""
        return self._transform


class SymmetricalLogTransform(Transform):
    input_dims = output_dims = 1

    def __init__(self, base, linthresh, linscale):
        super().__init__()
        if base <= 1.0:
            raise ValueError("'base' must be larger than 1")
        if linthresh <= 0.0:
            raise ValueError("'linthresh' must be positive")
        if linscale <= 0.0:
            raise ValueError("'linscale' must be positive")
        self.base = base
        self.linthresh = linthresh
        self.linscale = linscale
        self._linscale_adj = (linscale / (1.0 - self.base ** -1))
        self._log_base = np.log(base)

    def transform_non_affine(self, values):
        abs_a = np.abs(values)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.sign(values) * self.linthresh * (
                self._linscale_adj +
                np.log(abs_a / self.linthresh) / self._log_base)
            inside = abs_a <= self.linthresh
        out[inside] = values[inside] * self._linscale_adj
        return out

    def inverted(self):
        return InvertedSymmetricalLogTransform(self.base, self.linthresh,
                                               self.linscale)


class InvertedSymmetricalLogTransform(Transform):
    input_dims = output_dims = 1

    def __init__(self, base, linthresh, linscale):
        super().__init__()
        symlog = SymmetricalLogTransform(base, linthresh, linscale)
        self.base = base
        self.linthresh = linthresh
        self.invlinthresh = symlog.transform(linthresh)
        self.linscale = linscale
        self._linscale_adj = (linscale / (1.0 - self.base ** -1))

    def transform_non_affine(self, values):
        abs_a = np.abs(values)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.sign(values) * self.linthresh * (
                np.power(self.base,
                         abs_a / self.linthresh - self._linscale_adj))
            inside = abs_a <= self.invlinthresh
        out[inside] = values[inside] / self._linscale_adj
        return out

    def inverted(self):
        return SymmetricalLogTransform(self.base,
                                       self.linthresh, self.linscale)


class SymmetricalLogScale(ScaleBase):
    """
    The symmetrical logarithmic scale is logarithmic in both the
    positive and negative directions from the origin.

    Since the values close to zero tend toward infinity, there is a
    need to have a range around zero that is linear.  The parameter
    *linthresh* allows the user to specify the size of this range
    (-*linthresh*, *linthresh*).

    See :doc:`/gallery/scales/symlog_demo` for a detailed description.

    Parameters
    ----------
    base : float, default: 10
        The base of the logarithm.

    linthresh : float, default: 2
        Defines the range ``(-x, x)``, within which the plot is linear.
        This avoids having the plot go to infinity around zero.

    subs : sequence of int
        Where to place the subticks between each major tick.
        For example, in a log10 scale: ``[2, 3, 4, 5, 6, 7, 8, 9]`` will place
        8 logarithmically spaced minor ticks between each major tick.

    linscale : float, optional
        This allows the linear range ``(-linthresh, linthresh)`` to be
        stretched relative to the logarithmic range. Its value is the number of
        decades to use for each half of the linear range. For example, when
        *linscale* == 1.0 (the default), the space used for the positive and
        negative halves of the linear range will be equal to one decade in
        the logarithmic range.
    """
    name = 'symlog'

    def __init__(self, axis, *, base=10, linthresh=2, subs=None, linscale=1):
        self._transform = SymmetricalLogTransform(base, linthresh, linscale)
        self.subs = subs

    base = property(lambda self: self._transform.base)
    linthresh = property(lambda self: self._transform.linthresh)
    linscale = property(lambda self: self._transform.linscale)

    def set_default_locators_and_formatters(self, axis):
        # docstring inherited
        axis.set_major_locator(SymmetricalLogLocator(self.get_transform()))
        axis.set_major_formatter(LogFormatterSciNotation(self.base))
        axis.set_minor_locator(SymmetricalLogLocator(self.get_transform(),
                                                     self.subs))
        axis.set_minor_formatter(NullFormatter())

    def get_transform(self):
        """Return the `.SymmetricalLogTransform` associated with this scale."""
        return self._transform


class AsinhTransform(Transform):
    """Inverse hyperbolic-sine transformation used by `.AsinhScale`"""
    input_dims = output_dims = 1

    def __init__(self, linear_width):
        super().__init__()
        if linear_width <= 0.0:
            raise ValueError("Scale parameter 'linear_width' " +
                             "must be strictly positive")
        self.linear_width = linear_width

    def transform_non_affine(self, values):
        return self.linear_width * np.arcsinh(values / self.linear_width)

    def inverted(self):
        return InvertedAsinhTransform(self.linear_width)


class InvertedAsinhTransform(Transform):
    """Hyperbolic sine transformation used by `.AsinhScale`"""
    input_dims = output_dims = 1

    def __init__(self, linear_width):
        super().__init__()
        self.linear_width = linear_width

    def transform_non_affine(self, values):
        return self.linear_width * np.sinh(values / self.linear_width)

    def inverted(self):
        return AsinhTransform(self.linear_width)


class AsinhScale(ScaleBase):
    """
    A quasi-logarithmic scale based on the inverse hyperbolic sine (asinh)

    For values close to zero, this is essentially a linear scale,
    but for large magnitude values (either positive or negative)
    it is asymptotically logarithmic. The transition between these
    linear and logarithmic regimes is smooth, and has no discontinuities
    in the function gradient in contrast to
    the `.SymmetricalLogScale` ("symlog") scale.

    Specifically, the transformation of an axis coordinate :math:`a` is
    :math:`a \\rightarrow a_0 \\sinh^{-1} (a / a_0)` where :math:`a_0`
    is the effective width of the linear region of the transformation.
    In that region, the transformation is
    :math:`a \\rightarrow a + \\mathcal{O}(a^3)`.
    For large values of :math:`a` the transformation behaves as
    :math:`a \\rightarrow a_0 \\, \\mathrm{sgn}(a) \\ln |a| + \\mathcal{O}(1)`.

    .. note::

       This API is provisional and may be revised in the future
       based on early user feedback.
    """

    name = 'asinh'

    auto_tick_multipliers = {
        3: (2, ),
        4: (2, ),
        5: (2, ),
        8: (2, 4),
        10: (2, 5),
        16: (2, 4, 8),
        64: (4, 16),
        1024: (256, 512)
    }

    def __init__(self, axis, *, linear_width=1.0,
                 base=10, subs='auto', **kwargs):
        """
        Parameters
        ----------
        linear_width : float, default: 1
            The scale parameter (elsewhere referred to as :math:`a_0`)
            defining the extent of the quasi-linear region,
            and the coordinate values beyond which the transformation
            becomes asymptotically logarithmic.
        base : int, default: 10
            The number base used for rounding tick locations
            on a logarithmic scale. If this is less than one,
            then rounding is to the nearest integer multiple
            of powers of ten.
        subs : sequence of int
            Multiples of the number base used for minor ticks.
            If set to 'auto', this will use built-in defaults,
            e.g. (2, 5) for base=10.
        """
        super().__init__(axis)
        self._transform = AsinhTransform(linear_width)
        self._base = int(base)
        if subs == 'auto':
            self._subs = self.auto_tick_multipliers.get(self._base)
        else:
            self._subs = subs

    linear_width = property(lambda self: self._transform.linear_width)

    def get_transform(self):
        return self._transform

    def set_default_locators_and_formatters(self, axis):
        axis.set(major_locator=AsinhLocator(self.linear_width,
                                            base=self._base),
                 minor_locator=AsinhLocator(self.linear_width,
                                            base=self._base,
                                            subs=self._subs),
                 minor_formatter=NullFormatter())
        if self._base > 1:
            axis.set_major_formatter(LogFormatterSciNotation(self._base))
        else:
            axis.set_major_formatter('{x:.3g}')


class LogitTransform(Transform):
    input_dims = output_dims = 1

    def __init__(self, nonpositive='mask'):
        super().__init__()
        _api.check_in_list(['mask', 'clip'], nonpositive=nonpositive)
        self._nonpositive = nonpositive
        self._clip = {"clip": True, "mask": False}[nonpositive]

    def transform_non_affine(self, values):
        """logit transform (base 10), masked or clipped"""
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.log10(values / (1 - values))
        if self._clip:  # See LogTransform for choice of clip value.
            out[values <= 0] = -1000
            out[1 <= values] = 1000
        return out

    def inverted(self):
        return LogisticTransform(self._nonpositive)

    def __str__(self):
        return f"{type(self).__name__}({self._nonpositive!r})"


class LogisticTransform(Transform):
    input_dims = output_dims = 1

    def __init__(self, nonpositive='mask'):
        super().__init__()
        self._nonpositive = nonpositive

    def transform_non_affine(self, values):
        """logistic transform (base 10)"""
        return 1.0 / (1 + 10**(-values))

    def inverted(self):
        return LogitTransform(self._nonpositive)

    def __str__(self):
        return f"{type(self).__name__}({self._nonpositive!r})"


class LogitScale(ScaleBase):
    """
    Logit scale for data between zero and one, both excluded.

    This scale is similar to a log scale close to zero and to one, and almost
    linear around 0.5. It maps the interval ]0, 1[ onto ]-infty, +infty[.
    """
    name = 'logit'

    def __init__(self, axis, nonpositive='mask', *,
                 one_half=r"\frac{1}{2}", use_overline=False):
        r"""
        Parameters
        ----------
        axis : `~matplotlib.axis.Axis`
            Currently unused.
        nonpositive : {'mask', 'clip'}
            Determines the behavior for values beyond the open interval ]0, 1[.
            They can either be masked as invalid, or clipped to a number very
            close to 0 or 1.
        use_overline : bool, default: False
            Indicate the usage of survival notation (\overline{x}) in place of
            standard notation (1-x) for probability close to one.
        one_half : str, default: r"\frac{1}{2}"
            The string used for ticks formatter to represent 1/2.
        """
        self._transform = LogitTransform(nonpositive)
        self._use_overline = use_overline
        self._one_half = one_half

    def get_transform(self):
        """Return the `.LogitTransform` associated with this scale."""
        return self._transform

    def set_default_locators_and_formatters(self, axis):
        # docstring inherited
        # ..., 0.01, 0.1, 0.5, 0.9, 0.99, ...
        axis.set_major_locator(LogitLocator())
        axis.set_major_formatter(
            LogitFormatter(
                one_half=self._one_half,
                use_overline=self._use_overline
            )
        )
        axis.set_minor_locator(LogitLocator(minor=True))
        axis.set_minor_formatter(
            LogitFormatter(
                minor=True,
                one_half=self._one_half,
                use_overline=self._use_overline
            )
        )

    def limit_range_for_scale(self, vmin, vmax, minpos):
        """
        Limit the domain to values between 0 and 1 (excluded).
        """
        if not np.isfinite(minpos):
            minpos = 1e-7  # Should rarely (if ever) have a visible effect.
        return (minpos if vmin <= 0 else vmin,
                1 - minpos if vmax >= 1 else vmax)


_scale_mapping = {
    'linear': LinearScale,
    'log':    LogScale,
    'symlog': SymmetricalLogScale,
    'asinh':  AsinhScale,
    'logit':  LogitScale,
    'function': FuncScale,
    'functionlog': FuncScaleLog,
    }


def get_scale_names():
    """Return the names of the available scales."""
    return sorted(_scale_mapping)


def scale_factory(scale, axis, **kwargs):
    """
    Return a scale class by name.

    Parameters
    ----------
    scale : {%(names)s}
    axis : `~matplotlib.axis.Axis`
    """
    scale_cls = _api.check_getitem(_scale_mapping, scale=scale)
    return scale_cls(axis, **kwargs)


if scale_factory.__doc__:
    scale_factory.__doc__ = scale_factory.__doc__ % {
        "names": ", ".join(map(repr, get_scale_names()))}


def register_scale(scale_class):
    """
    Register a new kind of scale.

    Parameters
    ----------
    scale_class : subclass of `ScaleBase`
        The scale to register.
    """
    _scale_mapping[scale_class.name] = scale_class


def _get_scale_docs():
    """
    Helper function for generating docstrings related to scales.
    """
    docs = []
    for name, scale_class in _scale_mapping.items():
        docstring = inspect.getdoc(scale_class.__init__) or ""
        docs.extend([
            f"    {name!r}",
            "",
            textwrap.indent(docstring, " " * 8),
            ""
        ])
    return "\n".join(docs)


_docstring.interpd.register(
    scale_type='{%s}' % ', '.join([repr(x) for x in get_scale_names()]),
    scale_docs=_get_scale_docs().rstrip(),
    )
