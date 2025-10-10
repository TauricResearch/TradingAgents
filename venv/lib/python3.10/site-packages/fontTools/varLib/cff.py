from collections import namedtuple
from fontTools.cffLib import (
    maxStackLimit,
    TopDictIndex,
    buildOrder,
    topDictOperators,
    topDictOperators2,
    privateDictOperators,
    privateDictOperators2,
    FDArrayIndex,
    FontDict,
    VarStoreData,
)
from io import BytesIO
from fontTools.cffLib.specializer import specializeCommands, commandsToProgram
from fontTools.ttLib import newTable
from fontTools import varLib
from fontTools.varLib.models import allEqual
from fontTools.misc.loggingTools import deprecateFunction
from fontTools.misc.roundTools import roundFunc
from fontTools.misc.psCharStrings import T2CharString, T2OutlineExtractor
from fontTools.pens.t2CharStringPen import T2CharStringPen
from functools import partial

from .errors import (
    VarLibCFFDictMergeError,
    VarLibCFFPointTypeMergeError,
    VarLibCFFHintTypeMergeError,
    VarLibMergeError,
)


# Backwards compatibility
MergeDictError = VarLibCFFDictMergeError
MergeTypeError = VarLibCFFPointTypeMergeError


def addCFFVarStore(varFont, varModel, varDataList, masterSupports):
    fvarTable = varFont["fvar"]
    axisKeys = [axis.axisTag for axis in fvarTable.axes]
    varTupleList = varLib.builder.buildVarRegionList(masterSupports, axisKeys)
    varStoreCFFV = varLib.builder.buildVarStore(varTupleList, varDataList)

    topDict = varFont["CFF2"].cff.topDictIndex[0]
    topDict.VarStore = VarStoreData(otVarStore=varStoreCFFV)
    if topDict.FDArray[0].vstore is None:
        fdArray = topDict.FDArray
        for fontDict in fdArray:
            if hasattr(fontDict, "Private"):
                fontDict.Private.vstore = topDict.VarStore


@deprecateFunction("Use fontTools.cffLib.CFFToCFF2.convertCFFToCFF2 instead.")
def convertCFFtoCFF2(varFont):
    from fontTools.cffLib.CFFToCFF2 import convertCFFToCFF2

    return convertCFFToCFF2(varFont)


def conv_to_int(num):
    if isinstance(num, float) and num.is_integer():
        return int(num)
    return num


pd_blend_fields = (
    "BlueValues",
    "OtherBlues",
    "FamilyBlues",
    "FamilyOtherBlues",
    "BlueScale",
    "BlueShift",
    "BlueFuzz",
    "StdHW",
    "StdVW",
    "StemSnapH",
    "StemSnapV",
)


def get_private(regionFDArrays, fd_index, ri, fd_map):
    region_fdArray = regionFDArrays[ri]
    region_fd_map = fd_map[fd_index]
    if ri in region_fd_map:
        region_fdIndex = region_fd_map[ri]
        private = region_fdArray[region_fdIndex].Private
    else:
        private = None
    return private


def merge_PrivateDicts(top_dicts, vsindex_dict, var_model, fd_map):
    """
    I step through the FontDicts in the FDArray of the varfont TopDict.
    For each varfont FontDict:

    * step through each key in FontDict.Private.
    * For each key, step through each relevant source font Private dict, and
      build a list of values to blend.

    The 'relevant' source fonts are selected by first getting the right
    submodel using ``vsindex_dict[vsindex]``. The indices of the
    ``subModel.locations`` are mapped to source font list indices by
    assuming the latter order is the same as the order of the
    ``var_model.locations``. I can then get the index of each subModel
    location in the list of ``var_model.locations``.
    """

    topDict = top_dicts[0]
    region_top_dicts = top_dicts[1:]
    if hasattr(region_top_dicts[0], "FDArray"):
        regionFDArrays = [fdTopDict.FDArray for fdTopDict in region_top_dicts]
    else:
        regionFDArrays = [[fdTopDict] for fdTopDict in region_top_dicts]
    for fd_index, font_dict in enumerate(topDict.FDArray):
        private_dict = font_dict.Private
        vsindex = getattr(private_dict, "vsindex", 0)
        # At the moment, no PrivateDict has a vsindex key, but let's support
        # how it should work. See comment at end of
        # merge_charstrings() - still need to optimize use of vsindex.
        sub_model, _ = vsindex_dict[vsindex]
        master_indices = []
        for loc in sub_model.locations[1:]:
            i = var_model.locations.index(loc) - 1
            master_indices.append(i)
        pds = [private_dict]
        last_pd = private_dict
        for ri in master_indices:
            pd = get_private(regionFDArrays, fd_index, ri, fd_map)
            # If the region font doesn't have this FontDict, just reference
            # the last one used.
            if pd is None:
                pd = last_pd
            else:
                last_pd = pd
            pds.append(pd)
        num_masters = len(pds)
        for key, value in private_dict.rawDict.items():
            dataList = []
            if key not in pd_blend_fields:
                continue
            if isinstance(value, list):
                try:
                    values = [pd.rawDict[key] for pd in pds]
                except KeyError:
                    print(
                        "Warning: {key} in default font Private dict is "
                        "missing from another font, and was "
                        "discarded.".format(key=key)
                    )
                    continue
                try:
                    values = zip(*values)
                except IndexError:
                    raise VarLibCFFDictMergeError(key, value, values)
                """
				Row 0 contains the first  value from each master.
				Convert each row from absolute values to relative
				values from the previous row.
				e.g for three masters,	a list of values was:
				master 0 OtherBlues = [-217,-205]
				master 1 OtherBlues = [-234,-222]
				master 1 OtherBlues = [-188,-176]
				The call to zip() converts this to:
				[(-217, -234, -188), (-205, -222, -176)]
				and is converted finally to:
				OtherBlues = [[-217, 17.0, 46.0], [-205, 0.0, 0.0]]
				"""
                prev_val_list = [0] * num_masters
                any_points_differ = False
                for val_list in values:
                    rel_list = [
                        (val - prev_val_list[i]) for (i, val) in enumerate(val_list)
                    ]
                    if (not any_points_differ) and not allEqual(rel_list):
                        any_points_differ = True
                    prev_val_list = val_list
                    deltas = sub_model.getDeltas(rel_list)
                    # For PrivateDict BlueValues, the default font
                    # values are absolute, not relative to the prior value.
                    deltas[0] = val_list[0]
                    dataList.append(deltas)
                # If there are no blend values,then
                # we can collapse the blend lists.
                if not any_points_differ:
                    dataList = [data[0] for data in dataList]
            else:
                values = [pd.rawDict[key] for pd in pds]
                if not allEqual(values):
                    dataList = sub_model.getDeltas(values)
                else:
                    dataList = values[0]

            # Convert numbers with no decimal part to an int
            if isinstance(dataList, list):
                for i, item in enumerate(dataList):
                    if isinstance(item, list):
                        for j, jtem in enumerate(item):
                            dataList[i][j] = conv_to_int(jtem)
                    else:
                        dataList[i] = conv_to_int(item)
            else:
                dataList = conv_to_int(dataList)

            private_dict.rawDict[key] = dataList


def _cff_or_cff2(font):
    if "CFF " in font:
        return font["CFF "]
    return font["CFF2"]


def getfd_map(varFont, fonts_list):
    """Since a subset source font may have fewer FontDicts in their
    FDArray than the default font, we have to match up the FontDicts in
    the different fonts . We do this with the FDSelect array, and by
    assuming that the same glyph will reference  matching FontDicts in
    each source font. We return a mapping from fdIndex in the default
    font to a dictionary which maps each master list index of each
    region font to the equivalent fdIndex in the region font."""
    fd_map = {}
    default_font = fonts_list[0]
    region_fonts = fonts_list[1:]
    num_regions = len(region_fonts)
    topDict = _cff_or_cff2(default_font).cff.topDictIndex[0]
    if not hasattr(topDict, "FDSelect"):
        # All glyphs reference only one FontDict.
        # Map the FD index for regions to index 0.
        fd_map[0] = {ri: 0 for ri in range(num_regions)}
        return fd_map

    gname_mapping = {}
    default_fdSelect = topDict.FDSelect
    glyphOrder = default_font.getGlyphOrder()
    for gid, fdIndex in enumerate(default_fdSelect):
        gname_mapping[glyphOrder[gid]] = fdIndex
        if fdIndex not in fd_map:
            fd_map[fdIndex] = {}
    for ri, region_font in enumerate(region_fonts):
        region_glyphOrder = region_font.getGlyphOrder()
        region_topDict = _cff_or_cff2(region_font).cff.topDictIndex[0]
        if not hasattr(region_topDict, "FDSelect"):
            # All the glyphs share the same FontDict. Pick any glyph.
            default_fdIndex = gname_mapping[region_glyphOrder[0]]
            fd_map[default_fdIndex][ri] = 0
        else:
            region_fdSelect = region_topDict.FDSelect
            for gid, fdIndex in enumerate(region_fdSelect):
                default_fdIndex = gname_mapping[region_glyphOrder[gid]]
                region_map = fd_map[default_fdIndex]
                if ri not in region_map:
                    region_map[ri] = fdIndex
    return fd_map


CVarData = namedtuple("CVarData", "varDataList masterSupports vsindex_dict")


def merge_region_fonts(varFont, model, ordered_fonts_list, glyphOrder):
    topDict = varFont["CFF2"].cff.topDictIndex[0]
    top_dicts = [topDict] + [
        _cff_or_cff2(ttFont).cff.topDictIndex[0] for ttFont in ordered_fonts_list[1:]
    ]
    num_masters = len(model.mapping)
    cvData = merge_charstrings(glyphOrder, num_masters, top_dicts, model)
    fd_map = getfd_map(varFont, ordered_fonts_list)
    merge_PrivateDicts(top_dicts, cvData.vsindex_dict, model, fd_map)
    addCFFVarStore(varFont, model, cvData.varDataList, cvData.masterSupports)


def _get_cs(charstrings, glyphName, filterEmpty=False):
    if glyphName not in charstrings:
        return None
    cs = charstrings[glyphName]

    if filterEmpty:
        cs.decompile()
        if cs.program == []:  # CFF2 empty charstring
            return None
        elif (
            len(cs.program) <= 2
            and cs.program[-1] == "endchar"
            and (len(cs.program) == 1 or type(cs.program[0]) in (int, float))
        ):  # CFF1 empty charstring
            return None

    return cs


def _add_new_vsindex(
    model, key, masterSupports, vsindex_dict, vsindex_by_key, varDataList
):
    varTupleIndexes = []
    for support in model.supports[1:]:
        if support not in masterSupports:
            masterSupports.append(support)
        varTupleIndexes.append(masterSupports.index(support))
    var_data = varLib.builder.buildVarData(varTupleIndexes, None, False)
    vsindex = len(vsindex_dict)
    vsindex_by_key[key] = vsindex
    vsindex_dict[vsindex] = (model, [key])
    varDataList.append(var_data)
    return vsindex


def merge_charstrings(glyphOrder, num_masters, top_dicts, masterModel):
    vsindex_dict = {}
    vsindex_by_key = {}
    varDataList = []
    masterSupports = []
    default_charstrings = top_dicts[0].CharStrings
    for gid, gname in enumerate(glyphOrder):
        # interpret empty non-default masters as missing glyphs from a sparse master
        all_cs = [
            _get_cs(td.CharStrings, gname, i != 0) for i, td in enumerate(top_dicts)
        ]
        model, model_cs = masterModel.getSubModel(all_cs)
        # create the first pass CFF2 charstring, from
        # the default charstring.
        default_charstring = model_cs[0]
        var_pen = CFF2CharStringMergePen([], gname, num_masters, 0)
        # We need to override outlineExtractor because these
        # charstrings do have widths in the 'program'; we need to drop these
        # values rather than post assertion error for them.
        default_charstring.outlineExtractor = MergeOutlineExtractor
        default_charstring.draw(var_pen)

        # Add the coordinates from all the other regions to the
        # blend lists in the CFF2 charstring.
        region_cs = model_cs[1:]
        for region_idx, region_charstring in enumerate(region_cs, start=1):
            var_pen.restart(region_idx)
            region_charstring.outlineExtractor = MergeOutlineExtractor
            region_charstring.draw(var_pen)

        # Collapse each coordinate list to a blend operator and its args.
        new_cs = var_pen.getCharString(
            private=default_charstring.private,
            globalSubrs=default_charstring.globalSubrs,
            var_model=model,
            optimize=True,
        )
        default_charstrings[gname] = new_cs

        if not region_cs:
            continue

        if (not var_pen.seen_moveto) or ("blend" not in new_cs.program):
            # If this is not a marking glyph, or if there are no blend
            # arguments, then we can use vsindex 0. No need to
            # check if we need a new vsindex.
            continue

        # If the charstring required a new model, create
        # a VarData table to go with, and set vsindex.
        key = tuple(v is not None for v in all_cs)
        try:
            vsindex = vsindex_by_key[key]
        except KeyError:
            vsindex = _add_new_vsindex(
                model, key, masterSupports, vsindex_dict, vsindex_by_key, varDataList
            )
        # We do not need to check for an existing new_cs.private.vsindex,
        # as we know it doesn't exist yet.
        if vsindex != 0:
            new_cs.program[:0] = [vsindex, "vsindex"]

    # If there is no variation in any of the charstrings, then vsindex_dict
    # never gets built. This could still be needed if there is variation
    # in the PrivatDict, so we will build the default data for vsindex = 0.
    if not vsindex_dict:
        key = (True,) * num_masters
        _add_new_vsindex(
            masterModel, key, masterSupports, vsindex_dict, vsindex_by_key, varDataList
        )
    cvData = CVarData(
        varDataList=varDataList,
        masterSupports=masterSupports,
        vsindex_dict=vsindex_dict,
    )
    # XXX To do: optimize use of vsindex between the PrivateDicts and
    # charstrings
    return cvData


class CFFToCFF2OutlineExtractor(T2OutlineExtractor):
    """This class is used to remove the initial width from the CFF
    charstring without trying to add the width to self.nominalWidthX,
    which is None."""

    def popallWidth(self, evenOdd=0):
        args = self.popall()
        if not self.gotWidth:
            if evenOdd ^ (len(args) % 2):
                args = args[1:]
            self.width = self.defaultWidthX
            self.gotWidth = 1
        return args


class MergeOutlineExtractor(CFFToCFF2OutlineExtractor):
    """Used to extract the charstring commands - including hints - from a
    CFF charstring in order to merge it as another set of region data
    into a CFF2 variable font charstring."""

    def __init__(
        self,
        pen,
        localSubrs,
        globalSubrs,
        nominalWidthX,
        defaultWidthX,
        private=None,
        blender=None,
    ):
        super().__init__(
            pen, localSubrs, globalSubrs, nominalWidthX, defaultWidthX, private, blender
        )

    def countHints(self):
        args = self.popallWidth()
        self.hintCount = self.hintCount + len(args) // 2
        return args

    def _hint_op(self, type, args):
        self.pen.add_hint(type, args)

    def op_hstem(self, index):
        args = self.countHints()
        self._hint_op("hstem", args)

    def op_vstem(self, index):
        args = self.countHints()
        self._hint_op("vstem", args)

    def op_hstemhm(self, index):
        args = self.countHints()
        self._hint_op("hstemhm", args)

    def op_vstemhm(self, index):
        args = self.countHints()
        self._hint_op("vstemhm", args)

    def _get_hintmask(self, index):
        if not self.hintMaskBytes:
            args = self.countHints()
            if args:
                self._hint_op("vstemhm", args)
            self.hintMaskBytes = (self.hintCount + 7) // 8
        hintMaskBytes, index = self.callingStack[-1].getBytes(index, self.hintMaskBytes)
        return index, hintMaskBytes

    def op_hintmask(self, index):
        index, hintMaskBytes = self._get_hintmask(index)
        self.pen.add_hintmask("hintmask", [hintMaskBytes])
        return hintMaskBytes, index

    def op_cntrmask(self, index):
        index, hintMaskBytes = self._get_hintmask(index)
        self.pen.add_hintmask("cntrmask", [hintMaskBytes])
        return hintMaskBytes, index


class CFF2CharStringMergePen(T2CharStringPen):
    """Pen to merge Type 2 CharStrings."""

    def __init__(
        self, default_commands, glyphName, num_masters, master_idx, roundTolerance=0.01
    ):
        # For roundTolerance see https://github.com/fonttools/fonttools/issues/2838
        super().__init__(
            width=None, glyphSet=None, CFF2=True, roundTolerance=roundTolerance
        )
        self.pt_index = 0
        self._commands = default_commands
        self.m_index = master_idx
        self.num_masters = num_masters
        self.prev_move_idx = 0
        self.seen_moveto = False
        self.glyphName = glyphName
        self.round = roundFunc(roundTolerance, round=round)

    def add_point(self, point_type, pt_coords):
        if self.m_index == 0:
            self._commands.append([point_type, [pt_coords]])
        else:
            cmd = self._commands[self.pt_index]
            if cmd[0] != point_type:
                raise VarLibCFFPointTypeMergeError(
                    point_type, self.pt_index, len(cmd[1]), cmd[0], self.glyphName
                )
            cmd[1].append(pt_coords)
        self.pt_index += 1

    def add_hint(self, hint_type, args):
        if self.m_index == 0:
            self._commands.append([hint_type, [args]])
        else:
            cmd = self._commands[self.pt_index]
            if cmd[0] != hint_type:
                raise VarLibCFFHintTypeMergeError(
                    hint_type, self.pt_index, len(cmd[1]), cmd[0], self.glyphName
                )
            cmd[1].append(args)
        self.pt_index += 1

    def add_hintmask(self, hint_type, abs_args):
        # For hintmask, fonttools.cffLib.specializer.py expects
        # each of these to be represented by two sequential commands:
        # first holding only the operator name, with an empty arg list,
        # second with an empty string as the op name, and the mask arg list.
        if self.m_index == 0:
            self._commands.append([hint_type, []])
            self._commands.append(["", [abs_args]])
        else:
            cmd = self._commands[self.pt_index]
            if cmd[0] != hint_type:
                raise VarLibCFFHintTypeMergeError(
                    hint_type, self.pt_index, len(cmd[1]), cmd[0], self.glyphName
                )
            self.pt_index += 1
            cmd = self._commands[self.pt_index]
            cmd[1].append(abs_args)
        self.pt_index += 1

    def _moveTo(self, pt):
        if not self.seen_moveto:
            self.seen_moveto = True
        pt_coords = self._p(pt)
        self.add_point("rmoveto", pt_coords)
        # I set prev_move_idx here because add_point()
        # can change self.pt_index.
        self.prev_move_idx = self.pt_index - 1

    def _lineTo(self, pt):
        pt_coords = self._p(pt)
        self.add_point("rlineto", pt_coords)

    def _curveToOne(self, pt1, pt2, pt3):
        _p = self._p
        pt_coords = _p(pt1) + _p(pt2) + _p(pt3)
        self.add_point("rrcurveto", pt_coords)

    def _closePath(self):
        pass

    def _endPath(self):
        pass

    def restart(self, region_idx):
        self.pt_index = 0
        self.m_index = region_idx
        self._p0 = (0, 0)

    def getCommands(self):
        return self._commands

    def reorder_blend_args(self, commands, get_delta_func):
        """
        We first re-order the master coordinate values.
        For a moveto to lineto, the args are now arranged as::

                [ [master_0 x,y], [master_1 x,y], [master_2 x,y] ]

        We re-arrange this to::

                [	[master_0 x, master_1 x, master_2 x],
                        [master_0 y, master_1 y, master_2 y]
                ]

        If the master values are all the same, we collapse the list to
        as single value instead of a list.

        We then convert this to::

                [ [master_0 x] + [x delta tuple] + [numBlends=1]
                  [master_0 y] + [y delta tuple] + [numBlends=1]
                ]
        """
        for cmd in commands:
            # arg[i] is the set of arguments for this operator from master i.
            args = cmd[1]
            m_args = zip(*args)
            # m_args[n] is now all num_master args for the i'th argument
            # for this operation.
            cmd[1] = list(m_args)
        lastOp = None
        for cmd in commands:
            op = cmd[0]
            # masks are represented by two cmd's: first has only op names,
            # second has only args.
            if lastOp in ["hintmask", "cntrmask"]:
                coord = list(cmd[1])
                if not allEqual(coord):
                    raise VarLibMergeError(
                        "Hintmask values cannot differ between source fonts."
                    )
                cmd[1] = [coord[0][0]]
            else:
                coords = cmd[1]
                new_coords = []
                for coord in coords:
                    if allEqual(coord):
                        new_coords.append(coord[0])
                    else:
                        # convert to deltas
                        deltas = get_delta_func(coord)[1:]
                        coord = [coord[0]] + deltas
                        coord.append(1)
                        new_coords.append(coord)
                cmd[1] = new_coords
            lastOp = op
        return commands

    def getCharString(
        self, private=None, globalSubrs=None, var_model=None, optimize=True
    ):
        commands = self._commands
        commands = self.reorder_blend_args(
            commands, partial(var_model.getDeltas, round=self.round)
        )
        if optimize:
            commands = specializeCommands(
                commands, generalizeFirst=False, maxstack=maxStackLimit
            )
        program = commandsToProgram(commands)
        charString = T2CharString(
            program=program, private=private, globalSubrs=globalSubrs
        )
        return charString
