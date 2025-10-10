#
# The Python Imaging Library.
# $Id$
#
# im.show() drivers
#
# History:
# 2008-04-06 fl   Created
#
# Copyright (c) Secret Labs AB 2008.
#
# See the README file for information on usage and redistribution.
#
from __future__ import annotations

import abc
import os
import shutil
import subprocess
import sys
from shlex import quote
from typing import Any

from . import Image

_viewers = []


def register(viewer: type[Viewer] | Viewer, order: int = 1) -> None:
    """
    The :py:func:`register` function is used to register additional viewers::

        from PIL import ImageShow
        ImageShow.register(MyViewer())  # MyViewer will be used as a last resort
        ImageShow.register(MySecondViewer(), 0)  # MySecondViewer will be prioritised
        ImageShow.register(ImageShow.XVViewer(), 0)  # XVViewer will be prioritised

    :param viewer: The viewer to be registered.
    :param order:
        Zero or a negative integer to prepend this viewer to the list,
        a positive integer to append it.
    """
    if isinstance(viewer, type) and issubclass(viewer, Viewer):
        viewer = viewer()
    if order > 0:
        _viewers.append(viewer)
    else:
        _viewers.insert(0, viewer)


def show(image: Image.Image, title: str | None = None, **options: Any) -> bool:
    r"""
    Display a given image.

    :param image: An image object.
    :param title: Optional title. Not all viewers can display the title.
    :param \**options: Additional viewer options.
    :returns: ``True`` if a suitable viewer was found, ``False`` otherwise.
    """
    for viewer in _viewers:
        if viewer.show(image, title=title, **options):
            return True
    return False


class Viewer:
    """Base class for viewers."""

    # main api

    def show(self, image: Image.Image, **options: Any) -> int:
        """
        The main function for displaying an image.
        Converts the given image to the target format and displays it.
        """

        if not (
            image.mode in ("1", "RGBA")
            or (self.format == "PNG" and image.mode in ("I;16", "LA"))
        ):
            base = Image.getmodebase(image.mode)
            if image.mode != base:
                image = image.convert(base)

        return self.show_image(image, **options)

    # hook methods

    format: str | None = None
    """The format to convert the image into."""
    options: dict[str, Any] = {}
    """Additional options used to convert the image."""

    def get_format(self, image: Image.Image) -> str | None:
        """Return format name, or ``None`` to save as PGM/PPM."""
        return self.format

    def get_command(self, file: str, **options: Any) -> str:
        """
        Returns the command used to display the file.
        Not implemented in the base class.
        """
        msg = "unavailable in base viewer"
        raise NotImplementedError(msg)

    def save_image(self, image: Image.Image) -> str:
        """Save to temporary file and return filename."""
        return image._dump(format=self.get_format(image), **self.options)

    def show_image(self, image: Image.Image, **options: Any) -> int:
        """Display the given image."""
        return self.show_file(self.save_image(image), **options)

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        os.system(self.get_command(path, **options))  # nosec
        return 1


# --------------------------------------------------------------------


class WindowsViewer(Viewer):
    """The default viewer on Windows is the default system application for PNG files."""

    format = "PNG"
    options = {"compress_level": 1, "save_all": True}

    def get_command(self, file: str, **options: Any) -> str:
        return (
            f'start "Pillow" /WAIT "{file}" '
            "&& ping -n 4 127.0.0.1 >NUL "
            f'&& del /f "{file}"'
        )

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        subprocess.Popen(
            self.get_command(path, **options),
            shell=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW"),
        )  # nosec
        return 1


if sys.platform == "win32":
    register(WindowsViewer)


class MacViewer(Viewer):
    """The default viewer on macOS using ``Preview.app``."""

    format = "PNG"
    options = {"compress_level": 1, "save_all": True}

    def get_command(self, file: str, **options: Any) -> str:
        # on darwin open returns immediately resulting in the temp
        # file removal while app is opening
        command = "open -a Preview.app"
        command = f"({command} {quote(file)}; sleep 20; rm -f {quote(file)})&"
        return command

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        subprocess.call(["open", "-a", "Preview.app", path])

        pyinstaller = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        executable = (not pyinstaller and sys.executable) or shutil.which("python3")
        if executable:
            subprocess.Popen(
                [
                    executable,
                    "-c",
                    "import os, sys, time; time.sleep(20); os.remove(sys.argv[1])",
                    path,
                ]
            )
        return 1


if sys.platform == "darwin":
    register(MacViewer)


class UnixViewer(abc.ABC, Viewer):
    format = "PNG"
    options = {"compress_level": 1, "save_all": True}

    @abc.abstractmethod
    def get_command_ex(self, file: str, **options: Any) -> tuple[str, str]:
        pass

    def get_command(self, file: str, **options: Any) -> str:
        command = self.get_command_ex(file, **options)[0]
        return f"{command} {quote(file)}"


class XDGViewer(UnixViewer):
    """
    The freedesktop.org ``xdg-open`` command.
    """

    def get_command_ex(self, file: str, **options: Any) -> tuple[str, str]:
        command = executable = "xdg-open"
        return command, executable

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        subprocess.Popen(["xdg-open", path])
        return 1


class DisplayViewer(UnixViewer):
    """
    The ImageMagick ``display`` command.
    This viewer supports the ``title`` parameter.
    """

    def get_command_ex(
        self, file: str, title: str | None = None, **options: Any
    ) -> tuple[str, str]:
        command = executable = "display"
        if title:
            command += f" -title {quote(title)}"
        return command, executable

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        args = ["display"]
        title = options.get("title")
        if title:
            args += ["-title", title]
        args.append(path)

        subprocess.Popen(args)
        return 1


class GmDisplayViewer(UnixViewer):
    """The GraphicsMagick ``gm display`` command."""

    def get_command_ex(self, file: str, **options: Any) -> tuple[str, str]:
        executable = "gm"
        command = "gm display"
        return command, executable

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        subprocess.Popen(["gm", "display", path])
        return 1


class EogViewer(UnixViewer):
    """The GNOME Image Viewer ``eog`` command."""

    def get_command_ex(self, file: str, **options: Any) -> tuple[str, str]:
        executable = "eog"
        command = "eog -n"
        return command, executable

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        subprocess.Popen(["eog", "-n", path])
        return 1


class XVViewer(UnixViewer):
    """
    The X Viewer ``xv`` command.
    This viewer supports the ``title`` parameter.
    """

    def get_command_ex(
        self, file: str, title: str | None = None, **options: Any
    ) -> tuple[str, str]:
        # note: xv is pretty outdated.  most modern systems have
        # imagemagick's display command instead.
        command = executable = "xv"
        if title:
            command += f" -name {quote(title)}"
        return command, executable

    def show_file(self, path: str, **options: Any) -> int:
        """
        Display given file.
        """
        if not os.path.exists(path):
            raise FileNotFoundError
        args = ["xv"]
        title = options.get("title")
        if title:
            args += ["-name", title]
        args.append(path)

        subprocess.Popen(args)
        return 1


if sys.platform not in ("win32", "darwin"):  # unixoids
    if shutil.which("xdg-open"):
        register(XDGViewer)
    if shutil.which("display"):
        register(DisplayViewer)
    if shutil.which("gm"):
        register(GmDisplayViewer)
    if shutil.which("eog"):
        register(EogViewer)
    if shutil.which("xv"):
        register(XVViewer)


class IPythonViewer(Viewer):
    """The viewer for IPython frontends."""

    def show_image(self, image: Image.Image, **options: Any) -> int:
        ipython_display(image)
        return 1


try:
    from IPython.display import display as ipython_display
except ImportError:
    pass
else:
    register(IPythonViewer)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Syntax: python3 ImageShow.py imagefile [title]")
        sys.exit()

    with Image.open(sys.argv[1]) as im:
        print(show(im, *sys.argv[2:]))
