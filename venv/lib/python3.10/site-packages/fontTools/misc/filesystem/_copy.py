from __future__ import annotations

import typing

from ._errors import IllegalDestination
from ._path import combine, frombase, isbase
from ._tools import copy_file_data

if typing.TYPE_CHECKING:
    from ._base import FS


def copy_file(src_fs: FS, src_path: str, dst_fs: FS, dst_path: str):
    if src_fs is dst_fs and src_path == dst_path:
        raise IllegalDestination(f"cannot copy {src_path!r} to itself")

    with src_fs.open(src_path, "rb") as src_file:
        with dst_fs.open(dst_path, "wb") as dst_file:
            copy_file_data(src_file, dst_file)


def copy_structure(
    src_fs: FS,
    dst_fs: FS,
    src_root: str = "/",
    dst_root: str = "/",
):
    if src_fs is dst_fs and isbase(src_root, dst_root):
        raise IllegalDestination(f"cannot copy {src_fs!r} to itself")

    dst_fs.makedirs(dst_root, recreate=True)
    for dir_path in src_fs.walk.dirs(src_root):
        dst_fs.makedir(combine(dst_root, frombase(src_root, dir_path)), recreate=True)


def copy_dir(src_fs: FS, src_path: str, dst_fs: FS, dst_path: str):
    copy_structure(src_fs, dst_fs, src_path, dst_path)

    for file_path in src_fs.walk.files(src_path):
        copy_path = combine(dst_path, frombase(src_path, file_path))
        copy_file(src_fs, file_path, dst_fs, copy_path)


def copy_fs(src_fs: FS, dst_fs: FS):
    copy_dir(src_fs, "/", dst_fs, "/")
