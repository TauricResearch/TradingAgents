import numpy as np

import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.projections import PolarAxes
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import Affine2D, Transform
from matplotlib.testing.decorators import image_comparison

from mpl_toolkits.axisartist import SubplotHost
from mpl_toolkits.axes_grid1.parasite_axes import host_axes_class_factory
from mpl_toolkits.axisartist import angle_helper
from mpl_toolkits.axisartist.axislines import Axes
from mpl_toolkits.axisartist.grid_helper_curvelinear import \
    GridHelperCurveLinear


@image_comparison(['custom_transform.png'], style='default', tol=0.2)
def test_custom_transform():
    class MyTransform(Transform):
        input_dims = output_dims = 2

        def __init__(self, resolution):
            """
            Resolution is the number of steps to interpolate between each input
            line segment to approximate its path in transformed space.
            """
            Transform.__init__(self)
            self._resolution = resolution

        def transform(self, ll):
            x, y = ll.T
            return np.column_stack([x, y - x])

        transform_non_affine = transform

        def transform_path(self, path):
            ipath = path.interpolated(self._resolution)
            return Path(self.transform(ipath.vertices), ipath.codes)

        transform_path_non_affine = transform_path

        def inverted(self):
            return MyTransformInv(self._resolution)

    class MyTransformInv(Transform):
        input_dims = output_dims = 2

        def __init__(self, resolution):
            Transform.__init__(self)
            self._resolution = resolution

        def transform(self, ll):
            x, y = ll.T
            return np.column_stack([x, y + x])

        def inverted(self):
            return MyTransform(self._resolution)

    fig = plt.figure()

    SubplotHost = host_axes_class_factory(Axes)

    tr = MyTransform(1)
    grid_helper = GridHelperCurveLinear(tr)
    ax1 = SubplotHost(fig, 1, 1, 1, grid_helper=grid_helper)
    fig.add_subplot(ax1)

    ax2 = ax1.get_aux_axes(tr, viewlim_mode="equal")
    ax2.plot([3, 6], [5.0, 10.])

    ax1.set_aspect(1.)
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 10)

    ax1.grid(True)


@image_comparison(['polar_box.png'], style='default', tol=0.04)
def test_polar_box():
    fig = plt.figure(figsize=(5, 5))

    # PolarAxes.PolarTransform takes radian. However, we want our coordinate
    # system in degree
    tr = (Affine2D().scale(np.pi / 180., 1.) +
          PolarAxes.PolarTransform(apply_theta_transforms=False))

    # polar projection, which involves cycle, and also has limits in
    # its coordinates, needs a special method to find the extremes
    # (min, max of the coordinate within the view).
    extreme_finder = angle_helper.ExtremeFinderCycle(20, 20,
                                                     lon_cycle=360,
                                                     lat_cycle=None,
                                                     lon_minmax=None,
                                                     lat_minmax=(0, np.inf))

    grid_helper = GridHelperCurveLinear(
        tr,
        extreme_finder=extreme_finder,
        grid_locator1=angle_helper.LocatorDMS(12),
        tick_formatter1=angle_helper.FormatterDMS(),
        tick_formatter2=FuncFormatter(lambda x, p: "eight" if x == 8 else f"{int(x)}"),
    )

    ax1 = SubplotHost(fig, 1, 1, 1, grid_helper=grid_helper)

    ax1.axis["right"].major_ticklabels.set_visible(True)
    ax1.axis["top"].major_ticklabels.set_visible(True)

    # let right axis shows ticklabels for 1st coordinate (angle)
    ax1.axis["right"].get_helper().nth_coord_ticks = 0
    # let bottom axis shows ticklabels for 2nd coordinate (radius)
    ax1.axis["bottom"].get_helper().nth_coord_ticks = 1

    fig.add_subplot(ax1)

    ax1.axis["lat"] = axis = grid_helper.new_floating_axis(0, 45, axes=ax1)
    axis.label.set_text("Test")
    axis.label.set_visible(True)
    axis.get_helper().set_extremes(2, 12)

    ax1.axis["lon"] = axis = grid_helper.new_floating_axis(1, 6, axes=ax1)
    axis.label.set_text("Test 2")
    axis.get_helper().set_extremes(-180, 90)

    # A parasite axes with given transform
    ax2 = ax1.get_aux_axes(tr, viewlim_mode="equal")
    assert ax2.transData == tr + ax1.transData
    # Anything you draw in ax2 will match the ticks and grids of ax1.
    ax2.plot(np.linspace(0, 30, 50), np.linspace(10, 10, 50))

    ax1.set_aspect(1.)
    ax1.set_xlim(-5, 12)
    ax1.set_ylim(-5, 10)

    ax1.grid(True)


# Remove tol & kerning_factor when this test image is regenerated.
@image_comparison(['axis_direction.png'], style='default', tol=0.13)
def test_axis_direction():
    plt.rcParams['text.kerning_factor'] = 6

    fig = plt.figure(figsize=(5, 5))

    # PolarAxes.PolarTransform takes radian. However, we want our coordinate
    # system in degree
    tr = (Affine2D().scale(np.pi / 180., 1.) +
          PolarAxes.PolarTransform(apply_theta_transforms=False))

    # polar projection, which involves cycle, and also has limits in
    # its coordinates, needs a special method to find the extremes
    # (min, max of the coordinate within the view).

    # 20, 20 : number of sampling points along x, y direction
    extreme_finder = angle_helper.ExtremeFinderCycle(20, 20,
                                                     lon_cycle=360,
                                                     lat_cycle=None,
                                                     lon_minmax=None,
                                                     lat_minmax=(0, np.inf),
                                                     )

    grid_locator1 = angle_helper.LocatorDMS(12)
    tick_formatter1 = angle_helper.FormatterDMS()

    grid_helper = GridHelperCurveLinear(tr,
                                        extreme_finder=extreme_finder,
                                        grid_locator1=grid_locator1,
                                        tick_formatter1=tick_formatter1)

    ax1 = SubplotHost(fig, 1, 1, 1, grid_helper=grid_helper)

    for axis in ax1.axis.values():
        axis.set_visible(False)

    fig.add_subplot(ax1)

    ax1.axis["lat1"] = axis = grid_helper.new_floating_axis(
        0, 130,
        axes=ax1, axis_direction="left")
    axis.label.set_text("Test")
    axis.label.set_visible(True)
    axis.get_helper().set_extremes(0.001, 10)

    ax1.axis["lat2"] = axis = grid_helper.new_floating_axis(
        0, 50,
        axes=ax1, axis_direction="right")
    axis.label.set_text("Test")
    axis.label.set_visible(True)
    axis.get_helper().set_extremes(0.001, 10)

    ax1.axis["lon"] = axis = grid_helper.new_floating_axis(
        1, 10,
        axes=ax1, axis_direction="bottom")
    axis.label.set_text("Test 2")
    axis.get_helper().set_extremes(50, 130)
    axis.major_ticklabels.set_axis_direction("top")
    axis.label.set_axis_direction("top")

    grid_helper.grid_finder.grid_locator1.set_params(nbins=5)
    grid_helper.grid_finder.grid_locator2.set_params(nbins=5)

    ax1.set_aspect(1.)
    ax1.set_xlim(-8, 8)
    ax1.set_ylim(-4, 12)

    ax1.grid(True)
