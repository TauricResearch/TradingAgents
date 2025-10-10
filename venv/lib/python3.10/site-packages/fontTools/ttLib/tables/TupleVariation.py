from fontTools.misc.fixedTools import (
    fixedToFloat as fi2fl,
    floatToFixed as fl2fi,
    floatToFixedToStr as fl2str,
    strToFixedToFloat as str2fl,
    otRound,
)
from fontTools.misc.textTools import safeEval
import array
from collections import Counter, defaultdict
import io
import logging
import struct
import sys


# https://www.microsoft.com/typography/otspec/otvarcommonformats.htm

EMBEDDED_PEAK_TUPLE = 0x8000
INTERMEDIATE_REGION = 0x4000
PRIVATE_POINT_NUMBERS = 0x2000

DELTAS_ARE_ZERO = 0x80
DELTAS_ARE_WORDS = 0x40
DELTAS_ARE_LONGS = 0xC0
DELTAS_SIZE_MASK = 0xC0
DELTA_RUN_COUNT_MASK = 0x3F

POINTS_ARE_WORDS = 0x80
POINT_RUN_COUNT_MASK = 0x7F

TUPLES_SHARE_POINT_NUMBERS = 0x8000
TUPLE_COUNT_MASK = 0x0FFF
TUPLE_INDEX_MASK = 0x0FFF

log = logging.getLogger(__name__)


class TupleVariation(object):
    def __init__(self, axes, coordinates):
        self.axes = axes.copy()
        self.coordinates = list(coordinates)

    def __repr__(self):
        axes = ",".join(
            sorted(["%s=%s" % (name, value) for (name, value) in self.axes.items()])
        )
        return "<TupleVariation %s %s>" % (axes, self.coordinates)

    def __eq__(self, other):
        return self.coordinates == other.coordinates and self.axes == other.axes

    def getUsedPoints(self):
        # Empty set means "all points used".
        if None not in self.coordinates:
            return frozenset()
        used = frozenset([i for i, p in enumerate(self.coordinates) if p is not None])
        # Return None if no points used.
        return used if used else None

    def hasImpact(self):
        """Returns True if this TupleVariation has any visible impact.

        If the result is False, the TupleVariation can be omitted from the font
        without making any visible difference.
        """
        return any(c is not None for c in self.coordinates)

    def toXML(self, writer, axisTags):
        writer.begintag("tuple")
        writer.newline()
        for axis in axisTags:
            value = self.axes.get(axis)
            if value is not None:
                minValue, value, maxValue = value
                defaultMinValue = min(value, 0.0)  # -0.3 --> -0.3; 0.7 --> 0.0
                defaultMaxValue = max(value, 0.0)  # -0.3 -->  0.0; 0.7 --> 0.7
                if minValue == defaultMinValue and maxValue == defaultMaxValue:
                    writer.simpletag("coord", axis=axis, value=fl2str(value, 14))
                else:
                    attrs = [
                        ("axis", axis),
                        ("min", fl2str(minValue, 14)),
                        ("value", fl2str(value, 14)),
                        ("max", fl2str(maxValue, 14)),
                    ]
                    writer.simpletag("coord", attrs)
                writer.newline()
        wrote_any_deltas = False
        for i, delta in enumerate(self.coordinates):
            if type(delta) == tuple and len(delta) == 2:
                writer.simpletag("delta", pt=i, x=delta[0], y=delta[1])
                writer.newline()
                wrote_any_deltas = True
            elif type(delta) == int:
                writer.simpletag("delta", cvt=i, value=delta)
                writer.newline()
                wrote_any_deltas = True
            elif delta is not None:
                log.error("bad delta format")
                writer.comment("bad delta #%d" % i)
                writer.newline()
                wrote_any_deltas = True
        if not wrote_any_deltas:
            writer.comment("no deltas")
            writer.newline()
        writer.endtag("tuple")
        writer.newline()

    def fromXML(self, name, attrs, _content):
        if name == "coord":
            axis = attrs["axis"]
            value = str2fl(attrs["value"], 14)
            defaultMinValue = min(value, 0.0)  # -0.3 --> -0.3; 0.7 --> 0.0
            defaultMaxValue = max(value, 0.0)  # -0.3 -->  0.0; 0.7 --> 0.7
            minValue = str2fl(attrs.get("min", defaultMinValue), 14)
            maxValue = str2fl(attrs.get("max", defaultMaxValue), 14)
            self.axes[axis] = (minValue, value, maxValue)
        elif name == "delta":
            if "pt" in attrs:
                point = safeEval(attrs["pt"])
                x = safeEval(attrs["x"])
                y = safeEval(attrs["y"])
                self.coordinates[point] = (x, y)
            elif "cvt" in attrs:
                cvt = safeEval(attrs["cvt"])
                value = safeEval(attrs["value"])
                self.coordinates[cvt] = value
            else:
                log.warning("bad delta format: %s" % ", ".join(sorted(attrs.keys())))

    def compile(
        self, axisTags, sharedCoordIndices={}, pointData=None, *, optimizeSize=True
    ):
        assert set(self.axes.keys()) <= set(axisTags), (
            "Unknown axis tag found.",
            self.axes.keys(),
            axisTags,
        )

        tupleData = []
        auxData = []

        if pointData is None:
            usedPoints = self.getUsedPoints()
            if usedPoints is None:  # Nothing to encode
                return b"", b""
            pointData = self.compilePoints(usedPoints)

        coord = self.compileCoord(axisTags)
        flags = sharedCoordIndices.get(coord)
        if flags is None:
            flags = EMBEDDED_PEAK_TUPLE
            tupleData.append(coord)

        intermediateCoord = self.compileIntermediateCoord(axisTags)
        if intermediateCoord is not None:
            flags |= INTERMEDIATE_REGION
            tupleData.append(intermediateCoord)

        # pointData of b'' implies "use shared points".
        if pointData:
            flags |= PRIVATE_POINT_NUMBERS
            auxData.append(pointData)

        auxData.append(self.compileDeltas(optimizeSize=optimizeSize))
        auxData = b"".join(auxData)

        tupleData.insert(0, struct.pack(">HH", len(auxData), flags))
        return b"".join(tupleData), auxData

    def compileCoord(self, axisTags):
        result = []
        axes = self.axes
        for axis in axisTags:
            triple = axes.get(axis)
            if triple is None:
                result.append(b"\0\0")
            else:
                result.append(struct.pack(">h", fl2fi(triple[1], 14)))
        return b"".join(result)

    def compileIntermediateCoord(self, axisTags):
        needed = False
        for axis in axisTags:
            minValue, value, maxValue = self.axes.get(axis, (0.0, 0.0, 0.0))
            defaultMinValue = min(value, 0.0)  # -0.3 --> -0.3; 0.7 --> 0.0
            defaultMaxValue = max(value, 0.0)  # -0.3 -->  0.0; 0.7 --> 0.7
            if (minValue != defaultMinValue) or (maxValue != defaultMaxValue):
                needed = True
                break
        if not needed:
            return None
        minCoords = []
        maxCoords = []
        for axis in axisTags:
            minValue, value, maxValue = self.axes.get(axis, (0.0, 0.0, 0.0))
            minCoords.append(struct.pack(">h", fl2fi(minValue, 14)))
            maxCoords.append(struct.pack(">h", fl2fi(maxValue, 14)))
        return b"".join(minCoords + maxCoords)

    @staticmethod
    def decompileCoord_(axisTags, data, offset):
        coord = {}
        pos = offset
        for axis in axisTags:
            coord[axis] = fi2fl(struct.unpack(">h", data[pos : pos + 2])[0], 14)
            pos += 2
        return coord, pos

    @staticmethod
    def compilePoints(points):
        # If the set consists of all points in the glyph, it gets encoded with
        # a special encoding: a single zero byte.
        #
        # To use this optimization, points passed in must be empty set.
        # The following two lines are not strictly necessary as the main code
        # below would emit the same. But this is most common and faster.
        if not points:
            return b"\0"

        # In the 'gvar' table, the packing of point numbers is a little surprising.
        # It consists of multiple runs, each being a delta-encoded list of integers.
        # For example, the point set {17, 18, 19, 20, 21, 22, 23} gets encoded as
        # [6, 17, 1, 1, 1, 1, 1, 1]. The first value (6) is the run length minus 1.
        # There are two types of runs, with values being either 8 or 16 bit unsigned
        # integers.
        points = list(points)
        points.sort()
        numPoints = len(points)

        result = bytearray()
        # The binary representation starts with the total number of points in the set,
        # encoded into one or two bytes depending on the value.
        if numPoints < 0x80:
            result.append(numPoints)
        else:
            result.append((numPoints >> 8) | 0x80)
            result.append(numPoints & 0xFF)

        MAX_RUN_LENGTH = 127
        pos = 0
        lastValue = 0
        while pos < numPoints:
            runLength = 0

            headerPos = len(result)
            result.append(0)

            useByteEncoding = None
            while pos < numPoints and runLength <= MAX_RUN_LENGTH:
                curValue = points[pos]
                delta = curValue - lastValue
                if useByteEncoding is None:
                    useByteEncoding = 0 <= delta <= 0xFF
                if useByteEncoding and (delta > 0xFF or delta < 0):
                    # we need to start a new run (which will not use byte encoding)
                    break
                # TODO This never switches back to a byte-encoding from a short-encoding.
                # That's suboptimal.
                if useByteEncoding:
                    result.append(delta)
                else:
                    result.append(delta >> 8)
                    result.append(delta & 0xFF)
                lastValue = curValue
                pos += 1
                runLength += 1
            if useByteEncoding:
                result[headerPos] = runLength - 1
            else:
                result[headerPos] = (runLength - 1) | POINTS_ARE_WORDS

        return result

    @staticmethod
    def decompilePoints_(numPoints, data, offset, tableTag):
        """(numPoints, data, offset, tableTag) --> ([point1, point2, ...], newOffset)"""
        assert tableTag in ("cvar", "gvar")
        pos = offset
        numPointsInData = data[pos]
        pos += 1
        if (numPointsInData & POINTS_ARE_WORDS) != 0:
            numPointsInData = (numPointsInData & POINT_RUN_COUNT_MASK) << 8 | data[pos]
            pos += 1
        if numPointsInData == 0:
            return (range(numPoints), pos)

        result = []
        while len(result) < numPointsInData:
            runHeader = data[pos]
            pos += 1
            numPointsInRun = (runHeader & POINT_RUN_COUNT_MASK) + 1
            point = 0
            if (runHeader & POINTS_ARE_WORDS) != 0:
                points = array.array("H")
                pointsSize = numPointsInRun * 2
            else:
                points = array.array("B")
                pointsSize = numPointsInRun
            points.frombytes(data[pos : pos + pointsSize])
            if sys.byteorder != "big":
                points.byteswap()

            assert len(points) == numPointsInRun
            pos += pointsSize

            result.extend(points)

        # Convert relative to absolute
        absolute = []
        current = 0
        for delta in result:
            current += delta
            absolute.append(current)
        result = absolute
        del absolute

        badPoints = {str(p) for p in result if p < 0 or p >= numPoints}
        if badPoints:
            log.warning(
                "point %s out of range in '%s' table"
                % (",".join(sorted(badPoints)), tableTag)
            )
        return (result, pos)

    def compileDeltas(self, optimizeSize=True):
        deltaX = []
        deltaY = []
        if self.getCoordWidth() == 2:
            for c in self.coordinates:
                if c is None:
                    continue
                deltaX.append(c[0])
                deltaY.append(c[1])
        else:
            for c in self.coordinates:
                if c is None:
                    continue
                deltaX.append(c)
        bytearr = bytearray()
        self.compileDeltaValues_(deltaX, bytearr, optimizeSize=optimizeSize)
        self.compileDeltaValues_(deltaY, bytearr, optimizeSize=optimizeSize)
        return bytearr

    @staticmethod
    def compileDeltaValues_(deltas, bytearr=None, *, optimizeSize=True):
        """[value1, value2, value3, ...] --> bytearray

        Emits a sequence of runs. Each run starts with a
        byte-sized header whose 6 least significant bits
        (header & 0x3F) indicate how many values are encoded
        in this run. The stored length is the actual length
        minus one; run lengths are thus in the range [1..64].
        If the header byte has its most significant bit (0x80)
        set, all values in this run are zero, and no data
        follows. Otherwise, the header byte is followed by
        ((header & 0x3F) + 1) signed values.  If (header &
        0x40) is clear, the delta values are stored as signed
        bytes; if (header & 0x40) is set, the delta values are
        signed 16-bit integers.
        """  # Explaining the format because the 'gvar' spec is hard to understand.
        if bytearr is None:
            bytearr = bytearray()

        pos = 0
        numDeltas = len(deltas)

        if optimizeSize:
            while pos < numDeltas:
                value = deltas[pos]
                if value == 0:
                    pos = TupleVariation.encodeDeltaRunAsZeroes_(deltas, pos, bytearr)
                elif -128 <= value <= 127:
                    pos = TupleVariation.encodeDeltaRunAsBytes_(deltas, pos, bytearr)
                elif -32768 <= value <= 32767:
                    pos = TupleVariation.encodeDeltaRunAsWords_(deltas, pos, bytearr)
                else:
                    pos = TupleVariation.encodeDeltaRunAsLongs_(deltas, pos, bytearr)
        else:
            minVal, maxVal = min(deltas), max(deltas)
            if minVal == 0 == maxVal:
                pos = TupleVariation.encodeDeltaRunAsZeroes_(deltas, pos, bytearr)
            elif -128 <= minVal <= maxVal <= 127:
                pos = TupleVariation.encodeDeltaRunAsBytes_(
                    deltas, pos, bytearr, optimizeSize=False
                )
            elif -32768 <= minVal <= maxVal <= 32767:
                pos = TupleVariation.encodeDeltaRunAsWords_(
                    deltas, pos, bytearr, optimizeSize=False
                )
            else:
                pos = TupleVariation.encodeDeltaRunAsLongs_(
                    deltas, pos, bytearr, optimizeSize=False
                )

        assert pos == numDeltas, (pos, numDeltas)

        return bytearr

    @staticmethod
    def encodeDeltaRunAsZeroes_(deltas, offset, bytearr):
        pos = offset
        numDeltas = len(deltas)
        while pos < numDeltas and deltas[pos] == 0:
            pos += 1
        runLength = pos - offset
        while runLength >= 64:
            bytearr.append(DELTAS_ARE_ZERO | 63)
            runLength -= 64
        if runLength:
            bytearr.append(DELTAS_ARE_ZERO | (runLength - 1))
        return pos

    @staticmethod
    def encodeDeltaRunAsBytes_(deltas, offset, bytearr, optimizeSize=True):
        pos = offset
        numDeltas = len(deltas)
        while pos < numDeltas:
            value = deltas[pos]
            if not (-128 <= value <= 127):
                break
            # Within a byte-encoded run of deltas, a single zero
            # is best stored literally as 0x00 value. However,
            # if are two or more zeroes in a sequence, it is
            # better to start a new run. For example, the sequence
            # of deltas [15, 15, 0, 15, 15] becomes 6 bytes
            # (04 0F 0F 00 0F 0F) when storing the zero value
            # literally, but 7 bytes (01 0F 0F 80 01 0F 0F)
            # when starting a new run.
            if (
                optimizeSize
                and value == 0
                and pos + 1 < numDeltas
                and deltas[pos + 1] == 0
            ):
                break
            pos += 1
        runLength = pos - offset
        while runLength >= 64:
            bytearr.append(63)
            bytearr.extend(array.array("b", deltas[offset : offset + 64]))
            offset += 64
            runLength -= 64
        if runLength:
            bytearr.append(runLength - 1)
            bytearr.extend(array.array("b", deltas[offset:pos]))
        return pos

    @staticmethod
    def encodeDeltaRunAsWords_(deltas, offset, bytearr, optimizeSize=True):
        pos = offset
        numDeltas = len(deltas)
        while pos < numDeltas:
            value = deltas[pos]

            # Within a word-encoded run of deltas, it is easiest
            # to start a new run (with a different encoding)
            # whenever we encounter a zero value. For example,
            # the sequence [0x6666, 0, 0x7777] needs 7 bytes when
            # storing the zero literally (42 66 66 00 00 77 77),
            # and equally 7 bytes when starting a new run
            # (40 66 66 80 40 77 77).
            if optimizeSize and value == 0:
                break

            # Within a word-encoded run of deltas, a single value
            # in the range (-128..127) should be encoded literally
            # because it is more compact. For example, the sequence
            # [0x6666, 2, 0x7777] becomes 7 bytes when storing
            # the value literally (42 66 66 00 02 77 77), but 8 bytes
            # when starting a new run (40 66 66 00 02 40 77 77).
            if (
                optimizeSize
                and (-128 <= value <= 127)
                and pos + 1 < numDeltas
                and (-128 <= deltas[pos + 1] <= 127)
            ):
                break

            if not (-32768 <= value <= 32767):
                break

            pos += 1
        runLength = pos - offset
        while runLength >= 64:
            bytearr.append(DELTAS_ARE_WORDS | 63)
            a = array.array("h", deltas[offset : offset + 64])
            if sys.byteorder != "big":
                a.byteswap()
            bytearr.extend(a)
            offset += 64
            runLength -= 64
        if runLength:
            bytearr.append(DELTAS_ARE_WORDS | (runLength - 1))
            a = array.array("h", deltas[offset:pos])
            if sys.byteorder != "big":
                a.byteswap()
            bytearr.extend(a)
        return pos

    @staticmethod
    def encodeDeltaRunAsLongs_(deltas, offset, bytearr, optimizeSize=True):
        pos = offset
        numDeltas = len(deltas)
        while pos < numDeltas:
            value = deltas[pos]
            if optimizeSize and -32768 <= value <= 32767:
                break
            pos += 1
        runLength = pos - offset
        while runLength >= 64:
            bytearr.append(DELTAS_ARE_LONGS | 63)
            a = array.array("i", deltas[offset : offset + 64])
            if sys.byteorder != "big":
                a.byteswap()
            bytearr.extend(a)
            offset += 64
            runLength -= 64
        if runLength:
            bytearr.append(DELTAS_ARE_LONGS | (runLength - 1))
            a = array.array("i", deltas[offset:pos])
            if sys.byteorder != "big":
                a.byteswap()
            bytearr.extend(a)
        return pos

    @staticmethod
    def decompileDeltas_(numDeltas, data, offset=0):
        """(numDeltas, data, offset) --> ([delta, delta, ...], newOffset)"""
        result = []
        pos = offset
        while len(result) < numDeltas if numDeltas is not None else pos < len(data):
            runHeader = data[pos]
            pos += 1
            numDeltasInRun = (runHeader & DELTA_RUN_COUNT_MASK) + 1
            if (runHeader & DELTAS_SIZE_MASK) == DELTAS_ARE_ZERO:
                result.extend([0] * numDeltasInRun)
            else:
                if (runHeader & DELTAS_SIZE_MASK) == DELTAS_ARE_LONGS:
                    deltas = array.array("i")
                    deltasSize = numDeltasInRun * 4
                elif (runHeader & DELTAS_SIZE_MASK) == DELTAS_ARE_WORDS:
                    deltas = array.array("h")
                    deltasSize = numDeltasInRun * 2
                else:
                    deltas = array.array("b")
                    deltasSize = numDeltasInRun
                deltas.frombytes(data[pos : pos + deltasSize])
                if sys.byteorder != "big":
                    deltas.byteswap()
                assert len(deltas) == numDeltasInRun, (len(deltas), numDeltasInRun)
                pos += deltasSize
                result.extend(deltas)
        assert numDeltas is None or len(result) == numDeltas
        return (result, pos)

    @staticmethod
    def getTupleSize_(flags, axisCount):
        size = 4
        if (flags & EMBEDDED_PEAK_TUPLE) != 0:
            size += axisCount * 2
        if (flags & INTERMEDIATE_REGION) != 0:
            size += axisCount * 4
        return size

    def getCoordWidth(self):
        """Return 2 if coordinates are (x, y) as in gvar, 1 if single values
        as in cvar, or 0 if empty.
        """
        firstDelta = next((c for c in self.coordinates if c is not None), None)
        if firstDelta is None:
            return 0  # empty or has no impact
        if type(firstDelta) in (int, float):
            return 1
        if type(firstDelta) is tuple and len(firstDelta) == 2:
            return 2
        raise TypeError(
            "invalid type of delta; expected (int or float) number, or "
            "Tuple[number, number]: %r" % firstDelta
        )

    def scaleDeltas(self, scalar):
        if scalar == 1.0:
            return  # no change
        coordWidth = self.getCoordWidth()
        self.coordinates = [
            (
                None
                if d is None
                else d * scalar if coordWidth == 1 else (d[0] * scalar, d[1] * scalar)
            )
            for d in self.coordinates
        ]

    def roundDeltas(self):
        coordWidth = self.getCoordWidth()
        self.coordinates = [
            (
                None
                if d is None
                else otRound(d) if coordWidth == 1 else (otRound(d[0]), otRound(d[1]))
            )
            for d in self.coordinates
        ]

    def calcInferredDeltas(self, origCoords, endPts):
        from fontTools.varLib.iup import iup_delta

        if self.getCoordWidth() == 1:
            raise TypeError("Only 'gvar' TupleVariation can have inferred deltas")
        if None in self.coordinates:
            if len(self.coordinates) != len(origCoords):
                raise ValueError(
                    "Expected len(origCoords) == %d; found %d"
                    % (len(self.coordinates), len(origCoords))
                )
            self.coordinates = iup_delta(self.coordinates, origCoords, endPts)

    def optimize(self, origCoords, endPts, tolerance=0.5, isComposite=False):
        from fontTools.varLib.iup import iup_delta_optimize

        if None in self.coordinates:
            return  # already optimized

        deltaOpt = iup_delta_optimize(
            self.coordinates, origCoords, endPts, tolerance=tolerance
        )
        if None in deltaOpt:
            if isComposite and all(d is None for d in deltaOpt):
                # Fix for macOS composites
                # https://github.com/fonttools/fonttools/issues/1381
                deltaOpt = [(0, 0)] + [None] * (len(deltaOpt) - 1)
            # Use "optimized" version only if smaller...
            varOpt = TupleVariation(self.axes, deltaOpt)

            # Shouldn't matter that this is different from fvar...?
            axisTags = sorted(self.axes.keys())
            tupleData, auxData = self.compile(axisTags)
            unoptimizedLength = len(tupleData) + len(auxData)
            tupleData, auxData = varOpt.compile(axisTags)
            optimizedLength = len(tupleData) + len(auxData)

            if optimizedLength < unoptimizedLength:
                self.coordinates = varOpt.coordinates

    def __imul__(self, scalar):
        self.scaleDeltas(scalar)
        return self

    def __iadd__(self, other):
        if not isinstance(other, TupleVariation):
            return NotImplemented
        deltas1 = self.coordinates
        length = len(deltas1)
        deltas2 = other.coordinates
        if len(deltas2) != length:
            raise ValueError("cannot sum TupleVariation deltas with different lengths")
        # 'None' values have different meanings in gvar vs cvar TupleVariations:
        # within the gvar, when deltas are not provided explicitly for some points,
        # they need to be inferred; whereas for the 'cvar' table, if deltas are not
        # provided for some CVT values, then no adjustments are made (i.e. None == 0).
        # Thus, we cannot sum deltas for gvar TupleVariations if they contain
        # inferred inferred deltas (the latter need to be computed first using
        # 'calcInferredDeltas' method), but we can treat 'None' values in cvar
        # deltas as if they are zeros.
        if self.getCoordWidth() == 2:
            for i, d2 in zip(range(length), deltas2):
                d1 = deltas1[i]
                try:
                    deltas1[i] = (d1[0] + d2[0], d1[1] + d2[1])
                except TypeError:
                    raise ValueError("cannot sum gvar deltas with inferred points")
        else:
            for i, d2 in zip(range(length), deltas2):
                d1 = deltas1[i]
                if d1 is not None and d2 is not None:
                    deltas1[i] = d1 + d2
                elif d1 is None and d2 is not None:
                    deltas1[i] = d2
                # elif d2 is None do nothing
        return self


def decompileSharedTuples(axisTags, sharedTupleCount, data, offset):
    result = []
    for _ in range(sharedTupleCount):
        t, offset = TupleVariation.decompileCoord_(axisTags, data, offset)
        result.append(t)
    return result


def compileSharedTuples(
    axisTags, variations, MAX_NUM_SHARED_COORDS=TUPLE_INDEX_MASK + 1
):
    coordCount = Counter()
    for var in variations:
        coord = var.compileCoord(axisTags)
        coordCount[coord] += 1
    # In python < 3.7, most_common() ordering is non-deterministic
    # so apply a sort to make sure the ordering is consistent.
    sharedCoords = sorted(
        coordCount.most_common(MAX_NUM_SHARED_COORDS),
        key=lambda item: (-item[1], item[0]),
    )
    return [c[0] for c in sharedCoords if c[1] > 1]


def compileTupleVariationStore(
    variations,
    pointCount,
    axisTags,
    sharedTupleIndices,
    useSharedPoints=True,
    *,
    optimizeSize=True,
):
    # pointCount is actually unused. Keeping for API compat.
    del pointCount
    newVariations = []
    pointDatas = []
    # Compile all points and figure out sharing if desired
    sharedPoints = None

    # Collect, count, and compile point-sets for all variation sets
    pointSetCount = defaultdict(int)
    for v in variations:
        points = v.getUsedPoints()
        if points is None:  # Empty variations
            continue
        pointSetCount[points] += 1
        newVariations.append(v)
        pointDatas.append(points)
    variations = newVariations
    del newVariations

    if not variations:
        return (0, b"", b"")

    n = len(variations[0].coordinates)
    assert all(
        len(v.coordinates) == n for v in variations
    ), "Variation sets have different sizes"

    compiledPoints = {
        pointSet: TupleVariation.compilePoints(pointSet) for pointSet in pointSetCount
    }

    tupleVariationCount = len(variations)
    tuples = []
    data = []

    if useSharedPoints:
        # Find point-set which saves most bytes.
        def key(pn):
            pointSet = pn[0]
            count = pn[1]
            return len(compiledPoints[pointSet]) * (count - 1)

        sharedPoints = max(pointSetCount.items(), key=key)[0]

        data.append(compiledPoints[sharedPoints])
        tupleVariationCount |= TUPLES_SHARE_POINT_NUMBERS

    # b'' implies "use shared points"
    pointDatas = [
        compiledPoints[points] if points != sharedPoints else b""
        for points in pointDatas
    ]

    for v, p in zip(variations, pointDatas):
        thisTuple, thisData = v.compile(
            axisTags, sharedTupleIndices, pointData=p, optimizeSize=optimizeSize
        )

        tuples.append(thisTuple)
        data.append(thisData)

    tuples = b"".join(tuples)
    data = b"".join(data)
    return tupleVariationCount, tuples, data


def decompileTupleVariationStore(
    tableTag,
    axisTags,
    tupleVariationCount,
    pointCount,
    sharedTuples,
    data,
    pos,
    dataPos,
):
    numAxes = len(axisTags)
    result = []
    if (tupleVariationCount & TUPLES_SHARE_POINT_NUMBERS) != 0:
        sharedPoints, dataPos = TupleVariation.decompilePoints_(
            pointCount, data, dataPos, tableTag
        )
    else:
        sharedPoints = []
    for _ in range(tupleVariationCount & TUPLE_COUNT_MASK):
        dataSize, flags = struct.unpack(">HH", data[pos : pos + 4])
        tupleSize = TupleVariation.getTupleSize_(flags, numAxes)
        tupleData = data[pos : pos + tupleSize]
        pointDeltaData = data[dataPos : dataPos + dataSize]
        result.append(
            decompileTupleVariation_(
                pointCount,
                sharedTuples,
                sharedPoints,
                tableTag,
                axisTags,
                tupleData,
                pointDeltaData,
            )
        )
        pos += tupleSize
        dataPos += dataSize
    return result


def decompileTupleVariation_(
    pointCount, sharedTuples, sharedPoints, tableTag, axisTags, data, tupleData
):
    assert tableTag in ("cvar", "gvar"), tableTag
    flags = struct.unpack(">H", data[2:4])[0]
    pos = 4
    if (flags & EMBEDDED_PEAK_TUPLE) == 0:
        peak = sharedTuples[flags & TUPLE_INDEX_MASK]
    else:
        peak, pos = TupleVariation.decompileCoord_(axisTags, data, pos)
    if (flags & INTERMEDIATE_REGION) != 0:
        start, pos = TupleVariation.decompileCoord_(axisTags, data, pos)
        end, pos = TupleVariation.decompileCoord_(axisTags, data, pos)
    else:
        start, end = inferRegion_(peak)
    axes = {}
    for axis in axisTags:
        region = start[axis], peak[axis], end[axis]
        if region != (0.0, 0.0, 0.0):
            axes[axis] = region
    pos = 0
    if (flags & PRIVATE_POINT_NUMBERS) != 0:
        points, pos = TupleVariation.decompilePoints_(
            pointCount, tupleData, pos, tableTag
        )
    else:
        points = sharedPoints

    deltas = [None] * pointCount

    if tableTag == "cvar":
        deltas_cvt, pos = TupleVariation.decompileDeltas_(len(points), tupleData, pos)
        for p, delta in zip(points, deltas_cvt):
            if 0 <= p < pointCount:
                deltas[p] = delta

    elif tableTag == "gvar":
        deltas_x, pos = TupleVariation.decompileDeltas_(len(points), tupleData, pos)
        deltas_y, pos = TupleVariation.decompileDeltas_(len(points), tupleData, pos)
        for p, x, y in zip(points, deltas_x, deltas_y):
            if 0 <= p < pointCount:
                deltas[p] = (x, y)

    return TupleVariation(axes, deltas)


def inferRegion_(peak):
    """Infer start and end for a (non-intermediate) region

    This helper function computes the applicability region for
    variation tuples whose INTERMEDIATE_REGION flag is not set in the
    TupleVariationHeader structure.  Variation tuples apply only to
    certain regions of the variation space; outside that region, the
    tuple has no effect.  To make the binary encoding more compact,
    TupleVariationHeaders can omit the intermediateStartTuple and
    intermediateEndTuple fields.
    """
    start, end = {}, {}
    for axis, value in peak.items():
        start[axis] = min(value, 0.0)  # -0.3 --> -0.3; 0.7 --> 0.0
        end[axis] = max(value, 0.0)  # -0.3 -->  0.0; 0.7 --> 0.7
    return (start, end)
