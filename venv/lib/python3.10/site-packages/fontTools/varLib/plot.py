"""Visualize DesignSpaceDocument and resulting VariationModel."""

from fontTools.varLib.models import VariationModel, supportScalar
from fontTools.designspaceLib import DesignSpaceDocument
from matplotlib import pyplot
from mpl_toolkits.mplot3d import axes3d
from itertools import cycle
import math
import logging
import sys

log = logging.getLogger(__name__)


def stops(support, count=10):
    a, b, c = support

    return (
        [a + (b - a) * i / count for i in range(count)]
        + [b + (c - b) * i / count for i in range(count)]
        + [c]
    )


def _plotLocationsDots(locations, axes, subplot, **kwargs):
    for loc, color in zip(locations, cycle(pyplot.cm.Set1.colors)):
        if len(axes) == 1:
            subplot.plot([loc.get(axes[0], 0)], [1.0], "o", color=color, **kwargs)
        elif len(axes) == 2:
            subplot.plot(
                [loc.get(axes[0], 0)],
                [loc.get(axes[1], 0)],
                [1.0],
                "o",
                color=color,
                **kwargs,
            )
        else:
            raise AssertionError(len(axes))


def plotLocations(locations, fig, names=None, **kwargs):
    n = len(locations)
    cols = math.ceil(n**0.5)
    rows = math.ceil(n / cols)

    if names is None:
        names = [None] * len(locations)

    model = VariationModel(locations)
    names = [names[model.reverseMapping[i]] for i in range(len(names))]

    axes = sorted(locations[0].keys())
    if len(axes) == 1:
        _plotLocations2D(model, axes[0], fig, cols, rows, names=names, **kwargs)
    elif len(axes) == 2:
        _plotLocations3D(model, axes, fig, cols, rows, names=names, **kwargs)
    else:
        raise ValueError("Only 1 or 2 axes are supported")


def _plotLocations2D(model, axis, fig, cols, rows, names, **kwargs):
    subplot = fig.add_subplot(111)
    for i, (support, color, name) in enumerate(
        zip(model.supports, cycle(pyplot.cm.Set1.colors), cycle(names))
    ):
        if name is not None:
            subplot.set_title(name)
        subplot.set_xlabel(axis)
        pyplot.xlim(-1.0, +1.0)

        Xs = support.get(axis, (-1.0, 0.0, +1.0))
        X, Y = [], []
        for x in stops(Xs):
            y = supportScalar({axis: x}, support)
            X.append(x)
            Y.append(y)
        subplot.plot(X, Y, color=color, **kwargs)

        _plotLocationsDots(model.locations, [axis], subplot)


def _plotLocations3D(model, axes, fig, rows, cols, names, **kwargs):
    ax1, ax2 = axes

    axis3D = fig.add_subplot(111, projection="3d")
    for i, (support, color, name) in enumerate(
        zip(model.supports, cycle(pyplot.cm.Set1.colors), cycle(names))
    ):
        if name is not None:
            axis3D.set_title(name)
        axis3D.set_xlabel(ax1)
        axis3D.set_ylabel(ax2)
        pyplot.xlim(-1.0, +1.0)
        pyplot.ylim(-1.0, +1.0)

        Xs = support.get(ax1, (-1.0, 0.0, +1.0))
        Ys = support.get(ax2, (-1.0, 0.0, +1.0))
        for x in stops(Xs):
            X, Y, Z = [], [], []
            for y in Ys:
                z = supportScalar({ax1: x, ax2: y}, support)
                X.append(x)
                Y.append(y)
                Z.append(z)
            axis3D.plot(X, Y, Z, color=color, **kwargs)
        for y in stops(Ys):
            X, Y, Z = [], [], []
            for x in Xs:
                z = supportScalar({ax1: x, ax2: y}, support)
                X.append(x)
                Y.append(y)
                Z.append(z)
            axis3D.plot(X, Y, Z, color=color, **kwargs)

        _plotLocationsDots(model.locations, [ax1, ax2], axis3D)


def plotDocument(doc, fig, **kwargs):
    doc.normalize()
    locations = [s.location for s in doc.sources]
    names = [s.name for s in doc.sources]
    plotLocations(locations, fig, names, **kwargs)


def _plotModelFromMasters2D(model, masterValues, fig, **kwargs):
    assert len(model.axisOrder) == 1
    axis = model.axisOrder[0]

    axis_min = min(loc.get(axis, 0) for loc in model.locations)
    axis_max = max(loc.get(axis, 0) for loc in model.locations)

    import numpy as np

    X = np.arange(axis_min, axis_max, (axis_max - axis_min) / 100)
    Y = []

    for x in X:
        loc = {axis: x}
        v = model.interpolateFromMasters(loc, masterValues)
        Y.append(v)

    subplot = fig.add_subplot(111)
    subplot.plot(X, Y, "-", **kwargs)


def _plotModelFromMasters3D(model, masterValues, fig, **kwargs):
    assert len(model.axisOrder) == 2
    axis1, axis2 = model.axisOrder[0], model.axisOrder[1]

    axis1_min = min(loc.get(axis1, 0) for loc in model.locations)
    axis1_max = max(loc.get(axis1, 0) for loc in model.locations)
    axis2_min = min(loc.get(axis2, 0) for loc in model.locations)
    axis2_max = max(loc.get(axis2, 0) for loc in model.locations)

    import numpy as np

    X = np.arange(axis1_min, axis1_max, (axis1_max - axis1_min) / 100)
    Y = np.arange(axis2_min, axis2_max, (axis2_max - axis2_min) / 100)
    X, Y = np.meshgrid(X, Y)
    Z = []

    for row_x, row_y in zip(X, Y):
        z_row = []
        Z.append(z_row)
        for x, y in zip(row_x, row_y):
            loc = {axis1: x, axis2: y}
            v = model.interpolateFromMasters(loc, masterValues)
            z_row.append(v)
    Z = np.array(Z)

    axis3D = fig.add_subplot(111, projection="3d")
    axis3D.plot_surface(X, Y, Z, **kwargs)


def plotModelFromMasters(model, masterValues, fig, **kwargs):
    """Plot a variation model and set of master values corresponding
    to the locations to the model into a pyplot figure.  Variation
    model must have axisOrder of size 1 or 2."""
    if len(model.axisOrder) == 1:
        _plotModelFromMasters2D(model, masterValues, fig, **kwargs)
    elif len(model.axisOrder) == 2:
        _plotModelFromMasters3D(model, masterValues, fig, **kwargs)
    else:
        raise ValueError("Only 1 or 2 axes are supported")


def main(args=None):
    from fontTools import configLogger

    if args is None:
        args = sys.argv[1:]

    # configure the library logger (for >= WARNING)
    configLogger()
    # comment this out to enable debug messages from logger
    # log.setLevel(logging.DEBUG)

    if len(args) < 1:
        print("usage: fonttools varLib.plot source.designspace", file=sys.stderr)
        print("  or")
        print("usage: fonttools varLib.plot location1 location2 ...", file=sys.stderr)
        print("  or")
        print(
            "usage: fonttools varLib.plot location1=value1 location2=value2 ...",
            file=sys.stderr,
        )
        sys.exit(1)

    fig = pyplot.figure()
    fig.set_tight_layout(True)

    if len(args) == 1 and args[0].endswith(".designspace"):
        doc = DesignSpaceDocument()
        doc.read(args[0])
        plotDocument(doc, fig)
    else:
        axes = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        if "=" not in args[0]:
            locs = [dict(zip(axes, (float(v) for v in s.split(",")))) for s in args]
            plotLocations(locs, fig)
        else:
            locations = []
            masterValues = []
            for arg in args:
                loc, v = arg.split("=")
                locations.append(dict(zip(axes, (float(v) for v in loc.split(",")))))
                masterValues.append(float(v))
            model = VariationModel(locations, axes[: len(locations[0])])
            plotModelFromMasters(model, masterValues, fig)

    pyplot.show()


if __name__ == "__main__":
    import sys

    sys.exit(main())
