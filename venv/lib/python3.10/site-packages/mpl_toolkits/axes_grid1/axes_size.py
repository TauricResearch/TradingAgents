"""
Provides classes of simple units that will be used with `.AxesDivider`
class (or others) to determine the size of each Axes. The unit
classes define `get_size` method that returns a tuple of two floats,
meaning relative and absolute sizes, respectively.

Note that this class is nothing more than a simple tuple of two
floats. Take a look at the Divider class to see how these two
values are used.

Once created, the unit classes can be modified by simple arithmetic
operations: addition /subtraction with another unit type or a real number and scaling
(multiplication or division) by a real number.
"""

from numbers import Real

from matplotlib import _api
from matplotlib.axes import Axes


class _Base:
    def __rmul__(self, other):
        return self * other

    def __mul__(self, other):
        if not isinstance(other, Real):
            return NotImplemented
        return Fraction(other, self)

    def __div__(self, other):
        return (1 / other) * self

    def __add__(self, other):
        if isinstance(other, _Base):
            return Add(self, other)
        else:
            return Add(self, Fixed(other))

    def __neg__(self):
        return -1 * self

    def __radd__(self, other):
        # other cannot be a _Base instance, because A + B would trigger
        # A.__add__(B) first.
        return Add(self, Fixed(other))

    def __sub__(self, other):
        return self + (-other)

    def get_size(self, renderer):
        """
        Return two-float tuple with relative and absolute sizes.
        """
        raise NotImplementedError("Subclasses must implement")


class Add(_Base):
    """
    Sum of two sizes.
    """

    def __init__(self, a, b):
        self._a = a
        self._b = b

    def get_size(self, renderer):
        a_rel_size, a_abs_size = self._a.get_size(renderer)
        b_rel_size, b_abs_size = self._b.get_size(renderer)
        return a_rel_size + b_rel_size, a_abs_size + b_abs_size


class Fixed(_Base):
    """
    Simple fixed size with absolute part = *fixed_size* and relative part = 0.
    """

    def __init__(self, fixed_size):
        _api.check_isinstance(Real, fixed_size=fixed_size)
        self.fixed_size = fixed_size

    def get_size(self, renderer):
        rel_size = 0.
        abs_size = self.fixed_size
        return rel_size, abs_size


class Scaled(_Base):
    """
    Simple scaled(?) size with absolute part = 0 and
    relative part = *scalable_size*.
    """

    def __init__(self, scalable_size):
        self._scalable_size = scalable_size

    def get_size(self, renderer):
        rel_size = self._scalable_size
        abs_size = 0.
        return rel_size, abs_size

Scalable = Scaled


def _get_axes_aspect(ax):
    aspect = ax.get_aspect()
    if aspect == "auto":
        aspect = 1.
    return aspect


class AxesX(_Base):
    """
    Scaled size whose relative part corresponds to the data width
    of the *axes* multiplied by the *aspect*.
    """

    def __init__(self, axes, aspect=1., ref_ax=None):
        self._axes = axes
        self._aspect = aspect
        if aspect == "axes" and ref_ax is None:
            raise ValueError("ref_ax must be set when aspect='axes'")
        self._ref_ax = ref_ax

    def get_size(self, renderer):
        l1, l2 = self._axes.get_xlim()
        if self._aspect == "axes":
            ref_aspect = _get_axes_aspect(self._ref_ax)
            aspect = ref_aspect / _get_axes_aspect(self._axes)
        else:
            aspect = self._aspect

        rel_size = abs(l2-l1)*aspect
        abs_size = 0.
        return rel_size, abs_size


class AxesY(_Base):
    """
    Scaled size whose relative part corresponds to the data height
    of the *axes* multiplied by the *aspect*.
    """

    def __init__(self, axes, aspect=1., ref_ax=None):
        self._axes = axes
        self._aspect = aspect
        if aspect == "axes" and ref_ax is None:
            raise ValueError("ref_ax must be set when aspect='axes'")
        self._ref_ax = ref_ax

    def get_size(self, renderer):
        l1, l2 = self._axes.get_ylim()

        if self._aspect == "axes":
            ref_aspect = _get_axes_aspect(self._ref_ax)
            aspect = _get_axes_aspect(self._axes)
        else:
            aspect = self._aspect

        rel_size = abs(l2-l1)*aspect
        abs_size = 0.
        return rel_size, abs_size


class MaxExtent(_Base):
    """
    Size whose absolute part is either the largest width or the largest height
    of the given *artist_list*.
    """

    def __init__(self, artist_list, w_or_h):
        self._artist_list = artist_list
        _api.check_in_list(["width", "height"], w_or_h=w_or_h)
        self._w_or_h = w_or_h

    def add_artist(self, a):
        self._artist_list.append(a)

    def get_size(self, renderer):
        rel_size = 0.
        extent_list = [
            getattr(a.get_window_extent(renderer), self._w_or_h) / a.figure.dpi
            for a in self._artist_list]
        abs_size = max(extent_list, default=0)
        return rel_size, abs_size


class MaxWidth(MaxExtent):
    """
    Size whose absolute part is the largest width of the given *artist_list*.
    """

    def __init__(self, artist_list):
        super().__init__(artist_list, "width")


class MaxHeight(MaxExtent):
    """
    Size whose absolute part is the largest height of the given *artist_list*.
    """

    def __init__(self, artist_list):
        super().__init__(artist_list, "height")


class Fraction(_Base):
    """
    An instance whose size is a *fraction* of the *ref_size*.

    >>> s = Fraction(0.3, AxesX(ax))
    """

    def __init__(self, fraction, ref_size):
        _api.check_isinstance(Real, fraction=fraction)
        self._fraction_ref = ref_size
        self._fraction = fraction

    def get_size(self, renderer):
        if self._fraction_ref is None:
            return self._fraction, 0.
        else:
            r, a = self._fraction_ref.get_size(renderer)
            rel_size = r*self._fraction
            abs_size = a*self._fraction
            return rel_size, abs_size


def from_any(size, fraction_ref=None):
    """
    Create a Fixed unit when the first argument is a float, or a
    Fraction unit if that is a string that ends with %. The second
    argument is only meaningful when Fraction unit is created.

    >>> from mpl_toolkits.axes_grid1.axes_size import from_any
    >>> a = from_any(1.2) # => Fixed(1.2)
    >>> from_any("50%", a) # => Fraction(0.5, a)
    """
    if isinstance(size, Real):
        return Fixed(size)
    elif isinstance(size, str):
        if size[-1] == "%":
            return Fraction(float(size[:-1]) / 100, fraction_ref)
    raise ValueError("Unknown format")


class _AxesDecorationsSize(_Base):
    """
    Fixed size, corresponding to the size of decorations on a given Axes side.
    """

    _get_size_map = {
        "left":   lambda tight_bb, axes_bb: axes_bb.xmin - tight_bb.xmin,
        "right":  lambda tight_bb, axes_bb: tight_bb.xmax - axes_bb.xmax,
        "bottom": lambda tight_bb, axes_bb: axes_bb.ymin - tight_bb.ymin,
        "top":    lambda tight_bb, axes_bb: tight_bb.ymax - axes_bb.ymax,
    }

    def __init__(self, ax, direction):
        _api.check_in_list(self._get_size_map, direction=direction)
        self._direction = direction
        self._ax_list = [ax] if isinstance(ax, Axes) else ax

    def get_size(self, renderer):
        sz = max([
            self._get_size_map[self._direction](
                ax.get_tightbbox(renderer, call_axes_locator=False), ax.bbox)
            for ax in self._ax_list])
        dpi = renderer.points_to_pixels(72)
        abs_size = sz / dpi
        rel_size = 0
        return rel_size, abs_size
