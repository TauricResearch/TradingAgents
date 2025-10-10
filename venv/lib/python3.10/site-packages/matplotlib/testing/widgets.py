"""
========================
Widget testing utilities
========================

See also :mod:`matplotlib.tests.test_widgets`.
"""

from unittest import mock

import matplotlib.pyplot as plt


def get_ax():
    """Create a plot and return its Axes."""
    fig, ax = plt.subplots(1, 1)
    ax.plot([0, 200], [0, 200])
    ax.set_aspect(1.0)
    fig.canvas.draw()
    return ax


def noop(*args, **kwargs):
    pass


def mock_event(ax, button=1, xdata=0, ydata=0, key=None, step=1):
    r"""
    Create a mock event that can stand in for `.Event` and its subclasses.

    This event is intended to be used in tests where it can be passed into
    event handling functions.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        The Axes the event will be in.
    xdata : float
        x coord of mouse in data coords.
    ydata : float
        y coord of mouse in data coords.
    button : None or `MouseButton` or {'up', 'down'}
        The mouse button pressed in this event (see also `.MouseEvent`).
    key : None or str
        The key pressed when the mouse event triggered (see also `.KeyEvent`).
    step : int
        Number of scroll steps (positive for 'up', negative for 'down').

    Returns
    -------
    event
        A `.Event`\-like Mock instance.
    """
    event = mock.Mock()
    event.button = button
    event.x, event.y = ax.transData.transform([(xdata, ydata),
                                               (xdata, ydata)])[0]
    event.xdata, event.ydata = xdata, ydata
    event.inaxes = ax
    event.canvas = ax.get_figure(root=True).canvas
    event.key = key
    event.step = step
    event.guiEvent = None
    event.name = 'Custom'
    return event


def do_event(tool, etype, button=1, xdata=0, ydata=0, key=None, step=1):
    """
    Trigger an event on the given tool.

    Parameters
    ----------
    tool : matplotlib.widgets.AxesWidget
    etype : str
        The event to trigger.
    xdata : float
        x coord of mouse in data coords.
    ydata : float
        y coord of mouse in data coords.
    button : None or `MouseButton` or {'up', 'down'}
        The mouse button pressed in this event (see also `.MouseEvent`).
    key : None or str
        The key pressed when the mouse event triggered (see also `.KeyEvent`).
    step : int
        Number of scroll steps (positive for 'up', negative for 'down').
    """
    event = mock_event(tool.ax, button, xdata, ydata, key, step)
    func = getattr(tool, etype)
    func(event)


def click_and_drag(tool, start, end, key=None):
    """
    Helper to simulate a mouse drag operation.

    Parameters
    ----------
    tool : `~matplotlib.widgets.Widget`
    start : [float, float]
        Starting point in data coordinates.
    end : [float, float]
        End point in data coordinates.
    key : None or str
         An optional key that is pressed during the whole operation
         (see also `.KeyEvent`).
    """
    if key is not None:
        # Press key
        do_event(tool, 'on_key_press', xdata=start[0], ydata=start[1],
                 button=1, key=key)
    # Click, move, and release mouse
    do_event(tool, 'press', xdata=start[0], ydata=start[1], button=1)
    do_event(tool, 'onmove', xdata=end[0], ydata=end[1], button=1)
    do_event(tool, 'release', xdata=end[0], ydata=end[1], button=1)
    if key is not None:
        # Release key
        do_event(tool, 'on_key_release', xdata=end[0], ydata=end[1],
                 button=1, key=key)
