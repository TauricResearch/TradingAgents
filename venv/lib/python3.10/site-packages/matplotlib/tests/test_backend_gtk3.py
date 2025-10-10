import os
from matplotlib import pyplot as plt

import pytest
from unittest import mock


@pytest.mark.backend("gtk3agg", skip_on_importerror=True)
def test_correct_key():
    pytest.xfail("test_widget_send_event is not triggering key_press_event")

    from gi.repository import Gdk, Gtk  # type: ignore[import]
    fig = plt.figure()
    buf = []

    def send(event):
        for key, mod in [
                (Gdk.KEY_a, Gdk.ModifierType.SHIFT_MASK),
                (Gdk.KEY_a, 0),
                (Gdk.KEY_a, Gdk.ModifierType.CONTROL_MASK),
                (Gdk.KEY_agrave, 0),
                (Gdk.KEY_Control_L, Gdk.ModifierType.MOD1_MASK),
                (Gdk.KEY_Alt_L, Gdk.ModifierType.CONTROL_MASK),
                (Gdk.KEY_agrave,
                 Gdk.ModifierType.CONTROL_MASK
                 | Gdk.ModifierType.MOD1_MASK
                 | Gdk.ModifierType.MOD4_MASK),
                (0xfd16, 0),   # KEY_3270_Play.
                (Gdk.KEY_BackSpace, 0),
                (Gdk.KEY_BackSpace, Gdk.ModifierType.CONTROL_MASK),
        ]:
            # This is not actually really the right API: it depends on the
            # actual keymap (e.g. on Azerty, shift+agrave -> 0).
            Gtk.test_widget_send_key(fig.canvas, key, mod)

    def receive(event):
        buf.append(event.key)
        if buf == [
                "A", "a", "ctrl+a",
                "\N{LATIN SMALL LETTER A WITH GRAVE}",
                "alt+control", "ctrl+alt",
                "ctrl+alt+super+\N{LATIN SMALL LETTER A WITH GRAVE}",
                # (No entry for KEY_3270_Play.)
                "backspace", "ctrl+backspace",
        ]:
            plt.close(fig)

    fig.canvas.mpl_connect("draw_event", send)
    fig.canvas.mpl_connect("key_press_event", receive)
    plt.show()


@pytest.mark.backend("gtk3agg", skip_on_importerror=True)
def test_save_figure_return():
    from gi.repository import Gtk
    fig, ax = plt.subplots()
    ax.imshow([[1]])
    with mock.patch("gi.repository.Gtk.FileFilter") as fileFilter:
        filt = fileFilter.return_value
        filt.get_name.return_value = "Portable Network Graphics"
        with mock.patch("gi.repository.Gtk.FileChooserDialog") as dialogChooser:
            dialog = dialogChooser.return_value
            dialog.get_filter.return_value = filt
            dialog.get_filename.return_value = "foobar.png"
            dialog.run.return_value = Gtk.ResponseType.OK
            fname = fig.canvas.manager.toolbar.save_figure()
            os.remove("foobar.png")
            assert fname == "foobar.png"

            with mock.patch("gi.repository.Gtk.MessageDialog"):
                dialog.get_filename.return_value = None
                dialog.run.return_value = Gtk.ResponseType.OK
                fname = fig.canvas.manager.toolbar.save_figure()
                assert fname is None
