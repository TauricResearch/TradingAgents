"""Routines for calculating bounding boxes, point in rectangle calculations and
so on.
"""

from fontTools.misc.roundTools import otRound
from fontTools.misc.vector import Vector as _Vector
import math
import warnings


def calcBounds(array):
    """Calculate the bounding rectangle of a 2D points array.

    Args:
        array: A sequence of 2D tuples.

    Returns:
        A four-item tuple representing the bounding rectangle ``(xMin, yMin, xMax, yMax)``.
    """
    if not array:
        return 0, 0, 0, 0
    xs = [x for x, y in array]
    ys = [y for x, y in array]
    return min(xs), min(ys), max(xs), max(ys)


def calcIntBounds(array, round=otRound):
    """Calculate the integer bounding rectangle of a 2D points array.

    Values are rounded to closest integer towards ``+Infinity`` using the
    :func:`fontTools.misc.fixedTools.otRound` function by default, unless
    an optional ``round`` function is passed.

    Args:
        array: A sequence of 2D tuples.
        round: A rounding function of type ``f(x: float) -> int``.

    Returns:
        A four-item tuple of integers representing the bounding rectangle:
        ``(xMin, yMin, xMax, yMax)``.
    """
    return tuple(round(v) for v in calcBounds(array))


def updateBounds(bounds, p, min=min, max=max):
    """Add a point to a bounding rectangle.

    Args:
        bounds: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax), or None``.
        p: A 2D tuple representing a point.
        min,max: functions to compute the minimum and maximum.

    Returns:
        The updated bounding rectangle ``(xMin, yMin, xMax, yMax)``.
    """
    (x, y) = p
    if bounds is None:
        return x, y, x, y
    xMin, yMin, xMax, yMax = bounds
    return min(xMin, x), min(yMin, y), max(xMax, x), max(yMax, y)


def pointInRect(p, rect):
    """Test if a point is inside a bounding rectangle.

    Args:
        p: A 2D tuple representing a point.
        rect: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax)``.

    Returns:
        ``True`` if the point is inside the rectangle, ``False`` otherwise.
    """
    (x, y) = p
    xMin, yMin, xMax, yMax = rect
    return (xMin <= x <= xMax) and (yMin <= y <= yMax)


def pointsInRect(array, rect):
    """Determine which points are inside a bounding rectangle.

    Args:
        array: A sequence of 2D tuples.
        rect: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax)``.

    Returns:
        A list containing the points inside the rectangle.
    """
    if len(array) < 1:
        return []
    xMin, yMin, xMax, yMax = rect
    return [(xMin <= x <= xMax) and (yMin <= y <= yMax) for x, y in array]


def vectorLength(vector):
    """Calculate the length of the given vector.

    Args:
        vector: A 2D tuple.

    Returns:
        The Euclidean length of the vector.
    """
    x, y = vector
    return math.sqrt(x**2 + y**2)


def asInt16(array):
    """Round a list of floats to 16-bit signed integers.

    Args:
        array: List of float values.

    Returns:
        A list of rounded integers.
    """
    return [int(math.floor(i + 0.5)) for i in array]


def normRect(rect):
    """Normalize a bounding box rectangle.

    This function "turns the rectangle the right way up", so that the following
    holds::

        xMin <= xMax and yMin <= yMax

    Args:
        rect: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax)``.

    Returns:
        A normalized bounding rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    return min(xMin, xMax), min(yMin, yMax), max(xMin, xMax), max(yMin, yMax)


def scaleRect(rect, x, y):
    """Scale a bounding box rectangle.

    Args:
        rect: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax)``.
        x: Factor to scale the rectangle along the X axis.
        Y: Factor to scale the rectangle along the Y axis.

    Returns:
        A scaled bounding rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    return xMin * x, yMin * y, xMax * x, yMax * y


def offsetRect(rect, dx, dy):
    """Offset a bounding box rectangle.

    Args:
        rect: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax)``.
        dx: Amount to offset the rectangle along the X axis.
        dY: Amount to offset the rectangle along the Y axis.

    Returns:
        An offset bounding rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    return xMin + dx, yMin + dy, xMax + dx, yMax + dy


def insetRect(rect, dx, dy):
    """Inset a bounding box rectangle on all sides.

    Args:
        rect: A bounding rectangle expressed as a tuple
            ``(xMin, yMin, xMax, yMax)``.
        dx: Amount to inset the rectangle along the X axis.
        dY: Amount to inset the rectangle along the Y axis.

    Returns:
        An inset bounding rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    return xMin + dx, yMin + dy, xMax - dx, yMax - dy


def sectRect(rect1, rect2):
    """Test for rectangle-rectangle intersection.

    Args:
        rect1: First bounding rectangle, expressed as tuples
            ``(xMin, yMin, xMax, yMax)``.
        rect2: Second bounding rectangle.

    Returns:
        A boolean and a rectangle.
        If the input rectangles intersect, returns ``True`` and the intersecting
        rectangle. Returns ``False`` and ``(0, 0, 0, 0)`` if the input
        rectangles don't intersect.
    """
    (xMin1, yMin1, xMax1, yMax1) = rect1
    (xMin2, yMin2, xMax2, yMax2) = rect2
    xMin, yMin, xMax, yMax = (
        max(xMin1, xMin2),
        max(yMin1, yMin2),
        min(xMax1, xMax2),
        min(yMax1, yMax2),
    )
    if xMin >= xMax or yMin >= yMax:
        return False, (0, 0, 0, 0)
    return True, (xMin, yMin, xMax, yMax)


def unionRect(rect1, rect2):
    """Determine union of bounding rectangles.

    Args:
        rect1: First bounding rectangle, expressed as tuples
            ``(xMin, yMin, xMax, yMax)``.
        rect2: Second bounding rectangle.

    Returns:
        The smallest rectangle in which both input rectangles are fully
        enclosed.
    """
    (xMin1, yMin1, xMax1, yMax1) = rect1
    (xMin2, yMin2, xMax2, yMax2) = rect2
    xMin, yMin, xMax, yMax = (
        min(xMin1, xMin2),
        min(yMin1, yMin2),
        max(xMax1, xMax2),
        max(yMax1, yMax2),
    )
    return (xMin, yMin, xMax, yMax)


def rectCenter(rect):
    """Determine rectangle center.

    Args:
        rect: Bounding rectangle, expressed as tuples
            ``(xMin, yMin, xMax, yMax)``.

    Returns:
        A 2D tuple representing the point at the center of the rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    return (xMin + xMax) / 2, (yMin + yMax) / 2


def rectArea(rect):
    """Determine rectangle area.

    Args:
        rect: Bounding rectangle, expressed as tuples
            ``(xMin, yMin, xMax, yMax)``.

    Returns:
        The area of the rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    return (yMax - yMin) * (xMax - xMin)


def intRect(rect):
    """Round a rectangle to integer values.

    Guarantees that the resulting rectangle is NOT smaller than the original.

    Args:
        rect: Bounding rectangle, expressed as tuples
            ``(xMin, yMin, xMax, yMax)``.

    Returns:
        A rounded bounding rectangle.
    """
    (xMin, yMin, xMax, yMax) = rect
    xMin = int(math.floor(xMin))
    yMin = int(math.floor(yMin))
    xMax = int(math.ceil(xMax))
    yMax = int(math.ceil(yMax))
    return (xMin, yMin, xMax, yMax)


def quantizeRect(rect, factor=1):
    """
    >>> bounds = (72.3, -218.4, 1201.3, 919.1)
    >>> quantizeRect(bounds)
    (72, -219, 1202, 920)
    >>> quantizeRect(bounds, factor=10)
    (70, -220, 1210, 920)
    >>> quantizeRect(bounds, factor=100)
    (0, -300, 1300, 1000)
    """
    if factor < 1:
        raise ValueError(f"Expected quantization factor >= 1, found: {factor!r}")
    xMin, yMin, xMax, yMax = normRect(rect)
    return (
        int(math.floor(xMin / factor) * factor),
        int(math.floor(yMin / factor) * factor),
        int(math.ceil(xMax / factor) * factor),
        int(math.ceil(yMax / factor) * factor),
    )


class Vector(_Vector):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "fontTools.misc.arrayTools.Vector has been deprecated, please use "
            "fontTools.misc.vector.Vector instead.",
            DeprecationWarning,
        )


def pairwise(iterable, reverse=False):
    """Iterate over current and next items in iterable.

    Args:
        iterable: An iterable
        reverse: If true, iterate in reverse order.

    Returns:
        A iterable yielding two elements per iteration.

    Example:

        >>> tuple(pairwise([]))
        ()
        >>> tuple(pairwise([], reverse=True))
        ()
        >>> tuple(pairwise([0]))
        ((0, 0),)
        >>> tuple(pairwise([0], reverse=True))
        ((0, 0),)
        >>> tuple(pairwise([0, 1]))
        ((0, 1), (1, 0))
        >>> tuple(pairwise([0, 1], reverse=True))
        ((1, 0), (0, 1))
        >>> tuple(pairwise([0, 1, 2]))
        ((0, 1), (1, 2), (2, 0))
        >>> tuple(pairwise([0, 1, 2], reverse=True))
        ((2, 1), (1, 0), (0, 2))
        >>> tuple(pairwise(['a', 'b', 'c', 'd']))
        (('a', 'b'), ('b', 'c'), ('c', 'd'), ('d', 'a'))
        >>> tuple(pairwise(['a', 'b', 'c', 'd'], reverse=True))
        (('d', 'c'), ('c', 'b'), ('b', 'a'), ('a', 'd'))
    """
    if not iterable:
        return
    if reverse:
        it = reversed(iterable)
    else:
        it = iter(iterable)
    first = next(it, None)
    a = first
    for b in it:
        yield (a, b)
        a = b
    yield (a, first)


def _test():
    """
    >>> import math
    >>> calcBounds([])
    (0, 0, 0, 0)
    >>> calcBounds([(0, 40), (0, 100), (50, 50), (80, 10)])
    (0, 10, 80, 100)
    >>> updateBounds((0, 0, 0, 0), (100, 100))
    (0, 0, 100, 100)
    >>> pointInRect((50, 50), (0, 0, 100, 100))
    True
    >>> pointInRect((0, 0), (0, 0, 100, 100))
    True
    >>> pointInRect((100, 100), (0, 0, 100, 100))
    True
    >>> not pointInRect((101, 100), (0, 0, 100, 100))
    True
    >>> list(pointsInRect([(50, 50), (0, 0), (100, 100), (101, 100)], (0, 0, 100, 100)))
    [True, True, True, False]
    >>> vectorLength((3, 4))
    5.0
    >>> vectorLength((1, 1)) == math.sqrt(2)
    True
    >>> list(asInt16([0, 0.1, 0.5, 0.9]))
    [0, 0, 1, 1]
    >>> normRect((0, 10, 100, 200))
    (0, 10, 100, 200)
    >>> normRect((100, 200, 0, 10))
    (0, 10, 100, 200)
    >>> scaleRect((10, 20, 50, 150), 1.5, 2)
    (15.0, 40, 75.0, 300)
    >>> offsetRect((10, 20, 30, 40), 5, 6)
    (15, 26, 35, 46)
    >>> insetRect((10, 20, 50, 60), 5, 10)
    (15, 30, 45, 50)
    >>> insetRect((10, 20, 50, 60), -5, -10)
    (5, 10, 55, 70)
    >>> intersects, rect = sectRect((0, 10, 20, 30), (0, 40, 20, 50))
    >>> not intersects
    True
    >>> intersects, rect = sectRect((0, 10, 20, 30), (5, 20, 35, 50))
    >>> intersects
    1
    >>> rect
    (5, 20, 20, 30)
    >>> unionRect((0, 10, 20, 30), (0, 40, 20, 50))
    (0, 10, 20, 50)
    >>> rectCenter((0, 0, 100, 200))
    (50.0, 100.0)
    >>> rectCenter((0, 0, 100, 199.0))
    (50.0, 99.5)
    >>> intRect((0.9, 2.9, 3.1, 4.1))
    (0, 2, 4, 5)
    """


if __name__ == "__main__":
    import sys
    import doctest

    sys.exit(doctest.testmod().failed)
