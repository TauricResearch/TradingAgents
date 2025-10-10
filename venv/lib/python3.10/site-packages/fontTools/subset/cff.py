from fontTools.misc import psCharStrings
from fontTools import ttLib
from fontTools.pens.basePen import NullPen
from fontTools.misc.roundTools import otRound
from fontTools.misc.loggingTools import deprecateFunction
from fontTools.subset.util import _add_method, _uniq_sort


class _ClosureGlyphsT2Decompiler(psCharStrings.SimpleT2Decompiler):
    def __init__(self, components, localSubrs, globalSubrs):
        psCharStrings.SimpleT2Decompiler.__init__(self, localSubrs, globalSubrs)
        self.components = components

    def op_endchar(self, index):
        args = self.popall()
        if len(args) >= 4:
            from fontTools.encodings.StandardEncoding import StandardEncoding

            # endchar can do seac accent bulding; The T2 spec says it's deprecated,
            # but recent software that shall remain nameless does output it.
            adx, ady, bchar, achar = args[-4:]
            baseGlyph = StandardEncoding[bchar]
            accentGlyph = StandardEncoding[achar]
            self.components.add(baseGlyph)
            self.components.add(accentGlyph)


@_add_method(ttLib.getTableClass("CFF "))
def closure_glyphs(self, s):
    cff = self.cff
    assert len(cff) == 1
    font = cff[cff.keys()[0]]
    glyphSet = font.CharStrings

    decompose = s.glyphs
    while decompose:
        components = set()
        for g in decompose:
            if g not in glyphSet:
                continue
            gl = glyphSet[g]

            subrs = getattr(gl.private, "Subrs", [])
            decompiler = _ClosureGlyphsT2Decompiler(components, subrs, gl.globalSubrs)
            decompiler.execute(gl)
        components -= s.glyphs
        s.glyphs.update(components)
        decompose = components


def _empty_charstring(font, glyphName, isCFF2, ignoreWidth=False):
    c, fdSelectIndex = font.CharStrings.getItemAndSelector(glyphName)
    if isCFF2 or ignoreWidth:
        # CFF2 charstrings have no widths nor 'endchar' operators
        c.setProgram([] if isCFF2 else ["endchar"])
    else:
        if hasattr(font, "FDArray") and font.FDArray is not None:
            private = font.FDArray[fdSelectIndex].Private
        else:
            private = font.Private
        dfltWdX = private.defaultWidthX
        nmnlWdX = private.nominalWidthX
        pen = NullPen()
        c.draw(pen)  # this will set the charstring's width
        if c.width != dfltWdX:
            c.program = [c.width - nmnlWdX, "endchar"]
        else:
            c.program = ["endchar"]


@_add_method(ttLib.getTableClass("CFF "))
def prune_pre_subset(self, font, options):
    cff = self.cff
    # CFF table must have one font only
    cff.fontNames = cff.fontNames[:1]

    if options.notdef_glyph and not options.notdef_outline:
        isCFF2 = cff.major > 1
        for fontname in cff.keys():
            font = cff[fontname]
            _empty_charstring(font, ".notdef", isCFF2=isCFF2)

    # Clear useless Encoding
    for fontname in cff.keys():
        font = cff[fontname]
        # https://github.com/fonttools/fonttools/issues/620
        font.Encoding = "StandardEncoding"

    return True  # bool(cff.fontNames)


@_add_method(ttLib.getTableClass("CFF "))
def subset_glyphs(self, s):
    cff = self.cff
    for fontname in cff.keys():
        font = cff[fontname]
        cs = font.CharStrings

        glyphs = s.glyphs.union(s.glyphs_emptied)

        # Load all glyphs
        for g in font.charset:
            if g not in glyphs:
                continue
            c, _ = cs.getItemAndSelector(g)

        if cs.charStringsAreIndexed:
            indices = [i for i, g in enumerate(font.charset) if g in glyphs]
            csi = cs.charStringsIndex
            csi.items = [csi.items[i] for i in indices]
            del csi.file, csi.offsets
            if hasattr(font, "FDSelect"):
                sel = font.FDSelect
                sel.format = None
                sel.gidArray = [sel.gidArray[i] for i in indices]
            newCharStrings = {}
            for indicesIdx, charsetIdx in enumerate(indices):
                g = font.charset[charsetIdx]
                if g in cs.charStrings:
                    newCharStrings[g] = indicesIdx
            cs.charStrings = newCharStrings
        else:
            cs.charStrings = {g: v for g, v in cs.charStrings.items() if g in glyphs}
        font.charset = [g for g in font.charset if g in glyphs]
        font.numGlyphs = len(font.charset)

        if s.options.retain_gids:
            isCFF2 = cff.major > 1
            for g in s.glyphs_emptied:
                _empty_charstring(font, g, isCFF2=isCFF2, ignoreWidth=True)

    return True  # any(cff[fontname].numGlyphs for fontname in cff.keys())


@_add_method(ttLib.getTableClass("CFF "))
def prune_post_subset(self, ttfFont, options):
    cff = self.cff
    for fontname in cff.keys():
        font = cff[fontname]
        cs = font.CharStrings

        # Drop unused FontDictionaries
        if hasattr(font, "FDSelect"):
            sel = font.FDSelect
            indices = _uniq_sort(sel.gidArray)
            sel.gidArray = [indices.index(ss) for ss in sel.gidArray]
            arr = font.FDArray
            arr.items = [arr[i] for i in indices]
            del arr.file, arr.offsets

    # Desubroutinize if asked for
    if options.desubroutinize:
        cff.desubroutinize()

    # Drop hints if not needed
    if not options.hinting:
        self.remove_hints()
    elif not options.desubroutinize:
        self.remove_unused_subroutines()
    return True


@deprecateFunction(
    "use 'CFFFontSet.desubroutinize()' instead", category=DeprecationWarning
)
@_add_method(ttLib.getTableClass("CFF "))
def desubroutinize(self):
    self.cff.desubroutinize()


@deprecateFunction(
    "use 'CFFFontSet.remove_hints()' instead", category=DeprecationWarning
)
@_add_method(ttLib.getTableClass("CFF "))
def remove_hints(self):
    self.cff.remove_hints()


@deprecateFunction(
    "use 'CFFFontSet.remove_unused_subroutines' instead", category=DeprecationWarning
)
@_add_method(ttLib.getTableClass("CFF "))
def remove_unused_subroutines(self):
    self.cff.remove_unused_subroutines()
