import os
import platform

_WINDOWS_PLATFORM = platform.system() == "Windows"


def combine(path1: str, path2) -> str:
    if not path1:
        return path2
    return "{}/{}".format(path1.rstrip("/"), path2.lstrip("/"))


def split(path: str) -> tuple[str, str]:
    if "/" not in path:
        return ("", path)
    split = path.rsplit("/", 1)
    return (split[0] or "/", split[1])


def dirname(path: str) -> str:
    return split(path)[0]


def basename(path: str) -> str:
    return split(path)[1]


def forcedir(path: str) -> str:
    # Ensure the path ends with a trailing forward slash.
    if not path.endswith("/"):
        return path + "/"
    return path


def abspath(path: str) -> str:
    # FS objects have no concept of a *current directory*. This simply
    # ensures the path starts with a forward slash.
    if not path.startswith("/"):
        return "/" + path
    return path


def isbase(path1: str, path2: str) -> bool:
    # Check if `path1` is a base or prefix of `path2`.
    _path1 = forcedir(abspath(path1))
    _path2 = forcedir(abspath(path2))
    return _path2.startswith(_path1)


def frombase(path1: str, path2: str) -> str:
    # Get the final path of `path2` that isn't in `path1`.
    if not isbase(path1, path2):
        raise ValueError(f"path1 must be a prefix of path2: {path1!r} vs {path2!r}")
    return path2[len(path1) :]


def relpath(path: str) -> str:
    return path.lstrip("/")


def normpath(path: str) -> str:
    normalized = os.path.normpath(path)
    if _WINDOWS_PLATFORM:
        # os.path.normpath converts backslashes to forward slashes on Windows
        # but we want forward slashes, so we convert them back
        normalized = normalized.replace("\\", "/")
    return normalized
