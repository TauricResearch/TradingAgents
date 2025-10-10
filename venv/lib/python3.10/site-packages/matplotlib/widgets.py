"""
GUI neutral widgets
===================

Widgets that are designed to work for any of the GUI backends.
All of these widgets require you to predefine an `~.axes.Axes`
instance and pass that as the first parameter.  Matplotlib doesn't try to
be too smart with respect to layout -- you will have to figure out how
wide and tall you want your Axes to be to accommodate your widget.
"""

from contextlib import ExitStack
import copy
import itertools
from numbers import Integral, Number

from cycler import cycler
import numpy as np

import matplotlib as mpl
from . import (_api, _docstring, backend_tools, cbook, collections, colors,
               text as mtext, ticker, transforms)
from .lines import Line2D
from .patches import Rectangle, Ellipse, Polygon
from .transforms import TransformedPatchPath, Affine2D


class LockDraw:
    """
    Some widgets, like the cursor, draw onto the canvas, and this is not
    desirable under all circumstances, like when the toolbar is in zoom-to-rect
    mode and drawing a rectangle.  To avoid this, a widget can acquire a
    canvas' lock with ``canvas.widgetlock(widget)`` before drawing on the
    canvas; this will prevent other widgets from doing so at the same time (if
    they also try to acquire the lock first).
    """

    def __init__(self):
        self._owner = None

    def __call__(self, o):
        """Reserve the lock for *o*."""
        if not self.available(o):
            raise ValueError('already locked')
        self._owner = o

    def release(self, o):
        """Release the lock from *o*."""
        if not self.available(o):
            raise ValueError('you do not own this lock')
        self._owner = None

    def available(self, o):
        """Return whether drawing is available to *o*."""
        return not self.locked() or self.isowner(o)

    def isowner(self, o):
        """Return whether *o* owns this lock."""
        return self._owner is o

    def locked(self):
        """Return whether the lock is currently held by an owner."""
        return self._owner is not None


class Widget:
    """
    Abstract base class for GUI neutral widgets.
    """
    drawon = True
    eventson = True
    _active = True

    def set_active(self, active):
        """Set whether the widget is active."""
        self._active = active

    def get_active(self):
        """Get whether the widget is active."""
        return self._active

    # set_active is overridden by SelectorWidgets.
    active = property(get_active, set_active, doc="Is the widget active?")

    def ignore(self, event):
        """
        Return whether *event* should be ignored.

        This method should be called at the beginning of any event callback.
        """
        return not self.active


class AxesWidget(Widget):
    """
    Widget connected to a single `~matplotlib.axes.Axes`.

    To guarantee that the widget remains responsive and not garbage-collected,
    a reference to the object should be maintained by the user.

    This is necessary because the callback registry
    maintains only weak-refs to the functions, which are member
    functions of the widget.  If there are no references to the widget
    object it may be garbage collected which will disconnect the callbacks.

    Attributes
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.
    canvas : `~matplotlib.backend_bases.FigureCanvasBase`
        The parent figure canvas for the widget.
    active : bool
        If False, the widget does not respond to events.
    """

    def __init__(self, ax):
        self.ax = ax
        self._cids = []

    canvas = property(lambda self: self.ax.get_figure(root=True).canvas)

    def connect_event(self, event, callback):
        """
        Connect a callback function with an event.

        This should be used in lieu of ``figure.canvas.mpl_connect`` since this
        function stores callback ids for later clean up.
        """
        cid = self.canvas.mpl_connect(event, callback)
        self._cids.append(cid)

    def disconnect_events(self):
        """Disconnect all events created by this widget."""
        for c in self._cids:
            self.canvas.mpl_disconnect(c)

    def _get_data_coords(self, event):
        """Return *event*'s data coordinates in this widget's Axes."""
        # This method handles the possibility that event.inaxes != self.ax (which may
        # occur if multiple Axes are overlaid), in which case event.xdata/.ydata will
        # be wrong.  Note that we still special-case the common case where
        # event.inaxes == self.ax and avoid re-running the inverse data transform,
        # because that can introduce floating point errors for synthetic events.
        return ((event.xdata, event.ydata) if event.inaxes is self.ax
                else self.ax.transData.inverted().transform((event.x, event.y)))


class Button(AxesWidget):
    """
    A GUI neutral button.

    For the button to remain responsive you must keep a reference to it.
    Call `.on_clicked` to connect to the button.

    Attributes
    ----------
    ax
        The `~.axes.Axes` the button renders into.
    label
        A `.Text` instance.
    color
        The color of the button when not hovering.
    hovercolor
        The color of the button when hovering.
    """

    def __init__(self, ax, label, image=None,
                 color='0.85', hovercolor='0.95', *, useblit=True):
        """
        Parameters
        ----------
        ax : `~matplotlib.axes.Axes`
            The `~.axes.Axes` instance the button will be placed into.
        label : str
            The button text.
        image : array-like or PIL Image
            The image to place in the button, if not *None*.  The parameter is
            directly forwarded to `~.axes.Axes.imshow`.
        color : :mpltype:`color`
            The color of the button when not activated.
        hovercolor : :mpltype:`color`
            The color of the button when the mouse is over it.
        useblit : bool, default: True
            Use blitting for faster drawing if supported by the backend.
            See the tutorial :ref:`blitting` for details.

            .. versionadded:: 3.7
        """
        super().__init__(ax)

        if image is not None:
            ax.imshow(image)
        self.label = ax.text(0.5, 0.5, label,
                             verticalalignment='center',
                             horizontalalignment='center',
                             transform=ax.transAxes)

        self._useblit = useblit and self.canvas.supports_blit

        self._observers = cbook.CallbackRegistry(signals=["clicked"])

        self.connect_event('button_press_event', self._click)
        self.connect_event('button_release_event', self._release)
        self.connect_event('motion_notify_event', self._motion)
        ax.set_navigate(False)
        ax.set_facecolor(color)
        ax.set_xticks([])
        ax.set_yticks([])
        self.color = color
        self.hovercolor = hovercolor

    def _click(self, event):
        if not self.eventson or self.ignore(event) or not self.ax.contains(event)[0]:
            return
        if event.canvas.mouse_grabber != self.ax:
            event.canvas.grab_mouse(self.ax)

    def _release(self, event):
        if self.ignore(event) or event.canvas.mouse_grabber != self.ax:
            return
        event.canvas.release_mouse(self.ax)
        if self.eventson and self.ax.contains(event)[0]:
            self._observers.process('clicked', event)

    def _motion(self, event):
        if self.ignore(event):
            return
        c = self.hovercolor if self.ax.contains(event)[0] else self.color
        if not colors.same_color(c, self.ax.get_facecolor()):
            self.ax.set_facecolor(c)
            if self.drawon:
                if self._useblit:
                    self.ax.draw_artist(self.ax)
                    self.canvas.blit(self.ax.bbox)
                else:
                    self.canvas.draw()

    def on_clicked(self, func):
        """
        Connect the callback function *func* to button click events.

        Returns a connection id, which can be used to disconnect the callback.
        """
        return self._observers.connect('clicked', lambda event: func(event))

    def disconnect(self, cid):
        """Remove the callback function with connection id *cid*."""
        self._observers.disconnect(cid)


class SliderBase(AxesWidget):
    """
    The base class for constructing Slider widgets. Not intended for direct
    usage.

    For the slider to remain responsive you must maintain a reference to it.
    """
    def __init__(self, ax, orientation, closedmin, closedmax,
                 valmin, valmax, valfmt, dragging, valstep):
        if ax.name == '3d':
            raise ValueError('Sliders cannot be added to 3D Axes')

        super().__init__(ax)
        _api.check_in_list(['horizontal', 'vertical'], orientation=orientation)

        self.orientation = orientation
        self.closedmin = closedmin
        self.closedmax = closedmax
        self.valmin = valmin
        self.valmax = valmax
        self.valstep = valstep
        self.drag_active = False
        self.valfmt = valfmt

        if orientation == "vertical":
            ax.set_ylim((valmin, valmax))
            axis = ax.yaxis
        else:
            ax.set_xlim((valmin, valmax))
            axis = ax.xaxis

        self._fmt = axis.get_major_formatter()
        if not isinstance(self._fmt, ticker.ScalarFormatter):
            self._fmt = ticker.ScalarFormatter()
            self._fmt.set_axis(axis)
        self._fmt.set_useOffset(False)  # No additive offset.
        self._fmt.set_useMathText(True)  # x sign before multiplicative offset.

        ax.set_axis_off()
        ax.set_navigate(False)

        self.connect_event("button_press_event", self._update)
        self.connect_event("button_release_event", self._update)
        if dragging:
            self.connect_event("motion_notify_event", self._update)
        self._observers = cbook.CallbackRegistry(signals=["changed"])

    def _stepped_value(self, val):
        """Return *val* coerced to closest number in the ``valstep`` grid."""
        if isinstance(self.valstep, Number):
            val = (self.valmin
                   + round((val - self.valmin) / self.valstep) * self.valstep)
        elif self.valstep is not None:
            valstep = np.asanyarray(self.valstep)
            if valstep.ndim != 1:
                raise ValueError(
                    f"valstep must have 1 dimension but has {valstep.ndim}"
                )
            val = valstep[np.argmin(np.abs(valstep - val))]
        return val

    def disconnect(self, cid):
        """
        Remove the observer with connection id *cid*.

        Parameters
        ----------
        cid : int
            Connection id of the observer to be removed.
        """
        self._observers.disconnect(cid)

    def reset(self):
        """Reset the slider to the initial value."""
        if np.any(self.val != self.valinit):
            self.set_val(self.valinit)


class Slider(SliderBase):
    """
    A slider representing a floating point range.

    Create a slider from *valmin* to *valmax* in Axes *ax*. For the slider to
    remain responsive you must maintain a reference to it. Call
    :meth:`on_changed` to connect to the slider event.

    Attributes
    ----------
    val : float
        Slider value.
    """

    def __init__(self, ax, label, valmin, valmax, *, valinit=0.5, valfmt=None,
                 closedmin=True, closedmax=True, slidermin=None,
                 slidermax=None, dragging=True, valstep=None,
                 orientation='horizontal', initcolor='r',
                 track_color='lightgrey', handle_style=None, **kwargs):
        """
        Parameters
        ----------
        ax : Axes
            The Axes to put the slider in.

        label : str
            Slider label.

        valmin : float
            The minimum value of the slider.

        valmax : float
            The maximum value of the slider.

        valinit : float, default: 0.5
            The slider initial position.

        valfmt : str, default: None
            %-format string used to format the slider value.  If None, a
            `.ScalarFormatter` is used instead.

        closedmin : bool, default: True
            Whether the slider interval is closed on the bottom.

        closedmax : bool, default: True
            Whether the slider interval is closed on the top.

        slidermin : Slider, default: None
            Do not allow the current slider to have a value less than
            the value of the Slider *slidermin*.

        slidermax : Slider, default: None
            Do not allow the current slider to have a value greater than
            the value of the Slider *slidermax*.

        dragging : bool, default: True
            If True the slider can be dragged by the mouse.

        valstep : float or array-like, default: None
            If a float, the slider will snap to multiples of *valstep*.
            If an array the slider will snap to the values in the array.

        orientation : {'horizontal', 'vertical'}, default: 'horizontal'
            The orientation of the slider.

        initcolor : :mpltype:`color`, default: 'r'
            The color of the line at the *valinit* position. Set to ``'none'``
            for no line.

        track_color : :mpltype:`color`, default: 'lightgrey'
            The color of the background track. The track is accessible for
            further styling via the *track* attribute.

        handle_style : dict
            Properties of the slider handle. Default values are

            ========= ===== ======= ========================================
            Key       Value Default Description
            ========= ===== ======= ========================================
            facecolor color 'white' The facecolor of the slider handle.
            edgecolor color '.75'   The edgecolor of the slider handle.
            size      int   10      The size of the slider handle in points.
            ========= ===== ======= ========================================

            Other values will be transformed as marker{foo} and passed to the
            `~.Line2D` constructor. e.g. ``handle_style = {'style'='x'}`` will
            result in ``markerstyle = 'x'``.

        Notes
        -----
        Additional kwargs are passed on to ``self.poly`` which is the
        `~matplotlib.patches.Rectangle` that draws the slider knob.  See the
        `.Rectangle` documentation for valid property names (``facecolor``,
        ``edgecolor``, ``alpha``, etc.).
        """
        super().__init__(ax, orientation, closedmin, closedmax,
                         valmin, valmax, valfmt, dragging, valstep)

        if slidermin is not None and not hasattr(slidermin, 'val'):
            raise ValueError(
                f"Argument slidermin ({type(slidermin)}) has no 'val'")
        if slidermax is not None and not hasattr(slidermax, 'val'):
            raise ValueError(
                f"Argument slidermax ({type(slidermax)}) has no 'val'")
        self.slidermin = slidermin
        self.slidermax = slidermax
        valinit = self._value_in_bounds(valinit)
        if valinit is None:
            valinit = valmin
        self.val = valinit
        self.valinit = valinit

        defaults = {'facecolor': 'white', 'edgecolor': '.75', 'size': 10}
        handle_style = {} if handle_style is None else handle_style
        marker_props = {
            f'marker{k}': v for k, v in {**defaults, **handle_style}.items()
        }

        if orientation == 'vertical':
            self.track = Rectangle(
                (.25, 0), .5, 1,
                transform=ax.transAxes,
                facecolor=track_color
            )
            ax.add_patch(self.track)
            self.poly = ax.axhspan(valmin, valinit, .25, .75, **kwargs)
            # Drawing a longer line and clipping it to the track avoids
            # pixelation-related asymmetries.
            self.hline = ax.axhline(valinit, 0, 1, color=initcolor, lw=1,
                                    clip_path=TransformedPatchPath(self.track))
            handleXY = [[0.5], [valinit]]
        else:
            self.track = Rectangle(
                (0, .25), 1, .5,
                transform=ax.transAxes,
                facecolor=track_color
            )
            ax.add_patch(self.track)
            self.poly = ax.axvspan(valmin, valinit, .25, .75, **kwargs)
            self.vline = ax.axvline(valinit, 0, 1, color=initcolor, lw=1,
                                    clip_path=TransformedPatchPath(self.track))
            handleXY = [[valinit], [0.5]]
        self._handle, = ax.plot(
            *handleXY,
            "o",
            **marker_props,
            clip_on=False
        )

        if orientation == 'vertical':
            self.label = ax.text(0.5, 1.02, label, transform=ax.transAxes,
                                 verticalalignment='bottom',
                                 horizontalalignment='center')

            self.valtext = ax.text(0.5, -0.02, self._format(valinit),
                                   transform=ax.transAxes,
                                   verticalalignment='top',
                                   horizontalalignment='center')
        else:
            self.label = ax.text(-0.02, 0.5, label, transform=ax.transAxes,
                                 verticalalignment='center',
                                 horizontalalignment='right')

            self.valtext = ax.text(1.02, 0.5, self._format(valinit),
                                   transform=ax.transAxes,
                                   verticalalignment='center',
                                   horizontalalignment='left')

        self.set_val(valinit)

    def _value_in_bounds(self, val):
        """Makes sure *val* is with given bounds."""
        val = self._stepped_value(val)

        if val <= self.valmin:
            if not self.closedmin:
                return
            val = self.valmin
        elif val >= self.valmax:
            if not self.closedmax:
                return
            val = self.valmax

        if self.slidermin is not None and val <= self.slidermin.val:
            if not self.closedmin:
                return
            val = self.slidermin.val

        if self.slidermax is not None and val >= self.slidermax.val:
            if not self.closedmax:
                return
            val = self.slidermax.val
        return val

    def _update(self, event):
        """Update the slider position."""
        if self.ignore(event) or event.button != 1:
            return

        if event.name == 'button_press_event' and self.ax.contains(event)[0]:
            self.drag_active = True
            event.canvas.grab_mouse(self.ax)

        if not self.drag_active:
            return

        if (event.name == 'button_release_event'
              or event.name == 'button_press_event' and not self.ax.contains(event)[0]):
            self.drag_active = False
            event.canvas.release_mouse(self.ax)
            return

        xdata, ydata = self._get_data_coords(event)
        val = self._value_in_bounds(
            xdata if self.orientation == 'horizontal' else ydata)
        if val not in [None, self.val]:
            self.set_val(val)

    def _format(self, val):
        """Pretty-print *val*."""
        if self.valfmt is not None:
            return self.valfmt % val
        else:
            _, s, _ = self._fmt.format_ticks([self.valmin, val, self.valmax])
            # fmt.get_offset is actually the multiplicative factor, if any.
            return s + self._fmt.get_offset()

    def set_val(self, val):
        """
        Set slider value to *val*.

        Parameters
        ----------
        val : float
        """
        if self.orientation == 'vertical':
            self.poly.set_height(val - self.poly.get_y())
            self._handle.set_ydata([val])
        else:
            self.poly.set_width(val - self.poly.get_x())
            self._handle.set_xdata([val])
        self.valtext.set_text(self._format(val))
        if self.drawon:
            self.ax.get_figure(root=True).canvas.draw_idle()
        self.val = val
        if self.eventson:
            self._observers.process('changed', val)

    def on_changed(self, func):
        """
        Connect *func* as callback function to changes of the slider value.

        Parameters
        ----------
        func : callable
            Function to call when slider is changed.
            The function must accept a single float as its arguments.

        Returns
        -------
        int
            Connection id (which can be used to disconnect *func*).
        """
        return self._observers.connect('changed', lambda val: func(val))


class RangeSlider(SliderBase):
    """
    A slider representing a range of floating point values. Defines the min and
    max of the range via the *val* attribute as a tuple of (min, max).

    Create a slider that defines a range contained within [*valmin*, *valmax*]
    in Axes *ax*. For the slider to remain responsive you must maintain a
    reference to it. Call :meth:`on_changed` to connect to the slider event.

    Attributes
    ----------
    val : tuple of float
        Slider value.
    """

    def __init__(
        self,
        ax,
        label,
        valmin,
        valmax,
        *,
        valinit=None,
        valfmt=None,
        closedmin=True,
        closedmax=True,
        dragging=True,
        valstep=None,
        orientation="horizontal",
        track_color='lightgrey',
        handle_style=None,
        **kwargs,
    ):
        """
        Parameters
        ----------
        ax : Axes
            The Axes to put the slider in.

        label : str
            Slider label.

        valmin : float
            The minimum value of the slider.

        valmax : float
            The maximum value of the slider.

        valinit : tuple of float or None, default: None
            The initial positions of the slider. If None the initial positions
            will be at the 25th and 75th percentiles of the range.

        valfmt : str, default: None
            %-format string used to format the slider values.  If None, a
            `.ScalarFormatter` is used instead.

        closedmin : bool, default: True
            Whether the slider interval is closed on the bottom.

        closedmax : bool, default: True
            Whether the slider interval is closed on the top.

        dragging : bool, default: True
            If True the slider can be dragged by the mouse.

        valstep : float, default: None
            If given, the slider will snap to multiples of *valstep*.

        orientation : {'horizontal', 'vertical'}, default: 'horizontal'
            The orientation of the slider.

        track_color : :mpltype:`color`, default: 'lightgrey'
            The color of the background track. The track is accessible for
            further styling via the *track* attribute.

        handle_style : dict
            Properties of the slider handles. Default values are

            ========= ===== ======= =========================================
            Key       Value Default Description
            ========= ===== ======= =========================================
            facecolor color 'white' The facecolor of the slider handles.
            edgecolor color '.75'   The edgecolor of the slider handles.
            size      int   10      The size of the slider handles in points.
            ========= ===== ======= =========================================

            Other values will be transformed as marker{foo} and passed to the
            `~.Line2D` constructor. e.g. ``handle_style = {'style'='x'}`` will
            result in ``markerstyle = 'x'``.

        Notes
        -----
        Additional kwargs are passed on to ``self.poly`` which is the
        `~matplotlib.patches.Polygon` that draws the slider knob.  See the
        `.Polygon` documentation for valid property names (``facecolor``,
        ``edgecolor``, ``alpha``, etc.).
        """
        super().__init__(ax, orientation, closedmin, closedmax,
                         valmin, valmax, valfmt, dragging, valstep)

        # Set a value to allow _value_in_bounds() to work.
        self.val = (valmin, valmax)
        if valinit is None:
            # Place at the 25th and 75th percentiles
            extent = valmax - valmin
            valinit = np.array([valmin + extent * 0.25,
                                valmin + extent * 0.75])
        else:
            valinit = self._value_in_bounds(valinit)
        self.val = valinit
        self.valinit = valinit

        defaults = {'facecolor': 'white', 'edgecolor': '.75', 'size': 10}
        handle_style = {} if handle_style is None else handle_style
        marker_props = {
            f'marker{k}': v for k, v in {**defaults, **handle_style}.items()
        }

        if orientation == "vertical":
            self.track = Rectangle(
                (.25, 0), .5, 2,
                transform=ax.transAxes,
                facecolor=track_color
            )
            ax.add_patch(self.track)
            poly_transform = self.ax.get_yaxis_transform(which="grid")
            handleXY_1 = [.5, valinit[0]]
            handleXY_2 = [.5, valinit[1]]
        else:
            self.track = Rectangle(
                (0, .25), 1, .5,
                transform=ax.transAxes,
                facecolor=track_color
            )
            ax.add_patch(self.track)
            poly_transform = self.ax.get_xaxis_transform(which="grid")
            handleXY_1 = [valinit[0], .5]
            handleXY_2 = [valinit[1], .5]
        self.poly = Polygon(np.zeros([5, 2]), **kwargs)
        self._update_selection_poly(*valinit)
        self.poly.set_transform(poly_transform)
        self.poly.get_path()._interpolation_steps = 100
        self.ax.add_patch(self.poly)
        self.ax._request_autoscale_view()
        self._handles = [
            ax.plot(
                *handleXY_1,
                "o",
                **marker_props,
                clip_on=False
            )[0],
            ax.plot(
                *handleXY_2,
                "o",
                **marker_props,
                clip_on=False
            )[0]
        ]

        if orientation == "vertical":
            self.label = ax.text(
                0.5,
                1.02,
                label,
                transform=ax.transAxes,
                verticalalignment="bottom",
                horizontalalignment="center",
            )

            self.valtext = ax.text(
                0.5,
                -0.02,
                self._format(valinit),
                transform=ax.transAxes,
                verticalalignment="top",
                horizontalalignment="center",
            )
        else:
            self.label = ax.text(
                -0.02,
                0.5,
                label,
                transform=ax.transAxes,
                verticalalignment="center",
                horizontalalignment="right",
            )

            self.valtext = ax.text(
                1.02,
                0.5,
                self._format(valinit),
                transform=ax.transAxes,
                verticalalignment="center",
                horizontalalignment="left",
            )

        self._active_handle = None
        self.set_val(valinit)

    def _update_selection_poly(self, vmin, vmax):
        """
        Update the vertices of the *self.poly* slider in-place
        to cover the data range *vmin*, *vmax*.
        """
        # The vertices are positioned
        #  1 ------ 2
        #  |        |
        # 0, 4 ---- 3
        verts = self.poly.xy
        if self.orientation == "vertical":
            verts[0] = verts[4] = .25, vmin
            verts[1] = .25, vmax
            verts[2] = .75, vmax
            verts[3] = .75, vmin
        else:
            verts[0] = verts[4] = vmin, .25
            verts[1] = vmin, .75
            verts[2] = vmax, .75
            verts[3] = vmax, .25

    def _min_in_bounds(self, min):
        """Ensure the new min value is between valmin and self.val[1]."""
        if min <= self.valmin:
            if not self.closedmin:
                return self.val[0]
            min = self.valmin

        if min > self.val[1]:
            min = self.val[1]
        return self._stepped_value(min)

    def _max_in_bounds(self, max):
        """Ensure the new max value is between valmax and self.val[0]."""
        if max >= self.valmax:
            if not self.closedmax:
                return self.val[1]
            max = self.valmax

        if max <= self.val[0]:
            max = self.val[0]
        return self._stepped_value(max)

    def _value_in_bounds(self, vals):
        """Clip min, max values to the bounds."""
        return (self._min_in_bounds(vals[0]), self._max_in_bounds(vals[1]))

    def _update_val_from_pos(self, pos):
        """Update the slider value based on a given position."""
        idx = np.argmin(np.abs(self.val - pos))
        if idx == 0:
            val = self._min_in_bounds(pos)
            self.set_min(val)
        else:
            val = self._max_in_bounds(pos)
            self.set_max(val)
        if self._active_handle:
            if self.orientation == "vertical":
                self._active_handle.set_ydata([val])
            else:
                self._active_handle.set_xdata([val])

    def _update(self, event):
        """Update the slider position."""
        if self.ignore(event) or event.button != 1:
            return

        if event.name == "button_press_event" and self.ax.contains(event)[0]:
            self.drag_active = True
            event.canvas.grab_mouse(self.ax)

        if not self.drag_active:
            return

        if (event.name == "button_release_event"
              or event.name == "button_press_event" and not self.ax.contains(event)[0]):
            self.drag_active = False
            event.canvas.release_mouse(self.ax)
            self._active_handle = None
            return

        # determine which handle was grabbed
        xdata, ydata = self._get_data_coords(event)
        handle_index = np.argmin(np.abs(
            [h.get_xdata()[0] - xdata for h in self._handles]
            if self.orientation == "horizontal" else
            [h.get_ydata()[0] - ydata for h in self._handles]))
        handle = self._handles[handle_index]

        # these checks ensure smooth behavior if the handles swap which one
        # has a higher value. i.e. if one is dragged over and past the other.
        if handle is not self._active_handle:
            self._active_handle = handle

        self._update_val_from_pos(xdata if self.orientation == "horizontal" else ydata)

    def _format(self, val):
        """Pretty-print *val*."""
        if self.valfmt is not None:
            return f"({self.valfmt % val[0]}, {self.valfmt % val[1]})"
        else:
            _, s1, s2, _ = self._fmt.format_ticks(
                [self.valmin, *val, self.valmax]
            )
            # fmt.get_offset is actually the multiplicative factor, if any.
            s1 += self._fmt.get_offset()
            s2 += self._fmt.get_offset()
            # Use f string to avoid issues with backslashes when cast to a str
            return f"({s1}, {s2})"

    def set_min(self, min):
        """
        Set the lower value of the slider to *min*.

        Parameters
        ----------
        min : float
        """
        self.set_val((min, self.val[1]))

    def set_max(self, max):
        """
        Set the lower value of the slider to *max*.

        Parameters
        ----------
        max : float
        """
        self.set_val((self.val[0], max))

    def set_val(self, val):
        """
        Set slider value to *val*.

        Parameters
        ----------
        val : tuple or array-like of float
        """
        val = np.sort(val)
        _api.check_shape((2,), val=val)
        # Reset value to allow _value_in_bounds() to work.
        self.val = (self.valmin, self.valmax)
        vmin, vmax = self._value_in_bounds(val)
        self._update_selection_poly(vmin, vmax)
        if self.orientation == "vertical":
            self._handles[0].set_ydata([vmin])
            self._handles[1].set_ydata([vmax])
        else:
            self._handles[0].set_xdata([vmin])
            self._handles[1].set_xdata([vmax])

        self.valtext.set_text(self._format((vmin, vmax)))

        if self.drawon:
            self.ax.get_figure(root=True).canvas.draw_idle()
        self.val = (vmin, vmax)
        if self.eventson:
            self._observers.process("changed", (vmin, vmax))

    def on_changed(self, func):
        """
        Connect *func* as callback function to changes of the slider value.

        Parameters
        ----------
        func : callable
            Function to call when slider is changed. The function
            must accept a 2-tuple of floats as its argument.

        Returns
        -------
        int
            Connection id (which can be used to disconnect *func*).
        """
        return self._observers.connect('changed', lambda val: func(val))


def _expand_text_props(props):
    props = cbook.normalize_kwargs(props, mtext.Text)
    return cycler(**props)() if props else itertools.repeat({})


class CheckButtons(AxesWidget):
    r"""
    A GUI neutral set of check buttons.

    For the check buttons to remain responsive you must keep a
    reference to this object.

    Connect to the CheckButtons with the `.on_clicked` method.

    Attributes
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.
    labels : list of `~matplotlib.text.Text`
        The text label objects of the check buttons.
    """

    def __init__(self, ax, labels, actives=None, *, useblit=True,
                 label_props=None, frame_props=None, check_props=None):
        """
        Add check buttons to `~.axes.Axes` instance *ax*.

        Parameters
        ----------
        ax : `~matplotlib.axes.Axes`
            The parent Axes for the widget.
        labels : list of str
            The labels of the check buttons.
        actives : list of bool, optional
            The initial check states of the buttons. The list must have the
            same length as *labels*. If not given, all buttons are unchecked.
        useblit : bool, default: True
            Use blitting for faster drawing if supported by the backend.
            See the tutorial :ref:`blitting` for details.

            .. versionadded:: 3.7

        label_props : dict of lists, optional
            Dictionary of `.Text` properties to be used for the labels. Each
            dictionary value should be a list of at least a single element. If
            the list is of length M, its values are cycled such that the Nth
            label gets the (N mod M) property.

            .. versionadded:: 3.7
        frame_props : dict, optional
            Dictionary of scatter `.Collection` properties to be used for the
            check button frame. Defaults (label font size / 2)**2 size, black
            edgecolor, no facecolor, and 1.0 linewidth.

            .. versionadded:: 3.7
        check_props : dict, optional
            Dictionary of scatter `.Collection` properties to be used for the
            check button check. Defaults to (label font size / 2)**2 size,
            black color, and 1.0 linewidth.

            .. versionadded:: 3.7
        """
        super().__init__(ax)

        _api.check_isinstance((dict, None), label_props=label_props,
                              frame_props=frame_props, check_props=check_props)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_navigate(False)

        if actives is None:
            actives = [False] * len(labels)

        self._useblit = useblit and self.canvas.supports_blit
        self._background = None

        ys = np.linspace(1, 0, len(labels)+2)[1:-1]

        label_props = _expand_text_props(label_props)
        self.labels = [
            ax.text(0.25, y, label, transform=ax.transAxes,
                    horizontalalignment="left", verticalalignment="center",
                    **props)
            for y, label, props in zip(ys, labels, label_props)]
        text_size = np.array([text.get_fontsize() for text in self.labels]) / 2

        frame_props = {
            's': text_size**2,
            'linewidth': 1,
            **cbook.normalize_kwargs(frame_props, collections.PathCollection),
            'marker': 's',
            'transform': ax.transAxes,
        }
        frame_props.setdefault('facecolor', frame_props.get('color', 'none'))
        frame_props.setdefault('edgecolor', frame_props.pop('color', 'black'))
        self._frames = ax.scatter([0.15] * len(ys), ys, **frame_props)
        check_props = {
            'linewidth': 1,
            's': text_size**2,
            **cbook.normalize_kwargs(check_props, collections.PathCollection),
            'marker': 'x',
            'transform': ax.transAxes,
            'animated': self._useblit,
        }
        check_props.setdefault('facecolor', check_props.pop('color', 'black'))
        self._checks = ax.scatter([0.15] * len(ys), ys, **check_props)
        # The user may have passed custom colours in check_props, so we need to
        # create the checks (above), and modify the visibility after getting
        # whatever the user set.
        self._init_status(actives)

        self.connect_event('button_press_event', self._clicked)
        if self._useblit:
            self.connect_event('draw_event', self._clear)

        self._observers = cbook.CallbackRegistry(signals=["clicked"])

    def _clear(self, event):
        """Internal event handler to clear the buttons."""
        if self.ignore(event) or self.canvas.is_saving():
            return
        self._background = self.canvas.copy_from_bbox(self.ax.bbox)
        self.ax.draw_artist(self._checks)

    def _clicked(self, event):
        if self.ignore(event) or event.button != 1 or not self.ax.contains(event)[0]:
            return
        idxs = [  # Indices of frames and of texts that contain the event.
            *self._frames.contains(event)[1]["ind"],
            *[i for i, text in enumerate(self.labels) if text.contains(event)[0]]]
        if idxs:
            coords = self._frames.get_offset_transform().transform(
                self._frames.get_offsets())
            self.set_active(  # Closest index, only looking in idxs.
                idxs[(((event.x, event.y) - coords[idxs]) ** 2).sum(-1).argmin()])

    def set_label_props(self, props):
        """
        Set properties of the `.Text` labels.

        .. versionadded:: 3.7

        Parameters
        ----------
        props : dict
            Dictionary of `.Text` properties to be used for the labels. Same
            format as label_props argument of :class:`CheckButtons`.
        """
        _api.check_isinstance(dict, props=props)
        props = _expand_text_props(props)
        for text, prop in zip(self.labels, props):
            text.update(prop)

    def set_frame_props(self, props):
        """
        Set properties of the check button frames.

        .. versionadded:: 3.7

        Parameters
        ----------
        props : dict
            Dictionary of `.Collection` properties to be used for the check
            button frames.
        """
        _api.check_isinstance(dict, props=props)
        if 's' in props:  # Keep API consistent with constructor.
            props['sizes'] = np.broadcast_to(props.pop('s'), len(self.labels))
        self._frames.update(props)

    def set_check_props(self, props):
        """
        Set properties of the check button checks.

        .. versionadded:: 3.7

        Parameters
        ----------
        props : dict
            Dictionary of `.Collection` properties to be used for the check
            button check.
        """
        _api.check_isinstance(dict, props=props)
        if 's' in props:  # Keep API consistent with constructor.
            props['sizes'] = np.broadcast_to(props.pop('s'), len(self.labels))
        actives = self.get_status()
        self._checks.update(props)
        # If new colours are supplied, then we must re-apply the status.
        self._init_status(actives)

    def set_active(self, index, state=None):
        """
        Modify the state of a check button by index.

        Callbacks will be triggered if :attr:`eventson` is True.

        Parameters
        ----------
        index : int
            Index of the check button to toggle.

        state : bool, optional
            If a boolean value, set the state explicitly. If no value is
            provided, the state is toggled.

        Raises
        ------
        ValueError
            If *index* is invalid.
        TypeError
            If *state* is not boolean.
        """
        if index not in range(len(self.labels)):
            raise ValueError(f'Invalid CheckButton index: {index}')
        _api.check_isinstance((bool, None), state=state)

        invisible = colors.to_rgba('none')

        facecolors = self._checks.get_facecolor()
        if state is None:
            state = colors.same_color(facecolors[index], invisible)
        facecolors[index] = self._active_check_colors[index] if state else invisible
        self._checks.set_facecolor(facecolors)

        if self.drawon:
            if self._useblit:
                if self._background is not None:
                    self.canvas.restore_region(self._background)
                self.ax.draw_artist(self._checks)
                self.canvas.blit(self.ax.bbox)
            else:
                self.canvas.draw()

        if self.eventson:
            self._observers.process('clicked', self.labels[index].get_text())

    def _init_status(self, actives):
        """
        Initialize properties to match active status.

        The user may have passed custom colours in *check_props* to the
        constructor, or to `.set_check_props`, so we need to modify the
        visibility after getting whatever the user set.
        """
        self._active_check_colors = self._checks.get_facecolor()
        if len(self._active_check_colors) == 1:
            self._active_check_colors = np.repeat(self._active_check_colors,
                                                  len(actives), axis=0)
        self._checks.set_facecolor(
            [ec if active else "none"
             for ec, active in zip(self._active_check_colors, actives)])

    def clear(self):
        """Uncheck all checkboxes."""

        self._checks.set_facecolor(['none'] * len(self._active_check_colors))

        if hasattr(self, '_lines'):
            for l1, l2 in self._lines:
                l1.set_visible(False)
                l2.set_visible(False)

        if self.drawon:
            self.canvas.draw()

        if self.eventson:
            # Call with no label, as all checkboxes are being cleared.
            self._observers.process('clicked', None)

    def get_status(self):
        """
        Return a list of the status (True/False) of all of the check buttons.
        """
        return [not colors.same_color(color, colors.to_rgba("none"))
                for color in self._checks.get_facecolors()]

    def get_checked_labels(self):
        """Return a list of labels currently checked by user."""

        return [l.get_text() for l, box_checked in
                zip(self.labels, self.get_status())
                if box_checked]

    def on_clicked(self, func):
        """
        Connect the callback function *func* to button click events.

        Parameters
        ----------
        func : callable
            When the button is clicked, call *func* with button label.
            When all buttons are cleared, call *func* with None.
            The callback func must have the signature::

                def func(label: str | None) -> Any

            Return values may exist, but are ignored.

        Returns
        -------
        A connection id, which can be used to disconnect the callback.
        """
        return self._observers.connect('clicked', lambda text: func(text))

    def disconnect(self, cid):
        """Remove the observer with connection id *cid*."""
        self._observers.disconnect(cid)


class TextBox(AxesWidget):
    """
    A GUI neutral text input box.

    For the text box to remain responsive you must keep a reference to it.

    Call `.on_text_change` to be updated whenever the text changes.

    Call `.on_submit` to be updated whenever the user hits enter or
    leaves the text entry field.

    Attributes
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.
    label : `~matplotlib.text.Text`

    color : :mpltype:`color`
        The color of the text box when not hovering.
    hovercolor : :mpltype:`color`
        The color of the text box when hovering.
    """

    def __init__(self, ax, label, initial='', *,
                 color='.95', hovercolor='1', label_pad=.01,
                 textalignment="left"):
        """
        Parameters
        ----------
        ax : `~matplotlib.axes.Axes`
            The `~.axes.Axes` instance the button will be placed into.
        label : str
            Label for this text box.
        initial : str
            Initial value in the text box.
        color : :mpltype:`color`
            The color of the box.
        hovercolor : :mpltype:`color`
            The color of the box when the mouse is over it.
        label_pad : float
            The distance between the label and the right side of the textbox.
        textalignment : {'left', 'center', 'right'}
            The horizontal location of the text.
        """
        super().__init__(ax)

        self._text_position = _api.check_getitem(
            {"left": 0.05, "center": 0.5, "right": 0.95},
            textalignment=textalignment)

        self.label = ax.text(
            -label_pad, 0.5, label, transform=ax.transAxes,
            verticalalignment='center', horizontalalignment='right')

        # TextBox's text object should not parse mathtext at all.
        self.text_disp = self.ax.text(
            self._text_position, 0.5, initial, transform=self.ax.transAxes,
            verticalalignment='center', horizontalalignment=textalignment,
            parse_math=False)

        self._observers = cbook.CallbackRegistry(signals=["change", "submit"])

        ax.set(
            xlim=(0, 1), ylim=(0, 1),  # s.t. cursor appears from first click.
            navigate=False, facecolor=color,
            xticks=[], yticks=[])

        self.cursor_index = 0

        self.cursor = ax.vlines(0, 0, 0, visible=False, color="k", lw=1,
                                transform=mpl.transforms.IdentityTransform())

        self.connect_event('button_press_event', self._click)
        self.connect_event('button_release_event', self._release)
        self.connect_event('motion_notify_event', self._motion)
        self.connect_event('key_press_event', self._keypress)
        self.connect_event('resize_event', self._resize)

        self.color = color
        self.hovercolor = hovercolor

        self.capturekeystrokes = False

    @property
    def text(self):
        return self.text_disp.get_text()

    def _rendercursor(self):
        # this is a hack to figure out where the cursor should go.
        # we draw the text up to where the cursor should go, measure
        # and save its dimensions, draw the real text, then put the cursor
        # at the saved dimensions

        # This causes a single extra draw if the figure has never been rendered
        # yet, which should be fine as we're going to repeatedly re-render the
        # figure later anyways.
        fig = self.ax.get_figure(root=True)
        if fig._get_renderer() is None:
            fig.canvas.draw()

        text = self.text_disp.get_text()  # Save value before overwriting it.
        widthtext = text[:self.cursor_index]

        bb_text = self.text_disp.get_window_extent()
        self.text_disp.set_text(widthtext or ",")
        bb_widthtext = self.text_disp.get_window_extent()

        if bb_text.y0 == bb_text.y1:  # Restoring the height if no text.
            bb_text.y0 -= bb_widthtext.height / 2
            bb_text.y1 += bb_widthtext.height / 2
        elif not widthtext:  # Keep width to 0.
            bb_text.x1 = bb_text.x0
        else:  # Move the cursor using width of bb_widthtext.
            bb_text.x1 = bb_text.x0 + bb_widthtext.width

        self.cursor.set(
            segments=[[(bb_text.x1, bb_text.y0), (bb_text.x1, bb_text.y1)]],
            visible=True)
        self.text_disp.set_text(text)

        fig.canvas.draw()

    def _release(self, event):
        if self.ignore(event):
            return
        if event.canvas.mouse_grabber != self.ax:
            return
        event.canvas.release_mouse(self.ax)

    def _keypress(self, event):
        if self.ignore(event):
            return
        if self.capturekeystrokes:
            key = event.key
            text = self.text
            if len(key) == 1:
                text = (text[:self.cursor_index] + key +
                        text[self.cursor_index:])
                self.cursor_index += 1
            elif key == "right":
                if self.cursor_index != len(text):
                    self.cursor_index += 1
            elif key == "left":
                if self.cursor_index != 0:
                    self.cursor_index -= 1
            elif key == "home":
                self.cursor_index = 0
            elif key == "end":
                self.cursor_index = len(text)
            elif key == "backspace":
                if self.cursor_index != 0:
                    text = (text[:self.cursor_index - 1] +
                            text[self.cursor_index:])
                    self.cursor_index -= 1
            elif key == "delete":
                if self.cursor_index != len(self.text):
                    text = (text[:self.cursor_index] +
                            text[self.cursor_index + 1:])
            self.text_disp.set_text(text)
            self._rendercursor()
            if self.eventson:
                self._observers.process('change', self.text)
                if key in ["enter", "return"]:
                    self._observers.process('submit', self.text)

    def set_val(self, val):
        newval = str(val)
        if self.text == newval:
            return
        self.text_disp.set_text(newval)
        self._rendercursor()
        if self.eventson:
            self._observers.process('change', self.text)
            self._observers.process('submit', self.text)

    def begin_typing(self):
        self.capturekeystrokes = True
        # Disable keypress shortcuts, which may otherwise cause the figure to
        # be saved, closed, etc., until the user stops typing.  The way to
        # achieve this depends on whether toolmanager is in use.
        stack = ExitStack()  # Register cleanup actions when user stops typing.
        self._on_stop_typing = stack.close
        toolmanager = getattr(
            self.ax.get_figure(root=True).canvas.manager, "toolmanager", None)
        if toolmanager is not None:
            # If using toolmanager, lock keypresses, and plan to release the
            # lock when typing stops.
            toolmanager.keypresslock(self)
            stack.callback(toolmanager.keypresslock.release, self)
        else:
            # If not using toolmanager, disable all keypress-related rcParams.
            # Avoid spurious warnings if keymaps are getting deprecated.
            with _api.suppress_matplotlib_deprecation_warning():
                stack.enter_context(mpl.rc_context(
                    {k: [] for k in mpl.rcParams if k.startswith("keymap.")}))

    def stop_typing(self):
        if self.capturekeystrokes:
            self._on_stop_typing()
            self._on_stop_typing = None
            notifysubmit = True
        else:
            notifysubmit = False
        self.capturekeystrokes = False
        self.cursor.set_visible(False)
        self.ax.get_figure(root=True).canvas.draw()
        if notifysubmit and self.eventson:
            # Because process() might throw an error in the user's code, only
            # call it once we've already done our cleanup.
            self._observers.process('submit', self.text)

    def _click(self, event):
        if self.ignore(event):
            return
        if not self.ax.contains(event)[0]:
            self.stop_typing()
            return
        if not self.eventson:
            return
        if event.canvas.mouse_grabber != self.ax:
            event.canvas.grab_mouse(self.ax)
        if not self.capturekeystrokes:
            self.begin_typing()
        self.cursor_index = self.text_disp._char_index_at(event.x)
        self._rendercursor()

    def _resize(self, event):
        self.stop_typing()

    def _motion(self, event):
        if self.ignore(event):
            return
        c = self.hovercolor if self.ax.contains(event)[0] else self.color
        if not colors.same_color(c, self.ax.get_facecolor()):
            self.ax.set_facecolor(c)
            if self.drawon:
                self.ax.get_figure(root=True).canvas.draw()

    def on_text_change(self, func):
        """
        When the text changes, call this *func* with event.

        A connection id is returned which can be used to disconnect.
        """
        return self._observers.connect('change', lambda text: func(text))

    def on_submit(self, func):
        """
        When the user hits enter or leaves the submission box, call this
        *func* with event.

        A connection id is returned which can be used to disconnect.
        """
        return self._observers.connect('submit', lambda text: func(text))

    def disconnect(self, cid):
        """Remove the observer with connection id *cid*."""
        self._observers.disconnect(cid)


class RadioButtons(AxesWidget):
    """
    A GUI neutral radio button.

    For the buttons to remain responsive you must keep a reference to this
    object.

    Connect to the RadioButtons with the `.on_clicked` method.

    Attributes
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.
    activecolor : :mpltype:`color`
        The color of the selected button.
    labels : list of `.Text`
        The button labels.
    value_selected : str
        The label text of the currently selected button.
    index_selected : int
        The index of the selected button.
    """

    def __init__(self, ax, labels, active=0, activecolor=None, *,
                 useblit=True, label_props=None, radio_props=None):
        """
        Add radio buttons to an `~.axes.Axes`.

        Parameters
        ----------
        ax : `~matplotlib.axes.Axes`
            The Axes to add the buttons to.
        labels : list of str
            The button labels.
        active : int
            The index of the initially selected button.
        activecolor : :mpltype:`color`
            The color of the selected button. The default is ``'blue'`` if not
            specified here or in *radio_props*.
        useblit : bool, default: True
            Use blitting for faster drawing if supported by the backend.
            See the tutorial :ref:`blitting` for details.

            .. versionadded:: 3.7

        label_props : dict of lists, optional
            Dictionary of `.Text` properties to be used for the labels. Each
            dictionary value should be a list of at least a single element. If
            the list is of length M, its values are cycled such that the Nth
            label gets the (N mod M) property.

            .. versionadded:: 3.7
        radio_props : dict, optional
            Dictionary of scatter `.Collection` properties to be used for the
            radio buttons. Defaults to (label font size / 2)**2 size, black
            edgecolor, and *activecolor* facecolor (when active).

            .. note::
                If a facecolor is supplied in *radio_props*, it will override
                *activecolor*. This may be used to provide an active color per
                button.

            .. versionadded:: 3.7
        """
        super().__init__(ax)

        _api.check_isinstance((dict, None), label_props=label_props,
                              radio_props=radio_props)

        radio_props = cbook.normalize_kwargs(radio_props,
                                             collections.PathCollection)
        if activecolor is not None:
            if 'facecolor' in radio_props:
                _api.warn_external(
                    'Both the *activecolor* parameter and the *facecolor* '
                    'key in the *radio_props* parameter has been specified. '
                    '*activecolor* will be ignored.')
        else:
            activecolor = 'blue'  # Default.

        self._activecolor = activecolor
        self._initial_active = active
        self.value_selected = labels[active]
        self.index_selected = active

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_navigate(False)

        ys = np.linspace(1, 0, len(labels) + 2)[1:-1]

        self._useblit = useblit and self.canvas.supports_blit
        self._background = None

        label_props = _expand_text_props(label_props)
        self.labels = [
            ax.text(0.25, y, label, transform=ax.transAxes,
                    horizontalalignment="left", verticalalignment="center",
                    **props)
            for y, label, props in zip(ys, labels, label_props)]
        text_size = np.array([text.get_fontsize() for text in self.labels]) / 2

        radio_props = {
            's': text_size**2,
            **radio_props,
            'marker': 'o',
            'transform': ax.transAxes,
            'animated': self._useblit,
        }
        radio_props.setdefault('edgecolor', radio_props.get('color', 'black'))
        radio_props.setdefault('facecolor',
                               radio_props.pop('color', activecolor))
        self._buttons = ax.scatter([.15] * len(ys), ys, **radio_props)
        # The user may have passed custom colours in radio_props, so we need to
        # create the radios, and modify the visibility after getting whatever
        # the user set.
        self._active_colors = self._buttons.get_facecolor()
        if len(self._active_colors) == 1:
            self._active_colors = np.repeat(self._active_colors, len(labels),
                                            axis=0)
        self._buttons.set_facecolor(
            [activecolor if i == active else "none"
             for i, activecolor in enumerate(self._active_colors)])

        self.connect_event('button_press_event', self._clicked)
        if self._useblit:
            self.connect_event('draw_event', self._clear)

        self._observers = cbook.CallbackRegistry(signals=["clicked"])

    def _clear(self, event):
        """Internal event handler to clear the buttons."""
        if self.ignore(event) or self.canvas.is_saving():
            return
        self._background = self.canvas.copy_from_bbox(self.ax.bbox)
        self.ax.draw_artist(self._buttons)

    def _clicked(self, event):
        if self.ignore(event) or event.button != 1 or not self.ax.contains(event)[0]:
            return
        idxs = [  # Indices of buttons and of texts that contain the event.
            *self._buttons.contains(event)[1]["ind"],
            *[i for i, text in enumerate(self.labels) if text.contains(event)[0]]]
        if idxs:
            coords = self._buttons.get_offset_transform().transform(
                self._buttons.get_offsets())
            self.set_active(  # Closest index, only looking in idxs.
                idxs[(((event.x, event.y) - coords[idxs]) ** 2).sum(-1).argmin()])

    def set_label_props(self, props):
        """
        Set properties of the `.Text` labels.

        .. versionadded:: 3.7

        Parameters
        ----------
        props : dict
            Dictionary of `.Text` properties to be used for the labels. Same
            format as label_props argument of :class:`RadioButtons`.
        """
        _api.check_isinstance(dict, props=props)
        props = _expand_text_props(props)
        for text, prop in zip(self.labels, props):
            text.update(prop)

    def set_radio_props(self, props):
        """
        Set properties of the `.Text` labels.

        .. versionadded:: 3.7

        Parameters
        ----------
        props : dict
            Dictionary of `.Collection` properties to be used for the radio
            buttons.
        """
        _api.check_isinstance(dict, props=props)
        if 's' in props:  # Keep API consistent with constructor.
            props['sizes'] = np.broadcast_to(props.pop('s'), len(self.labels))
        self._buttons.update(props)
        self._active_colors = self._buttons.get_facecolor()
        if len(self._active_colors) == 1:
            self._active_colors = np.repeat(self._active_colors,
                                            len(self.labels), axis=0)
        self._buttons.set_facecolor(
            [activecolor if text.get_text() == self.value_selected else "none"
             for text, activecolor in zip(self.labels, self._active_colors)])

    @property
    def activecolor(self):
        return self._activecolor

    @activecolor.setter
    def activecolor(self, activecolor):
        colors._check_color_like(activecolor=activecolor)
        self._activecolor = activecolor
        self.set_radio_props({'facecolor': activecolor})

    def set_active(self, index):
        """
        Select button with number *index*.

        Callbacks will be triggered if :attr:`eventson` is True.

        Parameters
        ----------
        index : int
            The index of the button to activate.

        Raises
        ------
        ValueError
            If the index is invalid.
        """
        if index not in range(len(self.labels)):
            raise ValueError(f'Invalid RadioButton index: {index}')
        self.value_selected = self.labels[index].get_text()
        self.index_selected = index
        button_facecolors = self._buttons.get_facecolor()
        button_facecolors[:] = colors.to_rgba("none")
        button_facecolors[index] = colors.to_rgba(self._active_colors[index])
        self._buttons.set_facecolor(button_facecolors)

        if self.drawon:
            if self._useblit:
                if self._background is not None:
                    self.canvas.restore_region(self._background)
                self.ax.draw_artist(self._buttons)
                self.canvas.blit(self.ax.bbox)
            else:
                self.canvas.draw()

        if self.eventson:
            self._observers.process('clicked', self.labels[index].get_text())

    def clear(self):
        """Reset the active button to the initially active one."""
        self.set_active(self._initial_active)

    def on_clicked(self, func):
        """
        Connect the callback function *func* to button click events.

        Parameters
        ----------
        func : callable
            When the button is clicked, call *func* with button label.
            When all buttons are cleared, call *func* with None.
            The callback func must have the signature::

                def func(label: str | None) -> Any

            Return values may exist, but are ignored.

        Returns
        -------
        A connection id, which can be used to disconnect the callback.
        """
        return self._observers.connect('clicked', func)

    def disconnect(self, cid):
        """Remove the observer with connection id *cid*."""
        self._observers.disconnect(cid)


class SubplotTool(Widget):
    """
    A tool to adjust the subplot params of a `.Figure`.
    """

    def __init__(self, targetfig, toolfig):
        """
        Parameters
        ----------
        targetfig : `~matplotlib.figure.Figure`
            The figure instance to adjust.
        toolfig : `~matplotlib.figure.Figure`
            The figure instance to embed the subplot tool into.
        """

        self.figure = toolfig
        self.targetfig = targetfig
        toolfig.subplots_adjust(left=0.2, right=0.9)
        toolfig.suptitle("Click on slider to adjust subplot param")

        self._sliders = []
        names = ["left", "bottom", "right", "top", "wspace", "hspace"]
        # The last subplot, removed below, keeps space for the "Reset" button.
        for name, ax in zip(names, toolfig.subplots(len(names) + 1)):
            ax.set_navigate(False)
            slider = Slider(ax, name, 0, 1,
                            valinit=getattr(targetfig.subplotpars, name))
            slider.on_changed(self._on_slider_changed)
            self._sliders.append(slider)
        toolfig.axes[-1].remove()
        (self.sliderleft, self.sliderbottom, self.sliderright, self.slidertop,
         self.sliderwspace, self.sliderhspace) = self._sliders
        for slider in [self.sliderleft, self.sliderbottom,
                       self.sliderwspace, self.sliderhspace]:
            slider.closedmax = False
        for slider in [self.sliderright, self.slidertop]:
            slider.closedmin = False

        # constraints
        self.sliderleft.slidermax = self.sliderright
        self.sliderright.slidermin = self.sliderleft
        self.sliderbottom.slidermax = self.slidertop
        self.slidertop.slidermin = self.sliderbottom

        bax = toolfig.add_axes([0.8, 0.05, 0.15, 0.075])
        self.buttonreset = Button(bax, 'Reset')
        self.buttonreset.on_clicked(self._on_reset)

    def _on_slider_changed(self, _):
        self.targetfig.subplots_adjust(
            **{slider.label.get_text(): slider.val
               for slider in self._sliders})
        if self.drawon:
            self.targetfig.canvas.draw()

    def _on_reset(self, event):
        with ExitStack() as stack:
            # Temporarily disable drawing on self and self's sliders, and
            # disconnect slider events (as the subplotparams can be temporarily
            # invalid, depending on the order in which they are restored).
            stack.enter_context(cbook._setattr_cm(self, drawon=False))
            for slider in self._sliders:
                stack.enter_context(
                    cbook._setattr_cm(slider, drawon=False, eventson=False))
            # Reset the slider to the initial position.
            for slider in self._sliders:
                slider.reset()
        if self.drawon:
            event.canvas.draw()  # Redraw the subplottool canvas.
        self._on_slider_changed(None)  # Apply changes to the target window.


class Cursor(AxesWidget):
    """
    A crosshair cursor that spans the Axes and moves with mouse cursor.

    For the cursor to remain responsive you must keep a reference to it.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        The `~.axes.Axes` to attach the cursor to.
    horizOn : bool, default: True
        Whether to draw the horizontal line.
    vertOn : bool, default: True
        Whether to draw the vertical line.
    useblit : bool, default: False
        Use blitting for faster drawing if supported by the backend.
        See the tutorial :ref:`blitting` for details.

    Other Parameters
    ----------------
    **lineprops
        `.Line2D` properties that control the appearance of the lines.
        See also `~.Axes.axhline`.

    Examples
    --------
    See :doc:`/gallery/widgets/cursor`.
    """
    def __init__(self, ax, *, horizOn=True, vertOn=True, useblit=False,
                 **lineprops):
        super().__init__(ax)

        self.connect_event('motion_notify_event', self.onmove)
        self.connect_event('draw_event', self.clear)

        self.visible = True
        self.horizOn = horizOn
        self.vertOn = vertOn
        self.useblit = useblit and self.canvas.supports_blit

        if self.useblit:
            lineprops['animated'] = True
        self.lineh = ax.axhline(ax.get_ybound()[0], visible=False, **lineprops)
        self.linev = ax.axvline(ax.get_xbound()[0], visible=False, **lineprops)

        self.background = None
        self.needclear = False

    def clear(self, event):
        """Internal event handler to clear the cursor."""
        if self.ignore(event) or self.canvas.is_saving():
            return
        if self.useblit:
            self.background = self.canvas.copy_from_bbox(self.ax.bbox)

    def onmove(self, event):
        """Internal event handler to draw the cursor when the mouse moves."""
        if self.ignore(event):
            return
        if not self.canvas.widgetlock.available(self):
            return
        if not self.ax.contains(event)[0]:
            self.linev.set_visible(False)
            self.lineh.set_visible(False)
            if self.needclear:
                self.canvas.draw()
                self.needclear = False
            return
        self.needclear = True
        xdata, ydata = self._get_data_coords(event)
        self.linev.set_xdata((xdata, xdata))
        self.linev.set_visible(self.visible and self.vertOn)
        self.lineh.set_ydata((ydata, ydata))
        self.lineh.set_visible(self.visible and self.horizOn)
        if not (self.visible and (self.vertOn or self.horizOn)):
            return
        # Redraw.
        if self.useblit:
            if self.background is not None:
                self.canvas.restore_region(self.background)
            self.ax.draw_artist(self.linev)
            self.ax.draw_artist(self.lineh)
            self.canvas.blit(self.ax.bbox)
        else:
            self.canvas.draw_idle()


class MultiCursor(Widget):
    """
    Provide a vertical (default) and/or horizontal line cursor shared between
    multiple Axes.

    For the cursor to remain responsive you must keep a reference to it.

    Parameters
    ----------
    canvas : object
        This parameter is entirely unused and only kept for back-compatibility.

    axes : list of `~matplotlib.axes.Axes`
        The `~.axes.Axes` to attach the cursor to.

    useblit : bool, default: True
        Use blitting for faster drawing if supported by the backend.
        See the tutorial :ref:`blitting`
        for details.

    horizOn : bool, default: False
        Whether to draw the horizontal line.

    vertOn : bool, default: True
        Whether to draw the vertical line.

    Other Parameters
    ----------------
    **lineprops
        `.Line2D` properties that control the appearance of the lines.
        See also `~.Axes.axhline`.

    Examples
    --------
    See :doc:`/gallery/widgets/multicursor`.
    """

    def __init__(self, canvas, axes, *, useblit=True, horizOn=False, vertOn=True,
                 **lineprops):
        # canvas is stored only to provide the deprecated .canvas attribute;
        # once it goes away the unused argument won't need to be stored at all.
        self._canvas = canvas

        self.axes = axes
        self.horizOn = horizOn
        self.vertOn = vertOn

        self._canvas_infos = {
            ax.get_figure(root=True).canvas:
                {"cids": [], "background": None} for ax in axes}

        xmin, xmax = axes[-1].get_xlim()
        ymin, ymax = axes[-1].get_ylim()
        xmid = 0.5 * (xmin + xmax)
        ymid = 0.5 * (ymin + ymax)

        self.visible = True
        self.useblit = (
            useblit
            and all(canvas.supports_blit for canvas in self._canvas_infos))

        if self.useblit:
            lineprops['animated'] = True

        self.vlines = [ax.axvline(xmid, visible=False, **lineprops)
                       for ax in axes]
        self.hlines = [ax.axhline(ymid, visible=False, **lineprops)
                       for ax in axes]

        self.connect()

    def connect(self):
        """Connect events."""
        for canvas, info in self._canvas_infos.items():
            info["cids"] = [
                canvas.mpl_connect('motion_notify_event', self.onmove),
                canvas.mpl_connect('draw_event', self.clear),
            ]

    def disconnect(self):
        """Disconnect events."""
        for canvas, info in self._canvas_infos.items():
            for cid in info["cids"]:
                canvas.mpl_disconnect(cid)
            info["cids"].clear()

    def clear(self, event):
        """Clear the cursor."""
        if self.ignore(event):
            return
        if self.useblit:
            for canvas, info in self._canvas_infos.items():
                # someone has switched the canvas on us!  This happens if
                # `savefig` needs to save to a format the previous backend did
                # not support (e.g. saving a figure using an Agg based backend
                # saved to a vector format).
                if canvas is not canvas.figure.canvas:
                    continue
                info["background"] = canvas.copy_from_bbox(canvas.figure.bbox)

    def onmove(self, event):
        axs = [ax for ax in self.axes if ax.contains(event)[0]]
        if self.ignore(event) or not axs or not event.canvas.widgetlock.available(self):
            return
        ax = cbook._topmost_artist(axs)
        xdata, ydata = ((event.xdata, event.ydata) if event.inaxes is ax
                        else ax.transData.inverted().transform((event.x, event.y)))
        for line in self.vlines:
            line.set_xdata((xdata, xdata))
            line.set_visible(self.visible and self.vertOn)
        for line in self.hlines:
            line.set_ydata((ydata, ydata))
            line.set_visible(self.visible and self.horizOn)
        if not (self.visible and (self.vertOn or self.horizOn)):
            return
        # Redraw.
        if self.useblit:
            for canvas, info in self._canvas_infos.items():
                if info["background"]:
                    canvas.restore_region(info["background"])
            if self.vertOn:
                for ax, line in zip(self.axes, self.vlines):
                    ax.draw_artist(line)
            if self.horizOn:
                for ax, line in zip(self.axes, self.hlines):
                    ax.draw_artist(line)
            for canvas in self._canvas_infos:
                canvas.blit()
        else:
            for canvas in self._canvas_infos:
                canvas.draw_idle()


class _SelectorWidget(AxesWidget):

    def __init__(self, ax, onselect=None, useblit=False, button=None,
                 state_modifier_keys=None, use_data_coordinates=False):
        super().__init__(ax)

        self._visible = True
        if onselect is None:
            self.onselect = lambda *args: None
        else:
            self.onselect = onselect
        self.useblit = useblit and self.canvas.supports_blit
        self.connect_default_events()

        self._state_modifier_keys = dict(move=' ', clear='escape',
                                         square='shift', center='control',
                                         rotate='r')
        self._state_modifier_keys.update(state_modifier_keys or {})
        self._use_data_coordinates = use_data_coordinates

        self.background = None

        if isinstance(button, Integral):
            self.validButtons = [button]
        else:
            self.validButtons = button

        # Set to True when a selection is completed, otherwise is False
        self._selection_completed = False

        # will save the data (position at mouseclick)
        self._eventpress = None
        # will save the data (pos. at mouserelease)
        self._eventrelease = None
        self._prev_event = None
        self._state = set()

    def set_active(self, active):
        super().set_active(active)
        if active:
            self.update_background(None)

    def _get_animated_artists(self):
        """
        Convenience method to get all animated artists of the figure containing
        this widget, excluding those already present in self.artists.
        The returned tuple is not sorted by 'z_order': z_order sorting is
        valid only when considering all artists and not only a subset of all
        artists.
        """
        return tuple(a for ax_ in self.ax.get_figure().get_axes()
                     for a in ax_.get_children()
                     if a.get_animated() and a not in self.artists)

    def update_background(self, event):
        """Force an update of the background."""
        # If you add a call to `ignore` here, you'll want to check edge case:
        # `release` can call a draw event even when `ignore` is True.
        if not self.useblit:
            return
        if self.canvas.is_saving():
            return  # saving does not use blitting
        # Make sure that widget artists don't get accidentally included in the
        # background, by re-rendering the background if needed (and then
        # re-re-rendering the canvas with the visible widget artists).
        # We need to remove all artists which will be drawn when updating
        # the selector: if we have animated artists in the figure, it is safer
        # to redrawn by default, in case they have updated by the callback
        # zorder needs to be respected when redrawing
        artists = sorted(self.artists + self._get_animated_artists(),
                         key=lambda a: a.get_zorder())
        needs_redraw = any(artist.get_visible() for artist in artists)
        with ExitStack() as stack:
            if needs_redraw:
                for artist in artists:
                    stack.enter_context(artist._cm_set(visible=False))
                self.canvas.draw()
            self.background = self.canvas.copy_from_bbox(self.ax.bbox)
        if needs_redraw:
            for artist in artists:
                self.ax.draw_artist(artist)

    def connect_default_events(self):
        """Connect the major canvas events to methods."""
        self.connect_event('motion_notify_event', self.onmove)
        self.connect_event('button_press_event', self.press)
        self.connect_event('button_release_event', self.release)
        self.connect_event('draw_event', self.update_background)
        self.connect_event('key_press_event', self.on_key_press)
        self.connect_event('key_release_event', self.on_key_release)
        self.connect_event('scroll_event', self.on_scroll)

    def ignore(self, event):
        # docstring inherited
        if not self.active or not self.ax.get_visible():
            return True
        # If canvas was locked
        if not self.canvas.widgetlock.available(self):
            return True
        if not hasattr(event, 'button'):
            event.button = None
        # Only do rectangle selection if event was triggered
        # with a desired button
        if (self.validButtons is not None
                and event.button not in self.validButtons):
            return True
        # If no button was pressed yet ignore the event if it was out of the Axes.
        if self._eventpress is None:
            return not self.ax.contains(event)[0]
        # If a button was pressed, check if the release-button is the same.
        if event.button == self._eventpress.button:
            return False
        # If a button was pressed, check if the release-button is the same.
        return (not self.ax.contains(event)[0] or
                event.button != self._eventpress.button)

    def update(self):
        """Draw using blit() or draw_idle(), depending on ``self.useblit``."""
        if (not self.ax.get_visible() or
                self.ax.get_figure(root=True)._get_renderer() is None):
            return
        if self.useblit:
            if self.background is not None:
                self.canvas.restore_region(self.background)
            else:
                self.update_background(None)
            # We need to draw all artists, which are not included in the
            # background, therefore we also draw self._get_animated_artists()
            # and we make sure that we respect z_order
            artists = sorted(self.artists + self._get_animated_artists(),
                             key=lambda a: a.get_zorder())
            for artist in artists:
                self.ax.draw_artist(artist)
            self.canvas.blit(self.ax.bbox)
        else:
            self.canvas.draw_idle()

    def _get_data(self, event):
        """Get the xdata and ydata for event, with limits."""
        if event.xdata is None:
            return None, None
        xdata, ydata = self._get_data_coords(event)
        xdata = np.clip(xdata, *self.ax.get_xbound())
        ydata = np.clip(ydata, *self.ax.get_ybound())
        return xdata, ydata

    def _clean_event(self, event):
        """
        Preprocess an event:

        - Replace *event* by the previous event if *event* has no ``xdata``.
        - Get ``xdata`` and ``ydata`` from this widget's Axes, and clip them to the axes
          limits.
        - Update the previous event.
        """
        if event.xdata is None:
            event = self._prev_event
        else:
            event = copy.copy(event)
        event.xdata, event.ydata = self._get_data(event)
        self._prev_event = event
        return event

    def press(self, event):
        """Button press handler and validator."""
        if not self.ignore(event):
            event = self._clean_event(event)
            self._eventpress = event
            self._prev_event = event
            key = event.key or ''
            key = key.replace('ctrl', 'control')
            # move state is locked in on a button press
            if key == self._state_modifier_keys['move']:
                self._state.add('move')
            self._press(event)
            return True
        return False

    def _press(self, event):
        """Button press event handler."""

    def release(self, event):
        """Button release event handler and validator."""
        if not self.ignore(event) and self._eventpress:
            event = self._clean_event(event)
            self._eventrelease = event
            self._release(event)
            self._eventpress = None
            self._eventrelease = None
            self._state.discard('move')
            return True
        return False

    def _release(self, event):
        """Button release event handler."""

    def onmove(self, event):
        """Cursor move event handler and validator."""
        if not self.ignore(event) and self._eventpress:
            event = self._clean_event(event)
            self._onmove(event)
            return True
        return False

    def _onmove(self, event):
        """Cursor move event handler."""

    def on_scroll(self, event):
        """Mouse scroll event handler and validator."""
        if not self.ignore(event):
            self._on_scroll(event)

    def _on_scroll(self, event):
        """Mouse scroll event handler."""

    def on_key_press(self, event):
        """Key press event handler and validator for all selection widgets."""
        if self.active:
            key = event.key or ''
            key = key.replace('ctrl', 'control')
            if key == self._state_modifier_keys['clear']:
                self.clear()
                return
            for (state, modifier) in self._state_modifier_keys.items():
                if modifier in key.split('+'):
                    # 'rotate' is changing _state on press and is not removed
                    # from _state when releasing
                    if state == 'rotate':
                        if state in self._state:
                            self._state.discard(state)
                        else:
                            self._state.add(state)
                    else:
                        self._state.add(state)
            self._on_key_press(event)

    def _on_key_press(self, event):
        """Key press event handler - for widget-specific key press actions."""

    def on_key_release(self, event):
        """Key release event handler and validator."""
        if self.active:
            key = event.key or ''
            for (state, modifier) in self._state_modifier_keys.items():
                # 'rotate' is changing _state on press and is not removed
                # from _state when releasing
                if modifier in key.split('+') and state != 'rotate':
                    self._state.discard(state)
            self._on_key_release(event)

    def _on_key_release(self, event):
        """Key release event handler."""

    def set_visible(self, visible):
        """Set the visibility of the selector artists."""
        self._visible = visible
        for artist in self.artists:
            artist.set_visible(visible)

    def get_visible(self):
        """Get the visibility of the selector artists."""
        return self._visible

    def clear(self):
        """Clear the selection and set the selector ready to make a new one."""
        self._clear_without_update()
        self.update()

    def _clear_without_update(self):
        self._selection_completed = False
        self.set_visible(False)

    @property
    def artists(self):
        """Tuple of the artists of the selector."""
        handles_artists = getattr(self, '_handles_artists', ())
        return (self._selection_artist,) + handles_artists

    def set_props(self, **props):
        """
        Set the properties of the selector artist.

        See the *props* argument in the selector docstring to know which properties are
        supported.
        """
        artist = self._selection_artist
        props = cbook.normalize_kwargs(props, artist)
        artist.set(**props)
        if self.useblit:
            self.update()

    def set_handle_props(self, **handle_props):
        """
        Set the properties of the handles selector artist. See the
        `handle_props` argument in the selector docstring to know which
        properties are supported.
        """
        if not hasattr(self, '_handles_artists'):
            raise NotImplementedError("This selector doesn't have handles.")

        artist = self._handles_artists[0]
        handle_props = cbook.normalize_kwargs(handle_props, artist)
        for handle in self._handles_artists:
            handle.set(**handle_props)
        if self.useblit:
            self.update()
        self._handle_props.update(handle_props)

    def _validate_state(self, state):
        supported_state = [
            key for key, value in self._state_modifier_keys.items()
            if key != 'clear' and value != 'not-applicable'
            ]
        _api.check_in_list(supported_state, state=state)

    def add_state(self, state):
        """
        Add a state to define the widget's behavior. See the
        `state_modifier_keys` parameters for details.

        Parameters
        ----------
        state : str
            Must be a supported state of the selector. See the
            `state_modifier_keys` parameters for details.

        Raises
        ------
        ValueError
            When the state is not supported by the selector.

        """
        self._validate_state(state)
        self._state.add(state)

    def remove_state(self, state):
        """
        Remove a state to define the widget's behavior. See the
        `state_modifier_keys` parameters for details.

        Parameters
        ----------
        state : str
            Must be a supported state of the selector. See the
            `state_modifier_keys` parameters for details.

        Raises
        ------
        ValueError
            When the state is not supported by the selector.

        """
        self._validate_state(state)
        self._state.remove(state)


class SpanSelector(_SelectorWidget):
    """
    Visually select a min/max range on a single axis and call a function with
    those values.

    To guarantee that the selector remains responsive, keep a reference to it.

    In order to turn off the SpanSelector, set ``span_selector.active`` to
    False.  To turn it back on, set it to True.

    Press and release events triggered at the same coordinates outside the
    selection will clear the selector, except when
    ``ignore_event_outside=True``.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`

    onselect : callable with signature ``func(min: float, max: float)``
        A callback function that is called after a release event and the
        selection is created, changed or removed.

    direction : {"horizontal", "vertical"}
        The direction along which to draw the span selector.

    minspan : float, default: 0
        If selection is less than or equal to *minspan*, the selection is
        removed (when already existing) or cancelled.

    useblit : bool, default: False
        If True, use the backend-dependent blitting features for faster
        canvas updates. See the tutorial :ref:`blitting` for details.

    props : dict, default: {'facecolor': 'red', 'alpha': 0.5}
        Dictionary of `.Patch` properties.

    onmove_callback : callable with signature ``func(min: float, max: float)``, optional
        Called on mouse move while the span is being selected.

    interactive : bool, default: False
        Whether to draw a set of handles that allow interaction with the
        widget after it is drawn.

    button : `.MouseButton` or list of `.MouseButton`, default: all buttons
        The mouse buttons which activate the span selector.

    handle_props : dict, default: None
        Properties of the handle lines at the edges of the span. Only used
        when *interactive* is True. See `.Line2D` for valid properties.

    grab_range : float, default: 10
        Distance in pixels within which the interactive tool handles can be activated.

    state_modifier_keys : dict, optional
        Keyboard modifiers which affect the widget's behavior.  Values
        amend the defaults, which are:

        - "clear": Clear the current shape, default: "escape".

    drag_from_anywhere : bool, default: False
        If `True`, the widget can be moved by clicking anywhere within its bounds.

    ignore_event_outside : bool, default: False
        If `True`, the event triggered outside the span selector will be ignored.

    snap_values : 1D array-like, optional
        Snap the selector edges to the given values.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> import matplotlib.widgets as mwidgets
    >>> fig, ax = plt.subplots()
    >>> ax.plot([1, 2, 3], [10, 50, 100])
    >>> def onselect(vmin, vmax):
    ...     print(vmin, vmax)
    >>> span = mwidgets.SpanSelector(ax, onselect, 'horizontal',
    ...                              props=dict(facecolor='blue', alpha=0.5))
    >>> fig.show()

    See also: :doc:`/gallery/widgets/span_selector`
    """

    def __init__(self, ax, onselect, direction, *, minspan=0, useblit=False,
                 props=None, onmove_callback=None, interactive=False,
                 button=None, handle_props=None, grab_range=10,
                 state_modifier_keys=None, drag_from_anywhere=False,
                 ignore_event_outside=False, snap_values=None):

        if state_modifier_keys is None:
            state_modifier_keys = dict(clear='escape',
                                       square='not-applicable',
                                       center='not-applicable',
                                       rotate='not-applicable')
        super().__init__(ax, onselect, useblit=useblit, button=button,
                         state_modifier_keys=state_modifier_keys)

        if props is None:
            props = dict(facecolor='red', alpha=0.5)

        props['animated'] = self.useblit

        self.direction = direction
        self._extents_on_press = None
        self.snap_values = snap_values

        self.onmove_callback = onmove_callback
        self.minspan = minspan

        self.grab_range = grab_range
        self._interactive = interactive
        self._edge_handles = None
        self.drag_from_anywhere = drag_from_anywhere
        self.ignore_event_outside = ignore_event_outside

        self.new_axes(ax, _props=props, _init=True)

        # Setup handles
        self._handle_props = {
            'color': props.get('facecolor', 'r'),
            **cbook.normalize_kwargs(handle_props, Line2D)}

        if self._interactive:
            self._edge_order = ['min', 'max']
            self._setup_edge_handles(self._handle_props)

        self._active_handle = None

    def new_axes(self, ax, *, _props=None, _init=False):
        """Set SpanSelector to operate on a new Axes."""
        reconnect = False
        if _init or self.canvas is not ax.get_figure(root=True).canvas:
            if self.canvas is not None:
                self.disconnect_events()
            reconnect = True
        self.ax = ax
        if reconnect:
            self.connect_default_events()

        # Reset
        self._selection_completed = False

        if self.direction == 'horizontal':
            trans = ax.get_xaxis_transform()
            w, h = 0, 1
        else:
            trans = ax.get_yaxis_transform()
            w, h = 1, 0
        rect_artist = Rectangle((0, 0), w, h, transform=trans, visible=False)
        if _props is not None:
            rect_artist.update(_props)
        elif self._selection_artist is not None:
            rect_artist.update_from(self._selection_artist)

        self.ax.add_patch(rect_artist)
        self._selection_artist = rect_artist

    def _setup_edge_handles(self, props):
        # Define initial position using the axis bounds to keep the same bounds
        if self.direction == 'horizontal':
            positions = self.ax.get_xbound()
        else:
            positions = self.ax.get_ybound()
        self._edge_handles = ToolLineHandles(self.ax, positions,
                                             direction=self.direction,
                                             line_props=props,
                                             useblit=self.useblit)

    @property
    def _handles_artists(self):
        if self._edge_handles is not None:
            return self._edge_handles.artists
        else:
            return ()

    def _set_cursor(self, enabled):
        """Update the canvas cursor based on direction of the selector."""
        if enabled:
            cursor = (backend_tools.Cursors.RESIZE_HORIZONTAL
                      if self.direction == 'horizontal' else
                      backend_tools.Cursors.RESIZE_VERTICAL)
        else:
            cursor = backend_tools.Cursors.POINTER

        self.ax.get_figure(root=True).canvas.set_cursor(cursor)

    def connect_default_events(self):
        # docstring inherited
        super().connect_default_events()
        if getattr(self, '_interactive', False):
            self.connect_event('motion_notify_event', self._hover)

    def _press(self, event):
        """Button press event handler."""
        self._set_cursor(True)
        if self._interactive and self._selection_artist.get_visible():
            self._set_active_handle(event)
        else:
            self._active_handle = None

        if self._active_handle is None or not self._interactive:
            # Clear previous rectangle before drawing new rectangle.
            self.update()

        xdata, ydata = self._get_data_coords(event)
        v = xdata if self.direction == 'horizontal' else ydata

        if self._active_handle is None and not self.ignore_event_outside:
            # when the press event outside the span, we initially set the
            # visibility to False and extents to (v, v)
            # update will be called when setting the extents
            self._visible = False
            self._set_extents((v, v))
            # We need to set the visibility back, so the span selector will be
            # drawn when necessary (span width > 0)
            self._visible = True
        else:
            self.set_visible(True)

        return False

    @property
    def direction(self):
        """Direction of the span selector: 'vertical' or 'horizontal'."""
        return self._direction

    @direction.setter
    def direction(self, direction):
        """Set the direction of the span selector."""
        _api.check_in_list(['horizontal', 'vertical'], direction=direction)
        if hasattr(self, '_direction') and direction != self._direction:
            # remove previous artists
            self._selection_artist.remove()
            if self._interactive:
                self._edge_handles.remove()
            self._direction = direction
            self.new_axes(self.ax)
            if self._interactive:
                self._setup_edge_handles(self._handle_props)
        else:
            self._direction = direction

    def _release(self, event):
        """Button release event handler."""
        self._set_cursor(False)

        if not self._interactive:
            self._selection_artist.set_visible(False)

        if (self._active_handle is None and self._selection_completed and
                self.ignore_event_outside):
            return

        vmin, vmax = self.extents
        span = vmax - vmin

        if span <= self.minspan:
            # Remove span and set self._selection_completed = False
            self.set_visible(False)
            if self._selection_completed:
                # Call onselect, only when the span is already existing
                self.onselect(vmin, vmax)
            self._selection_completed = False
        else:
            self.onselect(vmin, vmax)
            self._selection_completed = True

        self.update()

        self._active_handle = None

        return False

    def _hover(self, event):
        """Update the canvas cursor if it's over a handle."""
        if self.ignore(event):
            return

        if self._active_handle is not None or not self._selection_completed:
            # Do nothing if button is pressed and a handle is active, which may
            # occur with drag_from_anywhere=True.
            # Do nothing if selection is not completed, which occurs when
            # a selector has been cleared
            return

        _, e_dist = self._edge_handles.closest(event.x, event.y)
        self._set_cursor(e_dist <= self.grab_range)

    def _onmove(self, event):
        """Motion notify event handler."""

        xdata, ydata = self._get_data_coords(event)
        if self.direction == 'horizontal':
            v = xdata
            vpress = self._eventpress.xdata
        else:
            v = ydata
            vpress = self._eventpress.ydata

        # move existing span
        # When "dragging from anywhere", `self._active_handle` is set to 'C'
        # (match notation used in the RectangleSelector)
        if self._active_handle == 'C' and self._extents_on_press is not None:
            vmin, vmax = self._extents_on_press
            dv = v - vpress
            vmin += dv
            vmax += dv

        # resize an existing shape
        elif self._active_handle and self._active_handle != 'C':
            vmin, vmax = self._extents_on_press
            if self._active_handle == 'min':
                vmin = v
            else:
                vmax = v
        # new shape
        else:
            # Don't create a new span if there is already one when
            # ignore_event_outside=True
            if self.ignore_event_outside and self._selection_completed:
                return
            vmin, vmax = vpress, v
            if vmin > vmax:
                vmin, vmax = vmax, vmin

        self._set_extents((vmin, vmax))

        if self.onmove_callback is not None:
            self.onmove_callback(vmin, vmax)

        return False

    def _draw_shape(self, vmin, vmax):
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        if self.direction == 'horizontal':
            self._selection_artist.set_x(vmin)
            self._selection_artist.set_width(vmax - vmin)
        else:
            self._selection_artist.set_y(vmin)
            self._selection_artist.set_height(vmax - vmin)

    def _set_active_handle(self, event):
        """Set active handle based on the location of the mouse event."""
        # Note: event.xdata/ydata in data coordinates, event.x/y in pixels
        e_idx, e_dist = self._edge_handles.closest(event.x, event.y)

        # Prioritise center handle over other handles
        # Use 'C' to match the notation used in the RectangleSelector
        if 'move' in self._state:
            self._active_handle = 'C'
        elif e_dist > self.grab_range:
            # Not close to any handles
            self._active_handle = None
            if self.drag_from_anywhere and self._contains(event):
                # Check if we've clicked inside the region
                self._active_handle = 'C'
                self._extents_on_press = self.extents
            else:
                self._active_handle = None
                return
        else:
            # Closest to an edge handle
            self._active_handle = self._edge_order[e_idx]

        # Save coordinates of rectangle at the start of handle movement.
        self._extents_on_press = self.extents

    def _contains(self, event):
        """Return True if event is within the patch."""
        return self._selection_artist.contains(event, radius=0)[0]

    @staticmethod
    def _snap(values, snap_values):
        """Snap values to a given array values (snap_values)."""
        # take into account machine precision
        eps = np.min(np.abs(np.diff(snap_values))) * 1e-12
        return tuple(
            snap_values[np.abs(snap_values - v + np.sign(v) * eps).argmin()]
            for v in values)

    @property
    def extents(self):
        """
        (float, float)
            The values, in data coordinates, for the start and end points of the current
            selection. If there is no selection then the start and end values will be
            the same.
        """
        if self.direction == 'horizontal':
            vmin = self._selection_artist.get_x()
            vmax = vmin + self._selection_artist.get_width()
        else:
            vmin = self._selection_artist.get_y()
            vmax = vmin + self._selection_artist.get_height()
        return vmin, vmax

    @extents.setter
    def extents(self, extents):
        self._set_extents(extents)
        self._selection_completed = True

    def _set_extents(self, extents):
        # Update displayed shape
        if self.snap_values is not None:
            extents = tuple(self._snap(extents, self.snap_values))
        self._draw_shape(*extents)
        if self._interactive:
            # Update displayed handles
            self._edge_handles.set_data(self.extents)
        self.set_visible(self._visible)
        self.update()


class ToolLineHandles:
    """
    Control handles for canvas tools.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        Matplotlib Axes where tool handles are displayed.
    positions : 1D array
        Positions of handles in data coordinates.
    direction : {"horizontal", "vertical"}
        Direction of handles, either 'vertical' or 'horizontal'
    line_props : dict, optional
        Additional line properties. See `.Line2D`.
    useblit : bool, default: True
        Whether to use blitting for faster drawing (if supported by the
        backend). See the tutorial :ref:`blitting`
        for details.
    """

    def __init__(self, ax, positions, direction, *, line_props=None,
                 useblit=True):
        self.ax = ax

        _api.check_in_list(['horizontal', 'vertical'], direction=direction)
        self._direction = direction

        line_props = {
            **(line_props if line_props is not None else {}),
            'visible': False,
            'animated': useblit,
        }

        line_fun = ax.axvline if self.direction == 'horizontal' else ax.axhline

        self._artists = [line_fun(p, **line_props) for p in positions]

    @property
    def artists(self):
        return tuple(self._artists)

    @property
    def positions(self):
        """Positions of the handle in data coordinates."""
        method = 'get_xdata' if self.direction == 'horizontal' else 'get_ydata'
        return [getattr(line, method)()[0] for line in self.artists]

    @property
    def direction(self):
        """Direction of the handle: 'vertical' or 'horizontal'."""
        return self._direction

    def set_data(self, positions):
        """
        Set x- or y-positions of handles, depending on if the lines are
        vertical or horizontal.

        Parameters
        ----------
        positions : tuple of length 2
            Set the positions of the handle in data coordinates
        """
        method = 'set_xdata' if self.direction == 'horizontal' else 'set_ydata'
        for line, p in zip(self.artists, positions):
            getattr(line, method)([p, p])

    def set_visible(self, value):
        """Set the visibility state of the handles artist."""
        for artist in self.artists:
            artist.set_visible(value)

    def set_animated(self, value):
        """Set the animated state of the handles artist."""
        for artist in self.artists:
            artist.set_animated(value)

    def remove(self):
        """Remove the handles artist from the figure."""
        for artist in self._artists:
            artist.remove()

    def closest(self, x, y):
        """
        Return index and pixel distance to closest handle.

        Parameters
        ----------
        x, y : float
            x, y position from which the distance will be calculated to
            determinate the closest handle

        Returns
        -------
        index, distance : index of the handle and its distance from
            position x, y
        """
        if self.direction == 'horizontal':
            p_pts = np.array([
                self.ax.transData.transform((p, 0))[0] for p in self.positions
                ])
            dist = abs(p_pts - x)
        else:
            p_pts = np.array([
                self.ax.transData.transform((0, p))[1] for p in self.positions
                ])
            dist = abs(p_pts - y)
        index = np.argmin(dist)
        return index, dist[index]


class ToolHandles:
    """
    Control handles for canvas tools.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        Matplotlib Axes where tool handles are displayed.
    x, y : 1D arrays
        Coordinates of control handles.
    marker : str, default: 'o'
        Shape of marker used to display handle. See `~.pyplot.plot`.
    marker_props : dict, optional
        Additional marker properties. See `.Line2D`.
    useblit : bool, default: True
        Whether to use blitting for faster drawing (if supported by the
        backend). See the tutorial :ref:`blitting`
        for details.
    """

    def __init__(self, ax, x, y, *, marker='o', marker_props=None, useblit=True):
        self.ax = ax
        props = {'marker': marker, 'markersize': 7, 'markerfacecolor': 'w',
                 'linestyle': 'none', 'alpha': 0.5, 'visible': False,
                 'label': '_nolegend_',
                 **cbook.normalize_kwargs(marker_props, Line2D._alias_map)}
        self._markers = Line2D(x, y, animated=useblit, **props)
        self.ax.add_line(self._markers)

    @property
    def x(self):
        return self._markers.get_xdata()

    @property
    def y(self):
        return self._markers.get_ydata()

    @property
    def artists(self):
        return (self._markers, )

    def set_data(self, pts, y=None):
        """Set x and y positions of handles."""
        if y is not None:
            x = pts
            pts = np.array([x, y])
        self._markers.set_data(pts)

    def set_visible(self, val):
        self._markers.set_visible(val)

    def set_animated(self, val):
        self._markers.set_animated(val)

    def closest(self, x, y):
        """Return index and pixel distance to closest index."""
        pts = np.column_stack([self.x, self.y])
        # Transform data coordinates to pixel coordinates.
        pts = self.ax.transData.transform(pts)
        diff = pts - [x, y]
        dist = np.hypot(*diff.T)
        min_index = np.argmin(dist)
        return min_index, dist[min_index]


_RECTANGLESELECTOR_PARAMETERS_DOCSTRING = \
    r"""
    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.

    onselect : function, optional
        A callback function that is called after a release event and the
        selection is created, changed or removed.
        It must have the signature::

            def onselect(eclick: MouseEvent, erelease: MouseEvent)

        where *eclick* and *erelease* are the mouse click and release
        `.MouseEvent`\s that start and complete the selection.

    minspanx : float, default: 0
        Selections with an x-span less than or equal to *minspanx* are removed
        (when already existing) or cancelled.

    minspany : float, default: 0
        Selections with an y-span less than or equal to *minspanx* are removed
        (when already existing) or cancelled.

    useblit : bool, default: False
        Whether to use blitting for faster drawing (if supported by the
        backend). See the tutorial :ref:`blitting`
        for details.

    props : dict, optional
        Properties with which the __ARTIST_NAME__ is drawn. See
        `.Patch` for valid properties.
        Default:

        ``dict(facecolor='red', edgecolor='black', alpha=0.2, fill=True)``

    spancoords : {"data", "pixels"}, default: "data"
        Whether to interpret *minspanx* and *minspany* in data or in pixel
        coordinates.

    button : `.MouseButton`, list of `.MouseButton`, default: all buttons
        Button(s) that trigger rectangle selection.

    grab_range : float, default: 10
        Distance in pixels within which the interactive tool handles can be
        activated.

    handle_props : dict, optional
        Properties with which the interactive handles (marker artists) are
        drawn. See the marker arguments in `.Line2D` for valid
        properties.  Default values are defined in ``mpl.rcParams`` except for
        the default value of ``markeredgecolor`` which will be the same as the
        ``edgecolor`` property in *props*.

    interactive : bool, default: False
        Whether to draw a set of handles that allow interaction with the
        widget after it is drawn.

    state_modifier_keys : dict, optional
        Keyboard modifiers which affect the widget's behavior.  Values
        amend the defaults, which are:

        - "move": Move the existing shape, default: no modifier.
        - "clear": Clear the current shape, default: "escape".
        - "square": Make the shape square, default: "shift".
        - "center": change the shape around its center, default: "ctrl".
        - "rotate": Rotate the shape around its center between -45° and 45°,
          default: "r".

        "square" and "center" can be combined. The square shape can be defined
        in data or display coordinates as determined by the
        ``use_data_coordinates`` argument specified when creating the selector.

    drag_from_anywhere : bool, default: False
        If `True`, the widget can be moved by clicking anywhere within
        its bounds.

    ignore_event_outside : bool, default: False
        If `True`, the event triggered outside the span selector will be
        ignored.

    use_data_coordinates : bool, default: False
        If `True`, the "square" shape of the selector is defined in
        data coordinates instead of display coordinates.
    """


@_docstring.Substitution(_RECTANGLESELECTOR_PARAMETERS_DOCSTRING.replace(
    '__ARTIST_NAME__', 'rectangle'))
class RectangleSelector(_SelectorWidget):
    """
    Select a rectangular region of an Axes.

    For the cursor to remain responsive you must keep a reference to it.

    Press and release events triggered at the same coordinates outside the
    selection will clear the selector, except when
    ``ignore_event_outside=True``.

    %s

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> import matplotlib.widgets as mwidgets
    >>> fig, ax = plt.subplots()
    >>> ax.plot([1, 2, 3], [10, 50, 100])
    >>> def onselect(eclick, erelease):
    ...     print(eclick.xdata, eclick.ydata)
    ...     print(erelease.xdata, erelease.ydata)
    >>> props = dict(facecolor='blue', alpha=0.5)
    >>> rect = mwidgets.RectangleSelector(ax, onselect, interactive=True,
    ...                                   props=props)
    >>> fig.show()
    >>> rect.add_state('square')

    See also: :doc:`/gallery/widgets/rectangle_selector`
    """

    def __init__(self, ax, onselect=None, *, minspanx=0,
                 minspany=0, useblit=False,
                 props=None, spancoords='data', button=None, grab_range=10,
                 handle_props=None, interactive=False,
                 state_modifier_keys=None, drag_from_anywhere=False,
                 ignore_event_outside=False, use_data_coordinates=False):
        super().__init__(ax, onselect, useblit=useblit, button=button,
                         state_modifier_keys=state_modifier_keys,
                         use_data_coordinates=use_data_coordinates)

        self._interactive = interactive
        self.drag_from_anywhere = drag_from_anywhere
        self.ignore_event_outside = ignore_event_outside
        self._rotation = 0.0
        self._aspect_ratio_correction = 1.0

        # State to allow the option of an interactive selector that can't be
        # interactively drawn. This is used in PolygonSelector as an
        # interactive bounding box to allow the polygon to be easily resized
        self._allow_creation = True

        if props is None:
            props = dict(facecolor='red', edgecolor='black',
                         alpha=0.2, fill=True)
        props = {**props, 'animated': self.useblit}
        self._visible = props.pop('visible', self._visible)
        to_draw = self._init_shape(**props)
        self.ax.add_patch(to_draw)

        self._selection_artist = to_draw
        self._set_aspect_ratio_correction()

        self.minspanx = minspanx
        self.minspany = minspany

        _api.check_in_list(['data', 'pixels'], spancoords=spancoords)
        self.spancoords = spancoords

        self.grab_range = grab_range

        if self._interactive:
            self._handle_props = {
                'markeredgecolor': (props or {}).get('edgecolor', 'black'),
                **cbook.normalize_kwargs(handle_props, Line2D)}

            self._corner_order = ['SW', 'SE', 'NE', 'NW']
            xc, yc = self.corners
            self._corner_handles = ToolHandles(self.ax, xc, yc,
                                               marker_props=self._handle_props,
                                               useblit=self.useblit)

            self._edge_order = ['W', 'S', 'E', 'N']
            xe, ye = self.edge_centers
            self._edge_handles = ToolHandles(self.ax, xe, ye, marker='s',
                                             marker_props=self._handle_props,
                                             useblit=self.useblit)

            xc, yc = self.center
            self._center_handle = ToolHandles(self.ax, [xc], [yc], marker='s',
                                              marker_props=self._handle_props,
                                              useblit=self.useblit)

            self._active_handle = None

        self._extents_on_press = None

    @property
    def _handles_artists(self):
        return (*self._center_handle.artists, *self._corner_handles.artists,
                *self._edge_handles.artists)

    def _init_shape(self, **props):
        return Rectangle((0, 0), 0, 1, visible=False,
                         rotation_point='center', **props)

    def _press(self, event):
        """Button press event handler."""
        # make the drawn box/line visible get the click-coordinates, button, ...
        if self._interactive and self._selection_artist.get_visible():
            self._set_active_handle(event)
        else:
            self._active_handle = None

        if ((self._active_handle is None or not self._interactive) and
                self._allow_creation):
            # Clear previous rectangle before drawing new rectangle.
            self.update()

        if (self._active_handle is None and not self.ignore_event_outside and
                self._allow_creation):
            x, y = self._get_data_coords(event)
            self._visible = False
            self.extents = x, x, y, y
            self._visible = True
        else:
            self.set_visible(True)

        self._extents_on_press = self.extents
        self._rotation_on_press = self._rotation
        self._set_aspect_ratio_correction()

        return False

    def _release(self, event):
        """Button release event handler."""
        if not self._interactive:
            self._selection_artist.set_visible(False)

        if (self._active_handle is None and self._selection_completed and
                self.ignore_event_outside):
            return

        # update the eventpress and eventrelease with the resulting extents
        x0, x1, y0, y1 = self.extents
        self._eventpress.xdata = x0
        self._eventpress.ydata = y0
        xy0 = self.ax.transData.transform([x0, y0])
        self._eventpress.x, self._eventpress.y = xy0

        self._eventrelease.xdata = x1
        self._eventrelease.ydata = y1
        xy1 = self.ax.transData.transform([x1, y1])
        self._eventrelease.x, self._eventrelease.y = xy1

        # calculate dimensions of box or line
        if self.spancoords == 'data':
            spanx = abs(self._eventpress.xdata - self._eventrelease.xdata)
            spany = abs(self._eventpress.ydata - self._eventrelease.ydata)
        elif self.spancoords == 'pixels':
            spanx = abs(self._eventpress.x - self._eventrelease.x)
            spany = abs(self._eventpress.y - self._eventrelease.y)
        else:
            _api.check_in_list(['data', 'pixels'],
                               spancoords=self.spancoords)
        # check if drawn distance (if it exists) is not too small in
        # either x or y-direction
        if spanx <= self.minspanx or spany <= self.minspany:
            if self._selection_completed:
                # Call onselect, only when the selection is already existing
                self.onselect(self._eventpress, self._eventrelease)
            self._clear_without_update()
        else:
            self.onselect(self._eventpress, self._eventrelease)
            self._selection_completed = True

        self.update()
        self._active_handle = None
        self._extents_on_press = None

        return False

    def _onmove(self, event):
        """
        Motion notify event handler.

        This can do one of four things:
        - Translate
        - Rotate
        - Re-size
        - Continue the creation of a new shape
        """
        eventpress = self._eventpress
        # The calculations are done for rotation at zero: we apply inverse
        # transformation to events except when we rotate and move
        state = self._state
        rotate = 'rotate' in state and self._active_handle in self._corner_order
        move = self._active_handle == 'C'
        resize = self._active_handle and not move

        xdata, ydata = self._get_data_coords(event)
        if resize:
            inv_tr = self._get_rotation_transform().inverted()
            xdata, ydata = inv_tr.transform([xdata, ydata])
            eventpress.xdata, eventpress.ydata = inv_tr.transform(
                (eventpress.xdata, eventpress.ydata))

        dx = xdata - eventpress.xdata
        dy = ydata - eventpress.ydata
        # refmax is used when moving the corner handle with the square state
        # and is the maximum between refx and refy
        refmax = None
        if self._use_data_coordinates:
            refx, refy = dx, dy
        else:
            # Get dx/dy in display coordinates
            refx = event.x - eventpress.x
            refy = event.y - eventpress.y

        x0, x1, y0, y1 = self._extents_on_press
        # rotate an existing shape
        if rotate:
            # calculate angle abc
            a = (eventpress.xdata, eventpress.ydata)
            b = self.center
            c = (xdata, ydata)
            angle = (np.arctan2(c[1]-b[1], c[0]-b[0]) -
                     np.arctan2(a[1]-b[1], a[0]-b[0]))
            self.rotation = np.rad2deg(self._rotation_on_press + angle)

        elif resize:
            size_on_press = [x1 - x0, y1 - y0]
            center = (x0 + size_on_press[0] / 2, y0 + size_on_press[1] / 2)

            # Keeping the center fixed
            if 'center' in state:
                # hh, hw are half-height and half-width
                if 'square' in state:
                    # when using a corner, find which reference to use
                    if self._active_handle in self._corner_order:
                        refmax = max(refx, refy, key=abs)
                    if self._active_handle in ['E', 'W'] or refmax == refx:
                        hw = xdata - center[0]
                        hh = hw / self._aspect_ratio_correction
                    else:
                        hh = ydata - center[1]
                        hw = hh * self._aspect_ratio_correction
                else:
                    hw = size_on_press[0] / 2
                    hh = size_on_press[1] / 2
                    # cancel changes in perpendicular direction
                    if self._active_handle in ['E', 'W'] + self._corner_order:
                        hw = abs(xdata - center[0])
                    if self._active_handle in ['N', 'S'] + self._corner_order:
                        hh = abs(ydata - center[1])

                x0, x1, y0, y1 = (center[0] - hw, center[0] + hw,
                                  center[1] - hh, center[1] + hh)

            else:
                # change sign of relative changes to simplify calculation
                # Switch variables so that x1 and/or y1 are updated on move
                if 'W' in self._active_handle:
                    x0 = x1
                if 'S' in self._active_handle:
                    y0 = y1
                if self._active_handle in ['E', 'W'] + self._corner_order:
                    x1 = xdata
                if self._active_handle in ['N', 'S'] + self._corner_order:
                    y1 = ydata
                if 'square' in state:
                    # when using a corner, find which reference to use
                    if self._active_handle in self._corner_order:
                        refmax = max(refx, refy, key=abs)
                    if self._active_handle in ['E', 'W'] or refmax == refx:
                        sign = np.sign(ydata - y0)
                        y1 = y0 + sign * abs(x1 - x0) / self._aspect_ratio_correction
                    else:
                        sign = np.sign(xdata - x0)
                        x1 = x0 + sign * abs(y1 - y0) * self._aspect_ratio_correction

        elif move:
            x0, x1, y0, y1 = self._extents_on_press
            dx = xdata - eventpress.xdata
            dy = ydata - eventpress.ydata
            x0 += dx
            x1 += dx
            y0 += dy
            y1 += dy

        else:
            # Create a new shape
            self._rotation = 0
            # Don't create a new rectangle if there is already one when
            # ignore_event_outside=True
            if ((self.ignore_event_outside and self._selection_completed) or
                    not self._allow_creation):
                return
            center = [eventpress.xdata, eventpress.ydata]
            dx = (xdata - center[0]) / 2
            dy = (ydata - center[1]) / 2

            # square shape
            if 'square' in state:
                refmax = max(refx, refy, key=abs)
                if refmax == refx:
                    dy = np.sign(dy) * abs(dx) / self._aspect_ratio_correction
                else:
                    dx = np.sign(dx) * abs(dy) * self._aspect_ratio_correction

            # from center
            if 'center' in state:
                dx *= 2
                dy *= 2

            # from corner
            else:
                center[0] += dx
                center[1] += dy

            x0, x1, y0, y1 = (center[0] - dx, center[0] + dx,
                              center[1] - dy, center[1] + dy)

        self.extents = x0, x1, y0, y1

    @property
    def _rect_bbox(self):
        return self._selection_artist.get_bbox().bounds

    def _set_aspect_ratio_correction(self):
        aspect_ratio = self.ax._get_aspect_ratio()
        self._selection_artist._aspect_ratio_correction = aspect_ratio
        if self._use_data_coordinates:
            self._aspect_ratio_correction = 1
        else:
            self._aspect_ratio_correction = aspect_ratio

    def _get_rotation_transform(self):
        aspect_ratio = self.ax._get_aspect_ratio()
        return Affine2D().translate(-self.center[0], -self.center[1]) \
                .scale(1, aspect_ratio) \
                .rotate(self._rotation) \
                .scale(1, 1 / aspect_ratio) \
                .translate(*self.center)

    @property
    def corners(self):
        """
        Corners of rectangle in data coordinates from lower left,
        moving clockwise.
        """
        x0, y0, width, height = self._rect_bbox
        xc = x0, x0 + width, x0 + width, x0
        yc = y0, y0, y0 + height, y0 + height
        transform = self._get_rotation_transform()
        coords = transform.transform(np.array([xc, yc]).T).T
        return coords[0], coords[1]

    @property
    def edge_centers(self):
        """
        Midpoint of rectangle edges in data coordinates from left,
        moving anti-clockwise.
        """
        x0, y0, width, height = self._rect_bbox
        w = width / 2.
        h = height / 2.
        xe = x0, x0 + w, x0 + width, x0 + w
        ye = y0 + h, y0, y0 + h, y0 + height
        transform = self._get_rotation_transform()
        coords = transform.transform(np.array([xe, ye]).T).T
        return coords[0], coords[1]

    @property
    def center(self):
        """Center of rectangle in data coordinates."""
        x0, y0, width, height = self._rect_bbox
        return x0 + width / 2., y0 + height / 2.

    @property
    def extents(self):
        """
        Return (xmin, xmax, ymin, ymax) in data coordinates as defined by the
        bounding box before rotation.
        """
        x0, y0, width, height = self._rect_bbox
        xmin, xmax = sorted([x0, x0 + width])
        ymin, ymax = sorted([y0, y0 + height])
        return xmin, xmax, ymin, ymax

    @extents.setter
    def extents(self, extents):
        # Update displayed shape
        self._draw_shape(extents)
        if self._interactive:
            # Update displayed handles
            self._corner_handles.set_data(*self.corners)
            self._edge_handles.set_data(*self.edge_centers)
            x, y = self.center
            self._center_handle.set_data([x], [y])
        self.set_visible(self._visible)
        self.update()

    @property
    def rotation(self):
        """
        Rotation in degree in interval [-45°, 45°]. The rotation is limited in
        range to keep the implementation simple.
        """
        return np.rad2deg(self._rotation)

    @rotation.setter
    def rotation(self, value):
        # Restrict to a limited range of rotation [-45°, 45°] to avoid changing
        # order of handles
        if -45 <= value and value <= 45:
            self._rotation = np.deg2rad(value)
            # call extents setter to draw shape and update handles positions
            self.extents = self.extents

    def _draw_shape(self, extents):
        x0, x1, y0, y1 = extents
        xmin, xmax = sorted([x0, x1])
        ymin, ymax = sorted([y0, y1])
        xlim = sorted(self.ax.get_xlim())
        ylim = sorted(self.ax.get_ylim())

        xmin = max(xlim[0], xmin)
        ymin = max(ylim[0], ymin)
        xmax = min(xmax, xlim[1])
        ymax = min(ymax, ylim[1])

        self._selection_artist.set_x(xmin)
        self._selection_artist.set_y(ymin)
        self._selection_artist.set_width(xmax - xmin)
        self._selection_artist.set_height(ymax - ymin)
        self._selection_artist.set_angle(self.rotation)

    def _set_active_handle(self, event):
        """Set active handle based on the location of the mouse event."""
        # Note: event.xdata/ydata in data coordinates, event.x/y in pixels
        c_idx, c_dist = self._corner_handles.closest(event.x, event.y)
        e_idx, e_dist = self._edge_handles.closest(event.x, event.y)
        m_idx, m_dist = self._center_handle.closest(event.x, event.y)

        if 'move' in self._state:
            self._active_handle = 'C'
        # Set active handle as closest handle, if mouse click is close enough.
        elif m_dist < self.grab_range * 2:
            # Prioritise center handle over other handles
            self._active_handle = 'C'
        elif c_dist > self.grab_range and e_dist > self.grab_range:
            # Not close to any handles
            if self.drag_from_anywhere and self._contains(event):
                # Check if we've clicked inside the region
                self._active_handle = 'C'
            else:
                self._active_handle = None
                return
        elif c_dist < e_dist:
            # Closest to a corner handle
            self._active_handle = self._corner_order[c_idx]
        else:
            # Closest to an edge handle
            self._active_handle = self._edge_order[e_idx]

    def _contains(self, event):
        """Return True if event is within the patch."""
        return self._selection_artist.contains(event, radius=0)[0]

    @property
    def geometry(self):
        """
        Return an array of shape (2, 5) containing the
        x (``RectangleSelector.geometry[1, :]``) and
        y (``RectangleSelector.geometry[0, :]``) data coordinates of the four
        corners of the rectangle starting and ending in the top left corner.
        """
        if hasattr(self._selection_artist, 'get_verts'):
            xfm = self.ax.transData.inverted()
            y, x = xfm.transform(self._selection_artist.get_verts()).T
            return np.array([x, y])
        else:
            return np.array(self._selection_artist.get_data())


@_docstring.Substitution(_RECTANGLESELECTOR_PARAMETERS_DOCSTRING.replace(
    '__ARTIST_NAME__', 'ellipse'))
class EllipseSelector(RectangleSelector):
    """
    Select an elliptical region of an Axes.

    For the cursor to remain responsive you must keep a reference to it.

    Press and release events triggered at the same coordinates outside the
    selection will clear the selector, except when
    ``ignore_event_outside=True``.

    %s

    Examples
    --------
    :doc:`/gallery/widgets/rectangle_selector`
    """
    def _init_shape(self, **props):
        return Ellipse((0, 0), 0, 1, visible=False, **props)

    def _draw_shape(self, extents):
        x0, x1, y0, y1 = extents
        xmin, xmax = sorted([x0, x1])
        ymin, ymax = sorted([y0, y1])
        center = [x0 + (x1 - x0) / 2., y0 + (y1 - y0) / 2.]
        a = (xmax - xmin) / 2.
        b = (ymax - ymin) / 2.

        self._selection_artist.center = center
        self._selection_artist.width = 2 * a
        self._selection_artist.height = 2 * b
        self._selection_artist.angle = self.rotation

    @property
    def _rect_bbox(self):
        x, y = self._selection_artist.center
        width = self._selection_artist.width
        height = self._selection_artist.height
        return x - width / 2., y - height / 2., width, height


class LassoSelector(_SelectorWidget):
    """
    Selection curve of an arbitrary shape.

    For the selector to remain responsive you must keep a reference to it.

    The selected path can be used in conjunction with `~.Path.contains_point`
    to select data points from an image.

    In contrast to `Lasso`, `LassoSelector` is written with an interface
    similar to `RectangleSelector` and `SpanSelector`, and will continue to
    interact with the Axes until disconnected.

    Example usage::

        ax = plt.subplot()
        ax.plot(x, y)

        def onselect(verts):
            print(verts)
        lasso = LassoSelector(ax, onselect)

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.
    onselect : function, optional
        Whenever the lasso is released, the *onselect* function is called and
        passed the vertices of the selected path.
    useblit : bool, default: True
        Whether to use blitting for faster drawing (if supported by the
        backend). See the tutorial :ref:`blitting`
        for details.
    props : dict, optional
        Properties with which the line is drawn, see `.Line2D`
        for valid properties. Default values are defined in ``mpl.rcParams``.
    button : `.MouseButton` or list of `.MouseButton`, optional
        The mouse buttons used for rectangle selection.  Default is ``None``,
        which corresponds to all buttons.
    """

    def __init__(self, ax, onselect=None, *, useblit=True, props=None, button=None):
        super().__init__(ax, onselect, useblit=useblit, button=button)
        self.verts = None
        props = {
            **(props if props is not None else {}),
            # Note that self.useblit may be != useblit, if the canvas doesn't
            # support blitting.
            'animated': self.useblit, 'visible': False,
        }
        line = Line2D([], [], **props)
        self.ax.add_line(line)
        self._selection_artist = line

    def _press(self, event):
        self.verts = [self._get_data(event)]
        self._selection_artist.set_visible(True)

    def _release(self, event):
        if self.verts is not None:
            self.verts.append(self._get_data(event))
            self.onselect(self.verts)
        self._selection_artist.set_data([[], []])
        self._selection_artist.set_visible(False)
        self.verts = None

    def _onmove(self, event):
        if self.verts is None:
            return
        self.verts.append(self._get_data(event))
        self._selection_artist.set_data(list(zip(*self.verts)))

        self.update()


class PolygonSelector(_SelectorWidget):
    """
    Select a polygon region of an Axes.

    Place vertices with each mouse click, and make the selection by completing
    the polygon (clicking on the first vertex). Once drawn individual vertices
    can be moved by clicking and dragging with the left mouse button, or
    removed by clicking the right mouse button.

    In addition, the following modifier keys can be used:

    - Hold *ctrl* and click and drag a vertex to reposition it before the
      polygon has been completed.
    - Hold the *shift* key and click and drag anywhere in the Axes to move
      all vertices.
    - Press the *esc* key to start a new polygon.

    For the selector to remain responsive you must keep a reference to it.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.

    onselect : function, optional
        When a polygon is completed or modified after completion,
        the *onselect* function is called and passed a list of the vertices as
        ``(xdata, ydata)`` tuples.

    useblit : bool, default: False
        Whether to use blitting for faster drawing (if supported by the
        backend). See the tutorial :ref:`blitting`
        for details.

    props : dict, optional
        Properties with which the line is drawn, see `.Line2D` for valid properties.
        Default::

            dict(color='k', linestyle='-', linewidth=2, alpha=0.5)

    handle_props : dict, optional
        Artist properties for the markers drawn at the vertices of the polygon.
        See the marker arguments in `.Line2D` for valid
        properties.  Default values are defined in ``mpl.rcParams`` except for
        the default value of ``markeredgecolor`` which will be the same as the
        ``color`` property in *props*.

    grab_range : float, default: 10
        A vertex is selected (to complete the polygon or to move a vertex) if
        the mouse click is within *grab_range* pixels of the vertex.

    draw_bounding_box : bool, optional
        If `True`, a bounding box will be drawn around the polygon selector
        once it is complete. This box can be used to move and resize the
        selector.

    box_handle_props : dict, optional
        Properties to set for the box handles. See the documentation for the
        *handle_props* argument to `RectangleSelector` for more info.

    box_props : dict, optional
        Properties to set for the box. See the documentation for the *props*
        argument to `RectangleSelector` for more info.

    Examples
    --------
    :doc:`/gallery/widgets/polygon_selector_simple`
    :doc:`/gallery/widgets/polygon_selector_demo`

    Notes
    -----
    If only one point remains after removing points, the selector reverts to an
    incomplete state and you can start drawing a new polygon from the existing
    point.
    """

    def __init__(self, ax, onselect=None, *, useblit=False,
                 props=None, handle_props=None, grab_range=10,
                 draw_bounding_box=False, box_handle_props=None,
                 box_props=None):
        # The state modifiers 'move', 'square', and 'center' are expected by
        # _SelectorWidget but are not supported by PolygonSelector
        # Note: could not use the existing 'move' state modifier in-place of
        # 'move_all' because _SelectorWidget automatically discards 'move'
        # from the state on button release.
        state_modifier_keys = dict(clear='escape', move_vertex='control',
                                   move_all='shift', move='not-applicable',
                                   square='not-applicable',
                                   center='not-applicable',
                                   rotate='not-applicable')
        super().__init__(ax, onselect, useblit=useblit,
                         state_modifier_keys=state_modifier_keys)

        self._xys = [(0, 0)]

        if props is None:
            props = dict(color='k', linestyle='-', linewidth=2, alpha=0.5)
        props = {**props, 'animated': self.useblit}
        self._selection_artist = line = Line2D([], [], **props)
        self.ax.add_line(line)

        if handle_props is None:
            handle_props = dict(markeredgecolor='k',
                                markerfacecolor=props.get('color', 'k'))
        self._handle_props = handle_props
        self._polygon_handles = ToolHandles(self.ax, [], [],
                                            useblit=self.useblit,
                                            marker_props=self._handle_props)

        self._active_handle_idx = -1
        self.grab_range = grab_range

        self.set_visible(True)
        self._draw_box = draw_bounding_box
        self._box = None

        if box_handle_props is None:
            box_handle_props = {}
        self._box_handle_props = self._handle_props.update(box_handle_props)
        self._box_props = box_props

    def _get_bbox(self):
        return self._selection_artist.get_bbox()

    def _add_box(self):
        self._box = RectangleSelector(self.ax,
                                      useblit=self.useblit,
                                      grab_range=self.grab_range,
                                      handle_props=self._box_handle_props,
                                      props=self._box_props,
                                      interactive=True)
        self._box._state_modifier_keys.pop('rotate')
        self._box.connect_event('motion_notify_event', self._scale_polygon)
        self._update_box()
        # Set state that prevents the RectangleSelector from being created
        # by the user
        self._box._allow_creation = False
        self._box._selection_completed = True
        self._draw_polygon()

    def _remove_box(self):
        if self._box is not None:
            self._box.set_visible(False)
            self._box = None

    def _update_box(self):
        # Update selection box extents to the extents of the polygon
        if self._box is not None:
            bbox = self._get_bbox()
            self._box.extents = [bbox.x0, bbox.x1, bbox.y0, bbox.y1]
            # Save a copy
            self._old_box_extents = self._box.extents

    def _scale_polygon(self, event):
        """
        Scale the polygon selector points when the bounding box is moved or
        scaled.

        This is set as a callback on the bounding box RectangleSelector.
        """
        if not self._selection_completed:
            return

        if self._old_box_extents == self._box.extents:
            return

        # Create transform from old box to new box
        x1, y1, w1, h1 = self._box._rect_bbox
        old_bbox = self._get_bbox()
        t = (transforms.Affine2D()
             .translate(-old_bbox.x0, -old_bbox.y0)
             .scale(1 / old_bbox.width, 1 / old_bbox.height)
             .scale(w1, h1)
             .translate(x1, y1))

        # Update polygon verts.  Must be a list of tuples for consistency.
        new_verts = [(x, y) for x, y in t.transform(np.array(self.verts))]
        self._xys = [*new_verts, new_verts[0]]
        self._draw_polygon()
        self._old_box_extents = self._box.extents

    @property
    def _handles_artists(self):
        return self._polygon_handles.artists

    def _remove_vertex(self, i):
        """Remove vertex with index i."""
        if (len(self._xys) > 2 and
                self._selection_completed and
                i in (0, len(self._xys) - 1)):
            # If selecting the first or final vertex, remove both first and
            # last vertex as they are the same for a closed polygon
            self._xys.pop(0)
            self._xys.pop(-1)
            # Close the polygon again by appending the new first vertex to the
            # end
            self._xys.append(self._xys[0])
        else:
            self._xys.pop(i)
        if len(self._xys) <= 2:
            # If only one point left, return to incomplete state to let user
            # start drawing again
            self._selection_completed = False
            self._remove_box()

    def _press(self, event):
        """Button press event handler."""
        # Check for selection of a tool handle.
        if ((self._selection_completed or 'move_vertex' in self._state)
                and len(self._xys) > 0):
            h_idx, h_dist = self._polygon_handles.closest(event.x, event.y)
            if h_dist < self.grab_range:
                self._active_handle_idx = h_idx
        # Save the vertex positions at the time of the press event (needed to
        # support the 'move_all' state modifier).
        self._xys_at_press = self._xys.copy()

    def _release(self, event):
        """Button release event handler."""
        # Release active tool handle.
        if self._active_handle_idx >= 0:
            if event.button == 3:
                self._remove_vertex(self._active_handle_idx)
                self._draw_polygon()
            self._active_handle_idx = -1

        # Complete the polygon.
        elif len(self._xys) > 3 and self._xys[-1] == self._xys[0]:
            self._selection_completed = True
            if self._draw_box and self._box is None:
                self._add_box()

        # Place new vertex.
        elif (not self._selection_completed
              and 'move_all' not in self._state
              and 'move_vertex' not in self._state):
            self._xys.insert(-1, self._get_data_coords(event))

        if self._selection_completed:
            self.onselect(self.verts)

    def onmove(self, event):
        """Cursor move event handler and validator."""
        # Method overrides _SelectorWidget.onmove because the polygon selector
        # needs to process the move callback even if there is no button press.
        # _SelectorWidget.onmove include logic to ignore move event if
        # _eventpress is None.
        if self.ignore(event):
            # Hide the cursor when interactive zoom/pan is active
            if not self.canvas.widgetlock.available(self) and self._xys:
                self._xys[-1] = (np.nan, np.nan)
                self._draw_polygon()
            return False

        else:
            event = self._clean_event(event)
            self._onmove(event)
            return True

    def _onmove(self, event):
        """Cursor move event handler."""
        # Move the active vertex (ToolHandle).
        if self._active_handle_idx >= 0:
            idx = self._active_handle_idx
            self._xys[idx] = self._get_data_coords(event)
            # Also update the end of the polygon line if the first vertex is
            # the active handle and the polygon is completed.
            if idx == 0 and self._selection_completed:
                self._xys[-1] = self._get_data_coords(event)

        # Move all vertices.
        elif 'move_all' in self._state and self._eventpress:
            xdata, ydata = self._get_data_coords(event)
            dx = xdata - self._eventpress.xdata
            dy = ydata - self._eventpress.ydata
            for k in range(len(self._xys)):
                x_at_press, y_at_press = self._xys_at_press[k]
                self._xys[k] = x_at_press + dx, y_at_press + dy

        # Do nothing if completed or waiting for a move.
        elif (self._selection_completed
              or 'move_vertex' in self._state or 'move_all' in self._state):
            return

        # Position pending vertex.
        else:
            # Calculate distance to the start vertex.
            x0, y0 = \
                self._selection_artist.get_transform().transform(self._xys[0])
            v0_dist = np.hypot(x0 - event.x, y0 - event.y)
            # Lock on to the start vertex if near it and ready to complete.
            if len(self._xys) > 3 and v0_dist < self.grab_range:
                self._xys[-1] = self._xys[0]
            else:
                self._xys[-1] = self._get_data_coords(event)

        self._draw_polygon()

    def _on_key_press(self, event):
        """Key press event handler."""
        # Remove the pending vertex if entering the 'move_vertex' or
        # 'move_all' mode
        if (not self._selection_completed
                and ('move_vertex' in self._state or
                     'move_all' in self._state)):
            self._xys.pop()
            self._draw_polygon()

    def _on_key_release(self, event):
        """Key release event handler."""
        # Add back the pending vertex if leaving the 'move_vertex' or
        # 'move_all' mode (by checking the released key)
        if (not self._selection_completed
                and
                (event.key == self._state_modifier_keys.get('move_vertex')
                 or event.key == self._state_modifier_keys.get('move_all'))):
            self._xys.append(self._get_data_coords(event))
            self._draw_polygon()
        # Reset the polygon if the released key is the 'clear' key.
        elif event.key == self._state_modifier_keys.get('clear'):
            event = self._clean_event(event)
            self._xys = [self._get_data_coords(event)]
            self._selection_completed = False
            self._remove_box()
            self.set_visible(True)

    def _draw_polygon_without_update(self):
        """Redraw the polygon based on new vertex positions, no update()."""
        xs, ys = zip(*self._xys) if self._xys else ([], [])
        self._selection_artist.set_data(xs, ys)
        self._update_box()
        # Only show one tool handle at the start and end vertex of the polygon
        # if the polygon is completed or the user is locked on to the start
        # vertex.
        if (self._selection_completed
                or (len(self._xys) > 3
                    and self._xys[-1] == self._xys[0])):
            self._polygon_handles.set_data(xs[:-1], ys[:-1])
        else:
            self._polygon_handles.set_data(xs, ys)

    def _draw_polygon(self):
        """Redraw the polygon based on the new vertex positions."""
        self._draw_polygon_without_update()
        self.update()

    @property
    def verts(self):
        """The polygon vertices, as a list of ``(x, y)`` pairs."""
        return self._xys[:-1]

    @verts.setter
    def verts(self, xys):
        """
        Set the polygon vertices.

        This will remove any preexisting vertices, creating a complete polygon
        with the new vertices.
        """
        self._xys = [*xys, xys[0]]
        self._selection_completed = True
        self.set_visible(True)
        if self._draw_box and self._box is None:
            self._add_box()
        self._draw_polygon()

    def _clear_without_update(self):
        self._selection_completed = False
        self._xys = [(0, 0)]
        self._draw_polygon_without_update()


class Lasso(AxesWidget):
    """
    Selection curve of an arbitrary shape.

    The selected path can be used in conjunction with
    `~matplotlib.path.Path.contains_point` to select data points from an image.

    Unlike `LassoSelector`, this must be initialized with a starting
    point *xy*, and the `Lasso` events are destroyed upon release.

    Parameters
    ----------
    ax : `~matplotlib.axes.Axes`
        The parent Axes for the widget.
    xy : (float, float)
        Coordinates of the start of the lasso.
    callback : callable
        Whenever the lasso is released, the *callback* function is called and
        passed the vertices of the selected path.
    useblit : bool, default: True
        Whether to use blitting for faster drawing (if supported by the
        backend). See the tutorial :ref:`blitting`
        for details.
    props: dict, optional
        Lasso line properties. See `.Line2D` for valid properties.
        Default *props* are::

            {'linestyle' : '-', 'color' : 'black', 'lw' : 2}

        .. versionadded:: 3.9
    """
    def __init__(self, ax, xy, callback, *, useblit=True, props=None):
        super().__init__(ax)

        self.useblit = useblit and self.canvas.supports_blit
        if self.useblit:
            self.background = self.canvas.copy_from_bbox(self.ax.bbox)

        style = {'linestyle': '-', 'color': 'black', 'lw': 2}

        if props is not None:
            style.update(props)

        x, y = xy
        self.verts = [(x, y)]
        self.line = Line2D([x], [y], **style)
        self.ax.add_line(self.line)
        self.callback = callback
        self.connect_event('button_release_event', self.onrelease)
        self.connect_event('motion_notify_event', self.onmove)

    def onrelease(self, event):
        if self.ignore(event):
            return
        if self.verts is not None:
            self.verts.append(self._get_data_coords(event))
            if len(self.verts) > 2:
                self.callback(self.verts)
            self.line.remove()
        self.verts = None
        self.disconnect_events()

    def onmove(self, event):
        if (self.ignore(event)
                or self.verts is None
                or event.button != 1
                or not self.ax.contains(event)[0]):
            return
        self.verts.append(self._get_data_coords(event))
        self.line.set_data(list(zip(*self.verts)))

        if self.useblit:
            self.canvas.restore_region(self.background)
            self.ax.draw_artist(self.line)
            self.canvas.blit(self.ax.bbox)
        else:
            self.canvas.draw_idle()
