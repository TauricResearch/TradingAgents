from fontTools import ttLib
from fontTools.ttLib.tables import otTables as ot

# VariationStore


def buildVarRegionAxis(axisSupport):
    self = ot.VarRegionAxis()
    self.StartCoord, self.PeakCoord, self.EndCoord = [float(v) for v in axisSupport]
    return self


def buildSparseVarRegionAxis(axisIndex, axisSupport):
    self = ot.SparseVarRegionAxis()
    self.AxisIndex = axisIndex
    self.StartCoord, self.PeakCoord, self.EndCoord = [float(v) for v in axisSupport]
    return self


def buildVarRegion(support, axisTags):
    assert all(tag in axisTags for tag in support.keys()), (
        "Unknown axis tag found.",
        support,
        axisTags,
    )
    self = ot.VarRegion()
    self.VarRegionAxis = []
    for tag in axisTags:
        self.VarRegionAxis.append(buildVarRegionAxis(support.get(tag, (0, 0, 0))))
    return self


def buildSparseVarRegion(support, axisTags):
    assert all(tag in axisTags for tag in support.keys()), (
        "Unknown axis tag found.",
        support,
        axisTags,
    )
    self = ot.SparseVarRegion()
    self.SparseVarRegionAxis = []
    for i, tag in enumerate(axisTags):
        if tag not in support:
            continue
        self.SparseVarRegionAxis.append(
            buildSparseVarRegionAxis(i, support.get(tag, (0, 0, 0)))
        )
    self.SparseRegionCount = len(self.SparseVarRegionAxis)
    return self


def buildVarRegionList(supports, axisTags):
    self = ot.VarRegionList()
    self.RegionAxisCount = len(axisTags)
    self.Region = []
    for support in supports:
        self.Region.append(buildVarRegion(support, axisTags))
    self.RegionCount = len(self.Region)
    return self


def buildSparseVarRegionList(supports, axisTags):
    self = ot.SparseVarRegionList()
    self.RegionAxisCount = len(axisTags)
    self.Region = []
    for support in supports:
        self.Region.append(buildSparseVarRegion(support, axisTags))
    self.RegionCount = len(self.Region)
    return self


def _reorderItem(lst, mapping):
    return [lst[i] for i in mapping]


def VarData_calculateNumShorts(self, optimize=False):
    count = self.VarRegionCount
    items = self.Item
    bit_lengths = [0] * count
    for item in items:
        # The "+ (i < -1)" magic is to handle two's-compliment.
        # That is, we want to get back 7 for -128, whereas
        # bit_length() returns 8. Similarly for -65536.
        # The reason "i < -1" is used instead of "i < 0" is that
        # the latter would make it return 0 for "-1" instead of 1.
        bl = [(i + (i < -1)).bit_length() for i in item]
        bit_lengths = [max(*pair) for pair in zip(bl, bit_lengths)]
    # The addition of 8, instead of seven, is to account for the sign bit.
    # This "((b + 8) >> 3) if b else 0" when combined with the above
    # "(i + (i < -1)).bit_length()" is a faster way to compute byte-lengths
    # conforming to:
    #
    # byte_length = (0 if i == 0 else
    # 		 1 if -128 <= i < 128 else
    # 		 2 if -65536 <= i < 65536 else
    # 		 ...)
    byte_lengths = [((b + 8) >> 3) if b else 0 for b in bit_lengths]

    # https://github.com/fonttools/fonttools/issues/2279
    longWords = any(b > 2 for b in byte_lengths)

    if optimize:
        # Reorder columns such that wider columns come before narrower columns
        mapping = []
        mapping.extend(i for i, b in enumerate(byte_lengths) if b > 2)
        mapping.extend(i for i, b in enumerate(byte_lengths) if b == 2)
        mapping.extend(i for i, b in enumerate(byte_lengths) if b == 1)

        byte_lengths = _reorderItem(byte_lengths, mapping)
        self.VarRegionIndex = _reorderItem(self.VarRegionIndex, mapping)
        self.VarRegionCount = len(self.VarRegionIndex)
        for i in range(len(items)):
            items[i] = _reorderItem(items[i], mapping)

    if longWords:
        self.NumShorts = (
            max((i for i, b in enumerate(byte_lengths) if b > 2), default=-1) + 1
        )
        self.NumShorts |= 0x8000
    else:
        self.NumShorts = (
            max((i for i, b in enumerate(byte_lengths) if b > 1), default=-1) + 1
        )

    self.VarRegionCount = len(self.VarRegionIndex)
    return self


ot.VarData.calculateNumShorts = VarData_calculateNumShorts


def VarData_CalculateNumShorts(self, optimize=True):
    """Deprecated name for VarData_calculateNumShorts() which
    defaults to optimize=True.  Use varData.calculateNumShorts()
    or varData.optimize()."""
    return VarData_calculateNumShorts(self, optimize=optimize)


def VarData_optimize(self):
    return VarData_calculateNumShorts(self, optimize=True)


ot.VarData.optimize = VarData_optimize


def buildVarData(varRegionIndices, items, optimize=True):
    self = ot.VarData()
    self.VarRegionIndex = list(varRegionIndices)
    regionCount = self.VarRegionCount = len(self.VarRegionIndex)
    records = self.Item = []
    if items:
        for item in items:
            assert len(item) == regionCount
            records.append(list(item))
    self.ItemCount = len(self.Item)
    self.calculateNumShorts(optimize=optimize)
    return self


def buildVarStore(varRegionList, varDataList):
    self = ot.VarStore()
    self.Format = 1
    self.VarRegionList = varRegionList
    self.VarData = list(varDataList)
    self.VarDataCount = len(self.VarData)
    return self


def buildMultiVarData(varRegionIndices, items):
    self = ot.MultiVarData()
    self.Format = 1
    self.VarRegionIndex = list(varRegionIndices)
    regionCount = self.VarRegionCount = len(self.VarRegionIndex)
    records = self.Item = []
    if items:
        for item in items:
            assert len(item) == regionCount
            records.append(list(item))
    self.ItemCount = len(self.Item)
    return self


def buildMultiVarStore(varRegionList, multiVarDataList):
    self = ot.MultiVarStore()
    self.Format = 1
    self.SparseVarRegionList = varRegionList
    self.MultiVarData = list(multiVarDataList)
    self.MultiVarDataCount = len(self.MultiVarData)
    return self


# Variation helpers


def buildVarIdxMap(varIdxes, glyphOrder):
    self = ot.VarIdxMap()
    self.mapping = {g: v for g, v in zip(glyphOrder, varIdxes)}
    return self


def buildDeltaSetIndexMap(varIdxes):
    mapping = list(varIdxes)
    if all(i == v for i, v in enumerate(mapping)):
        return None
    self = ot.DeltaSetIndexMap()
    self.mapping = mapping
    self.Format = 1 if len(mapping) > 0xFFFF else 0
    return self


def buildVarDevTable(varIdx):
    self = ot.Device()
    self.DeltaFormat = 0x8000
    self.StartSize = varIdx >> 16
    self.EndSize = varIdx & 0xFFFF
    return self
