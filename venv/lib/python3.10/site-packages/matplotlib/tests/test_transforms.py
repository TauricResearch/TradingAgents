import copy

import numpy as np
from numpy.testing import (assert_allclose, assert_almost_equal,
                           assert_array_equal, assert_array_almost_equal)
import pytest

from matplotlib import scale
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.transforms as mtransforms
from matplotlib.transforms import Affine2D, Bbox, TransformedBbox, _ScaledRotation
from matplotlib.path import Path
from matplotlib.testing.decorators import image_comparison, check_figures_equal
from unittest.mock import MagicMock


class TestAffine2D:
    single_point = [1.0, 1.0]
    multiple_points = [[0.0, 2.0], [3.0, 3.0], [4.0, 0.0]]
    pivot = single_point

    def test_init(self):
        Affine2D([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        Affine2D(np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], int))
        Affine2D(np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], float))

    def test_values(self):
        np.random.seed(19680801)
        values = np.random.random(6)
        assert_array_equal(Affine2D.from_values(*values).to_values(), values)

    def test_modify_inplace(self):
        # Some polar transforms require modifying the matrix in place.
        trans = Affine2D()
        mtx = trans.get_matrix()
        mtx[0, 0] = 42
        assert_array_equal(trans.get_matrix(), [[42, 0, 0], [0, 1, 0], [0, 0, 1]])

    def test_clear(self):
        a = Affine2D(np.random.rand(3, 3) + 5)  # Anything non-identity.
        a.clear()
        assert_array_equal(a.get_matrix(), [[1, 0, 0], [0, 1, 0], [0, 0, 1]])

    def test_rotate(self):
        r_pi_2 = Affine2D().rotate(np.pi / 2)
        r90 = Affine2D().rotate_deg(90)
        assert_array_equal(r_pi_2.get_matrix(), r90.get_matrix())
        assert_array_almost_equal(r90.transform(self.single_point), [-1, 1])
        assert_array_almost_equal(r90.transform(self.multiple_points),
                                  [[-2, 0], [-3, 3], [0, 4]])

        r_pi = Affine2D().rotate(np.pi)
        r180 = Affine2D().rotate_deg(180)
        assert_array_equal(r_pi.get_matrix(), r180.get_matrix())
        assert_array_almost_equal(r180.transform(self.single_point), [-1, -1])
        assert_array_almost_equal(r180.transform(self.multiple_points),
                                  [[0, -2], [-3, -3], [-4, 0]])

        r_pi_3_2 = Affine2D().rotate(3 * np.pi / 2)
        r270 = Affine2D().rotate_deg(270)
        assert_array_equal(r_pi_3_2.get_matrix(), r270.get_matrix())
        assert_array_almost_equal(r270.transform(self.single_point), [1, -1])
        assert_array_almost_equal(r270.transform(self.multiple_points),
                                  [[2, 0], [3, -3], [0, -4]])

        assert_array_equal((r90 + r90).get_matrix(), r180.get_matrix())
        assert_array_equal((r90 + r180).get_matrix(), r270.get_matrix())

    def test_rotate_around(self):
        r_pi_2 = Affine2D().rotate_around(*self.pivot, np.pi / 2)
        r90 = Affine2D().rotate_deg_around(*self.pivot, 90)
        assert_array_equal(r_pi_2.get_matrix(), r90.get_matrix())
        assert_array_almost_equal(r90.transform(self.single_point), [1, 1])
        assert_array_almost_equal(r90.transform(self.multiple_points),
                                  [[0, 0], [-1, 3], [2, 4]])

        r_pi = Affine2D().rotate_around(*self.pivot, np.pi)
        r180 = Affine2D().rotate_deg_around(*self.pivot, 180)
        assert_array_equal(r_pi.get_matrix(), r180.get_matrix())
        assert_array_almost_equal(r180.transform(self.single_point), [1, 1])
        assert_array_almost_equal(r180.transform(self.multiple_points),
                                  [[2, 0], [-1, -1], [-2, 2]])

        r_pi_3_2 = Affine2D().rotate_around(*self.pivot, 3 * np.pi / 2)
        r270 = Affine2D().rotate_deg_around(*self.pivot, 270)
        assert_array_equal(r_pi_3_2.get_matrix(), r270.get_matrix())
        assert_array_almost_equal(r270.transform(self.single_point), [1, 1])
        assert_array_almost_equal(r270.transform(self.multiple_points),
                                  [[2, 2], [3, -1], [0, -2]])

        assert_array_almost_equal((r90 + r90).get_matrix(), r180.get_matrix())
        assert_array_almost_equal((r90 + r180).get_matrix(), r270.get_matrix())

    def test_scale(self):
        sx = Affine2D().scale(3, 1)
        sy = Affine2D().scale(1, -2)
        trans = Affine2D().scale(3, -2)
        assert_array_equal((sx + sy).get_matrix(), trans.get_matrix())
        assert_array_equal(trans.transform(self.single_point), [3, -2])
        assert_array_equal(trans.transform(self.multiple_points),
                           [[0, -4], [9, -6], [12, 0]])

    def test_skew(self):
        trans_rad = Affine2D().skew(np.pi / 8, np.pi / 12)
        trans_deg = Affine2D().skew_deg(22.5, 15)
        assert_array_equal(trans_rad.get_matrix(), trans_deg.get_matrix())
        # Using ~atan(0.5), ~atan(0.25) produces roundish numbers on output.
        trans = Affine2D().skew_deg(26.5650512, 14.0362435)
        assert_array_almost_equal(trans.transform(self.single_point), [1.5, 1.25])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[1, 2], [4.5, 3.75], [4, 1]])

    def test_translate(self):
        tx = Affine2D().translate(23, 0)
        ty = Affine2D().translate(0, 42)
        trans = Affine2D().translate(23, 42)
        assert_array_equal((tx + ty).get_matrix(), trans.get_matrix())
        assert_array_equal(trans.transform(self.single_point), [24, 43])
        assert_array_equal(trans.transform(self.multiple_points),
                           [[23, 44], [26, 45], [27, 42]])

    def test_rotate_plus_other(self):
        trans = Affine2D().rotate_deg(90).rotate_deg_around(*self.pivot, 180)
        trans_added = (Affine2D().rotate_deg(90) +
                       Affine2D().rotate_deg_around(*self.pivot, 180))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [3, 1])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[4, 2], [5, -1], [2, -2]])

        trans = Affine2D().rotate_deg(90).scale(3, -2)
        trans_added = Affine2D().rotate_deg(90) + Affine2D().scale(3, -2)
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [-3, -2])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[-6, -0], [-9, -6], [0, -8]])

        trans = (Affine2D().rotate_deg(90)
                 .skew_deg(26.5650512, 14.0362435))  # ~atan(0.5), ~atan(0.25)
        trans_added = (Affine2D().rotate_deg(90) +
                       Affine2D().skew_deg(26.5650512, 14.0362435))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [-0.5, 0.75])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[-2, -0.5], [-1.5, 2.25], [2, 4]])

        trans = Affine2D().rotate_deg(90).translate(23, 42)
        trans_added = Affine2D().rotate_deg(90) + Affine2D().translate(23, 42)
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [22, 43])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[21, 42], [20, 45], [23, 46]])

    def test_rotate_around_plus_other(self):
        trans = Affine2D().rotate_deg_around(*self.pivot, 90).rotate_deg(180)
        trans_added = (Affine2D().rotate_deg_around(*self.pivot, 90) +
                       Affine2D().rotate_deg(180))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [-1, -1])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[0, 0], [1, -3], [-2, -4]])

        trans = Affine2D().rotate_deg_around(*self.pivot, 90).scale(3, -2)
        trans_added = (Affine2D().rotate_deg_around(*self.pivot, 90) +
                       Affine2D().scale(3, -2))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [3, -2])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[0, 0], [-3, -6], [6, -8]])

        trans = (Affine2D().rotate_deg_around(*self.pivot, 90)
                 .skew_deg(26.5650512, 14.0362435))  # ~atan(0.5), ~atan(0.25)
        trans_added = (Affine2D().rotate_deg_around(*self.pivot, 90) +
                       Affine2D().skew_deg(26.5650512, 14.0362435))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [1.5, 1.25])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[0, 0], [0.5, 2.75], [4, 4.5]])

        trans = Affine2D().rotate_deg_around(*self.pivot, 90).translate(23, 42)
        trans_added = (Affine2D().rotate_deg_around(*self.pivot, 90) +
                       Affine2D().translate(23, 42))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [24, 43])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[23, 42], [22, 45], [25, 46]])

    def test_scale_plus_other(self):
        trans = Affine2D().scale(3, -2).rotate_deg(90)
        trans_added = Affine2D().scale(3, -2) + Affine2D().rotate_deg(90)
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_equal(trans.transform(self.single_point), [2, 3])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[4, 0], [6, 9], [0, 12]])

        trans = Affine2D().scale(3, -2).rotate_deg_around(*self.pivot, 90)
        trans_added = (Affine2D().scale(3, -2) +
                       Affine2D().rotate_deg_around(*self.pivot, 90))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_equal(trans.transform(self.single_point), [4, 3])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[6, 0], [8, 9], [2, 12]])

        trans = (Affine2D().scale(3, -2)
                 .skew_deg(26.5650512, 14.0362435))  # ~atan(0.5), ~atan(0.25)
        trans_added = (Affine2D().scale(3, -2) +
                       Affine2D().skew_deg(26.5650512, 14.0362435))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [2, -1.25])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[-2, -4], [6, -3.75], [12, 3]])

        trans = Affine2D().scale(3, -2).translate(23, 42)
        trans_added = Affine2D().scale(3, -2) + Affine2D().translate(23, 42)
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_equal(trans.transform(self.single_point), [26, 40])
        assert_array_equal(trans.transform(self.multiple_points),
                           [[23, 38], [32, 36], [35, 42]])

    def test_skew_plus_other(self):
        # Using ~atan(0.5), ~atan(0.25) produces roundish numbers on output.
        trans = Affine2D().skew_deg(26.5650512, 14.0362435).rotate_deg(90)
        trans_added = (Affine2D().skew_deg(26.5650512, 14.0362435) +
                       Affine2D().rotate_deg(90))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [-1.25, 1.5])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[-2, 1], [-3.75, 4.5], [-1, 4]])

        trans = (Affine2D().skew_deg(26.5650512, 14.0362435)
                 .rotate_deg_around(*self.pivot, 90))
        trans_added = (Affine2D().skew_deg(26.5650512, 14.0362435) +
                       Affine2D().rotate_deg_around(*self.pivot, 90))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [0.75, 1.5])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[0, 1], [-1.75, 4.5], [1, 4]])

        trans = Affine2D().skew_deg(26.5650512, 14.0362435).scale(3, -2)
        trans_added = (Affine2D().skew_deg(26.5650512, 14.0362435) +
                       Affine2D().scale(3, -2))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [4.5, -2.5])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[3, -4], [13.5, -7.5], [12, -2]])

        trans = Affine2D().skew_deg(26.5650512, 14.0362435).translate(23, 42)
        trans_added = (Affine2D().skew_deg(26.5650512, 14.0362435) +
                       Affine2D().translate(23, 42))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [24.5, 43.25])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[24, 44], [27.5, 45.75], [27, 43]])

    def test_translate_plus_other(self):
        trans = Affine2D().translate(23, 42).rotate_deg(90)
        trans_added = Affine2D().translate(23, 42) + Affine2D().rotate_deg(90)
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [-43, 24])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[-44, 23], [-45, 26], [-42, 27]])

        trans = Affine2D().translate(23, 42).rotate_deg_around(*self.pivot, 90)
        trans_added = (Affine2D().translate(23, 42) +
                       Affine2D().rotate_deg_around(*self.pivot, 90))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [-41, 24])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[-42, 23], [-43, 26], [-40, 27]])

        trans = Affine2D().translate(23, 42).scale(3, -2)
        trans_added = Affine2D().translate(23, 42) + Affine2D().scale(3, -2)
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [72, -86])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[69, -88], [78, -90], [81, -84]])

        trans = (Affine2D().translate(23, 42)
                 .skew_deg(26.5650512, 14.0362435))  # ~atan(0.5), ~atan(0.25)
        trans_added = (Affine2D().translate(23, 42) +
                       Affine2D().skew_deg(26.5650512, 14.0362435))
        assert_array_equal(trans.get_matrix(), trans_added.get_matrix())
        assert_array_almost_equal(trans.transform(self.single_point), [45.5, 49])
        assert_array_almost_equal(trans.transform(self.multiple_points),
                                  [[45, 49.75], [48.5, 51.5], [48, 48.75]])

    def test_invalid_transform(self):
        t = mtransforms.Affine2D()
        # There are two different exceptions, since the wrong number of
        # dimensions is caught when constructing an array_view, and that
        # raises a ValueError, and a wrong shape with a possible number
        # of dimensions is caught by our CALL_CPP macro, which always
        # raises the less precise RuntimeError.
        with pytest.raises(ValueError):
            t.transform(1)
        with pytest.raises(ValueError):
            t.transform([[[1]]])
        with pytest.raises(RuntimeError):
            t.transform([])
        with pytest.raises(RuntimeError):
            t.transform([1])
        with pytest.raises(ValueError):
            t.transform([[1]])
        with pytest.raises(ValueError):
            t.transform([[1, 2, 3]])

    def test_copy(self):
        a = mtransforms.Affine2D()
        b = mtransforms.Affine2D()
        s = a + b
        # Updating a dependee should invalidate a copy of the dependent.
        s.get_matrix()  # resolve it.
        s1 = copy.copy(s)
        assert not s._invalid and not s1._invalid
        a.translate(1, 2)
        assert s._invalid and s1._invalid
        assert (s1.get_matrix() == a.get_matrix()).all()
        # Updating a copy of a dependee shouldn't invalidate a dependent.
        s.get_matrix()  # resolve it.
        b1 = copy.copy(b)
        b1.translate(3, 4)
        assert not s._invalid
        assert_array_equal(s.get_matrix(), a.get_matrix())

    def test_deepcopy(self):
        a = mtransforms.Affine2D()
        b = mtransforms.Affine2D()
        s = a + b
        # Updating a dependee shouldn't invalidate a deepcopy of the dependent.
        s.get_matrix()  # resolve it.
        s1 = copy.deepcopy(s)
        assert not s._invalid and not s1._invalid
        a.translate(1, 2)
        assert s._invalid and not s1._invalid
        assert_array_equal(s1.get_matrix(), mtransforms.Affine2D().get_matrix())
        # Updating a deepcopy of a dependee shouldn't invalidate a dependent.
        s.get_matrix()  # resolve it.
        b1 = copy.deepcopy(b)
        b1.translate(3, 4)
        assert not s._invalid
        assert_array_equal(s.get_matrix(), a.get_matrix())


class TestAffineDeltaTransform:
    def test_invalidate(self):
        before = np.array([[1.0, 4.0, 0.0],
                           [5.0, 1.0, 0.0],
                           [0.0, 0.0, 1.0]])
        after = np.array([[1.0, 3.0, 0.0],
                          [5.0, 1.0, 0.0],
                          [0.0, 0.0, 1.0]])

        # Translation and skew present
        base = mtransforms.Affine2D.from_values(1, 5, 4, 1, 2, 3)
        t = mtransforms.AffineDeltaTransform(base)
        assert_array_equal(t.get_matrix(), before)

        # Mess with the internal structure of `base` without invalidating
        # This should not affect this transform because it's a passthrough:
        # it's always invalid
        base.get_matrix()[0, 1:] = 3
        assert_array_equal(t.get_matrix(), after)

        # Invalidate the base
        base.invalidate()
        assert_array_equal(t.get_matrix(), after)


def test_non_affine_caching():
    class AssertingNonAffineTransform(mtransforms.Transform):
        """
        This transform raises an assertion error when called when it
        shouldn't be and ``self.raise_on_transform`` is True.

        """
        input_dims = output_dims = 2
        is_affine = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.raise_on_transform = False
            self.underlying_transform = mtransforms.Affine2D().scale(10, 10)

        def transform_path_non_affine(self, path):
            assert not self.raise_on_transform, \
                'Invalidated affine part of transform unnecessarily.'
            return self.underlying_transform.transform_path(path)
        transform_path = transform_path_non_affine

        def transform_non_affine(self, path):
            assert not self.raise_on_transform, \
                'Invalidated affine part of transform unnecessarily.'
            return self.underlying_transform.transform(path)
        transform = transform_non_affine

    my_trans = AssertingNonAffineTransform()
    ax = plt.axes()
    plt.plot(np.arange(10), transform=my_trans + ax.transData)
    plt.draw()
    # enable the transform to raise an exception if it's non-affine transform
    # method is triggered again.
    my_trans.raise_on_transform = True
    ax.transAxes.invalidate()
    plt.draw()


def test_external_transform_api():
    class ScaledBy:
        def __init__(self, scale_factor):
            self._scale_factor = scale_factor

        def _as_mpl_transform(self, axes):
            return (mtransforms.Affine2D().scale(self._scale_factor)
                    + axes.transData)

    ax = plt.axes()
    line, = plt.plot(np.arange(10), transform=ScaledBy(10))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    # assert that the top transform of the line is the scale transform.
    assert_allclose(line.get_transform()._a.get_matrix(),
                    mtransforms.Affine2D().scale(10).get_matrix())


@image_comparison(['pre_transform_data'], remove_text=True, style='mpl20',
                  tol=0.05)
def test_pre_transform_plotting():
    # a catch-all for as many as possible plot layouts which handle
    # pre-transforming the data NOTE: The axis range is important in this
    # plot. It should be x10 what the data suggests it should be

    ax = plt.axes()
    times10 = mtransforms.Affine2D().scale(10)

    ax.contourf(np.arange(48).reshape(6, 8), transform=times10 + ax.transData)

    ax.pcolormesh(np.linspace(0, 4, 7),
                  np.linspace(5.5, 8, 9),
                  np.arange(48).reshape(8, 6),
                  transform=times10 + ax.transData)

    ax.scatter(np.linspace(0, 10), np.linspace(10, 0),
               transform=times10 + ax.transData)

    x = np.linspace(8, 10, 20)
    y = np.linspace(1, 5, 20)
    u = 2*np.sin(x) + np.cos(y[:, np.newaxis])
    v = np.sin(x) - np.cos(y[:, np.newaxis])

    ax.streamplot(x, y, u, v, transform=times10 + ax.transData,
                  linewidth=np.hypot(u, v))

    # reduce the vector data down a bit for barb and quiver plotting
    x, y = x[::3], y[::3]
    u, v = u[::3, ::3], v[::3, ::3]

    ax.quiver(x, y + 5, u, v, transform=times10 + ax.transData)

    ax.barbs(x - 3, y + 5, u**2, v**2, transform=times10 + ax.transData)


def test_contour_pre_transform_limits():
    ax = plt.axes()
    xs, ys = np.meshgrid(np.linspace(15, 20, 15), np.linspace(12.4, 12.5, 20))
    ax.contourf(xs, ys, np.log(xs * ys),
                transform=mtransforms.Affine2D().scale(0.1) + ax.transData)

    expected = np.array([[1.5, 1.24],
                         [2., 1.25]])
    assert_almost_equal(expected, ax.dataLim.get_points())


def test_pcolor_pre_transform_limits():
    # Based on test_contour_pre_transform_limits()
    ax = plt.axes()
    xs, ys = np.meshgrid(np.linspace(15, 20, 15), np.linspace(12.4, 12.5, 20))
    ax.pcolor(xs, ys, np.log(xs * ys)[:-1, :-1],
              transform=mtransforms.Affine2D().scale(0.1) + ax.transData)

    expected = np.array([[1.5, 1.24],
                         [2., 1.25]])
    assert_almost_equal(expected, ax.dataLim.get_points())


def test_pcolormesh_pre_transform_limits():
    # Based on test_contour_pre_transform_limits()
    ax = plt.axes()
    xs, ys = np.meshgrid(np.linspace(15, 20, 15), np.linspace(12.4, 12.5, 20))
    ax.pcolormesh(xs, ys, np.log(xs * ys)[:-1, :-1],
                  transform=mtransforms.Affine2D().scale(0.1) + ax.transData)

    expected = np.array([[1.5, 1.24],
                         [2., 1.25]])
    assert_almost_equal(expected, ax.dataLim.get_points())


def test_pcolormesh_gouraud_nans():
    np.random.seed(19680801)

    values = np.linspace(0, 180, 3)
    radii = np.linspace(100, 1000, 10)
    z, y = np.meshgrid(values, radii)
    x = np.radians(np.random.rand(*z.shape) * 100)

    fig = plt.figure()
    ax = fig.add_subplot(111, projection="polar")
    # Setting the limit to cause clipping of the r values causes NaN to be
    # introduced; these should not crash but be ignored as in other path
    # operations.
    ax.set_rlim(101, 1000)
    ax.pcolormesh(x, y, z, shading="gouraud")

    fig.canvas.draw()


def test_Affine2D_from_values():
    points = np.array([[0, 0],
                       [10, 20],
                       [-1, 0],
                       ])

    t = mtransforms.Affine2D.from_values(1, 0, 0, 0, 0, 0)
    actual = t.transform(points)
    expected = np.array([[0, 0], [10, 0], [-1, 0]])
    assert_almost_equal(actual, expected)

    t = mtransforms.Affine2D.from_values(0, 2, 0, 0, 0, 0)
    actual = t.transform(points)
    expected = np.array([[0, 0], [0, 20], [0, -2]])
    assert_almost_equal(actual, expected)

    t = mtransforms.Affine2D.from_values(0, 0, 3, 0, 0, 0)
    actual = t.transform(points)
    expected = np.array([[0, 0], [60, 0], [0, 0]])
    assert_almost_equal(actual, expected)

    t = mtransforms.Affine2D.from_values(0, 0, 0, 4, 0, 0)
    actual = t.transform(points)
    expected = np.array([[0, 0], [0, 80], [0, 0]])
    assert_almost_equal(actual, expected)

    t = mtransforms.Affine2D.from_values(0, 0, 0, 0, 5, 0)
    actual = t.transform(points)
    expected = np.array([[5, 0], [5, 0], [5, 0]])
    assert_almost_equal(actual, expected)

    t = mtransforms.Affine2D.from_values(0, 0, 0, 0, 0, 6)
    actual = t.transform(points)
    expected = np.array([[0, 6], [0, 6], [0, 6]])
    assert_almost_equal(actual, expected)


def test_affine_inverted_invalidated():
    # Ensure that the an affine transform is not declared valid on access
    point = [1.0, 1.0]
    t = mtransforms.Affine2D()

    assert_almost_equal(point, t.transform(t.inverted().transform(point)))
    # Change and access the transform
    t.translate(1.0, 1.0).get_matrix()
    assert_almost_equal(point, t.transform(t.inverted().transform(point)))


def test_clipping_of_log():
    # issue 804
    path = Path._create_closed([(0.2, -99), (0.4, -99), (0.4, 20), (0.2, 20)])
    # something like this happens in plotting logarithmic histograms
    trans = mtransforms.BlendedGenericTransform(
        mtransforms.Affine2D(), scale.LogTransform(10, 'clip'))
    tpath = trans.transform_path_non_affine(path)
    result = tpath.iter_segments(trans.get_affine(),
                                 clip=(0, 0, 100, 100),
                                 simplify=False)
    tpoints, tcodes = zip(*result)
    assert_allclose(tcodes, path.codes[:-1])  # No longer closed.


class NonAffineForTest(mtransforms.Transform):
    """
    A class which looks like a non affine transform, but does whatever
    the given transform does (even if it is affine). This is very useful
    for testing NonAffine behaviour with a simple Affine transform.

    """
    is_affine = False
    output_dims = 2
    input_dims = 2

    def __init__(self, real_trans, *args, **kwargs):
        self.real_trans = real_trans
        super().__init__(*args, **kwargs)

    def transform_non_affine(self, values):
        return self.real_trans.transform(values)

    def transform_path_non_affine(self, path):
        return self.real_trans.transform_path(path)


class TestBasicTransform:
    def setup_method(self):

        self.ta1 = mtransforms.Affine2D(shorthand_name='ta1').rotate(np.pi / 2)
        self.ta2 = mtransforms.Affine2D(shorthand_name='ta2').translate(10, 0)
        self.ta3 = mtransforms.Affine2D(shorthand_name='ta3').scale(1, 2)

        self.tn1 = NonAffineForTest(mtransforms.Affine2D().translate(1, 2),
                                    shorthand_name='tn1')
        self.tn2 = NonAffineForTest(mtransforms.Affine2D().translate(1, 2),
                                    shorthand_name='tn2')
        self.tn3 = NonAffineForTest(mtransforms.Affine2D().translate(1, 2),
                                    shorthand_name='tn3')

        # creates a transform stack which looks like ((A, (N, A)), A)
        self.stack1 = (self.ta1 + (self.tn1 + self.ta2)) + self.ta3
        # creates a transform stack which looks like (((A, N), A), A)
        self.stack2 = self.ta1 + self.tn1 + self.ta2 + self.ta3
        # creates a transform stack which is a subset of stack2
        self.stack2_subset = self.tn1 + self.ta2 + self.ta3

        # when in debug, the transform stacks can produce dot images:
#        self.stack1.write_graphviz(file('stack1.dot', 'w'))
#        self.stack2.write_graphviz(file('stack2.dot', 'w'))
#        self.stack2_subset.write_graphviz(file('stack2_subset.dot', 'w'))

    def test_transform_depth(self):
        assert self.stack1.depth == 4
        assert self.stack2.depth == 4
        assert self.stack2_subset.depth == 3

    def test_left_to_right_iteration(self):
        stack3 = (self.ta1 + (self.tn1 + (self.ta2 + self.tn2))) + self.ta3
#        stack3.write_graphviz(file('stack3.dot', 'w'))

        target_transforms = [stack3,
                             (self.tn1 + (self.ta2 + self.tn2)) + self.ta3,
                             (self.ta2 + self.tn2) + self.ta3,
                             self.tn2 + self.ta3,
                             self.ta3,
                             ]
        r = [rh for _, rh in stack3._iter_break_from_left_to_right()]
        assert len(r) == len(target_transforms)

        for target_stack, stack in zip(target_transforms, r):
            assert target_stack == stack

    def test_transform_shortcuts(self):
        assert self.stack1 - self.stack2_subset == self.ta1
        assert self.stack2 - self.stack2_subset == self.ta1

        assert self.stack2_subset - self.stack2 == self.ta1.inverted()
        assert (self.stack2_subset - self.stack2).depth == 1

        with pytest.raises(ValueError):
            self.stack1 - self.stack2

        aff1 = self.ta1 + (self.ta2 + self.ta3)
        aff2 = self.ta2 + self.ta3

        assert aff1 - aff2 == self.ta1
        assert aff1 - self.ta2 == aff1 + self.ta2.inverted()

        assert self.stack1 - self.ta3 == self.ta1 + (self.tn1 + self.ta2)
        assert self.stack2 - self.ta3 == self.ta1 + self.tn1 + self.ta2

        assert ((self.ta2 + self.ta3) - self.ta3 + self.ta3 ==
                self.ta2 + self.ta3)

    def test_contains_branch(self):
        r1 = (self.ta2 + self.ta1)
        r2 = (self.ta2 + self.ta1)
        assert r1 == r2
        assert r1 != self.ta1
        assert r1.contains_branch(r2)
        assert r1.contains_branch(self.ta1)
        assert not r1.contains_branch(self.ta2)
        assert not r1.contains_branch(self.ta2 + self.ta2)

        assert r1 == r2

        assert self.stack1.contains_branch(self.ta3)
        assert self.stack2.contains_branch(self.ta3)

        assert self.stack1.contains_branch(self.stack2_subset)
        assert self.stack2.contains_branch(self.stack2_subset)

        assert not self.stack2_subset.contains_branch(self.stack1)
        assert not self.stack2_subset.contains_branch(self.stack2)

        assert self.stack1.contains_branch(self.ta2 + self.ta3)
        assert self.stack2.contains_branch(self.ta2 + self.ta3)

        assert not self.stack1.contains_branch(self.tn1 + self.ta2)

        blend = mtransforms.BlendedGenericTransform(self.tn2, self.stack2)
        x, y = blend.contains_branch_seperately(self.stack2_subset)
        stack_blend = self.tn3 + blend
        sx, sy = stack_blend.contains_branch_seperately(self.stack2_subset)
        assert x is sx is False
        assert y is sy is True

    def test_affine_simplification(self):
        # tests that a transform stack only calls as much is absolutely
        # necessary "non-affine" allowing the best possible optimization with
        # complex transformation stacks.
        points = np.array([[0, 0], [10, 20], [np.nan, 1], [-1, 0]],
                          dtype=np.float64)
        na_pts = self.stack1.transform_non_affine(points)
        all_pts = self.stack1.transform(points)

        na_expected = np.array([[1., 2.], [-19., 12.],
                                [np.nan, np.nan], [1., 1.]], dtype=np.float64)
        all_expected = np.array([[11., 4.], [-9., 24.],
                                 [np.nan, np.nan], [11., 2.]],
                                dtype=np.float64)

        # check we have the expected results from doing the affine part only
        assert_array_almost_equal(na_pts, na_expected)
        # check we have the expected results from a full transformation
        assert_array_almost_equal(all_pts, all_expected)
        # check we have the expected results from doing the transformation in
        # two steps
        assert_array_almost_equal(self.stack1.transform_affine(na_pts),
                                  all_expected)
        # check that getting the affine transformation first, then fully
        # transforming using that yields the same result as before.
        assert_array_almost_equal(self.stack1.get_affine().transform(na_pts),
                                  all_expected)

        # check that the affine part of stack1 & stack2 are equivalent
        # (i.e. the optimization is working)
        expected_result = (self.ta2 + self.ta3).get_matrix()
        result = self.stack1.get_affine().get_matrix()
        assert_array_equal(expected_result, result)

        result = self.stack2.get_affine().get_matrix()
        assert_array_equal(expected_result, result)


class TestTransformPlotInterface:
    def test_line_extent_axes_coords(self):
        # a simple line in axes coordinates
        ax = plt.axes()
        ax.plot([0.1, 1.2, 0.8], [0.9, 0.5, 0.8], transform=ax.transAxes)
        assert_array_equal(ax.dataLim.get_points(),
                           np.array([[np.inf, np.inf],
                                     [-np.inf, -np.inf]]))

    def test_line_extent_data_coords(self):
        # a simple line in data coordinates
        ax = plt.axes()
        ax.plot([0.1, 1.2, 0.8], [0.9, 0.5, 0.8], transform=ax.transData)
        assert_array_equal(ax.dataLim.get_points(),
                           np.array([[0.1,  0.5], [1.2,  0.9]]))

    def test_line_extent_compound_coords1(self):
        # a simple line in data coordinates in the y component, and in axes
        # coordinates in the x
        ax = plt.axes()
        trans = mtransforms.blended_transform_factory(ax.transAxes,
                                                      ax.transData)
        ax.plot([0.1, 1.2, 0.8], [35, -5, 18], transform=trans)
        assert_array_equal(ax.dataLim.get_points(),
                           np.array([[np.inf, -5.],
                                     [-np.inf, 35.]]))

    def test_line_extent_predata_transform_coords(self):
        # a simple line in (offset + data) coordinates
        ax = plt.axes()
        trans = mtransforms.Affine2D().scale(10) + ax.transData
        ax.plot([0.1, 1.2, 0.8], [35, -5, 18], transform=trans)
        assert_array_equal(ax.dataLim.get_points(),
                           np.array([[1., -50.], [12., 350.]]))

    def test_line_extent_compound_coords2(self):
        # a simple line in (offset + data) coordinates in the y component, and
        # in axes coordinates in the x
        ax = plt.axes()
        trans = mtransforms.blended_transform_factory(
            ax.transAxes, mtransforms.Affine2D().scale(10) + ax.transData)
        ax.plot([0.1, 1.2, 0.8], [35, -5, 18], transform=trans)
        assert_array_equal(ax.dataLim.get_points(),
                           np.array([[np.inf, -50.], [-np.inf, 350.]]))

    def test_line_extents_affine(self):
        ax = plt.axes()
        offset = mtransforms.Affine2D().translate(10, 10)
        plt.plot(np.arange(10), transform=offset + ax.transData)
        expected_data_lim = np.array([[0., 0.], [9.,  9.]]) + 10
        assert_array_almost_equal(ax.dataLim.get_points(), expected_data_lim)

    def test_line_extents_non_affine(self):
        ax = plt.axes()
        offset = mtransforms.Affine2D().translate(10, 10)
        na_offset = NonAffineForTest(mtransforms.Affine2D().translate(10, 10))
        plt.plot(np.arange(10), transform=offset + na_offset + ax.transData)
        expected_data_lim = np.array([[0., 0.], [9.,  9.]]) + 20
        assert_array_almost_equal(ax.dataLim.get_points(), expected_data_lim)

    def test_pathc_extents_non_affine(self):
        ax = plt.axes()
        offset = mtransforms.Affine2D().translate(10, 10)
        na_offset = NonAffineForTest(mtransforms.Affine2D().translate(10, 10))
        pth = Path([[0, 0], [0, 10], [10, 10], [10, 0]])
        patch = mpatches.PathPatch(pth,
                                   transform=offset + na_offset + ax.transData)
        ax.add_patch(patch)
        expected_data_lim = np.array([[0., 0.], [10.,  10.]]) + 20
        assert_array_almost_equal(ax.dataLim.get_points(), expected_data_lim)

    def test_pathc_extents_affine(self):
        ax = plt.axes()
        offset = mtransforms.Affine2D().translate(10, 10)
        pth = Path([[0, 0], [0, 10], [10, 10], [10, 0]])
        patch = mpatches.PathPatch(pth, transform=offset + ax.transData)
        ax.add_patch(patch)
        expected_data_lim = np.array([[0., 0.], [10.,  10.]]) + 10
        assert_array_almost_equal(ax.dataLim.get_points(), expected_data_lim)

    def test_line_extents_for_non_affine_transData(self):
        ax = plt.axes(projection='polar')
        # add 10 to the radius of the data
        offset = mtransforms.Affine2D().translate(0, 10)

        plt.plot(np.arange(10), transform=offset + ax.transData)
        # the data lim of a polar plot is stored in coordinates
        # before a transData transformation, hence the data limits
        # are not what is being shown on the actual plot.
        expected_data_lim = np.array([[0., 0.], [9.,  9.]]) + [0, 10]
        assert_array_almost_equal(ax.dataLim.get_points(), expected_data_lim)


def assert_bbox_eq(bbox1, bbox2):
    assert_array_equal(bbox1.bounds, bbox2.bounds)


def test_bbox_frozen_copies_minpos():
    bbox = mtransforms.Bbox.from_extents(0.0, 0.0, 1.0, 1.0, minpos=1.0)
    frozen = bbox.frozen()
    assert_array_equal(frozen.minpos, bbox.minpos)


def test_bbox_intersection():
    bbox_from_ext = mtransforms.Bbox.from_extents
    inter = mtransforms.Bbox.intersection

    r1 = bbox_from_ext(0, 0, 1, 1)
    r2 = bbox_from_ext(0.5, 0.5, 1.5, 1.5)
    r3 = bbox_from_ext(0.5, 0, 0.75, 0.75)
    r4 = bbox_from_ext(0.5, 1.5, 1, 2.5)
    r5 = bbox_from_ext(1, 1, 2, 2)

    # self intersection -> no change
    assert_bbox_eq(inter(r1, r1), r1)
    # simple intersection
    assert_bbox_eq(inter(r1, r2), bbox_from_ext(0.5, 0.5, 1, 1))
    # r3 contains r2
    assert_bbox_eq(inter(r1, r3), r3)
    # no intersection
    assert inter(r1, r4) is None
    # single point
    assert_bbox_eq(inter(r1, r5), bbox_from_ext(1, 1, 1, 1))


def test_bbox_as_strings():
    b = mtransforms.Bbox([[.5, 0], [.75, .75]])
    assert_bbox_eq(b, eval(repr(b), {'Bbox': mtransforms.Bbox}))
    asdict = eval(str(b), {'Bbox': dict})
    for k, v in asdict.items():
        assert getattr(b, k) == v
    fmt = '.1f'
    asdict = eval(format(b, fmt), {'Bbox': dict})
    for k, v in asdict.items():
        assert eval(format(getattr(b, k), fmt)) == v


def test_str_transform():
    # The str here should not be considered as "absolutely stable", and may be
    # reformatted later; this is just a smoketest for __str__.
    assert str(plt.subplot(projection="polar").transData) == """\
CompositeGenericTransform(
    CompositeGenericTransform(
        CompositeGenericTransform(
            TransformWrapper(
                BlendedAffine2D(
                    IdentityTransform(),
                    IdentityTransform())),
            CompositeAffine2D(
                Affine2D().scale(1.0),
                Affine2D().scale(1.0))),
        PolarTransform(
            PolarAxes(0.125,0.1;0.775x0.8),
            use_rmin=True,
            apply_theta_transforms=False)),
    CompositeGenericTransform(
        CompositeGenericTransform(
            PolarAffine(
                TransformWrapper(
                    BlendedAffine2D(
                        IdentityTransform(),
                        IdentityTransform())),
                LockableBbox(
                    Bbox(x0=0.0, y0=0.0, x1=6.283185307179586, y1=1.0),
                    [[-- --]
                     [-- --]])),
            BboxTransformFrom(
                _WedgeBbox(
                    (0.5, 0.5),
                    TransformedBbox(
                        Bbox(x0=0.0, y0=0.0, x1=6.283185307179586, y1=1.0),
                        CompositeAffine2D(
                            Affine2D().scale(1.0),
                            Affine2D().scale(1.0))),
                    LockableBbox(
                        Bbox(x0=0.0, y0=0.0, x1=6.283185307179586, y1=1.0),
                        [[-- --]
                         [-- --]])))),
        BboxTransformTo(
            TransformedBbox(
                Bbox(x0=0.125, y0=0.09999999999999998, x1=0.9, y1=0.9),
                BboxTransformTo(
                    TransformedBbox(
                        Bbox(x0=0.0, y0=0.0, x1=8.0, y1=6.0),
                        Affine2D().scale(80.0)))))))"""


def test_transform_single_point():
    t = mtransforms.Affine2D()
    r = t.transform_affine((1, 1))
    assert r.shape == (2,)


def test_log_transform():
    # Tests that the last line runs without exception (previously the
    # transform would fail if one of the axes was logarithmic).
    fig, ax = plt.subplots()
    ax.set_yscale('log')
    ax.transData.transform((1, 1))


def test_nan_overlap():
    a = mtransforms.Bbox([[0, 0], [1, 1]])
    b = mtransforms.Bbox([[0, 0], [1, np.nan]])
    assert not a.overlaps(b)


def test_transform_angles():
    t = mtransforms.Affine2D()  # Identity transform
    angles = np.array([20, 45, 60])
    points = np.array([[0, 0], [1, 1], [2, 2]])

    # Identity transform does not change angles
    new_angles = t.transform_angles(angles, points)
    assert_array_almost_equal(angles, new_angles)

    # points missing a 2nd dimension
    with pytest.raises(ValueError):
        t.transform_angles(angles, points[0:2, 0:1])

    # Number of angles != Number of points
    with pytest.raises(ValueError):
        t.transform_angles(angles, points[0:2, :])


def test_nonsingular():
    # test for zero-expansion type cases; other cases may be added later
    zero_expansion = np.array([-0.001, 0.001])
    cases = [(0, np.nan), (0, 0), (0, 7.9e-317)]
    for args in cases:
        out = np.array(mtransforms.nonsingular(*args))
        assert_array_equal(out, zero_expansion)


def test_transformed_path():
    points = [(0, 0), (1, 0), (1, 1), (0, 1)]
    path = Path(points, closed=True)

    trans = mtransforms.Affine2D()
    trans_path = mtransforms.TransformedPath(path, trans)
    assert_allclose(trans_path.get_fully_transformed_path().vertices, points)

    # Changing the transform should change the result.
    r2 = 1 / np.sqrt(2)
    trans.rotate(np.pi / 4)
    assert_allclose(trans_path.get_fully_transformed_path().vertices,
                    [(0, 0), (r2, r2), (0, 2 * r2), (-r2, r2)],
                    atol=1e-15)

    # Changing the path does not change the result (it's cached).
    path.points = [(0, 0)] * 4
    assert_allclose(trans_path.get_fully_transformed_path().vertices,
                    [(0, 0), (r2, r2), (0, 2 * r2), (-r2, r2)],
                    atol=1e-15)


def test_transformed_patch_path():
    trans = mtransforms.Affine2D()
    patch = mpatches.Wedge((0, 0), 1, 45, 135, transform=trans)

    tpatch = mtransforms.TransformedPatchPath(patch)
    points = tpatch.get_fully_transformed_path().vertices

    # Changing the transform should change the result.
    trans.scale(2)
    assert_allclose(tpatch.get_fully_transformed_path().vertices, points * 2)

    # Changing the path should change the result (and cancel out the scaling
    # from the transform).
    patch.set_radius(0.5)
    assert_allclose(tpatch.get_fully_transformed_path().vertices, points)


@pytest.mark.parametrize('locked_element', ['x0', 'y0', 'x1', 'y1'])
def test_lockable_bbox(locked_element):
    other_elements = ['x0', 'y0', 'x1', 'y1']
    other_elements.remove(locked_element)

    orig = mtransforms.Bbox.unit()
    locked = mtransforms.LockableBbox(orig, **{locked_element: 2})

    # LockableBbox should keep its locked element as specified in __init__.
    assert getattr(locked, locked_element) == 2
    assert getattr(locked, 'locked_' + locked_element) == 2
    for elem in other_elements:
        assert getattr(locked, elem) == getattr(orig, elem)

    # Changing underlying Bbox should update everything but locked element.
    orig.set_points(orig.get_points() + 10)
    assert getattr(locked, locked_element) == 2
    assert getattr(locked, 'locked_' + locked_element) == 2
    for elem in other_elements:
        assert getattr(locked, elem) == getattr(orig, elem)

    # Unlocking element should revert values back to the underlying Bbox.
    setattr(locked, 'locked_' + locked_element, None)
    assert getattr(locked, 'locked_' + locked_element) is None
    assert np.all(orig.get_points() == locked.get_points())

    # Relocking an element should change its value, but not others.
    setattr(locked, 'locked_' + locked_element, 3)
    assert getattr(locked, locked_element) == 3
    assert getattr(locked, 'locked_' + locked_element) == 3
    for elem in other_elements:
        assert getattr(locked, elem) == getattr(orig, elem)


def test_transformwrapper():
    t = mtransforms.TransformWrapper(mtransforms.Affine2D())
    with pytest.raises(ValueError, match=(
            r"The input and output dims of the new child \(1, 1\) "
            r"do not match those of current child \(2, 2\)")):
        t.set(scale.LogTransform(10))


@check_figures_equal(extensions=["png"])
def test_scale_swapping(fig_test, fig_ref):
    np.random.seed(19680801)
    samples = np.random.normal(size=10)
    x = np.linspace(-5, 5, 10)

    for fig, log_state in zip([fig_test, fig_ref], [True, False]):
        ax = fig.subplots()
        ax.hist(samples, log=log_state, density=True)
        ax.plot(x, np.exp(-(x**2) / 2) / np.sqrt(2 * np.pi))
        fig.canvas.draw()
        ax.set_yscale('linear')


def test_offset_copy_errors():
    with pytest.raises(ValueError,
                       match="'fontsize' is not a valid value for units;"
                             " supported values are 'dots', 'points', 'inches'"):
        mtransforms.offset_copy(None, units='fontsize')

    with pytest.raises(ValueError,
                       match='For units of inches or points a fig kwarg is needed'):
        mtransforms.offset_copy(None, units='inches')


def test_transformedbbox_contains():
    bb = TransformedBbox(Bbox.unit(), Affine2D().rotate_deg(30))
    assert bb.contains(.8, .5)
    assert bb.contains(-.4, .85)
    assert not bb.contains(.9, .5)
    bb = TransformedBbox(Bbox.unit(), Affine2D().translate(.25, .5))
    assert bb.contains(1.25, 1.5)
    assert not bb.fully_contains(1.25, 1.5)
    assert not bb.fully_contains(.1, .1)


def test_interval_contains():
    assert mtransforms.interval_contains((0, 1), 0.5)
    assert mtransforms.interval_contains((0, 1), 0)
    assert mtransforms.interval_contains((0, 1), 1)
    assert not mtransforms.interval_contains((0, 1), -1)
    assert not mtransforms.interval_contains((0, 1), 2)
    assert mtransforms.interval_contains((1, 0), 0.5)


def test_interval_contains_open():
    assert mtransforms.interval_contains_open((0, 1), 0.5)
    assert not mtransforms.interval_contains_open((0, 1), 0)
    assert not mtransforms.interval_contains_open((0, 1), 1)
    assert not mtransforms.interval_contains_open((0, 1), -1)
    assert not mtransforms.interval_contains_open((0, 1), 2)
    assert mtransforms.interval_contains_open((1, 0), 0.5)


def test_scaledrotation_initialization():
    """Test that the ScaledRotation object is initialized correctly."""
    theta = 1.0  # Arbitrary theta value for testing
    trans_shift = MagicMock()  # Mock the trans_shift transformation
    scaled_rot = _ScaledRotation(theta, trans_shift)
    assert scaled_rot._theta == theta
    assert scaled_rot._trans_shift == trans_shift
    assert scaled_rot._mtx is None


def test_scaledrotation_get_matrix_invalid():
    """Test get_matrix when the matrix is invalid and needs recalculation."""
    theta = np.pi / 2
    trans_shift = MagicMock(transform=MagicMock(return_value=[[theta, 0]]))
    scaled_rot = _ScaledRotation(theta, trans_shift)
    scaled_rot._invalid = True
    matrix = scaled_rot.get_matrix()
    trans_shift.transform.assert_called_once_with([[theta, 0]])
    expected_rotation = np.array([[0, -1],
                                  [1,  0]])
    assert matrix is not None
    assert_allclose(matrix[:2, :2], expected_rotation, atol=1e-15)
