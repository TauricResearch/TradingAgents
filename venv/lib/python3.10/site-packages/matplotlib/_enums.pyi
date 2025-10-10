from typing import cast
from enum import Enum


class JoinStyle(str, Enum):
    miter = "miter"
    round = "round"
    bevel = "bevel"
    @staticmethod
    def demo() -> None: ...


class CapStyle(str, Enum):
    butt = "butt"
    projecting = "projecting"
    round = "round"

    @staticmethod
    def demo() -> None: ...
