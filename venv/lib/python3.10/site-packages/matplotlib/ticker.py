"""
Tick locating and formatting
============================

This module contains classes for configuring tick locating and formatting.
Generic tick locators and formatters are provided, as well as domain specific
custom ones.

Although the locators know nothing about major or minor ticks, they are used
by the Axis class to support major and minor tick locating and formatting.

.. _tick_locating:
.. _locators:

Tick locating
-------------

The Locator class is the base class for all tick locators. The locators
handle autoscaling of the view limits based on the data limits, and the
choosing of tick locations. A useful semi-automatic tick locator is
`MultipleLocator`. It is initialized with a base, e.g., 10, and it picks
axis limits and ticks that are multiples of that base.

The Locator subclasses defined here are:

======================= =======================================================
`AutoLocator`           `MaxNLocator` with simple defaults. This is the default
                        tick locator for most plotting.
`MaxNLocator`           Finds up to a max number of intervals with ticks at
                        nice locations.
`LinearLocator`         Space ticks evenly from min to max.
`LogLocator`            Space ticks logarithmically from min to max.
`MultipleLocator`       Ticks and range are a multiple of base; either integer
                        or float.
`FixedLocator`          Tick locations are fixed.
`IndexLocator`          Locator for index plots (e.g., where
                        ``x = range(len(y))``).
`NullLocator`           No ticks.
`SymmetricalLogLocator` Locator for use with the symlog norm; works like
                        `LogLocator` for the part outside of the threshold and
                        adds 0 if inside the limits.
`AsinhLocator`          Locator for use with the asinh norm, attempting to
                        space ticks approximately uniformly.
`LogitLocator`          Locator for logit scaling.
`AutoMinorLocator`      Locator for minor ticks when the axis is linear and the
                        major ticks are uniformly spaced. Subdivides the major
                        tick interval into a specified number of minor
                        intervals, defaulting to 4 or 5 depending on the major
                        interval.
======================= =======================================================

There are a number of locators specialized for date locations - see
the :mod:`.dates` module.

You can define your own locator by deriving from Locator. You must
override the ``__call__`` method, which returns a sequence of locations,
and you will probably want to override the autoscale method to set the
view limits from the data limits.

If you want to override the default locator, use one of the above or a custom
locator and pass it to the x- or y-axis instance. The relevant methods are::

  ax.xaxis.set_major_locator(xmajor_locator)
  ax.xaxis.set_minor_locator(xminor_locator)
  ax.yaxis.set_major_locator(ymajor_locator)
  ax.yaxis.set_minor_locator(yminor_locator)

The default minor locator is `NullLocator`, i.e., no minor ticks on by default.

.. note::
    `Locator` instances should not be used with more than one
    `~matplotlib.axis.Axis` or `~matplotlib.axes.Axes`. So instead of::

        locator = MultipleLocator(5)
        ax.xaxis.set_major_locator(locator)
        ax2.xaxis.set_major_locator(locator)

    do the following instead::

        ax.xaxis.set_major_locator(MultipleLocator(5))
        ax2.xaxis.set_major_locator(MultipleLocator(5))

.. _formatters:

Tick formatting
---------------

Tick formatting is controlled by classes derived from Formatter. The formatter
operates on a single tick value and returns a string to the axis.

========================= =====================================================
`NullFormatter`           No labels on the ticks.
`FixedFormatter`          Set the strings manually for the labels.
`FuncFormatter`           User defined function sets the labels.
`StrMethodFormatter`      Use string `format` method.
`FormatStrFormatter`      Use an old-style sprintf format string.
`ScalarFormatter`         Default formatter for scalars: autopick the format
                          string.
`LogFormatter`            Formatter for log axes.
`LogFormatterExponent`    Format values for log axis using
                          ``exponent = log_base(value)``.
`LogFormatterMathtext`    Format values for log axis using
                          ``exponent = log_base(value)`` using Math text.
`LogFormatterSciNotation` Format values for log axis using scientific notation.
`LogitFormatter`          Probability formatter.
`EngFormatter`            Format labels in engineering notation.
`PercentFormatter`        Format labels as a percentage.
========================= =====================================================

You can derive your own formatter from the Formatter base class by
simply overriding the ``__call__`` method. The formatter class has
access to the axis view and data limits.

To control the major and minor tick label formats, use one of the
following methods::

  ax.xaxis.set_major_formatter(xmajor_formatter)
  ax.xaxis.set_minor_formatter(xminor_formatter)
  ax.yaxis.set_major_formatter(ymajor_formatter)
  ax.yaxis.set_minor_formatter(yminor_formatter)

In addition to a `.Formatter` instance, `~.Axis.set_major_formatter` and
`~.Axis.set_minor_formatter` also accept a ``str`` or function.  ``str`` input
will be internally replaced with an autogenerated `.StrMethodFormatter` with
the input ``str``. For function input, a `.FuncFormatter` with the input
function will be generated and used.

See :doc:`/gallery/ticks/major_minor_demo` for an example of setting major
and minor ticks. See the :mod:`matplotlib.dates` module for more information
and examples of using date locators and formatters.
"""

import itertools
import logging
import locale
import math
from numbers import Integral
import string

import numpy as np

import matplotlib as mpl
from matplotlib import _api, cbook
from matplotlib import transforms as mtransforms

_log = logging.getLogger(__name__)

__all__ = ('TickHelper', 'Formatter', 'FixedFormatter',
           'NullFormatter', 'FuncFormatter', 'FormatStrFormatter',
           'StrMethodFormatter', 'ScalarFormatter', 'LogFormatter',
           'LogFormatterExponent', 'LogFormatterMathtext',
           'LogFormatterSciNotation',
           'LogitFormatter', 'EngFormatter', 'PercentFormatter',
           'Locator', 'IndexLocator', 'FixedLocator', 'NullLocator',
           'LinearLocator', 'LogLocator', 'AutoLocator',
           'MultipleLocator', 'MaxNLocator', 'AutoMinorLocator',
           'SymmetricalLogLocator', 'AsinhLocator', 'LogitLocator')


class _DummyAxis:
    __name__ = "dummy"

    def __init__(self, minpos=0):
        self._data_interval = (0, 1)
        self._view_interval = (0, 1)
        self._minpos = minpos

    def get_view_interval(self):
        return self._view_interval

    def set_view_interval(self, vmin, vmax):
        self._view_interval = (vmin, vmax)

    def get_minpos(self):
        return self._minpos

    def get_data_interval(self):
        return self._data_interval

    def set_data_interval(self, vmin, vmax):
        self._data_interval = (vmin, vmax)

    def get_tick_space(self):
        # Just use the long-standing default of nbins==9
        return 9


class TickHelper:
    axis = None

    def set_axis(self, axis):
        self.axis = axis

    def create_dummy_axis(self, **kwargs):
        if self.axis is None:
            self.axis = _DummyAxis(**kwargs)


class Formatter(TickHelper):
    """
    Create a string based on a tick value and location.
    """
    # some classes want to see all the locs to help format
    # individual ones
    locs = []

    def __call__(self, x, pos=None):
        """
        Return the format for tick value *x* at position pos.
        ``pos=None`` indicates an unspecified location.
        """
        raise NotImplementedError('Derived must override')

    def format_ticks(self, values):
        """Return the tick labels for all the ticks at once."""
        self.set_locs(values)
        return [self(value, i) for i, value in enumerate(values)]

    def format_data(self, value):
        """
        Return the full string representation of the value with the
        position unspecified.
        """
        return self.__call__(value)

    def format_data_short(self, value):
        """
        Return a short string version of the tick value.

        Defaults to the position-independent long value.
        """
        return self.format_data(value)

    def get_offset(self):
        return ''

    def set_locs(self, locs):
        """
        Set the locations of the ticks.

        This method is called before computing the tick labels because some
        formatters need to know all tick locations to do so.
        """
        self.locs = locs

    @staticmethod
    def fix_minus(s):
        """
        Some classes may want to replace a hyphen for minus with the proper
        Unicode symbol (U+2212) for typographical correctness.  This is a
        helper method to perform such a replacement when it is enabled via
        :rc:`axes.unicode_minus`.
        """
        return (s.replace('-', '\N{MINUS SIGN}')
                if mpl.rcParams['axes.unicode_minus']
                else s)

    def _set_locator(self, locator):
        """Subclasses may want to override this to set a locator."""
        pass


class NullFormatter(Formatter):
    """Always return the empty string."""

    def __call__(self, x, pos=None):
        # docstring inherited
        return ''


class FixedFormatter(Formatter):
    """
    Return fixed strings for tick labels based only on position, not value.

    .. note::
        `.FixedFormatter` should only be used together with `.FixedLocator`.
        Otherwise, the labels may end up in unexpected positions.
    """

    def __init__(self, seq):
        """Set the sequence *seq* of strings that will be used for labels."""
        self.seq = seq
        self.offset_string = ''

    def __call__(self, x, pos=None):
        """
        Return the label that matches the position, regardless of the value.

        For positions ``pos < len(seq)``, return ``seq[i]`` regardless of
        *x*. Otherwise return empty string. ``seq`` is the sequence of
        strings that this object was initialized with.
        """
        if pos is None or pos >= len(self.seq):
            return ''
        else:
            return self.seq[pos]

    def get_offset(self):
        return self.offset_string

    def set_offset_string(self, ofs):
        self.offset_string = ofs


class FuncFormatter(Formatter):
    """
    Use a user-defined function for formatting.

    The function should take in two inputs (a tick value ``x`` and a
    position ``pos``), and return a string containing the corresponding
    tick label.
    """

    def __init__(self, func):
        self.func = func
        self.offset_string = ""

    def __call__(self, x, pos=None):
        """
        Return the value of the user defined function.

        *x* and *pos* are passed through as-is.
        """
        return self.func(x, pos)

    def get_offset(self):
        return self.offset_string

    def set_offset_string(self, ofs):
        self.offset_string = ofs


class FormatStrFormatter(Formatter):
    """
    Use an old-style ('%' operator) format string to format the tick.

    The format string should have a single variable format (%) in it.
    It will be applied to the value (not the position) of the tick.

    Negative numeric values (e.g., -1) will use a dash, not a Unicode minus;
    use mathtext to get a Unicode minus by wrapping the format specifier with $
    (e.g. "$%g$").
    """

    def __init__(self, fmt):
        self.fmt = fmt

    def __call__(self, x, pos=None):
        """
        Return the formatted label string.

        Only the value *x* is formatted. The position is ignored.
        """
        return self.fmt % x


class _UnicodeMinusFormat(string.Formatter):
    """
    A specialized string formatter so that `.StrMethodFormatter` respects
    :rc:`axes.unicode_minus`.  This implementation relies on the fact that the
    format string is only ever called with kwargs *x* and *pos*, so it blindly
    replaces dashes by unicode minuses without further checking.
    """

    def format_field(self, value, format_spec):
        return Formatter.fix_minus(super().format_field(value, format_spec))


class StrMethodFormatter(Formatter):
    """
    Use a new-style format string (as used by `str.format`) to format the tick.

    The field used for the tick value must be labeled *x* and the field used
    for the tick position must be labeled *pos*.

    The formatter will respect :rc:`axes.unicode_minus` when formatting
    negative numeric values.

    It is typically unnecessary to explicitly construct `.StrMethodFormatter`
    objects, as `~.Axis.set_major_formatter` directly accepts the format string
    itself.
    """

    def __init__(self, fmt):
        self.fmt = fmt

    def __call__(self, x, pos=None):
        """
        Return the formatted label string.

        *x* and *pos* are passed to `str.format` as keyword arguments
        with those exact names.
        """
        return _UnicodeMinusFormat().format(self.fmt, x=x, pos=pos)


class ScalarFormatter(Formatter):
    """
    Format tick values as a number.

    Parameters
    ----------
    useOffset : bool or float, default: :rc:`axes.formatter.useoffset`
        Whether to use offset notation. See `.set_useOffset`.
    useMathText : bool, default: :rc:`axes.formatter.use_mathtext`
        Whether to use fancy math formatting. See `.set_useMathText`.
    useLocale : bool, default: :rc:`axes.formatter.use_locale`.
        Whether to use locale settings for decimal sign and positive sign.
        See `.set_useLocale`.
    usetex : bool, default: :rc:`text.usetex`
        To enable/disable the use of TeX's math mode for rendering the
        numbers in the formatter.

        .. versionadded:: 3.10

    Notes
    -----
    In addition to the parameters above, the formatting of scientific vs.
    floating point representation can be configured via `.set_scientific`
    and `.set_powerlimits`).

    **Offset notation and scientific notation**

    Offset notation and scientific notation look quite similar at first sight.
    Both split some information from the formatted tick values and display it
    at the end of the axis.

    - The scientific notation splits up the order of magnitude, i.e. a
      multiplicative scaling factor, e.g. ``1e6``.

    - The offset notation separates an additive constant, e.g. ``+1e6``. The
      offset notation label is always prefixed with a ``+`` or ``-`` sign
      and is thus distinguishable from the order of magnitude label.

    The following plot with x limits ``1_000_000`` to ``1_000_010`` illustrates
    the different formatting. Note the labels at the right edge of the x axis.

    .. plot::

        lim = (1_000_000, 1_000_010)

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, gridspec_kw={'hspace': 2})
        ax1.set(title='offset notation', xlim=lim)
        ax2.set(title='scientific notation', xlim=lim)
        ax2.xaxis.get_major_formatter().set_useOffset(False)
        ax3.set(title='floating-point notation', xlim=lim)
        ax3.xaxis.get_major_formatter().set_useOffset(False)
        ax3.xaxis.get_major_formatter().set_scientific(False)

    """

    def __init__(self, useOffset=None, useMathText=None, useLocale=None, *,
                 usetex=None):
        if useOffset is None:
            useOffset = mpl.rcParams['axes.formatter.useoffset']
        self._offset_threshold = \
            mpl.rcParams['axes.formatter.offset_threshold']
        self.set_useOffset(useOffset)
        self.set_usetex(usetex)
        self.set_useMathText(useMathText)
        self.orderOfMagnitude = 0
        self.format = ''
        self._scientific = True
        self._powerlimits = mpl.rcParams['axes.formatter.limits']
        self.set_useLocale(useLocale)

    def get_usetex(self):
        """Return whether TeX's math mode is enabled for rendering."""
        return self._usetex

    def set_usetex(self, val):
        """Set whether to use TeX's math mode for rendering numbers in the formatter."""
        self._usetex = mpl._val_or_rc(val, 'text.usetex')

    usetex = property(fget=get_usetex, fset=set_usetex)

    def get_useOffset(self):
        """
        Return whether automatic mode for offset notation is active.

        This returns True if ``set_useOffset(True)``; it returns False if an
        explicit offset was set, e.g. ``set_useOffset(1000)``.

        See Also
        --------
        ScalarFormatter.set_useOffset
        """
        return self._useOffset

    def set_useOffset(self, val):
        """
        Set whether to use offset notation.

        When formatting a set numbers whose value is large compared to their
        range, the formatter can separate an additive constant. This can
        shorten the formatted numbers so that they are less likely to overlap
        when drawn on an axis.

        Parameters
        ----------
        val : bool or float
            - If False, do not use offset notation.
            - If True (=automatic mode), use offset notation if it can make
              the residual numbers significantly shorter. The exact behavior
              is controlled by :rc:`axes.formatter.offset_threshold`.
            - If a number, force an offset of the given value.

        Examples
        --------
        With active offset notation, the values

        ``100_000, 100_002, 100_004, 100_006, 100_008``

        will be formatted as ``0, 2, 4, 6, 8`` plus an offset ``+1e5``, which
        is written to the edge of the axis.
        """
        if val in [True, False]:
            self.offset = 0
            self._useOffset = val
        else:
            self._useOffset = False
            self.offset = val

    useOffset = property(fget=get_useOffset, fset=set_useOffset)

    def get_useLocale(self):
        """
        Return whether locale settings are used for formatting.

        See Also
        --------
        ScalarFormatter.set_useLocale
        """
        return self._useLocale

    def set_useLocale(self, val):
        """
        Set whether to use locale settings for decimal sign and positive sign.

        Parameters
        ----------
        val : bool or None
            *None* resets to :rc:`axes.formatter.use_locale`.
        """
        if val is None:
            self._useLocale = mpl.rcParams['axes.formatter.use_locale']
        else:
            self._useLocale = val

    useLocale = property(fget=get_useLocale, fset=set_useLocale)

    def _format_maybe_minus_and_locale(self, fmt, arg):
        """
        Format *arg* with *fmt*, applying Unicode minus and locale if desired.
        """
        return self.fix_minus(
                # Escape commas introduced by locale.format_string if using math text,
                # but not those present from the beginning in fmt.
                (",".join(locale.format_string(part, (arg,), True).replace(",", "{,}")
                          for part in fmt.split(",")) if self._useMathText
                 else locale.format_string(fmt, (arg,), True))
                if self._useLocale
                else fmt % arg)

    def get_useMathText(self):
        """
        Return whether to use fancy math formatting.

        See Also
        --------
        ScalarFormatter.set_useMathText
        """
        return self._useMathText

    def set_useMathText(self, val):
        r"""
        Set whether to use fancy math formatting.

        If active, scientific notation is formatted as :math:`1.2 \times 10^3`.

        Parameters
        ----------
        val : bool or None
            *None* resets to :rc:`axes.formatter.use_mathtext`.
        """
        if val is None:
            self._useMathText = mpl.rcParams['axes.formatter.use_mathtext']
            if self._useMathText is False:
                try:
                    from matplotlib import font_manager
                    ufont = font_manager.findfont(
                        font_manager.FontProperties(
                            family=mpl.rcParams["font.family"]
                        ),
                        fallback_to_default=False,
                    )
                except ValueError:
                    ufont = None

                if ufont == str(cbook._get_data_path("fonts/ttf/cmr10.ttf")):
                    _api.warn_external(
                        "cmr10 font should ideally be used with "
                        "mathtext, set axes.formatter.use_mathtext to True"
                    )
        else:
            self._useMathText = val

    useMathText = property(fget=get_useMathText, fset=set_useMathText)

    def __call__(self, x, pos=None):
        """
        Return the format for tick value *x* at position *pos*.
        """
        if len(self.locs) == 0:
            return ''
        else:
            xp = (x - self.offset) / (10. ** self.orderOfMagnitude)
            if abs(xp) < 1e-8:
                xp = 0
            return self._format_maybe_minus_and_locale(self.format, xp)

    def set_scientific(self, b):
        """
        Turn scientific notation on or off.

        See Also
        --------
        ScalarFormatter.set_powerlimits
        """
        self._scientific = bool(b)

    def set_powerlimits(self, lims):
        r"""
        Set size thresholds for scientific notation.

        Parameters
        ----------
        lims : (int, int)
            A tuple *(min_exp, max_exp)* containing the powers of 10 that
            determine the switchover threshold. For a number representable as
            :math:`a \times 10^\mathrm{exp}` with :math:`1 <= |a| < 10`,
            scientific notation will be used if ``exp <= min_exp`` or
            ``exp >= max_exp``.

            The default limits are controlled by :rc:`axes.formatter.limits`.

            In particular numbers with *exp* equal to the thresholds are
            written in scientific notation.

            Typically, *min_exp* will be negative and *max_exp* will be
            positive.

            For example, ``formatter.set_powerlimits((-3, 4))`` will provide
            the following formatting:
            :math:`1 \times 10^{-3}, 9.9 \times 10^{-3}, 0.01,`
            :math:`9999, 1 \times 10^4`.

        See Also
        --------
        ScalarFormatter.set_scientific
        """
        if len(lims) != 2:
            raise ValueError("'lims' must be a sequence of length 2")
        self._powerlimits = lims

    def format_data_short(self, value):
        # docstring inherited
        if value is np.ma.masked:
            return ""
        if isinstance(value, Integral):
            fmt = "%d"
        else:
            if getattr(self.axis, "__name__", "") in ["xaxis", "yaxis"]:
                if self.axis.__name__ == "xaxis":
                    axis_trf = self.axis.axes.get_xaxis_transform()
                    axis_inv_trf = axis_trf.inverted()
                    screen_xy = axis_trf.transform((value, 0))
                    neighbor_values = axis_inv_trf.transform(
                        screen_xy + [[-1, 0], [+1, 0]])[:, 0]
                else:  # yaxis:
                    axis_trf = self.axis.axes.get_yaxis_transform()
                    axis_inv_trf = axis_trf.inverted()
                    screen_xy = axis_trf.transform((0, value))
                    neighbor_values = axis_inv_trf.transform(
                        screen_xy + [[0, -1], [0, +1]])[:, 1]
                delta = abs(neighbor_values - value).max()
            else:
                # Rough approximation: no more than 1e4 divisions.
                a, b = self.axis.get_view_interval()
                delta = (b - a) / 1e4
            fmt = f"%-#.{cbook._g_sig_digits(value, delta)}g"
        return self._format_maybe_minus_and_locale(fmt, value)

    def format_data(self, value):
        # docstring inherited
        e = math.floor(math.log10(abs(value)))
        s = round(value / 10**e, 10)
        significand = self._format_maybe_minus_and_locale(
            "%d" if s % 1 == 0 else "%1.10g", s)
        if e == 0:
            return significand
        exponent = self._format_maybe_minus_and_locale("%d", e)
        if self._useMathText or self._usetex:
            exponent = "10^{%s}" % exponent
            return (exponent if s == 1  # reformat 1x10^y as 10^y
                    else rf"{significand} \times {exponent}")
        else:
            return f"{significand}e{exponent}"

    def get_offset(self):
        """
        Return scientific notation, plus offset.
        """
        if len(self.locs) == 0:
            return ''
        if self.orderOfMagnitude or self.offset:
            offsetStr = ''
            sciNotStr = ''
            if self.offset:
                offsetStr = self.format_data(self.offset)
                if self.offset > 0:
                    offsetStr = '+' + offsetStr
            if self.orderOfMagnitude:
                if self._usetex or self._useMathText:
                    sciNotStr = self.format_data(10 ** self.orderOfMagnitude)
                else:
                    sciNotStr = '1e%d' % self.orderOfMagnitude
            if self._useMathText or self._usetex:
                if sciNotStr != '':
                    sciNotStr = r'\times\mathdefault{%s}' % sciNotStr
                s = fr'${sciNotStr}\mathdefault{{{offsetStr}}}$'
            else:
                s = ''.join((sciNotStr, offsetStr))
            return self.fix_minus(s)
        return ''

    def set_locs(self, locs):
        # docstring inherited
        self.locs = locs
        if len(self.locs) > 0:
            if self._useOffset:
                self._compute_offset()
            self._set_order_of_magnitude()
            self._set_format()

    def _compute_offset(self):
        locs = self.locs
        # Restrict to visible ticks.
        vmin, vmax = sorted(self.axis.get_view_interval())
        locs = np.asarray(locs)
        locs = locs[(vmin <= locs) & (locs <= vmax)]
        if not len(locs):
            self.offset = 0
            return
        lmin, lmax = locs.min(), locs.max()
        # Only use offset if there are at least two ticks and every tick has
        # the same sign.
        if lmin == lmax or lmin <= 0 <= lmax:
            self.offset = 0
            return
        # min, max comparing absolute values (we want division to round towards
        # zero so we work on absolute values).
        abs_min, abs_max = sorted([abs(float(lmin)), abs(float(lmax))])
        sign = math.copysign(1, lmin)
        # What is the smallest power of ten such that abs_min and abs_max are
        # equal up to that precision?
        # Note: Internally using oom instead of 10 ** oom avoids some numerical
        # accuracy issues.
        oom_max = np.ceil(math.log10(abs_max))
        oom = 1 + next(oom for oom in itertools.count(oom_max, -1)
                       if abs_min // 10 ** oom != abs_max // 10 ** oom)
        if (abs_max - abs_min) / 10 ** oom <= 1e-2:
            # Handle the case of straddling a multiple of a large power of ten
            # (relative to the span).
            # What is the smallest power of ten such that abs_min and abs_max
            # are no more than 1 apart at that precision?
            oom = 1 + next(oom for oom in itertools.count(oom_max, -1)
                           if abs_max // 10 ** oom - abs_min // 10 ** oom > 1)
        # Only use offset if it saves at least _offset_threshold digits.
        n = self._offset_threshold - 1
        self.offset = (sign * (abs_max // 10 ** oom) * 10 ** oom
                       if abs_max // 10 ** oom >= 10**n
                       else 0)

    def _set_order_of_magnitude(self):
        # if scientific notation is to be used, find the appropriate exponent
        # if using a numerical offset, find the exponent after applying the
        # offset. When lower power limit = upper <> 0, use provided exponent.
        if not self._scientific:
            self.orderOfMagnitude = 0
            return
        if self._powerlimits[0] == self._powerlimits[1] != 0:
            # fixed scaling when lower power limit = upper <> 0.
            self.orderOfMagnitude = self._powerlimits[0]
            return
        # restrict to visible ticks
        vmin, vmax = sorted(self.axis.get_view_interval())
        locs = np.asarray(self.locs)
        locs = locs[(vmin <= locs) & (locs <= vmax)]
        locs = np.abs(locs)
        if not len(locs):
            self.orderOfMagnitude = 0
            return
        if self.offset:
            oom = math.floor(math.log10(vmax - vmin))
        else:
            val = locs.max()
            if val == 0:
                oom = 0
            else:
                oom = math.floor(math.log10(val))
        if oom <= self._powerlimits[0]:
            self.orderOfMagnitude = oom
        elif oom >= self._powerlimits[1]:
            self.orderOfMagnitude = oom
        else:
            self.orderOfMagnitude = 0

    def _set_format(self):
        # set the format string to format all the ticklabels
        if len(self.locs) < 2:
            # Temporarily augment the locations with the axis end points.
            _locs = [*self.locs, *self.axis.get_view_interval()]
        else:
            _locs = self.locs
        locs = (np.asarray(_locs) - self.offset) / 10. ** self.orderOfMagnitude
        loc_range = np.ptp(locs)
        # Curvilinear coordinates can yield two identical points.
        if loc_range == 0:
            loc_range = np.max(np.abs(locs))
        # Both points might be zero.
        if loc_range == 0:
            loc_range = 1
        if len(self.locs) < 2:
            # We needed the end points only for the loc_range calculation.
            locs = locs[:-2]
        loc_range_oom = int(math.floor(math.log10(loc_range)))
        # first estimate:
        sigfigs = max(0, 3 - loc_range_oom)
        # refined estimate:
        thresh = 1e-3 * 10 ** loc_range_oom
        while sigfigs >= 0:
            if np.abs(locs - np.round(locs, decimals=sigfigs)).max() < thresh:
                sigfigs -= 1
            else:
                break
        sigfigs += 1
        self.format = f'%1.{sigfigs}f'
        if self._usetex or self._useMathText:
            self.format = r'$\mathdefault{%s}$' % self.format


class LogFormatter(Formatter):
    """
    Base class for formatting ticks on a log or symlog scale.

    It may be instantiated directly, or subclassed.

    Parameters
    ----------
    base : float, default: 10.
        Base of the logarithm used in all calculations.

    labelOnlyBase : bool, default: False
        If True, label ticks only at integer powers of base.
        This is normally True for major ticks and False for
        minor ticks.

    minor_thresholds : (subset, all), default: (1, 0.4)
        If labelOnlyBase is False, these two numbers control
        the labeling of ticks that are not at integer powers of
        base; normally these are the minor ticks. The controlling
        parameter is the log of the axis data range.  In the typical
        case where base is 10 it is the number of decades spanned
        by the axis, so we can call it 'numdec'. If ``numdec <= all``,
        all minor ticks will be labeled.  If ``all < numdec <= subset``,
        then only a subset of minor ticks will be labeled, so as to
        avoid crowding. If ``numdec > subset`` then no minor ticks will
        be labeled.

    linthresh : None or float, default: None
        If a symmetric log scale is in use, its ``linthresh``
        parameter must be supplied here.

    Notes
    -----
    The `set_locs` method must be called to enable the subsetting
    logic controlled by the ``minor_thresholds`` parameter.

    In some cases such as the colorbar, there is no distinction between
    major and minor ticks; the tick locations might be set manually,
    or by a locator that puts ticks at integer powers of base and
    at intermediate locations.  For this situation, disable the
    minor_thresholds logic by using ``minor_thresholds=(np.inf, np.inf)``,
    so that all ticks will be labeled.

    To disable labeling of minor ticks when 'labelOnlyBase' is False,
    use ``minor_thresholds=(0, 0)``.  This is the default for the
    "classic" style.

    Examples
    --------
    To label a subset of minor ticks when the view limits span up
    to 2 decades, and all of the ticks when zoomed in to 0.5 decades
    or less, use ``minor_thresholds=(2, 0.5)``.

    To label all minor ticks when the view limits span up to 1.5
    decades, use ``minor_thresholds=(1.5, 1.5)``.
    """

    def __init__(self, base=10.0, labelOnlyBase=False,
                 minor_thresholds=None,
                 linthresh=None):

        self.set_base(base)
        self.set_label_minor(labelOnlyBase)
        if minor_thresholds is None:
            if mpl.rcParams['_internal.classic_mode']:
                minor_thresholds = (0, 0)
            else:
                minor_thresholds = (1, 0.4)
        self.minor_thresholds = minor_thresholds
        self._sublabels = None
        self._linthresh = linthresh

    def set_base(self, base):
        """
        Change the *base* for labeling.

        .. warning::
           Should always match the base used for :class:`LogLocator`
        """
        self._base = float(base)

    def set_label_minor(self, labelOnlyBase):
        """
        Switch minor tick labeling on or off.

        Parameters
        ----------
        labelOnlyBase : bool
            If True, label ticks only at integer powers of base.
        """
        self.labelOnlyBase = labelOnlyBase

    def set_locs(self, locs=None):
        """
        Use axis view limits to control which ticks are labeled.

        The *locs* parameter is ignored in the present algorithm.
        """
        if np.isinf(self.minor_thresholds[0]):
            self._sublabels = None
            return

        # Handle symlog case:
        linthresh = self._linthresh
        if linthresh is None:
            try:
                linthresh = self.axis.get_transform().linthresh
            except AttributeError:
                pass

        vmin, vmax = self.axis.get_view_interval()
        if vmin > vmax:
            vmin, vmax = vmax, vmin

        if linthresh is None and vmin <= 0:
            # It's probably a colorbar with
            # a format kwarg setting a LogFormatter in the manner
            # that worked with 1.5.x, but that doesn't work now.
            self._sublabels = {1}  # label powers of base
            return

        b = self._base
        if linthresh is not None:  # symlog
            # Only compute the number of decades in the logarithmic part of the
            # axis
            numdec = 0
            if vmin < -linthresh:
                rhs = min(vmax, -linthresh)
                numdec += math.log(vmin / rhs) / math.log(b)
            if vmax > linthresh:
                lhs = max(vmin, linthresh)
                numdec += math.log(vmax / lhs) / math.log(b)
        else:
            vmin = math.log(vmin) / math.log(b)
            vmax = math.log(vmax) / math.log(b)
            numdec = abs(vmax - vmin)

        if numdec > self.minor_thresholds[0]:
            # Label only bases
            self._sublabels = {1}
        elif numdec > self.minor_thresholds[1]:
            # Add labels between bases at log-spaced coefficients;
            # include base powers in case the locations include
            # "major" and "minor" points, as in colorbar.
            c = np.geomspace(1, b, int(b)//2 + 1)
            self._sublabels = set(np.round(c))
            # For base 10, this yields (1, 2, 3, 4, 6, 10).
        else:
            # Label all integer multiples of base**n.
            self._sublabels = set(np.arange(1, b + 1))

    def _num_to_string(self, x, vmin, vmax):
        return self._pprint_val(x, vmax - vmin) if 1 <= x <= 10000 else f"{x:1.0e}"

    def __call__(self, x, pos=None):
        # docstring inherited
        if x == 0.0:  # Symlog
            return '0'

        x = abs(x)
        b = self._base
        # only label the decades
        fx = math.log(x) / math.log(b)
        is_x_decade = _is_close_to_int(fx)
        exponent = round(fx) if is_x_decade else np.floor(fx)
        coeff = round(b ** (fx - exponent))

        if self.labelOnlyBase and not is_x_decade:
            return ''
        if self._sublabels is not None and coeff not in self._sublabels:
            return ''

        vmin, vmax = self.axis.get_view_interval()
        vmin, vmax = mtransforms.nonsingular(vmin, vmax, expander=0.05)
        s = self._num_to_string(x, vmin, vmax)
        return self.fix_minus(s)

    def format_data(self, value):
        with cbook._setattr_cm(self, labelOnlyBase=False):
            return cbook.strip_math(self.__call__(value))

    def format_data_short(self, value):
        # docstring inherited
        return ('%-12g' % value).rstrip()

    def _pprint_val(self, x, d):
        # If the number is not too big and it's an int, format it as an int.
        if abs(x) < 1e4 and x == int(x):
            return '%d' % x
        fmt = ('%1.3e' if d < 1e-2 else
               '%1.3f' if d <= 1 else
               '%1.2f' if d <= 10 else
               '%1.1f' if d <= 1e5 else
               '%1.1e')
        s = fmt % x
        tup = s.split('e')
        if len(tup) == 2:
            mantissa = tup[0].rstrip('0').rstrip('.')
            exponent = int(tup[1])
            if exponent:
                s = '%se%d' % (mantissa, exponent)
            else:
                s = mantissa
        else:
            s = s.rstrip('0').rstrip('.')
        return s


class LogFormatterExponent(LogFormatter):
    """
    Format values for log axis using ``exponent = log_base(value)``.
    """

    def _num_to_string(self, x, vmin, vmax):
        fx = math.log(x) / math.log(self._base)
        if 1 <= abs(fx) <= 10000:
            fd = math.log(vmax - vmin) / math.log(self._base)
            s = self._pprint_val(fx, fd)
        else:
            s = f"{fx:1.0g}"
        return s


class LogFormatterMathtext(LogFormatter):
    """
    Format values for log axis using ``exponent = log_base(value)``.
    """

    def _non_decade_format(self, sign_string, base, fx, usetex):
        """Return string for non-decade locations."""
        return r'$\mathdefault{%s%s^{%.2f}}$' % (sign_string, base, fx)

    def __call__(self, x, pos=None):
        # docstring inherited
        if x == 0:  # Symlog
            return r'$\mathdefault{0}$'

        sign_string = '-' if x < 0 else ''
        x = abs(x)
        b = self._base

        # only label the decades
        fx = math.log(x) / math.log(b)
        is_x_decade = _is_close_to_int(fx)
        exponent = round(fx) if is_x_decade else np.floor(fx)
        coeff = round(b ** (fx - exponent))

        if self.labelOnlyBase and not is_x_decade:
            return ''
        if self._sublabels is not None and coeff not in self._sublabels:
            return ''

        if is_x_decade:
            fx = round(fx)

        # use string formatting of the base if it is not an integer
        if b % 1 == 0.0:
            base = '%d' % b
        else:
            base = '%s' % b

        if abs(fx) < mpl.rcParams['axes.formatter.min_exponent']:
            return r'$\mathdefault{%s%g}$' % (sign_string, x)
        elif not is_x_decade:
            usetex = mpl.rcParams['text.usetex']
            return self._non_decade_format(sign_string, base, fx, usetex)
        else:
            return r'$\mathdefault{%s%s^{%d}}$' % (sign_string, base, fx)


class LogFormatterSciNotation(LogFormatterMathtext):
    """
    Format values following scientific notation in a logarithmic axis.
    """

    def _non_decade_format(self, sign_string, base, fx, usetex):
        """Return string for non-decade locations."""
        b = float(base)
        exponent = math.floor(fx)
        coeff = b ** (fx - exponent)
        if _is_close_to_int(coeff):
            coeff = round(coeff)
        return r'$\mathdefault{%s%g\times%s^{%d}}$' \
            % (sign_string, coeff, base, exponent)


class LogitFormatter(Formatter):
    """
    Probability formatter (using Math text).
    """

    def __init__(
        self,
        *,
        use_overline=False,
        one_half=r"\frac{1}{2}",
        minor=False,
        minor_threshold=25,
        minor_number=6,
    ):
        r"""
        Parameters
        ----------
        use_overline : bool, default: False
            If x > 1/2, with x = 1 - v, indicate if x should be displayed as
            $\overline{v}$. The default is to display $1 - v$.

        one_half : str, default: r"\\frac{1}{2}"
            The string used to represent 1/2.

        minor : bool, default: False
            Indicate if the formatter is formatting minor ticks or not.
            Basically minor ticks are not labelled, except when only few ticks
            are provided, ticks with most space with neighbor ticks are
            labelled. See other parameters to change the default behavior.

        minor_threshold : int, default: 25
            Maximum number of locs for labelling some minor ticks. This
            parameter have no effect if minor is False.

        minor_number : int, default: 6
            Number of ticks which are labelled when the number of ticks is
            below the threshold.
        """
        self._use_overline = use_overline
        self._one_half = one_half
        self._minor = minor
        self._labelled = set()
        self._minor_threshold = minor_threshold
        self._minor_number = minor_number

    def use_overline(self, use_overline):
        r"""
        Switch display mode with overline for labelling p>1/2.

        Parameters
        ----------
        use_overline : bool
            If x > 1/2, with x = 1 - v, indicate if x should be displayed as
            $\overline{v}$. The default is to display $1 - v$.
        """
        self._use_overline = use_overline

    def set_one_half(self, one_half):
        r"""
        Set the way one half is displayed.

        one_half : str
            The string used to represent 1/2.
        """
        self._one_half = one_half

    def set_minor_threshold(self, minor_threshold):
        """
        Set the threshold for labelling minors ticks.

        Parameters
        ----------
        minor_threshold : int
            Maximum number of locations for labelling some minor ticks. This
            parameter have no effect if minor is False.
        """
        self._minor_threshold = minor_threshold

    def set_minor_number(self, minor_number):
        """
        Set the number of minor ticks to label when some minor ticks are
        labelled.

        Parameters
        ----------
        minor_number : int
            Number of ticks which are labelled when the number of ticks is
            below the threshold.
        """
        self._minor_number = minor_number

    def set_locs(self, locs):
        self.locs = np.array(locs)
        self._labelled.clear()

        if not self._minor:
            return None
        if all(
            _is_decade(x, rtol=1e-7)
            or _is_decade(1 - x, rtol=1e-7)
            or (_is_close_to_int(2 * x) and
                int(np.round(2 * x)) == 1)
            for x in locs
        ):
            # minor ticks are subsample from ideal, so no label
            return None
        if len(locs) < self._minor_threshold:
            if len(locs) < self._minor_number:
                self._labelled.update(locs)
            else:
                # we do not have a lot of minor ticks, so only few decades are
                # displayed, then we choose some (spaced) minor ticks to label.
                # Only minor ticks are known, we assume it is sufficient to
                # choice which ticks are displayed.
                # For each ticks we compute the distance between the ticks and
                # the previous, and between the ticks and the next one. Ticks
                # with smallest minimum are chosen. As tiebreak, the ticks
                # with smallest sum is chosen.
                diff = np.diff(-np.log(1 / self.locs - 1))
                space_pessimistic = np.minimum(
                    np.concatenate(((np.inf,), diff)),
                    np.concatenate((diff, (np.inf,))),
                )
                space_sum = (
                    np.concatenate(((0,), diff))
                    + np.concatenate((diff, (0,)))
                )
                good_minor = sorted(
                    range(len(self.locs)),
                    key=lambda i: (space_pessimistic[i], space_sum[i]),
                )[-self._minor_number:]
                self._labelled.update(locs[i] for i in good_minor)

    def _format_value(self, x, locs, sci_notation=True):
        if sci_notation:
            exponent = math.floor(np.log10(x))
            min_precision = 0
        else:
            exponent = 0
            min_precision = 1
        value = x * 10 ** (-exponent)
        if len(locs) < 2:
            precision = min_precision
        else:
            diff = np.sort(np.abs(locs - x))[1]
            precision = -np.log10(diff) + exponent
            precision = (
                int(np.round(precision))
                if _is_close_to_int(precision)
                else math.ceil(precision)
            )
            if precision < min_precision:
                precision = min_precision
        mantissa = r"%.*f" % (precision, value)
        if not sci_notation:
            return mantissa
        s = r"%s\cdot10^{%d}" % (mantissa, exponent)
        return s

    def _one_minus(self, s):
        if self._use_overline:
            return r"\overline{%s}" % s
        else:
            return f"1-{s}"

    def __call__(self, x, pos=None):
        if self._minor and x not in self._labelled:
            return ""
        if x <= 0 or x >= 1:
            return ""
        if _is_close_to_int(2 * x) and round(2 * x) == 1:
            s = self._one_half
        elif x < 0.5 and _is_decade(x, rtol=1e-7):
            exponent = round(math.log10(x))
            s = "10^{%d}" % exponent
        elif x > 0.5 and _is_decade(1 - x, rtol=1e-7):
            exponent = round(math.log10(1 - x))
            s = self._one_minus("10^{%d}" % exponent)
        elif x < 0.1:
            s = self._format_value(x, self.locs)
        elif x > 0.9:
            s = self._one_minus(self._format_value(1-x, 1-self.locs))
        else:
            s = self._format_value(x, self.locs, sci_notation=False)
        return r"$\mathdefault{%s}$" % s

    def format_data_short(self, value):
        # docstring inherited
        # Thresholds chosen to use scientific notation iff exponent <= -2.
        if value < 0.1:
            return f"{value:e}"
        if value < 0.9:
            return f"{value:f}"
        return f"1-{1 - value:e}"


class EngFormatter(ScalarFormatter):
    """
    Format axis values using engineering prefixes to represent powers
    of 1000, plus a specified unit, e.g., 10 MHz instead of 1e7.
    """

    # The SI engineering prefixes
    ENG_PREFIXES = {
        -30: "q",
        -27: "r",
        -24: "y",
        -21: "z",
        -18: "a",
        -15: "f",
        -12: "p",
         -9: "n",
         -6: "\N{MICRO SIGN}",
         -3: "m",
          0: "",
          3: "k",
          6: "M",
          9: "G",
         12: "T",
         15: "P",
         18: "E",
         21: "Z",
         24: "Y",
         27: "R",
         30: "Q"
    }

    def __init__(self, unit="", places=None, sep=" ", *, usetex=None,
                 useMathText=None, useOffset=False):
        r"""
        Parameters
        ----------
        unit : str, default: ""
            Unit symbol to use, suitable for use with single-letter
            representations of powers of 1000. For example, 'Hz' or 'm'.

        places : int, default: None
            Precision with which to display the number, specified in
            digits after the decimal point (there will be between one
            and three digits before the decimal point). If it is None,
            the formatting falls back to the floating point format '%g',
            which displays up to 6 *significant* digits, i.e. the equivalent
            value for *places* varies between 0 and 5 (inclusive).

        sep : str, default: " "
            Separator used between the value and the prefix/unit. For
            example, one get '3.14 mV' if ``sep`` is " " (default) and
            '3.14mV' if ``sep`` is "". Besides the default behavior, some
            other useful options may be:

            * ``sep=""`` to append directly the prefix/unit to the value;
            * ``sep="\N{THIN SPACE}"`` (``U+2009``);
            * ``sep="\N{NARROW NO-BREAK SPACE}"`` (``U+202F``);
            * ``sep="\N{NO-BREAK SPACE}"`` (``U+00A0``).

        usetex : bool, default: :rc:`text.usetex`
            To enable/disable the use of TeX's math mode for rendering the
            numbers in the formatter.

        useMathText : bool, default: :rc:`axes.formatter.use_mathtext`
            To enable/disable the use mathtext for rendering the numbers in
            the formatter.
        useOffset : bool or float, default: False
            Whether to use offset notation with :math:`10^{3*N}` based prefixes.
            This features allows showing an offset with standard SI order of
            magnitude prefix near the axis. Offset is computed similarly to
            how `ScalarFormatter` computes it internally, but here you are
            guaranteed to get an offset which will make the tick labels exceed
            3 digits. See also `.set_useOffset`.

            .. versionadded:: 3.10
        """
        self.unit = unit
        self.places = places
        self.sep = sep
        super().__init__(
            useOffset=useOffset,
            useMathText=useMathText,
            useLocale=False,
            usetex=usetex,
        )

    def __call__(self, x, pos=None):
        """
        Return the format for tick value *x* at position *pos*.

        If there is no currently offset in the data, it returns the best
        engineering formatting that fits the given argument, independently.
        """
        if len(self.locs) == 0 or self.offset == 0:
            return self.fix_minus(self.format_data(x))
        else:
            xp = (x - self.offset) / (10. ** self.orderOfMagnitude)
            if abs(xp) < 1e-8:
                xp = 0
            return self._format_maybe_minus_and_locale(self.format, xp)

    def set_locs(self, locs):
        # docstring inherited
        self.locs = locs
        if len(self.locs) > 0:
            vmin, vmax = sorted(self.axis.get_view_interval())
            if self._useOffset:
                self._compute_offset()
                if self.offset != 0:
                    # We don't want to use the offset computed by
                    # self._compute_offset because it rounds the offset unaware
                    # of our engineering prefixes preference, and this can
                    # cause ticks with 4+ digits to appear. These ticks are
                    # slightly less readable, so if offset is justified
                    # (decided by self._compute_offset) we set it to better
                    # value:
                    self.offset = round((vmin + vmax)/2, 3)
            # Use log1000 to use engineers' oom standards
            self.orderOfMagnitude = math.floor(math.log(vmax - vmin, 1000))*3
            self._set_format()

    # Simplify a bit ScalarFormatter.get_offset: We always want to use
    # self.format_data. Also we want to return a non-empty string only if there
    # is an offset, no matter what is self.orderOfMagnitude. If there _is_ an
    # offset, self.orderOfMagnitude is consulted. This behavior is verified
    # in `test_ticker.py`.
    def get_offset(self):
        # docstring inherited
        if len(self.locs) == 0:
            return ''
        if self.offset:
            offsetStr = ''
            if self.offset:
                offsetStr = self.format_data(self.offset)
                if self.offset > 0:
                    offsetStr = '+' + offsetStr
            sciNotStr = self.format_data(10 ** self.orderOfMagnitude)
            if self._useMathText or self._usetex:
                if sciNotStr != '':
                    sciNotStr = r'\times%s' % sciNotStr
                s = f'${sciNotStr}{offsetStr}$'
            else:
                s = sciNotStr + offsetStr
            return self.fix_minus(s)
        return ''

    def format_eng(self, num):
        """Alias to EngFormatter.format_data"""
        return self.format_data(num)

    def format_data(self, value):
        """
        Format a number in engineering notation, appending a letter
        representing the power of 1000 of the original number.
        Some examples:

        >>> format_data(0)        # for self.places = 0
        '0'

        >>> format_data(1000000)  # for self.places = 1
        '1.0 M'

        >>> format_data(-1e-6)  # for self.places = 2
        '-1.00 \N{MICRO SIGN}'
        """
        sign = 1
        fmt = "g" if self.places is None else f".{self.places:d}f"

        if value < 0:
            sign = -1
            value = -value

        if value != 0:
            pow10 = int(math.floor(math.log10(value) / 3) * 3)
        else:
            pow10 = 0
            # Force value to zero, to avoid inconsistencies like
            # format_eng(-0) = "0" and format_eng(0.0) = "0"
            # but format_eng(-0.0) = "-0.0"
            value = 0.0

        pow10 = np.clip(pow10, min(self.ENG_PREFIXES), max(self.ENG_PREFIXES))

        mant = sign * value / (10.0 ** pow10)
        # Taking care of the cases like 999.9..., which may be rounded to 1000
        # instead of 1 k.  Beware of the corner case of values that are beyond
        # the range of SI prefixes (i.e. > 'Y').
        if (abs(float(format(mant, fmt))) >= 1000
                and pow10 < max(self.ENG_PREFIXES)):
            mant /= 1000
            pow10 += 3

        unit_prefix = self.ENG_PREFIXES[int(pow10)]
        if self.unit or unit_prefix:
            suffix = f"{self.sep}{unit_prefix}{self.unit}"
        else:
            suffix = ""
        if self._usetex or self._useMathText:
            return f"${mant:{fmt}}${suffix}"
        else:
            return f"{mant:{fmt}}{suffix}"


class PercentFormatter(Formatter):
    """
    Format numbers as a percentage.

    Parameters
    ----------
    xmax : float
        Determines how the number is converted into a percentage.
        *xmax* is the data value that corresponds to 100%.
        Percentages are computed as ``x / xmax * 100``. So if the data is
        already scaled to be percentages, *xmax* will be 100. Another common
        situation is where *xmax* is 1.0.

    decimals : None or int
        The number of decimal places to place after the point.
        If *None* (the default), the number will be computed automatically.

    symbol : str or None
        A string that will be appended to the label. It may be
        *None* or empty to indicate that no symbol should be used. LaTeX
        special characters are escaped in *symbol* whenever latex mode is
        enabled, unless *is_latex* is *True*.

    is_latex : bool
        If *False*, reserved LaTeX characters in *symbol* will be escaped.
    """
    def __init__(self, xmax=100, decimals=None, symbol='%', is_latex=False):
        self.xmax = xmax + 0.0
        self.decimals = decimals
        self._symbol = symbol
        self._is_latex = is_latex

    def __call__(self, x, pos=None):
        """Format the tick as a percentage with the appropriate scaling."""
        ax_min, ax_max = self.axis.get_view_interval()
        display_range = abs(ax_max - ax_min)
        return self.fix_minus(self.format_pct(x, display_range))

    def format_pct(self, x, display_range):
        """
        Format the number as a percentage number with the correct
        number of decimals and adds the percent symbol, if any.

        If ``self.decimals`` is `None`, the number of digits after the
        decimal point is set based on the *display_range* of the axis
        as follows:

        ============= ======== =======================
        display_range decimals sample
        ============= ======== =======================
        >50           0        ``x = 34.5`` => 35%
        >5            1        ``x = 34.5`` => 34.5%
        >0.5          2        ``x = 34.5`` => 34.50%
        ...           ...      ...
        ============= ======== =======================

        This method will not be very good for tiny axis ranges or
        extremely large ones. It assumes that the values on the chart
        are percentages displayed on a reasonable scale.
        """
        x = self.convert_to_pct(x)
        if self.decimals is None:
            # conversion works because display_range is a difference
            scaled_range = self.convert_to_pct(display_range)
            if scaled_range <= 0:
                decimals = 0
            else:
                # Luckily Python's built-in ceil rounds to +inf, not away from
                # zero. This is very important since the equation for decimals
                # starts out as `scaled_range > 0.5 * 10**(2 - decimals)`
                # and ends up with `decimals > 2 - log10(2 * scaled_range)`.
                decimals = math.ceil(2.0 - math.log10(2.0 * scaled_range))
                if decimals > 5:
                    decimals = 5
                elif decimals < 0:
                    decimals = 0
        else:
            decimals = self.decimals
        s = f'{x:0.{int(decimals)}f}'

        return s + self.symbol

    def convert_to_pct(self, x):
        return 100.0 * (x / self.xmax)

    @property
    def symbol(self):
        r"""
        The configured percent symbol as a string.

        If LaTeX is enabled via :rc:`text.usetex`, the special characters
        ``{'#', '$', '%', '&', '~', '_', '^', '\', '{', '}'}`` are
        automatically escaped in the string.
        """
        symbol = self._symbol
        if not symbol:
            symbol = ''
        elif not self._is_latex and mpl.rcParams['text.usetex']:
            # Source: http://www.personal.ceu.hu/tex/specchar.htm
            # Backslash must be first for this to work correctly since
            # it keeps getting added in
            for spec in r'\#$%&~_^{}':
                symbol = symbol.replace(spec, '\\' + spec)
        return symbol

    @symbol.setter
    def symbol(self, symbol):
        self._symbol = symbol


class Locator(TickHelper):
    """
    Determine tick locations.

    Note that the same locator should not be used across multiple
    `~matplotlib.axis.Axis` because the locator stores references to the Axis
    data and view limits.
    """

    # Some automatic tick locators can generate so many ticks they
    # kill the machine when you try and render them.
    # This parameter is set to cause locators to raise an error if too
    # many ticks are generated.
    MAXTICKS = 1000

    def tick_values(self, vmin, vmax):
        """
        Return the values of the located ticks given **vmin** and **vmax**.

        .. note::
            To get tick locations with the vmin and vmax values defined
            automatically for the associated ``axis`` simply call
            the Locator instance::

                >>> print(type(loc))
                <type 'Locator'>
                >>> print(loc())
                [1, 2, 3, 4]

        """
        raise NotImplementedError('Derived must override')

    def set_params(self, **kwargs):
        """
        Do nothing, and raise a warning. Any locator class not supporting the
        set_params() function will call this.
        """
        _api.warn_external(
            "'set_params()' not defined for locator of type " +
            str(type(self)))

    def __call__(self):
        """Return the locations of the ticks."""
        # note: some locators return data limits, other return view limits,
        # hence there is no *one* interface to call self.tick_values.
        raise NotImplementedError('Derived must override')

    def raise_if_exceeds(self, locs):
        """
        Log at WARNING level if *locs* is longer than `Locator.MAXTICKS`.

        This is intended to be called immediately before returning *locs* from
        ``__call__`` to inform users in case their Locator returns a huge
        number of ticks, causing Matplotlib to run out of memory.

        The "strange" name of this method dates back to when it would raise an
        exception instead of emitting a log.
        """
        if len(locs) >= self.MAXTICKS:
            _log.warning(
                "Locator attempting to generate %s ticks ([%s, ..., %s]), "
                "which exceeds Locator.MAXTICKS (%s).",
                len(locs), locs[0], locs[-1], self.MAXTICKS)
        return locs

    def nonsingular(self, v0, v1):
        """
        Adjust a range as needed to avoid singularities.

        This method gets called during autoscaling, with ``(v0, v1)`` set to
        the data limits on the Axes if the Axes contains any data, or
        ``(-inf, +inf)`` if not.

        - If ``v0 == v1`` (possibly up to some floating point slop), this
          method returns an expanded interval around this value.
        - If ``(v0, v1) == (-inf, +inf)``, this method returns appropriate
          default view limits.
        - Otherwise, ``(v0, v1)`` is returned without modification.
        """
        return mtransforms.nonsingular(v0, v1, expander=.05)

    def view_limits(self, vmin, vmax):
        """
        Select a scale for the range from vmin to vmax.

        Subclasses should override this method to change locator behaviour.
        """
        return mtransforms.nonsingular(vmin, vmax)


class IndexLocator(Locator):
    """
    Place ticks at every nth point plotted.

    IndexLocator assumes index plotting; i.e., that the ticks are placed at integer
    values in the range between 0 and len(data) inclusive.
    """
    def __init__(self, base, offset):
        """Place ticks every *base* data point, starting at *offset*."""
        self._base = base
        self.offset = offset

    def set_params(self, base=None, offset=None):
        """Set parameters within this locator"""
        if base is not None:
            self._base = base
        if offset is not None:
            self.offset = offset

    def __call__(self):
        """Return the locations of the ticks"""
        dmin, dmax = self.axis.get_data_interval()
        return self.tick_values(dmin, dmax)

    def tick_values(self, vmin, vmax):
        return self.raise_if_exceeds(
            np.arange(vmin + self.offset, vmax + 1, self._base))


class FixedLocator(Locator):
    r"""
    Place ticks at a set of fixed values.

    If *nbins* is None ticks are placed at all values. Otherwise, the *locs* array of
    possible positions will be subsampled to keep the number of ticks
    :math:`\leq nbins + 1`. The subsampling will be done to include the smallest
    absolute value; for example, if zero is included in the array of possibilities, then
    it will be included in the chosen ticks.
    """

    def __init__(self, locs, nbins=None):
        self.locs = np.asarray(locs)
        _api.check_shape((None,), locs=self.locs)
        self.nbins = max(nbins, 2) if nbins is not None else None

    def set_params(self, nbins=None):
        """Set parameters within this locator."""
        if nbins is not None:
            self.nbins = nbins

    def __call__(self):
        return self.tick_values(None, None)

    def tick_values(self, vmin, vmax):
        """
        Return the locations of the ticks.

        .. note::

            Because the values are fixed, vmin and vmax are not used in this
            method.

        """
        if self.nbins is None:
            return self.locs
        step = max(int(np.ceil(len(self.locs) / self.nbins)), 1)
        ticks = self.locs[::step]
        for i in range(1, step):
            ticks1 = self.locs[i::step]
            if np.abs(ticks1).min() < np.abs(ticks).min():
                ticks = ticks1
        return self.raise_if_exceeds(ticks)


class NullLocator(Locator):
    """
    No ticks
    """

    def __call__(self):
        return self.tick_values(None, None)

    def tick_values(self, vmin, vmax):
        """
        Return the locations of the ticks.

        .. note::

            Because the values are Null, vmin and vmax are not used in this
            method.
        """
        return []


class LinearLocator(Locator):
    """
    Place ticks at evenly spaced values.

    The first time this function is called it will try to set the
    number of ticks to make a nice tick partitioning.  Thereafter, the
    number of ticks will be fixed so that interactive navigation will
    be nice

    """
    def __init__(self, numticks=None, presets=None):
        """
        Parameters
        ----------
        numticks : int or None, default None
            Number of ticks. If None, *numticks* = 11.
        presets : dict or None, default: None
            Dictionary mapping ``(vmin, vmax)`` to an array of locations.
            Overrides *numticks* if there is an entry for the current
            ``(vmin, vmax)``.
        """
        self.numticks = numticks
        if presets is None:
            self.presets = {}
        else:
            self.presets = presets

    @property
    def numticks(self):
        # Old hard-coded default.
        return self._numticks if self._numticks is not None else 11

    @numticks.setter
    def numticks(self, numticks):
        self._numticks = numticks

    def set_params(self, numticks=None, presets=None):
        """Set parameters within this locator."""
        if presets is not None:
            self.presets = presets
        if numticks is not None:
            self.numticks = numticks

    def __call__(self):
        """Return the locations of the ticks."""
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        vmin, vmax = mtransforms.nonsingular(vmin, vmax, expander=0.05)

        if (vmin, vmax) in self.presets:
            return self.presets[(vmin, vmax)]

        if self.numticks == 0:
            return []
        ticklocs = np.linspace(vmin, vmax, self.numticks)

        return self.raise_if_exceeds(ticklocs)

    def view_limits(self, vmin, vmax):
        """Try to choose the view limits intelligently."""

        if vmax < vmin:
            vmin, vmax = vmax, vmin

        if vmin == vmax:
            vmin -= 1
            vmax += 1

        if mpl.rcParams['axes.autolimit_mode'] == 'round_numbers':
            exponent, remainder = divmod(
                math.log10(vmax - vmin), math.log10(max(self.numticks - 1, 1)))
            exponent -= (remainder < .5)
            scale = max(self.numticks - 1, 1) ** (-exponent)
            vmin = math.floor(scale * vmin) / scale
            vmax = math.ceil(scale * vmax) / scale

        return mtransforms.nonsingular(vmin, vmax)


class MultipleLocator(Locator):
    """
    Place ticks at every integer multiple of a base plus an offset.
    """

    def __init__(self, base=1.0, offset=0.0):
        """
        Parameters
        ----------
        base : float > 0, default: 1.0
            Interval between ticks.
        offset : float, default: 0.0
            Value added to each multiple of *base*.

            .. versionadded:: 3.8
        """
        self._edge = _Edge_integer(base, 0)
        self._offset = offset

    def set_params(self, base=None, offset=None):
        """
        Set parameters within this locator.

        Parameters
        ----------
        base : float > 0, optional
            Interval between ticks.
        offset : float, optional
            Value added to each multiple of *base*.

            .. versionadded:: 3.8
        """
        if base is not None:
            self._edge = _Edge_integer(base, 0)
        if offset is not None:
            self._offset = offset

    def __call__(self):
        """Return the locations of the ticks."""
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        if vmax < vmin:
            vmin, vmax = vmax, vmin
        step = self._edge.step
        vmin -= self._offset
        vmax -= self._offset
        vmin = self._edge.ge(vmin) * step
        n = (vmax - vmin + 0.001 * step) // step
        locs = vmin - step + np.arange(n + 3) * step + self._offset
        return self.raise_if_exceeds(locs)

    def view_limits(self, dmin, dmax):
        """
        Set the view limits to the nearest tick values that contain the data.
        """
        if mpl.rcParams['axes.autolimit_mode'] == 'round_numbers':
            vmin = self._edge.le(dmin - self._offset) * self._edge.step + self._offset
            vmax = self._edge.ge(dmax - self._offset) * self._edge.step + self._offset
            if vmin == vmax:
                vmin -= 1
                vmax += 1
        else:
            vmin = dmin
            vmax = dmax

        return mtransforms.nonsingular(vmin, vmax)


def scale_range(vmin, vmax, n=1, threshold=100):
    dv = abs(vmax - vmin)  # > 0 as nonsingular is called before.
    meanv = (vmax + vmin) / 2
    if abs(meanv) / dv < threshold:
        offset = 0
    else:
        offset = math.copysign(10 ** (math.log10(abs(meanv)) // 1), meanv)
    scale = 10 ** (math.log10(dv / n) // 1)
    return scale, offset


class _Edge_integer:
    """
    Helper for `.MaxNLocator`, `.MultipleLocator`, etc.

    Take floating-point precision limitations into account when calculating
    tick locations as integer multiples of a step.
    """
    def __init__(self, step, offset):
        """
        Parameters
        ----------
        step : float > 0
            Interval between ticks.
        offset : float
            Offset subtracted from the data limits prior to calculating tick
            locations.
        """
        if step <= 0:
            raise ValueError("'step' must be positive")
        self.step = step
        self._offset = abs(offset)

    def closeto(self, ms, edge):
        # Allow more slop when the offset is large compared to the step.
        if self._offset > 0:
            digits = np.log10(self._offset / self.step)
            tol = max(1e-10, 10 ** (digits - 12))
            tol = min(0.4999, tol)
        else:
            tol = 1e-10
        return abs(ms - edge) < tol

    def le(self, x):
        """Return the largest n: n*step <= x."""
        d, m = divmod(x, self.step)
        if self.closeto(m / self.step, 1):
            return d + 1
        return d

    def ge(self, x):
        """Return the smallest n: n*step >= x."""
        d, m = divmod(x, self.step)
        if self.closeto(m / self.step, 0):
            return d
        return d + 1


class MaxNLocator(Locator):
    """
    Place evenly spaced ticks, with a cap on the total number of ticks.

    Finds nice tick locations with no more than :math:`nbins + 1` ticks being within the
    view limits. Locations beyond the limits are added to support autoscaling.
    """
    default_params = dict(nbins=10,
                          steps=None,
                          integer=False,
                          symmetric=False,
                          prune=None,
                          min_n_ticks=2)

    def __init__(self, nbins=None, **kwargs):
        """
        Parameters
        ----------
        nbins : int or 'auto', default: 10
            Maximum number of intervals; one less than max number of
            ticks.  If the string 'auto', the number of bins will be
            automatically determined based on the length of the axis.

        steps : array-like, optional
            Sequence of acceptable tick multiples, starting with 1 and
            ending with 10. For example, if ``steps=[1, 2, 4, 5, 10]``,
            ``20, 40, 60`` or ``0.4, 0.6, 0.8`` would be possible
            sets of ticks because they are multiples of 2.
            ``30, 60, 90`` would not be generated because 3 does not
            appear in this example list of steps.

        integer : bool, default: False
            If True, ticks will take only integer values, provided at least
            *min_n_ticks* integers are found within the view limits.

        symmetric : bool, default: False
            If True, autoscaling will result in a range symmetric about zero.

        prune : {'lower', 'upper', 'both', None}, default: None
            Remove the 'lower' tick, the 'upper' tick, or ticks on 'both' sides
            *if they fall exactly on an axis' edge* (this typically occurs when
            :rc:`axes.autolimit_mode` is 'round_numbers').  Removing such ticks
            is mostly useful for stacked or ganged plots, where the upper tick
            of an Axes overlaps with the lower tick of the axes above it.

        min_n_ticks : int, default: 2
            Relax *nbins* and *integer* constraints if necessary to obtain
            this minimum number of ticks.
        """
        if nbins is not None:
            kwargs['nbins'] = nbins
        self.set_params(**{**self.default_params, **kwargs})

    @staticmethod
    def _validate_steps(steps):
        if not np.iterable(steps):
            raise ValueError('steps argument must be an increasing sequence '
                             'of numbers between 1 and 10 inclusive')
        steps = np.asarray(steps)
        if np.any(np.diff(steps) <= 0) or steps[-1] > 10 or steps[0] < 1:
            raise ValueError('steps argument must be an increasing sequence '
                             'of numbers between 1 and 10 inclusive')
        if steps[0] != 1:
            steps = np.concatenate([[1], steps])
        if steps[-1] != 10:
            steps = np.concatenate([steps, [10]])
        return steps

    @staticmethod
    def _staircase(steps):
        # Make an extended staircase within which the needed step will be
        # found.  This is probably much larger than necessary.
        return np.concatenate([0.1 * steps[:-1], steps, [10 * steps[1]]])

    def set_params(self, **kwargs):
        """
        Set parameters for this locator.

        Parameters
        ----------
        nbins : int or 'auto', optional
            see `.MaxNLocator`
        steps : array-like, optional
            see `.MaxNLocator`
        integer : bool, optional
            see `.MaxNLocator`
        symmetric : bool, optional
            see `.MaxNLocator`
        prune : {'lower', 'upper', 'both', None}, optional
            see `.MaxNLocator`
        min_n_ticks : int, optional
            see `.MaxNLocator`
        """
        if 'nbins' in kwargs:
            self._nbins = kwargs.pop('nbins')
            if self._nbins != 'auto':
                self._nbins = int(self._nbins)
        if 'symmetric' in kwargs:
            self._symmetric = kwargs.pop('symmetric')
        if 'prune' in kwargs:
            prune = kwargs.pop('prune')
            _api.check_in_list(['upper', 'lower', 'both', None], prune=prune)
            self._prune = prune
        if 'min_n_ticks' in kwargs:
            self._min_n_ticks = max(1, kwargs.pop('min_n_ticks'))
        if 'steps' in kwargs:
            steps = kwargs.pop('steps')
            if steps is None:
                self._steps = np.array([1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10])
            else:
                self._steps = self._validate_steps(steps)
            self._extended_steps = self._staircase(self._steps)
        if 'integer' in kwargs:
            self._integer = kwargs.pop('integer')
        if kwargs:
            raise _api.kwarg_error("set_params", kwargs)

    def _raw_ticks(self, vmin, vmax):
        """
        Generate a list of tick locations including the range *vmin* to
        *vmax*.  In some applications, one or both of the end locations
        will not be needed, in which case they are trimmed off
        elsewhere.
        """
        if self._nbins == 'auto':
            if self.axis is not None:
                nbins = np.clip(self.axis.get_tick_space(),
                                max(1, self._min_n_ticks - 1), 9)
            else:
                nbins = 9
        else:
            nbins = self._nbins

        scale, offset = scale_range(vmin, vmax, nbins)
        _vmin = vmin - offset
        _vmax = vmax - offset
        steps = self._extended_steps * scale
        if self._integer:
            # For steps > 1, keep only integer values.
            igood = (steps < 1) | (np.abs(steps - np.round(steps)) < 0.001)
            steps = steps[igood]

        raw_step = ((_vmax - _vmin) / nbins)
        if hasattr(self.axis, "axes") and self.axis.axes.name == '3d':
            # Due to the change in automargin behavior in mpl3.9, we need to
            # adjust the raw step to match the mpl3.8 appearance. The zoom
            # factor of 2/48, gives us the 23/24 modifier.
            raw_step = raw_step * 23/24
        large_steps = steps >= raw_step
        if mpl.rcParams['axes.autolimit_mode'] == 'round_numbers':
            # Classic round_numbers mode may require a larger step.
            # Get first multiple of steps that are <= _vmin
            floored_vmins = (_vmin // steps) * steps
            floored_vmaxs = floored_vmins + steps * nbins
            large_steps = large_steps & (floored_vmaxs >= _vmax)

        # Find index of smallest large step
        if any(large_steps):
            istep = np.nonzero(large_steps)[0][0]
        else:
            istep = len(steps) - 1

        # Start at smallest of the steps greater than the raw step, and check
        # if it provides enough ticks. If not, work backwards through
        # smaller steps until one is found that provides enough ticks.
        for step in steps[:istep+1][::-1]:

            if (self._integer and
                    np.floor(_vmax) - np.ceil(_vmin) >= self._min_n_ticks - 1):
                step = max(1, step)
            best_vmin = (_vmin // step) * step

            # Find tick locations spanning the vmin-vmax range, taking into
            # account degradation of precision when there is a large offset.
            # The edge ticks beyond vmin and/or vmax are needed for the
            # "round_numbers" autolimit mode.
            edge = _Edge_integer(step, offset)
            low = edge.le(_vmin - best_vmin)
            high = edge.ge(_vmax - best_vmin)
            ticks = np.arange(low, high + 1) * step + best_vmin
            # Count only the ticks that will be displayed.
            nticks = ((ticks <= _vmax) & (ticks >= _vmin)).sum()
            if nticks >= self._min_n_ticks:
                break
        return ticks + offset

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        if self._symmetric:
            vmax = max(abs(vmin), abs(vmax))
            vmin = -vmax
        vmin, vmax = mtransforms.nonsingular(
            vmin, vmax, expander=1e-13, tiny=1e-14)
        locs = self._raw_ticks(vmin, vmax)

        prune = self._prune
        if prune == 'lower':
            locs = locs[1:]
        elif prune == 'upper':
            locs = locs[:-1]
        elif prune == 'both':
            locs = locs[1:-1]
        return self.raise_if_exceeds(locs)

    def view_limits(self, dmin, dmax):
        if self._symmetric:
            dmax = max(abs(dmin), abs(dmax))
            dmin = -dmax

        dmin, dmax = mtransforms.nonsingular(
            dmin, dmax, expander=1e-12, tiny=1e-13)

        if mpl.rcParams['axes.autolimit_mode'] == 'round_numbers':
            return self._raw_ticks(dmin, dmax)[[0, -1]]
        else:
            return dmin, dmax


def _is_decade(x, *, base=10, rtol=None):
    """Return True if *x* is an integer power of *base*."""
    if not np.isfinite(x):
        return False
    if x == 0.0:
        return True
    lx = np.log(abs(x)) / np.log(base)
    if rtol is None:
        return np.isclose(lx, np.round(lx))
    else:
        return np.isclose(lx, np.round(lx), rtol=rtol)


def _decade_less_equal(x, base):
    """
    Return the largest integer power of *base* that's less or equal to *x*.

    If *x* is negative, the exponent will be *greater*.
    """
    return (x if x == 0 else
            -_decade_greater_equal(-x, base) if x < 0 else
            base ** np.floor(np.log(x) / np.log(base)))


def _decade_greater_equal(x, base):
    """
    Return the smallest integer power of *base* that's greater or equal to *x*.

    If *x* is negative, the exponent will be *smaller*.
    """
    return (x if x == 0 else
            -_decade_less_equal(-x, base) if x < 0 else
            base ** np.ceil(np.log(x) / np.log(base)))


def _decade_less(x, base):
    """
    Return the largest integer power of *base* that's less than *x*.

    If *x* is negative, the exponent will be *greater*.
    """
    if x < 0:
        return -_decade_greater(-x, base)
    less = _decade_less_equal(x, base)
    if less == x:
        less /= base
    return less


def _decade_greater(x, base):
    """
    Return the smallest integer power of *base* that's greater than *x*.

    If *x* is negative, the exponent will be *smaller*.
    """
    if x < 0:
        return -_decade_less(-x, base)
    greater = _decade_greater_equal(x, base)
    if greater == x:
        greater *= base
    return greater


def _is_close_to_int(x):
    return math.isclose(x, round(x))


class LogLocator(Locator):
    """
    Place logarithmically spaced ticks.

    Places ticks at the values ``subs[j] * base**i``.
    """

    def __init__(self, base=10.0, subs=(1.0,), *, numticks=None):
        """
        Parameters
        ----------
        base : float, default: 10.0
            The base of the log used, so major ticks are placed at ``base**n``, where
            ``n`` is an integer.
        subs : None or {'auto', 'all'} or sequence of float, default: (1.0,)
            Gives the multiples of integer powers of the base at which to place ticks.
            The default of ``(1.0, )`` places ticks only at integer powers of the base.
            Permitted string values are ``'auto'`` and ``'all'``. Both of these use an
            algorithm based on the axis view limits to determine whether and how to put
            ticks between integer powers of the base:
            - ``'auto'``: Ticks are placed only between integer powers.
            - ``'all'``: Ticks are placed between *and* at integer powers.
            - ``None``: Equivalent to ``'auto'``.
        numticks : None or int, default: None
            The maximum number of ticks to allow on a given axis. The default of
            ``None`` will try to choose intelligently as long as this Locator has
            already been assigned to an axis using `~.axis.Axis.get_tick_space`, but
            otherwise falls back to 9.
        """
        if numticks is None:
            if mpl.rcParams['_internal.classic_mode']:
                numticks = 15
            else:
                numticks = 'auto'
        self._base = float(base)
        self._set_subs(subs)
        self.numticks = numticks

    def set_params(self, base=None, subs=None, *, numticks=None):
        """Set parameters within this locator."""
        if base is not None:
            self._base = float(base)
        if subs is not None:
            self._set_subs(subs)
        if numticks is not None:
            self.numticks = numticks

    def _set_subs(self, subs):
        """
        Set the minor ticks for the log scaling every ``base**i*subs[j]``.
        """
        if subs is None:  # consistency with previous bad API
            self._subs = 'auto'
        elif isinstance(subs, str):
            _api.check_in_list(('all', 'auto'), subs=subs)
            self._subs = subs
        else:
            try:
                self._subs = np.asarray(subs, dtype=float)
            except ValueError as e:
                raise ValueError("subs must be None, 'all', 'auto' or "
                                 "a sequence of floats, not "
                                 f"{subs}.") from e
            if self._subs.ndim != 1:
                raise ValueError("A sequence passed to subs must be "
                                 "1-dimensional, not "
                                 f"{self._subs.ndim}-dimensional.")

    def __call__(self):
        """Return the locations of the ticks."""
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        if self.numticks == 'auto':
            if self.axis is not None:
                numticks = np.clip(self.axis.get_tick_space(), 2, 9)
            else:
                numticks = 9
        else:
            numticks = self.numticks

        b = self._base
        if vmin <= 0.0:
            if self.axis is not None:
                vmin = self.axis.get_minpos()

            if vmin <= 0.0 or not np.isfinite(vmin):
                raise ValueError(
                    "Data has no positive values, and therefore cannot be log-scaled.")

        _log.debug('vmin %s vmax %s', vmin, vmax)

        if vmax < vmin:
            vmin, vmax = vmax, vmin
        log_vmin = math.log(vmin) / math.log(b)
        log_vmax = math.log(vmax) / math.log(b)

        numdec = math.floor(log_vmax) - math.ceil(log_vmin)

        if isinstance(self._subs, str):
            if numdec > 10 or b < 3:
                if self._subs == 'auto':
                    return np.array([])  # no minor or major ticks
                else:
                    subs = np.array([1.0])  # major ticks
            else:
                _first = 2.0 if self._subs == 'auto' else 1.0
                subs = np.arange(_first, b)
        else:
            subs = self._subs

        # Get decades between major ticks.
        stride = (max(math.ceil(numdec / (numticks - 1)), 1)
                  if mpl.rcParams['_internal.classic_mode'] else
                  numdec // numticks + 1)

        # if we have decided that the stride is as big or bigger than
        # the range, clip the stride back to the available range - 1
        # with a floor of 1.  This prevents getting axis with only 1 tick
        # visible.
        if stride >= numdec:
            stride = max(1, numdec - 1)

        # Does subs include anything other than 1?  Essentially a hack to know
        # whether we're a major or a minor locator.
        have_subs = len(subs) > 1 or (len(subs) == 1 and subs[0] != 1.0)

        decades = np.arange(math.floor(log_vmin) - stride,
                            math.ceil(log_vmax) + 2 * stride, stride)

        if have_subs:
            if stride == 1:
                ticklocs = np.concatenate(
                    [subs * decade_start for decade_start in b ** decades])
            else:
                ticklocs = np.array([])
        else:
            ticklocs = b ** decades

        _log.debug('ticklocs %r', ticklocs)
        if (len(subs) > 1
                and stride == 1
                and ((vmin <= ticklocs) & (ticklocs <= vmax)).sum() <= 1):
            # If we're a minor locator *that expects at least two ticks per
            # decade* and the major locator stride is 1 and there's no more
            # than one minor tick, switch to AutoLocator.
            return AutoLocator().tick_values(vmin, vmax)
        else:
            return self.raise_if_exceeds(ticklocs)

    def view_limits(self, vmin, vmax):
        """Try to choose the view limits intelligently."""
        b = self._base

        vmin, vmax = self.nonsingular(vmin, vmax)

        if mpl.rcParams['axes.autolimit_mode'] == 'round_numbers':
            vmin = _decade_less_equal(vmin, b)
            vmax = _decade_greater_equal(vmax, b)

        return vmin, vmax

    def nonsingular(self, vmin, vmax):
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            vmin, vmax = 1, 10  # Initial range, no data plotted yet.
        elif vmax <= 0:
            _api.warn_external(
                "Data has no positive values, and therefore cannot be "
                "log-scaled.")
            vmin, vmax = 1, 10
        else:
            # Consider shared axises
            minpos = min(axis.get_minpos() for axis in self.axis._get_shared_axis())
            if not np.isfinite(minpos):
                minpos = 1e-300  # This should never take effect.
            if vmin <= 0:
                vmin = minpos
            if vmin == vmax:
                vmin = _decade_less(vmin, self._base)
                vmax = _decade_greater(vmax, self._base)
        return vmin, vmax


class SymmetricalLogLocator(Locator):
    """
    Place ticks spaced linearly near zero and spaced logarithmically beyond a threshold.
    """

    def __init__(self, transform=None, subs=None, linthresh=None, base=None):
        """
        Parameters
        ----------
        transform : `~.scale.SymmetricalLogTransform`, optional
            If set, defines the *base* and *linthresh* of the symlog transform.
        base, linthresh : float, optional
            The *base* and *linthresh* of the symlog transform, as documented
            for `.SymmetricalLogScale`.  These parameters are only used if
            *transform* is not set.
        subs : sequence of float, default: [1]
            The multiples of integer powers of the base where ticks are placed,
            i.e., ticks are placed at
            ``[sub * base**i for i in ... for sub in subs]``.

        Notes
        -----
        Either *transform*, or both *base* and *linthresh*, must be given.
        """
        if transform is not None:
            self._base = transform.base
            self._linthresh = transform.linthresh
        elif linthresh is not None and base is not None:
            self._base = base
            self._linthresh = linthresh
        else:
            raise ValueError("Either transform, or both linthresh "
                             "and base, must be provided.")
        if subs is None:
            self._subs = [1.0]
        else:
            self._subs = subs
        self.numticks = 15

    def set_params(self, subs=None, numticks=None):
        """Set parameters within this locator."""
        if numticks is not None:
            self.numticks = numticks
        if subs is not None:
            self._subs = subs

    def __call__(self):
        """Return the locations of the ticks."""
        # Note, these are untransformed coordinates
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        linthresh = self._linthresh

        if vmax < vmin:
            vmin, vmax = vmax, vmin

        # The domain is divided into three sections, only some of
        # which may actually be present.
        #
        # <======== -t ==0== t ========>
        # aaaaaaaaa    bbbbb   ccccccccc
        #
        # a) and c) will have ticks at integral log positions.  The
        # number of ticks needs to be reduced if there are more
        # than self.numticks of them.
        #
        # b) has a tick at 0 and only 0 (we assume t is a small
        # number, and the linear segment is just an implementation
        # detail and not interesting.)
        #
        # We could also add ticks at t, but that seems to usually be
        # uninteresting.
        #
        # "simple" mode is when the range falls entirely within [-t, t]
        #  -- it should just display (vmin, 0, vmax)
        if -linthresh <= vmin < vmax <= linthresh:
            # only the linear range is present
            return sorted({vmin, 0, vmax})

        # Lower log range is present
        has_a = (vmin < -linthresh)
        # Upper log range is present
        has_c = (vmax > linthresh)

        # Check if linear range is present
        has_b = (has_a and vmax > -linthresh) or (has_c and vmin < linthresh)

        base = self._base

        def get_log_range(lo, hi):
            lo = np.floor(np.log(lo) / np.log(base))
            hi = np.ceil(np.log(hi) / np.log(base))
            return lo, hi

        # Calculate all the ranges, so we can determine striding
        a_lo, a_hi = (0, 0)
        if has_a:
            a_upper_lim = min(-linthresh, vmax)
            a_lo, a_hi = get_log_range(abs(a_upper_lim), abs(vmin) + 1)

        c_lo, c_hi = (0, 0)
        if has_c:
            c_lower_lim = max(linthresh, vmin)
            c_lo, c_hi = get_log_range(c_lower_lim, vmax + 1)

        # Calculate the total number of integer exponents in a and c ranges
        total_ticks = (a_hi - a_lo) + (c_hi - c_lo)
        if has_b:
            total_ticks += 1
        stride = max(total_ticks // (self.numticks - 1), 1)

        decades = []
        if has_a:
            decades.extend(-1 * (base ** (np.arange(a_lo, a_hi,
                                                    stride)[::-1])))

        if has_b:
            decades.append(0.0)

        if has_c:
            decades.extend(base ** (np.arange(c_lo, c_hi, stride)))

        subs = np.asarray(self._subs)

        if len(subs) > 1 or subs[0] != 1.0:
            ticklocs = []
            for decade in decades:
                if decade == 0:
                    ticklocs.append(decade)
                else:
                    ticklocs.extend(subs * decade)
        else:
            ticklocs = decades

        return self.raise_if_exceeds(np.array(ticklocs))

    def view_limits(self, vmin, vmax):
        """Try to choose the view limits intelligently."""
        b = self._base
        if vmax < vmin:
            vmin, vmax = vmax, vmin

        if mpl.rcParams['axes.autolimit_mode'] == 'round_numbers':
            vmin = _decade_less_equal(vmin, b)
            vmax = _decade_greater_equal(vmax, b)
            if vmin == vmax:
                vmin = _decade_less(vmin, b)
                vmax = _decade_greater(vmax, b)

        return mtransforms.nonsingular(vmin, vmax)


class AsinhLocator(Locator):
    """
    Place ticks spaced evenly on an inverse-sinh scale.

    Generally used with the `~.scale.AsinhScale` class.

    .. note::

       This API is provisional and may be revised in the future
       based on early user feedback.
    """
    def __init__(self, linear_width, numticks=11, symthresh=0.2,
                 base=10, subs=None):
        """
        Parameters
        ----------
        linear_width : float
            The scale parameter defining the extent
            of the quasi-linear region.
        numticks : int, default: 11
            The approximate number of major ticks that will fit
            along the entire axis
        symthresh : float, default: 0.2
            The fractional threshold beneath which data which covers
            a range that is approximately symmetric about zero
            will have ticks that are exactly symmetric.
        base : int, default: 10
            The number base used for rounding tick locations
            on a logarithmic scale. If this is less than one,
            then rounding is to the nearest integer multiple
            of powers of ten.
        subs : tuple, default: None
            Multiples of the number base, typically used
            for the minor ticks, e.g. (2, 5) when base=10.
        """
        super().__init__()
        self.linear_width = linear_width
        self.numticks = numticks
        self.symthresh = symthresh
        self.base = base
        self.subs = subs

    def set_params(self, numticks=None, symthresh=None,
                   base=None, subs=None):
        """Set parameters within this locator."""
        if numticks is not None:
            self.numticks = numticks
        if symthresh is not None:
            self.symthresh = symthresh
        if base is not None:
            self.base = base
        if subs is not None:
            self.subs = subs if len(subs) > 0 else None

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        if (vmin * vmax) < 0 and abs(1 + vmax / vmin) < self.symthresh:
            # Data-range appears to be almost symmetric, so round up:
            bound = max(abs(vmin), abs(vmax))
            return self.tick_values(-bound, bound)
        else:
            return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        # Construct a set of uniformly-spaced "on-screen" locations.
        ymin, ymax = self.linear_width * np.arcsinh(np.array([vmin, vmax])
                                                    / self.linear_width)
        ys = np.linspace(ymin, ymax, self.numticks)
        zero_dev = abs(ys / (ymax - ymin))
        if ymin * ymax < 0:
            # Ensure that the zero tick-mark is included, if the axis straddles zero.
            ys = np.hstack([ys[(zero_dev > 0.5 / self.numticks)], 0.0])

        # Transform the "on-screen" grid to the data space:
        xs = self.linear_width * np.sinh(ys / self.linear_width)
        zero_xs = (ys == 0)

        # Round the data-space values to be intuitive base-n numbers, keeping track of
        # positive and negative values separately and carefully treating the zero value.
        with np.errstate(divide="ignore"):  # base ** log(0) = base ** -inf = 0.
            if self.base > 1:
                pows = (np.sign(xs)
                        * self.base ** np.floor(np.log(abs(xs)) / math.log(self.base)))
                qs = np.outer(pows, self.subs).flatten() if self.subs else pows
            else:  # No need to adjust sign(pows), as it cancels out when computing qs.
                pows = np.where(zero_xs, 1, 10**np.floor(np.log10(abs(xs))))
                qs = pows * np.round(xs / pows)
        ticks = np.array(sorted(set(qs)))

        return ticks if len(ticks) >= 2 else np.linspace(vmin, vmax, self.numticks)


class LogitLocator(MaxNLocator):
    """
    Place ticks spaced evenly on a logit scale.
    """

    def __init__(self, minor=False, *, nbins="auto"):
        """
        Parameters
        ----------
        nbins : int or 'auto', optional
            Number of ticks. Only used if minor is False.
        minor : bool, default: False
            Indicate if this locator is for minor ticks or not.
        """

        self._minor = minor
        super().__init__(nbins=nbins, steps=[1, 2, 5, 10])

    def set_params(self, minor=None, **kwargs):
        """Set parameters within this locator."""
        if minor is not None:
            self._minor = minor
        super().set_params(**kwargs)

    @property
    def minor(self):
        return self._minor

    @minor.setter
    def minor(self, value):
        self.set_params(minor=value)

    def tick_values(self, vmin, vmax):
        # dummy axis has no axes attribute
        if hasattr(self.axis, "axes") and self.axis.axes.name == "polar":
            raise NotImplementedError("Polar axis cannot be logit scaled yet")

        if self._nbins == "auto":
            if self.axis is not None:
                nbins = self.axis.get_tick_space()
                if nbins < 2:
                    nbins = 2
            else:
                nbins = 9
        else:
            nbins = self._nbins

        # We define ideal ticks with their index:
        # linscale: ... 1e-3 1e-2 1e-1 1/2 1-1e-1 1-1e-2 1-1e-3 ...
        # b-scale : ... -3   -2   -1   0   1      2      3      ...
        def ideal_ticks(x):
            return 10 ** x if x < 0 else 1 - (10 ** (-x)) if x > 0 else 0.5

        vmin, vmax = self.nonsingular(vmin, vmax)
        binf = int(
            np.floor(np.log10(vmin))
            if vmin < 0.5
            else 0
            if vmin < 0.9
            else -np.ceil(np.log10(1 - vmin))
        )
        bsup = int(
            np.ceil(np.log10(vmax))
            if vmax <= 0.5
            else 1
            if vmax <= 0.9
            else -np.floor(np.log10(1 - vmax))
        )
        numideal = bsup - binf - 1
        if numideal >= 2:
            # have 2 or more wanted ideal ticks, so use them as major ticks
            if numideal > nbins:
                # to many ideal ticks, subsampling ideals for major ticks, and
                # take others for minor ticks
                subsampling_factor = math.ceil(numideal / nbins)
                if self._minor:
                    ticklocs = [
                        ideal_ticks(b)
                        for b in range(binf, bsup + 1)
                        if (b % subsampling_factor) != 0
                    ]
                else:
                    ticklocs = [
                        ideal_ticks(b)
                        for b in range(binf, bsup + 1)
                        if (b % subsampling_factor) == 0
                    ]
                return self.raise_if_exceeds(np.array(ticklocs))
            if self._minor:
                ticklocs = []
                for b in range(binf, bsup):
                    if b < -1:
                        ticklocs.extend(np.arange(2, 10) * 10 ** b)
                    elif b == -1:
                        ticklocs.extend(np.arange(2, 5) / 10)
                    elif b == 0:
                        ticklocs.extend(np.arange(6, 9) / 10)
                    else:
                        ticklocs.extend(
                            1 - np.arange(2, 10)[::-1] * 10 ** (-b - 1)
                        )
                return self.raise_if_exceeds(np.array(ticklocs))
            ticklocs = [ideal_ticks(b) for b in range(binf, bsup + 1)]
            return self.raise_if_exceeds(np.array(ticklocs))
        # the scale is zoomed so same ticks as linear scale can be used
        if self._minor:
            return []
        return super().tick_values(vmin, vmax)

    def nonsingular(self, vmin, vmax):
        standard_minpos = 1e-7
        initial_range = (standard_minpos, 1 - standard_minpos)
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        if not np.isfinite(vmin) or not np.isfinite(vmax):
            vmin, vmax = initial_range  # Initial range, no data plotted yet.
        elif vmax <= 0 or vmin >= 1:
            # vmax <= 0 occurs when all values are negative
            # vmin >= 1 occurs when all values are greater than one
            _api.warn_external(
                "Data has no values between 0 and 1, and therefore cannot be "
                "logit-scaled."
            )
            vmin, vmax = initial_range
        else:
            minpos = (
                self.axis.get_minpos()
                if self.axis is not None
                else standard_minpos
            )
            if not np.isfinite(minpos):
                minpos = standard_minpos  # This should never take effect.
            if vmin <= 0:
                vmin = minpos
            # NOTE: for vmax, we should query a property similar to get_minpos,
            # but related to the maximal, less-than-one data point.
            # Unfortunately, Bbox._minpos is defined very deep in the BBox and
            # updated with data, so for now we use 1 - minpos as a substitute.
            if vmax >= 1:
                vmax = 1 - minpos
            if vmin == vmax:
                vmin, vmax = 0.1 * vmin, 1 - 0.1 * vmin

        return vmin, vmax


class AutoLocator(MaxNLocator):
    """
    Place evenly spaced ticks, with the step size and maximum number of ticks chosen
    automatically.

    This is a subclass of `~matplotlib.ticker.MaxNLocator`, with parameters
    *nbins = 'auto'* and *steps = [1, 2, 2.5, 5, 10]*.
    """
    def __init__(self):
        """
        To know the values of the non-public parameters, please have a
        look to the defaults of `~matplotlib.ticker.MaxNLocator`.
        """
        if mpl.rcParams['_internal.classic_mode']:
            nbins = 9
            steps = [1, 2, 5, 10]
        else:
            nbins = 'auto'
            steps = [1, 2, 2.5, 5, 10]
        super().__init__(nbins=nbins, steps=steps)


class AutoMinorLocator(Locator):
    """
    Place evenly spaced minor ticks, with the step size and maximum number of ticks
    chosen automatically.

    The Axis must use a linear scale and have evenly spaced major ticks.
    """

    def __init__(self, n=None):
        """
        Parameters
        ----------
        n : int or 'auto', default: :rc:`xtick.minor.ndivs` or :rc:`ytick.minor.ndivs`
            The number of subdivisions of the interval between major ticks;
            e.g., n=2 will place a single minor tick midway between major ticks.

            If *n* is 'auto', it will be set to 4 or 5: if the distance
            between the major ticks equals 1, 2.5, 5 or 10 it can be perfectly
            divided in 5 equidistant sub-intervals with a length multiple of
            0.05; otherwise, it is divided in 4 sub-intervals.
        """
        self.ndivs = n

    def __call__(self):
        # docstring inherited
        if self.axis.get_scale() == 'log':
            _api.warn_external('AutoMinorLocator does not work on logarithmic scales')
            return []

        majorlocs = np.unique(self.axis.get_majorticklocs())
        if len(majorlocs) < 2:
            # Need at least two major ticks to find minor tick locations.
            # TODO: Figure out a way to still be able to display minor ticks with less
            # than two major ticks visible. For now, just display no ticks at all.
            return []
        majorstep = majorlocs[1] - majorlocs[0]

        if self.ndivs is None:
            self.ndivs = mpl.rcParams[
                'ytick.minor.ndivs' if self.axis.axis_name == 'y'
                else 'xtick.minor.ndivs']  # for x and z axis

        if self.ndivs == 'auto':
            majorstep_mantissa = 10 ** (np.log10(majorstep) % 1)
            ndivs = 5 if np.isclose(majorstep_mantissa, [1, 2.5, 5, 10]).any() else 4
        else:
            ndivs = self.ndivs

        minorstep = majorstep / ndivs

        vmin, vmax = sorted(self.axis.get_view_interval())
        t0 = majorlocs[0]
        tmin = round((vmin - t0) / minorstep)
        tmax = round((vmax - t0) / minorstep) + 1
        locs = (np.arange(tmin, tmax) * minorstep) + t0

        return self.raise_if_exceeds(locs)

    def tick_values(self, vmin, vmax):
        raise NotImplementedError(
            f"Cannot get tick locations for a {type(self).__name__}")
