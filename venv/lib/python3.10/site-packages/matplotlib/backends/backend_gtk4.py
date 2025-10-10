import functools
import io
import os

import matplotlib as mpl
from matplotlib import _api, backend_tools, cbook
from matplotlib.backend_bases import (
    ToolContainerBase, MouseButton,
    KeyEvent, LocationEvent, MouseEvent, ResizeEvent, CloseEvent)

try:
    import gi
except ImportError as err:
    raise ImportError("The GTK4 backends require PyGObject") from err

try:
    # :raises ValueError: If module/version is already loaded, already
    # required, or unavailable.
    gi.require_version("Gtk", "4.0")
except ValueError as e:
    # in this case we want to re-raise as ImportError so the
    # auto-backend selection logic correctly skips.
    raise ImportError(e) from e

from gi.repository import Gio, GLib, Gtk, Gdk, GdkPixbuf
from . import _backend_gtk
from ._backend_gtk import (  # noqa: F401 # pylint: disable=W0611
    _BackendGTK, _FigureCanvasGTK, _FigureManagerGTK, _NavigationToolbar2GTK,
    TimerGTK as TimerGTK4,
)

_GOBJECT_GE_3_47 = gi.version_info >= (3, 47, 0)
_GTK_GE_4_12 = Gtk.check_version(4, 12, 0) is None


class FigureCanvasGTK4(_FigureCanvasGTK, Gtk.DrawingArea):
    required_interactive_framework = "gtk4"
    supports_blit = False
    manager_class = _api.classproperty(lambda cls: FigureManagerGTK4)

    def __init__(self, figure=None):
        super().__init__(figure=figure)

        self.set_hexpand(True)
        self.set_vexpand(True)

        self._idle_draw_id = 0
        self._rubberband_rect = None

        self.set_draw_func(self._draw_func)
        self.connect('resize', self.resize_event)
        if _GTK_GE_4_12:
            self.connect('realize', self._realize_event)
        else:
            self.connect('notify::scale-factor', self._update_device_pixel_ratio)

        click = Gtk.GestureClick()
        click.set_button(0)  # All buttons.
        click.connect('pressed', self.button_press_event)
        click.connect('released', self.button_release_event)
        self.add_controller(click)

        key = Gtk.EventControllerKey()
        key.connect('key-pressed', self.key_press_event)
        key.connect('key-released', self.key_release_event)
        self.add_controller(key)

        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self.motion_notify_event)
        motion.connect('enter', self.enter_notify_event)
        motion.connect('leave', self.leave_notify_event)
        self.add_controller(motion)

        scroll = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect('scroll', self.scroll_event)
        self.add_controller(scroll)

        self.set_focusable(True)

        css = Gtk.CssProvider()
        style = '.matplotlib-canvas { background-color: white; }'
        if Gtk.check_version(4, 9, 3) is None:
            css.load_from_data(style, -1)
        else:
            css.load_from_data(style.encode('utf-8'))
        style_ctx = self.get_style_context()
        style_ctx.add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        style_ctx.add_class("matplotlib-canvas")

    def destroy(self):
        CloseEvent("close_event", self)._process()

    def set_cursor(self, cursor):
        # docstring inherited
        self.set_cursor_from_name(_backend_gtk.mpl_to_gtk_cursor_name(cursor))

    def _mpl_coords(self, xy=None):
        """
        Convert the *xy* position of a GTK event, or of the current cursor
        position if *xy* is None, to Matplotlib coordinates.

        GTK use logical pixels, but the figure is scaled to physical pixels for
        rendering.  Transform to physical pixels so that all of the down-stream
        transforms work as expected.

        Also, the origin is different and needs to be corrected.
        """
        if xy is None:
            surface = self.get_native().get_surface()
            is_over, x, y, mask = surface.get_device_position(
                self.get_display().get_default_seat().get_pointer())
        else:
            x, y = xy
        x = x * self.device_pixel_ratio
        # flip y so y=0 is bottom of canvas
        y = self.figure.bbox.height - y * self.device_pixel_ratio
        return x, y

    def scroll_event(self, controller, dx, dy):
        MouseEvent(
            "scroll_event", self, *self._mpl_coords(), step=dy,
            modifiers=self._mpl_modifiers(controller),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()
        return True

    def button_press_event(self, controller, n_press, x, y):
        MouseEvent(
            "button_press_event", self, *self._mpl_coords((x, y)),
            controller.get_current_button(),
            modifiers=self._mpl_modifiers(controller),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()
        self.grab_focus()

    def button_release_event(self, controller, n_press, x, y):
        MouseEvent(
            "button_release_event", self, *self._mpl_coords((x, y)),
            controller.get_current_button(),
            modifiers=self._mpl_modifiers(controller),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()

    def key_press_event(self, controller, keyval, keycode, state):
        KeyEvent(
            "key_press_event", self, self._get_key(keyval, keycode, state),
            *self._mpl_coords(),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()
        return True

    def key_release_event(self, controller, keyval, keycode, state):
        KeyEvent(
            "key_release_event", self, self._get_key(keyval, keycode, state),
            *self._mpl_coords(),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()
        return True

    def motion_notify_event(self, controller, x, y):
        MouseEvent(
            "motion_notify_event", self, *self._mpl_coords((x, y)),
            buttons=self._mpl_buttons(controller),
            modifiers=self._mpl_modifiers(controller),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()

    def enter_notify_event(self, controller, x, y):
        LocationEvent(
            "figure_enter_event", self, *self._mpl_coords((x, y)),
            modifiers=self._mpl_modifiers(),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()

    def leave_notify_event(self, controller):
        LocationEvent(
            "figure_leave_event", self, *self._mpl_coords(),
            modifiers=self._mpl_modifiers(),
            guiEvent=controller.get_current_event() if _GOBJECT_GE_3_47 else None,
        )._process()

    def resize_event(self, area, width, height):
        self._update_device_pixel_ratio()
        dpi = self.figure.dpi
        winch = width * self.device_pixel_ratio / dpi
        hinch = height * self.device_pixel_ratio / dpi
        self.figure.set_size_inches(winch, hinch, forward=False)
        ResizeEvent("resize_event", self)._process()
        self.draw_idle()

    def _mpl_buttons(self, controller):
        # NOTE: This spews "Broken accounting of active state" warnings on
        # right click on macOS.
        surface = self.get_native().get_surface()
        is_over, x, y, event_state = surface.get_device_position(
            self.get_display().get_default_seat().get_pointer())
        # NOTE: alternatively we could use
        #   event_state = controller.get_current_event_state()
        # but for button_press/button_release this would report the state
        # *prior* to the event rather than after it; the above reports the
        # state *after* it.
        mod_table = [
            (MouseButton.LEFT, Gdk.ModifierType.BUTTON1_MASK),
            (MouseButton.MIDDLE, Gdk.ModifierType.BUTTON2_MASK),
            (MouseButton.RIGHT, Gdk.ModifierType.BUTTON3_MASK),
            (MouseButton.BACK, Gdk.ModifierType.BUTTON4_MASK),
            (MouseButton.FORWARD, Gdk.ModifierType.BUTTON5_MASK),
        ]
        return {name for name, mask in mod_table if event_state & mask}

    def _mpl_modifiers(self, controller=None):
        if controller is None:
            surface = self.get_native().get_surface()
            is_over, x, y, event_state = surface.get_device_position(
                self.get_display().get_default_seat().get_pointer())
        else:
            event_state = controller.get_current_event_state()
        mod_table = [
            ("ctrl", Gdk.ModifierType.CONTROL_MASK),
            ("alt", Gdk.ModifierType.ALT_MASK),
            ("shift", Gdk.ModifierType.SHIFT_MASK),
            ("super", Gdk.ModifierType.SUPER_MASK),
        ]
        return [name for name, mask in mod_table if event_state & mask]

    def _get_key(self, keyval, keycode, state):
        unikey = chr(Gdk.keyval_to_unicode(keyval))
        key = cbook._unikey_or_keysym_to_mplkey(
            unikey,
            Gdk.keyval_name(keyval))
        modifiers = [
            ("ctrl", Gdk.ModifierType.CONTROL_MASK, "control"),
            ("alt", Gdk.ModifierType.ALT_MASK, "alt"),
            ("shift", Gdk.ModifierType.SHIFT_MASK, "shift"),
            ("super", Gdk.ModifierType.SUPER_MASK, "super"),
        ]
        mods = [
            mod for mod, mask, mod_key in modifiers
            if (mod_key != key and state & mask
                and not (mod == "shift" and unikey.isprintable()))]
        return "+".join([*mods, key])

    def _realize_event(self, obj):
        surface = self.get_native().get_surface()
        surface.connect('notify::scale', self._update_device_pixel_ratio)
        self._update_device_pixel_ratio()

    def _update_device_pixel_ratio(self, *args, **kwargs):
        # We need to be careful in cases with mixed resolution displays if
        # device_pixel_ratio changes.
        if _GTK_GE_4_12:
            scale = self.get_native().get_surface().get_scale()
        else:
            scale = self.get_scale_factor()
        assert scale is not None
        if self._set_device_pixel_ratio(scale):
            self.draw()

    def _draw_rubberband(self, rect):
        self._rubberband_rect = rect
        # TODO: Only update the rubberband area.
        self.queue_draw()

    def _draw_func(self, drawing_area, ctx, width, height):
        self.on_draw_event(self, ctx)
        self._post_draw(self, ctx)

    def _post_draw(self, widget, ctx):
        if self._rubberband_rect is None:
            return

        lw = 1
        dash = 3
        x0, y0, w, h = (dim / self.device_pixel_ratio
                        for dim in self._rubberband_rect)
        x1 = x0 + w
        y1 = y0 + h

        # Draw the lines from x0, y0 towards x1, y1 so that the
        # dashes don't "jump" when moving the zoom box.
        ctx.move_to(x0, y0)
        ctx.line_to(x0, y1)
        ctx.move_to(x0, y0)
        ctx.line_to(x1, y0)
        ctx.move_to(x0, y1)
        ctx.line_to(x1, y1)
        ctx.move_to(x1, y0)
        ctx.line_to(x1, y1)

        ctx.set_antialias(1)
        ctx.set_line_width(lw)
        ctx.set_dash((dash, dash), 0)
        ctx.set_source_rgb(0, 0, 0)
        ctx.stroke_preserve()

        ctx.set_dash((dash, dash), dash)
        ctx.set_source_rgb(1, 1, 1)
        ctx.stroke()

    def on_draw_event(self, widget, ctx):
        # to be overwritten by GTK4Agg or GTK4Cairo
        pass

    def draw(self):
        # docstring inherited
        if self.is_drawable():
            self.queue_draw()

    def draw_idle(self):
        # docstring inherited
        if self._idle_draw_id != 0:
            return
        def idle_draw(*args):
            try:
                self.draw()
            finally:
                self._idle_draw_id = 0
            return False
        self._idle_draw_id = GLib.idle_add(idle_draw)

    def flush_events(self):
        # docstring inherited
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(True)


class NavigationToolbar2GTK4(_NavigationToolbar2GTK, Gtk.Box):
    def __init__(self, canvas):
        Gtk.Box.__init__(self)

        self.add_css_class('toolbar')

        self._gtk_ids = {}
        for text, tooltip_text, image_file, callback in self.toolitems:
            if text is None:
                self.append(Gtk.Separator())
                continue
            image = Gtk.Image.new_from_gicon(
                Gio.Icon.new_for_string(
                    str(cbook._get_data_path('images',
                                             f'{image_file}-symbolic.svg'))))
            self._gtk_ids[text] = button = (
                Gtk.ToggleButton() if callback in ['zoom', 'pan'] else
                Gtk.Button())
            button.set_child(image)
            button.add_css_class('flat')
            button.add_css_class('image-button')
            # Save the handler id, so that we can block it as needed.
            button._signal_handler = button.connect(
                'clicked', getattr(self, callback))
            button.set_tooltip_text(tooltip_text)
            self.append(button)

        # This filler item ensures the toolbar is always at least two text
        # lines high. Otherwise the canvas gets redrawn as the mouse hovers
        # over images because those use two-line messages which resize the
        # toolbar.
        label = Gtk.Label()
        label.set_markup(
            '<small>\N{NO-BREAK SPACE}\n\N{NO-BREAK SPACE}</small>')
        label.set_hexpand(True)  # Push real message to the right.
        self.append(label)

        self.message = Gtk.Label()
        self.message.set_justify(Gtk.Justification.RIGHT)
        self.append(self.message)

        _NavigationToolbar2GTK.__init__(self, canvas)

    def save_figure(self, *args):
        dialog = Gtk.FileChooserNative(
            title='Save the figure',
            transient_for=self.canvas.get_root(),
            action=Gtk.FileChooserAction.SAVE,
            modal=True)
        self._save_dialog = dialog  # Must keep a reference.

        ff = Gtk.FileFilter()
        ff.set_name('All files')
        ff.add_pattern('*')
        dialog.add_filter(ff)
        dialog.set_filter(ff)

        formats = []
        default_format = None
        for i, (name, fmts) in enumerate(
                self.canvas.get_supported_filetypes_grouped().items()):
            ff = Gtk.FileFilter()
            ff.set_name(name)
            for fmt in fmts:
                ff.add_pattern(f'*.{fmt}')
            dialog.add_filter(ff)
            formats.append(name)
            if self.canvas.get_default_filetype() in fmts:
                default_format = i
        # Setting the choice doesn't always work, so make sure the default
        # format is first.
        formats = [formats[default_format], *formats[:default_format],
                   *formats[default_format+1:]]
        dialog.add_choice('format', 'File format', formats, formats)
        dialog.set_choice('format', formats[0])

        dialog.set_current_folder(Gio.File.new_for_path(
            os.path.expanduser(mpl.rcParams['savefig.directory'])))
        dialog.set_current_name(self.canvas.get_default_filename())

        @functools.partial(dialog.connect, 'response')
        def on_response(dialog, response):
            file = dialog.get_file()
            fmt = dialog.get_choice('format')
            fmt = self.canvas.get_supported_filetypes_grouped()[fmt][0]
            dialog.destroy()
            self._save_dialog = None
            if response != Gtk.ResponseType.ACCEPT:
                return
            # Save dir for next time, unless empty str (which means use cwd).
            if mpl.rcParams['savefig.directory']:
                parent = file.get_parent()
                mpl.rcParams['savefig.directory'] = parent.get_path()
            try:
                self.canvas.figure.savefig(file.get_path(), format=fmt)
            except Exception as e:
                msg = Gtk.MessageDialog(
                    transient_for=self.canvas.get_root(),
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK, modal=True,
                    text=str(e))
                msg.show()

        dialog.show()
        return self.UNKNOWN_SAVED_STATUS


class ToolbarGTK4(ToolContainerBase, Gtk.Box):
    _icon_extension = '-symbolic.svg'

    def __init__(self, toolmanager):
        ToolContainerBase.__init__(self, toolmanager)
        Gtk.Box.__init__(self)
        self.set_property('orientation', Gtk.Orientation.HORIZONTAL)

        # Tool items are created later, but must appear before the message.
        self._tool_box = Gtk.Box()
        self.append(self._tool_box)
        self._groups = {}
        self._toolitems = {}

        # This filler item ensures the toolbar is always at least two text
        # lines high. Otherwise the canvas gets redrawn as the mouse hovers
        # over images because those use two-line messages which resize the
        # toolbar.
        label = Gtk.Label()
        label.set_markup(
            '<small>\N{NO-BREAK SPACE}\n\N{NO-BREAK SPACE}</small>')
        label.set_hexpand(True)  # Push real message to the right.
        self.append(label)

        self._message = Gtk.Label()
        self._message.set_justify(Gtk.Justification.RIGHT)
        self.append(self._message)

    def add_toolitem(self, name, group, position, image_file, description,
                     toggle):
        if toggle:
            button = Gtk.ToggleButton()
        else:
            button = Gtk.Button()
        button.set_label(name)
        button.add_css_class('flat')

        if image_file is not None:
            image = Gtk.Image.new_from_gicon(
                Gio.Icon.new_for_string(image_file))
            button.set_child(image)
            button.add_css_class('image-button')

        if position is None:
            position = -1

        self._add_button(button, group, position)
        signal = button.connect('clicked', self._call_tool, name)
        button.set_tooltip_text(description)
        self._toolitems.setdefault(name, [])
        self._toolitems[name].append((button, signal))

    def _find_child_at_position(self, group, position):
        children = [None]
        child = self._groups[group].get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        return children[position]

    def _add_button(self, button, group, position):
        if group not in self._groups:
            if self._groups:
                self._add_separator()
            group_box = Gtk.Box()
            self._tool_box.append(group_box)
            self._groups[group] = group_box
        self._groups[group].insert_child_after(
            button, self._find_child_at_position(group, position))

    def _call_tool(self, btn, name):
        self.trigger_tool(name)

    def toggle_toolitem(self, name, toggled):
        if name not in self._toolitems:
            return
        for toolitem, signal in self._toolitems[name]:
            toolitem.handler_block(signal)
            toolitem.set_active(toggled)
            toolitem.handler_unblock(signal)

    def remove_toolitem(self, name):
        for toolitem, _signal in self._toolitems.pop(name, []):
            for group in self._groups:
                if toolitem in self._groups[group]:
                    self._groups[group].remove(toolitem)

    def _add_separator(self):
        sep = Gtk.Separator()
        sep.set_property("orientation", Gtk.Orientation.VERTICAL)
        self._tool_box.append(sep)

    def set_message(self, s):
        self._message.set_label(s)


@backend_tools._register_tool_class(FigureCanvasGTK4)
class SaveFigureGTK4(backend_tools.SaveFigureBase):
    def trigger(self, *args, **kwargs):
        NavigationToolbar2GTK4.save_figure(
            self._make_classic_style_pseudo_toolbar())


@backend_tools._register_tool_class(FigureCanvasGTK4)
class HelpGTK4(backend_tools.ToolHelpBase):
    def _normalize_shortcut(self, key):
        """
        Convert Matplotlib key presses to GTK+ accelerator identifiers.

        Related to `FigureCanvasGTK4._get_key`.
        """
        special = {
            'backspace': 'BackSpace',
            'pagedown': 'Page_Down',
            'pageup': 'Page_Up',
            'scroll_lock': 'Scroll_Lock',
        }

        parts = key.split('+')
        mods = ['<' + mod + '>' for mod in parts[:-1]]
        key = parts[-1]

        if key in special:
            key = special[key]
        elif len(key) > 1:
            key = key.capitalize()
        elif key.isupper():
            mods += ['<shift>']

        return ''.join(mods) + key

    def _is_valid_shortcut(self, key):
        """
        Check for a valid shortcut to be displayed.

        - GTK will never send 'cmd+' (see `FigureCanvasGTK4._get_key`).
        - The shortcut window only shows keyboard shortcuts, not mouse buttons.
        """
        return 'cmd+' not in key and not key.startswith('MouseButton.')

    def trigger(self, *args):
        section = Gtk.ShortcutsSection()

        for name, tool in sorted(self.toolmanager.tools.items()):
            if not tool.description:
                continue

            # Putting everything in a separate group allows GTK to
            # automatically split them into separate columns/pages, which is
            # useful because we have lots of shortcuts, some with many keys
            # that are very wide.
            group = Gtk.ShortcutsGroup()
            section.append(group)
            # A hack to remove the title since we have no group naming.
            child = group.get_first_child()
            while child is not None:
                child.set_visible(False)
                child = child.get_next_sibling()

            shortcut = Gtk.ShortcutsShortcut(
                accelerator=' '.join(
                    self._normalize_shortcut(key)
                    for key in self.toolmanager.get_tool_keymap(name)
                    if self._is_valid_shortcut(key)),
                title=tool.name,
                subtitle=tool.description)
            group.append(shortcut)

        window = Gtk.ShortcutsWindow(
            title='Help',
            modal=True,
            transient_for=self._figure.canvas.get_root())
        window.set_child(section)

        window.show()


@backend_tools._register_tool_class(FigureCanvasGTK4)
class ToolCopyToClipboardGTK4(backend_tools.ToolCopyToClipboardBase):
    def trigger(self, *args, **kwargs):
        with io.BytesIO() as f:
            self.canvas.print_rgba(f)
            w, h = self.canvas.get_width_height()
            pb = GdkPixbuf.Pixbuf.new_from_data(f.getbuffer(),
                                                GdkPixbuf.Colorspace.RGB, True,
                                                8, w, h, w*4)
        clipboard = self.canvas.get_clipboard()
        clipboard.set(pb)


backend_tools._register_tool_class(
    FigureCanvasGTK4, _backend_gtk.ConfigureSubplotsGTK)
backend_tools._register_tool_class(
    FigureCanvasGTK4, _backend_gtk.RubberbandGTK)
Toolbar = ToolbarGTK4


class FigureManagerGTK4(_FigureManagerGTK):
    _toolbar2_class = NavigationToolbar2GTK4
    _toolmanager_toolbar_class = ToolbarGTK4


@_BackendGTK.export
class _BackendGTK4(_BackendGTK):
    FigureCanvas = FigureCanvasGTK4
    FigureManager = FigureManagerGTK4
