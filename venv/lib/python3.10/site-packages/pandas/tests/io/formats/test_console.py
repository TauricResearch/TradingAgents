import locale

import pytest

from pandas._config import detect_console_encoding


class MockEncoding:
    """
    Used to add a side effect when accessing the 'encoding' property. If the
    side effect is a str in nature, the value will be returned. Otherwise, the
    side effect should be an exception that will be raised.
    """

    def __init__(self, encoding) -> None:
        super().__init__()
        self.val = encoding

    @property
    def encoding(self):
        return self.raise_or_return(self.val)

    @staticmethod
    def raise_or_return(val):
        if isinstance(val, str):
            return val
        else:
            raise val


@pytest.mark.parametrize("empty,filled", [["stdin", "stdout"], ["stdout", "stdin"]])
def test_detect_console_encoding_from_stdout_stdin(monkeypatch, empty, filled):
    # Ensures that when sys.stdout.encoding or sys.stdin.encoding is used when
    # they have values filled.
    # GH 21552
    with monkeypatch.context() as context:
        context.setattr(f"sys.{empty}", MockEncoding(""))
        context.setattr(f"sys.{filled}", MockEncoding(filled))
        assert detect_console_encoding() == filled


@pytest.mark.parametrize("encoding", [AttributeError, OSError, "ascii"])
def test_detect_console_encoding_fallback_to_locale(monkeypatch, encoding):
    # GH 21552
    with monkeypatch.context() as context:
        context.setattr("locale.getpreferredencoding", lambda: "foo")
        context.setattr("sys.stdout", MockEncoding(encoding))
        assert detect_console_encoding() == "foo"


@pytest.mark.parametrize(
    "std,locale",
    [
        ["ascii", "ascii"],
        ["ascii", locale.Error],
        [AttributeError, "ascii"],
        [AttributeError, locale.Error],
        [OSError, "ascii"],
        [OSError, locale.Error],
    ],
)
def test_detect_console_encoding_fallback_to_default(monkeypatch, std, locale):
    # When both the stdout/stdin encoding and locale preferred encoding checks
    # fail (or return 'ascii', we should default to the sys default encoding.
    # GH 21552
    with monkeypatch.context() as context:
        context.setattr(
            "locale.getpreferredencoding", lambda: MockEncoding.raise_or_return(locale)
        )
        context.setattr("sys.stdout", MockEncoding(std))
        context.setattr("sys.getdefaultencoding", lambda: "sysDefaultEncoding")
        assert detect_console_encoding() == "sysDefaultEncoding"
