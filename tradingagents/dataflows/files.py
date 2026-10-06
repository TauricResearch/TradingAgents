"""Files written whole, and held by one writer at a time, under concurrent writers."""

import errno
import logging
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


def replace_file(path, write: Callable[[str], None]) -> None:
    """Write ``path`` through a uniquely named temp file beside it, then move it into place.

    A reader sees the old file or the new one, never a partial write, and two
    writers of the same path (tool calls run concurrently) never share a temp file.
    ``write`` receives the temp path and creates the file, so it gets the usual
    permissions. The file is a cache: where another reader holds it open (Windows),
    the old one stays and the write is skipped.
    """
    path = Path(path)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write(str(temp))
        os.replace(temp, path)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        logger.warning("Kept the cached %s; it is in use (%s)", path.name, exc)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


@contextmanager
def locked(path, wait: bool = True) -> Iterator[bool]:
    """Hold ``path`` for one writer at a time, across threads and processes.

    For a file read, changed and written back: without the lock, two writers
    each read the same text and the second write drops the first's change. The
    lock is taken on a ``.lock`` file beside ``path``. Yields whether it is
    held: with ``wait=False`` a lock someone else holds is not waited for, and
    the block runs holding nothing.
    """
    with open(f"{path}.lock", "a+b") as handle:
        hold = _hold_windows if os.name == "nt" else _hold_posix
        with hold(handle, wait) as acquired:
            yield acquired


@contextmanager
def _hold_posix(handle, wait: bool = True) -> Iterator[bool]:
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _hold_windows(handle, wait: bool = True) -> Iterator[bool]:
    import msvcrt

    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
            break
        except OSError as exc:
            if not wait and exc.errno in (errno.EACCES, errno.EDEADLOCK):
                yield False   # another writer holds it
                return
            # LK_LOCK gives up after about ten seconds of another writer's hold;
            # any other failure is not a wait.
            if exc.errno != errno.EDEADLOCK:
                raise
    try:
        yield True
    finally:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
