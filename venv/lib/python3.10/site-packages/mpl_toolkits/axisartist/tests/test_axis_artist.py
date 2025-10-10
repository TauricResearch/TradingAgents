import matplotlib.pyplot as plt
from matplotlib.testing.decorators import image_comparison

from mpl_toolkits.axisartist import AxisArtistHelperRectlinear
from mpl_toolkits.axisartist.axis_artist import (AxisArtist, AxisLabel,
                                                 LabelBase, Ticks, TickLabels)


@image_comparison(['axis_artist_ticks.png'], style='default')
def test_ticks():
    fig, ax = plt.subplots()

    ax.xaxis.set_visible(False)
    ax.yaxis.set_visible(False)

    locs_angles = [((i / 10, 0.0), i * 30) for i in range(-1, 12)]

    ticks_in = Ticks(ticksize=10, axis=ax.xaxis)
    ticks_in.set_locs_angles(locs_angles)
    ax.add_artist(ticks_in)

    ticks_out = Ticks(ticksize=10, tick_out=True, color='C3', axis=ax.xaxis)
    ticks_out.set_locs_angles(locs_angles)
    ax.add_artist(ticks_out)


@image_comparison(['axis_artist_labelbase.png'], style='default')
def test_labelbase():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig, ax = plt.subplots()

    ax.plot([0.5], [0.5], "o")

    label = LabelBase(0.5, 0.5, "Test")
    label._ref_angle = -90
    label._offset_radius = 50
    label.set_rotation(-90)
    label.set(ha="center", va="top")
    ax.add_artist(label)


@image_comparison(['axis_artist_ticklabels.png'], style='default')
def test_ticklabels():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig, ax = plt.subplots()

    ax.xaxis.set_visible(False)
    ax.yaxis.set_visible(False)

    ax.plot([0.2, 0.4], [0.5, 0.5], "o")

    ticks = Ticks(ticksize=10, axis=ax.xaxis)
    ax.add_artist(ticks)
    locs_angles_labels = [((0.2, 0.5), -90, "0.2"),
                          ((0.4, 0.5), -120, "0.4")]
    tick_locs_angles = [(xy, a + 180) for xy, a, l in locs_angles_labels]
    ticks.set_locs_angles(tick_locs_angles)

    ticklabels = TickLabels(axis_direction="left")
    ticklabels._locs_angles_labels = locs_angles_labels
    ticklabels.set_pad(10)
    ax.add_artist(ticklabels)

    ax.plot([0.5], [0.5], "s")
    axislabel = AxisLabel(0.5, 0.5, "Test")
    axislabel._offset_radius = 20
    axislabel._ref_angle = 0
    axislabel.set_axis_direction("bottom")
    ax.add_artist(axislabel)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


@image_comparison(['axis_artist.png'], style='default')
def test_axis_artist():
    # Remove this line when this test image is regenerated.
    plt.rcParams['text.kerning_factor'] = 6

    fig, ax = plt.subplots()

    ax.xaxis.set_visible(False)
    ax.yaxis.set_visible(False)

    for loc in ('left', 'right', 'bottom'):
        helper = AxisArtistHelperRectlinear.Fixed(ax, loc=loc)
        axisline = AxisArtist(ax, helper, offset=None, axis_direction=loc)
        ax.add_artist(axisline)

    # Settings for bottom AxisArtist.
    axisline.set_label("TTT")
    axisline.major_ticks.set_tick_out(False)
    axisline.label.set_pad(5)

    ax.set_ylabel("Test")
