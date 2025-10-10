import weakref
from fontTools.feaLib.error import FeatureLibError
from fontTools.feaLib.location import FeatureLibLocation
from fontTools.misc.encodingTools import getEncoding
from fontTools.misc.textTools import byteord, tobytes
from collections import OrderedDict
import itertools

SHIFT = " " * 4

__all__ = [
    "Element",
    "FeatureFile",
    "Comment",
    "GlyphName",
    "GlyphClass",
    "GlyphClassName",
    "MarkClassName",
    "AnonymousBlock",
    "Block",
    "FeatureBlock",
    "NestedBlock",
    "LookupBlock",
    "GlyphClassDefinition",
    "GlyphClassDefStatement",
    "MarkClass",
    "MarkClassDefinition",
    "AlternateSubstStatement",
    "Anchor",
    "AnchorDefinition",
    "AttachStatement",
    "AxisValueLocationStatement",
    "BaseAxis",
    "CVParametersNameStatement",
    "ChainContextPosStatement",
    "ChainContextSubstStatement",
    "CharacterStatement",
    "ConditionsetStatement",
    "CursivePosStatement",
    "ElidedFallbackName",
    "ElidedFallbackNameID",
    "Expression",
    "FeatureNameStatement",
    "FeatureReferenceStatement",
    "FontRevisionStatement",
    "HheaField",
    "IgnorePosStatement",
    "IgnoreSubstStatement",
    "IncludeStatement",
    "LanguageStatement",
    "LanguageSystemStatement",
    "LigatureCaretByIndexStatement",
    "LigatureCaretByPosStatement",
    "LigatureSubstStatement",
    "LookupFlagStatement",
    "LookupReferenceStatement",
    "MarkBasePosStatement",
    "MarkLigPosStatement",
    "MarkMarkPosStatement",
    "MultipleSubstStatement",
    "NameRecord",
    "OS2Field",
    "PairPosStatement",
    "ReverseChainSingleSubstStatement",
    "ScriptStatement",
    "SinglePosStatement",
    "SingleSubstStatement",
    "SizeParameters",
    "Statement",
    "STATAxisValueStatement",
    "STATDesignAxisStatement",
    "STATNameStatement",
    "SubtableStatement",
    "TableBlock",
    "ValueRecord",
    "ValueRecordDefinition",
    "VheaField",
]


def deviceToString(device):
    if device is None:
        return "<device NULL>"
    else:
        return "<device %s>" % ", ".join("%d %d" % t for t in device)


fea_keywords = set(
    [
        "anchor",
        "anchordef",
        "anon",
        "anonymous",
        "by",
        "contour",
        "cursive",
        "device",
        "enum",
        "enumerate",
        "excludedflt",
        "exclude_dflt",
        "feature",
        "from",
        "ignore",
        "ignorebaseglyphs",
        "ignoreligatures",
        "ignoremarks",
        "include",
        "includedflt",
        "include_dflt",
        "language",
        "languagesystem",
        "lookup",
        "lookupflag",
        "mark",
        "markattachmenttype",
        "markclass",
        "nameid",
        "null",
        "parameters",
        "pos",
        "position",
        "required",
        "righttoleft",
        "reversesub",
        "rsub",
        "script",
        "sub",
        "substitute",
        "subtable",
        "table",
        "usemarkfilteringset",
        "useextension",
        "valuerecorddef",
        "base",
        "gdef",
        "head",
        "hhea",
        "name",
        "vhea",
        "vmtx",
    ]
)


def asFea(g):
    if hasattr(g, "asFea"):
        return g.asFea()
    elif isinstance(g, tuple) and len(g) == 2:
        return asFea(g[0]) + " - " + asFea(g[1])  # a range
    elif g.lower() in fea_keywords:
        return "\\" + g
    else:
        return g


class Element(object):
    """A base class representing "something" in a feature file."""

    def __init__(self, location=None):
        #: location of this element as a `FeatureLibLocation` object.
        if location and not isinstance(location, FeatureLibLocation):
            location = FeatureLibLocation(*location)
        self.location = location

    def build(self, builder):
        pass

    def asFea(self, indent=""):
        """Returns this element as a string of feature code. For block-type
        elements (such as :class:`FeatureBlock`), the `indent` string is
        added to the start of each line in the output."""
        raise NotImplementedError

    def __str__(self):
        return self.asFea()


class Statement(Element):
    pass


class Expression(Element):
    pass


class Comment(Element):
    """A comment in a feature file."""

    def __init__(self, text, location=None):
        super(Comment, self).__init__(location)
        #: Text of the comment
        self.text = text

    def asFea(self, indent=""):
        return self.text


class NullGlyph(Expression):
    """The NULL glyph, used in glyph deletion substitutions."""

    def __init__(self, location=None):
        Expression.__init__(self, location)
        #: The name itself as a string

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return ()

    def asFea(self, indent=""):
        return "NULL"


class GlyphName(Expression):
    """A single glyph name, such as ``cedilla``."""

    def __init__(self, glyph, location=None):
        Expression.__init__(self, location)
        #: The name itself as a string
        self.glyph = glyph

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return (self.glyph,)

    def asFea(self, indent=""):
        return asFea(self.glyph)


class GlyphClass(Expression):
    """A glyph class, such as ``[acute cedilla grave]``."""

    def __init__(self, glyphs=None, location=None):
        Expression.__init__(self, location)
        #: The list of glyphs in this class, as :class:`GlyphName` objects.
        self.glyphs = glyphs if glyphs is not None else []
        self.original = []
        self.curr = 0

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return tuple(self.glyphs)

    def asFea(self, indent=""):
        if len(self.original):
            if self.curr < len(self.glyphs):
                self.original.extend(self.glyphs[self.curr :])
                self.curr = len(self.glyphs)
            return "[" + " ".join(map(asFea, self.original)) + "]"
        else:
            return "[" + " ".join(map(asFea, self.glyphs)) + "]"

    def extend(self, glyphs):
        """Add a list of :class:`GlyphName` objects to the class."""
        self.glyphs.extend(glyphs)

    def append(self, glyph):
        """Add a single :class:`GlyphName` object to the class."""
        self.glyphs.append(glyph)

    def add_range(self, start, end, glyphs):
        """Add a range (e.g. ``A-Z``) to the class. ``start`` and ``end``
        are either :class:`GlyphName` objects or strings representing the
        start and end glyphs in the class, and ``glyphs`` is the full list of
        :class:`GlyphName` objects in the range."""
        if self.curr < len(self.glyphs):
            self.original.extend(self.glyphs[self.curr :])
        self.original.append((start, end))
        self.glyphs.extend(glyphs)
        self.curr = len(self.glyphs)

    def add_cid_range(self, start, end, glyphs):
        """Add a range to the class by glyph ID. ``start`` and ``end`` are the
        initial and final IDs, and ``glyphs`` is the full list of
        :class:`GlyphName` objects in the range."""
        if self.curr < len(self.glyphs):
            self.original.extend(self.glyphs[self.curr :])
        self.original.append(("\\{}".format(start), "\\{}".format(end)))
        self.glyphs.extend(glyphs)
        self.curr = len(self.glyphs)

    def add_class(self, gc):
        """Add glyphs from the given :class:`GlyphClassName` object to the
        class."""
        if self.curr < len(self.glyphs):
            self.original.extend(self.glyphs[self.curr :])
        self.original.append(gc)
        self.glyphs.extend(gc.glyphSet())
        self.curr = len(self.glyphs)


class GlyphClassName(Expression):
    """A glyph class name, such as ``@FRENCH_MARKS``. This must be instantiated
    with a :class:`GlyphClassDefinition` object."""

    def __init__(self, glyphclass, location=None):
        Expression.__init__(self, location)
        assert isinstance(glyphclass, GlyphClassDefinition)
        self.glyphclass = glyphclass

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return tuple(self.glyphclass.glyphSet())

    def asFea(self, indent=""):
        return "@" + self.glyphclass.name


class MarkClassName(Expression):
    """A mark class name, such as ``@FRENCH_MARKS`` defined with ``markClass``.
    This must be instantiated with a :class:`MarkClass` object."""

    def __init__(self, markClass, location=None):
        Expression.__init__(self, location)
        assert isinstance(markClass, MarkClass)
        self.markClass = markClass

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return self.markClass.glyphSet()

    def asFea(self, indent=""):
        return "@" + self.markClass.name


class AnonymousBlock(Statement):
    """An anonymous data block."""

    def __init__(self, tag, content, location=None):
        Statement.__init__(self, location)
        self.tag = tag  #: string containing the block's "tag"
        self.content = content  #: block data as string

    def asFea(self, indent=""):
        res = "anon {} {{\n".format(self.tag)
        res += self.content
        res += "}} {};\n\n".format(self.tag)
        return res


class Block(Statement):
    """A block of statements: feature, lookup, etc."""

    def __init__(self, location=None):
        Statement.__init__(self, location)
        self.statements = []  #: Statements contained in the block

    def build(self, builder):
        """When handed a 'builder' object of comparable interface to
        :class:`fontTools.feaLib.builder`, walks the statements in this
        block, calling the builder callbacks."""
        for s in self.statements:
            s.build(builder)

    def asFea(self, indent=""):
        indent += SHIFT
        return (
            indent
            + ("\n" + indent).join([s.asFea(indent=indent) for s in self.statements])
            + "\n"
        )


class FeatureFile(Block):
    """The top-level element of the syntax tree, containing the whole feature
    file in its ``statements`` attribute."""

    def __init__(self):
        Block.__init__(self, location=None)
        self.markClasses = {}  # name --> ast.MarkClass

    def asFea(self, indent=""):
        return "\n".join(s.asFea(indent=indent) for s in self.statements)


class FeatureBlock(Block):
    """A named feature block."""

    def __init__(self, name, use_extension=False, location=None):
        Block.__init__(self, location)
        self.name, self.use_extension = name, use_extension

    def build(self, builder):
        """Call the ``start_feature`` callback on the builder object, visit
        all the statements in this feature, and then call ``end_feature``."""
        builder.start_feature(self.location, self.name, self.use_extension)
        # language exclude_dflt statements modify builder.features_
        # limit them to this block with temporary builder.features_
        features = builder.features_
        builder.features_ = {}
        Block.build(self, builder)
        for key, value in builder.features_.items():
            features.setdefault(key, []).extend(value)
        builder.features_ = features
        builder.end_feature()

    def asFea(self, indent=""):
        res = indent + "feature %s " % self.name.strip()
        if self.use_extension:
            res += "useExtension "
        res += "{\n"
        res += Block.asFea(self, indent=indent)
        res += indent + "} %s;\n" % self.name.strip()
        return res


class NestedBlock(Block):
    """A block inside another block, for example when found inside a
    ``cvParameters`` block."""

    def __init__(self, tag, block_name, location=None):
        Block.__init__(self, location)
        self.tag = tag
        self.block_name = block_name

    def build(self, builder):
        Block.build(self, builder)
        if self.block_name == "ParamUILabelNameID":
            builder.add_to_cv_num_named_params(self.tag)

    def asFea(self, indent=""):
        res = "{}{} {{\n".format(indent, self.block_name)
        res += Block.asFea(self, indent=indent)
        res += "{}}};\n".format(indent)
        return res


class LookupBlock(Block):
    """A named lookup, containing ``statements``."""

    def __init__(self, name, use_extension=False, location=None):
        Block.__init__(self, location)
        self.name, self.use_extension = name, use_extension

    def build(self, builder):
        builder.start_lookup_block(self.location, self.name, self.use_extension)
        Block.build(self, builder)
        builder.end_lookup_block()

    def asFea(self, indent=""):
        res = "lookup {} ".format(self.name)
        if self.use_extension:
            res += "useExtension "
        res += "{\n"
        res += Block.asFea(self, indent=indent)
        res += "{}}} {};\n".format(indent, self.name)
        return res


class TableBlock(Block):
    """A ``table ... { }`` block."""

    def __init__(self, name, location=None):
        Block.__init__(self, location)
        self.name = name

    def asFea(self, indent=""):
        res = "table {} {{\n".format(self.name.strip())
        res += super(TableBlock, self).asFea(indent=indent)
        res += "}} {};\n".format(self.name.strip())
        return res


class GlyphClassDefinition(Statement):
    """Example: ``@UPPERCASE = [A-Z];``."""

    def __init__(self, name, glyphs, location=None):
        Statement.__init__(self, location)
        self.name = name  #: class name as a string, without initial ``@``
        self.glyphs = glyphs  #: a :class:`GlyphClass` object

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return tuple(self.glyphs.glyphSet())

    def asFea(self, indent=""):
        return "@" + self.name + " = " + self.glyphs.asFea() + ";"


class GlyphClassDefStatement(Statement):
    """Example: ``GlyphClassDef @UPPERCASE, [B], [C], [D];``. The parameters
    must be either :class:`GlyphClass` or :class:`GlyphClassName` objects, or
    ``None``."""

    def __init__(
        self, baseGlyphs, markGlyphs, ligatureGlyphs, componentGlyphs, location=None
    ):
        Statement.__init__(self, location)
        self.baseGlyphs, self.markGlyphs = (baseGlyphs, markGlyphs)
        self.ligatureGlyphs = ligatureGlyphs
        self.componentGlyphs = componentGlyphs

    def build(self, builder):
        """Calls the builder's ``add_glyphClassDef`` callback."""
        base = self.baseGlyphs.glyphSet() if self.baseGlyphs else tuple()
        liga = self.ligatureGlyphs.glyphSet() if self.ligatureGlyphs else tuple()
        mark = self.markGlyphs.glyphSet() if self.markGlyphs else tuple()
        comp = self.componentGlyphs.glyphSet() if self.componentGlyphs else tuple()
        builder.add_glyphClassDef(self.location, base, liga, mark, comp)

    def asFea(self, indent=""):
        return "GlyphClassDef {}, {}, {}, {};".format(
            self.baseGlyphs.asFea() if self.baseGlyphs else "",
            self.ligatureGlyphs.asFea() if self.ligatureGlyphs else "",
            self.markGlyphs.asFea() if self.markGlyphs else "",
            self.componentGlyphs.asFea() if self.componentGlyphs else "",
        )


class MarkClass(object):
    """One `or more` ``markClass`` statements for the same mark class.

    While glyph classes can be defined only once, the feature file format
    allows expanding mark classes with multiple definitions, each using
    different glyphs and anchors. The following are two ``MarkClassDefinitions``
    for the same ``MarkClass``::

        markClass [acute grave] <anchor 350 800> @FRENCH_ACCENTS;
        markClass [cedilla] <anchor 350 -200> @FRENCH_ACCENTS;

    The ``MarkClass`` object is therefore just a container for a list of
    :class:`MarkClassDefinition` statements.
    """

    def __init__(self, name):
        self.name = name
        self.definitions = []
        self.glyphs = OrderedDict()  # glyph --> ast.MarkClassDefinitions

    def addDefinition(self, definition):
        """Add a :class:`MarkClassDefinition` statement to this mark class."""
        assert isinstance(definition, MarkClassDefinition)
        self.definitions.append(weakref.proxy(definition))
        for glyph in definition.glyphSet():
            if glyph in self.glyphs:
                otherLoc = self.glyphs[glyph].location
                if otherLoc is None:
                    end = ""
                else:
                    end = f" at {otherLoc}"
                raise FeatureLibError(
                    "Glyph %s already defined%s" % (glyph, end), definition.location
                )
            self.glyphs[glyph] = definition

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return tuple(self.glyphs.keys())

    def asFea(self, indent=""):
        res = "\n".join(d.asFea() for d in self.definitions)
        return res


class MarkClassDefinition(Statement):
    """A single ``markClass`` statement. The ``markClass`` should be a
    :class:`MarkClass` object, the ``anchor`` an :class:`Anchor` object,
    and the ``glyphs`` parameter should be a `glyph-containing object`_ .

    Example:

        .. code:: python

            mc = MarkClass("FRENCH_ACCENTS")
            mc.addDefinition( MarkClassDefinition(mc, Anchor(350, 800),
                GlyphClass([ GlyphName("acute"), GlyphName("grave") ])
            ) )
            mc.addDefinition( MarkClassDefinition(mc, Anchor(350, -200),
                GlyphClass([ GlyphName("cedilla") ])
            ) )

            mc.asFea()
            # markClass [acute grave] <anchor 350 800> @FRENCH_ACCENTS;
            # markClass [cedilla] <anchor 350 -200> @FRENCH_ACCENTS;

    """

    def __init__(self, markClass, anchor, glyphs, location=None):
        Statement.__init__(self, location)
        assert isinstance(markClass, MarkClass)
        assert isinstance(anchor, Anchor) and isinstance(glyphs, Expression)
        self.markClass, self.anchor, self.glyphs = markClass, anchor, glyphs

    def glyphSet(self):
        """The glyphs in this class as a tuple of :class:`GlyphName` objects."""
        return self.glyphs.glyphSet()

    def asFea(self, indent=""):
        return "markClass {} {} @{};".format(
            self.glyphs.asFea(), self.anchor.asFea(), self.markClass.name
        )


class AlternateSubstStatement(Statement):
    """A ``sub ... from ...`` statement.

    ``glyph`` and ``replacement`` should be `glyph-containing objects`_.
    ``prefix`` and ``suffix`` should be lists of `glyph-containing objects`_."""

    def __init__(self, prefix, glyph, suffix, replacement, location=None):
        Statement.__init__(self, location)
        self.prefix, self.glyph, self.suffix = (prefix, glyph, suffix)
        self.replacement = replacement

    def build(self, builder):
        """Calls the builder's ``add_alternate_subst`` callback."""
        glyph = self.glyph.glyphSet()
        assert len(glyph) == 1, glyph
        glyph = list(glyph)[0]
        prefix = [p.glyphSet() for p in self.prefix]
        suffix = [s.glyphSet() for s in self.suffix]
        replacement = self.replacement.glyphSet()
        builder.add_alternate_subst(self.location, prefix, glyph, suffix, replacement)

    def asFea(self, indent=""):
        res = "sub "
        if len(self.prefix) or len(self.suffix):
            if len(self.prefix):
                res += " ".join(map(asFea, self.prefix)) + " "
            res += asFea(self.glyph) + "'"  # even though we really only use 1
            if len(self.suffix):
                res += " " + " ".join(map(asFea, self.suffix))
        else:
            res += asFea(self.glyph)
        res += " from "
        res += asFea(self.replacement)
        res += ";"
        return res


class Anchor(Expression):
    """An ``Anchor`` element, used inside a ``pos`` rule.

    If a ``name`` is given, this will be used in preference to the coordinates.
    Other values should be integer.
    """

    def __init__(
        self,
        x,
        y,
        name=None,
        contourpoint=None,
        xDeviceTable=None,
        yDeviceTable=None,
        location=None,
    ):
        Expression.__init__(self, location)
        self.name = name
        self.x, self.y, self.contourpoint = x, y, contourpoint
        self.xDeviceTable, self.yDeviceTable = xDeviceTable, yDeviceTable

    def asFea(self, indent=""):
        if self.name is not None:
            return "<anchor {}>".format(self.name)
        res = "<anchor {} {}".format(self.x, self.y)
        if self.contourpoint:
            res += " contourpoint {}".format(self.contourpoint)
        if self.xDeviceTable or self.yDeviceTable:
            res += " "
            res += deviceToString(self.xDeviceTable)
            res += " "
            res += deviceToString(self.yDeviceTable)
        res += ">"
        return res


class AnchorDefinition(Statement):
    """A named anchor definition. (2.e.viii). ``name`` should be a string."""

    def __init__(self, name, x, y, contourpoint=None, location=None):
        Statement.__init__(self, location)
        self.name, self.x, self.y, self.contourpoint = name, x, y, contourpoint

    def asFea(self, indent=""):
        res = "anchorDef {} {}".format(self.x, self.y)
        if self.contourpoint:
            res += " contourpoint {}".format(self.contourpoint)
        res += " {};".format(self.name)
        return res


class AttachStatement(Statement):
    """A ``GDEF`` table ``Attach`` statement."""

    def __init__(self, glyphs, contourPoints, location=None):
        Statement.__init__(self, location)
        self.glyphs = glyphs  #: A `glyph-containing object`_
        self.contourPoints = contourPoints  #: A list of integer contour points

    def build(self, builder):
        """Calls the builder's ``add_attach_points`` callback."""
        glyphs = self.glyphs.glyphSet()
        builder.add_attach_points(self.location, glyphs, self.contourPoints)

    def asFea(self, indent=""):
        return "Attach {} {};".format(
            self.glyphs.asFea(), " ".join(str(c) for c in self.contourPoints)
        )


class ChainContextPosStatement(Statement):
    r"""A chained contextual positioning statement.

    ``prefix``, ``glyphs``, and ``suffix`` should be lists of
    `glyph-containing objects`_ .

    ``lookups`` should be a list of elements representing what lookups
    to apply at each glyph position. Each element should be a
    :class:`LookupBlock` to apply a single chaining lookup at the given
    position, a list of :class:`LookupBlock`\ s to apply multiple
    lookups, or ``None`` to apply no lookup. The length of the outer
    list should equal the length of ``glyphs``; the inner lists can be
    of variable length."""

    def __init__(self, prefix, glyphs, suffix, lookups, location=None):
        Statement.__init__(self, location)
        self.prefix, self.glyphs, self.suffix = prefix, glyphs, suffix
        self.lookups = list(lookups)
        for i, lookup in enumerate(lookups):
            if lookup:
                try:
                    iter(lookup)
                except TypeError:
                    self.lookups[i] = [lookup]

    def build(self, builder):
        """Calls the builder's ``add_chain_context_pos`` callback."""
        prefix = [p.glyphSet() for p in self.prefix]
        glyphs = [g.glyphSet() for g in self.glyphs]
        suffix = [s.glyphSet() for s in self.suffix]
        builder.add_chain_context_pos(
            self.location, prefix, glyphs, suffix, self.lookups
        )

    def asFea(self, indent=""):
        res = "pos "
        if (
            len(self.prefix)
            or len(self.suffix)
            or any([x is not None for x in self.lookups])
        ):
            if len(self.prefix):
                res += " ".join(g.asFea() for g in self.prefix) + " "
            for i, g in enumerate(self.glyphs):
                res += g.asFea() + "'"
                if self.lookups[i]:
                    for lu in self.lookups[i]:
                        res += " lookup " + lu.name
                if i < len(self.glyphs) - 1:
                    res += " "
            if len(self.suffix):
                res += " " + " ".join(map(asFea, self.suffix))
        else:
            res += " ".join(map(asFea, self.glyphs))
        res += ";"
        return res


class ChainContextSubstStatement(Statement):
    r"""A chained contextual substitution statement.

    ``prefix``, ``glyphs``, and ``suffix`` should be lists of
    `glyph-containing objects`_ .

    ``lookups`` should be a list of elements representing what lookups
    to apply at each glyph position. Each element should be a
    :class:`LookupBlock` to apply a single chaining lookup at the given
    position, a list of :class:`LookupBlock`\ s to apply multiple
    lookups, or ``None`` to apply no lookup. The length of the outer
    list should equal the length of ``glyphs``; the inner lists can be
    of variable length."""

    def __init__(self, prefix, glyphs, suffix, lookups, location=None):
        Statement.__init__(self, location)
        self.prefix, self.glyphs, self.suffix = prefix, glyphs, suffix
        self.lookups = list(lookups)
        for i, lookup in enumerate(lookups):
            if lookup:
                try:
                    iter(lookup)
                except TypeError:
                    self.lookups[i] = [lookup]

    def build(self, builder):
        """Calls the builder's ``add_chain_context_subst`` callback."""
        prefix = [p.glyphSet() for p in self.prefix]
        glyphs = [g.glyphSet() for g in self.glyphs]
        suffix = [s.glyphSet() for s in self.suffix]
        builder.add_chain_context_subst(
            self.location, prefix, glyphs, suffix, self.lookups
        )

    def asFea(self, indent=""):
        res = "sub "
        if (
            len(self.prefix)
            or len(self.suffix)
            or any([x is not None for x in self.lookups])
        ):
            if len(self.prefix):
                res += " ".join(g.asFea() for g in self.prefix) + " "
            for i, g in enumerate(self.glyphs):
                res += g.asFea() + "'"
                if self.lookups[i]:
                    for lu in self.lookups[i]:
                        res += " lookup " + lu.name
                if i < len(self.glyphs) - 1:
                    res += " "
            if len(self.suffix):
                res += " " + " ".join(map(asFea, self.suffix))
        else:
            res += " ".join(map(asFea, self.glyphs))
        res += ";"
        return res


class CursivePosStatement(Statement):
    """A cursive positioning statement. Entry and exit anchors can either
    be :class:`Anchor` objects or ``None``."""

    def __init__(self, glyphclass, entryAnchor, exitAnchor, location=None):
        Statement.__init__(self, location)
        self.glyphclass = glyphclass
        self.entryAnchor, self.exitAnchor = entryAnchor, exitAnchor

    def build(self, builder):
        """Calls the builder object's ``add_cursive_pos`` callback."""
        builder.add_cursive_pos(
            self.location, self.glyphclass.glyphSet(), self.entryAnchor, self.exitAnchor
        )

    def asFea(self, indent=""):
        entry = self.entryAnchor.asFea() if self.entryAnchor else "<anchor NULL>"
        exit = self.exitAnchor.asFea() if self.exitAnchor else "<anchor NULL>"
        return "pos cursive {} {} {};".format(self.glyphclass.asFea(), entry, exit)


class FeatureReferenceStatement(Statement):
    """Example: ``feature salt;``"""

    def __init__(self, featureName, location=None):
        Statement.__init__(self, location)
        self.location, self.featureName = (location, featureName)

    def build(self, builder):
        """Calls the builder object's ``add_feature_reference`` callback."""
        builder.add_feature_reference(self.location, self.featureName)

    def asFea(self, indent=""):
        return "feature {};".format(self.featureName)


class IgnorePosStatement(Statement):
    """An ``ignore pos`` statement, containing `one or more` contexts to ignore.

    ``chainContexts`` should be a list of ``(prefix, glyphs, suffix)`` tuples,
    with each of ``prefix``, ``glyphs`` and ``suffix`` being
    `glyph-containing objects`_ ."""

    def __init__(self, chainContexts, location=None):
        Statement.__init__(self, location)
        self.chainContexts = chainContexts

    def build(self, builder):
        """Calls the builder object's ``add_chain_context_pos`` callback on each
        rule context."""
        for prefix, glyphs, suffix in self.chainContexts:
            prefix = [p.glyphSet() for p in prefix]
            glyphs = [g.glyphSet() for g in glyphs]
            suffix = [s.glyphSet() for s in suffix]
            builder.add_chain_context_pos(self.location, prefix, glyphs, suffix, [])

    def asFea(self, indent=""):
        contexts = []
        for prefix, glyphs, suffix in self.chainContexts:
            res = ""
            if len(prefix) or len(suffix):
                if len(prefix):
                    res += " ".join(map(asFea, prefix)) + " "
                res += " ".join(g.asFea() + "'" for g in glyphs)
                if len(suffix):
                    res += " " + " ".join(map(asFea, suffix))
            else:
                res += " ".join(map(asFea, glyphs))
            contexts.append(res)
        return "ignore pos " + ", ".join(contexts) + ";"


class IgnoreSubstStatement(Statement):
    """An ``ignore sub`` statement, containing `one or more` contexts to ignore.

    ``chainContexts`` should be a list of ``(prefix, glyphs, suffix)`` tuples,
    with each of ``prefix``, ``glyphs`` and ``suffix`` being
    `glyph-containing objects`_ ."""

    def __init__(self, chainContexts, location=None):
        Statement.__init__(self, location)
        self.chainContexts = chainContexts

    def build(self, builder):
        """Calls the builder object's ``add_chain_context_subst`` callback on
        each rule context."""
        for prefix, glyphs, suffix in self.chainContexts:
            prefix = [p.glyphSet() for p in prefix]
            glyphs = [g.glyphSet() for g in glyphs]
            suffix = [s.glyphSet() for s in suffix]
            builder.add_chain_context_subst(self.location, prefix, glyphs, suffix, [])

    def asFea(self, indent=""):
        contexts = []
        for prefix, glyphs, suffix in self.chainContexts:
            res = ""
            if len(prefix):
                res += " ".join(map(asFea, prefix)) + " "
            res += " ".join(g.asFea() + "'" for g in glyphs)
            if len(suffix):
                res += " " + " ".join(map(asFea, suffix))
            contexts.append(res)
        return "ignore sub " + ", ".join(contexts) + ";"


class IncludeStatement(Statement):
    """An ``include()`` statement."""

    def __init__(self, filename, location=None):
        super(IncludeStatement, self).__init__(location)
        self.filename = filename  #: String containing name of file to include

    def build(self):
        # TODO: consider lazy-loading the including parser/lexer?
        raise FeatureLibError(
            "Building an include statement is not implemented yet. "
            "Instead, use Parser(..., followIncludes=True) for building.",
            self.location,
        )

    def asFea(self, indent=""):
        return indent + "include(%s);" % self.filename


class LanguageStatement(Statement):
    """A ``language`` statement within a feature."""

    def __init__(self, language, include_default=True, required=False, location=None):
        Statement.__init__(self, location)
        assert len(language) == 4
        self.language = language  #: A four-character language tag
        self.include_default = include_default  #: If false, "exclude_dflt"
        self.required = required

    def build(self, builder):
        """Call the builder object's ``set_language`` callback."""
        builder.set_language(
            location=self.location,
            language=self.language,
            include_default=self.include_default,
            required=self.required,
        )

    def asFea(self, indent=""):
        res = "language {}".format(self.language.strip())
        if not self.include_default:
            res += " exclude_dflt"
        if self.required:
            res += " required"
        res += ";"
        return res


class LanguageSystemStatement(Statement):
    """A top-level ``languagesystem`` statement."""

    def __init__(self, script, language, location=None):
        Statement.__init__(self, location)
        self.script, self.language = (script, language)

    def build(self, builder):
        """Calls the builder object's ``add_language_system`` callback."""
        builder.add_language_system(self.location, self.script, self.language)

    def asFea(self, indent=""):
        return "languagesystem {} {};".format(self.script, self.language.strip())


class FontRevisionStatement(Statement):
    """A ``head`` table ``FontRevision`` statement. ``revision`` should be a
    number, and will be formatted to three significant decimal places."""

    def __init__(self, revision, location=None):
        Statement.__init__(self, location)
        self.revision = revision

    def build(self, builder):
        builder.set_font_revision(self.location, self.revision)

    def asFea(self, indent=""):
        return "FontRevision {:.3f};".format(self.revision)


class LigatureCaretByIndexStatement(Statement):
    """A ``GDEF`` table ``LigatureCaretByIndex`` statement. ``glyphs`` should be
    a `glyph-containing object`_, and ``carets`` should be a list of integers."""

    def __init__(self, glyphs, carets, location=None):
        Statement.__init__(self, location)
        self.glyphs, self.carets = (glyphs, carets)

    def build(self, builder):
        """Calls the builder object's ``add_ligatureCaretByIndex_`` callback."""
        glyphs = self.glyphs.glyphSet()
        builder.add_ligatureCaretByIndex_(self.location, glyphs, set(self.carets))

    def asFea(self, indent=""):
        return "LigatureCaretByIndex {} {};".format(
            self.glyphs.asFea(), " ".join(str(x) for x in self.carets)
        )


class LigatureCaretByPosStatement(Statement):
    """A ``GDEF`` table ``LigatureCaretByPos`` statement. ``glyphs`` should be
    a `glyph-containing object`_, and ``carets`` should be a list of integers."""

    def __init__(self, glyphs, carets, location=None):
        Statement.__init__(self, location)
        self.glyphs, self.carets = (glyphs, carets)

    def build(self, builder):
        """Calls the builder object's ``add_ligatureCaretByPos_`` callback."""
        glyphs = self.glyphs.glyphSet()
        builder.add_ligatureCaretByPos_(self.location, glyphs, set(self.carets))

    def asFea(self, indent=""):
        return "LigatureCaretByPos {} {};".format(
            self.glyphs.asFea(), " ".join(str(x) for x in self.carets)
        )


class LigatureSubstStatement(Statement):
    """A chained contextual substitution statement.

    ``prefix``, ``glyphs``, and ``suffix`` should be lists of
    `glyph-containing objects`_; ``replacement`` should be a single
    `glyph-containing object`_.

    If ``forceChain`` is True, this is expressed as a chaining rule
    (e.g. ``sub f' i' by f_i``) even when no context is given."""

    def __init__(self, prefix, glyphs, suffix, replacement, forceChain, location=None):
        Statement.__init__(self, location)
        self.prefix, self.glyphs, self.suffix = (prefix, glyphs, suffix)
        self.replacement, self.forceChain = replacement, forceChain

    def build(self, builder):
        prefix = [p.glyphSet() for p in self.prefix]
        glyphs = [g.glyphSet() for g in self.glyphs]
        suffix = [s.glyphSet() for s in self.suffix]
        builder.add_ligature_subst(
            self.location, prefix, glyphs, suffix, self.replacement, self.forceChain
        )

    def asFea(self, indent=""):
        res = "sub "
        if len(self.prefix) or len(self.suffix) or self.forceChain:
            if len(self.prefix):
                res += " ".join(g.asFea() for g in self.prefix) + " "
            res += " ".join(g.asFea() + "'" for g in self.glyphs)
            if len(self.suffix):
                res += " " + " ".join(g.asFea() for g in self.suffix)
        else:
            res += " ".join(g.asFea() for g in self.glyphs)
        res += " by "
        res += asFea(self.replacement)
        res += ";"
        return res


class LookupFlagStatement(Statement):
    """A ``lookupflag`` statement. The ``value`` should be an integer value
    representing the flags in use, but not including the ``markAttachment``
    class and ``markFilteringSet`` values, which must be specified as
    glyph-containing objects."""

    def __init__(
        self, value=0, markAttachment=None, markFilteringSet=None, location=None
    ):
        Statement.__init__(self, location)
        self.value = value
        self.markAttachment = markAttachment
        self.markFilteringSet = markFilteringSet

    def build(self, builder):
        """Calls the builder object's ``set_lookup_flag`` callback."""
        markAttach = None
        if self.markAttachment is not None:
            markAttach = self.markAttachment.glyphSet()
        markFilter = None
        if self.markFilteringSet is not None:
            markFilter = self.markFilteringSet.glyphSet()
        builder.set_lookup_flag(self.location, self.value, markAttach, markFilter)

    def asFea(self, indent=""):
        res = []
        flags = ["RightToLeft", "IgnoreBaseGlyphs", "IgnoreLigatures", "IgnoreMarks"]
        curr = 1
        for i in range(len(flags)):
            if self.value & curr != 0:
                res.append(flags[i])
            curr = curr << 1
        if self.markAttachment is not None:
            res.append("MarkAttachmentType {}".format(self.markAttachment.asFea()))
        if self.markFilteringSet is not None:
            res.append("UseMarkFilteringSet {}".format(self.markFilteringSet.asFea()))
        if not res:
            res = ["0"]
        return "lookupflag {};".format(" ".join(res))


class LookupReferenceStatement(Statement):
    """Represents a ``lookup ...;`` statement to include a lookup in a feature.

    The ``lookup`` should be a :class:`LookupBlock` object."""

    def __init__(self, lookup, location=None):
        Statement.__init__(self, location)
        self.location, self.lookup = (location, lookup)

    def build(self, builder):
        """Calls the builder object's ``add_lookup_call`` callback."""
        builder.add_lookup_call(self.lookup.name)

    def asFea(self, indent=""):
        return "lookup {};".format(self.lookup.name)


class MarkBasePosStatement(Statement):
    """A mark-to-base positioning rule. The ``base`` should be a
    `glyph-containing object`_. The ``marks`` should be a list of
    (:class:`Anchor`, :class:`MarkClass`) tuples."""

    def __init__(self, base, marks, location=None):
        Statement.__init__(self, location)
        self.base, self.marks = base, marks

    def build(self, builder):
        """Calls the builder object's ``add_mark_base_pos`` callback."""
        builder.add_mark_base_pos(self.location, self.base.glyphSet(), self.marks)

    def asFea(self, indent=""):
        res = "pos base {}".format(self.base.asFea())
        for a, m in self.marks:
            res += "\n" + indent + SHIFT + "{} mark @{}".format(a.asFea(), m.name)
        res += ";"
        return res


class MarkLigPosStatement(Statement):
    """A mark-to-ligature positioning rule. The ``ligatures`` must be a
    `glyph-containing object`_. The ``marks`` should be a list of lists: each
    element in the top-level list represents a component glyph, and is made
    up of a list of (:class:`Anchor`, :class:`MarkClass`) tuples representing
    mark attachment points for that position.

    Example::

        m1 = MarkClass("TOP_MARKS")
        m2 = MarkClass("BOTTOM_MARKS")
        # ... add definitions to mark classes...

        glyph = GlyphName("lam_meem_jeem")
        marks = [
            [ (Anchor(625,1800), m1) ], # Attachments on 1st component (lam)
            [ (Anchor(376,-378), m2) ], # Attachments on 2nd component (meem)
            [ ]                         # No attachments on the jeem
        ]
        mlp = MarkLigPosStatement(glyph, marks)

        mlp.asFea()
        # pos ligature lam_meem_jeem <anchor 625 1800> mark @TOP_MARKS
        # ligComponent <anchor 376 -378> mark @BOTTOM_MARKS;

    """

    def __init__(self, ligatures, marks, location=None):
        Statement.__init__(self, location)
        self.ligatures, self.marks = ligatures, marks

    def build(self, builder):
        """Calls the builder object's ``add_mark_lig_pos`` callback."""
        builder.add_mark_lig_pos(self.location, self.ligatures.glyphSet(), self.marks)

    def asFea(self, indent=""):
        res = "pos ligature {}".format(self.ligatures.asFea())
        ligs = []
        for l in self.marks:
            temp = ""
            if l is None or not len(l):
                temp = "\n" + indent + SHIFT * 2 + "<anchor NULL>"
            else:
                for a, m in l:
                    temp += (
                        "\n"
                        + indent
                        + SHIFT * 2
                        + "{} mark @{}".format(a.asFea(), m.name)
                    )
            ligs.append(temp)
        res += ("\n" + indent + SHIFT + "ligComponent").join(ligs)
        res += ";"
        return res


class MarkMarkPosStatement(Statement):
    """A mark-to-mark positioning rule. The ``baseMarks`` must be a
    `glyph-containing object`_. The ``marks`` should be a list of
    (:class:`Anchor`, :class:`MarkClass`) tuples."""

    def __init__(self, baseMarks, marks, location=None):
        Statement.__init__(self, location)
        self.baseMarks, self.marks = baseMarks, marks

    def build(self, builder):
        """Calls the builder object's ``add_mark_mark_pos`` callback."""
        builder.add_mark_mark_pos(self.location, self.baseMarks.glyphSet(), self.marks)

    def asFea(self, indent=""):
        res = "pos mark {}".format(self.baseMarks.asFea())
        for a, m in self.marks:
            res += "\n" + indent + SHIFT + "{} mark @{}".format(a.asFea(), m.name)
        res += ";"
        return res


class MultipleSubstStatement(Statement):
    """A multiple substitution statement.

    Args:
        prefix: a list of `glyph-containing objects`_.
        glyph: a single glyph-containing object.
        suffix: a list of glyph-containing objects.
        replacement: a list of glyph-containing objects.
        forceChain: If true, the statement is expressed as a chaining rule
            (e.g. ``sub f' i' by f_i``) even when no context is given.
    """

    def __init__(
        self, prefix, glyph, suffix, replacement, forceChain=False, location=None
    ):
        Statement.__init__(self, location)
        self.prefix, self.glyph, self.suffix = prefix, glyph, suffix
        self.replacement = replacement
        self.forceChain = forceChain

    def build(self, builder):
        """Calls the builder object's ``add_multiple_subst`` callback."""
        prefix = [p.glyphSet() for p in self.prefix]
        suffix = [s.glyphSet() for s in self.suffix]
        if hasattr(self.glyph, "glyphSet"):
            originals = self.glyph.glyphSet()
        else:
            originals = [self.glyph]
        count = len(originals)
        replaces = []
        for r in self.replacement:
            if hasattr(r, "glyphSet"):
                replace = r.glyphSet()
            else:
                replace = [r]
            if len(replace) == 1 and len(replace) != count:
                replace = replace * count
            replaces.append(replace)
        replaces = list(zip(*replaces))

        seen_originals = set()
        for i, original in enumerate(originals):
            if original not in seen_originals:
                seen_originals.add(original)
                builder.add_multiple_subst(
                    self.location,
                    prefix,
                    original,
                    suffix,
                    replaces and replaces[i] or (),
                    self.forceChain,
                )

    def asFea(self, indent=""):
        res = "sub "
        if len(self.prefix) or len(self.suffix) or self.forceChain:
            if len(self.prefix):
                res += " ".join(map(asFea, self.prefix)) + " "
            res += asFea(self.glyph) + "'"
            if len(self.suffix):
                res += " " + " ".join(map(asFea, self.suffix))
        else:
            res += asFea(self.glyph)
        replacement = self.replacement or [NullGlyph()]
        res += " by "
        res += " ".join(map(asFea, replacement))
        res += ";"
        return res


class PairPosStatement(Statement):
    """A pair positioning statement.

    ``glyphs1`` and ``glyphs2`` should be `glyph-containing objects`_.
    ``valuerecord1`` should be a :class:`ValueRecord` object;
    ``valuerecord2`` should be either a :class:`ValueRecord` object or ``None``.
    If ``enumerated`` is true, then this is expressed as an
    `enumerated pair <https://adobe-type-tools.github.io/afdko/OpenTypeFeatureFileSpecification.html#6.b.ii>`_.
    """

    def __init__(
        self,
        glyphs1,
        valuerecord1,
        glyphs2,
        valuerecord2,
        enumerated=False,
        location=None,
    ):
        Statement.__init__(self, location)
        self.enumerated = enumerated
        self.glyphs1, self.valuerecord1 = glyphs1, valuerecord1
        self.glyphs2, self.valuerecord2 = glyphs2, valuerecord2

    def build(self, builder):
        """Calls a callback on the builder object:

        * If the rule is enumerated, calls ``add_specific_pair_pos`` on each
          combination of first and second glyphs.
        * If the glyphs are both single :class:`GlyphName` objects, calls
          ``add_specific_pair_pos``.
        * Else, calls ``add_class_pair_pos``.
        """
        if self.enumerated:
            g = [self.glyphs1.glyphSet(), self.glyphs2.glyphSet()]
            seen_pair = False
            for glyph1, glyph2 in itertools.product(*g):
                seen_pair = True
                builder.add_specific_pair_pos(
                    self.location, glyph1, self.valuerecord1, glyph2, self.valuerecord2
                )
            if not seen_pair:
                raise FeatureLibError(
                    "Empty glyph class in positioning rule", self.location
                )
            return

        is_specific = isinstance(self.glyphs1, GlyphName) and isinstance(
            self.glyphs2, GlyphName
        )
        if is_specific:
            builder.add_specific_pair_pos(
                self.location,
                self.glyphs1.glyph,
                self.valuerecord1,
                self.glyphs2.glyph,
                self.valuerecord2,
            )
        else:
            builder.add_class_pair_pos(
                self.location,
                self.glyphs1.glyphSet(),
                self.valuerecord1,
                self.glyphs2.glyphSet(),
                self.valuerecord2,
            )

    def asFea(self, indent=""):
        res = "enum " if self.enumerated else ""
        if self.valuerecord2:
            res += "pos {} {} {} {};".format(
                self.glyphs1.asFea(),
                self.valuerecord1.asFea(),
                self.glyphs2.asFea(),
                self.valuerecord2.asFea(),
            )
        else:
            res += "pos {} {} {};".format(
                self.glyphs1.asFea(), self.glyphs2.asFea(), self.valuerecord1.asFea()
            )
        return res


class ReverseChainSingleSubstStatement(Statement):
    """A reverse chaining substitution statement. You don't see those every day.

    Note the unusual argument order: ``suffix`` comes `before` ``glyphs``.
    ``old_prefix``, ``old_suffix``, ``glyphs`` and ``replacements`` should be
    lists of `glyph-containing objects`_. ``glyphs`` and ``replacements`` should
    be one-item lists.
    """

    def __init__(self, old_prefix, old_suffix, glyphs, replacements, location=None):
        Statement.__init__(self, location)
        self.old_prefix, self.old_suffix = old_prefix, old_suffix
        self.glyphs = glyphs
        self.replacements = replacements

    def build(self, builder):
        prefix = [p.glyphSet() for p in self.old_prefix]
        suffix = [s.glyphSet() for s in self.old_suffix]
        originals = self.glyphs[0].glyphSet()
        replaces = self.replacements[0].glyphSet()
        if len(replaces) == 1:
            replaces = replaces * len(originals)
        builder.add_reverse_chain_single_subst(
            self.location, prefix, suffix, dict(zip(originals, replaces))
        )

    def asFea(self, indent=""):
        res = "rsub "
        if len(self.old_prefix) or len(self.old_suffix):
            if len(self.old_prefix):
                res += " ".join(asFea(g) for g in self.old_prefix) + " "
            res += " ".join(asFea(g) + "'" for g in self.glyphs)
            if len(self.old_suffix):
                res += " " + " ".join(asFea(g) for g in self.old_suffix)
        else:
            res += " ".join(map(asFea, self.glyphs))
        res += " by {};".format(" ".join(asFea(g) for g in self.replacements))
        return res


class SingleSubstStatement(Statement):
    """A single substitution statement.

    Note the unusual argument order: ``prefix`` and suffix come `after`
    the replacement ``glyphs``. ``prefix``, ``suffix``, ``glyphs`` and
    ``replace`` should be lists of `glyph-containing objects`_. ``glyphs`` and
    ``replace`` should be one-item lists.
    """

    def __init__(self, glyphs, replace, prefix, suffix, forceChain, location=None):
        Statement.__init__(self, location)
        self.prefix, self.suffix = prefix, suffix
        self.forceChain = forceChain
        self.glyphs = glyphs
        self.replacements = replace

    def build(self, builder):
        """Calls the builder object's ``add_single_subst`` callback."""
        prefix = [p.glyphSet() for p in self.prefix]
        suffix = [s.glyphSet() for s in self.suffix]
        originals = self.glyphs[0].glyphSet()
        replaces = self.replacements[0].glyphSet()
        if len(replaces) == 1:
            replaces = replaces * len(originals)
        builder.add_single_subst(
            self.location,
            prefix,
            suffix,
            OrderedDict(zip(originals, replaces)),
            self.forceChain,
        )

    def asFea(self, indent=""):
        res = "sub "
        if len(self.prefix) or len(self.suffix) or self.forceChain:
            if len(self.prefix):
                res += " ".join(asFea(g) for g in self.prefix) + " "
            res += " ".join(asFea(g) + "'" for g in self.glyphs)
            if len(self.suffix):
                res += " " + " ".join(asFea(g) for g in self.suffix)
        else:
            res += " ".join(asFea(g) for g in self.glyphs)
        res += " by {};".format(" ".join(asFea(g) for g in self.replacements))
        return res


class ScriptStatement(Statement):
    """A ``script`` statement."""

    def __init__(self, script, location=None):
        Statement.__init__(self, location)
        self.script = script  #: the script code

    def build(self, builder):
        """Calls the builder's ``set_script`` callback."""
        builder.set_script(self.location, self.script)

    def asFea(self, indent=""):
        return "script {};".format(self.script.strip())


class SinglePosStatement(Statement):
    """A single position statement. ``prefix`` and ``suffix`` should be
    lists of `glyph-containing objects`_.

    ``pos`` should be a one-element list containing a (`glyph-containing object`_,
    :class:`ValueRecord`) tuple."""

    def __init__(self, pos, prefix, suffix, forceChain, location=None):
        Statement.__init__(self, location)
        self.pos, self.prefix, self.suffix = pos, prefix, suffix
        self.forceChain = forceChain

    def build(self, builder):
        """Calls the builder object's ``add_single_pos`` callback."""
        prefix = [p.glyphSet() for p in self.prefix]
        suffix = [s.glyphSet() for s in self.suffix]
        pos = [(g.glyphSet(), value) for g, value in self.pos]
        builder.add_single_pos(self.location, prefix, suffix, pos, self.forceChain)

    def asFea(self, indent=""):
        res = "pos "
        if len(self.prefix) or len(self.suffix) or self.forceChain:
            if len(self.prefix):
                res += " ".join(map(asFea, self.prefix)) + " "
            res += " ".join(
                [
                    asFea(x[0])
                    + "'"
                    + ((" " + x[1].asFea()) if x[1] is not None else "")
                    for x in self.pos
                ]
            )
            if len(self.suffix):
                res += " " + " ".join(map(asFea, self.suffix))
        else:
            res += " ".join(
                [
                    asFea(x[0]) + " " + (x[1].asFea() if x[1] is not None else "")
                    for x in self.pos
                ]
            )
        res += ";"
        return res


class SubtableStatement(Statement):
    """Represents a subtable break."""

    def __init__(self, location=None):
        Statement.__init__(self, location)

    def build(self, builder):
        """Calls the builder objects's ``add_subtable_break`` callback."""
        builder.add_subtable_break(self.location)

    def asFea(self, indent=""):
        return "subtable;"


class ValueRecord(Expression):
    """Represents a value record."""

    def __init__(
        self,
        xPlacement=None,
        yPlacement=None,
        xAdvance=None,
        yAdvance=None,
        xPlaDevice=None,
        yPlaDevice=None,
        xAdvDevice=None,
        yAdvDevice=None,
        vertical=False,
        location=None,
    ):
        Expression.__init__(self, location)
        self.xPlacement, self.yPlacement = (xPlacement, yPlacement)
        self.xAdvance, self.yAdvance = (xAdvance, yAdvance)
        self.xPlaDevice, self.yPlaDevice = (xPlaDevice, yPlaDevice)
        self.xAdvDevice, self.yAdvDevice = (xAdvDevice, yAdvDevice)
        self.vertical = vertical

    def __eq__(self, other):
        return (
            self.xPlacement == other.xPlacement
            and self.yPlacement == other.yPlacement
            and self.xAdvance == other.xAdvance
            and self.yAdvance == other.yAdvance
            and self.xPlaDevice == other.xPlaDevice
            and self.xAdvDevice == other.xAdvDevice
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return (
            hash(self.xPlacement)
            ^ hash(self.yPlacement)
            ^ hash(self.xAdvance)
            ^ hash(self.yAdvance)
            ^ hash(self.xPlaDevice)
            ^ hash(self.yPlaDevice)
            ^ hash(self.xAdvDevice)
            ^ hash(self.yAdvDevice)
        )

    def asFea(self, indent=""):
        if not self:
            return "<NULL>"

        x, y = self.xPlacement, self.yPlacement
        xAdvance, yAdvance = self.xAdvance, self.yAdvance
        xPlaDevice, yPlaDevice = self.xPlaDevice, self.yPlaDevice
        xAdvDevice, yAdvDevice = self.xAdvDevice, self.yAdvDevice
        vertical = self.vertical

        # Try format A, if possible.
        if x is None and y is None:
            if xAdvance is None and vertical:
                return str(yAdvance)
            elif yAdvance is None and not vertical:
                return str(xAdvance)

        # Make any remaining None value 0 to avoid generating invalid records.
        x = x or 0
        y = y or 0
        xAdvance = xAdvance or 0
        yAdvance = yAdvance or 0

        # Try format B, if possible.
        if (
            xPlaDevice is None
            and yPlaDevice is None
            and xAdvDevice is None
            and yAdvDevice is None
        ):
            return "<%s %s %s %s>" % (x, y, xAdvance, yAdvance)

        # Last resort is format C.
        return "<%s %s %s %s %s %s %s %s>" % (
            x,
            y,
            xAdvance,
            yAdvance,
            deviceToString(xPlaDevice),
            deviceToString(yPlaDevice),
            deviceToString(xAdvDevice),
            deviceToString(yAdvDevice),
        )

    def __bool__(self):
        return any(
            getattr(self, v) is not None
            for v in [
                "xPlacement",
                "yPlacement",
                "xAdvance",
                "yAdvance",
                "xPlaDevice",
                "yPlaDevice",
                "xAdvDevice",
                "yAdvDevice",
            ]
        )

    __nonzero__ = __bool__


class ValueRecordDefinition(Statement):
    """Represents a named value record definition."""

    def __init__(self, name, value, location=None):
        Statement.__init__(self, location)
        self.name = name  #: Value record name as string
        self.value = value  #: :class:`ValueRecord` object

    def asFea(self, indent=""):
        return "valueRecordDef {} {};".format(self.value.asFea(), self.name)


def simplify_name_attributes(pid, eid, lid):
    if pid == 3 and eid == 1 and lid == 1033:
        return ""
    elif pid == 1 and eid == 0 and lid == 0:
        return "1"
    else:
        return "{} {} {}".format(pid, eid, lid)


class NameRecord(Statement):
    """Represents a name record. (`Section 9.e. <https://adobe-type-tools.github.io/afdko/OpenTypeFeatureFileSpecification.html#9.e>`_)"""

    def __init__(self, nameID, platformID, platEncID, langID, string, location=None):
        Statement.__init__(self, location)
        self.nameID = nameID  #: Name ID as integer (e.g. 9 for designer's name)
        self.platformID = platformID  #: Platform ID as integer
        self.platEncID = platEncID  #: Platform encoding ID as integer
        self.langID = langID  #: Language ID as integer
        self.string = string  #: Name record value

    def build(self, builder):
        """Calls the builder object's ``add_name_record`` callback."""
        builder.add_name_record(
            self.location,
            self.nameID,
            self.platformID,
            self.platEncID,
            self.langID,
            self.string,
        )

    def asFea(self, indent=""):
        def escape(c, escape_pattern):
            # Also escape U+0022 QUOTATION MARK and U+005C REVERSE SOLIDUS
            if c >= 0x20 and c <= 0x7E and c not in (0x22, 0x5C):
                return chr(c)
            else:
                return escape_pattern % c

        encoding = getEncoding(self.platformID, self.platEncID, self.langID)
        if encoding is None:
            raise FeatureLibError("Unsupported encoding", self.location)
        s = tobytes(self.string, encoding=encoding)
        if encoding == "utf_16_be":
            escaped_string = "".join(
                [
                    escape(byteord(s[i]) * 256 + byteord(s[i + 1]), r"\%04x")
                    for i in range(0, len(s), 2)
                ]
            )
        else:
            escaped_string = "".join([escape(byteord(b), r"\%02x") for b in s])
        plat = simplify_name_attributes(self.platformID, self.platEncID, self.langID)
        if plat != "":
            plat += " "
        return 'nameid {} {}"{}";'.format(self.nameID, plat, escaped_string)


class FeatureNameStatement(NameRecord):
    """Represents a ``sizemenuname`` or ``name`` statement."""

    def build(self, builder):
        """Calls the builder object's ``add_featureName`` callback."""
        NameRecord.build(self, builder)
        builder.add_featureName(self.nameID)

    def asFea(self, indent=""):
        if self.nameID == "size":
            tag = "sizemenuname"
        else:
            tag = "name"
        plat = simplify_name_attributes(self.platformID, self.platEncID, self.langID)
        if plat != "":
            plat += " "
        return '{} {}"{}";'.format(tag, plat, self.string)


class STATNameStatement(NameRecord):
    """Represents a STAT table ``name`` statement."""

    def asFea(self, indent=""):
        plat = simplify_name_attributes(self.platformID, self.platEncID, self.langID)
        if plat != "":
            plat += " "
        return 'name {}"{}";'.format(plat, self.string)


class SizeParameters(Statement):
    """A ``parameters`` statement."""

    def __init__(self, DesignSize, SubfamilyID, RangeStart, RangeEnd, location=None):
        Statement.__init__(self, location)
        self.DesignSize = DesignSize
        self.SubfamilyID = SubfamilyID
        self.RangeStart = RangeStart
        self.RangeEnd = RangeEnd

    def build(self, builder):
        """Calls the builder object's ``set_size_parameters`` callback."""
        builder.set_size_parameters(
            self.location,
            self.DesignSize,
            self.SubfamilyID,
            self.RangeStart,
            self.RangeEnd,
        )

    def asFea(self, indent=""):
        res = "parameters {:.1f} {}".format(self.DesignSize, self.SubfamilyID)
        if self.RangeStart != 0 or self.RangeEnd != 0:
            res += " {} {}".format(int(self.RangeStart * 10), int(self.RangeEnd * 10))
        return res + ";"


class CVParametersNameStatement(NameRecord):
    """Represent a name statement inside a ``cvParameters`` block."""

    def __init__(
        self, nameID, platformID, platEncID, langID, string, block_name, location=None
    ):
        NameRecord.__init__(
            self, nameID, platformID, platEncID, langID, string, location=location
        )
        self.block_name = block_name

    def build(self, builder):
        """Calls the builder object's ``add_cv_parameter`` callback."""
        item = ""
        if self.block_name == "ParamUILabelNameID":
            item = "_{}".format(builder.cv_num_named_params_.get(self.nameID, 0))
        builder.add_cv_parameter(self.nameID)
        self.nameID = (self.nameID, self.block_name + item)
        NameRecord.build(self, builder)

    def asFea(self, indent=""):
        plat = simplify_name_attributes(self.platformID, self.platEncID, self.langID)
        if plat != "":
            plat += " "
        return 'name {}"{}";'.format(plat, self.string)


class CharacterStatement(Statement):
    """
    Statement used in cvParameters blocks of Character Variant features (cvXX).
    The Unicode value may be written with either decimal or hexadecimal
    notation. The value must be preceded by '0x' if it is a hexadecimal value.
    The largest Unicode value allowed is 0xFFFFFF.
    """

    def __init__(self, character, tag, location=None):
        Statement.__init__(self, location)
        self.character = character
        self.tag = tag

    def build(self, builder):
        """Calls the builder object's ``add_cv_character`` callback."""
        builder.add_cv_character(self.character, self.tag)

    def asFea(self, indent=""):
        return "Character {:#x};".format(self.character)


class BaseAxis(Statement):
    """An axis definition, being either a ``VertAxis.BaseTagList/BaseScriptList``
    pair or a ``HorizAxis.BaseTagList/BaseScriptList`` pair."""

    def __init__(self, bases, scripts, vertical, minmax=None, location=None):
        Statement.__init__(self, location)
        self.bases = bases  #: A list of baseline tag names as strings
        self.scripts = scripts  #: A list of script record tuplets (script tag, default baseline tag, base coordinate)
        self.vertical = vertical  #: Boolean; VertAxis if True, HorizAxis if False
        self.minmax = []  #: A set of minmax record

    def build(self, builder):
        """Calls the builder object's ``set_base_axis`` callback."""
        builder.set_base_axis(self.bases, self.scripts, self.vertical, self.minmax)

    def asFea(self, indent=""):
        direction = "Vert" if self.vertical else "Horiz"
        scripts = [
            "{} {} {}".format(a[0], a[1], " ".join(map(str, a[2])))
            for a in self.scripts
        ]
        minmaxes = [
            "\n{}Axis.MinMax {} {} {}, {};".format(direction, a[0], a[1], a[2], a[3])
            for a in self.minmax
        ]
        return "{}Axis.BaseTagList {};\n{}{}Axis.BaseScriptList {};".format(
            direction, " ".join(self.bases), indent, direction, ", ".join(scripts)
        ) + "\n".join(minmaxes)


class OS2Field(Statement):
    """An entry in the ``OS/2`` table. Most ``values`` should be numbers or
    strings, apart from when the key is ``UnicodeRange``, ``CodePageRange``
    or ``Panose``, in which case it should be an array of integers."""

    def __init__(self, key, value, location=None):
        Statement.__init__(self, location)
        self.key = key
        self.value = value

    def build(self, builder):
        """Calls the builder object's ``add_os2_field`` callback."""
        builder.add_os2_field(self.key, self.value)

    def asFea(self, indent=""):
        def intarr2str(x):
            return " ".join(map(str, x))

        numbers = (
            "FSType",
            "TypoAscender",
            "TypoDescender",
            "TypoLineGap",
            "winAscent",
            "winDescent",
            "XHeight",
            "CapHeight",
            "WeightClass",
            "WidthClass",
            "LowerOpSize",
            "UpperOpSize",
        )
        ranges = ("UnicodeRange", "CodePageRange")
        keywords = dict([(x.lower(), [x, str]) for x in numbers])
        keywords.update([(x.lower(), [x, intarr2str]) for x in ranges])
        keywords["panose"] = ["Panose", intarr2str]
        keywords["vendor"] = ["Vendor", lambda y: '"{}"'.format(y)]
        if self.key in keywords:
            return "{} {};".format(
                keywords[self.key][0], keywords[self.key][1](self.value)
            )
        return ""  # should raise exception


class HheaField(Statement):
    """An entry in the ``hhea`` table."""

    def __init__(self, key, value, location=None):
        Statement.__init__(self, location)
        self.key = key
        self.value = value

    def build(self, builder):
        """Calls the builder object's ``add_hhea_field`` callback."""
        builder.add_hhea_field(self.key, self.value)

    def asFea(self, indent=""):
        fields = ("CaretOffset", "Ascender", "Descender", "LineGap")
        keywords = dict([(x.lower(), x) for x in fields])
        return "{} {};".format(keywords[self.key], self.value)


class VheaField(Statement):
    """An entry in the ``vhea`` table."""

    def __init__(self, key, value, location=None):
        Statement.__init__(self, location)
        self.key = key
        self.value = value

    def build(self, builder):
        """Calls the builder object's ``add_vhea_field`` callback."""
        builder.add_vhea_field(self.key, self.value)

    def asFea(self, indent=""):
        fields = ("VertTypoAscender", "VertTypoDescender", "VertTypoLineGap")
        keywords = dict([(x.lower(), x) for x in fields])
        return "{} {};".format(keywords[self.key], self.value)


class STATDesignAxisStatement(Statement):
    """A STAT table Design Axis

    Args:
        tag (str): a 4 letter axis tag
        axisOrder (int): an int
        names (list): a list of :class:`STATNameStatement` objects
    """

    def __init__(self, tag, axisOrder, names, location=None):
        Statement.__init__(self, location)
        self.tag = tag
        self.axisOrder = axisOrder
        self.names = names
        self.location = location

    def build(self, builder):
        builder.addDesignAxis(self, self.location)

    def asFea(self, indent=""):
        indent += SHIFT
        res = f"DesignAxis {self.tag} {self.axisOrder} {{ \n"
        res += ("\n" + indent).join([s.asFea(indent=indent) for s in self.names]) + "\n"
        res += "};"
        return res


class ElidedFallbackName(Statement):
    """STAT table ElidedFallbackName

    Args:
        names: a list of :class:`STATNameStatement` objects
    """

    def __init__(self, names, location=None):
        Statement.__init__(self, location)
        self.names = names
        self.location = location

    def build(self, builder):
        builder.setElidedFallbackName(self.names, self.location)

    def asFea(self, indent=""):
        indent += SHIFT
        res = "ElidedFallbackName { \n"
        res += ("\n" + indent).join([s.asFea(indent=indent) for s in self.names]) + "\n"
        res += "};"
        return res


class ElidedFallbackNameID(Statement):
    """STAT table ElidedFallbackNameID

    Args:
        value: an int pointing to an existing name table name ID
    """

    def __init__(self, value, location=None):
        Statement.__init__(self, location)
        self.value = value
        self.location = location

    def build(self, builder):
        builder.setElidedFallbackName(self.value, self.location)

    def asFea(self, indent=""):
        return f"ElidedFallbackNameID {self.value};"


class STATAxisValueStatement(Statement):
    """A STAT table Axis Value Record

    Args:
        names (list): a list of :class:`STATNameStatement` objects
        locations (list): a list of :class:`AxisValueLocationStatement` objects
        flags (int): an int
    """

    def __init__(self, names, locations, flags, location=None):
        Statement.__init__(self, location)
        self.names = names
        self.locations = locations
        self.flags = flags

    def build(self, builder):
        builder.addAxisValueRecord(self, self.location)

    def asFea(self, indent=""):
        res = "AxisValue {\n"
        for location in self.locations:
            res += location.asFea()

        for nameRecord in self.names:
            res += nameRecord.asFea()
            res += "\n"

        if self.flags:
            flags = ["OlderSiblingFontAttribute", "ElidableAxisValueName"]
            flagStrings = []
            curr = 1
            for i in range(len(flags)):
                if self.flags & curr != 0:
                    flagStrings.append(flags[i])
                curr = curr << 1
            res += f"flag {' '.join(flagStrings)};\n"
        res += "};"
        return res


class AxisValueLocationStatement(Statement):
    """
    A STAT table Axis Value Location

    Args:
        tag (str): a 4 letter axis tag
        values (list): a list of ints and/or floats
    """

    def __init__(self, tag, values, location=None):
        Statement.__init__(self, location)
        self.tag = tag
        self.values = values

    def asFea(self, res=""):
        res += f"location {self.tag} "
        res += f"{' '.join(str(i) for i in self.values)};\n"
        return res


class ConditionsetStatement(Statement):
    """
    A variable layout conditionset

    Args:
        name (str): the name of this conditionset
        conditions (dict): a dictionary mapping axis tags to a
            tuple of (min,max) userspace coordinates.
    """

    def __init__(self, name, conditions, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.conditions = conditions

    def build(self, builder):
        builder.add_conditionset(self.location, self.name, self.conditions)

    def asFea(self, res="", indent=""):
        res += indent + f"conditionset {self.name} " + "{\n"
        for tag, (minvalue, maxvalue) in self.conditions.items():
            res += indent + SHIFT + f"{tag} {minvalue} {maxvalue};\n"
        res += indent + "}" + f" {self.name};\n"
        return res


class VariationBlock(Block):
    """A variation feature block, applicable in a given set of conditions."""

    def __init__(self, name, conditionset, use_extension=False, location=None):
        Block.__init__(self, location)
        self.name, self.conditionset, self.use_extension = (
            name,
            conditionset,
            use_extension,
        )

    def build(self, builder):
        """Call the ``start_feature`` callback on the builder object, visit
        all the statements in this feature, and then call ``end_feature``."""
        builder.start_feature(self.location, self.name, self.use_extension)
        if (
            self.conditionset != "NULL"
            and self.conditionset not in builder.conditionsets_
        ):
            raise FeatureLibError(
                f"variation block used undefined conditionset {self.conditionset}",
                self.location,
            )

        # language exclude_dflt statements modify builder.features_
        # limit them to this block with temporary builder.features_
        features = builder.features_
        builder.features_ = {}
        Block.build(self, builder)
        for key, value in builder.features_.items():
            items = builder.feature_variations_.setdefault(key, {}).setdefault(
                self.conditionset, []
            )
            items.extend(value)
            if key not in features:
                features[key] = []  # Ensure we make a feature record
        builder.features_ = features
        builder.end_feature()

    def asFea(self, indent=""):
        res = indent + "variation %s " % self.name.strip()
        res += self.conditionset + " "
        if self.use_extension:
            res += "useExtension "
        res += "{\n"
        res += Block.asFea(self, indent=indent)
        res += indent + "} %s;\n" % self.name.strip()
        return res
