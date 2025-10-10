import numpy as np
from numpy.testing import assert_allclose
import pytest

import matplotlib as mpl
from matplotlib import pyplot as plt
from matplotlib.testing.decorators import image_comparison, check_figures_equal


@image_comparison(['polar_axes.png'], style='default', tol=0.012)
def test_polar_annotations():
    # You can specify the xypoint and the xytext in different positions and
    # coordinate systems, and optionally turn on a connecting line and mark the
    # point with a marker.  Annotations work on polar axes too.  In the example
    # below, the xy point is in native coordinates (xycoords defaults to
    # 'data').  For a polar axes, this is in (theta, radius) space.  The text
    # in this example is placed in the fractional figure coordinate system.
    # Text keyword args like horizontal and vertical alignment are respected.

    # Setup some data
    r = np.arange(0.0, 1.0, 0.001)
    theta = 2.0 * 2.0 * np.pi * r

    fig = plt.figure()
    ax = fig.add_subplot(polar=True)
    line, = ax.plot(theta, r, color='#ee8d18', lw=3)
    line, = ax.plot((0, 0), (0, 1), color="#0000ff", lw=1)

    ind = 800
    thisr, thistheta = r[ind], theta[ind]
    ax.plot([thistheta], [thisr], 'o')
    ax.annotate('a polar annotation',
                xy=(thistheta, thisr),  # theta, radius
                xytext=(0.05, 0.05),    # fraction, fraction
                textcoords='figure fraction',
                arrowprops=dict(facecolor='black', shrink=0.05),
                horizontalalignment='left',
                verticalalignment='baseline',
                )

    ax.tick_params(axis='x', tick1On=True, tick2On=True, direction='out')


@image_comparison(['polar_coords.png'], style='default', remove_text=True,
                  tol=0.014)
def test_polar_coord_annotations():
    # You can also use polar notation on a cartesian axes.  Here the native
    # coordinate system ('data') is cartesian, so you need to specify the
    # xycoords and textcoords as 'polar' if you want to use (theta, radius).
    el = mpl.patches.Ellipse((0, 0), 10, 20, facecolor='r', alpha=0.5)

    fig = plt.figure()
    ax = fig.add_subplot(aspect='equal')

    ax.add_artist(el)
    el.set_clip_box(ax.bbox)

    ax.annotate('the top',
                xy=(np.pi/2., 10.),      # theta, radius
                xytext=(np.pi/3, 20.),   # theta, radius
                xycoords='polar',
                textcoords='polar',
                arrowprops=dict(facecolor='black', shrink=0.05),
                horizontalalignment='left',
                verticalalignment='baseline',
                clip_on=True,  # clip to the axes bounding box
                )

    ax.set_xlim(-20, 20)
    ax.set_ylim(-20, 20)


@image_comparison(['polar_alignment.png'])
def test_polar_alignment():
    # Test changing the vertical/horizontal alignment of a polar graph.
    angles = np.arange(0, 360, 90)
    grid_values = [0, 0.2, 0.4, 0.6, 0.8, 1]

    fig = plt.figure()
    rect = [0.1, 0.1, 0.8, 0.8]

    horizontal = fig.add_axes(rect, polar=True, label='horizontal')
    horizontal.set_thetagrids(angles)

    vertical = fig.add_axes(rect, polar=True, label='vertical')
    vertical.patch.set_visible(False)

    for i in range(2):
        fig.axes[i].set_rgrids(
            grid_values, angle=angles[i],
            horizontalalignment='left', verticalalignment='top')


def test_polar_twice():
    fig = plt.figure()
    plt.polar([1, 2], [.1, .2])
    plt.polar([3, 4], [.3, .4])
    assert len(fig.axes) == 1, 'More than one polar Axes created.'


@check_figures_equal(extensions=['png'])
def test_polar_wrap(fig_test, fig_ref):
    ax = fig_test.add_subplot(projection="polar")
    ax.plot(np.deg2rad([179, -179]), [0.2, 0.1])
    ax.plot(np.deg2rad([2, -2]), [0.2, 0.1])
    ax = fig_ref.add_subplot(projection="polar")
    ax.plot(np.deg2rad([179, 181]), [0.2, 0.1])
    ax.plot(np.deg2rad([2, 358]), [0.2, 0.1])


@check_figures_equal(extensions=['png'])
def test_polar_units_1(fig_test, fig_ref):
    import matplotlib.testing.jpl_units as units
    units.register()
    xs = [30.0, 45.0, 60.0, 90.0]
    ys = [1.0, 2.0, 3.0, 4.0]

    plt.figure(fig_test.number)
    plt.polar([x * units.deg for x in xs], ys)

    ax = fig_ref.add_subplot(projection="polar")
    ax.plot(np.deg2rad(xs), ys)
    ax.set(xlabel="deg")


@check_figures_equal(extensions=['png'])
def test_polar_units_2(fig_test, fig_ref):
    import matplotlib.testing.jpl_units as units
    units.register()
    xs = [30.0, 45.0, 60.0, 90.0]
    xs_deg = [x * units.deg for x in xs]
    ys = [1.0, 2.0, 3.0, 4.0]
    ys_km = [y * units.km for y in ys]

    plt.figure(fig_test.number)
    # test {theta,r}units.
    plt.polar(xs_deg, ys_km, thetaunits="rad", runits="km")
    assert isinstance(plt.gca().xaxis.get_major_formatter(),
                      units.UnitDblFormatter)

    ax = fig_ref.add_subplot(projection="polar")
    ax.plot(np.deg2rad(xs), ys)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter("{:.12}".format))
    ax.set(xlabel="rad", ylabel="km")


@image_comparison(['polar_rmin.png'], style='default')
def test_polar_rmin():
    r = np.arange(0, 3.0, 0.01)
    theta = 2*np.pi*r

    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)
    ax.plot(theta, r)
    ax.set_rmax(2.0)
    ax.set_rmin(0.5)


@image_comparison(['polar_negative_rmin.png'], style='default')
def test_polar_negative_rmin():
    r = np.arange(-3.0, 0.0, 0.01)
    theta = 2*np.pi*r

    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)
    ax.plot(theta, r)
    ax.set_rmax(0.0)
    ax.set_rmin(-3.0)


@image_comparison(['polar_rorigin.png'], style='default')
def test_polar_rorigin():
    r = np.arange(0, 3.0, 0.01)
    theta = 2*np.pi*r

    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)
    ax.plot(theta, r)
    ax.set_rmax(2.0)
    ax.set_rmin(0.5)
    ax.set_rorigin(0.0)


@image_comparison(['polar_invertedylim.png'], style='default')
def test_polar_invertedylim():
    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)
    ax.set_ylim(2, 0)


@image_comparison(['polar_invertedylim_rorigin.png'], style='default')
def test_polar_invertedylim_rorigin():
    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)
    ax.yaxis.set_inverted(True)
    # Set the rlims to inverted (2, 0) without calling set_rlim, to check that
    # viewlims are correctly unstaled before draw()ing.
    ax.plot([0, 0], [0, 2], c="none")
    ax.margins(0)
    ax.set_rorigin(3)


@image_comparison(['polar_theta_position.png'], style='default')
def test_polar_theta_position():
    r = np.arange(0, 3.0, 0.01)
    theta = 2*np.pi*r

    fig = plt.figure()
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)
    ax.plot(theta, r)
    ax.set_theta_zero_location("NW", 30)
    ax.set_theta_direction('clockwise')


@image_comparison(['polar_rlabel_position.png'], style='default')
def test_polar_rlabel_position():
    fig = plt.figure()
    ax = fig.add_subplot(projection='polar')
    ax.set_rlabel_position(315)
    ax.tick_params(rotation='auto')


@image_comparison(['polar_title_position.png'], style='mpl20')
def test_polar_title_position():
    fig = plt.figure()
    ax = fig.add_subplot(projection='polar')
    ax.set_title('foo')


@image_comparison(['polar_theta_wedge.png'], style='default')
def test_polar_theta_limits():
    r = np.arange(0, 3.0, 0.01)
    theta = 2*np.pi*r

    theta_mins = np.arange(15.0, 361.0, 90.0)
    theta_maxs = np.arange(50.0, 361.0, 90.0)
    DIRECTIONS = ('out', 'in', 'inout')

    fig, axs = plt.subplots(len(theta_mins), len(theta_maxs),
                            subplot_kw={'polar': True},
                            figsize=(8, 6))

    for i, start in enumerate(theta_mins):
        for j, end in enumerate(theta_maxs):
            ax = axs[i, j]
            ax.plot(theta, r)
            if start < end:
                ax.set_thetamin(start)
                ax.set_thetamax(end)
            else:
                # Plot with clockwise orientation instead.
                ax.set_thetamin(end)
                ax.set_thetamax(start)
                ax.set_theta_direction('clockwise')
            ax.tick_params(tick1On=True, tick2On=True,
                           direction=DIRECTIONS[i % len(DIRECTIONS)],
                           rotation='auto')
            ax.yaxis.set_tick_params(label2On=True, rotation='auto')
            ax.xaxis.get_major_locator().base.set_params(  # backcompat
                steps=[1, 2, 2.5, 5, 10])


@check_figures_equal(extensions=["png"])
def test_polar_rlim(fig_test, fig_ref):
    ax = fig_test.subplots(subplot_kw={'polar': True})
    ax.set_rlim(top=10)
    ax.set_rlim(bottom=.5)

    ax = fig_ref.subplots(subplot_kw={'polar': True})
    ax.set_rmax(10.)
    ax.set_rmin(.5)


@check_figures_equal(extensions=["png"])
def test_polar_rlim_bottom(fig_test, fig_ref):
    ax = fig_test.subplots(subplot_kw={'polar': True})
    ax.set_rlim(bottom=[.5, 10])

    ax = fig_ref.subplots(subplot_kw={'polar': True})
    ax.set_rmax(10.)
    ax.set_rmin(.5)


def test_polar_rlim_zero():
    ax = plt.figure().add_subplot(projection='polar')
    ax.plot(np.arange(10), np.arange(10) + .01)
    assert ax.get_ylim()[0] == 0


def test_polar_no_data():
    plt.subplot(projection="polar")
    ax = plt.gca()
    assert ax.get_rmin() == 0 and ax.get_rmax() == 1
    plt.close("all")
    # Used to behave differently (by triggering an autoscale with no data).
    plt.polar()
    ax = plt.gca()
    assert ax.get_rmin() == 0 and ax.get_rmax() == 1


def test_polar_default_log_lims():
    plt.subplot(projection='polar')
    ax = plt.gca()
    ax.set_rscale('log')
    assert ax.get_rmin() > 0


def test_polar_not_datalim_adjustable():
    ax = plt.figure().add_subplot(projection="polar")
    with pytest.raises(ValueError):
        ax.set_adjustable("datalim")


def test_polar_gridlines():
    fig = plt.figure()
    ax = fig.add_subplot(polar=True)
    # make all major grid lines lighter, only x grid lines set in 2.1.0
    ax.grid(alpha=0.2)
    # hide y tick labels, no effect in 2.1.0
    plt.setp(ax.yaxis.get_ticklabels(), visible=False)
    fig.canvas.draw()
    assert ax.xaxis.majorTicks[0].gridline.get_alpha() == .2
    assert ax.yaxis.majorTicks[0].gridline.get_alpha() == .2


def test_get_tightbbox_polar():
    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
    fig.canvas.draw()
    bb = ax.get_tightbbox(fig.canvas.get_renderer())
    assert_allclose(
        bb.extents, [107.7778,  29.2778, 539.7847, 450.7222], rtol=1e-03)


@check_figures_equal(extensions=["png"])
def test_polar_interpolation_steps_constant_r(fig_test, fig_ref):
    # Check that an extra half-turn doesn't make any difference -- modulo
    # antialiasing, which we disable here.
    p1 = (fig_test.add_subplot(121, projection="polar")
          .bar([0], [1], 3*np.pi, edgecolor="none", antialiased=False))
    p2 = (fig_test.add_subplot(122, projection="polar")
          .bar([0], [1], -3*np.pi, edgecolor="none", antialiased=False))
    p3 = (fig_ref.add_subplot(121, projection="polar")
          .bar([0], [1], 2*np.pi, edgecolor="none", antialiased=False))
    p4 = (fig_ref.add_subplot(122, projection="polar")
          .bar([0], [1], -2*np.pi, edgecolor="none", antialiased=False))


@check_figures_equal(extensions=["png"])
def test_polar_interpolation_steps_variable_r(fig_test, fig_ref):
    l, = fig_test.add_subplot(projection="polar").plot([0, np.pi/2], [1, 2])
    l.get_path()._interpolation_steps = 100
    fig_ref.add_subplot(projection="polar").plot(
        np.linspace(0, np.pi/2, 101), np.linspace(1, 2, 101))


def test_thetalim_valid_invalid():
    ax = plt.subplot(projection='polar')
    ax.set_thetalim(0, 2 * np.pi)  # doesn't raise.
    ax.set_thetalim(thetamin=800, thetamax=440)  # doesn't raise.
    with pytest.raises(ValueError,
                       match='angle range must be less than a full circle'):
        ax.set_thetalim(0, 3 * np.pi)
    with pytest.raises(ValueError,
                       match='angle range must be less than a full circle'):
        ax.set_thetalim(thetamin=800, thetamax=400)


def test_thetalim_args():
    ax = plt.subplot(projection='polar')
    ax.set_thetalim(0, 1)
    assert tuple(np.radians((ax.get_thetamin(), ax.get_thetamax()))) == (0, 1)
    ax.set_thetalim((2, 3))
    assert tuple(np.radians((ax.get_thetamin(), ax.get_thetamax()))) == (2, 3)


def test_default_thetalocator():
    # Ideally we would check AAAABBC, but the smallest axes currently puts a
    # single tick at 150° because MaxNLocator doesn't have a way to accept 15°
    # while rejecting 150°.
    fig, axs = plt.subplot_mosaic(
        "AAAABB.", subplot_kw={"projection": "polar"})
    for ax in axs.values():
        ax.set_thetalim(0, np.pi)
    for ax in axs.values():
        ticklocs = np.degrees(ax.xaxis.get_majorticklocs()).tolist()
        assert pytest.approx(90) in ticklocs
        assert pytest.approx(100) not in ticklocs


def test_axvspan():
    ax = plt.subplot(projection="polar")
    span = ax.axvspan(0, np.pi/4)
    assert span.get_path()._interpolation_steps > 1


@check_figures_equal(extensions=["png"])
def test_remove_shared_polar(fig_ref, fig_test):
    # Removing shared polar axes used to crash.  Test removing them, keeping in
    # both cases just the lower left axes of a grid to avoid running into a
    # separate issue (now being fixed) of ticklabel visibility for shared axes.
    axs = fig_ref.subplots(
        2, 2, sharex=True, subplot_kw={"projection": "polar"})
    for i in [0, 1, 3]:
        axs.flat[i].remove()
    axs = fig_test.subplots(
        2, 2, sharey=True, subplot_kw={"projection": "polar"})
    for i in [0, 1, 3]:
        axs.flat[i].remove()


def test_shared_polar_keeps_ticklabels():
    fig, axs = plt.subplots(
        2, 2, subplot_kw={"projection": "polar"}, sharex=True, sharey=True)
    fig.canvas.draw()
    assert axs[0, 1].xaxis.majorTicks[0].get_visible()
    assert axs[0, 1].yaxis.majorTicks[0].get_visible()
    fig, axs = plt.subplot_mosaic(
        "ab\ncd", subplot_kw={"projection": "polar"}, sharex=True, sharey=True)
    fig.canvas.draw()
    assert axs["b"].xaxis.majorTicks[0].get_visible()
    assert axs["b"].yaxis.majorTicks[0].get_visible()


def test_axvline_axvspan_do_not_modify_rlims():
    ax = plt.subplot(projection="polar")
    ax.axvspan(0, 1)
    ax.axvline(.5)
    ax.plot([.1, .2])
    assert ax.get_ylim() == (0, .2)


def test_cursor_precision():
    ax = plt.subplot(projection="polar")
    # Higher radii correspond to higher theta-precisions.
    assert ax.format_coord(0, 0.005) == "θ=0.0π (0°), r=0.005"
    assert ax.format_coord(0, .1) == "θ=0.00π (0°), r=0.100"
    assert ax.format_coord(0, 1) == "θ=0.000π (0.0°), r=1.000"
    assert ax.format_coord(1, 0.005) == "θ=0.3π (57°), r=0.005"
    assert ax.format_coord(1, .1) == "θ=0.32π (57°), r=0.100"
    assert ax.format_coord(1, 1) == "θ=0.318π (57.3°), r=1.000"
    assert ax.format_coord(2, 0.005) == "θ=0.6π (115°), r=0.005"
    assert ax.format_coord(2, .1) == "θ=0.64π (115°), r=0.100"
    assert ax.format_coord(2, 1) == "θ=0.637π (114.6°), r=1.000"


def test_custom_fmt_data():
    ax = plt.subplot(projection="polar")
    def millions(x):
        return '$%1.1fM' % (x*1e-6)

    # Test only x formatter
    ax.fmt_xdata = None
    ax.fmt_ydata = millions
    assert ax.format_coord(12, 2e7) == "θ=3.8197186342π (687.54935416°), r=$20.0M"
    assert ax.format_coord(1234, 2e6) == "θ=392.794399551π (70702.9919191°), r=$2.0M"
    assert ax.format_coord(3, 100) == "θ=0.95493π (171.887°), r=$0.0M"

    # Test only y formatter
    ax.fmt_xdata = millions
    ax.fmt_ydata = None
    assert ax.format_coord(2e5, 1) == "θ=$0.2M, r=1.000"
    assert ax.format_coord(1, .1) == "θ=$0.0M, r=0.100"
    assert ax.format_coord(1e6, 0.005) == "θ=$1.0M, r=0.005"

    # Test both x and y formatters
    ax.fmt_xdata = millions
    ax.fmt_ydata = millions
    assert ax.format_coord(2e6, 2e4*3e5) == "θ=$2.0M, r=$6000.0M"
    assert ax.format_coord(1e18, 12891328123) == "θ=$1000000000000.0M, r=$12891.3M"
    assert ax.format_coord(63**7, 1081968*1024) == "θ=$3938980.6M, r=$1107.9M"


@image_comparison(['polar_log.png'], style='default')
def test_polar_log():
    fig = plt.figure()
    ax = fig.add_subplot(polar=True)

    ax.set_rscale('log')
    ax.set_rlim(1, 1000)

    n = 100
    ax.plot(np.linspace(0, 2 * np.pi, n), np.logspace(0, 2, n))


@check_figures_equal()
def test_polar_log_rorigin(fig_ref, fig_test):
    # Test that equivalent linear and log radial settings give the same axes patch
    # and spines.
    ax_ref = fig_ref.add_subplot(projection='polar', facecolor='red')
    ax_ref.set_rlim(0, 2)
    ax_ref.set_rorigin(-3)
    ax_ref.set_rticks(np.linspace(0, 2, 5))

    ax_test = fig_test.add_subplot(projection='polar', facecolor='red')
    ax_test.set_rscale('log')
    ax_test.set_rlim(1, 100)
    ax_test.set_rorigin(10**-3)
    ax_test.set_rticks(np.logspace(0, 2, 5))

    for ax in ax_ref, ax_test:
        # Radial tick labels should be the only difference, so turn them off.
        ax.tick_params(labelleft=False)


def test_polar_neg_theta_lims():
    fig = plt.figure()
    ax = fig.add_subplot(projection='polar')
    ax.set_thetalim(-np.pi, np.pi)
    labels = [l.get_text() for l in ax.xaxis.get_ticklabels()]
    assert labels == ['-180°', '-135°', '-90°', '-45°', '0°', '45°', '90°', '135°']


@pytest.mark.parametrize("order", ["before", "after"])
@image_comparison(baseline_images=['polar_errorbar.png'], remove_text=True,
                  style='mpl20')
def test_polar_errorbar(order):
    theta = np.arange(0, 2 * np.pi, np.pi / 8)
    r = theta / np.pi / 2 + 0.5
    fig = plt.figure(figsize=(5, 5))
    ax = fig.add_subplot(projection='polar')
    if order == "before":
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.errorbar(theta, r, xerr=0.1, yerr=0.1, capsize=7, fmt="o", c="seagreen")
    else:
        ax.errorbar(theta, r, xerr=0.1, yerr=0.1, capsize=7, fmt="o", c="seagreen")
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
