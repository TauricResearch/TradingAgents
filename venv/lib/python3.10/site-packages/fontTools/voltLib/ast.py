from fontTools.voltLib.error import VoltLibError
from typing import NamedTuple


class Pos(NamedTuple):
    adv: int
    dx: int
    dy: int
    adv_adjust_by: dict
    dx_adjust_by: dict
    dy_adjust_by: dict

    def __str__(self):
        res = " POS"
        for attr in ("adv", "dx", "dy"):
            value = getattr(self, attr)
            if value is not None:
                res += f" {attr.upper()} {value}"
                adjust_by = getattr(self, f"{attr}_adjust_by", {})
                for size, adjustment in adjust_by.items():
                    res += f" ADJUST_BY {adjustment} AT {size}"
        res += " END_POS"
        return res


class Element(object):
    def __init__(self, location=None):
        self.location = location

    def build(self, builder):
        pass

    def __str__(self):
        raise NotImplementedError


class Statement(Element):
    pass


class Expression(Element):
    pass


class VoltFile(Statement):
    def __init__(self):
        Statement.__init__(self, location=None)
        self.statements = []

    def build(self, builder):
        for s in self.statements:
            s.build(builder)

    def __str__(self):
        return "\n" + "\n".join(str(s) for s in self.statements) + " END\n"


class GlyphDefinition(Statement):
    def __init__(self, name, gid, gunicode, gtype, components, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.id = gid
        self.unicode = gunicode
        self.type = gtype
        self.components = components

    def __str__(self):
        res = f'DEF_GLYPH "{self.name}" ID {self.id}'
        if self.unicode is not None:
            if len(self.unicode) > 1:
                unicodes = ",".join(f"U+{u:04X}" for u in self.unicode)
                res += f' UNICODEVALUES "{unicodes}"'
            else:
                res += f" UNICODE {self.unicode[0]}"
        if self.type is not None:
            res += f" TYPE {self.type}"
        if self.components is not None:
            res += f" COMPONENTS {self.components}"
        res += " END_GLYPH"
        return res


class GroupDefinition(Statement):
    def __init__(self, name, enum, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.enum = enum
        self.glyphs_ = None

    def glyphSet(self, groups=None):
        if groups is not None and self.name in groups:
            raise VoltLibError(
                'Group "%s" contains itself.' % (self.name), self.location
            )
        if self.glyphs_ is None:
            if groups is None:
                groups = set({self.name})
            else:
                groups.add(self.name)
            self.glyphs_ = self.enum.glyphSet(groups)
        return self.glyphs_

    def __str__(self):
        enum = self.enum and str(self.enum) or ""
        return f'DEF_GROUP "{self.name}"\n{enum}\nEND_GROUP'


class GlyphName(Expression):
    """A single glyph name, such as cedilla."""

    def __init__(self, glyph, location=None):
        Expression.__init__(self, location)
        self.glyph = glyph

    def glyphSet(self):
        return (self.glyph,)

    def __str__(self):
        return f' GLYPH "{self.glyph}"'


class Enum(Expression):
    """An enum"""

    def __init__(self, enum, location=None):
        Expression.__init__(self, location)
        self.enum = enum

    def __iter__(self):
        for e in self.glyphSet():
            yield e

    def glyphSet(self, groups=None):
        glyphs = []
        for element in self.enum:
            if isinstance(element, (GroupName, Enum)):
                glyphs.extend(element.glyphSet(groups))
            else:
                glyphs.extend(element.glyphSet())
        return tuple(glyphs)

    def __str__(self):
        enum = "".join(str(e) for e in self.enum)
        return f" ENUM{enum} END_ENUM"


class GroupName(Expression):
    """A glyph group"""

    def __init__(self, group, parser, location=None):
        Expression.__init__(self, location)
        self.group = group
        self.parser_ = parser

    def glyphSet(self, groups=None):
        group = self.parser_.resolve_group(self.group)
        if group is not None:
            self.glyphs_ = group.glyphSet(groups)
            return self.glyphs_
        else:
            raise VoltLibError(
                'Group "%s" is used but undefined.' % (self.group), self.location
            )

    def __str__(self):
        return f' GROUP "{self.group}"'


class Range(Expression):
    """A glyph range"""

    def __init__(self, start, end, parser, location=None):
        Expression.__init__(self, location)
        self.start = start
        self.end = end
        self.parser = parser

    def glyphSet(self):
        return tuple(self.parser.glyph_range(self.start, self.end))

    def __str__(self):
        return f' RANGE "{self.start}" TO "{self.end}"'


class ScriptDefinition(Statement):
    def __init__(self, name, tag, langs, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.tag = tag
        self.langs = langs

    def __str__(self):
        res = "DEF_SCRIPT"
        if self.name is not None:
            res += f' NAME "{self.name}"'
        res += f' TAG "{self.tag}"\n\n'
        for lang in self.langs:
            res += f"{lang}"
        res += "END_SCRIPT"
        return res


class LangSysDefinition(Statement):
    def __init__(self, name, tag, features, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.tag = tag
        self.features = features

    def __str__(self):
        res = "DEF_LANGSYS"
        if self.name is not None:
            res += f' NAME "{self.name}"'
        res += f' TAG "{self.tag}"\n\n'
        for feature in self.features:
            res += f"{feature}"
        res += "END_LANGSYS\n"
        return res


class FeatureDefinition(Statement):
    def __init__(self, name, tag, lookups, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.tag = tag
        self.lookups = lookups

    def __str__(self):
        res = f'DEF_FEATURE NAME "{self.name}" TAG "{self.tag}"\n'
        res += " " + " ".join(f'LOOKUP "{l}"' for l in self.lookups) + "\n"
        res += "END_FEATURE\n"
        return res


class LookupDefinition(Statement):
    def __init__(
        self,
        name,
        process_base,
        process_marks,
        mark_glyph_set,
        direction,
        reversal,
        comments,
        context,
        sub,
        pos,
        location=None,
    ):
        Statement.__init__(self, location)
        self.name = name
        self.process_base = process_base
        self.process_marks = process_marks
        self.mark_glyph_set = mark_glyph_set
        self.direction = direction
        self.reversal = reversal
        self.comments = comments
        self.context = context
        self.sub = sub
        self.pos = pos

    def __str__(self):
        res = f'DEF_LOOKUP "{self.name}"'
        res += f' {self.process_base and "PROCESS_BASE" or "SKIP_BASE"}'
        if self.process_marks:
            res += " PROCESS_MARKS "
            if self.mark_glyph_set:
                res += f'MARK_GLYPH_SET "{self.mark_glyph_set}"'
            elif isinstance(self.process_marks, str):
                res += f'"{self.process_marks}"'
            else:
                res += "ALL"
        else:
            res += " SKIP_MARKS"
        if self.direction is not None:
            res += f" DIRECTION {self.direction}"
        if self.reversal:
            res += " REVERSAL"
        if self.comments is not None:
            comments = self.comments.replace("\n", r"\n")
            res += f'\nCOMMENTS "{comments}"'
        if self.context:
            res += "\n" + "\n".join(str(c) for c in self.context)
        else:
            res += "\nIN_CONTEXT\nEND_CONTEXT"
        if self.sub:
            res += f"\n{self.sub}"
        if self.pos:
            res += f"\n{self.pos}"
        return res


class SubstitutionDefinition(Statement):
    def __init__(self, mapping, location=None):
        Statement.__init__(self, location)
        self.mapping = mapping

    def __str__(self):
        res = "AS_SUBSTITUTION\n"
        for src, dst in self.mapping.items():
            src = "".join(str(s) for s in src)
            dst = "".join(str(d) for d in dst)
            res += f"SUB{src}\nWITH{dst}\nEND_SUB\n"
        res += "END_SUBSTITUTION"
        return res


class SubstitutionSingleDefinition(SubstitutionDefinition):
    pass


class SubstitutionMultipleDefinition(SubstitutionDefinition):
    pass


class SubstitutionLigatureDefinition(SubstitutionDefinition):
    pass


class SubstitutionAlternateDefinition(SubstitutionDefinition):
    pass


class SubstitutionReverseChainingSingleDefinition(SubstitutionDefinition):
    pass


class PositionAttachDefinition(Statement):
    def __init__(self, coverage, coverage_to, location=None):
        Statement.__init__(self, location)
        self.coverage = coverage
        self.coverage_to = coverage_to

    def __str__(self):
        coverage = "".join(str(c) for c in self.coverage)
        res = f"AS_POSITION\nATTACH{coverage}\nTO"
        for coverage, anchor in self.coverage_to:
            coverage = "".join(str(c) for c in coverage)
            res += f'{coverage} AT ANCHOR "{anchor}"'
        res += "\nEND_ATTACH\nEND_POSITION"
        return res


class PositionAttachCursiveDefinition(Statement):
    def __init__(self, coverages_exit, coverages_enter, location=None):
        Statement.__init__(self, location)
        self.coverages_exit = coverages_exit
        self.coverages_enter = coverages_enter

    def __str__(self):
        res = "AS_POSITION\nATTACH_CURSIVE"
        for coverage in self.coverages_exit:
            coverage = "".join(str(c) for c in coverage)
            res += f"\nEXIT {coverage}"
        for coverage in self.coverages_enter:
            coverage = "".join(str(c) for c in coverage)
            res += f"\nENTER {coverage}"
        res += "\nEND_ATTACH\nEND_POSITION"
        return res


class PositionAdjustPairDefinition(Statement):
    def __init__(self, coverages_1, coverages_2, adjust_pair, location=None):
        Statement.__init__(self, location)
        self.coverages_1 = coverages_1
        self.coverages_2 = coverages_2
        self.adjust_pair = adjust_pair

    def __str__(self):
        res = "AS_POSITION\nADJUST_PAIR\n"
        for coverage in self.coverages_1:
            coverage = " ".join(str(c) for c in coverage)
            res += f" FIRST {coverage}"
        res += "\n"
        for coverage in self.coverages_2:
            coverage = " ".join(str(c) for c in coverage)
            res += f" SECOND {coverage}"
        res += "\n"
        for (id_1, id_2), (pos_1, pos_2) in self.adjust_pair.items():
            res += f" {id_1} {id_2} BY{pos_1}{pos_2}\n"
        res += "\nEND_ADJUST\nEND_POSITION"
        return res


class PositionAdjustSingleDefinition(Statement):
    def __init__(self, adjust_single, location=None):
        Statement.__init__(self, location)
        self.adjust_single = adjust_single

    def __str__(self):
        res = "AS_POSITION\nADJUST_SINGLE"
        for coverage, pos in self.adjust_single:
            coverage = "".join(str(c) for c in coverage)
            res += f"{coverage} BY{pos}"
        res += "\nEND_ADJUST\nEND_POSITION"
        return res


class ContextDefinition(Statement):
    def __init__(self, ex_or_in, left=None, right=None, location=None):
        Statement.__init__(self, location)
        self.ex_or_in = ex_or_in
        self.left = left if left is not None else []
        self.right = right if right is not None else []

    def __str__(self):
        res = self.ex_or_in + "\n"
        for coverage in self.left:
            coverage = "".join(str(c) for c in coverage)
            res += f" LEFT{coverage}\n"
        for coverage in self.right:
            coverage = "".join(str(c) for c in coverage)
            res += f" RIGHT{coverage}\n"
        res += "END_CONTEXT"
        return res


class AnchorDefinition(Statement):
    def __init__(self, name, gid, glyph_name, component, locked, pos, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.gid = gid
        self.glyph_name = glyph_name
        self.component = component
        self.locked = locked
        self.pos = pos

    def __str__(self):
        locked = self.locked and " LOCKED" or ""
        return (
            f'DEF_ANCHOR "{self.name}"'
            f" ON {self.gid}"
            f" GLYPH {self.glyph_name}"
            f" COMPONENT {self.component}"
            f"{locked}"
            f" AT {self.pos} END_ANCHOR"
        )


class SettingDefinition(Statement):
    def __init__(self, name, value, location=None):
        Statement.__init__(self, location)
        self.name = name
        self.value = value

    def __str__(self):
        if self.value is True:
            return f"{self.name}"
        if isinstance(self.value, (tuple, list)):
            value = " ".join(str(v) for v in self.value)
            return f"{self.name} {value}"
        return f"{self.name} {self.value}"
