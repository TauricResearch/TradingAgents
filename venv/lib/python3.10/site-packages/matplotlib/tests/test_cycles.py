import contextlib
from io import StringIO

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pytest

from cycler import cycler


def test_colorcycle_basic():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(cycler('color', ['r', 'g', 'y']))
    for _ in range(4):
        ax.plot(range(10), range(10))
    assert [l.get_color() for l in ax.lines] == ['r', 'g', 'y', 'r']


def test_marker_cycle():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(cycler('c', ['r', 'g', 'y']) +
                      cycler('marker', ['.', '*', 'x']))
    for _ in range(4):
        ax.plot(range(10), range(10))
    assert [l.get_color() for l in ax.lines] == ['r', 'g', 'y', 'r']
    assert [l.get_marker() for l in ax.lines] == ['.', '*', 'x', '.']


def test_valid_marker_cycles():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(cycler(marker=[1, "+", ".", 4]))


def test_marker_cycle_kwargs_arrays_iterators():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(c=np.array(['r', 'g', 'y']),
                      marker=iter(['.', '*', 'x']))
    for _ in range(4):
        ax.plot(range(10), range(10))
    assert [l.get_color() for l in ax.lines] == ['r', 'g', 'y', 'r']
    assert [l.get_marker() for l in ax.lines] == ['.', '*', 'x', '.']


def test_linestylecycle_basic():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(cycler('ls', ['-', '--', ':']))
    for _ in range(4):
        ax.plot(range(10), range(10))
    assert [l.get_linestyle() for l in ax.lines] == ['-', '--', ':', '-']


def test_fillcycle_basic():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(cycler('c',  ['r', 'g', 'y']) +
                      cycler('hatch', ['xx', 'O', '|-']) +
                      cycler('linestyle', ['-', '--', ':']))
    for _ in range(4):
        ax.fill(range(10), range(10))
    assert ([p.get_facecolor() for p in ax.patches]
            == [mpl.colors.to_rgba(c) for c in ['r', 'g', 'y', 'r']])
    assert [p.get_hatch() for p in ax.patches] == ['xx', 'O', '|-', 'xx']
    assert [p.get_linestyle() for p in ax.patches] == ['-', '--', ':', '-']


def test_fillcycle_ignore():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(cycler('color',  ['r', 'g', 'y']) +
                      cycler('hatch', ['xx', 'O', '|-']) +
                      cycler('marker', ['.', '*', 'D']))
    t = range(10)
    # Should not advance the cycler, even though there is an
    # unspecified property in the cycler "marker".
    # "marker" is not a Polygon property, and should be ignored.
    ax.fill(t, t, 'r', hatch='xx')
    # Allow the cycler to advance, but specify some properties
    ax.fill(t, t, hatch='O')
    ax.fill(t, t)
    ax.fill(t, t)
    assert ([p.get_facecolor() for p in ax.patches]
            == [mpl.colors.to_rgba(c) for c in ['r', 'r', 'g', 'y']])
    assert [p.get_hatch() for p in ax.patches] == ['xx', 'O', 'O', '|-']


def test_property_collision_plot():
    fig, ax = plt.subplots()
    ax.set_prop_cycle('linewidth', [2, 4])
    t = range(10)
    for c in range(1, 4):
        ax.plot(t, t, lw=0.1)
    ax.plot(t, t)
    ax.plot(t, t)
    assert [l.get_linewidth() for l in ax.lines] == [0.1, 0.1, 0.1, 2, 4]


def test_property_collision_fill():
    fig, ax = plt.subplots()
    ax.set_prop_cycle(linewidth=[2, 3, 4, 5, 6], facecolor='bgcmy')
    t = range(10)
    for c in range(1, 4):
        ax.fill(t, t, lw=0.1)
    ax.fill(t, t)
    ax.fill(t, t)
    assert ([p.get_facecolor() for p in ax.patches]
            == [mpl.colors.to_rgba(c) for c in 'bgcmy'])
    assert [p.get_linewidth() for p in ax.patches] == [0.1, 0.1, 0.1, 5, 6]


def test_valid_input_forms():
    fig, ax = plt.subplots()
    # These should not raise an error.
    ax.set_prop_cycle(None)
    ax.set_prop_cycle(cycler('linewidth', [1, 2]))
    ax.set_prop_cycle('color', 'rgywkbcm')
    ax.set_prop_cycle('lw', (1, 2))
    ax.set_prop_cycle('linewidth', [1, 2])
    ax.set_prop_cycle('linewidth', iter([1, 2]))
    ax.set_prop_cycle('linewidth', np.array([1, 2]))
    ax.set_prop_cycle('color', np.array([[1, 0, 0],
                                         [0, 1, 0],
                                         [0, 0, 1]]))
    ax.set_prop_cycle('dashes', [[], [13, 2], [8, 3, 1, 3]])
    ax.set_prop_cycle(lw=[1, 2], color=['k', 'w'], ls=['-', '--'])
    ax.set_prop_cycle(lw=np.array([1, 2]),
                      color=np.array(['k', 'w']),
                      ls=np.array(['-', '--']))


def test_cycle_reset():
    fig, ax = plt.subplots()
    prop0 = StringIO()
    prop1 = StringIO()
    prop2 = StringIO()

    with contextlib.redirect_stdout(prop0):
        plt.getp(ax.plot([1, 2], label="label")[0])

    ax.set_prop_cycle(linewidth=[10, 9, 4])
    with contextlib.redirect_stdout(prop1):
        plt.getp(ax.plot([1, 2], label="label")[0])
    assert prop1.getvalue() != prop0.getvalue()

    ax.set_prop_cycle(None)
    with contextlib.redirect_stdout(prop2):
        plt.getp(ax.plot([1, 2], label="label")[0])
    assert prop2.getvalue() == prop0.getvalue()


def test_invalid_input_forms():
    fig, ax = plt.subplots()

    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle(1)
    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle([1, 2])

    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle('color', 'fish')

    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle('linewidth', 1)
    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle('linewidth', {1, 2})
    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle(linewidth=1, color='r')

    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle('foobar', [1, 2])
    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle(foobar=[1, 2])

    with pytest.raises((TypeError, ValueError)):
        ax.set_prop_cycle(cycler(foobar=[1, 2]))
    with pytest.raises(ValueError):
        ax.set_prop_cycle(cycler(color='rgb', c='cmy'))
