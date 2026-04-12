"""Lightweight pandas stub for tests."""

from typing import Any, Iterable, Optional


class DataFrame(list):
    def __init__(self, *args: Iterable[Any], **kwargs: Any):
        super().__init__(*args)

    def to_dict(self, *args, **kwargs) -> dict:
        return {}


class Series:
    def __init__(self, data: Optional[Iterable[Any]] = None):
        self.data = list(data) if data is not None else []


def read_csv(*args: Any, **kwargs: Any) -> DataFrame:
    return DataFrame()


def concat(*args: Any, **kwargs: Any) -> DataFrame:
    return DataFrame()
