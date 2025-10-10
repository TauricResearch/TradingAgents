# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class Error(Exception):
    """Base Cu2Qu exception class for all other errors."""


class ApproxNotFoundError(Error):
    def __init__(self, curve):
        message = "no approximation found: %s" % curve
        super().__init__(message)
        self.curve = curve


class UnequalZipLengthsError(Error):
    pass


class IncompatibleGlyphsError(Error):
    def __init__(self, glyphs):
        assert len(glyphs) > 1
        self.glyphs = glyphs
        names = set(repr(g.name) for g in glyphs)
        if len(names) > 1:
            self.combined_name = "{%s}" % ", ".join(sorted(names))
        else:
            self.combined_name = names.pop()

    def __repr__(self):
        return "<%s %s>" % (type(self).__name__, self.combined_name)


class IncompatibleSegmentNumberError(IncompatibleGlyphsError):
    def __str__(self):
        return "Glyphs named %s have different number of segments" % (
            self.combined_name
        )


class IncompatibleSegmentTypesError(IncompatibleGlyphsError):
    def __init__(self, glyphs, segments):
        IncompatibleGlyphsError.__init__(self, glyphs)
        self.segments = segments

    def __str__(self):
        lines = []
        ndigits = len(str(max(self.segments)))
        for i, tags in sorted(self.segments.items()):
            lines.append(
                "%s: (%s)" % (str(i).rjust(ndigits), ", ".join(repr(t) for t in tags))
            )
        return "Glyphs named %s have incompatible segment types:\n  %s" % (
            self.combined_name,
            "\n  ".join(lines),
        )


class IncompatibleFontsError(Error):
    def __init__(self, glyph_errors):
        self.glyph_errors = glyph_errors

    def __str__(self):
        return "fonts contains incompatible glyphs: %s" % (
            ", ".join(repr(g) for g in sorted(self.glyph_errors.keys()))
        )
