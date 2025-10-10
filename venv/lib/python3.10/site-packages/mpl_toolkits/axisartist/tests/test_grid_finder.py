import numpy as np
import pytest

from matplotlib.transforms import Bbox
from mpl_toolkits.axisartist.grid_finder import (
    _find_line_box_crossings, FormatterPrettyPrint, MaxNLocator)


def test_find_line_box_crossings():
    x = np.array([-3, -2, -1, 0., 1, 2, 3, 2, 1, 0, -1, -2, -3, 5])
    y = np.arange(len(x))
    bbox = Bbox.from_extents(-2, 3, 2, 12.5)
    left, right, bottom, top = _find_line_box_crossings(
        np.column_stack([x, y]), bbox)
    ((lx0, ly0), la0), ((lx1, ly1), la1), = left
    ((rx0, ry0), ra0), ((rx1, ry1), ra1), = right
    ((bx0, by0), ba0), = bottom
    ((tx0, ty0), ta0), = top
    assert (lx0, ly0, la0) == (-2, 11, 135)
    assert (lx1, ly1, la1) == pytest.approx((-2., 12.125, 7.125016))
    assert (rx0, ry0, ra0) == (2, 5, 45)
    assert (rx1, ry1, ra1) == (2, 7, 135)
    assert (bx0, by0, ba0) == (0, 3, 45)
    assert (tx0, ty0, ta0) == pytest.approx((1., 12.5, 7.125016))


def test_pretty_print_format():
    locator = MaxNLocator()
    locs, nloc, factor = locator(0, 100)

    fmt = FormatterPrettyPrint()

    assert fmt("left", None, locs) == \
        [r'$\mathdefault{%d}$' % (l, ) for l in locs]
