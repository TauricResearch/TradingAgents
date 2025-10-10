from fontTools.misc.roundTools import otRound
from fontTools import ttLib
from fontTools.misc.textTools import safeEval
from . import DefaultTable
import sys
import struct
import array
import logging


log = logging.getLogger(__name__)


class table__h_m_t_x(DefaultTable.DefaultTable):
    """Horizontal Metrics table

    The ``hmtx`` table contains per-glyph metrics for the glyphs in a
    ``glyf``, ``CFF ``, or ``CFF2`` table, as needed for horizontal text
    layout.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/hmtx
    """

    headerTag = "hhea"
    advanceName = "width"
    sideBearingName = "lsb"
    numberOfMetricsName = "numberOfHMetrics"
    longMetricFormat = "Hh"

    def decompile(self, data, ttFont):
        numGlyphs = ttFont["maxp"].numGlyphs
        headerTable = ttFont.get(self.headerTag)
        if headerTable is not None:
            numberOfMetrics = int(getattr(headerTable, self.numberOfMetricsName))
        else:
            numberOfMetrics = numGlyphs
        if numberOfMetrics > numGlyphs:
            log.warning(
                "The %s.%s exceeds the maxp.numGlyphs"
                % (self.headerTag, self.numberOfMetricsName)
            )
            numberOfMetrics = numGlyphs
        numberOfSideBearings = numGlyphs - numberOfMetrics
        tableSize = 4 * numberOfMetrics + 2 * numberOfSideBearings
        if len(data) < tableSize:
            raise ttLib.TTLibError(
                f"not enough '{self.tableTag}' table data: "
                f"expected {tableSize} bytes, got {len(data)}"
            )
        # Note: advanceWidth is unsigned, but some font editors might
        # read/write as signed. We can't be sure whether it was a mistake
        # or not, so we read as unsigned but also issue a warning...
        metricsFmt = ">" + self.longMetricFormat * numberOfMetrics
        metrics = struct.unpack(metricsFmt, data[: 4 * numberOfMetrics])
        data = data[4 * numberOfMetrics :]
        sideBearings = array.array("h", data[: 2 * numberOfSideBearings])
        data = data[2 * numberOfSideBearings :]

        if sys.byteorder != "big":
            sideBearings.byteswap()
        if data:
            log.warning("too much '%s' table data" % self.tableTag)
        self.metrics = {}
        glyphOrder = ttFont.getGlyphOrder()
        for i in range(numberOfMetrics):
            glyphName = glyphOrder[i]
            advanceWidth, lsb = metrics[i * 2 : i * 2 + 2]
            if advanceWidth > 32767:
                log.warning(
                    "Glyph %r has a huge advance %s (%d); is it intentional or "
                    "an (invalid) negative value?",
                    glyphName,
                    self.advanceName,
                    advanceWidth,
                )
            self.metrics[glyphName] = (advanceWidth, lsb)
        lastAdvance = metrics[-2]
        for i in range(numberOfSideBearings):
            glyphName = glyphOrder[i + numberOfMetrics]
            self.metrics[glyphName] = (lastAdvance, sideBearings[i])

    def compile(self, ttFont):
        metrics = []
        hasNegativeAdvances = False
        for glyphName in ttFont.getGlyphOrder():
            advanceWidth, sideBearing = self.metrics[glyphName]
            if advanceWidth < 0:
                log.error(
                    "Glyph %r has negative advance %s" % (glyphName, self.advanceName)
                )
                hasNegativeAdvances = True
            metrics.append([advanceWidth, sideBearing])

        headerTable = ttFont.get(self.headerTag)
        if headerTable is not None:
            lastAdvance = metrics[-1][0]
            lastIndex = len(metrics)
            while metrics[lastIndex - 2][0] == lastAdvance:
                lastIndex -= 1
                if lastIndex <= 1:
                    # all advances are equal
                    lastIndex = 1
                    break
            additionalMetrics = metrics[lastIndex:]
            additionalMetrics = [otRound(sb) for _, sb in additionalMetrics]
            metrics = metrics[:lastIndex]
            numberOfMetrics = len(metrics)
            setattr(headerTable, self.numberOfMetricsName, numberOfMetrics)
        else:
            # no hhea/vhea, can't store numberOfMetrics; assume == numGlyphs
            numberOfMetrics = ttFont["maxp"].numGlyphs
            additionalMetrics = []

        allMetrics = []
        for advance, sb in metrics:
            allMetrics.extend([otRound(advance), otRound(sb)])
        metricsFmt = ">" + self.longMetricFormat * numberOfMetrics
        try:
            data = struct.pack(metricsFmt, *allMetrics)
        except struct.error as e:
            if "out of range" in str(e) and hasNegativeAdvances:
                raise ttLib.TTLibError(
                    "'%s' table can't contain negative advance %ss"
                    % (self.tableTag, self.advanceName)
                )
            else:
                raise
        additionalMetrics = array.array("h", additionalMetrics)
        if sys.byteorder != "big":
            additionalMetrics.byteswap()
        data = data + additionalMetrics.tobytes()
        return data

    def toXML(self, writer, ttFont):
        names = sorted(self.metrics.keys())
        for glyphName in names:
            advance, sb = self.metrics[glyphName]
            writer.simpletag(
                "mtx",
                [
                    ("name", glyphName),
                    (self.advanceName, advance),
                    (self.sideBearingName, sb),
                ],
            )
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "metrics"):
            self.metrics = {}
        if name == "mtx":
            self.metrics[attrs["name"]] = (
                safeEval(attrs[self.advanceName]),
                safeEval(attrs[self.sideBearingName]),
            )

    def __delitem__(self, glyphName):
        del self.metrics[glyphName]

    def __getitem__(self, glyphName):
        return self.metrics[glyphName]

    def __setitem__(self, glyphName, advance_sb_pair):
        self.metrics[glyphName] = tuple(advance_sb_pair)
