from __future__ import annotations

import typing
from pathlib import PurePosixPath

from ._errors import DirectoryNotEmpty

if typing.TYPE_CHECKING:
    from typing import IO

    from ._base import FS


def remove_empty(fs: FS, path: str):
    """Remove all empty parents."""
    path = PurePosixPath(path)
    root = PurePosixPath("/")
    try:
        while path != root:
            fs.removedir(path.as_posix())
            path = path.parent
    except DirectoryNotEmpty:
        pass


def copy_file_data(src_file: IO, dst_file: IO, chunk_size: int | None = None):
    """Copy data from one file object to another."""
    _chunk_size = 1024 * 1024 if chunk_size is None else chunk_size
    read = src_file.read
    write = dst_file.write
    # in iter(callable, sentilel), callable is called until it returns the sentinel;
    # this allows to copy `chunk_size` bytes at a time.
    for chunk in iter(lambda: read(_chunk_size) or None, None):
        write(chunk)
