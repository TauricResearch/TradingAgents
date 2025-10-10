from __future__ import annotations

import io
import os
import shutil
import stat
import typing
import zipfile
from datetime import datetime

from ._base import FS
from ._errors import FileExpected, ResourceNotFound, ResourceReadOnly
from ._info import Info
from ._path import dirname, forcedir, normpath, relpath
from ._tempfs import TempFS

if typing.TYPE_CHECKING:
    from collections.abc import Collection
    from typing import IO, Any

    from ._subfs import SubFS


class ZipFS(FS):
    """Read and write zip files."""

    def __new__(
        cls, file: str | os.PathLike, write: bool = False, encoding: str = "utf-8"
    ):
        if write:
            return WriteZipFS(file, encoding)
        else:
            return ReadZipFS(file, encoding)

    if typing.TYPE_CHECKING:

        def __init__(
            self, file: str | os.PathLike, write: bool = False, encoding: str = "utf-8"
        ):
            pass


class ReadZipFS(FS):
    """A readable zip file."""

    def __init__(self, file: str | os.PathLike, encoding: str = "utf-8"):
        super().__init__()
        self._file = os.fspath(file)
        self.encoding = encoding  # unused
        self._zip = zipfile.ZipFile(file, "r")
        self._directory_fs = None

    def __repr__(self) -> str:
        return f"ReadZipFS({self._file!r})"

    def __str__(self) -> str:
        return f"<zipfs '{self._file}'>"

    def _path_to_zip_name(self, path: str) -> str:
        """Convert a path to a zip file name."""
        path = relpath(normpath(path))
        if self._directory.isdir(path):
            path = forcedir(path)
        return path

    @property
    def _directory(self) -> TempFS:
        if self._directory_fs is None:
            self._directory_fs = _fs = TempFS()
            for zip_name in self._zip.namelist():
                resource_name = zip_name
                if resource_name.endswith("/"):
                    _fs.makedirs(resource_name, recreate=True)
                else:
                    _fs.makedirs(dirname(resource_name), recreate=True)
                    _fs.create(resource_name)
        return self._directory_fs

    def close(self):
        super(ReadZipFS, self).close()
        self._zip.close()
        if self._directory_fs is not None:
            self._directory_fs.close()

    def getinfo(self, path: str, namespaces: Collection[str] | None = None) -> Info:
        namespaces = namespaces or ()
        raw_info = {}

        if path == "/":
            raw_info["basic"] = {"name": "", "is_dir": True}
            if "details" in namespaces:
                raw_info["details"] = {"type": stat.S_IFDIR}
        else:
            basic_info = self._directory.getinfo(path)
            raw_info["basic"] = {"name": basic_info.name, "is_dir": basic_info.is_dir}

            if "details" in namespaces:
                zip_name = self._path_to_zip_name(path)
                try:
                    zip_info = self._zip.getinfo(zip_name)
                except KeyError:
                    pass
                else:
                    if "details" in namespaces:
                        raw_info["details"] = {
                            "size": zip_info.file_size,
                            "type": int(
                                stat.S_IFDIR if basic_info.is_dir else stat.S_IFREG
                            ),
                            "modified": datetime(*zip_info.date_time).timestamp(),
                        }

        return Info(raw_info)

    def exists(self, path: str) -> bool:
        self.check()
        return self._directory.exists(path)

    def isdir(self, path: str) -> bool:
        self.check()
        return self._directory.isdir(path)

    def isfile(self, path: str) -> bool:
        self.check()
        return self._directory.isfile(path)

    def listdir(self, path: str) -> str:
        self.check()
        return self._directory.listdir(path)

    def makedir(self, path: str, recreate: bool = False) -> SubFS:
        self.check()
        raise ResourceReadOnly(path)

    def makedirs(self, path: str, recreate: bool = False) -> SubFS:
        self.check()
        raise ResourceReadOnly(path)

    def remove(self, path: str):
        self.check()
        raise ResourceReadOnly(path)

    def removedir(self, path: str):
        self.check()
        raise ResourceReadOnly(path)

    def removetree(self, path: str):
        self.check()
        raise ResourceReadOnly(path)

    def movedir(self, src: str, dst: str, create: bool = False):
        self.check()
        raise ResourceReadOnly(src)

    def readbytes(self, path: str) -> bytes:
        self.check()
        if not self._directory.isfile(path):
            raise ResourceNotFound(path)
        zip_name = self._path_to_zip_name(path)
        zip_bytes = self._zip.read(zip_name)
        return zip_bytes

    def open(self, path: str, mode: str = "rb", **kwargs) -> IO[Any]:
        self.check()
        if self._directory.isdir(path):
            raise FileExpected(f"{path!r} is a directory")

        zip_mode = mode[0]
        if zip_mode == "r" and not self._directory.exists(path):
            raise ResourceNotFound(f"No such file or directory: {path!r}")

        if any(m in mode for m in "wax+"):
            raise ResourceReadOnly(path)

        zip_name = self._path_to_zip_name(path)
        stream = self._zip.open(zip_name, zip_mode)
        if "b" in mode:
            if kwargs:
                raise ValueError("encoding args invalid for binary operation")
            return stream
        # Text mode
        return io.TextIOWrapper(stream, **kwargs)


class WriteZipFS(TempFS):
    """A writable zip file."""

    def __init__(self, file: str | os.PathLike, encoding: str = "utf-8"):
        super().__init__()
        self._file = os.fspath(file)
        self.encoding = encoding  # unused

    def __repr__(self) -> str:
        return f"WriteZipFS({self._file!r})"

    def __str__(self) -> str:
        return f"<zipfs-write '{self._file}'>"

    def close(self):
        base_name = os.path.splitext(self._file)[0]
        shutil.make_archive(base_name, format="zip", root_dir=self._temp_dir)
        if self._file != base_name + ".zip":
            shutil.move(base_name + ".zip", self._file)
        super().close()
