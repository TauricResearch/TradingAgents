from __future__ import annotations

import errno
import platform
import shutil
import stat
import typing
from os import PathLike
from pathlib import Path

from ._base import FS
from ._errors import (
    CreateFailed,
    DirectoryExpected,
    DirectoryNotEmpty,
    FileExpected,
    IllegalDestination,
    ResourceError,
    ResourceNotFound,
)
from ._info import Info
from ._path import isbase

if typing.TYPE_CHECKING:
    from collections.abc import Collection
    from typing import IO, Any

    from ._subfs import SubFS


_WINDOWS_PLATFORM = platform.system() == "Windows"


class OSFS(FS):
    """Filesystem for a directory on the local disk.

    A thin layer on top of `pathlib.Path`.
    """

    def __init__(self, root: str | PathLike, create: bool = False):
        super().__init__()
        self._root = Path(root).resolve()
        if create:
            self._root.mkdir(parents=True, exist_ok=True)
        else:
            if not self._root.is_dir():
                raise CreateFailed(
                    f"unable to create OSFS: {root!r} does not exist or is not a directory"
                )

    def _abs(self, rel_path: str) -> Path:
        self.check()
        return (self._root / rel_path.strip("/")).resolve()

    def open(self, path: str, mode: str = "rb", **kwargs) -> IO[Any]:
        try:
            return self._abs(path).open(mode, **kwargs)
        except FileNotFoundError:
            raise ResourceNotFound(f"No such file or directory: {path!r}")

    def exists(self, path: str) -> bool:
        return self._abs(path).exists()

    def isdir(self, path: str) -> bool:
        return self._abs(path).is_dir()

    def isfile(self, path: str) -> bool:
        return self._abs(path).is_file()

    def listdir(self, path: str) -> list[str]:
        return [p.name for p in self._abs(path).iterdir()]

    def _mkdir(self, path: str, parents: bool = False, exist_ok: bool = False) -> SubFS:
        self._abs(path).mkdir(parents=parents, exist_ok=exist_ok)
        return self.opendir(path)

    def makedir(self, path: str, recreate: bool = False) -> SubFS:
        return self._mkdir(path, parents=False, exist_ok=recreate)

    def makedirs(self, path: str, recreate: bool = False) -> SubFS:
        return self._mkdir(path, parents=True, exist_ok=recreate)

    def getinfo(self, path: str, namespaces: Collection[str] | None = None) -> Info:
        path = self._abs(path)
        if not path.exists():
            raise ResourceNotFound(f"No such file or directory: {str(path)!r}")
        info = {
            "basic": {
                "name": path.name,
                "is_dir": path.is_dir(),
            }
        }
        namespaces = namespaces or ()
        if "details" in namespaces:
            stat_result = path.stat()
            details = info["details"] = {
                "accessed": stat_result.st_atime,
                "modified": stat_result.st_mtime,
                "size": stat_result.st_size,
                "type": stat.S_IFMT(stat_result.st_mode),
                "created": getattr(stat_result, "st_birthtime", None),
            }
            ctime_key = "created" if _WINDOWS_PLATFORM else "metadata_changed"
            details[ctime_key] = stat_result.st_ctime
        return Info(info)

    def remove(self, path: str):
        path = self._abs(path)
        try:
            path.unlink()
        except FileNotFoundError:
            raise ResourceNotFound(f"No such file or directory: {str(path)!r}")
        except OSError as e:
            if path.is_dir():
                raise FileExpected(f"path {str(path)!r} should be a file")
            else:
                raise ResourceError(f"unable to remove {str(path)!r}: {e}")

    def removedir(self, path: str):
        try:
            self._abs(path).rmdir()
        except NotADirectoryError:
            raise DirectoryExpected(f"path {path!r} should be a directory")
        except OSError as e:
            if e.errno == errno.ENOTEMPTY:
                raise DirectoryNotEmpty(f"Directory not empty: {path!r}")
            else:
                raise ResourceError(f"unable to remove {path!r}: {e}")

    def removetree(self, path: str):
        shutil.rmtree(self._abs(path))

    def movedir(self, src_dir: str, dst_dir: str, create: bool = False):
        if isbase(src_dir, dst_dir):
            raise IllegalDestination(f"cannot move {src_dir!r} to {dst_dir!r}")
        src_path = self._abs(src_dir)
        if not src_path.exists():
            raise ResourceNotFound(f"Source {src_dir!r} does not exist")
        elif not src_path.is_dir():
            raise DirectoryExpected(f"Source {src_dir!r} should be a directory")
        dst_path = self._abs(dst_dir)
        if not create and not dst_path.exists():
            raise ResourceNotFound(f"Destination {dst_dir!r} does not exist")
        if dst_path.is_file():
            raise DirectoryExpected(f"Destination {dst_dir!r} should be a directory")
        if create:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
        if dst_path.exists():
            if list(dst_path.iterdir()):
                raise DirectoryNotEmpty(f"Destination {dst_dir!r} is not empty")
            elif _WINDOWS_PLATFORM:
                # on Unix os.rename silently replaces an empty dst_dir whereas on
                # Windows it always raises FileExistsError, empty or not.
                dst_path.rmdir()
        src_path.rename(dst_path)

    def getsyspath(self, path: str) -> str:
        return str(self._abs(path))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self._root)!r})"

    def __str__(self) -> str:
        return f"<{self.__class__.__name__.lower()} '{self._root}'>"
