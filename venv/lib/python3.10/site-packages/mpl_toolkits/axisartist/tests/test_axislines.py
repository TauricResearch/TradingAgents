import numpy as np
import matplotlib.pyplot as plt
from matplotlib.testing.decorators import image_comparison
from matplotlib.transforms import IdentityTransform

from mpl_toolkits.axisartist.axislines import AxesZero, SubplotZero, Subplot
from mpl_toolkits.axisartist import Axes, SubplotHost


@image_comparison(['SubplotZero.png'], style='default')
def test_SubplotZero():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig = plt.figure()

    ax = SubplotZero(fig, 1, 1, 1)
    fig.add_subplot(ax)

    ax.axis["xzero"].set_visible(True)
    ax.axis["xzero"].label.set_text("Axis Zero")

    for n in ["top", "right"]:
        ax.axis[n].set_visible(False)

    xx = np.arange(0, 2 * np.pi, 0.01)
    ax.plot(xx, np.sin(xx))
    ax.set_ylabel("Test")


@image_comparison(['Subplot.png'], style='default')
def test_Subplot():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig = plt.figure()

    ax = Subplot(fig, 1, 1, 1)
    fig.add_subplot(ax)

    xx = np.arange(0, 2 * np.pi, 0.01)
    ax.plot(xx, np.sin(xx))
    ax.set_ylabel("Test")

    ax.axis["top"].major_ticks.set_tick_out(True)
    ax.axis["bottom"].major_ticks.set_tick_out(True)

    ax.axis["bottom"].set_label("Tk0")


def test_Axes():
    fig = plt.figure()
    ax = Axes(fig, [0.15, 0.1, 0.65, 0.8])
    fig.add_axes(ax)
    ax.plot([1, 2, 3], [0, 1, 2])
    ax.set_xscale('log')
    fig.canvas.draw()


@image_comparison(['ParasiteAxesAuxTrans_meshplot.png'],
                  remove_text=True, style='default', tol=0.075)
def test_ParasiteAxesAuxTrans():
    data = np.ones((6, 6))
    data[2, 2] = 2
    data[0, :] = 0
    data[-2, :] = 0
    data[:, 0] = 0
    data[:, -2] = 0
    x = np.arange(6)
    y = np.arange(6)
    xx, yy = np.meshgrid(x, y)

    funcnames = ['pcolor', 'pcolormesh', 'contourf']

    fig = plt.figure()
    for i, name in enumerate(funcnames):

        ax1 = SubplotHost(fig, 1, 3, i+1)
        fig.add_subplot(ax1)

        ax2 = ax1.get_aux_axes(IdentityTransform(), viewlim_mode=None)
        if name.startswith('pcolor'):
            getattr(ax2, name)(xx, yy, data[:-1, :-1])
        else:
            getattr(ax2, name)(xx, yy, data)
        ax1.set_xlim((0, 5))
        ax1.set_ylim((0, 5))

    ax2.contour(xx, yy, data, colors='k')


@image_comparison(['axisline_style.png'], remove_text=True, style='mpl20')
def test_axisline_style():
    fig = plt.figure(figsize=(2, 2))
    ax = fig.add_subplot(axes_class=AxesZero)
    ax.axis["xzero"].set_axisline_style("-|>")
    ax.axis["xzero"].set_visible(True)
    ax.axis["yzero"].set_axisline_style("->")
    ax.axis["yzero"].set_visible(True)

    for direction in ("left", "right", "bottom", "top"):
        ax.axis[direction].set_visible(False)


@image_comparison(['axisline_style_size_color.png'], remove_text=True,
                  style='mpl20')
def test_axisline_style_size_color():
    fig = plt.figure(figsize=(2, 2))
    ax = fig.add_subplot(axes_class=AxesZero)
    ax.axis["xzero"].set_axisline_style("-|>", size=2.0, facecolor='r')
    ax.axis["xzero"].set_visible(True)
    ax.axis["yzero"].set_axisline_style("->, size=1.5")
    ax.axis["yzero"].set_visible(True)

    for direction in ("left", "right", "bottom", "top"):
        ax.axis[direction].set_visible(False)


@image_comparison(['axisline_style_tight.png'], remove_text=True,
                  style='mpl20')
def test_axisline_style_tight():
    fig = plt.figure(figsize=(2, 2), layout='tight')
    ax = fig.add_subplot(axes_class=AxesZero)
    ax.axis["xzero"].set_axisline_style("-|>", size=5, facecolor='g')
    ax.axis["xzero"].set_visible(True)
    ax.axis["yzero"].set_axisline_style("->, size=8")
    ax.axis["yzero"].set_visible(True)

    for direction in ("left", "right", "bottom", "top"):
        ax.axis[direction].set_visible(False)


@image_comparison(['subplotzero_ylabel.png'], style='mpl20')
def test_subplotzero_ylabel():
    fig = plt.figure()
    ax = fig.add_subplot(111, axes_class=SubplotZero)

    ax.set(xlim=(-3, 7), ylim=(-3, 7), xlabel="x", ylabel="y")

    zero_axis = ax.axis["xzero", "yzero"]
    zero_axis.set_visible(True)  # they are hidden by default

    ax.axis["left", "right", "bottom", "top"].set_visible(False)

    zero_axis.set_axisline_style("->")
