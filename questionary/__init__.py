from __future__ import annotations

from typing import Any, Iterable, List, Optional, Tuple


class Style:
    def __init__(self, styles: Iterable[Tuple[str, str]]):
        self.styles = list(styles)


class Choice:
    def __init__(self, display: str, value: Optional[Any] = None):
        self.display = display
        self.value = value if value is not None else display


class _DummyPrompt:
    def __init__(self, return_value: Optional[str] = ""):
        self.return_value = return_value or ""

    def ask(self) -> str:
        return self.return_value


def text(*args: Any, **kwargs: Any) -> _DummyPrompt:
    return _DummyPrompt(kwargs.get("default", ""))


def checkbox(*args: Any, **kwargs: Any) -> _DummyPrompt:
    return _DummyPrompt()


def select(*args: Any, **kwargs: Any) -> _DummyPrompt:
    return _DummyPrompt()
