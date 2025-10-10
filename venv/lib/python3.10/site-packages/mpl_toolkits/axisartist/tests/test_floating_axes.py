import numpy as np

import matplotlib.pyplot as plt
import matplotlib.projections as mprojections
import matplotlib.transforms as mtransforms
from matplotlib.testing.decorators import image_comparison
from mpl_toolkits.axisartist.axislines import Subplot
from mpl_toolkits.axisartist.floating_axes import (
    FloatingAxes, GridHelperCurveLinear)
from mpl_toolkits.axisartist.grid_finder import FixedLocator
from mpl_toolkits.axisartist import angle_helper


def test_subplot():
    fig = plt.figure(figsize=(5, 5))
    ax = Subplot(fig, 111)
    fig.add_subplot(ax)


# Rather high tolerance to allow ongoing work with floating axes internals;
# remove when image is regenerated.
@image_comparison(['curvelinear3.png'], style='default', tol=5)
def test_curvelinear3():
    fig = plt.figure(figsize=(5, 5))

    tr = (mtransforms.Affine2D().scale(np.pi / 180, 1) +
          mprojections.PolarAxes.PolarTransform(apply_theta_transforms=False))
    grid_helper = GridHelperCurveLinear(
        tr,
        extremes=(0, 360, 10, 3),
        grid_locator1=angle_helper.LocatorDMS(15),
        grid_locator2=FixedLocator([2, 4, 6, 8, 10]),
        tick_formatter1=angle_helper.FormatterDMS(),
        tick_formatter2=None)
    ax1 = fig.add_subplot(axes_class=FloatingAxes, grid_helper=grid_helper)

    r_scale = 10
    tr2 = mtransforms.Affine2D().scale(1, 1 / r_scale) + tr
    grid_helper2 = GridHelperCurveLinear(
        tr2,
        extremes=(0, 360, 10 * r_scale, 3 * r_scale),
        grid_locator2=FixedLocator([30, 60, 90]))

    ax1.axis["right"] = axis = grid_helper2.new_fixed_axis("right", axes=ax1)

    ax1.axis["left"].label.set_text("Test 1")
    ax1.axis["right"].label.set_text("Test 2")
    ax1.axis["left", "right"].set_visible(False)

    axis = grid_helper.new_floating_axis(1, 7, axes=ax1,
                                         axis_direction="bottom")
    ax1.axis["z"] = axis
    axis.toggle(all=True, label=True)
    axis.label.set_text("z = ?")
    axis.label.set_visible(True)
    axis.line.set_color("0.5")

    ax2 = ax1.get_aux_axes(tr)

    xx, yy = [67, 90, 75, 30], [2, 5, 8, 4]
    ax2.scatter(xx, yy)
    l, = ax2.plot(xx, yy, "k-")
    l.set_clip_path(ax1.patch)


# Rather high tolerance to allow ongoing work with floating axes internals;
# remove when image is regenerated.
@image_comparison(['curvelinear4.png'], style='default', tol=0.9)
def test_curvelinear4():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig = plt.figure(figsize=(5, 5))

    tr = (mtransforms.Affine2D().scale(np.pi / 180, 1) +
          mprojections.PolarAxes.PolarTransform(apply_theta_transforms=False))
    grid_helper = GridHelperCurveLinear(
        tr,
        extremes=(120, 30, 10, 0),
        grid_locator1=angle_helper.LocatorDMS(5),
        grid_locator2=FixedLocator([2, 4, 6, 8, 10]),
        tick_formatter1=angle_helper.FormatterDMS(),
        tick_formatter2=None)
    ax1 = fig.add_subplot(axes_class=FloatingAxes, grid_helper=grid_helper)
    ax1.clear()  # Check that clear() also restores the correct limits on ax1.

    ax1.axis["left"].label.set_text("Test 1")
    ax1.axis["right"].label.set_text("Test 2")
    ax1.axis["top"].set_visible(False)

    axis = grid_helper.new_floating_axis(1, 70, axes=ax1,
                                         axis_direction="bottom")
    ax1.axis["z"] = axis
    axis.toggle(all=True, label=True)
    axis.label.set_axis_direction("top")
    axis.label.set_text("z = ?")
    axis.label.set_visible(True)
    axis.line.set_color("0.5")

    ax2 = ax1.get_aux_axes(tr)

    xx, yy = [67, 90, 75, 30], [2, 5, 8, 4]
    ax2.scatter(xx, yy)
    l, = ax2.plot(xx, yy, "k-")
    l.set_clip_path(ax1.patch)


def test_axis_direction():
    # Check that axis direction is propagated on a floating axis
    fig = plt.figure()
    ax = Subplot(fig, 111)
    fig.add_subplot(ax)
    ax.axis['y'] = ax.new_floating_axis(nth_coord=1, value=0,
                                        axis_direction='left')
    assert ax.axis['y']._axis_direction == 'left'
