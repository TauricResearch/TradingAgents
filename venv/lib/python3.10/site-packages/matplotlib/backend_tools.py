"""
Abstract base classes define the primitives for Tools.
These tools are used by `matplotlib.backend_managers.ToolManager`

:class:`ToolBase`
    Simple stateless tool

:class:`ToolToggleBase`
    Tool that has two states, only one Toggle tool can be
    active at any given time for the same
    `matplotlib.backend_managers.ToolManager`
"""

import enum
import functools
import re
import time
from types import SimpleNamespace
import uuid
from weakref import WeakKeyDictionary

import numpy as np

import matplotlib as mpl
from matplotlib._pylab_helpers import Gcf
from matplotlib import _api, cbook


class Cursors(enum.IntEnum):  # Must subclass int for the macOS backend.
    """Backend-independent cursor types."""
    POINTER = enum.auto()
    HAND = enum.auto()
    SELECT_REGION = enum.auto()
    MOVE = enum.auto()
    WAIT = enum.auto()
    RESIZE_HORIZONTAL = enum.auto()
    RESIZE_VERTICAL = enum.auto()
cursors = Cursors  # Backcompat.


# _tool_registry, _register_tool_class, and _find_tool_class implement a
# mechanism through which ToolManager.add_tool can determine whether a subclass
# of the requested tool class has been registered (either for the current
# canvas class or for a parent class), in which case that tool subclass will be
# instantiated instead.  This is the mechanism used e.g. to allow different
# GUI backends to implement different specializations for ConfigureSubplots.


_tool_registry = set()


def _register_tool_class(canvas_cls, tool_cls=None):
    """Decorator registering *tool_cls* as a tool class for *canvas_cls*."""
    if tool_cls is None:
        return functools.partial(_register_tool_class, canvas_cls)
    _tool_registry.add((canvas_cls, tool_cls))
    return tool_cls


def _find_tool_class(canvas_cls, tool_cls):
    """Find a subclass of *tool_cls* registered for *canvas_cls*."""
    for canvas_parent in canvas_cls.__mro__:
        for tool_child in _api.recursive_subclasses(tool_cls):
            if (canvas_parent, tool_child) in _tool_registry:
                return tool_child
    return tool_cls


# Views positions tool
_views_positions = 'viewpos'


class ToolBase:
    """
    Base tool class.

    A base tool, only implements `trigger` method or no method at all.
    The tool is instantiated by `matplotlib.backend_managers.ToolManager`.
    """

    default_keymap = None
    """
    Keymap to associate with this tool.

    ``list[str]``: List of keys that will trigger this tool when a keypress
    event is emitted on ``self.figure.canvas``.  Note that this attribute is
    looked up on the instance, and can therefore be a property (this is used
    e.g. by the built-in tools to load the rcParams at instantiation time).
    """

    description = None
    """
    Description of the Tool.

    `str`: Tooltip used if the Tool is included in a Toolbar.
    """

    image = None
    """
    Icon filename.

    ``str | None``: Filename of the Toolbar icon; either absolute, or relative to the
    directory containing the Python source file where the ``Tool.image`` class attribute
    is defined (in the latter case, this cannot be defined as an instance attribute).
    In either case, the extension is optional; leaving it off lets individual backends
    select the icon format they prefer.  If None, the *name* is used as a label in the
    toolbar button.
    """

    def __init__(self, toolmanager, name):
        self._name = name
        self._toolmanager = toolmanager
        self._figure = None

    name = property(
        lambda self: self._name,
        doc="The tool id (str, must be unique among tools of a tool manager).")
    toolmanager = property(
        lambda self: self._toolmanager,
        doc="The `.ToolManager` that controls this tool.")
    canvas = property(
        lambda self: self._figure.canvas if self._figure is not None else None,
        doc="The canvas of the figure affected by this tool, or None.")

    def set_figure(self, figure):
        self._figure = figure

    figure = property(
        lambda self: self._figure,
        # The setter must explicitly call self.set_figure so that subclasses can
        # meaningfully override it.
        lambda self, figure: self.set_figure(figure),
        doc="The Figure affected by this tool, or None.")

    def _make_classic_style_pseudo_toolbar(self):
        """
        Return a placeholder object with a single `canvas` attribute.

        This is useful to reuse the implementations of tools already provided
        by the classic Toolbars.
        """
        return SimpleNamespace(canvas=self.canvas)

    def trigger(self, sender, event, data=None):
        """
        Called when this tool gets used.

        This method is called by `.ToolManager.trigger_tool`.

        Parameters
        ----------
        event : `.Event`
            The canvas event that caused this tool to be called.
        sender : object
            Object that requested the tool to be triggered.
        data : object
            Extra data.
        """
        pass


class ToolToggleBase(ToolBase):
    """
    Toggleable tool.

    Every time it is triggered, it switches between enable and disable.

    Parameters
    ----------
    ``*args``
        Variable length argument to be used by the Tool.
    ``**kwargs``
        `toggled` if present and True, sets the initial state of the Tool
        Arbitrary keyword arguments to be consumed by the Tool
    """

    radio_group = None
    """
    Attribute to group 'radio' like tools (mutually exclusive).

    `str` that identifies the group or **None** if not belonging to a group.
    """

    cursor = None
    """Cursor to use when the tool is active."""

    default_toggled = False
    """Default of toggled state."""

    def __init__(self, *args, **kwargs):
        self._toggled = kwargs.pop('toggled', self.default_toggled)
        super().__init__(*args, **kwargs)

    def trigger(self, sender, event, data=None):
        """Calls `enable` or `disable` based on `toggled` value."""
        if self._toggled:
            self.disable(event)
        else:
            self.enable(event)
        self._toggled = not self._toggled

    def enable(self, event=None):
        """
        Enable the toggle tool.

        `trigger` calls this method when `toggled` is False.
        """
        pass

    def disable(self, event=None):
        """
        Disable the toggle tool.

        `trigger` call this method when `toggled` is True.

        This can happen in different circumstances.

        * Click on the toolbar tool button.
        * Call to `matplotlib.backend_managers.ToolManager.trigger_tool`.
        * Another `ToolToggleBase` derived tool is triggered
          (from the same `.ToolManager`).
        """
        pass

    @property
    def toggled(self):
        """State of the toggled tool."""
        return self._toggled

    def set_figure(self, figure):
        toggled = self.toggled
        if toggled:
            if self.figure:
                self.trigger(self, None)
            else:
                # if no figure the internal state is not changed
                # we change it here so next call to trigger will change it back
                self._toggled = False
        super().set_figure(figure)
        if toggled:
            if figure:
                self.trigger(self, None)
            else:
                # if there is no figure, trigger won't change the internal
                # state we change it back
                self._toggled = True


class ToolSetCursor(ToolBase):
    """
    Change to the current cursor while inaxes.

    This tool, keeps track of all `ToolToggleBase` derived tools, and updates
    the cursor when a tool gets triggered.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id_drag = None
        self._current_tool = None
        self._default_cursor = cursors.POINTER
        self._last_cursor = self._default_cursor
        self.toolmanager.toolmanager_connect('tool_added_event',
                                             self._add_tool_cbk)
        for tool in self.toolmanager.tools.values():  # process current tools
            self._add_tool_cbk(mpl.backend_managers.ToolEvent(
                'tool_added_event', self.toolmanager, tool))

    def set_figure(self, figure):
        if self._id_drag:
            self.canvas.mpl_disconnect(self._id_drag)
        super().set_figure(figure)
        if figure:
            self._id_drag = self.canvas.mpl_connect(
                'motion_notify_event', self._set_cursor_cbk)

    def _add_tool_cbk(self, event):
        """Process every newly added tool."""
        if getattr(event.tool, 'cursor', None) is not None:
            self.toolmanager.toolmanager_connect(
                f'tool_trigger_{event.tool.name}', self._tool_trigger_cbk)

    def _tool_trigger_cbk(self, event):
        self._current_tool = event.tool if event.tool.toggled else None
        self._set_cursor_cbk(event.canvasevent)

    def _set_cursor_cbk(self, event):
        if not event or not self.canvas:
            return
        if (self._current_tool and getattr(event, "inaxes", None)
                and event.inaxes.get_navigate()):
            if self._last_cursor != self._current_tool.cursor:
                self.canvas.set_cursor(self._current_tool.cursor)
                self._last_cursor = self._current_tool.cursor
        elif self._last_cursor != self._default_cursor:
            self.canvas.set_cursor(self._default_cursor)
            self._last_cursor = self._default_cursor


class ToolCursorPosition(ToolBase):
    """
    Send message with the current pointer position.

    This tool runs in the background reporting the position of the cursor.
    """
    def __init__(self, *args, **kwargs):
        self._id_drag = None
        super().__init__(*args, **kwargs)

    def set_figure(self, figure):
        if self._id_drag:
            self.canvas.mpl_disconnect(self._id_drag)
        super().set_figure(figure)
        if figure:
            self._id_drag = self.canvas.mpl_connect(
                'motion_notify_event', self.send_message)

    def send_message(self, event):
        """Call `matplotlib.backend_managers.ToolManager.message_event`."""
        if self.toolmanager.messagelock.locked():
            return

        from matplotlib.backend_bases import NavigationToolbar2
        message = NavigationToolbar2._mouse_event_to_message(event)
        self.toolmanager.message_event(message, self)


class RubberbandBase(ToolBase):
    """Draw and remove a rubberband."""
    def trigger(self, sender, event, data=None):
        """Call `draw_rubberband` or `remove_rubberband` based on data."""
        if not self.figure.canvas.widgetlock.available(sender):
            return
        if data is not None:
            self.draw_rubberband(*data)
        else:
            self.remove_rubberband()

    def draw_rubberband(self, *data):
        """
        Draw rubberband.

        This method must get implemented per backend.
        """
        raise NotImplementedError

    def remove_rubberband(self):
        """
        Remove rubberband.

        This method should get implemented per backend.
        """
        pass


class ToolQuit(ToolBase):
    """Tool to call the figure manager destroy method."""

    description = 'Quit the figure'
    default_keymap = property(lambda self: mpl.rcParams['keymap.quit'])

    def trigger(self, sender, event, data=None):
        Gcf.destroy_fig(self.figure)


class ToolQuitAll(ToolBase):
    """Tool to call the figure manager destroy method."""

    description = 'Quit all figures'
    default_keymap = property(lambda self: mpl.rcParams['keymap.quit_all'])

    def trigger(self, sender, event, data=None):
        Gcf.destroy_all()


class ToolGrid(ToolBase):
    """Tool to toggle the major grids of the figure."""

    description = 'Toggle major grids'
    default_keymap = property(lambda self: mpl.rcParams['keymap.grid'])

    def trigger(self, sender, event, data=None):
        sentinel = str(uuid.uuid4())
        # Trigger grid switching by temporarily setting :rc:`keymap.grid`
        # to a unique key and sending an appropriate event.
        with (cbook._setattr_cm(event, key=sentinel),
              mpl.rc_context({'keymap.grid': sentinel})):
            mpl.backend_bases.key_press_handler(event, self.figure.canvas)


class ToolMinorGrid(ToolBase):
    """Tool to toggle the major and minor grids of the figure."""

    description = 'Toggle major and minor grids'
    default_keymap = property(lambda self: mpl.rcParams['keymap.grid_minor'])

    def trigger(self, sender, event, data=None):
        sentinel = str(uuid.uuid4())
        # Trigger grid switching by temporarily setting :rc:`keymap.grid_minor`
        # to a unique key and sending an appropriate event.
        with (cbook._setattr_cm(event, key=sentinel),
              mpl.rc_context({'keymap.grid_minor': sentinel})):
            mpl.backend_bases.key_press_handler(event, self.figure.canvas)


class ToolFullScreen(ToolBase):
    """Tool to toggle full screen."""

    description = 'Toggle fullscreen mode'
    default_keymap = property(lambda self: mpl.rcParams['keymap.fullscreen'])

    def trigger(self, sender, event, data=None):
        self.figure.canvas.manager.full_screen_toggle()


class AxisScaleBase(ToolToggleBase):
    """Base Tool to toggle between linear and logarithmic."""

    def trigger(self, sender, event, data=None):
        if event.inaxes is None:
            return
        super().trigger(sender, event, data)

    def enable(self, event=None):
        self.set_scale(event.inaxes, 'log')
        self.figure.canvas.draw_idle()

    def disable(self, event=None):
        self.set_scale(event.inaxes, 'linear')
        self.figure.canvas.draw_idle()


class ToolYScale(AxisScaleBase):
    """Tool to toggle between linear and logarithmic scales on the Y axis."""

    description = 'Toggle scale Y axis'
    default_keymap = property(lambda self: mpl.rcParams['keymap.yscale'])

    def set_scale(self, ax, scale):
        ax.set_yscale(scale)


class ToolXScale(AxisScaleBase):
    """Tool to toggle between linear and logarithmic scales on the X axis."""

    description = 'Toggle scale X axis'
    default_keymap = property(lambda self: mpl.rcParams['keymap.xscale'])

    def set_scale(self, ax, scale):
        ax.set_xscale(scale)


class ToolViewsPositions(ToolBase):
    """
    Auxiliary Tool to handle changes in views and positions.

    Runs in the background and should get used by all the tools that
    need to access the figure's history of views and positions, e.g.

    * `ToolZoom`
    * `ToolPan`
    * `ToolHome`
    * `ToolBack`
    * `ToolForward`
    """

    def __init__(self, *args, **kwargs):
        self.views = WeakKeyDictionary()
        self.positions = WeakKeyDictionary()
        self.home_views = WeakKeyDictionary()
        super().__init__(*args, **kwargs)

    def add_figure(self, figure):
        """Add the current figure to the stack of views and positions."""

        if figure not in self.views:
            self.views[figure] = cbook._Stack()
            self.positions[figure] = cbook._Stack()
            self.home_views[figure] = WeakKeyDictionary()
            # Define Home
            self.push_current(figure)
            # Make sure we add a home view for new Axes as they're added
            figure.add_axobserver(lambda fig: self.update_home_views(fig))

    def clear(self, figure):
        """Reset the Axes stack."""
        if figure in self.views:
            self.views[figure].clear()
            self.positions[figure].clear()
            self.home_views[figure].clear()
            self.update_home_views()

    def update_view(self):
        """
        Update the view limits and position for each Axes from the current
        stack position. If any Axes are present in the figure that aren't in
        the current stack position, use the home view limits for those Axes and
        don't update *any* positions.
        """

        views = self.views[self.figure]()
        if views is None:
            return
        pos = self.positions[self.figure]()
        if pos is None:
            return
        home_views = self.home_views[self.figure]
        all_axes = self.figure.get_axes()
        for a in all_axes:
            if a in views:
                cur_view = views[a]
            else:
                cur_view = home_views[a]
            a._set_view(cur_view)

        if set(all_axes).issubset(pos):
            for a in all_axes:
                # Restore both the original and modified positions
                a._set_position(pos[a][0], 'original')
                a._set_position(pos[a][1], 'active')

        self.figure.canvas.draw_idle()

    def push_current(self, figure=None):
        """
        Push the current view limits and position onto their respective stacks.
        """
        if not figure:
            figure = self.figure
        views = WeakKeyDictionary()
        pos = WeakKeyDictionary()
        for a in figure.get_axes():
            views[a] = a._get_view()
            pos[a] = self._axes_pos(a)
        self.views[figure].push(views)
        self.positions[figure].push(pos)

    def _axes_pos(self, ax):
        """
        Return the original and modified positions for the specified Axes.

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            The `.Axes` to get the positions for.

        Returns
        -------
        original_position, modified_position
            A tuple of the original and modified positions.
        """

        return (ax.get_position(True).frozen(),
                ax.get_position().frozen())

    def update_home_views(self, figure=None):
        """
        Make sure that ``self.home_views`` has an entry for all Axes present
        in the figure.
        """

        if not figure:
            figure = self.figure
        for a in figure.get_axes():
            if a not in self.home_views[figure]:
                self.home_views[figure][a] = a._get_view()

    def home(self):
        """Recall the first view and position from the stack."""
        self.views[self.figure].home()
        self.positions[self.figure].home()

    def back(self):
        """Back one step in the stack of views and positions."""
        self.views[self.figure].back()
        self.positions[self.figure].back()

    def forward(self):
        """Forward one step in the stack of views and positions."""
        self.views[self.figure].forward()
        self.positions[self.figure].forward()


class ViewsPositionsBase(ToolBase):
    """Base class for `ToolHome`, `ToolBack` and `ToolForward`."""

    _on_trigger = None

    def trigger(self, sender, event, data=None):
        self.toolmanager.get_tool(_views_positions).add_figure(self.figure)
        getattr(self.toolmanager.get_tool(_views_positions),
                self._on_trigger)()
        self.toolmanager.get_tool(_views_positions).update_view()


class ToolHome(ViewsPositionsBase):
    """Restore the original view limits."""

    description = 'Reset original view'
    image = 'mpl-data/images/home'
    default_keymap = property(lambda self: mpl.rcParams['keymap.home'])
    _on_trigger = 'home'


class ToolBack(ViewsPositionsBase):
    """Move back up the view limits stack."""

    description = 'Back to previous view'
    image = 'mpl-data/images/back'
    default_keymap = property(lambda self: mpl.rcParams['keymap.back'])
    _on_trigger = 'back'


class ToolForward(ViewsPositionsBase):
    """Move forward in the view lim stack."""

    description = 'Forward to next view'
    image = 'mpl-data/images/forward'
    default_keymap = property(lambda self: mpl.rcParams['keymap.forward'])
    _on_trigger = 'forward'


class ConfigureSubplotsBase(ToolBase):
    """Base tool for the configuration of subplots."""

    description = 'Configure subplots'
    image = 'mpl-data/images/subplots'


class SaveFigureBase(ToolBase):
    """Base tool for figure saving."""

    description = 'Save the figure'
    image = 'mpl-data/images/filesave'
    default_keymap = property(lambda self: mpl.rcParams['keymap.save'])


class ZoomPanBase(ToolToggleBase):
    """Base class for `ToolZoom` and `ToolPan`."""
    def __init__(self, *args):
        super().__init__(*args)
        self._button_pressed = None
        self._xypress = None
        self._idPress = None
        self._idRelease = None
        self._idScroll = None
        self.base_scale = 2.
        self.scrollthresh = .5  # .5 second scroll threshold
        self.lastscroll = time.time()-self.scrollthresh

    def enable(self, event=None):
        """Connect press/release events and lock the canvas."""
        self.figure.canvas.widgetlock(self)
        self._idPress = self.figure.canvas.mpl_connect(
            'button_press_event', self._press)
        self._idRelease = self.figure.canvas.mpl_connect(
            'button_release_event', self._release)
        self._idScroll = self.figure.canvas.mpl_connect(
            'scroll_event', self.scroll_zoom)

    def disable(self, event=None):
        """Release the canvas and disconnect press/release events."""
        self._cancel_action()
        self.figure.canvas.widgetlock.release(self)
        self.figure.canvas.mpl_disconnect(self._idPress)
        self.figure.canvas.mpl_disconnect(self._idRelease)
        self.figure.canvas.mpl_disconnect(self._idScroll)

    def trigger(self, sender, event, data=None):
        self.toolmanager.get_tool(_views_positions).add_figure(self.figure)
        super().trigger(sender, event, data)
        new_navigate_mode = self.name.upper() if self.toggled else None
        for ax in self.figure.axes:
            ax.set_navigate_mode(new_navigate_mode)

    def scroll_zoom(self, event):
        # https://gist.github.com/tacaswell/3144287
        if event.inaxes is None:
            return

        if event.button == 'up':
            # deal with zoom in
            scl = self.base_scale
        elif event.button == 'down':
            # deal with zoom out
            scl = 1/self.base_scale
        else:
            # deal with something that should never happen
            scl = 1

        ax = event.inaxes
        ax._set_view_from_bbox([event.x, event.y, scl])

        # If last scroll was done within the timing threshold, delete the
        # previous view
        if (time.time()-self.lastscroll) < self.scrollthresh:
            self.toolmanager.get_tool(_views_positions).back()

        self.figure.canvas.draw_idle()  # force re-draw

        self.lastscroll = time.time()
        self.toolmanager.get_tool(_views_positions).push_current()


class ToolZoom(ZoomPanBase):
    """A Tool for zooming using a rectangle selector."""

    description = 'Zoom to rectangle'
    image = 'mpl-data/images/zoom_to_rect'
    default_keymap = property(lambda self: mpl.rcParams['keymap.zoom'])
    cursor = cursors.SELECT_REGION
    radio_group = 'default'

    def __init__(self, *args):
        super().__init__(*args)
        self._ids_zoom = []

    def _cancel_action(self):
        for zoom_id in self._ids_zoom:
            self.figure.canvas.mpl_disconnect(zoom_id)
        self.toolmanager.trigger_tool('rubberband', self)
        self.figure.canvas.draw_idle()
        self._xypress = None
        self._button_pressed = None
        self._ids_zoom = []
        return

    def _press(self, event):
        """Callback for mouse button presses in zoom-to-rectangle mode."""

        # If we're already in the middle of a zoom, pressing another
        # button works to "cancel"
        if self._ids_zoom:
            self._cancel_action()

        if event.button == 1:
            self._button_pressed = 1
        elif event.button == 3:
            self._button_pressed = 3
        else:
            self._cancel_action()
            return

        x, y = event.x, event.y

        self._xypress = []
        for i, a in enumerate(self.figure.get_axes()):
            if (x is not None and y is not None and a.in_axes(event) and
                    a.get_navigate() and a.can_zoom()):
                self._xypress.append((x, y, a, i, a._get_view()))

        id1 = self.figure.canvas.mpl_connect(
            'motion_notify_event', self._mouse_move)
        id2 = self.figure.canvas.mpl_connect(
            'key_press_event', self._switch_on_zoom_mode)
        id3 = self.figure.canvas.mpl_connect(
            'key_release_event', self._switch_off_zoom_mode)

        self._ids_zoom = id1, id2, id3
        self._zoom_mode = event.key

    def _switch_on_zoom_mode(self, event):
        self._zoom_mode = event.key
        self._mouse_move(event)

    def _switch_off_zoom_mode(self, event):
        self._zoom_mode = None
        self._mouse_move(event)

    def _mouse_move(self, event):
        """Callback for mouse moves in zoom-to-rectangle mode."""

        if self._xypress:
            x, y = event.x, event.y
            lastx, lasty, a, ind, view = self._xypress[0]
            (x1, y1), (x2, y2) = np.clip(
                [[lastx, lasty], [x, y]], a.bbox.min, a.bbox.max)
            if self._zoom_mode == "x":
                y1, y2 = a.bbox.intervaly
            elif self._zoom_mode == "y":
                x1, x2 = a.bbox.intervalx
            self.toolmanager.trigger_tool(
                'rubberband', self, data=(x1, y1, x2, y2))

    def _release(self, event):
        """Callback for mouse button releases in zoom-to-rectangle mode."""

        for zoom_id in self._ids_zoom:
            self.figure.canvas.mpl_disconnect(zoom_id)
        self._ids_zoom = []

        if not self._xypress:
            self._cancel_action()
            return

        done_ax = []

        for cur_xypress in self._xypress:
            x, y = event.x, event.y
            lastx, lasty, a, _ind, view = cur_xypress
            # ignore singular clicks - 5 pixels is a threshold
            if abs(x - lastx) < 5 or abs(y - lasty) < 5:
                self._cancel_action()
                return

            # detect twinx, twiny Axes and avoid double zooming
            twinx = any(a.get_shared_x_axes().joined(a, a1) for a1 in done_ax)
            twiny = any(a.get_shared_y_axes().joined(a, a1) for a1 in done_ax)
            done_ax.append(a)

            if self._button_pressed == 1:
                direction = 'in'
            elif self._button_pressed == 3:
                direction = 'out'
            else:
                continue

            a._set_view_from_bbox((lastx, lasty, x, y), direction,
                                  self._zoom_mode, twinx, twiny)

        self._zoom_mode = None
        self.toolmanager.get_tool(_views_positions).push_current()
        self._cancel_action()


class ToolPan(ZoomPanBase):
    """Pan Axes with left mouse, zoom with right."""

    default_keymap = property(lambda self: mpl.rcParams['keymap.pan'])
    description = 'Pan axes with left mouse, zoom with right'
    image = 'mpl-data/images/move'
    cursor = cursors.MOVE
    radio_group = 'default'

    def __init__(self, *args):
        super().__init__(*args)
        self._id_drag = None

    def _cancel_action(self):
        self._button_pressed = None
        self._xypress = []
        self.figure.canvas.mpl_disconnect(self._id_drag)
        self.toolmanager.messagelock.release(self)
        self.figure.canvas.draw_idle()

    def _press(self, event):
        if event.button == 1:
            self._button_pressed = 1
        elif event.button == 3:
            self._button_pressed = 3
        else:
            self._cancel_action()
            return

        x, y = event.x, event.y

        self._xypress = []
        for i, a in enumerate(self.figure.get_axes()):
            if (x is not None and y is not None and a.in_axes(event) and
                    a.get_navigate() and a.can_pan()):
                a.start_pan(x, y, event.button)
                self._xypress.append((a, i))
                self.toolmanager.messagelock(self)
                self._id_drag = self.figure.canvas.mpl_connect(
                    'motion_notify_event', self._mouse_move)

    def _release(self, event):
        if self._button_pressed is None:
            self._cancel_action()
            return

        self.figure.canvas.mpl_disconnect(self._id_drag)
        self.toolmanager.messagelock.release(self)

        for a, _ind in self._xypress:
            a.end_pan()
        if not self._xypress:
            self._cancel_action()
            return

        self.toolmanager.get_tool(_views_positions).push_current()
        self._cancel_action()

    def _mouse_move(self, event):
        for a, _ind in self._xypress:
            # safer to use the recorded button at the _press than current
            # button: # multiple button can get pressed during motion...
            a.drag_pan(self._button_pressed, event.key, event.x, event.y)
        self.toolmanager.canvas.draw_idle()


class ToolHelpBase(ToolBase):
    description = 'Print tool list, shortcuts and description'
    default_keymap = property(lambda self: mpl.rcParams['keymap.help'])
    image = 'mpl-data/images/help'

    @staticmethod
    def format_shortcut(key_sequence):
        """
        Convert a shortcut string from the notation used in rc config to the
        standard notation for displaying shortcuts, e.g. 'ctrl+a' -> 'Ctrl+A'.
        """
        return (key_sequence if len(key_sequence) == 1 else
                re.sub(r"\+[A-Z]", r"+Shift\g<0>", key_sequence).title())

    def _format_tool_keymap(self, name):
        keymaps = self.toolmanager.get_tool_keymap(name)
        return ", ".join(self.format_shortcut(keymap) for keymap in keymaps)

    def _get_help_entries(self):
        return [(name, self._format_tool_keymap(name), tool.description)
                for name, tool in sorted(self.toolmanager.tools.items())
                if tool.description]

    def _get_help_text(self):
        entries = self._get_help_entries()
        entries = ["{}: {}\n\t{}".format(*entry) for entry in entries]
        return "\n".join(entries)

    def _get_help_html(self):
        fmt = "<tr><td>{}</td><td>{}</td><td>{}</td></tr>"
        rows = [fmt.format(
            "<b>Action</b>", "<b>Shortcuts</b>", "<b>Description</b>")]
        rows += [fmt.format(*row) for row in self._get_help_entries()]
        return ("<style>td {padding: 0px 4px}</style>"
                "<table><thead>" + rows[0] + "</thead>"
                "<tbody>".join(rows[1:]) + "</tbody></table>")


class ToolCopyToClipboardBase(ToolBase):
    """Tool to copy the figure to the clipboard."""

    description = 'Copy the canvas figure to clipboard'
    default_keymap = property(lambda self: mpl.rcParams['keymap.copy'])

    def trigger(self, *args, **kwargs):
        message = "Copy tool is not available"
        self.toolmanager.message_event(message, self)


default_tools = {'home': ToolHome, 'back': ToolBack, 'forward': ToolForward,
                 'zoom': ToolZoom, 'pan': ToolPan,
                 'subplots': ConfigureSubplotsBase,
                 'save': SaveFigureBase,
                 'grid': ToolGrid,
                 'grid_minor': ToolMinorGrid,
                 'fullscreen': ToolFullScreen,
                 'quit': ToolQuit,
                 'quit_all': ToolQuitAll,
                 'xscale': ToolXScale,
                 'yscale': ToolYScale,
                 'position': ToolCursorPosition,
                 _views_positions: ToolViewsPositions,
                 'cursor': ToolSetCursor,
                 'rubberband': RubberbandBase,
                 'help': ToolHelpBase,
                 'copy': ToolCopyToClipboardBase,
                 }

default_toolbar_tools = [['navigation', ['home', 'back', 'forward']],
                         ['zoompan', ['pan', 'zoom', 'subplots']],
                         ['io', ['save', 'help']]]


def add_tools_to_manager(toolmanager, tools=default_tools):
    """
    Add multiple tools to a `.ToolManager`.

    Parameters
    ----------
    toolmanager : `.backend_managers.ToolManager`
        Manager to which the tools are added.
    tools : {str: class_like}, optional
        The tools to add in a {name: tool} dict, see
        `.backend_managers.ToolManager.add_tool` for more info.
    """

    for name, tool in tools.items():
        toolmanager.add_tool(name, tool)


def add_tools_to_container(container, tools=default_toolbar_tools):
    """
    Add multiple tools to the container.

    Parameters
    ----------
    container : Container
        `.backend_bases.ToolContainerBase` object that will get the tools
        added.
    tools : list, optional
        List in the form ``[[group1, [tool1, tool2 ...]], [group2, [...]]]``
        where the tools ``[tool1, tool2, ...]`` will display in group1.
        See `.backend_bases.ToolContainerBase.add_tool` for details.
    """

    for group, grouptools in tools:
        for position, tool in enumerate(grouptools):
            container.add_tool(tool, group, position)
