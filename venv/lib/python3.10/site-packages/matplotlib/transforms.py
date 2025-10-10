"""
Matplotlib includes a framework for arbitrary geometric transformations that is used to
determine the final position of all elements drawn on the canvas.

Transforms are composed into trees of `TransformNode` objects
whose actual value depends on their children.  When the contents of
children change, their parents are automatically invalidated.  The
next time an invalidated transform is accessed, it is recomputed to
reflect those changes.  This invalidation/caching approach prevents
unnecessary recomputations of transforms, and contributes to better
interactive performance.

For example, here is a graph of the transform tree used to plot data to the figure:

.. graphviz:: /api/transforms.dot
    :alt: Diagram of transform tree from data to figure coordinates.

The framework can be used for both affine and non-affine
transformations.  However, for speed, we want to use the backend
renderers to perform affine transformations whenever possible.
Therefore, it is possible to perform just the affine or non-affine
part of a transformation on a set of data.  The affine is always
assumed to occur after the non-affine.  For any transform::

  full transform == non-affine part + affine part

The backends are not expected to handle non-affine transformations
themselves.

See the tutorial :ref:`transforms_tutorial` for examples
of how to use transforms.
"""

# Note: There are a number of places in the code where we use `np.min` or
# `np.minimum` instead of the builtin `min`, and likewise for `max`.  This is
# done so that `nan`s are propagated, instead of being silently dropped.

import functools
import itertools
import textwrap
import weakref
import math

import numpy as np
from numpy.linalg import inv

from matplotlib import _api
from matplotlib._path import (
    affine_transform, count_bboxes_overlapping_bbox, update_path_extents)
from .path import Path

DEBUG = False


def _make_str_method(*args, **kwargs):
    """
    Generate a ``__str__`` method for a `.Transform` subclass.

    After ::

        class T:
            __str__ = _make_str_method("attr", key="other")

    ``str(T(...))`` will be

    .. code-block:: text

        {type(T).__name__}(
            {self.attr},
            key={self.other})
    """
    indent = functools.partial(textwrap.indent, prefix=" " * 4)
    def strrepr(x): return repr(x) if isinstance(x, str) else str(x)
    return lambda self: (
        type(self).__name__ + "("
        + ",".join([*(indent("\n" + strrepr(getattr(self, arg)))
                      for arg in args),
                    *(indent("\n" + k + "=" + strrepr(getattr(self, arg)))
                      for k, arg in kwargs.items())])
        + ")")


class TransformNode:
    """
    The base class for anything that participates in the transform tree
    and needs to invalidate its parents or be invalidated.  This includes
    classes that are not really transforms, such as bounding boxes, since some
    transforms depend on bounding boxes to compute their values.
    """

    # Invalidation may affect only the affine part.  If the
    # invalidation was "affine-only", the _invalid member is set to
    # INVALID_AFFINE_ONLY

    # Possible values for the _invalid attribute.
    _VALID, _INVALID_AFFINE_ONLY, _INVALID_FULL = range(3)

    # Some metadata about the transform, used to determine whether an
    # invalidation is affine-only
    is_affine = False
    is_bbox = _api.deprecated("3.9")(_api.classproperty(lambda cls: False))

    pass_through = False
    """
    If pass_through is True, all ancestors will always be
    invalidated, even if 'self' is already invalid.
    """

    def __init__(self, shorthand_name=None):
        """
        Parameters
        ----------
        shorthand_name : str
            A string representing the "name" of the transform. The name carries
            no significance other than to improve the readability of
            ``str(transform)`` when DEBUG=True.
        """
        self._parents = {}
        # Initially invalid, until first computation.
        self._invalid = self._INVALID_FULL
        self._shorthand_name = shorthand_name or ''

    if DEBUG:
        def __str__(self):
            # either just return the name of this TransformNode, or its repr
            return self._shorthand_name or repr(self)

    def __getstate__(self):
        # turn the dictionary with weak values into a normal dictionary
        return {**self.__dict__,
                '_parents': {k: v() for k, v in self._parents.items()}}

    def __setstate__(self, data_dict):
        self.__dict__ = data_dict
        # turn the normal dictionary back into a dictionary with weak values
        # The extra lambda is to provide a callback to remove dead
        # weakrefs from the dictionary when garbage collection is done.
        self._parents = {
            k: weakref.ref(v, lambda _, pop=self._parents.pop, k=k: pop(k))
            for k, v in self._parents.items() if v is not None}

    def __copy__(self):
        cls = type(self)
        other = cls.__new__(cls)
        other.__dict__.update(self.__dict__)
        # If `c = a + b; a1 = copy(a)`, then modifications to `a1` do not
        # propagate back to `c`, i.e. we need to clear the parents of `a1`.
        other._parents = {}
        # If `c = a + b; c1 = copy(c)`, then modifications to `a` also need to
        # be propagated to `c1`.
        for key, val in vars(self).items():
            if isinstance(val, TransformNode) and id(self) in val._parents:
                other.set_children(val)  # val == getattr(other, key)
        return other

    def invalidate(self):
        """
        Invalidate this `TransformNode` and triggers an invalidation of its
        ancestors.  Should be called any time the transform changes.
        """
        return self._invalidate_internal(
            level=self._INVALID_AFFINE_ONLY if self.is_affine else self._INVALID_FULL,
            invalidating_node=self)

    def _invalidate_internal(self, level, invalidating_node):
        """
        Called by :meth:`invalidate` and subsequently ascends the transform
        stack calling each TransformNode's _invalidate_internal method.
        """
        # If we are already more invalid than the currently propagated invalidation,
        # then we don't need to do anything.
        if level <= self._invalid and not self.pass_through:
            return
        self._invalid = level
        for parent in list(self._parents.values()):
            parent = parent()  # Dereference the weak reference.
            if parent is not None:
                parent._invalidate_internal(level=level, invalidating_node=self)

    def set_children(self, *children):
        """
        Set the children of the transform, to let the invalidation
        system know which transforms can invalidate this transform.
        Should be called from the constructor of any transforms that
        depend on other transforms.
        """
        # Parents are stored as weak references, so that if the
        # parents are destroyed, references from the children won't
        # keep them alive.
        id_self = id(self)
        for child in children:
            # Use weak references so this dictionary won't keep obsolete nodes
            # alive; the callback deletes the dictionary entry. This is a
            # performance improvement over using WeakValueDictionary.
            ref = weakref.ref(
                self, lambda _, pop=child._parents.pop, k=id_self: pop(k))
            child._parents[id_self] = ref

    def frozen(self):
        """
        Return a frozen copy of this transform node.  The frozen copy will not
        be updated when its children change.  Useful for storing a previously
        known state of a transform where ``copy.deepcopy()`` might normally be
        used.
        """
        return self


class BboxBase(TransformNode):
    """
    The base class of all bounding boxes.

    This class is immutable; `Bbox` is a mutable subclass.

    The canonical representation is as two points, with no
    restrictions on their ordering.  Convenience properties are
    provided to get the left, bottom, right and top edges and width
    and height, but these are not stored explicitly.
    """

    is_bbox = _api.deprecated("3.9")(_api.classproperty(lambda cls: True))
    is_affine = True

    if DEBUG:
        @staticmethod
        def _check(points):
            if isinstance(points, np.ma.MaskedArray):
                _api.warn_external("Bbox bounds are a masked array.")
            points = np.asarray(points)
            if any((points[1, :] - points[0, :]) == 0):
                _api.warn_external("Singular Bbox.")

    def frozen(self):
        return Bbox(self.get_points().copy())
    frozen.__doc__ = TransformNode.__doc__

    def __array__(self, *args, **kwargs):
        return self.get_points()

    @property
    def x0(self):
        """
        The first of the pair of *x* coordinates that define the bounding box.

        This is not guaranteed to be less than :attr:`x1` (for that, use
        :attr:`xmin`).
        """
        return self.get_points()[0, 0]

    @property
    def y0(self):
        """
        The first of the pair of *y* coordinates that define the bounding box.

        This is not guaranteed to be less than :attr:`y1` (for that, use
        :attr:`ymin`).
        """
        return self.get_points()[0, 1]

    @property
    def x1(self):
        """
        The second of the pair of *x* coordinates that define the bounding box.

        This is not guaranteed to be greater than :attr:`x0` (for that, use
        :attr:`xmax`).
        """
        return self.get_points()[1, 0]

    @property
    def y1(self):
        """
        The second of the pair of *y* coordinates that define the bounding box.

        This is not guaranteed to be greater than :attr:`y0` (for that, use
        :attr:`ymax`).
        """
        return self.get_points()[1, 1]

    @property
    def p0(self):
        """
        The first pair of (*x*, *y*) coordinates that define the bounding box.

        This is not guaranteed to be the bottom-left corner (for that, use
        :attr:`min`).
        """
        return self.get_points()[0]

    @property
    def p1(self):
        """
        The second pair of (*x*, *y*) coordinates that define the bounding box.

        This is not guaranteed to be the top-right corner (for that, use
        :attr:`max`).
        """
        return self.get_points()[1]

    @property
    def xmin(self):
        """The left edge of the bounding box."""
        return np.min(self.get_points()[:, 0])

    @property
    def ymin(self):
        """The bottom edge of the bounding box."""
        return np.min(self.get_points()[:, 1])

    @property
    def xmax(self):
        """The right edge of the bounding box."""
        return np.max(self.get_points()[:, 0])

    @property
    def ymax(self):
        """The top edge of the bounding box."""
        return np.max(self.get_points()[:, 1])

    @property
    def min(self):
        """The bottom-left corner of the bounding box."""
        return np.min(self.get_points(), axis=0)

    @property
    def max(self):
        """The top-right corner of the bounding box."""
        return np.max(self.get_points(), axis=0)

    @property
    def intervalx(self):
        """
        The pair of *x* coordinates that define the bounding box.

        This is not guaranteed to be sorted from left to right.
        """
        return self.get_points()[:, 0]

    @property
    def intervaly(self):
        """
        The pair of *y* coordinates that define the bounding box.

        This is not guaranteed to be sorted from bottom to top.
        """
        return self.get_points()[:, 1]

    @property
    def width(self):
        """The (signed) width of the bounding box."""
        points = self.get_points()
        return points[1, 0] - points[0, 0]

    @property
    def height(self):
        """The (signed) height of the bounding box."""
        points = self.get_points()
        return points[1, 1] - points[0, 1]

    @property
    def size(self):
        """The (signed) width and height of the bounding box."""
        points = self.get_points()
        return points[1] - points[0]

    @property
    def bounds(self):
        """Return (:attr:`x0`, :attr:`y0`, :attr:`width`, :attr:`height`)."""
        (x0, y0), (x1, y1) = self.get_points()
        return (x0, y0, x1 - x0, y1 - y0)

    @property
    def extents(self):
        """Return (:attr:`x0`, :attr:`y0`, :attr:`x1`, :attr:`y1`)."""
        return self.get_points().flatten()  # flatten returns a copy.

    def get_points(self):
        raise NotImplementedError

    def containsx(self, x):
        """
        Return whether *x* is in the closed (:attr:`x0`, :attr:`x1`) interval.
        """
        x0, x1 = self.intervalx
        return x0 <= x <= x1 or x0 >= x >= x1

    def containsy(self, y):
        """
        Return whether *y* is in the closed (:attr:`y0`, :attr:`y1`) interval.
        """
        y0, y1 = self.intervaly
        return y0 <= y <= y1 or y0 >= y >= y1

    def contains(self, x, y):
        """
        Return whether ``(x, y)`` is in the bounding box or on its edge.
        """
        return self.containsx(x) and self.containsy(y)

    def overlaps(self, other):
        """
        Return whether this bounding box overlaps with the other bounding box.

        Parameters
        ----------
        other : `.BboxBase`
        """
        ax1, ay1, ax2, ay2 = self.extents
        bx1, by1, bx2, by2 = other.extents
        if ax2 < ax1:
            ax2, ax1 = ax1, ax2
        if ay2 < ay1:
            ay2, ay1 = ay1, ay2
        if bx2 < bx1:
            bx2, bx1 = bx1, bx2
        if by2 < by1:
            by2, by1 = by1, by2
        return ax1 <= bx2 and bx1 <= ax2 and ay1 <= by2 and by1 <= ay2

    def fully_containsx(self, x):
        """
        Return whether *x* is in the open (:attr:`x0`, :attr:`x1`) interval.
        """
        x0, x1 = self.intervalx
        return x0 < x < x1 or x0 > x > x1

    def fully_containsy(self, y):
        """
        Return whether *y* is in the open (:attr:`y0`, :attr:`y1`) interval.
        """
        y0, y1 = self.intervaly
        return y0 < y < y1 or y0 > y > y1

    def fully_contains(self, x, y):
        """
        Return whether ``x, y`` is in the bounding box, but not on its edge.
        """
        return self.fully_containsx(x) and self.fully_containsy(y)

    def fully_overlaps(self, other):
        """
        Return whether this bounding box overlaps with the other bounding box,
        not including the edges.

        Parameters
        ----------
        other : `.BboxBase`
        """
        ax1, ay1, ax2, ay2 = self.extents
        bx1, by1, bx2, by2 = other.extents
        if ax2 < ax1:
            ax2, ax1 = ax1, ax2
        if ay2 < ay1:
            ay2, ay1 = ay1, ay2
        if bx2 < bx1:
            bx2, bx1 = bx1, bx2
        if by2 < by1:
            by2, by1 = by1, by2
        return ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2

    def transformed(self, transform):
        """
        Construct a `Bbox` by statically transforming this one by *transform*.
        """
        pts = self.get_points()
        ll, ul, lr = transform.transform(np.array(
            [pts[0], [pts[0, 0], pts[1, 1]], [pts[1, 0], pts[0, 1]]]))
        return Bbox([ll, [lr[0], ul[1]]])

    coefs = {'C':  (0.5, 0.5),
             'SW': (0, 0),
             'S':  (0.5, 0),
             'SE': (1.0, 0),
             'E':  (1.0, 0.5),
             'NE': (1.0, 1.0),
             'N':  (0.5, 1.0),
             'NW': (0, 1.0),
             'W':  (0, 0.5)}

    def anchored(self, c, container):
        """
        Return a copy of the `Bbox` anchored to *c* within *container*.

        Parameters
        ----------
        c : (float, float) or {'C', 'SW', 'S', 'SE', 'E', 'NE', ...}
            Either an (*x*, *y*) pair of relative coordinates (0 is left or
            bottom, 1 is right or top), 'C' (center), or a cardinal direction
            ('SW', southwest, is bottom left, etc.).
        container : `Bbox`
            The box within which the `Bbox` is positioned.

        See Also
        --------
        .Axes.set_anchor
        """
        l, b, w, h = container.bounds
        L, B, W, H = self.bounds
        cx, cy = self.coefs[c] if isinstance(c, str) else c
        return Bbox(self._points +
                    [(l + cx * (w - W)) - L,
                     (b + cy * (h - H)) - B])

    def shrunk(self, mx, my):
        """
        Return a copy of the `Bbox`, shrunk by the factor *mx*
        in the *x* direction and the factor *my* in the *y* direction.
        The lower left corner of the box remains unchanged.  Normally
        *mx* and *my* will be less than 1, but this is not enforced.
        """
        w, h = self.size
        return Bbox([self._points[0],
                     self._points[0] + [mx * w, my * h]])

    def shrunk_to_aspect(self, box_aspect, container=None, fig_aspect=1.0):
        """
        Return a copy of the `Bbox`, shrunk so that it is as
        large as it can be while having the desired aspect ratio,
        *box_aspect*.  If the box coordinates are relative (i.e.
        fractions of a larger box such as a figure) then the
        physical aspect ratio of that figure is specified with
        *fig_aspect*, so that *box_aspect* can also be given as a
        ratio of the absolute dimensions, not the relative dimensions.
        """
        if box_aspect <= 0 or fig_aspect <= 0:
            raise ValueError("'box_aspect' and 'fig_aspect' must be positive")
        if container is None:
            container = self
        w, h = container.size
        H = w * box_aspect / fig_aspect
        if H <= h:
            W = w
        else:
            W = h * fig_aspect / box_aspect
            H = h
        return Bbox([self._points[0],
                     self._points[0] + (W, H)])

    def splitx(self, *args):
        """
        Return a list of new `Bbox` objects formed by splitting the original
        one with vertical lines at fractional positions given by *args*.
        """
        xf = [0, *args, 1]
        x0, y0, x1, y1 = self.extents
        w = x1 - x0
        return [Bbox([[x0 + xf0 * w, y0], [x0 + xf1 * w, y1]])
                for xf0, xf1 in itertools.pairwise(xf)]

    def splity(self, *args):
        """
        Return a list of new `Bbox` objects formed by splitting the original
        one with horizontal lines at fractional positions given by *args*.
        """
        yf = [0, *args, 1]
        x0, y0, x1, y1 = self.extents
        h = y1 - y0
        return [Bbox([[x0, y0 + yf0 * h], [x1, y0 + yf1 * h]])
                for yf0, yf1 in itertools.pairwise(yf)]

    def count_contains(self, vertices):
        """
        Count the number of vertices contained in the `Bbox`.
        Any vertices with a non-finite x or y value are ignored.

        Parameters
        ----------
        vertices : (N, 2) array
        """
        if len(vertices) == 0:
            return 0
        vertices = np.asarray(vertices)
        with np.errstate(invalid='ignore'):
            return (((self.min < vertices) &
                     (vertices < self.max)).all(axis=1).sum())

    def count_overlaps(self, bboxes):
        """
        Count the number of bounding boxes that overlap this one.

        Parameters
        ----------
        bboxes : sequence of `.BboxBase`
        """
        return count_bboxes_overlapping_bbox(
            self, np.atleast_3d([np.array(x) for x in bboxes]))

    def expanded(self, sw, sh):
        """
        Construct a `Bbox` by expanding this one around its center by the
        factors *sw* and *sh*.
        """
        width = self.width
        height = self.height
        deltaw = (sw * width - width) / 2.0
        deltah = (sh * height - height) / 2.0
        a = np.array([[-deltaw, -deltah], [deltaw, deltah]])
        return Bbox(self._points + a)

    def padded(self, w_pad, h_pad=None):
        """
        Construct a `Bbox` by padding this one on all four sides.

        Parameters
        ----------
        w_pad : float
            Width pad
        h_pad : float, optional
            Height pad.  Defaults to *w_pad*.

        """
        points = self.get_points()
        if h_pad is None:
            h_pad = w_pad
        return Bbox(points + [[-w_pad, -h_pad], [w_pad, h_pad]])

    def translated(self, tx, ty):
        """Construct a `Bbox` by translating this one by *tx* and *ty*."""
        return Bbox(self._points + (tx, ty))

    def corners(self):
        """
        Return the corners of this rectangle as an array of points.

        Specifically, this returns the array
        ``[[x0, y0], [x0, y1], [x1, y0], [x1, y1]]``.
        """
        (x0, y0), (x1, y1) = self.get_points()
        return np.array([[x0, y0], [x0, y1], [x1, y0], [x1, y1]])

    def rotated(self, radians):
        """
        Return the axes-aligned bounding box that bounds the result of rotating
        this `Bbox` by an angle of *radians*.
        """
        corners = self.corners()
        corners_rotated = Affine2D().rotate(radians).transform(corners)
        bbox = Bbox.unit()
        bbox.update_from_data_xy(corners_rotated, ignore=True)
        return bbox

    @staticmethod
    def union(bboxes):
        """Return a `Bbox` that contains all of the given *bboxes*."""
        if not len(bboxes):
            raise ValueError("'bboxes' cannot be empty")
        x0 = np.min([bbox.xmin for bbox in bboxes])
        x1 = np.max([bbox.xmax for bbox in bboxes])
        y0 = np.min([bbox.ymin for bbox in bboxes])
        y1 = np.max([bbox.ymax for bbox in bboxes])
        return Bbox([[x0, y0], [x1, y1]])

    @staticmethod
    def intersection(bbox1, bbox2):
        """
        Return the intersection of *bbox1* and *bbox2* if they intersect, or
        None if they don't.
        """
        x0 = np.maximum(bbox1.xmin, bbox2.xmin)
        x1 = np.minimum(bbox1.xmax, bbox2.xmax)
        y0 = np.maximum(bbox1.ymin, bbox2.ymin)
        y1 = np.minimum(bbox1.ymax, bbox2.ymax)
        return Bbox([[x0, y0], [x1, y1]]) if x0 <= x1 and y0 <= y1 else None


_default_minpos = np.array([np.inf, np.inf])


class Bbox(BboxBase):
    """
    A mutable bounding box.

    Examples
    --------
    **Create from known bounds**

    The default constructor takes the boundary "points" ``[[xmin, ymin],
    [xmax, ymax]]``.

        >>> Bbox([[1, 1], [3, 7]])
        Bbox([[1.0, 1.0], [3.0, 7.0]])

    Alternatively, a Bbox can be created from the flattened points array, the
    so-called "extents" ``(xmin, ymin, xmax, ymax)``

        >>> Bbox.from_extents(1, 1, 3, 7)
        Bbox([[1.0, 1.0], [3.0, 7.0]])

    or from the "bounds" ``(xmin, ymin, width, height)``.

        >>> Bbox.from_bounds(1, 1, 2, 6)
        Bbox([[1.0, 1.0], [3.0, 7.0]])

    **Create from collections of points**

    The "empty" object for accumulating Bboxs is the null bbox, which is a
    stand-in for the empty set.

        >>> Bbox.null()
        Bbox([[inf, inf], [-inf, -inf]])

    Adding points to the null bbox will give you the bbox of those points.

        >>> box = Bbox.null()
        >>> box.update_from_data_xy([[1, 1]])
        >>> box
        Bbox([[1.0, 1.0], [1.0, 1.0]])
        >>> box.update_from_data_xy([[2, 3], [3, 2]], ignore=False)
        >>> box
        Bbox([[1.0, 1.0], [3.0, 3.0]])

    Setting ``ignore=True`` is equivalent to starting over from a null bbox.

        >>> box.update_from_data_xy([[1, 1]], ignore=True)
        >>> box
        Bbox([[1.0, 1.0], [1.0, 1.0]])

    .. warning::

        It is recommended to always specify ``ignore`` explicitly.  If not, the
        default value of ``ignore`` can be changed at any time by code with
        access to your Bbox, for example using the method `~.Bbox.ignore`.

    **Properties of the ``null`` bbox**

    .. note::

        The current behavior of `Bbox.null()` may be surprising as it does
        not have all of the properties of the "empty set", and as such does
        not behave like a "zero" object in the mathematical sense. We may
        change that in the future (with a deprecation period).

    The null bbox is the identity for intersections

        >>> Bbox.intersection(Bbox([[1, 1], [3, 7]]), Bbox.null())
        Bbox([[1.0, 1.0], [3.0, 7.0]])

    except with itself, where it returns the full space.

        >>> Bbox.intersection(Bbox.null(), Bbox.null())
        Bbox([[-inf, -inf], [inf, inf]])

    A union containing null will always return the full space (not the other
    set!)

        >>> Bbox.union([Bbox([[0, 0], [0, 0]]), Bbox.null()])
        Bbox([[-inf, -inf], [inf, inf]])
    """

    def __init__(self, points, **kwargs):
        """
        Parameters
        ----------
        points : `~numpy.ndarray`
            A (2, 2) array of the form ``[[x0, y0], [x1, y1]]``.
        """
        super().__init__(**kwargs)
        points = np.asarray(points, float)
        if points.shape != (2, 2):
            raise ValueError('Bbox points must be of the form '
                             '"[[x0, y0], [x1, y1]]".')
        self._points = points
        self._minpos = _default_minpos.copy()
        self._ignore = True
        # it is helpful in some contexts to know if the bbox is a
        # default or has been mutated; we store the orig points to
        # support the mutated methods
        self._points_orig = self._points.copy()
    if DEBUG:
        ___init__ = __init__

        def __init__(self, points, **kwargs):
            self._check(points)
            self.___init__(points, **kwargs)

        def invalidate(self):
            self._check(self._points)
            super().invalidate()

    def frozen(self):
        # docstring inherited
        frozen_bbox = super().frozen()
        frozen_bbox._minpos = self.minpos.copy()
        return frozen_bbox

    @staticmethod
    def unit():
        """Create a new unit `Bbox` from (0, 0) to (1, 1)."""
        return Bbox([[0, 0], [1, 1]])

    @staticmethod
    def null():
        """Create a new null `Bbox` from (inf, inf) to (-inf, -inf)."""
        return Bbox([[np.inf, np.inf], [-np.inf, -np.inf]])

    @staticmethod
    def from_bounds(x0, y0, width, height):
        """
        Create a new `Bbox` from *x0*, *y0*, *width* and *height*.

        *width* and *height* may be negative.
        """
        return Bbox.from_extents(x0, y0, x0 + width, y0 + height)

    @staticmethod
    def from_extents(*args, minpos=None):
        """
        Create a new Bbox from *left*, *bottom*, *right* and *top*.

        The *y*-axis increases upwards.

        Parameters
        ----------
        left, bottom, right, top : float
            The four extents of the bounding box.
        minpos : float or None
            If this is supplied, the Bbox will have a minimum positive value
            set. This is useful when dealing with logarithmic scales and other
            scales where negative bounds result in floating point errors.
        """
        bbox = Bbox(np.reshape(args, (2, 2)))
        if minpos is not None:
            bbox._minpos[:] = minpos
        return bbox

    def __format__(self, fmt):
        return (
            'Bbox(x0={0.x0:{1}}, y0={0.y0:{1}}, x1={0.x1:{1}}, y1={0.y1:{1}})'.
            format(self, fmt))

    def __str__(self):
        return format(self, '')

    def __repr__(self):
        return 'Bbox([[{0.x0}, {0.y0}], [{0.x1}, {0.y1}]])'.format(self)

    def ignore(self, value):
        """
        Set whether the existing bounds of the box should be ignored
        by subsequent calls to :meth:`update_from_data_xy`.

        value : bool
            - When ``True``, subsequent calls to `update_from_data_xy` will
              ignore the existing bounds of the `Bbox`.
            - When ``False``, subsequent calls to `update_from_data_xy` will
              include the existing bounds of the `Bbox`.
        """
        self._ignore = value

    def update_from_path(self, path, ignore=None, updatex=True, updatey=True):
        """
        Update the bounds of the `Bbox` to contain the vertices of the
        provided path. After updating, the bounds will have positive *width*
        and *height*; *x0* and *y0* will be the minimal values.

        Parameters
        ----------
        path : `~matplotlib.path.Path`
        ignore : bool, optional
           - When ``True``, ignore the existing bounds of the `Bbox`.
           - When ``False``, include the existing bounds of the `Bbox`.
           - When ``None``, use the last value passed to :meth:`ignore`.
        updatex, updatey : bool, default: True
            When ``True``, update the x/y values.
        """
        if ignore is None:
            ignore = self._ignore

        if path.vertices.size == 0:
            return

        points, minpos, changed = update_path_extents(
            path, None, self._points, self._minpos, ignore)

        if changed:
            self.invalidate()
            if updatex:
                self._points[:, 0] = points[:, 0]
                self._minpos[0] = minpos[0]
            if updatey:
                self._points[:, 1] = points[:, 1]
                self._minpos[1] = minpos[1]

    def update_from_data_x(self, x, ignore=None):
        """
        Update the x-bounds of the `Bbox` based on the passed in data. After
        updating, the bounds will have positive *width*, and *x0* will be the
        minimal value.

        Parameters
        ----------
        x : `~numpy.ndarray`
            Array of x-values.
        ignore : bool, optional
           - When ``True``, ignore the existing bounds of the `Bbox`.
           - When ``False``, include the existing bounds of the `Bbox`.
           - When ``None``, use the last value passed to :meth:`ignore`.
        """
        x = np.ravel(x)
        self.update_from_data_xy(np.column_stack([x, np.ones(x.size)]),
                                 ignore=ignore, updatey=False)

    def update_from_data_y(self, y, ignore=None):
        """
        Update the y-bounds of the `Bbox` based on the passed in data. After
        updating, the bounds will have positive *height*, and *y0* will be the
        minimal value.

        Parameters
        ----------
        y : `~numpy.ndarray`
            Array of y-values.
        ignore : bool, optional
            - When ``True``, ignore the existing bounds of the `Bbox`.
            - When ``False``, include the existing bounds of the `Bbox`.
            - When ``None``, use the last value passed to :meth:`ignore`.
        """
        y = np.ravel(y)
        self.update_from_data_xy(np.column_stack([np.ones(y.size), y]),
                                 ignore=ignore, updatex=False)

    def update_from_data_xy(self, xy, ignore=None, updatex=True, updatey=True):
        """
        Update the `Bbox` bounds based on the passed in *xy* coordinates.

        After updating, the bounds will have positive *width* and *height*;
        *x0* and *y0* will be the minimal values.

        Parameters
        ----------
        xy : (N, 2) array-like
            The (x, y) coordinates.
        ignore : bool, optional
            - When ``True``, ignore the existing bounds of the `Bbox`.
            - When ``False``, include the existing bounds of the `Bbox`.
            - When ``None``, use the last value passed to :meth:`ignore`.
        updatex, updatey : bool, default: True
             When ``True``, update the x/y values.
        """
        if len(xy) == 0:
            return

        path = Path(xy)
        self.update_from_path(path, ignore=ignore,
                              updatex=updatex, updatey=updatey)

    @BboxBase.x0.setter
    def x0(self, val):
        self._points[0, 0] = val
        self.invalidate()

    @BboxBase.y0.setter
    def y0(self, val):
        self._points[0, 1] = val
        self.invalidate()

    @BboxBase.x1.setter
    def x1(self, val):
        self._points[1, 0] = val
        self.invalidate()

    @BboxBase.y1.setter
    def y1(self, val):
        self._points[1, 1] = val
        self.invalidate()

    @BboxBase.p0.setter
    def p0(self, val):
        self._points[0] = val
        self.invalidate()

    @BboxBase.p1.setter
    def p1(self, val):
        self._points[1] = val
        self.invalidate()

    @BboxBase.intervalx.setter
    def intervalx(self, interval):
        self._points[:, 0] = interval
        self.invalidate()

    @BboxBase.intervaly.setter
    def intervaly(self, interval):
        self._points[:, 1] = interval
        self.invalidate()

    @BboxBase.bounds.setter
    def bounds(self, bounds):
        l, b, w, h = bounds
        points = np.array([[l, b], [l + w, b + h]], float)
        if np.any(self._points != points):
            self._points = points
            self.invalidate()

    @property
    def minpos(self):
        """
        The minimum positive value in both directions within the Bbox.

        This is useful when dealing with logarithmic scales and other scales
        where negative bounds result in floating point errors, and will be used
        as the minimum extent instead of *p0*.
        """
        return self._minpos

    @minpos.setter
    def minpos(self, val):
        self._minpos[:] = val

    @property
    def minposx(self):
        """
        The minimum positive value in the *x*-direction within the Bbox.

        This is useful when dealing with logarithmic scales and other scales
        where negative bounds result in floating point errors, and will be used
        as the minimum *x*-extent instead of *x0*.
        """
        return self._minpos[0]

    @minposx.setter
    def minposx(self, val):
        self._minpos[0] = val

    @property
    def minposy(self):
        """
        The minimum positive value in the *y*-direction within the Bbox.

        This is useful when dealing with logarithmic scales and other scales
        where negative bounds result in floating point errors, and will be used
        as the minimum *y*-extent instead of *y0*.
        """
        return self._minpos[1]

    @minposy.setter
    def minposy(self, val):
        self._minpos[1] = val

    def get_points(self):
        """
        Get the points of the bounding box as an array of the form
        ``[[x0, y0], [x1, y1]]``.
        """
        self._invalid = 0
        return self._points

    def set_points(self, points):
        """
        Set the points of the bounding box directly from an array of the form
        ``[[x0, y0], [x1, y1]]``.  No error checking is performed, as this
        method is mainly for internal use.
        """
        if np.any(self._points != points):
            self._points = points
            self.invalidate()

    def set(self, other):
        """
        Set this bounding box from the "frozen" bounds of another `Bbox`.
        """
        if np.any(self._points != other.get_points()):
            self._points = other.get_points()
            self.invalidate()

    def mutated(self):
        """Return whether the bbox has changed since init."""
        return self.mutatedx() or self.mutatedy()

    def mutatedx(self):
        """Return whether the x-limits have changed since init."""
        return (self._points[0, 0] != self._points_orig[0, 0] or
                self._points[1, 0] != self._points_orig[1, 0])

    def mutatedy(self):
        """Return whether the y-limits have changed since init."""
        return (self._points[0, 1] != self._points_orig[0, 1] or
                self._points[1, 1] != self._points_orig[1, 1])


class TransformedBbox(BboxBase):
    """
    A `Bbox` that is automatically transformed by a given
    transform.  When either the child bounding box or transform
    changes, the bounds of this bbox will update accordingly.
    """

    def __init__(self, bbox, transform, **kwargs):
        """
        Parameters
        ----------
        bbox : `Bbox`
        transform : `Transform`
        """
        _api.check_isinstance(BboxBase, bbox=bbox)
        _api.check_isinstance(Transform, transform=transform)
        if transform.input_dims != 2 or transform.output_dims != 2:
            raise ValueError(
                "The input and output dimensions of 'transform' must be 2")

        super().__init__(**kwargs)
        self._bbox = bbox
        self._transform = transform
        self.set_children(bbox, transform)
        self._points = None

    __str__ = _make_str_method("_bbox", "_transform")

    def get_points(self):
        # docstring inherited
        if self._invalid:
            p = self._bbox.get_points()
            # Transform all four points, then make a new bounding box
            # from the result, taking care to make the orientation the
            # same.
            points = self._transform.transform(
                [[p[0, 0], p[0, 1]],
                 [p[1, 0], p[0, 1]],
                 [p[0, 0], p[1, 1]],
                 [p[1, 0], p[1, 1]]])
            points = np.ma.filled(points, 0.0)

            xs = min(points[:, 0]), max(points[:, 0])
            if p[0, 0] > p[1, 0]:
                xs = xs[::-1]

            ys = min(points[:, 1]), max(points[:, 1])
            if p[0, 1] > p[1, 1]:
                ys = ys[::-1]

            self._points = np.array([
                [xs[0], ys[0]],
                [xs[1], ys[1]]
            ])

            self._invalid = 0
        return self._points

    if DEBUG:
        _get_points = get_points

        def get_points(self):
            points = self._get_points()
            self._check(points)
            return points

    def contains(self, x, y):
        # Docstring inherited.
        return self._bbox.contains(*self._transform.inverted().transform((x, y)))

    def fully_contains(self, x, y):
        # Docstring inherited.
        return self._bbox.fully_contains(*self._transform.inverted().transform((x, y)))


class LockableBbox(BboxBase):
    """
    A `Bbox` where some elements may be locked at certain values.

    When the child bounding box changes, the bounds of this bbox will update
    accordingly with the exception of the locked elements.
    """
    def __init__(self, bbox, x0=None, y0=None, x1=None, y1=None, **kwargs):
        """
        Parameters
        ----------
        bbox : `Bbox`
            The child bounding box to wrap.

        x0 : float or None
            The locked value for x0, or None to leave unlocked.

        y0 : float or None
            The locked value for y0, or None to leave unlocked.

        x1 : float or None
            The locked value for x1, or None to leave unlocked.

        y1 : float or None
            The locked value for y1, or None to leave unlocked.

        """
        _api.check_isinstance(BboxBase, bbox=bbox)
        super().__init__(**kwargs)
        self._bbox = bbox
        self.set_children(bbox)
        self._points = None
        fp = [x0, y0, x1, y1]
        mask = [val is None for val in fp]
        self._locked_points = np.ma.array(fp, float, mask=mask).reshape((2, 2))

    __str__ = _make_str_method("_bbox", "_locked_points")

    def get_points(self):
        # docstring inherited
        if self._invalid:
            points = self._bbox.get_points()
            self._points = np.where(self._locked_points.mask,
                                    points,
                                    self._locked_points)
            self._invalid = 0
        return self._points

    if DEBUG:
        _get_points = get_points

        def get_points(self):
            points = self._get_points()
            self._check(points)
            return points

    @property
    def locked_x0(self):
        """
        float or None: The value used for the locked x0.
        """
        if self._locked_points.mask[0, 0]:
            return None
        else:
            return self._locked_points[0, 0]

    @locked_x0.setter
    def locked_x0(self, x0):
        self._locked_points.mask[0, 0] = x0 is None
        self._locked_points.data[0, 0] = x0
        self.invalidate()

    @property
    def locked_y0(self):
        """
        float or None: The value used for the locked y0.
        """
        if self._locked_points.mask[0, 1]:
            return None
        else:
            return self._locked_points[0, 1]

    @locked_y0.setter
    def locked_y0(self, y0):
        self._locked_points.mask[0, 1] = y0 is None
        self._locked_points.data[0, 1] = y0
        self.invalidate()

    @property
    def locked_x1(self):
        """
        float or None: The value used for the locked x1.
        """
        if self._locked_points.mask[1, 0]:
            return None
        else:
            return self._locked_points[1, 0]

    @locked_x1.setter
    def locked_x1(self, x1):
        self._locked_points.mask[1, 0] = x1 is None
        self._locked_points.data[1, 0] = x1
        self.invalidate()

    @property
    def locked_y1(self):
        """
        float or None: The value used for the locked y1.
        """
        if self._locked_points.mask[1, 1]:
            return None
        else:
            return self._locked_points[1, 1]

    @locked_y1.setter
    def locked_y1(self, y1):
        self._locked_points.mask[1, 1] = y1 is None
        self._locked_points.data[1, 1] = y1
        self.invalidate()


class Transform(TransformNode):
    """
    The base class of all `TransformNode` instances that
    actually perform a transformation.

    All non-affine transformations should be subclasses of this class.
    New affine transformations should be subclasses of `Affine2D`.

    Subclasses of this class should override the following members (at
    minimum):

    - :attr:`input_dims`
    - :attr:`output_dims`
    - :meth:`transform`
    - :meth:`inverted` (if an inverse exists)

    The following attributes may be overridden if the default is unsuitable:

    - :attr:`is_separable` (defaults to True for 1D -> 1D transforms, False
      otherwise)
    - :attr:`has_inverse` (defaults to True if :meth:`inverted` is overridden,
      False otherwise)

    If the transform needs to do something non-standard with
    `matplotlib.path.Path` objects, such as adding curves
    where there were once line segments, it should override:

    - :meth:`transform_path`
    """

    input_dims = None
    """
    The number of input dimensions of this transform.
    Must be overridden (with integers) in the subclass.
    """

    output_dims = None
    """
    The number of output dimensions of this transform.
    Must be overridden (with integers) in the subclass.
    """

    is_separable = False
    """True if this transform is separable in the x- and y- dimensions."""

    has_inverse = False
    """True if this transform has a corresponding inverse transform."""

    def __init_subclass__(cls):
        # 1d transforms are always separable; we assume higher-dimensional ones
        # are not but subclasses can also directly set is_separable -- this is
        # verified by checking whether "is_separable" appears more than once in
        # the class's MRO (it appears once in Transform).
        if (sum("is_separable" in vars(parent) for parent in cls.__mro__) == 1
                and cls.input_dims == cls.output_dims == 1):
            cls.is_separable = True
        # Transform.inverted raises NotImplementedError; we assume that if this
        # is overridden then the transform is invertible but subclass can also
        # directly set has_inverse.
        if (sum("has_inverse" in vars(parent) for parent in cls.__mro__) == 1
                and hasattr(cls, "inverted")
                and cls.inverted is not Transform.inverted):
            cls.has_inverse = True

    def __add__(self, other):
        """
        Compose two transforms together so that *self* is followed by *other*.

        ``A + B`` returns a transform ``C`` so that
        ``C.transform(x) == B.transform(A.transform(x))``.
        """
        return (composite_transform_factory(self, other)
                if isinstance(other, Transform) else
                NotImplemented)

    # Equality is based on object identity for `Transform`s (so we don't
    # override `__eq__`), but some subclasses, such as TransformWrapper &
    # AffineBase, override this behavior.

    def _iter_break_from_left_to_right(self):
        """
        Return an iterator breaking down this transform stack from left to
        right recursively. If self == ((A, N), A) then the result will be an
        iterator which yields I : ((A, N), A), followed by A : (N, A),
        followed by (A, N) : (A), but not ((A, N), A) : I.

        This is equivalent to flattening the stack then yielding
        ``flat_stack[:i], flat_stack[i:]`` where i=0..(n-1).
        """
        yield IdentityTransform(), self

    @property
    def depth(self):
        """
        Return the number of transforms which have been chained
        together to form this Transform instance.

        .. note::

            For the special case of a Composite transform, the maximum depth
            of the two is returned.

        """
        return 1

    def contains_branch(self, other):
        """
        Return whether the given transform is a sub-tree of this transform.

        This routine uses transform equality to identify sub-trees, therefore
        in many situations it is object id which will be used.

        For the case where the given transform represents the whole
        of this transform, returns True.
        """
        if self.depth < other.depth:
            return False

        # check that a subtree is equal to other (starting from self)
        for _, sub_tree in self._iter_break_from_left_to_right():
            if sub_tree == other:
                return True
        return False

    def contains_branch_seperately(self, other_transform):
        """
        Return whether the given branch is a sub-tree of this transform on
        each separate dimension.

        A common use for this method is to identify if a transform is a blended
        transform containing an Axes' data transform. e.g.::

            x_isdata, y_isdata = trans.contains_branch_seperately(ax.transData)

        """
        if self.output_dims != 2:
            raise ValueError('contains_branch_seperately only supports '
                             'transforms with 2 output dimensions')
        # for a non-blended transform each separate dimension is the same, so
        # just return the appropriate shape.
        return (self.contains_branch(other_transform), ) * 2

    def __sub__(self, other):
        """
        Compose *self* with the inverse of *other*, cancelling identical terms
        if any::

            # In general:
            A - B == A + B.inverted()
            # (but see note regarding frozen transforms below).

            # If A "ends with" B (i.e. A == A' + B for some A') we can cancel
            # out B:
            (A' + B) - B == A'

            # Likewise, if B "starts with" A (B = A + B'), we can cancel out A:
            A - (A + B') == B'.inverted() == B'^-1

        Cancellation (rather than naively returning ``A + B.inverted()``) is
        important for multiple reasons:

        - It avoids floating-point inaccuracies when computing the inverse of
          B: ``B - B`` is guaranteed to cancel out exactly (resulting in the
          identity transform), whereas ``B + B.inverted()`` may differ by a
          small epsilon.
        - ``B.inverted()`` always returns a frozen transform: if one computes
          ``A + B + B.inverted()`` and later mutates ``B``, then
          ``B.inverted()`` won't be updated and the last two terms won't cancel
          out anymore; on the other hand, ``A + B - B`` will always be equal to
          ``A`` even if ``B`` is mutated.
        """
        # we only know how to do this operation if other is a Transform.
        if not isinstance(other, Transform):
            return NotImplemented
        for remainder, sub_tree in self._iter_break_from_left_to_right():
            if sub_tree == other:
                return remainder
        for remainder, sub_tree in other._iter_break_from_left_to_right():
            if sub_tree == self:
                if not remainder.has_inverse:
                    raise ValueError(
                        "The shortcut cannot be computed since 'other' "
                        "includes a non-invertible component")
                return remainder.inverted()
        # if we have got this far, then there was no shortcut possible
        if other.has_inverse:
            return self + other.inverted()
        else:
            raise ValueError('It is not possible to compute transA - transB '
                             'since transB cannot be inverted and there is no '
                             'shortcut possible.')

    def __array__(self, *args, **kwargs):
        """Array interface to get at this Transform's affine matrix."""
        return self.get_affine().get_matrix()

    def transform(self, values):
        """
        Apply this transformation on the given array of *values*.

        Parameters
        ----------
        values : array-like
            The input values as an array of length :attr:`input_dims` or
            shape (N, :attr:`input_dims`).

        Returns
        -------
        array
            The output values as an array of length :attr:`output_dims` or
            shape (N, :attr:`output_dims`), depending on the input.
        """
        # Ensure that values is a 2d array (but remember whether
        # we started with a 1d or 2d array).
        values = np.asanyarray(values)
        ndim = values.ndim
        values = values.reshape((-1, self.input_dims))

        # Transform the values
        res = self.transform_affine(self.transform_non_affine(values))

        # Convert the result back to the shape of the input values.
        if ndim == 0:
            assert not np.ma.is_masked(res)  # just to be on the safe side
            return res[0, 0]
        if ndim == 1:
            return res.reshape(-1)
        elif ndim == 2:
            return res
        raise ValueError(
            "Input values must have shape (N, {dims}) or ({dims},)"
            .format(dims=self.input_dims))

    def transform_affine(self, values):
        """
        Apply only the affine part of this transformation on the
        given array of values.

        ``transform(values)`` is always equivalent to
        ``transform_affine(transform_non_affine(values))``.

        In non-affine transformations, this is generally a no-op.  In
        affine transformations, this is equivalent to
        ``transform(values)``.

        Parameters
        ----------
        values : array
            The input values as an array of length :attr:`input_dims` or
            shape (N, :attr:`input_dims`).

        Returns
        -------
        array
            The output values as an array of length :attr:`output_dims` or
            shape (N, :attr:`output_dims`), depending on the input.
        """
        return self.get_affine().transform(values)

    def transform_non_affine(self, values):
        """
        Apply only the non-affine part of this transformation.

        ``transform(values)`` is always equivalent to
        ``transform_affine(transform_non_affine(values))``.

        In non-affine transformations, this is generally equivalent to
        ``transform(values)``.  In affine transformations, this is
        always a no-op.

        Parameters
        ----------
        values : array
            The input values as an array of length :attr:`input_dims` or
            shape (N, :attr:`input_dims`).

        Returns
        -------
        array
            The output values as an array of length :attr:`output_dims` or
            shape (N, :attr:`output_dims`), depending on the input.
        """
        return values

    def transform_bbox(self, bbox):
        """
        Transform the given bounding box.

        For smarter transforms including caching (a common requirement in
        Matplotlib), see `TransformedBbox`.
        """
        return Bbox(self.transform(bbox.get_points()))

    def get_affine(self):
        """Get the affine part of this transform."""
        return IdentityTransform()

    def get_matrix(self):
        """Get the matrix for the affine part of this transform."""
        return self.get_affine().get_matrix()

    def transform_point(self, point):
        """
        Return a transformed point.

        This function is only kept for backcompatibility; the more general
        `.transform` method is capable of transforming both a list of points
        and a single point.

        The point is given as a sequence of length :attr:`input_dims`.
        The transformed point is returned as a sequence of length
        :attr:`output_dims`.
        """
        if len(point) != self.input_dims:
            raise ValueError("The length of 'point' must be 'self.input_dims'")
        return self.transform(point)

    def transform_path(self, path):
        """
        Apply the transform to `.Path` *path*, returning a new `.Path`.

        In some cases, this transform may insert curves into the path
        that began as line segments.
        """
        return self.transform_path_affine(self.transform_path_non_affine(path))

    def transform_path_affine(self, path):
        """
        Apply the affine part of this transform to `.Path` *path*, returning a
        new `.Path`.

        ``transform_path(path)`` is equivalent to
        ``transform_path_affine(transform_path_non_affine(values))``.
        """
        return self.get_affine().transform_path_affine(path)

    def transform_path_non_affine(self, path):
        """
        Apply the non-affine part of this transform to `.Path` *path*,
        returning a new `.Path`.

        ``transform_path(path)`` is equivalent to
        ``transform_path_affine(transform_path_non_affine(values))``.
        """
        x = self.transform_non_affine(path.vertices)
        return Path._fast_from_codes_and_verts(x, path.codes, path)

    def transform_angles(self, angles, pts, radians=False, pushoff=1e-5):
        """
        Transform a set of angles anchored at specific locations.

        Parameters
        ----------
        angles : (N,) array-like
            The angles to transform.
        pts : (N, 2) array-like
            The points where the angles are anchored.
        radians : bool, default: False
            Whether *angles* are radians or degrees.
        pushoff : float
            For each point in *pts* and angle in *angles*, the transformed
            angle is computed by transforming a segment of length *pushoff*
            starting at that point and making that angle relative to the
            horizontal axis, and measuring the angle between the horizontal
            axis and the transformed segment.

        Returns
        -------
        (N,) array
        """
        # Must be 2D
        if self.input_dims != 2 or self.output_dims != 2:
            raise NotImplementedError('Only defined in 2D')
        angles = np.asarray(angles)
        pts = np.asarray(pts)
        _api.check_shape((None, 2), pts=pts)
        _api.check_shape((None,), angles=angles)
        if len(angles) != len(pts):
            raise ValueError("There must be as many 'angles' as 'pts'")
        # Convert to radians if desired
        if not radians:
            angles = np.deg2rad(angles)
        # Move a short distance away
        pts2 = pts + pushoff * np.column_stack([np.cos(angles),
                                                np.sin(angles)])
        # Transform both sets of points
        tpts = self.transform(pts)
        tpts2 = self.transform(pts2)
        # Calculate transformed angles
        d = tpts2 - tpts
        a = np.arctan2(d[:, 1], d[:, 0])
        # Convert back to degrees if desired
        if not radians:
            a = np.rad2deg(a)
        return a

    def inverted(self):
        """
        Return the corresponding inverse transformation.

        It holds ``x == self.inverted().transform(self.transform(x))``.

        The return value of this method should be treated as
        temporary.  An update to *self* does not cause a corresponding
        update to its inverted copy.
        """
        raise NotImplementedError()


class TransformWrapper(Transform):
    """
    A helper class that holds a single child transform and acts
    equivalently to it.

    This is useful if a node of the transform tree must be replaced at
    run time with a transform of a different type.  This class allows
    that replacement to correctly trigger invalidation.

    `TransformWrapper` instances must have the same input and output dimensions
    during their entire lifetime, so the child transform may only be replaced
    with another child transform of the same dimensions.
    """

    pass_through = True

    def __init__(self, child):
        """
        *child*: A `Transform` instance.  This child may later
        be replaced with :meth:`set`.
        """
        _api.check_isinstance(Transform, child=child)
        super().__init__()
        self.set(child)

    def __eq__(self, other):
        return self._child.__eq__(other)

    __str__ = _make_str_method("_child")

    def frozen(self):
        # docstring inherited
        return self._child.frozen()

    def set(self, child):
        """
        Replace the current child of this transform with another one.

        The new child must have the same number of input and output
        dimensions as the current child.
        """
        if hasattr(self, "_child"):  # Absent during init.
            self.invalidate()
            new_dims = (child.input_dims, child.output_dims)
            old_dims = (self._child.input_dims, self._child.output_dims)
            if new_dims != old_dims:
                raise ValueError(
                    f"The input and output dims of the new child {new_dims} "
                    f"do not match those of current child {old_dims}")
            self._child._parents.pop(id(self), None)

        self._child = child
        self.set_children(child)

        self.transform = child.transform
        self.transform_affine = child.transform_affine
        self.transform_non_affine = child.transform_non_affine
        self.transform_path = child.transform_path
        self.transform_path_affine = child.transform_path_affine
        self.transform_path_non_affine = child.transform_path_non_affine
        self.get_affine = child.get_affine
        self.inverted = child.inverted
        self.get_matrix = child.get_matrix
        # note we do not wrap other properties here since the transform's
        # child can be changed with WrappedTransform.set and so checking
        # is_affine and other such properties may be dangerous.

        self._invalid = 0
        self.invalidate()
        self._invalid = 0

    input_dims = property(lambda self: self._child.input_dims)
    output_dims = property(lambda self: self._child.output_dims)
    is_affine = property(lambda self: self._child.is_affine)
    is_separable = property(lambda self: self._child.is_separable)
    has_inverse = property(lambda self: self._child.has_inverse)


class AffineBase(Transform):
    """
    The base class of all affine transformations of any number of dimensions.
    """
    is_affine = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._inverted = None

    def __array__(self, *args, **kwargs):
        # optimises the access of the transform matrix vs. the superclass
        return self.get_matrix()

    def __eq__(self, other):
        if getattr(other, "is_affine", False) and hasattr(other, "get_matrix"):
            return (self.get_matrix() == other.get_matrix()).all()
        return NotImplemented

    def transform(self, values):
        # docstring inherited
        return self.transform_affine(values)

    def transform_affine(self, values):
        # docstring inherited
        raise NotImplementedError('Affine subclasses should override this '
                                  'method.')

    def transform_non_affine(self, values):
        # docstring inherited
        return values

    def transform_path(self, path):
        # docstring inherited
        return self.transform_path_affine(path)

    def transform_path_affine(self, path):
        # docstring inherited
        return Path(self.transform_affine(path.vertices),
                    path.codes, path._interpolation_steps)

    def transform_path_non_affine(self, path):
        # docstring inherited
        return path

    def get_affine(self):
        # docstring inherited
        return self


class Affine2DBase(AffineBase):
    """
    The base class of all 2D affine transformations.

    2D affine transformations are performed using a 3x3 numpy array::

        a c e
        b d f
        0 0 1

    This class provides the read-only interface.  For a mutable 2D
    affine transformation, use `Affine2D`.

    Subclasses of this class will generally only need to override a
    constructor and `~.Transform.get_matrix` that generates a custom 3x3 matrix.
    """
    input_dims = 2
    output_dims = 2

    def frozen(self):
        # docstring inherited
        return Affine2D(self.get_matrix().copy())

    @property
    def is_separable(self):
        mtx = self.get_matrix()
        return mtx[0, 1] == mtx[1, 0] == 0.0

    def to_values(self):
        """
        Return the values of the matrix as an ``(a, b, c, d, e, f)`` tuple.
        """
        mtx = self.get_matrix()
        return tuple(mtx[:2].swapaxes(0, 1).flat)

    def transform_affine(self, values):
        mtx = self.get_matrix()
        if isinstance(values, np.ma.MaskedArray):
            tpoints = affine_transform(values.data, mtx)
            return np.ma.MaskedArray(tpoints, mask=np.ma.getmask(values))
        return affine_transform(values, mtx)

    if DEBUG:
        _transform_affine = transform_affine

        def transform_affine(self, values):
            # docstring inherited
            # The major speed trap here is just converting to the
            # points to an array in the first place.  If we can use
            # more arrays upstream, that should help here.
            if not isinstance(values, np.ndarray):
                _api.warn_external(
                    f'A non-numpy array of type {type(values)} was passed in '
                    f'for transformation, which results in poor performance.')
            return self._transform_affine(values)

    def inverted(self):
        # docstring inherited
        if self._inverted is None or self._invalid:
            mtx = self.get_matrix()
            shorthand_name = None
            if self._shorthand_name:
                shorthand_name = '(%s)-1' % self._shorthand_name
            self._inverted = Affine2D(inv(mtx), shorthand_name=shorthand_name)
            self._invalid = 0
        return self._inverted


class Affine2D(Affine2DBase):
    """
    A mutable 2D affine transformation.
    """

    def __init__(self, matrix=None, **kwargs):
        """
        Initialize an Affine transform from a 3x3 numpy float array::

          a c e
          b d f
          0 0 1

        If *matrix* is None, initialize with the identity transform.
        """
        super().__init__(**kwargs)
        if matrix is None:
            # A bit faster than np.identity(3).
            matrix = IdentityTransform._mtx
        self._mtx = matrix.copy()
        self._invalid = 0

    _base_str = _make_str_method("_mtx")

    def __str__(self):
        return (self._base_str()
                if (self._mtx != np.diag(np.diag(self._mtx))).any()
                else f"Affine2D().scale({self._mtx[0, 0]}, {self._mtx[1, 1]})"
                if self._mtx[0, 0] != self._mtx[1, 1]
                else f"Affine2D().scale({self._mtx[0, 0]})")

    @staticmethod
    def from_values(a, b, c, d, e, f):
        """
        Create a new Affine2D instance from the given values::

          a c e
          b d f
          0 0 1

        .
        """
        return Affine2D(
            np.array([a, c, e, b, d, f, 0.0, 0.0, 1.0], float).reshape((3, 3)))

    def get_matrix(self):
        """
        Get the underlying transformation matrix as a 3x3 array::

          a c e
          b d f
          0 0 1

        .
        """
        if self._invalid:
            self._inverted = None
            self._invalid = 0
        return self._mtx

    def set_matrix(self, mtx):
        """
        Set the underlying transformation matrix from a 3x3 array::

          a c e
          b d f
          0 0 1

        .
        """
        self._mtx = mtx
        self.invalidate()

    def set(self, other):
        """
        Set this transformation from the frozen copy of another
        `Affine2DBase` object.
        """
        _api.check_isinstance(Affine2DBase, other=other)
        self._mtx = other.get_matrix()
        self.invalidate()

    def clear(self):
        """
        Reset the underlying matrix to the identity transform.
        """
        # A bit faster than np.identity(3).
        self._mtx = IdentityTransform._mtx.copy()
        self.invalidate()
        return self

    def rotate(self, theta):
        """
        Add a rotation (in radians) to this transform in place.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        a = math.cos(theta)
        b = math.sin(theta)
        mtx = self._mtx
        # Operating and assigning one scalar at a time is much faster.
        (xx, xy, x0), (yx, yy, y0), _ = mtx.tolist()
        # mtx = [[a -b 0], [b a 0], [0 0 1]] * mtx
        mtx[0, 0] = a * xx - b * yx
        mtx[0, 1] = a * xy - b * yy
        mtx[0, 2] = a * x0 - b * y0
        mtx[1, 0] = b * xx + a * yx
        mtx[1, 1] = b * xy + a * yy
        mtx[1, 2] = b * x0 + a * y0
        self.invalidate()
        return self

    def rotate_deg(self, degrees):
        """
        Add a rotation (in degrees) to this transform in place.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        return self.rotate(math.radians(degrees))

    def rotate_around(self, x, y, theta):
        """
        Add a rotation (in radians) around the point (x, y) in place.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        return self.translate(-x, -y).rotate(theta).translate(x, y)

    def rotate_deg_around(self, x, y, degrees):
        """
        Add a rotation (in degrees) around the point (x, y) in place.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        # Cast to float to avoid wraparound issues with uint8's
        x, y = float(x), float(y)
        return self.translate(-x, -y).rotate_deg(degrees).translate(x, y)

    def translate(self, tx, ty):
        """
        Add a translation in place.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        self._mtx[0, 2] += tx
        self._mtx[1, 2] += ty
        self.invalidate()
        return self

    def scale(self, sx, sy=None):
        """
        Add a scale in place.

        If *sy* is None, the same scale is applied in both the *x*- and
        *y*-directions.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        if sy is None:
            sy = sx
        # explicit element-wise scaling is fastest
        self._mtx[0, 0] *= sx
        self._mtx[0, 1] *= sx
        self._mtx[0, 2] *= sx
        self._mtx[1, 0] *= sy
        self._mtx[1, 1] *= sy
        self._mtx[1, 2] *= sy
        self.invalidate()
        return self

    def skew(self, xShear, yShear):
        """
        Add a skew in place.

        *xShear* and *yShear* are the shear angles along the *x*- and
        *y*-axes, respectively, in radians.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        rx = math.tan(xShear)
        ry = math.tan(yShear)
        mtx = self._mtx
        # Operating and assigning one scalar at a time is much faster.
        (xx, xy, x0), (yx, yy, y0), _ = mtx.tolist()
        # mtx = [[1 rx 0], [ry 1 0], [0 0 1]] * mtx
        mtx[0, 0] += rx * yx
        mtx[0, 1] += rx * yy
        mtx[0, 2] += rx * y0
        mtx[1, 0] += ry * xx
        mtx[1, 1] += ry * xy
        mtx[1, 2] += ry * x0
        self.invalidate()
        return self

    def skew_deg(self, xShear, yShear):
        """
        Add a skew in place.

        *xShear* and *yShear* are the shear angles along the *x*- and
        *y*-axes, respectively, in degrees.

        Returns *self*, so this method can easily be chained with more
        calls to :meth:`rotate`, :meth:`rotate_deg`, :meth:`translate`
        and :meth:`scale`.
        """
        return self.skew(math.radians(xShear), math.radians(yShear))


class IdentityTransform(Affine2DBase):
    """
    A special class that does one thing, the identity transform, in a
    fast way.
    """
    _mtx = np.identity(3)

    def frozen(self):
        # docstring inherited
        return self

    __str__ = _make_str_method()

    def get_matrix(self):
        # docstring inherited
        return self._mtx

    def transform(self, values):
        # docstring inherited
        return np.asanyarray(values)

    def transform_affine(self, values):
        # docstring inherited
        return np.asanyarray(values)

    def transform_non_affine(self, values):
        # docstring inherited
        return np.asanyarray(values)

    def transform_path(self, path):
        # docstring inherited
        return path

    def transform_path_affine(self, path):
        # docstring inherited
        return path

    def transform_path_non_affine(self, path):
        # docstring inherited
        return path

    def get_affine(self):
        # docstring inherited
        return self

    def inverted(self):
        # docstring inherited
        return self


class _BlendedMixin:
    """Common methods for `BlendedGenericTransform` and `BlendedAffine2D`."""

    def __eq__(self, other):
        if isinstance(other, (BlendedAffine2D, BlendedGenericTransform)):
            return (self._x == other._x) and (self._y == other._y)
        elif self._x == self._y:
            return self._x == other
        else:
            return NotImplemented

    def contains_branch_seperately(self, transform):
        return (self._x.contains_branch(transform),
                self._y.contains_branch(transform))

    __str__ = _make_str_method("_x", "_y")


class BlendedGenericTransform(_BlendedMixin, Transform):
    """
    A "blended" transform uses one transform for the *x*-direction, and
    another transform for the *y*-direction.

    This "generic" version can handle any given child transform in the
    *x*- and *y*-directions.
    """
    input_dims = 2
    output_dims = 2
    is_separable = True
    pass_through = True

    def __init__(self, x_transform, y_transform, **kwargs):
        """
        Create a new "blended" transform using *x_transform* to transform the
        *x*-axis and *y_transform* to transform the *y*-axis.

        You will generally not call this constructor directly but use the
        `blended_transform_factory` function instead, which can determine
        automatically which kind of blended transform to create.
        """
        Transform.__init__(self, **kwargs)
        self._x = x_transform
        self._y = y_transform
        self.set_children(x_transform, y_transform)
        self._affine = None

    @property
    def depth(self):
        return max(self._x.depth, self._y.depth)

    def contains_branch(self, other):
        # A blended transform cannot possibly contain a branch from two
        # different transforms.
        return False

    is_affine = property(lambda self: self._x.is_affine and self._y.is_affine)
    has_inverse = property(
        lambda self: self._x.has_inverse and self._y.has_inverse)

    def frozen(self):
        # docstring inherited
        return blended_transform_factory(self._x.frozen(), self._y.frozen())

    def transform_non_affine(self, values):
        # docstring inherited
        if self._x.is_affine and self._y.is_affine:
            return values
        x = self._x
        y = self._y

        if x == y and x.input_dims == 2:
            return x.transform_non_affine(values)

        if x.input_dims == 2:
            x_points = x.transform_non_affine(values)[:, 0:1]
        else:
            x_points = x.transform_non_affine(values[:, 0])
            x_points = x_points.reshape((len(x_points), 1))

        if y.input_dims == 2:
            y_points = y.transform_non_affine(values)[:, 1:]
        else:
            y_points = y.transform_non_affine(values[:, 1])
            y_points = y_points.reshape((len(y_points), 1))

        if (isinstance(x_points, np.ma.MaskedArray) or
                isinstance(y_points, np.ma.MaskedArray)):
            return np.ma.concatenate((x_points, y_points), 1)
        else:
            return np.concatenate((x_points, y_points), 1)

    def inverted(self):
        # docstring inherited
        return BlendedGenericTransform(self._x.inverted(), self._y.inverted())

    def get_affine(self):
        # docstring inherited
        if self._invalid or self._affine is None:
            if self._x == self._y:
                self._affine = self._x.get_affine()
            else:
                x_mtx = self._x.get_affine().get_matrix()
                y_mtx = self._y.get_affine().get_matrix()
                # We already know the transforms are separable, so we can skip
                # setting b and c to zero.
                mtx = np.array([x_mtx[0], y_mtx[1], [0.0, 0.0, 1.0]])
                self._affine = Affine2D(mtx)
            self._invalid = 0
        return self._affine


class BlendedAffine2D(_BlendedMixin, Affine2DBase):
    """
    A "blended" transform uses one transform for the *x*-direction, and
    another transform for the *y*-direction.

    This version is an optimization for the case where both child
    transforms are of type `Affine2DBase`.
    """

    is_separable = True

    def __init__(self, x_transform, y_transform, **kwargs):
        """
        Create a new "blended" transform using *x_transform* to transform the
        *x*-axis and *y_transform* to transform the *y*-axis.

        Both *x_transform* and *y_transform* must be 2D affine transforms.

        You will generally not call this constructor directly but use the
        `blended_transform_factory` function instead, which can determine
        automatically which kind of blended transform to create.
        """
        is_affine = x_transform.is_affine and y_transform.is_affine
        is_separable = x_transform.is_separable and y_transform.is_separable
        is_correct = is_affine and is_separable
        if not is_correct:
            raise ValueError("Both *x_transform* and *y_transform* must be 2D "
                             "affine transforms")

        Transform.__init__(self, **kwargs)
        self._x = x_transform
        self._y = y_transform
        self.set_children(x_transform, y_transform)

        Affine2DBase.__init__(self)
        self._mtx = None

    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            if self._x == self._y:
                self._mtx = self._x.get_matrix()
            else:
                x_mtx = self._x.get_matrix()
                y_mtx = self._y.get_matrix()
                # We already know the transforms are separable, so we can skip
                # setting b and c to zero.
                self._mtx = np.array([x_mtx[0], y_mtx[1], [0.0, 0.0, 1.0]])
            self._inverted = None
            self._invalid = 0
        return self._mtx


def blended_transform_factory(x_transform, y_transform):
    """
    Create a new "blended" transform using *x_transform* to transform
    the *x*-axis and *y_transform* to transform the *y*-axis.

    A faster version of the blended transform is returned for the case
    where both child transforms are affine.
    """
    if (isinstance(x_transform, Affine2DBase) and
            isinstance(y_transform, Affine2DBase)):
        return BlendedAffine2D(x_transform, y_transform)
    return BlendedGenericTransform(x_transform, y_transform)


class CompositeGenericTransform(Transform):
    """
    A composite transform formed by applying transform *a* then
    transform *b*.

    This "generic" version can handle any two arbitrary
    transformations.
    """
    pass_through = True

    def __init__(self, a, b, **kwargs):
        """
        Create a new composite transform that is the result of
        applying transform *a* then transform *b*.

        You will generally not call this constructor directly but write ``a +
        b`` instead, which will automatically choose the best kind of composite
        transform instance to create.
        """
        if a.output_dims != b.input_dims:
            raise ValueError("The output dimension of 'a' must be equal to "
                             "the input dimensions of 'b'")
        self.input_dims = a.input_dims
        self.output_dims = b.output_dims

        super().__init__(**kwargs)
        self._a = a
        self._b = b
        self.set_children(a, b)

    def frozen(self):
        # docstring inherited
        self._invalid = 0
        frozen = composite_transform_factory(
            self._a.frozen(), self._b.frozen())
        if not isinstance(frozen, CompositeGenericTransform):
            return frozen.frozen()
        return frozen

    def _invalidate_internal(self, level, invalidating_node):
        # When the left child is invalidated at AFFINE_ONLY level and the right child is
        # non-affine, the composite transform is FULLY invalidated.
        if invalidating_node is self._a and not self._b.is_affine:
            level = Transform._INVALID_FULL
        super()._invalidate_internal(level, invalidating_node)

    def __eq__(self, other):
        if isinstance(other, (CompositeGenericTransform, CompositeAffine2D)):
            return self is other or (self._a == other._a
                                     and self._b == other._b)
        else:
            return False

    def _iter_break_from_left_to_right(self):
        for left, right in self._a._iter_break_from_left_to_right():
            yield left, right + self._b
        for left, right in self._b._iter_break_from_left_to_right():
            yield self._a + left, right

    def contains_branch_seperately(self, other_transform):
        # docstring inherited
        if self.output_dims != 2:
            raise ValueError('contains_branch_seperately only supports '
                             'transforms with 2 output dimensions')
        if self == other_transform:
            return (True, True)
        return self._b.contains_branch_seperately(other_transform)

    depth = property(lambda self: self._a.depth + self._b.depth)
    is_affine = property(lambda self: self._a.is_affine and self._b.is_affine)
    is_separable = property(
        lambda self: self._a.is_separable and self._b.is_separable)
    has_inverse = property(
        lambda self: self._a.has_inverse and self._b.has_inverse)

    __str__ = _make_str_method("_a", "_b")

    def transform_affine(self, values):
        # docstring inherited
        return self.get_affine().transform(values)

    def transform_non_affine(self, values):
        # docstring inherited
        if self._a.is_affine and self._b.is_affine:
            return values
        elif not self._a.is_affine and self._b.is_affine:
            return self._a.transform_non_affine(values)
        else:
            return self._b.transform_non_affine(self._a.transform(values))

    def transform_path_non_affine(self, path):
        # docstring inherited
        if self._a.is_affine and self._b.is_affine:
            return path
        elif not self._a.is_affine and self._b.is_affine:
            return self._a.transform_path_non_affine(path)
        else:
            return self._b.transform_path_non_affine(
                                    self._a.transform_path(path))

    def get_affine(self):
        # docstring inherited
        if not self._b.is_affine:
            return self._b.get_affine()
        else:
            return Affine2D(np.dot(self._b.get_affine().get_matrix(),
                                   self._a.get_affine().get_matrix()))

    def inverted(self):
        # docstring inherited
        return CompositeGenericTransform(
            self._b.inverted(), self._a.inverted())


class CompositeAffine2D(Affine2DBase):
    """
    A composite transform formed by applying transform *a* then transform *b*.

    This version is an optimization that handles the case where both *a*
    and *b* are 2D affines.
    """
    def __init__(self, a, b, **kwargs):
        """
        Create a new composite transform that is the result of
        applying `Affine2DBase` *a* then `Affine2DBase` *b*.

        You will generally not call this constructor directly but write ``a +
        b`` instead, which will automatically choose the best kind of composite
        transform instance to create.
        """
        if not a.is_affine or not b.is_affine:
            raise ValueError("'a' and 'b' must be affine transforms")
        if a.output_dims != b.input_dims:
            raise ValueError("The output dimension of 'a' must be equal to "
                             "the input dimensions of 'b'")
        self.input_dims = a.input_dims
        self.output_dims = b.output_dims

        super().__init__(**kwargs)
        self._a = a
        self._b = b
        self.set_children(a, b)
        self._mtx = None

    @property
    def depth(self):
        return self._a.depth + self._b.depth

    def _iter_break_from_left_to_right(self):
        for left, right in self._a._iter_break_from_left_to_right():
            yield left, right + self._b
        for left, right in self._b._iter_break_from_left_to_right():
            yield self._a + left, right

    __str__ = _make_str_method("_a", "_b")

    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            self._mtx = np.dot(
                self._b.get_matrix(),
                self._a.get_matrix())
            self._inverted = None
            self._invalid = 0
        return self._mtx


def composite_transform_factory(a, b):
    """
    Create a new composite transform that is the result of applying
    transform a then transform b.

    Shortcut versions of the blended transform are provided for the
    case where both child transforms are affine, or one or the other
    is the identity transform.

    Composite transforms may also be created using the '+' operator,
    e.g.::

      c = a + b
    """
    # check to see if any of a or b are IdentityTransforms. We use
    # isinstance here to guarantee that the transforms will *always*
    # be IdentityTransforms. Since TransformWrappers are mutable,
    # use of equality here would be wrong.
    if isinstance(a, IdentityTransform):
        return b
    elif isinstance(b, IdentityTransform):
        return a
    elif isinstance(a, Affine2D) and isinstance(b, Affine2D):
        return CompositeAffine2D(a, b)
    return CompositeGenericTransform(a, b)


class BboxTransform(Affine2DBase):
    """
    `BboxTransform` linearly transforms points from one `Bbox` to another.
    """

    is_separable = True

    def __init__(self, boxin, boxout, **kwargs):
        """
        Create a new `BboxTransform` that linearly transforms
        points from *boxin* to *boxout*.
        """
        _api.check_isinstance(BboxBase, boxin=boxin, boxout=boxout)

        super().__init__(**kwargs)
        self._boxin = boxin
        self._boxout = boxout
        self.set_children(boxin, boxout)
        self._mtx = None
        self._inverted = None

    __str__ = _make_str_method("_boxin", "_boxout")

    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            inl, inb, inw, inh = self._boxin.bounds
            outl, outb, outw, outh = self._boxout.bounds
            x_scale = outw / inw
            y_scale = outh / inh
            if DEBUG and (x_scale == 0 or y_scale == 0):
                raise ValueError(
                    "Transforming from or to a singular bounding box")
            self._mtx = np.array([[x_scale,     0.0, -inl*x_scale+outl],
                                  [    0.0, y_scale, -inb*y_scale+outb],
                                  [    0.0,     0.0,               1.0]],
                                 float)
            self._inverted = None
            self._invalid = 0
        return self._mtx


class BboxTransformTo(Affine2DBase):
    """
    `BboxTransformTo` is a transformation that linearly transforms points from
    the unit bounding box to a given `Bbox`.
    """

    is_separable = True

    def __init__(self, boxout, **kwargs):
        """
        Create a new `BboxTransformTo` that linearly transforms
        points from the unit bounding box to *boxout*.
        """
        _api.check_isinstance(BboxBase, boxout=boxout)

        super().__init__(**kwargs)
        self._boxout = boxout
        self.set_children(boxout)
        self._mtx = None
        self._inverted = None

    __str__ = _make_str_method("_boxout")

    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            outl, outb, outw, outh = self._boxout.bounds
            if DEBUG and (outw == 0 or outh == 0):
                raise ValueError("Transforming to a singular bounding box.")
            self._mtx = np.array([[outw,  0.0, outl],
                                  [ 0.0, outh, outb],
                                  [ 0.0,  0.0,  1.0]],
                                 float)
            self._inverted = None
            self._invalid = 0
        return self._mtx


@_api.deprecated("3.9")
class BboxTransformToMaxOnly(BboxTransformTo):
    """
    `BboxTransformToMaxOnly` is a transformation that linearly transforms points from
    the unit bounding box to a given `Bbox` with a fixed upper left of (0, 0).
    """
    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            xmax, ymax = self._boxout.max
            if DEBUG and (xmax == 0 or ymax == 0):
                raise ValueError("Transforming to a singular bounding box.")
            self._mtx = np.array([[xmax,  0.0, 0.0],
                                  [ 0.0, ymax, 0.0],
                                  [ 0.0,  0.0, 1.0]],
                                 float)
            self._inverted = None
            self._invalid = 0
        return self._mtx


class BboxTransformFrom(Affine2DBase):
    """
    `BboxTransformFrom` linearly transforms points from a given `Bbox` to the
    unit bounding box.
    """
    is_separable = True

    def __init__(self, boxin, **kwargs):
        _api.check_isinstance(BboxBase, boxin=boxin)

        super().__init__(**kwargs)
        self._boxin = boxin
        self.set_children(boxin)
        self._mtx = None
        self._inverted = None

    __str__ = _make_str_method("_boxin")

    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            inl, inb, inw, inh = self._boxin.bounds
            if DEBUG and (inw == 0 or inh == 0):
                raise ValueError("Transforming from a singular bounding box.")
            x_scale = 1.0 / inw
            y_scale = 1.0 / inh
            self._mtx = np.array([[x_scale,     0.0, -inl*x_scale],
                                  [    0.0, y_scale, -inb*y_scale],
                                  [    0.0,     0.0,          1.0]],
                                 float)
            self._inverted = None
            self._invalid = 0
        return self._mtx


class ScaledTranslation(Affine2DBase):
    """
    A transformation that translates by *xt* and *yt*, after *xt* and *yt*
    have been transformed by *scale_trans*.
    """
    def __init__(self, xt, yt, scale_trans, **kwargs):
        super().__init__(**kwargs)
        self._t = (xt, yt)
        self._scale_trans = scale_trans
        self.set_children(scale_trans)
        self._mtx = None
        self._inverted = None

    __str__ = _make_str_method("_t")

    def get_matrix(self):
        # docstring inherited
        if self._invalid:
            # A bit faster than np.identity(3).
            self._mtx = IdentityTransform._mtx.copy()
            self._mtx[:2, 2] = self._scale_trans.transform(self._t)
            self._invalid = 0
            self._inverted = None
        return self._mtx


class _ScaledRotation(Affine2DBase):
    """
    A transformation that applies rotation by *theta*, after transform by *trans_shift*.
    """
    def __init__(self, theta, trans_shift):
        super().__init__()
        self._theta = theta
        self._trans_shift = trans_shift
        self._mtx = None

    def get_matrix(self):
        if self._invalid:
            transformed_coords = self._trans_shift.transform([[self._theta, 0]])[0]
            adjusted_theta = transformed_coords[0]
            rotation = Affine2D().rotate(adjusted_theta)
            self._mtx = rotation.get_matrix()
        return self._mtx


class AffineDeltaTransform(Affine2DBase):
    r"""
    A transform wrapper for transforming displacements between pairs of points.

    This class is intended to be used to transform displacements ("position
    deltas") between pairs of points (e.g., as the ``offset_transform``
    of `.Collection`\s): given a transform ``t`` such that ``t =
    AffineDeltaTransform(t) + offset``, ``AffineDeltaTransform``
    satisfies ``AffineDeltaTransform(a - b) == AffineDeltaTransform(a) -
    AffineDeltaTransform(b)``.

    This is implemented by forcing the offset components of the transform
    matrix to zero.

    This class is experimental as of 3.3, and the API may change.
    """

    pass_through = True

    def __init__(self, transform, **kwargs):
        super().__init__(**kwargs)
        self._base_transform = transform
        self.set_children(transform)

    __str__ = _make_str_method("_base_transform")

    def get_matrix(self):
        if self._invalid:
            self._mtx = self._base_transform.get_matrix().copy()
            self._mtx[:2, -1] = 0
        return self._mtx


class TransformedPath(TransformNode):
    """
    A `TransformedPath` caches a non-affine transformed copy of the
    `~.path.Path`.  This cached copy is automatically updated when the
    non-affine part of the transform changes.

    .. note::

        Paths are considered immutable by this class. Any update to the
        path's vertices/codes will not trigger a transform recomputation.

    """
    def __init__(self, path, transform):
        """
        Parameters
        ----------
        path : `~.path.Path`
        transform : `Transform`
        """
        _api.check_isinstance(Transform, transform=transform)
        super().__init__()
        self._path = path
        self._transform = transform
        self.set_children(transform)
        self._transformed_path = None
        self._transformed_points = None

    def _revalidate(self):
        # only recompute if the invalidation includes the non_affine part of
        # the transform
        if (self._invalid == self._INVALID_FULL
                or self._transformed_path is None):
            self._transformed_path = \
                self._transform.transform_path_non_affine(self._path)
            self._transformed_points = \
                Path._fast_from_codes_and_verts(
                    self._transform.transform_non_affine(self._path.vertices),
                    None, self._path)
        self._invalid = 0

    def get_transformed_points_and_affine(self):
        """
        Return a copy of the child path, with the non-affine part of
        the transform already applied, along with the affine part of
        the path necessary to complete the transformation.  Unlike
        :meth:`get_transformed_path_and_affine`, no interpolation will
        be performed.
        """
        self._revalidate()
        return self._transformed_points, self.get_affine()

    def get_transformed_path_and_affine(self):
        """
        Return a copy of the child path, with the non-affine part of
        the transform already applied, along with the affine part of
        the path necessary to complete the transformation.
        """
        self._revalidate()
        return self._transformed_path, self.get_affine()

    def get_fully_transformed_path(self):
        """
        Return a fully-transformed copy of the child path.
        """
        self._revalidate()
        return self._transform.transform_path_affine(self._transformed_path)

    def get_affine(self):
        return self._transform.get_affine()


class TransformedPatchPath(TransformedPath):
    """
    A `TransformedPatchPath` caches a non-affine transformed copy of the
    `~.patches.Patch`. This cached copy is automatically updated when the
    non-affine part of the transform or the patch changes.
    """

    def __init__(self, patch):
        """
        Parameters
        ----------
        patch : `~.patches.Patch`
        """
        # Defer to TransformedPath.__init__.
        super().__init__(patch.get_path(), patch.get_transform())
        self._patch = patch

    def _revalidate(self):
        patch_path = self._patch.get_path()
        # Force invalidation if the patch path changed; otherwise, let base
        # class check invalidation.
        if patch_path != self._path:
            self._path = patch_path
            self._transformed_path = None
        super()._revalidate()


def nonsingular(vmin, vmax, expander=0.001, tiny=1e-15, increasing=True):
    """
    Modify the endpoints of a range as needed to avoid singularities.

    Parameters
    ----------
    vmin, vmax : float
        The initial endpoints.
    expander : float, default: 0.001
        Fractional amount by which *vmin* and *vmax* are expanded if
        the original interval is too small, based on *tiny*.
    tiny : float, default: 1e-15
        Threshold for the ratio of the interval to the maximum absolute
        value of its endpoints.  If the interval is smaller than
        this, it will be expanded.  This value should be around
        1e-15 or larger; otherwise the interval will be approaching
        the double precision resolution limit.
    increasing : bool, default: True
        If True, swap *vmin*, *vmax* if *vmin* > *vmax*.

    Returns
    -------
    vmin, vmax : float
        Endpoints, expanded and/or swapped if necessary.
        If either input is inf or NaN, or if both inputs are 0 or very
        close to zero, it returns -*expander*, *expander*.
    """

    if (not np.isfinite(vmin)) or (not np.isfinite(vmax)):
        return -expander, expander

    swapped = False
    if vmax < vmin:
        vmin, vmax = vmax, vmin
        swapped = True

    # Expand vmin, vmax to float: if they were integer types, they can wrap
    # around in abs (abs(np.int8(-128)) == -128) and vmax - vmin can overflow.
    vmin, vmax = map(float, [vmin, vmax])

    maxabsvalue = max(abs(vmin), abs(vmax))
    if maxabsvalue < (1e6 / tiny) * np.finfo(float).tiny:
        vmin = -expander
        vmax = expander

    elif vmax - vmin <= maxabsvalue * tiny:
        if vmax == 0 and vmin == 0:
            vmin = -expander
            vmax = expander
        else:
            vmin -= expander*abs(vmin)
            vmax += expander*abs(vmax)

    if swapped and not increasing:
        vmin, vmax = vmax, vmin
    return vmin, vmax


def interval_contains(interval, val):
    """
    Check, inclusively, whether an interval includes a given value.

    Parameters
    ----------
    interval : (float, float)
        The endpoints of the interval.
    val : float
        Value to check is within interval.

    Returns
    -------
    bool
        Whether *val* is within the *interval*.
    """
    a, b = interval
    if a > b:
        a, b = b, a
    return a <= val <= b


def _interval_contains_close(interval, val, rtol=1e-10):
    """
    Check, inclusively, whether an interval includes a given value, with the
    interval expanded by a small tolerance to admit floating point errors.

    Parameters
    ----------
    interval : (float, float)
        The endpoints of the interval.
    val : float
        Value to check is within interval.
    rtol : float, default: 1e-10
        Relative tolerance slippage allowed outside of the interval.
        For an interval ``[a, b]``, values
        ``a - rtol * (b - a) <= val <= b + rtol * (b - a)`` are considered
        inside the interval.

    Returns
    -------
    bool
        Whether *val* is within the *interval* (with tolerance).
    """
    a, b = interval
    if a > b:
        a, b = b, a
    rtol = (b - a) * rtol
    return a - rtol <= val <= b + rtol


def interval_contains_open(interval, val):
    """
    Check, excluding endpoints, whether an interval includes a given value.

    Parameters
    ----------
    interval : (float, float)
        The endpoints of the interval.
    val : float
        Value to check is within interval.

    Returns
    -------
    bool
        Whether *val* is within the *interval*.
    """
    a, b = interval
    return a < val < b or a > val > b


def offset_copy(trans, fig=None, x=0.0, y=0.0, units='inches'):
    """
    Return a new transform with an added offset.

    Parameters
    ----------
    trans : `Transform` subclass
        Any transform, to which offset will be applied.
    fig : `~matplotlib.figure.Figure`, default: None
        Current figure. It can be None if *units* are 'dots'.
    x, y : float, default: 0.0
        The offset to apply.
    units : {'inches', 'points', 'dots'}, default: 'inches'
        Units of the offset.

    Returns
    -------
    `Transform` subclass
        Transform with applied offset.
    """
    _api.check_in_list(['dots', 'points', 'inches'], units=units)
    if units == 'dots':
        return trans + Affine2D().translate(x, y)
    if fig is None:
        raise ValueError('For units of inches or points a fig kwarg is needed')
    if units == 'points':
        x /= 72.0
        y /= 72.0
    # Default units are 'inches'
    return trans + ScaledTranslation(x, y, fig.dpi_scale_trans)
