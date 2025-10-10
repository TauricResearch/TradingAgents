from __future__ import annotations

import typing
from pathlib import PurePosixPath

from ._base import FS
from ._errors import DirectoryExpected, ResourceNotFound

if typing.TYPE_CHECKING:
    from collections.abc import Collection
    from typing import IO, Any

    from ._info import Info


class SubFS(FS):
    """Maps a sub-directory of another filesystem."""

    def __init__(self, parent: FS, sub_path: str):
        super().__init__()
        self._parent = parent
        self._prefix = PurePosixPath(sub_path).as_posix().rstrip("/")
        if not parent.exists(self._prefix):
            raise ResourceNotFound(f"No such file or directory: {sub_path!r}")
        elif not parent.isdir(self._prefix):
            raise DirectoryExpected(f"{sub_path!r} is not a directory")

    def delegate_fs(self):
        return self._parent

    def _full(self, rel: str) -> str:
        self.check()
        return f"{self._prefix}/{PurePosixPath(rel).as_posix()}".lstrip("/")

    def open(self, path: str, mode: str = "rb", **kwargs) -> IO[Any]:
        return self._parent.open(self._full(path), mode, **kwargs)

    def exists(self, path: str) -> bool:
        return self._parent.exists(self._full(path))

    def isdir(self, path: str) -> bool:
        return self._parent.isdir(self._full(path))

    def isfile(self, path: str) -> bool:
        return self._parent.isfile(self._full(path))

    def listdir(self, path: str) -> list[str]:
        return self._parent.listdir(self._full(path))

    def makedir(self, path: str, recreate: bool = False):
        return self._parent.makedir(self._full(path), recreate=recreate)

    def makedirs(self, path: str, recreate: bool = False):
        return self._parent.makedirs(self._full(path), recreate=recreate)

    def getinfo(self, path: str, namespaces: Collection[str] | None = None) -> Info:
        return self._parent.getinfo(self._full(path), namespaces=namespaces)

    def remove(self, path: str):
        return self._parent.remove(self._full(path))

    def removedir(self, path: str):
        return self._parent.removedir(self._full(path))

    def removetree(self, path: str):
        return self._parent.removetree(self._full(path))

    def movedir(self, src: str, dst: str, create: bool = False):
        self._parent.movedir(self._full(src), self._full(dst), create=create)

    def getsyspath(self, path: str) -> str:
        return self._parent.getsyspath(self._full(path))

    def readbytes(self, path: str) -> bytes:
        return self._parent.readbytes(self._full(path))

    def writebytes(self, path: str, data: bytes):
        self._parent.writebytes(self._full(path), data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._parent!r}, {self._prefix!r})"

    def __str__(self) -> str:
        return f"{self._parent}/{self._prefix}"


class ClosingSubFS(SubFS):
    """Like SubFS, but auto-closes the parent filesystem when closed."""

    def close(self):
        super().close()
        self._parent.close()
