from __future__ import annotations

import typing
from collections import deque
from collections.abc import Collection, Iterator

from ._path import combine

if typing.TYPE_CHECKING:
    from typing import Callable

    from ._base import FS
    from ._info import Info


class BoundWalker:
    def __init__(self, fs: FS):
        self._fs = fs

    def _iter_walk(
        self, path: str, namespaces: Collection[str] | None = None
    ) -> Iterator[tuple[str, Info | None]]:
        """Walk files using a *breadth first* search."""
        queue = deque([path])
        push = queue.appendleft
        pop = queue.pop
        _scan = self._fs.scandir
        _combine = combine

        while queue:
            dir_path = pop()
            for info in _scan(dir_path, namespaces=namespaces):
                if info.is_dir:
                    yield dir_path, info
                    push(_combine(dir_path, info.name))
                else:
                    yield dir_path, info
        yield path, None

    def _filter(
        self,
        include: Callable[[str, Info], bool] = lambda path, info: True,
        path: str = "/",
        namespaces: Collection[str] | None = None,
    ) -> Iterator[str]:
        _combine = combine
        for path, info in self._iter_walk(path, namespaces):
            if info is not None and include(path, info):
                yield _combine(path, info.name)

    def files(self, path: str = "/") -> Iterator[str]:
        yield from self._filter(lambda _, info: info.is_file, path)

    def dirs(self, path: str = "/") -> Iterator[str]:
        yield from self._filter(lambda _, info: info.is_dir, path)
