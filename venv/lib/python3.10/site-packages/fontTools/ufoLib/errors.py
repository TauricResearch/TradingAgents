from __future__ import annotations


class UFOLibError(Exception):
    pass


class UnsupportedUFOFormat(UFOLibError):
    pass


class GlifLibError(UFOLibError):
    """An error raised by glifLib.

    This class is a loose backport of PEP 678, adding a :attr:`.note`
    attribute that can hold additional context for errors encountered.

    It will be maintained until only Python 3.11-and-later are supported.
    """

    def _add_note(self, note: str) -> None:
        # Loose backport of PEP 678 until we only support Python 3.11+, used for
        # adding additional context to errors.
        # TODO: Replace with https://docs.python.org/3.11/library/exceptions.html#BaseException.add_note
        (message, *rest) = self.args
        self.args = ((message + "\n" + note), *rest)


class UnsupportedGLIFFormat(GlifLibError):
    pass
