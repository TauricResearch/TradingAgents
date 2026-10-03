"""Writing a path the way it should be read on screen.

Everything the UI shows lives under the user's home by default, so the absolute
form is mostly a long prefix that pushes the part that identifies the file off
the end of the line — and puts the local directory layout on screen for anyone
looking at it. The tilde form is shorter, is what a shell prints, and pastes
back into one unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path


def tilde(path: str | Path | None) -> str | None:
    """An absolute path written relative to home, when it is under home."""
    if path is None:
        return None
    text = str(path)
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):      # no home on this system
        return text
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        return "~" + text[len(home):]
    return text
