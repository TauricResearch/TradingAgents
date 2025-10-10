from typing import Callable
from fontTools.pens.basePen import BasePen


def pointToString(pt, ntos=str):
    return " ".join(ntos(i) for i in pt)


class SVGPathPen(BasePen):
    """Pen to draw SVG path d commands.

    Args:
        glyphSet: a dictionary of drawable glyph objects keyed by name
            used to resolve component references in composite glyphs.
        ntos: a callable that takes a number and returns a string, to
            customize how numbers are formatted (default: str).

    :Example:
        .. code-block::

            >>> pen = SVGPathPen(None)
            >>> pen.moveTo((0, 0))
            >>> pen.lineTo((1, 1))
            >>> pen.curveTo((2, 2), (3, 3), (4, 4))
            >>> pen.closePath()
            >>> pen.getCommands()
            'M0 0 1 1C2 2 3 3 4 4Z'

    Note:
        Fonts have a coordinate system where Y grows up, whereas in SVG,
        Y grows down.  As such, rendering path data from this pen in
        SVG typically results in upside-down glyphs.  You can fix this
        by wrapping the data from this pen in an SVG group element with
        transform, or wrap this pen in a transform pen.  For example:
        .. code-block:: python

            spen = svgPathPen.SVGPathPen(glyphset)
            pen= TransformPen(spen , (1, 0, 0, -1, 0, 0))
            glyphset[glyphname].draw(pen)
            print(tpen.getCommands())
    """

    def __init__(self, glyphSet, ntos: Callable[[float], str] = str):
        BasePen.__init__(self, glyphSet)
        self._commands = []
        self._lastCommand = None
        self._lastX = None
        self._lastY = None
        self._ntos = ntos

    def _handleAnchor(self):
        """
        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((0, 0))
        >>> pen.moveTo((10, 10))
        >>> pen._commands
        ['M10 10']
        """
        if self._lastCommand == "M":
            self._commands.pop(-1)

    def _moveTo(self, pt):
        """
        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((0, 0))
        >>> pen._commands
        ['M0 0']

        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((10, 0))
        >>> pen._commands
        ['M10 0']

        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((0, 10))
        >>> pen._commands
        ['M0 10']
        """
        self._handleAnchor()
        t = "M%s" % (pointToString(pt, self._ntos))
        self._commands.append(t)
        self._lastCommand = "M"
        self._lastX, self._lastY = pt

    def _lineTo(self, pt):
        """
        # duplicate point
        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((10, 10))
        >>> pen.lineTo((10, 10))
        >>> pen._commands
        ['M10 10']

        # vertical line
        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((10, 10))
        >>> pen.lineTo((10, 0))
        >>> pen._commands
        ['M10 10', 'V0']

        # horizontal line
        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((10, 10))
        >>> pen.lineTo((0, 10))
        >>> pen._commands
        ['M10 10', 'H0']

        # basic
        >>> pen = SVGPathPen(None)
        >>> pen.lineTo((70, 80))
        >>> pen._commands
        ['L70 80']

        # basic following a moveto
        >>> pen = SVGPathPen(None)
        >>> pen.moveTo((0, 0))
        >>> pen.lineTo((10, 10))
        >>> pen._commands
        ['M0 0', ' 10 10']
        """
        x, y = pt
        # duplicate point
        if x == self._lastX and y == self._lastY:
            return
        # vertical line
        elif x == self._lastX:
            cmd = "V"
            pts = self._ntos(y)
        # horizontal line
        elif y == self._lastY:
            cmd = "H"
            pts = self._ntos(x)
        # previous was a moveto
        elif self._lastCommand == "M":
            cmd = None
            pts = " " + pointToString(pt, self._ntos)
        # basic
        else:
            cmd = "L"
            pts = pointToString(pt, self._ntos)
        # write the string
        t = ""
        if cmd:
            t += cmd
            self._lastCommand = cmd
        t += pts
        self._commands.append(t)
        # store for future reference
        self._lastX, self._lastY = pt

    def _curveToOne(self, pt1, pt2, pt3):
        """
        >>> pen = SVGPathPen(None)
        >>> pen.curveTo((10, 20), (30, 40), (50, 60))
        >>> pen._commands
        ['C10 20 30 40 50 60']
        """
        t = "C"
        t += pointToString(pt1, self._ntos) + " "
        t += pointToString(pt2, self._ntos) + " "
        t += pointToString(pt3, self._ntos)
        self._commands.append(t)
        self._lastCommand = "C"
        self._lastX, self._lastY = pt3

    def _qCurveToOne(self, pt1, pt2):
        """
        >>> pen = SVGPathPen(None)
        >>> pen.qCurveTo((10, 20), (30, 40))
        >>> pen._commands
        ['Q10 20 30 40']
        >>> from fontTools.misc.roundTools import otRound
        >>> pen = SVGPathPen(None, ntos=lambda v: str(otRound(v)))
        >>> pen.qCurveTo((3, 3), (7, 5), (11, 4))
        >>> pen._commands
        ['Q3 3 5 4', 'Q7 5 11 4']
        """
        assert pt2 is not None
        t = "Q"
        t += pointToString(pt1, self._ntos) + " "
        t += pointToString(pt2, self._ntos)
        self._commands.append(t)
        self._lastCommand = "Q"
        self._lastX, self._lastY = pt2

    def _closePath(self):
        """
        >>> pen = SVGPathPen(None)
        >>> pen.closePath()
        >>> pen._commands
        ['Z']
        """
        self._commands.append("Z")
        self._lastCommand = "Z"
        self._lastX = self._lastY = None

    def _endPath(self):
        """
        >>> pen = SVGPathPen(None)
        >>> pen.endPath()
        >>> pen._commands
        []
        """
        self._lastCommand = None
        self._lastX = self._lastY = None

    def getCommands(self):
        return "".join(self._commands)


def main(args=None):
    """Generate per-character SVG from font and text"""

    if args is None:
        import sys

        args = sys.argv[1:]

    from fontTools.ttLib import TTFont
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools pens.svgPathPen", description="Generate SVG from text"
    )
    parser.add_argument("font", metavar="font.ttf", help="Font file.")
    parser.add_argument("text", metavar="text", nargs="?", help="Text string.")
    parser.add_argument(
        "-y",
        metavar="<number>",
        help="Face index into a collection to open. Zero based.",
    )
    parser.add_argument(
        "--glyphs",
        metavar="whitespace-separated list of glyph names",
        type=str,
        help="Glyphs to show. Exclusive with text option",
    )
    parser.add_argument(
        "--variations",
        metavar="AXIS=LOC",
        default="",
        help="List of space separated locations. A location consist in "
        "the name of a variation axis, followed by '=' and a number. E.g.: "
        "wght=700 wdth=80. The default is the location of the base master.",
    )

    options = parser.parse_args(args)

    fontNumber = int(options.y) if options.y is not None else 0

    font = TTFont(options.font, fontNumber=fontNumber)
    text = options.text
    glyphs = options.glyphs

    location = {}
    for tag_v in options.variations.split():
        fields = tag_v.split("=")
        tag = fields[0].strip()
        v = float(fields[1])
        location[tag] = v

    hhea = font["hhea"]
    ascent, descent = hhea.ascent, hhea.descent

    glyphset = font.getGlyphSet(location=location)
    cmap = font["cmap"].getBestCmap()

    if glyphs is not None and text is not None:
        raise ValueError("Options --glyphs and --text are exclusive")

    if glyphs is None:
        glyphs = " ".join(cmap[ord(u)] for u in text)

    glyphs = glyphs.split()

    s = ""
    width = 0
    for g in glyphs:
        glyph = glyphset[g]

        pen = SVGPathPen(glyphset)
        glyph.draw(pen)
        commands = pen.getCommands()

        s += '<g transform="translate(%d %d) scale(1 -1)"><path d="%s"/></g>\n' % (
            width,
            ascent,
            commands,
        )

        width += glyph.width

    print('<?xml version="1.0" encoding="UTF-8"?>')
    print(
        '<svg width="%d" height="%d" xmlns="http://www.w3.org/2000/svg">'
        % (width, ascent - descent)
    )
    print(s, end="")
    print("</svg>")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        import doctest

        sys.exit(doctest.testmod().failed)

    sys.exit(main())
