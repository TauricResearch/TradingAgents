"""Cross-platform single-process guard for an observation-only source directory.

The OS automatically releases advisory locks when the owning process exits,
including a crash. A persistent lock FILE is never treated as proof that an
observer is running. Never unlink the lockfile: a different inode would let a
second process bypass the active lock.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def observer_instance_lock(home: Path) -> Iterator[Path]:
    """Exclusive observer lock; does not read any portfolio or credential."""
    home.mkdir(parents=True, exist_ok=True)
    lock_path = home / ".observer.lock"
    if lock_path.is_symlink():
        raise ValueError("Observer lock path cannot be a symlink")
    with lock_path.open("a+b") as stream:
        # Windows byte-range locking needs an actual byte to lock. Leave the
        # file permanently present; its existence alone has no active meaning.
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
            os.fsync(stream.fileno())
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "Another Koral Observer owns this directory; stop it before launching a second"
            ) from exc
        try:
            yield lock_path
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
