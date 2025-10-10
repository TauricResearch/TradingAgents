import textwrap


class VarLibError(Exception):
    """Base exception for the varLib module."""


class VarLibValidationError(VarLibError):
    """Raised when input data is invalid from varLib's point of view."""


class VarLibMergeError(VarLibError):
    """Raised when input data cannot be merged into a variable font."""

    def __init__(self, merger=None, **kwargs):
        self.merger = merger
        if not kwargs:
            kwargs = {}
        if "stack" in kwargs:
            self.stack = kwargs["stack"]
            del kwargs["stack"]
        else:
            self.stack = []
        self.cause = kwargs

    @property
    def reason(self):
        return self.__doc__

    def _master_name(self, ix):
        if self.merger is not None:
            ttf = self.merger.ttfs[ix]
            if "name" in ttf and ttf["name"].getBestFullName():
                return ttf["name"].getBestFullName()
            elif hasattr(ttf.reader, "file") and hasattr(ttf.reader.file, "name"):
                return ttf.reader.file.name
        return f"master number {ix}"

    @property
    def offender(self):
        if "expected" in self.cause and "got" in self.cause:
            index = [x == self.cause["expected"] for x in self.cause["got"]].index(
                False
            )
            master_name = self._master_name(index)
            if "location" in self.cause:
                master_name = f"{master_name} ({self.cause['location']})"
            return index, master_name
        return None, None

    @property
    def details(self):
        if "expected" in self.cause and "got" in self.cause:
            offender_index, offender = self.offender
            got = self.cause["got"][offender_index]
            return f"Expected to see {self.stack[0]}=={self.cause['expected']!r}, instead saw {got!r}\n"
        return ""

    def __str__(self):
        offender_index, offender = self.offender
        location = ""
        if offender:
            location = f"\n\nThe problem is likely to be in {offender}:\n"
        context = "".join(reversed(self.stack))
        basic = textwrap.fill(
            f"Couldn't merge the fonts, because {self.reason}. "
            f"This happened while performing the following operation: {context}",
            width=78,
        )
        return "\n\n" + basic + location + self.details


class ShouldBeConstant(VarLibMergeError):
    """some values were different, but should have been the same"""

    @property
    def details(self):
        basic_message = super().details

        if self.stack[0] != ".FeatureCount" or self.merger is None:
            return basic_message

        assert self.stack[0] == ".FeatureCount"
        offender_index, _ = self.offender
        bad_ttf = self.merger.ttfs[offender_index]
        good_ttf = next(
            ttf
            for ttf in self.merger.ttfs
            if self.stack[-1] in ttf
            and ttf[self.stack[-1]].table.FeatureList.FeatureCount
            == self.cause["expected"]
        )

        good_features = [
            x.FeatureTag
            for x in good_ttf[self.stack[-1]].table.FeatureList.FeatureRecord
        ]
        bad_features = [
            x.FeatureTag
            for x in bad_ttf[self.stack[-1]].table.FeatureList.FeatureRecord
        ]
        return basic_message + (
            "\nIncompatible features between masters.\n"
            f"Expected: {', '.join(good_features)}.\n"
            f"Got: {', '.join(bad_features)}.\n"
        )


class FoundANone(VarLibMergeError):
    """one of the values in a list was empty when it shouldn't have been"""

    @property
    def offender(self):
        index = [x is None for x in self.cause["got"]].index(True)
        return index, self._master_name(index)

    @property
    def details(self):
        cause, stack = self.cause, self.stack
        return f"{stack[0]}=={cause['got']}\n"


class NotANone(VarLibMergeError):
    """one of the values in a list was not empty when it should have been"""

    @property
    def offender(self):
        index = [x is not None for x in self.cause["got"]].index(True)
        return index, self._master_name(index)

    @property
    def details(self):
        cause, stack = self.cause, self.stack
        return f"{stack[0]}=={cause['got']}\n"


class MismatchedTypes(VarLibMergeError):
    """data had inconsistent types"""


class LengthsDiffer(VarLibMergeError):
    """a list of objects had inconsistent lengths"""


class KeysDiffer(VarLibMergeError):
    """a list of objects had different keys"""


class InconsistentGlyphOrder(VarLibMergeError):
    """the glyph order was inconsistent between masters"""


class InconsistentExtensions(VarLibMergeError):
    """the masters use extension lookups in inconsistent ways"""


class UnsupportedFormat(VarLibMergeError):
    """an OpenType subtable (%s) had a format I didn't expect"""

    def __init__(self, merger=None, **kwargs):
        super().__init__(merger, **kwargs)
        if not self.stack:
            self.stack = [".Format"]

    @property
    def reason(self):
        s = self.__doc__ % self.cause["subtable"]
        if "value" in self.cause:
            s += f" ({self.cause['value']!r})"
        return s


class InconsistentFormats(UnsupportedFormat):
    """an OpenType subtable (%s) had inconsistent formats between masters"""


class VarLibCFFMergeError(VarLibError):
    pass


class VarLibCFFDictMergeError(VarLibCFFMergeError):
    """Raised when a CFF PrivateDict cannot be merged."""

    def __init__(self, key, value, values):
        error_msg = (
            f"For the Private Dict key '{key}', the default font value list:"
            f"\n\t{value}\nhad a different number of values than a region font:"
        )
        for region_value in values:
            error_msg += f"\n\t{region_value}"
        self.args = (error_msg,)


class VarLibCFFPointTypeMergeError(VarLibCFFMergeError):
    """Raised when a CFF glyph cannot be merged because of point type differences."""

    def __init__(self, point_type, pt_index, m_index, default_type, glyph_name):
        error_msg = (
            f"Glyph '{glyph_name}': '{point_type}' at point index {pt_index} in "
            f"master index {m_index} differs from the default font point type "
            f"'{default_type}'"
        )
        self.args = (error_msg,)


class VarLibCFFHintTypeMergeError(VarLibCFFMergeError):
    """Raised when a CFF glyph cannot be merged because of hint type differences."""

    def __init__(self, hint_type, cmd_index, m_index, default_type, glyph_name):
        error_msg = (
            f"Glyph '{glyph_name}': '{hint_type}' at index {cmd_index} in "
            f"master index {m_index} differs from the default font hint type "
            f"'{default_type}'"
        )
        self.args = (error_msg,)


class VariationModelError(VarLibError):
    """Raised when a variation model is faulty."""
