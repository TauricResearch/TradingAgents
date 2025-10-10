from __future__ import annotations

import typing
from datetime import datetime, timezone

from ._errors import MissingInfoNamespace

if typing.TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any


def epoch_to_datetime(t: int | None) -> datetime | None:
    """Convert epoch time to a UTC datetime."""
    if t is None:
        return None
    return datetime.fromtimestamp(t, tz=timezone.utc)


class Info:
    __slots__ = ["raw", "namespaces"]

    def __init__(self, raw_info: Mapping[str, Any]):
        self.raw = raw_info
        self.namespaces = frozenset(raw_info.keys())

    def get(self, namespace: str, key: str, default: Any | None = None) -> Any | None:
        try:
            return self.raw[namespace].get(key, default)
        except KeyError:
            raise MissingInfoNamespace(f"Namespace {namespace!r} does not exist")

    @property
    def name(self) -> str:
        return self.get("basic", "name")

    @property
    def is_dir(self) -> bool:
        return self.get("basic", "is_dir")

    @property
    def is_file(self) -> bool:
        return not self.is_dir

    @property
    def accessed(self) -> datetime | None:
        return epoch_to_datetime(self.get("details", "accessed"))

    @property
    def modified(self) -> datetime | None:
        return epoch_to_datetime(self.get("details", "modified"))

    @property
    def size(self) -> int | None:
        return self.get("details", "size")

    @property
    def type(self) -> int | None:
        return self.get("details", "type")

    @property
    def created(self) -> datetime | None:
        return epoch_to_datetime(self.get("details", "created"))

    @property
    def metadata_changed(self) -> datetime | None:
        return epoch_to_datetime(self.get("details", "metadata_changed"))

    def __str__(self) -> str:
        if self.is_dir:
            return "<dir '{}'>".format(self.name)
        else:
            return "<file '{}'>".format(self.name)

    __repr__ = __str__
