from fontTools.misc import sstruct
from fontTools.misc.textTools import Tag, tostr, binary2num, safeEval
from fontTools.feaLib.error import FeatureLibError
from fontTools.feaLib.lookupDebugInfo import (
    LookupDebugInfo,
    LOOKUP_DEBUG_INFO_KEY,
    LOOKUP_DEBUG_ENV_VAR,
)
from fontTools.feaLib.parser import Parser
from fontTools.feaLib.ast import FeatureFile
from fontTools.feaLib.variableScalar import VariableScalar
from fontTools.otlLib import builder as otl
from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.ttLib import newTable, getTableModule
from fontTools.ttLib.tables import otBase, otTables
from fontTools.otlLib.builder import (
    AlternateSubstBuilder,
    ChainContextPosBuilder,
    ChainContextSubstBuilder,
    LigatureSubstBuilder,
    MultipleSubstBuilder,
    CursivePosBuilder,
    MarkBasePosBuilder,
    MarkLigPosBuilder,
    MarkMarkPosBuilder,
    ReverseChainSingleSubstBuilder,
    SingleSubstBuilder,
    ClassPairPosSubtableBuilder,
    PairPosBuilder,
    SinglePosBuilder,
    ChainContextualRule,
    AnySubstBuilder,
)
from fontTools.otlLib.error import OpenTypeLibError
from fontTools.varLib.errors import VarLibError
from fontTools.varLib.varStore import OnlineVarStoreBuilder
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.featureVars import addFeatureVariationsRaw
from fontTools.varLib.models import normalizeValue, piecewiseLinearMap
from collections import defaultdict
import copy
import itertools
from io import StringIO
import logging
import warnings
import os


log = logging.getLogger(__name__)


def addOpenTypeFeatures(font, featurefile, tables=None, debug=False):
    """Add features from a file to a font. Note that this replaces any features
    currently present.

    Args:
        font (feaLib.ttLib.TTFont): The font object.
        featurefile: Either a path or file object (in which case we
            parse it into an AST), or a pre-parsed AST instance.
        tables: If passed, restrict the set of affected tables to those in the
            list.
        debug: Whether to add source debugging information to the font in the
            ``Debg`` table

    """
    builder = Builder(font, featurefile)
    builder.build(tables=tables, debug=debug)


def addOpenTypeFeaturesFromString(
    font, features, filename=None, tables=None, debug=False
):
    """Add features from a string to a font. Note that this replaces any
    features currently present.

    Args:
        font (feaLib.ttLib.TTFont): The font object.
        features: A string containing feature code.
        filename: The directory containing ``filename`` is used as the root of
            relative ``include()`` paths; if ``None`` is provided, the current
            directory is assumed.
        tables: If passed, restrict the set of affected tables to those in the
            list.
        debug: Whether to add source debugging information to the font in the
            ``Debg`` table

    """

    featurefile = StringIO(tostr(features))
    if filename:
        featurefile.name = filename
    addOpenTypeFeatures(font, featurefile, tables=tables, debug=debug)


class Builder(object):
    supportedTables = frozenset(
        Tag(tag)
        for tag in [
            "BASE",
            "GDEF",
            "GPOS",
            "GSUB",
            "OS/2",
            "head",
            "hhea",
            "name",
            "vhea",
            "STAT",
        ]
    )

    def __init__(self, font, featurefile):
        self.font = font
        # 'featurefile' can be either a path or file object (in which case we
        # parse it into an AST), or a pre-parsed AST instance
        if isinstance(featurefile, FeatureFile):
            self.parseTree, self.file = featurefile, None
        else:
            self.parseTree, self.file = None, featurefile
        self.glyphMap = font.getReverseGlyphMap()
        self.varstorebuilder = None
        if "fvar" in font:
            self.axes = font["fvar"].axes
            self.varstorebuilder = OnlineVarStoreBuilder(
                [ax.axisTag for ax in self.axes]
            )
        self.default_language_systems_ = set()
        self.script_ = None
        self.lookupflag_ = 0
        self.lookupflag_markFilterSet_ = None
        self.use_extension_ = False
        self.language_systems = set()
        self.seen_non_DFLT_script_ = False
        self.named_lookups_ = {}
        self.cur_lookup_ = None
        self.cur_lookup_name_ = None
        self.cur_feature_name_ = None
        self.lookups_ = []
        self.lookup_locations = {"GSUB": {}, "GPOS": {}}
        self.features_ = {}  # ('latn', 'DEU ', 'smcp') --> [LookupBuilder*]
        self.required_features_ = {}  # ('latn', 'DEU ') --> 'scmp'
        self.feature_variations_ = {}
        # for feature 'aalt'
        self.aalt_features_ = []  # [(location, featureName)*], for 'aalt'
        self.aalt_location_ = None
        self.aalt_alternates_ = {}
        self.aalt_use_extension_ = False
        # for 'featureNames'
        self.featureNames_ = set()
        self.featureNames_ids_ = {}
        # for 'cvParameters'
        self.cv_parameters_ = set()
        self.cv_parameters_ids_ = {}
        self.cv_num_named_params_ = {}
        self.cv_characters_ = defaultdict(list)
        # for feature 'size'
        self.size_parameters_ = None
        # for table 'head'
        self.fontRevision_ = None  # 2.71
        # for table 'name'
        self.names_ = []
        # for table 'BASE'
        self.base_horiz_axis_ = None
        self.base_vert_axis_ = None
        # for table 'GDEF'
        self.attachPoints_ = {}  # "a" --> {3, 7}
        self.ligCaretCoords_ = {}  # "f_f_i" --> {300, 600}
        self.ligCaretPoints_ = {}  # "f_f_i" --> {3, 7}
        self.glyphClassDefs_ = {}  # "fi" --> (2, (file, line, column))
        self.markAttach_ = {}  # "acute" --> (4, (file, line, column))
        self.markAttachClassID_ = {}  # frozenset({"acute", "grave"}) --> 4
        self.markFilterSets_ = {}  # frozenset({"acute", "grave"}) --> 4
        # for table 'OS/2'
        self.os2_ = {}
        # for table 'hhea'
        self.hhea_ = {}
        # for table 'vhea'
        self.vhea_ = {}
        # for table 'STAT'
        self.stat_ = {}
        # for conditionsets
        self.conditionsets_ = {}
        # We will often use exactly the same locations (i.e. the font's masters)
        # for a large number of variable scalars. Instead of creating a model
        # for each, let's share the models.
        self.model_cache = {}

    def build(self, tables=None, debug=False):
        if self.parseTree is None:
            self.parseTree = Parser(self.file, self.glyphMap).parse()
        self.parseTree.build(self)
        # by default, build all the supported tables
        if tables is None:
            tables = self.supportedTables
        else:
            tables = frozenset(tables)
            unsupported = tables - self.supportedTables
            if unsupported:
                unsupported_string = ", ".join(sorted(unsupported))
                raise NotImplementedError(
                    "The following tables were requested but are unsupported: "
                    f"{unsupported_string}."
                )
        if "GSUB" in tables:
            self.build_feature_aalt_()
        if "head" in tables:
            self.build_head()
        if "hhea" in tables:
            self.build_hhea()
        if "vhea" in tables:
            self.build_vhea()
        if "name" in tables:
            self.build_name()
        if "OS/2" in tables:
            self.build_OS_2()
        if "STAT" in tables:
            self.build_STAT()
        for tag in ("GPOS", "GSUB"):
            if tag not in tables:
                continue
            table = self.makeTable(tag)
            if self.feature_variations_:
                self.makeFeatureVariations(table, tag)
            if (
                table.ScriptList.ScriptCount > 0
                or table.FeatureList.FeatureCount > 0
                or table.LookupList.LookupCount > 0
            ):
                fontTable = self.font[tag] = newTable(tag)
                fontTable.table = table
            elif tag in self.font:
                del self.font[tag]
        if any(tag in self.font for tag in ("GPOS", "GSUB")) and "OS/2" in self.font:
            self.font["OS/2"].usMaxContext = maxCtxFont(self.font)
        if "GDEF" in tables:
            gdef = self.buildGDEF()
            if gdef:
                self.font["GDEF"] = gdef
            elif "GDEF" in self.font:
                del self.font["GDEF"]
        if "BASE" in tables:
            base = self.buildBASE()
            if base:
                self.font["BASE"] = base
            elif "BASE" in self.font:
                del self.font["BASE"]
        if debug or os.environ.get(LOOKUP_DEBUG_ENV_VAR):
            self.buildDebg()

    def get_chained_lookup_(self, location, builder_class):
        result = builder_class(self.font, location)
        result.lookupflag = self.lookupflag_
        result.markFilterSet = self.lookupflag_markFilterSet_
        result.extension = self.use_extension_
        self.lookups_.append(result)
        return result

    def add_lookup_to_feature_(self, lookup, feature_name):
        for script, lang in self.language_systems:
            key = (script, lang, feature_name)
            self.features_.setdefault(key, []).append(lookup)

    def get_lookup_(self, location, builder_class, mapping=None):
        if (
            self.cur_lookup_
            and type(self.cur_lookup_) == builder_class
            and self.cur_lookup_.lookupflag == self.lookupflag_
            and self.cur_lookup_.markFilterSet == self.lookupflag_markFilterSet_
            and self.cur_lookup_.can_add_mapping(mapping)
        ):
            return self.cur_lookup_
        if self.cur_lookup_name_ and self.cur_lookup_:
            raise FeatureLibError(
                "Within a named lookup block, all rules must be of "
                "the same lookup type and flag",
                location,
            )
        self.cur_lookup_ = builder_class(self.font, location)
        self.cur_lookup_.lookupflag = self.lookupflag_
        self.cur_lookup_.markFilterSet = self.lookupflag_markFilterSet_
        self.cur_lookup_.extension = self.use_extension_
        self.lookups_.append(self.cur_lookup_)
        if self.cur_lookup_name_:
            # We are starting a lookup rule inside a named lookup block.
            self.named_lookups_[self.cur_lookup_name_] = self.cur_lookup_
        if self.cur_feature_name_:
            # We are starting a lookup rule inside a feature. This includes
            # lookup rules inside named lookups inside features.
            self.add_lookup_to_feature_(self.cur_lookup_, self.cur_feature_name_)
        return self.cur_lookup_

    def build_feature_aalt_(self):
        if not self.aalt_features_ and not self.aalt_alternates_:
            return
        # > alternate glyphs will be sorted in the order that the source features
        # > are named in the aalt definition, not the order of the feature definitions
        # > in the file. Alternates defined explicitly ... will precede all others.
        # https://github.com/fonttools/fonttools/issues/836
        alternates = {g: list(a) for g, a in self.aalt_alternates_.items()}
        for location, name in self.aalt_features_ + [(None, "aalt")]:
            feature = [
                (script, lang, feature, lookups)
                for (script, lang, feature), lookups in self.features_.items()
                if feature == name
            ]
            # "aalt" does not have to specify its own lookups, but it might.
            if not feature and name != "aalt":
                warnings.warn("%s: Feature %s has not been defined" % (location, name))
                continue
            for script, lang, feature, lookups in feature:
                for lookuplist in lookups:
                    if not isinstance(lookuplist, list):
                        lookuplist = [lookuplist]
                    for lookup in lookuplist:
                        for glyph, alts in lookup.getAlternateGlyphs().items():
                            alts_for_glyph = alternates.setdefault(glyph, [])
                            alts_for_glyph.extend(
                                g for g in alts if g not in alts_for_glyph
                            )
        single = {
            glyph: repl[0] for glyph, repl in alternates.items() if len(repl) == 1
        }
        multi = {glyph: repl for glyph, repl in alternates.items() if len(repl) > 1}
        if not single and not multi:
            return
        self.features_ = {
            (script, lang, feature): lookups
            for (script, lang, feature), lookups in self.features_.items()
            if feature != "aalt"
        }
        old_lookups = self.lookups_
        self.lookups_ = []
        self.start_feature(self.aalt_location_, "aalt", self.aalt_use_extension_)
        if single:
            single_lookup = self.get_lookup_(location, SingleSubstBuilder)
            single_lookup.mapping = single
        if multi:
            multi_lookup = self.get_lookup_(location, AlternateSubstBuilder)
            multi_lookup.alternates = multi
        self.end_feature()
        self.lookups_.extend(old_lookups)

    def build_head(self):
        if not self.fontRevision_:
            return
        table = self.font.get("head")
        if not table:  # this only happens for unit tests
            table = self.font["head"] = newTable("head")
            table.decompile(b"\0" * 54, self.font)
            table.tableVersion = 1.0
            table.magicNumber = 0x5F0F3CF5
            table.created = table.modified = 3406620153  # 2011-12-13 11:22:33
        table.fontRevision = self.fontRevision_

    def build_hhea(self):
        if not self.hhea_:
            return
        table = self.font.get("hhea")
        if not table:  # this only happens for unit tests
            table = self.font["hhea"] = newTable("hhea")
            table.decompile(b"\0" * 36, self.font)
            table.tableVersion = 0x00010000
        if "caretoffset" in self.hhea_:
            table.caretOffset = self.hhea_["caretoffset"]
        if "ascender" in self.hhea_:
            table.ascent = self.hhea_["ascender"]
        if "descender" in self.hhea_:
            table.descent = self.hhea_["descender"]
        if "linegap" in self.hhea_:
            table.lineGap = self.hhea_["linegap"]

    def build_vhea(self):
        if not self.vhea_:
            return
        table = self.font.get("vhea")
        if not table:  # this only happens for unit tests
            table = self.font["vhea"] = newTable("vhea")
            table.decompile(b"\0" * 36, self.font)
            table.tableVersion = 0x00011000
        if "verttypoascender" in self.vhea_:
            table.ascent = self.vhea_["verttypoascender"]
        if "verttypodescender" in self.vhea_:
            table.descent = self.vhea_["verttypodescender"]
        if "verttypolinegap" in self.vhea_:
            table.lineGap = self.vhea_["verttypolinegap"]

    def get_user_name_id(self, table):
        # Try to find first unused font-specific name id
        nameIDs = [name.nameID for name in table.names]
        for user_name_id in range(256, 32767):
            if user_name_id not in nameIDs:
                return user_name_id

    def buildFeatureParams(self, tag):
        params = None
        if tag == "size":
            params = otTables.FeatureParamsSize()
            (
                params.DesignSize,
                params.SubfamilyID,
                params.RangeStart,
                params.RangeEnd,
            ) = self.size_parameters_
            if tag in self.featureNames_ids_:
                params.SubfamilyNameID = self.featureNames_ids_[tag]
            else:
                params.SubfamilyNameID = 0
        elif tag in self.featureNames_:
            if not self.featureNames_ids_:
                # name table wasn't selected among the tables to build; skip
                pass
            else:
                assert tag in self.featureNames_ids_
                params = otTables.FeatureParamsStylisticSet()
                params.Version = 0
                params.UINameID = self.featureNames_ids_[tag]
        elif tag in self.cv_parameters_:
            params = otTables.FeatureParamsCharacterVariants()
            params.Format = 0
            params.FeatUILabelNameID = self.cv_parameters_ids_.get(
                (tag, "FeatUILabelNameID"), 0
            )
            params.FeatUITooltipTextNameID = self.cv_parameters_ids_.get(
                (tag, "FeatUITooltipTextNameID"), 0
            )
            params.SampleTextNameID = self.cv_parameters_ids_.get(
                (tag, "SampleTextNameID"), 0
            )
            params.NumNamedParameters = self.cv_num_named_params_.get(tag, 0)
            params.FirstParamUILabelNameID = self.cv_parameters_ids_.get(
                (tag, "ParamUILabelNameID_0"), 0
            )
            params.CharCount = len(self.cv_characters_[tag])
            params.Character = self.cv_characters_[tag]
        return params

    def build_name(self):
        if not self.names_:
            return
        table = self.font.get("name")
        if not table:  # this only happens for unit tests
            table = self.font["name"] = newTable("name")
            table.names = []
        for name in self.names_:
            nameID, platformID, platEncID, langID, string = name
            # For featureNames block, nameID is 'feature tag'
            # For cvParameters blocks, nameID is ('feature tag', 'block name')
            if not isinstance(nameID, int):
                tag = nameID
                if tag in self.featureNames_:
                    if tag not in self.featureNames_ids_:
                        self.featureNames_ids_[tag] = self.get_user_name_id(table)
                        assert self.featureNames_ids_[tag] is not None
                    nameID = self.featureNames_ids_[tag]
                elif tag[0] in self.cv_parameters_:
                    if tag not in self.cv_parameters_ids_:
                        self.cv_parameters_ids_[tag] = self.get_user_name_id(table)
                        assert self.cv_parameters_ids_[tag] is not None
                    nameID = self.cv_parameters_ids_[tag]
            table.setName(string, nameID, platformID, platEncID, langID)
        table.names.sort()

    def build_OS_2(self):
        if not self.os2_:
            return
        table = self.font.get("OS/2")
        if not table:  # this only happens for unit tests
            table = self.font["OS/2"] = newTable("OS/2")
            data = b"\0" * sstruct.calcsize(getTableModule("OS/2").OS2_format_0)
            table.decompile(data, self.font)
        version = 0
        if "fstype" in self.os2_:
            table.fsType = self.os2_["fstype"]
        if "panose" in self.os2_:
            panose = getTableModule("OS/2").Panose()
            (
                panose.bFamilyType,
                panose.bSerifStyle,
                panose.bWeight,
                panose.bProportion,
                panose.bContrast,
                panose.bStrokeVariation,
                panose.bArmStyle,
                panose.bLetterForm,
                panose.bMidline,
                panose.bXHeight,
            ) = self.os2_["panose"]
            table.panose = panose
        if "typoascender" in self.os2_:
            table.sTypoAscender = self.os2_["typoascender"]
        if "typodescender" in self.os2_:
            table.sTypoDescender = self.os2_["typodescender"]
        if "typolinegap" in self.os2_:
            table.sTypoLineGap = self.os2_["typolinegap"]
        if "winascent" in self.os2_:
            table.usWinAscent = self.os2_["winascent"]
        if "windescent" in self.os2_:
            table.usWinDescent = self.os2_["windescent"]
        if "vendor" in self.os2_:
            table.achVendID = safeEval("'''" + self.os2_["vendor"] + "'''")
        if "weightclass" in self.os2_:
            table.usWeightClass = self.os2_["weightclass"]
        if "widthclass" in self.os2_:
            table.usWidthClass = self.os2_["widthclass"]
        if "unicoderange" in self.os2_:
            table.setUnicodeRanges(self.os2_["unicoderange"])
        if "codepagerange" in self.os2_:
            pages = self.build_codepages_(self.os2_["codepagerange"])
            table.ulCodePageRange1, table.ulCodePageRange2 = pages
            version = 1
        if "xheight" in self.os2_:
            table.sxHeight = self.os2_["xheight"]
            version = 2
        if "capheight" in self.os2_:
            table.sCapHeight = self.os2_["capheight"]
            version = 2
        if "loweropsize" in self.os2_:
            table.usLowerOpticalPointSize = self.os2_["loweropsize"]
            version = 5
        if "upperopsize" in self.os2_:
            table.usUpperOpticalPointSize = self.os2_["upperopsize"]
            version = 5

        def checkattr(table, attrs):
            for attr in attrs:
                if not hasattr(table, attr):
                    setattr(table, attr, 0)

        table.version = max(version, table.version)
        # this only happens for unit tests
        if version >= 1:
            checkattr(table, ("ulCodePageRange1", "ulCodePageRange2"))
        if version >= 2:
            checkattr(
                table,
                (
                    "sxHeight",
                    "sCapHeight",
                    "usDefaultChar",
                    "usBreakChar",
                    "usMaxContext",
                ),
            )
        if version >= 5:
            checkattr(table, ("usLowerOpticalPointSize", "usUpperOpticalPointSize"))

    def setElidedFallbackName(self, value, location):
        # ElidedFallbackName is a convenience method for setting
        # ElidedFallbackNameID so only one can be allowed
        for token in ("ElidedFallbackName", "ElidedFallbackNameID"):
            if token in self.stat_:
                raise FeatureLibError(
                    f"{token} is already set.",
                    location,
                )
        if isinstance(value, int):
            self.stat_["ElidedFallbackNameID"] = value
        elif isinstance(value, list):
            self.stat_["ElidedFallbackName"] = value
        else:
            raise AssertionError(value)

    def addDesignAxis(self, designAxis, location):
        if "DesignAxes" not in self.stat_:
            self.stat_["DesignAxes"] = []
        if designAxis.tag in (r.tag for r in self.stat_["DesignAxes"]):
            raise FeatureLibError(
                f'DesignAxis already defined for tag "{designAxis.tag}".',
                location,
            )
        if designAxis.axisOrder in (r.axisOrder for r in self.stat_["DesignAxes"]):
            raise FeatureLibError(
                f"DesignAxis already defined for axis number {designAxis.axisOrder}.",
                location,
            )
        self.stat_["DesignAxes"].append(designAxis)

    def addAxisValueRecord(self, axisValueRecord, location):
        if "AxisValueRecords" not in self.stat_:
            self.stat_["AxisValueRecords"] = []
        # Check for duplicate AxisValueRecords
        for record_ in self.stat_["AxisValueRecords"]:
            if (
                {n.asFea() for n in record_.names}
                == {n.asFea() for n in axisValueRecord.names}
                and {n.asFea() for n in record_.locations}
                == {n.asFea() for n in axisValueRecord.locations}
                and record_.flags == axisValueRecord.flags
            ):
                raise FeatureLibError(
                    "An AxisValueRecord with these values is already defined.",
                    location,
                )
        self.stat_["AxisValueRecords"].append(axisValueRecord)

    def build_STAT(self):
        if not self.stat_:
            return

        axes = self.stat_.get("DesignAxes")
        if not axes:
            raise FeatureLibError("DesignAxes not defined", None)
        axisValueRecords = self.stat_.get("AxisValueRecords")
        axisValues = {}
        format4_locations = []
        for tag in axes:
            axisValues[tag.tag] = []
        if axisValueRecords is not None:
            for avr in axisValueRecords:
                valuesDict = {}
                if avr.flags > 0:
                    valuesDict["flags"] = avr.flags
                if len(avr.locations) == 1:
                    location = avr.locations[0]
                    values = location.values
                    if len(values) == 1:  # format1
                        valuesDict.update({"value": values[0], "name": avr.names})
                    if len(values) == 2:  # format3
                        valuesDict.update(
                            {
                                "value": values[0],
                                "linkedValue": values[1],
                                "name": avr.names,
                            }
                        )
                    if len(values) == 3:  # format2
                        nominal, minVal, maxVal = values
                        valuesDict.update(
                            {
                                "nominalValue": nominal,
                                "rangeMinValue": minVal,
                                "rangeMaxValue": maxVal,
                                "name": avr.names,
                            }
                        )
                    axisValues[location.tag].append(valuesDict)
                else:
                    valuesDict.update(
                        {
                            "location": {i.tag: i.values[0] for i in avr.locations},
                            "name": avr.names,
                        }
                    )
                    format4_locations.append(valuesDict)

        designAxes = [
            {
                "ordering": a.axisOrder,
                "tag": a.tag,
                "name": a.names,
                "values": axisValues[a.tag],
            }
            for a in axes
        ]

        nameTable = self.font.get("name")
        if not nameTable:  # this only happens for unit tests
            nameTable = self.font["name"] = newTable("name")
            nameTable.names = []

        if "ElidedFallbackNameID" in self.stat_:
            nameID = self.stat_["ElidedFallbackNameID"]
            name = nameTable.getDebugName(nameID)
            if not name:
                raise FeatureLibError(
                    f"ElidedFallbackNameID {nameID} points "
                    "to a nameID that does not exist in the "
                    '"name" table',
                    None,
                )
        elif "ElidedFallbackName" in self.stat_:
            nameID = self.stat_["ElidedFallbackName"]

        otl.buildStatTable(
            self.font,
            designAxes,
            locations=format4_locations,
            elidedFallbackName=nameID,
        )

    def build_codepages_(self, pages):
        pages2bits = {
            1252: 0,
            1250: 1,
            1251: 2,
            1253: 3,
            1254: 4,
            1255: 5,
            1256: 6,
            1257: 7,
            1258: 8,
            874: 16,
            932: 17,
            936: 18,
            949: 19,
            950: 20,
            1361: 21,
            869: 48,
            866: 49,
            865: 50,
            864: 51,
            863: 52,
            862: 53,
            861: 54,
            860: 55,
            857: 56,
            855: 57,
            852: 58,
            775: 59,
            737: 60,
            708: 61,
            850: 62,
            437: 63,
        }
        bits = [pages2bits[p] for p in pages if p in pages2bits]
        pages = []
        for i in range(2):
            pages.append("")
            for j in range(i * 32, (i + 1) * 32):
                if j in bits:
                    pages[i] += "1"
                else:
                    pages[i] += "0"
        return [binary2num(p[::-1]) for p in pages]

    def buildBASE(self):
        if not self.base_horiz_axis_ and not self.base_vert_axis_:
            return None
        base = otTables.BASE()
        base.Version = 0x00010000
        base.HorizAxis = self.buildBASEAxis(self.base_horiz_axis_)
        base.VertAxis = self.buildBASEAxis(self.base_vert_axis_)

        result = newTable("BASE")
        result.table = base
        return result

    def buildBASECoord(self, c):
        coord = otTables.BaseCoord()
        coord.Format = 1
        coord.Coordinate = c
        return coord

    def buildBASEAxis(self, axis):
        if not axis:
            return
        bases, scripts, minmax = axis
        axis = otTables.Axis()
        axis.BaseTagList = otTables.BaseTagList()
        axis.BaseTagList.BaselineTag = bases
        axis.BaseTagList.BaseTagCount = len(bases)
        axis.BaseScriptList = otTables.BaseScriptList()
        axis.BaseScriptList.BaseScriptRecord = []
        axis.BaseScriptList.BaseScriptCount = len(scripts)
        for script in sorted(scripts):
            minmax_for_script = [
                record[1:] for record in minmax if record[0] == script[0]
            ]
            record = otTables.BaseScriptRecord()
            record.BaseScriptTag = script[0]
            record.BaseScript = otTables.BaseScript()
            record.BaseScript.BaseValues = otTables.BaseValues()
            record.BaseScript.BaseValues.DefaultIndex = bases.index(script[1])
            record.BaseScript.BaseValues.BaseCoord = []
            record.BaseScript.BaseValues.BaseCoordCount = len(script[2])
            record.BaseScript.BaseLangSysRecord = []

            for c in script[2]:
                record.BaseScript.BaseValues.BaseCoord.append(self.buildBASECoord(c))
            for language, min_coord, max_coord in minmax_for_script:
                minmax_record = otTables.MinMax()
                minmax_record.MinCoord = self.buildBASECoord(min_coord)
                minmax_record.MaxCoord = self.buildBASECoord(max_coord)
                minmax_record.FeatMinMaxCount = 0
                if language == "dflt":
                    record.BaseScript.DefaultMinMax = minmax_record
                else:
                    lang_record = otTables.BaseLangSysRecord()
                    lang_record.BaseLangSysTag = language
                    lang_record.MinMax = minmax_record
                    record.BaseScript.BaseLangSysRecord.append(lang_record)
            record.BaseScript.BaseLangSysCount = len(
                record.BaseScript.BaseLangSysRecord
            )
            axis.BaseScriptList.BaseScriptRecord.append(record)
        return axis

    def buildGDEF(self):
        gdef = otTables.GDEF()
        gdef.GlyphClassDef = self.buildGDEFGlyphClassDef_()
        gdef.AttachList = otl.buildAttachList(self.attachPoints_, self.glyphMap)
        gdef.LigCaretList = otl.buildLigCaretList(
            self.ligCaretCoords_, self.ligCaretPoints_, self.glyphMap
        )
        gdef.MarkAttachClassDef = self.buildGDEFMarkAttachClassDef_()
        gdef.MarkGlyphSetsDef = self.buildGDEFMarkGlyphSetsDef_()
        gdef.Version = 0x00010002 if gdef.MarkGlyphSetsDef else 0x00010000
        if self.varstorebuilder:
            store = self.varstorebuilder.finish()
            if store:
                gdef.Version = 0x00010003
                gdef.VarStore = store
                varidx_map = store.optimize()

                gdef.remap_device_varidxes(varidx_map)
                if "GPOS" in self.font:
                    self.font["GPOS"].table.remap_device_varidxes(varidx_map)
            self.model_cache.clear()
        if any(
            (
                gdef.GlyphClassDef,
                gdef.AttachList,
                gdef.LigCaretList,
                gdef.MarkAttachClassDef,
                gdef.MarkGlyphSetsDef,
            )
        ) or hasattr(gdef, "VarStore"):
            result = newTable("GDEF")
            result.table = gdef
            return result
        else:
            return None

    def buildGDEFGlyphClassDef_(self):
        if self.glyphClassDefs_:
            classes = {g: c for (g, (c, _)) in self.glyphClassDefs_.items()}
        else:
            classes = {}
            for lookup in self.lookups_:
                classes.update(lookup.inferGlyphClasses())
            for markClass in self.parseTree.markClasses.values():
                for markClassDef in markClass.definitions:
                    for glyph in markClassDef.glyphSet():
                        classes[glyph] = 3
        if classes:
            result = otTables.GlyphClassDef()
            result.classDefs = classes
            return result
        else:
            return None

    def buildGDEFMarkAttachClassDef_(self):
        classDefs = {g: c for g, (c, _) in self.markAttach_.items()}
        if not classDefs:
            return None
        result = otTables.MarkAttachClassDef()
        result.classDefs = classDefs
        return result

    def buildGDEFMarkGlyphSetsDef_(self):
        sets = []
        for glyphs, id_ in sorted(
            self.markFilterSets_.items(), key=lambda item: item[1]
        ):
            sets.append(glyphs)
        return otl.buildMarkGlyphSetsDef(sets, self.glyphMap)

    def buildDebg(self):
        if "Debg" not in self.font:
            self.font["Debg"] = newTable("Debg")
            self.font["Debg"].data = {}
        self.font["Debg"].data[LOOKUP_DEBUG_INFO_KEY] = self.lookup_locations

    def buildLookups_(self, tag):
        assert tag in ("GPOS", "GSUB"), tag
        for lookup in self.lookups_:
            lookup.lookup_index = None
        lookups = []
        for lookup in self.lookups_:
            if lookup.table != tag:
                continue
            name = self.get_lookup_name_(lookup)
            resolved = lookup.promote_lookup_type(is_named_lookup=name is not None)
            if resolved is None:
                raise FeatureLibError(
                    "Within a named lookup block, all rules must be of "
                    "the same lookup type and flag",
                    lookup.location,
                )
            for l in resolved:
                lookup.lookup_index = len(lookups)
                self.lookup_locations[tag][str(lookup.lookup_index)] = LookupDebugInfo(
                    location=str(lookup.location),
                    name=name,
                    feature=None,
                )
                lookups.append(l)
        otLookups = []
        for l in lookups:
            try:
                otLookups.append(l.build())
            except OpenTypeLibError as e:
                raise FeatureLibError(str(e), e.location) from e
            except Exception as e:
                location = self.lookup_locations[tag][str(l.lookup_index)].location
                raise FeatureLibError(str(e), location) from e
        return otLookups

    def makeTable(self, tag):
        table = getattr(otTables, tag, None)()
        table.Version = 0x00010000
        table.ScriptList = otTables.ScriptList()
        table.ScriptList.ScriptRecord = []
        table.FeatureList = otTables.FeatureList()
        table.FeatureList.FeatureRecord = []
        table.LookupList = otTables.LookupList()
        table.LookupList.Lookup = self.buildLookups_(tag)

        # Build a table for mapping (tag, lookup_indices) to feature_index.
        # For example, ('liga', (2,3,7)) --> 23.
        feature_indices = {}
        required_feature_indices = {}  # ('latn', 'DEU') --> 23
        scripts = {}  # 'latn' --> {'DEU': [23, 24]} for feature #23,24
        # Sort the feature table by feature tag:
        # https://github.com/fonttools/fonttools/issues/568
        sortFeatureTag = lambda f: (f[0][2], f[0][1], f[0][0], f[1])
        for key, lookups in sorted(self.features_.items(), key=sortFeatureTag):
            script, lang, feature_tag = key
            # l.lookup_index will be None when a lookup is not needed
            # for the table under construction. For example, substitution
            # rules will have no lookup_index while building GPOS tables.
            # We also deduplicate lookup indices, as they only get applied once
            # within a given feature:
            # https://github.com/fonttools/fonttools/issues/2946
            lookup_indices = tuple(
                dict.fromkeys(
                    l.lookup_index for l in lookups if l.lookup_index is not None
                )
            )
            # order doesn't matter, but lookup_indices preserves it.
            # We want to combine identical sets of lookups (order doesn't matter)
            # but also respect the order provided by the user (although there's
            # a reasonable argument to just sort and dedupe, which fontc does)
            lookup_key = frozenset(lookup_indices)

            size_feature = tag == "GPOS" and feature_tag == "size"
            force_feature = self.any_feature_variations(feature_tag, tag)
            if len(lookup_indices) == 0 and not size_feature and not force_feature:
                continue

            for ix in lookup_indices:
                try:
                    self.lookup_locations[tag][str(ix)] = self.lookup_locations[tag][
                        str(ix)
                    ]._replace(feature=key)
                except KeyError:
                    warnings.warn(
                        "feaLib.Builder subclass needs upgrading to "
                        "stash debug information. See fonttools#2065."
                    )

            feature_key = (feature_tag, lookup_key)
            feature_index = feature_indices.get(feature_key)
            if feature_index is None:
                feature_index = len(table.FeatureList.FeatureRecord)
                frec = otTables.FeatureRecord()
                frec.FeatureTag = feature_tag
                frec.Feature = otTables.Feature()
                frec.Feature.FeatureParams = self.buildFeatureParams(feature_tag)
                frec.Feature.LookupListIndex = list(lookup_indices)
                frec.Feature.LookupCount = len(lookup_indices)
                table.FeatureList.FeatureRecord.append(frec)
                feature_indices[feature_key] = feature_index
            scripts.setdefault(script, {}).setdefault(lang, []).append(feature_index)
            if self.required_features_.get((script, lang)) == feature_tag:
                required_feature_indices[(script, lang)] = feature_index

        # Build ScriptList.
        for script, lang_features in sorted(scripts.items()):
            srec = otTables.ScriptRecord()
            srec.ScriptTag = script
            srec.Script = otTables.Script()
            srec.Script.DefaultLangSys = None
            srec.Script.LangSysRecord = []
            for lang, feature_indices in sorted(lang_features.items()):
                langrec = otTables.LangSysRecord()
                langrec.LangSys = otTables.LangSys()
                langrec.LangSys.LookupOrder = None

                req_feature_index = required_feature_indices.get((script, lang))
                if req_feature_index is None:
                    langrec.LangSys.ReqFeatureIndex = 0xFFFF
                else:
                    langrec.LangSys.ReqFeatureIndex = req_feature_index

                langrec.LangSys.FeatureIndex = [
                    i for i in feature_indices if i != req_feature_index
                ]
                langrec.LangSys.FeatureCount = len(langrec.LangSys.FeatureIndex)

                if lang == "dflt":
                    srec.Script.DefaultLangSys = langrec.LangSys
                else:
                    langrec.LangSysTag = lang
                    srec.Script.LangSysRecord.append(langrec)
            srec.Script.LangSysCount = len(srec.Script.LangSysRecord)
            table.ScriptList.ScriptRecord.append(srec)

        table.ScriptList.ScriptCount = len(table.ScriptList.ScriptRecord)
        table.FeatureList.FeatureCount = len(table.FeatureList.FeatureRecord)
        table.LookupList.LookupCount = len(table.LookupList.Lookup)
        return table

    def makeFeatureVariations(self, table, table_tag):
        feature_vars = {}
        has_any_variations = False
        # Sort out which lookups to build, gather their indices
        for (_, _, feature_tag), variations in self.feature_variations_.items():
            feature_vars[feature_tag] = []
            for conditionset, builders in variations.items():
                raw_conditionset = self.conditionsets_[conditionset]
                indices = []
                for b in builders:
                    if b.table != table_tag:
                        continue
                    assert b.lookup_index is not None
                    indices.append(b.lookup_index)
                    has_any_variations = True
                feature_vars[feature_tag].append((raw_conditionset, indices))

        if has_any_variations:
            for feature_tag, conditions_and_lookups in feature_vars.items():
                addFeatureVariationsRaw(
                    self.font, table, conditions_and_lookups, feature_tag
                )

    def any_feature_variations(self, feature_tag, table_tag):
        for (_, _, feature), variations in self.feature_variations_.items():
            if feature != feature_tag:
                continue
            for conditionset, builders in variations.items():
                if any(b.table == table_tag for b in builders):
                    return True
        return False

    def get_lookup_name_(self, lookup):
        rev = {v: k for k, v in self.named_lookups_.items()}
        if lookup in rev:
            return rev[lookup]
        return None

    def add_language_system(self, location, script, language):
        # OpenType Feature File Specification, section 4.b.i
        if script == "DFLT" and language == "dflt" and self.default_language_systems_:
            raise FeatureLibError(
                'If "languagesystem DFLT dflt" is present, it must be '
                "the first of the languagesystem statements",
                location,
            )
        if script == "DFLT":
            if self.seen_non_DFLT_script_:
                raise FeatureLibError(
                    'languagesystems using the "DFLT" script tag must '
                    "precede all other languagesystems",
                    location,
                )
        else:
            self.seen_non_DFLT_script_ = True
        if (script, language) in self.default_language_systems_:
            raise FeatureLibError(
                '"languagesystem %s %s" has already been specified'
                % (script.strip(), language.strip()),
                location,
            )
        self.default_language_systems_.add((script, language))

    def get_default_language_systems_(self):
        # OpenType Feature File specification, 4.b.i. languagesystem:
        # If no "languagesystem" statement is present, then the
        # implementation must behave exactly as though the following
        # statement were present at the beginning of the feature file:
        # languagesystem DFLT dflt;
        if self.default_language_systems_:
            return frozenset(self.default_language_systems_)
        else:
            return frozenset({("DFLT", "dflt")})

    def start_feature(self, location, name, use_extension=False):
        if use_extension and name != "aalt":
            raise FeatureLibError(
                "'useExtension' keyword for feature blocks is allowed only for 'aalt' feature",
                location,
            )
        self.language_systems = self.get_default_language_systems_()
        self.script_ = "DFLT"
        self.cur_lookup_ = None
        self.cur_feature_name_ = name
        self.lookupflag_ = 0
        self.lookupflag_markFilterSet_ = None
        self.use_extension_ = use_extension
        if name == "aalt":
            self.aalt_location_ = location
            self.aalt_use_extension_ = use_extension

    def end_feature(self):
        assert self.cur_feature_name_ is not None
        self.cur_feature_name_ = None
        self.language_systems = None
        self.cur_lookup_ = None
        self.lookupflag_ = 0
        self.lookupflag_markFilterSet_ = None
        self.use_extension_ = False

    def start_lookup_block(self, location, name, use_extension=False):
        if name in self.named_lookups_:
            raise FeatureLibError(
                'Lookup "%s" has already been defined' % name, location
            )
        if self.cur_feature_name_ == "aalt":
            raise FeatureLibError(
                "Lookup blocks cannot be placed inside 'aalt' features; "
                "move it out, and then refer to it with a lookup statement",
                location,
            )
        self.cur_lookup_name_ = name
        self.named_lookups_[name] = None
        self.cur_lookup_ = None
        self.use_extension_ = use_extension
        if self.cur_feature_name_ is None:
            self.lookupflag_ = 0
            self.lookupflag_markFilterSet_ = None

    def end_lookup_block(self):
        assert self.cur_lookup_name_ is not None
        self.cur_lookup_name_ = None
        self.cur_lookup_ = None
        self.use_extension_ = False
        if self.cur_feature_name_ is None:
            self.lookupflag_ = 0
            self.lookupflag_markFilterSet_ = None

    def add_lookup_call(self, lookup_name):
        assert lookup_name in self.named_lookups_, lookup_name
        self.cur_lookup_ = None
        lookup = self.named_lookups_[lookup_name]
        if lookup is not None:  # skip empty named lookup
            self.add_lookup_to_feature_(lookup, self.cur_feature_name_)

    def set_font_revision(self, location, revision):
        self.fontRevision_ = revision

    def set_language(self, location, language, include_default, required):
        assert len(language) == 4
        if self.cur_feature_name_ in ("aalt", "size"):
            raise FeatureLibError(
                "Language statements are not allowed "
                'within "feature %s"' % self.cur_feature_name_,
                location,
            )
        if self.cur_feature_name_ is None:
            raise FeatureLibError(
                "Language statements are not allowed "
                "within standalone lookup blocks",
                location,
            )
        self.cur_lookup_ = None

        key = (self.script_, language, self.cur_feature_name_)
        lookups = self.features_.get((key[0], "dflt", key[2]))
        if (language == "dflt" or include_default) and lookups:
            self.features_[key] = lookups[:]
        else:
            # if we aren't including default we need to manually remove the
            # default lookups, which were added to all declared langsystems
            # as they were encountered (we don't remove all lookups because
            # we want to allow duplicate script/lang statements;
            # see https://github.com/fonttools/fonttools/issues/3748
            cur_lookups = self.features_.get(key, [])
            self.features_[key] = [x for x in cur_lookups if x not in lookups]
        self.language_systems = frozenset([(self.script_, language)])

        if required:
            key = (self.script_, language)
            if key in self.required_features_:
                raise FeatureLibError(
                    "Language %s (script %s) has already "
                    "specified feature %s as its required feature"
                    % (
                        language.strip(),
                        self.script_.strip(),
                        self.required_features_[key].strip(),
                    ),
                    location,
                )
            self.required_features_[key] = self.cur_feature_name_

    def getMarkAttachClass_(self, location, glyphs):
        glyphs = frozenset(glyphs)
        id_ = self.markAttachClassID_.get(glyphs)
        if id_ is not None:
            return id_
        id_ = len(self.markAttachClassID_) + 1
        self.markAttachClassID_[glyphs] = id_
        for glyph in glyphs:
            if glyph in self.markAttach_:
                _, loc = self.markAttach_[glyph]
                raise FeatureLibError(
                    "Glyph %s already has been assigned "
                    "a MarkAttachmentType at %s" % (glyph, loc),
                    location,
                )
            self.markAttach_[glyph] = (id_, location)
        return id_

    def getMarkFilterSet_(self, location, glyphs):
        glyphs = frozenset(glyphs)
        id_ = self.markFilterSets_.get(glyphs)
        if id_ is not None:
            return id_
        id_ = len(self.markFilterSets_)
        self.markFilterSets_[glyphs] = id_
        return id_

    def set_lookup_flag(self, location, value, markAttach, markFilter):
        value = value & 0xFF
        if markAttach is not None:
            markAttachClass = self.getMarkAttachClass_(location, markAttach)
            value = value | (markAttachClass << 8)
        if markFilter is not None:
            markFilterSet = self.getMarkFilterSet_(location, markFilter)
            value = value | 0x10
            self.lookupflag_markFilterSet_ = markFilterSet
        else:
            self.lookupflag_markFilterSet_ = None
        self.lookupflag_ = value

    def set_script(self, location, script):
        if self.cur_feature_name_ in ("aalt", "size"):
            raise FeatureLibError(
                "Script statements are not allowed "
                'within "feature %s"' % self.cur_feature_name_,
                location,
            )
        if self.cur_feature_name_ is None:
            raise FeatureLibError(
                "Script statements are not allowed " "within standalone lookup blocks",
                location,
            )
        if self.language_systems == {(script, "dflt")}:
            # Nothing to do.
            return
        self.cur_lookup_ = None
        self.script_ = script
        self.lookupflag_ = 0
        self.lookupflag_markFilterSet_ = None
        self.set_language(location, "dflt", include_default=True, required=False)

    def find_lookup_builders_(self, lookups):
        """Helper for building chain contextual substitutions

        Given a list of lookup names, finds the LookupBuilder for each name.
        If an input name is None, it gets mapped to a None LookupBuilder.
        """
        lookup_builders = []
        for lookuplist in lookups:
            if lookuplist is not None:
                lookup_builders.append(
                    [self.named_lookups_.get(l.name) for l in lookuplist]
                )
            else:
                lookup_builders.append(None)
        return lookup_builders

    def add_attach_points(self, location, glyphs, contourPoints):
        for glyph in glyphs:
            self.attachPoints_.setdefault(glyph, set()).update(contourPoints)

    def add_feature_reference(self, location, featureName):
        if self.cur_feature_name_ != "aalt":
            raise FeatureLibError(
                'Feature references are only allowed inside "feature aalt"', location
            )
        self.aalt_features_.append((location, featureName))

    def add_featureName(self, tag):
        self.featureNames_.add(tag)

    def add_cv_parameter(self, tag):
        self.cv_parameters_.add(tag)

    def add_to_cv_num_named_params(self, tag):
        """Adds new items to ``self.cv_num_named_params_``
        or increments the count of existing items."""
        if tag in self.cv_num_named_params_:
            self.cv_num_named_params_[tag] += 1
        else:
            self.cv_num_named_params_[tag] = 1

    def add_cv_character(self, character, tag):
        self.cv_characters_[tag].append(character)

    def set_base_axis(self, bases, scripts, vertical, minmax=[]):
        if vertical:
            self.base_vert_axis_ = (bases, scripts, minmax)
        else:
            self.base_horiz_axis_ = (bases, scripts, minmax)

    def set_size_parameters(
        self, location, DesignSize, SubfamilyID, RangeStart, RangeEnd
    ):
        if self.cur_feature_name_ != "size":
            raise FeatureLibError(
                "Parameters statements are not allowed "
                'within "feature %s"' % self.cur_feature_name_,
                location,
            )
        self.size_parameters_ = [DesignSize, SubfamilyID, RangeStart, RangeEnd]
        for script, lang in self.language_systems:
            key = (script, lang, self.cur_feature_name_)
            self.features_.setdefault(key, [])

    # GSUB rules

    def add_any_subst_(self, location, mapping):
        lookup = self.get_lookup_(location, AnySubstBuilder, mapping=mapping)
        for key, value in mapping.items():
            if key in lookup.mapping:
                if value == lookup.mapping[key]:
                    log.info(
                        'Removing duplicate substitution from "%s" to "%s" at %s',
                        ", ".join(key),
                        ", ".join(value),
                        location,
                    )
                else:
                    raise FeatureLibError(
                        'Already defined substitution for "%s"' % ", ".join(key),
                        location,
                    )
            lookup.mapping[key] = value

    # GSUB 1
    def add_single_subst(self, location, prefix, suffix, mapping, forceChain):
        if self.cur_feature_name_ == "aalt":
            for from_glyph, to_glyph in mapping.items():
                alts = self.aalt_alternates_.setdefault(from_glyph, [])
                if to_glyph not in alts:
                    alts.append(to_glyph)
            return
        if prefix or suffix or forceChain:
            self.add_single_subst_chained_(location, prefix, suffix, mapping)
            return

        self.add_any_subst_(
            location,
            {(key,): (value,) for key, value in mapping.items()},
        )

    # GSUB 2
    def add_multiple_subst(
        self, location, prefix, glyph, suffix, replacements, forceChain=False
    ):
        if prefix or suffix or forceChain:
            self.add_multi_subst_chained_(location, prefix, glyph, suffix, replacements)
            return
        self.add_any_subst_(
            location,
            {(glyph,): tuple(replacements)},
        )

    # GSUB 3
    def add_alternate_subst(self, location, prefix, glyph, suffix, replacement):
        if self.cur_feature_name_ == "aalt":
            alts = self.aalt_alternates_.setdefault(glyph, [])
            alts.extend(g for g in replacement if g not in alts)
            return
        if prefix or suffix:
            chain = self.get_lookup_(location, ChainContextSubstBuilder)
            lookup = self.get_chained_lookup_(location, AlternateSubstBuilder)
            chain.rules.append(ChainContextualRule(prefix, [{glyph}], suffix, [lookup]))
        else:
            lookup = self.get_lookup_(location, AlternateSubstBuilder)
        if glyph in lookup.alternates:
            raise FeatureLibError(
                'Already defined alternates for glyph "%s"' % glyph, location
            )
        # We allow empty replacement glyphs here.
        lookup.alternates[glyph] = replacement

    # GSUB 4
    def add_ligature_subst(
        self, location, prefix, glyphs, suffix, replacement, forceChain
    ):
        if prefix or suffix or forceChain:
            self.add_ligature_subst_chained_(
                location, prefix, glyphs, suffix, replacement
            )
            return
        if not all(glyphs):
            raise FeatureLibError("Empty glyph class in substitution", location)

        # OpenType feature file syntax, section 5.d, "Ligature substitution":
        # "Since the OpenType specification does not allow ligature
        # substitutions to be specified on target sequences that contain
        # glyph classes, the implementation software will enumerate
        # all specific glyph sequences if glyph classes are detected"
        self.add_any_subst_(
            location,
            {g: (replacement,) for g in itertools.product(*glyphs)},
        )

    # GSUB 5/6
    def add_chain_context_subst(self, location, prefix, glyphs, suffix, lookups):
        if not all(glyphs) or not all(prefix) or not all(suffix):
            raise FeatureLibError(
                "Empty glyph class in contextual substitution", location
            )
        lookup = self.get_lookup_(location, ChainContextSubstBuilder)
        lookup.rules.append(
            ChainContextualRule(
                prefix, glyphs, suffix, self.find_lookup_builders_(lookups)
            )
        )

    def add_single_subst_chained_(self, location, prefix, suffix, mapping):
        if not mapping or not all(prefix) or not all(suffix):
            raise FeatureLibError(
                "Empty glyph class in contextual substitution", location
            )
        # https://github.com/fonttools/fonttools/issues/512
        # https://github.com/fonttools/fonttools/issues/2150
        chain = self.get_lookup_(location, ChainContextSubstBuilder)
        sub = chain.find_chainable_subst(mapping, SingleSubstBuilder)
        if sub is None:
            sub = self.get_chained_lookup_(location, SingleSubstBuilder)
        sub.mapping.update(mapping)
        chain.rules.append(
            ChainContextualRule(prefix, [list(mapping.keys())], suffix, [sub])
        )

    def add_multi_subst_chained_(self, location, prefix, glyph, suffix, replacements):
        if not all(prefix) or not all(suffix):
            raise FeatureLibError(
                "Empty glyph class in contextual substitution", location
            )
        # https://github.com/fonttools/fonttools/issues/3551
        chain = self.get_lookup_(location, ChainContextSubstBuilder)
        sub = chain.find_chainable_subst({glyph: replacements}, MultipleSubstBuilder)
        if sub is None:
            sub = self.get_chained_lookup_(location, MultipleSubstBuilder)
        sub.mapping[glyph] = replacements
        chain.rules.append(ChainContextualRule(prefix, [{glyph}], suffix, [sub]))

    def add_ligature_subst_chained_(
        self, location, prefix, glyphs, suffix, replacement
    ):
        # https://github.com/fonttools/fonttools/issues/3701
        if not all(prefix) or not all(suffix):
            raise FeatureLibError(
                "Empty glyph class in contextual substitution", location
            )
        chain = self.get_lookup_(location, ChainContextSubstBuilder)
        sub = chain.find_chainable_ligature_subst(glyphs, replacement)
        if sub is None:
            sub = self.get_chained_lookup_(location, LigatureSubstBuilder)

        for g in itertools.product(*glyphs):
            existing = sub.ligatures.get(g, replacement)
            if existing != replacement:
                raise FeatureLibError(
                    f"Conflicting ligature sub rules: '{g}' maps to '{existing}' and '{replacement}'",
                    location,
                )

            sub.ligatures[g] = replacement

        chain.rules.append(ChainContextualRule(prefix, glyphs, suffix, [sub]))

    # GSUB 8
    def add_reverse_chain_single_subst(self, location, old_prefix, old_suffix, mapping):
        if not mapping:
            raise FeatureLibError("Empty glyph class in substitution", location)
        lookup = self.get_lookup_(location, ReverseChainSingleSubstBuilder)
        lookup.rules.append((old_prefix, old_suffix, mapping))

    # GPOS rules

    # GPOS 1
    def add_single_pos(self, location, prefix, suffix, pos, forceChain):
        if prefix or suffix or forceChain:
            self.add_single_pos_chained_(location, prefix, suffix, pos)
        else:
            lookup = self.get_lookup_(location, SinglePosBuilder)
            for glyphs, value in pos:
                if not glyphs:
                    raise FeatureLibError(
                        "Empty glyph class in positioning rule", location
                    )
                otValueRecord = self.makeOpenTypeValueRecord(
                    location, value, pairPosContext=False
                )
                for glyph in glyphs:
                    try:
                        lookup.add_pos(location, glyph, otValueRecord)
                    except OpenTypeLibError as e:
                        raise FeatureLibError(str(e), e.location) from e

    # GPOS 2
    def add_class_pair_pos(self, location, glyphclass1, value1, glyphclass2, value2):
        if not glyphclass1 or not glyphclass2:
            raise FeatureLibError("Empty glyph class in positioning rule", location)
        lookup = self.get_lookup_(location, PairPosBuilder)
        v1 = self.makeOpenTypeValueRecord(location, value1, pairPosContext=True)
        v2 = self.makeOpenTypeValueRecord(location, value2, pairPosContext=True)
        cls1 = tuple(sorted(set(glyphclass1)))
        cls2 = tuple(sorted(set(glyphclass2)))
        lookup.addClassPair(location, cls1, v1, cls2, v2)

    def add_specific_pair_pos(self, location, glyph1, value1, glyph2, value2):
        if not glyph1 or not glyph2:
            raise FeatureLibError("Empty glyph class in positioning rule", location)
        lookup = self.get_lookup_(location, PairPosBuilder)
        v1 = self.makeOpenTypeValueRecord(location, value1, pairPosContext=True)
        v2 = self.makeOpenTypeValueRecord(location, value2, pairPosContext=True)
        lookup.addGlyphPair(location, glyph1, v1, glyph2, v2)

    # GPOS 3
    def add_cursive_pos(self, location, glyphclass, entryAnchor, exitAnchor):
        if not glyphclass:
            raise FeatureLibError("Empty glyph class in positioning rule", location)
        lookup = self.get_lookup_(location, CursivePosBuilder)
        lookup.add_attachment(
            location,
            glyphclass,
            self.makeOpenTypeAnchor(location, entryAnchor),
            self.makeOpenTypeAnchor(location, exitAnchor),
        )

    # GPOS 4
    def add_mark_base_pos(self, location, bases, marks):
        builder = self.get_lookup_(location, MarkBasePosBuilder)
        self.add_marks_(location, builder, marks)
        if not bases:
            raise FeatureLibError("Empty glyph class in positioning rule", location)
        for baseAnchor, markClass in marks:
            otBaseAnchor = self.makeOpenTypeAnchor(location, baseAnchor)
            for base in bases:
                builder.bases.setdefault(base, {})[markClass.name] = otBaseAnchor

    # GPOS 5
    def add_mark_lig_pos(self, location, ligatures, components):
        builder = self.get_lookup_(location, MarkLigPosBuilder)
        componentAnchors = []
        if not ligatures:
            raise FeatureLibError("Empty glyph class in positioning rule", location)
        for marks in components:
            anchors = {}
            self.add_marks_(location, builder, marks)
            for ligAnchor, markClass in marks:
                anchors[markClass.name] = self.makeOpenTypeAnchor(location, ligAnchor)
            componentAnchors.append(anchors)
        for glyph in ligatures:
            builder.ligatures[glyph] = componentAnchors

    # GPOS 6
    def add_mark_mark_pos(self, location, baseMarks, marks):
        builder = self.get_lookup_(location, MarkMarkPosBuilder)
        self.add_marks_(location, builder, marks)
        if not baseMarks:
            raise FeatureLibError("Empty glyph class in positioning rule", location)
        for baseAnchor, markClass in marks:
            otBaseAnchor = self.makeOpenTypeAnchor(location, baseAnchor)
            for baseMark in baseMarks:
                builder.baseMarks.setdefault(baseMark, {})[
                    markClass.name
                ] = otBaseAnchor

    # GPOS 7/8
    def add_chain_context_pos(self, location, prefix, glyphs, suffix, lookups):
        if not all(glyphs) or not all(prefix) or not all(suffix):
            raise FeatureLibError(
                "Empty glyph class in contextual positioning rule", location
            )
        lookup = self.get_lookup_(location, ChainContextPosBuilder)
        lookup.rules.append(
            ChainContextualRule(
                prefix, glyphs, suffix, self.find_lookup_builders_(lookups)
            )
        )

    def add_single_pos_chained_(self, location, prefix, suffix, pos):
        if not pos or not all(prefix) or not all(suffix):
            raise FeatureLibError(
                "Empty glyph class in contextual positioning rule", location
            )
        # https://github.com/fonttools/fonttools/issues/514
        chain = self.get_lookup_(location, ChainContextPosBuilder)
        targets = []
        for _, _, _, lookups in chain.rules:
            targets.extend(lookups)
        subs = []
        for glyphs, value in pos:
            if value is None:
                subs.append(None)
                continue
            otValue = self.makeOpenTypeValueRecord(
                location, value, pairPosContext=False
            )
            sub = chain.find_chainable_single_pos(targets, glyphs, otValue)
            if sub is None:
                sub = self.get_chained_lookup_(location, SinglePosBuilder)
                targets.append(sub)
            for glyph in glyphs:
                sub.add_pos(location, glyph, otValue)
            subs.append(sub)
        assert len(pos) == len(subs), (pos, subs)
        chain.rules.append(
            ChainContextualRule(prefix, [g for g, v in pos], suffix, subs)
        )

    def add_marks_(self, location, lookupBuilder, marks):
        """Helper for add_mark_{base,liga,mark}_pos."""
        for _, markClass in marks:
            for markClassDef in markClass.definitions:
                for mark in markClassDef.glyphs.glyphSet():
                    if mark not in lookupBuilder.marks:
                        otMarkAnchor = self.makeOpenTypeAnchor(
                            location, copy.deepcopy(markClassDef.anchor)
                        )
                        lookupBuilder.marks[mark] = (markClass.name, otMarkAnchor)
                    else:
                        existingMarkClass = lookupBuilder.marks[mark][0]
                        if markClass.name != existingMarkClass:
                            raise FeatureLibError(
                                "Glyph %s cannot be in both @%s and @%s"
                                % (mark, existingMarkClass, markClass.name),
                                location,
                            )

    def add_subtable_break(self, location):
        self.cur_lookup_.add_subtable_break(location)

    def setGlyphClass_(self, location, glyph, glyphClass):
        oldClass, oldLocation = self.glyphClassDefs_.get(glyph, (None, None))
        if oldClass and oldClass != glyphClass:
            raise FeatureLibError(
                "Glyph %s was assigned to a different class at %s"
                % (glyph, oldLocation),
                location,
            )
        self.glyphClassDefs_[glyph] = (glyphClass, location)

    def add_glyphClassDef(
        self, location, baseGlyphs, ligatureGlyphs, markGlyphs, componentGlyphs
    ):
        for glyph in baseGlyphs:
            self.setGlyphClass_(location, glyph, 1)
        for glyph in ligatureGlyphs:
            self.setGlyphClass_(location, glyph, 2)
        for glyph in markGlyphs:
            self.setGlyphClass_(location, glyph, 3)
        for glyph in componentGlyphs:
            self.setGlyphClass_(location, glyph, 4)

    def add_ligatureCaretByIndex_(self, location, glyphs, carets):
        for glyph in glyphs:
            if glyph not in self.ligCaretPoints_:
                self.ligCaretPoints_[glyph] = carets

    def makeLigCaret(self, location, caret):
        if not isinstance(caret, VariableScalar):
            return caret
        default, device = self.makeVariablePos(location, caret)
        if device is not None:
            return (default, device)
        return default

    def add_ligatureCaretByPos_(self, location, glyphs, carets):
        carets = [self.makeLigCaret(location, caret) for caret in carets]
        for glyph in glyphs:
            if glyph not in self.ligCaretCoords_:
                self.ligCaretCoords_[glyph] = carets

    def add_name_record(self, location, nameID, platformID, platEncID, langID, string):
        self.names_.append([nameID, platformID, platEncID, langID, string])

    def add_os2_field(self, key, value):
        self.os2_[key] = value

    def add_hhea_field(self, key, value):
        self.hhea_[key] = value

    def add_vhea_field(self, key, value):
        self.vhea_[key] = value

    def add_conditionset(self, location, key, value):
        if "fvar" not in self.font:
            raise FeatureLibError(
                "Cannot add feature variations to a font without an 'fvar' table",
                location,
            )

        # Normalize
        axisMap = {
            axis.axisTag: (axis.minValue, axis.defaultValue, axis.maxValue)
            for axis in self.axes
        }

        value = {
            tag: (
                normalizeValue(bottom, axisMap[tag]),
                normalizeValue(top, axisMap[tag]),
            )
            for tag, (bottom, top) in value.items()
        }

        # NOTE: This might result in rounding errors (off-by-ones) compared to
        # rules in Designspace files, since we're working with what's in the
        # `avar` table rather than the original values.
        if "avar" in self.font:
            mapping = self.font["avar"].segments
            value = {
                axis: tuple(
                    piecewiseLinearMap(v, mapping[axis]) if axis in mapping else v
                    for v in condition_range
                )
                for axis, condition_range in value.items()
            }

        self.conditionsets_[key] = value

    def makeVariablePos(self, location, varscalar):
        if not self.varstorebuilder:
            raise FeatureLibError(
                "Can't define a variable scalar in a non-variable font", location
            )

        varscalar.axes = self.axes
        if not varscalar.does_vary:
            return varscalar.default, None

        try:
            default, index = varscalar.add_to_variation_store(
                self.varstorebuilder, self.model_cache, self.font.get("avar")
            )
        except VarLibError as e:
            raise FeatureLibError(
                "Failed to compute deltas for variable scalar", location
            ) from e

        device = None
        if index is not None and index != 0xFFFFFFFF:
            device = buildVarDevTable(index)

        return default, device

    def makeAnchorPos(self, varscalar, deviceTable, location):
        device = None
        if not isinstance(varscalar, VariableScalar):
            if deviceTable is not None:
                device = otl.buildDevice(dict(deviceTable))
            return varscalar, device
        default, device = self.makeVariablePos(location, varscalar)
        if device is not None and deviceTable is not None:
            raise FeatureLibError(
                "Can't define a device coordinate and variable scalar", location
            )
        return default, device

    def makeOpenTypeAnchor(self, location, anchor):
        """ast.Anchor --> otTables.Anchor"""
        if anchor is None:
            return None
        deviceX, deviceY = None, None
        if anchor.xDeviceTable is not None:
            deviceX = otl.buildDevice(dict(anchor.xDeviceTable))
        if anchor.yDeviceTable is not None:
            deviceY = otl.buildDevice(dict(anchor.yDeviceTable))
        x, deviceX = self.makeAnchorPos(anchor.x, anchor.xDeviceTable, location)
        y, deviceY = self.makeAnchorPos(anchor.y, anchor.yDeviceTable, location)
        otlanchor = otl.buildAnchor(x, y, anchor.contourpoint, deviceX, deviceY)
        return otlanchor

    _VALUEREC_ATTRS = {
        name[0].lower() + name[1:]: (name, isDevice)
        for _, name, isDevice, _ in otBase.valueRecordFormat
        if not name.startswith("Reserved")
    }

    def makeOpenTypeValueRecord(self, location, v, pairPosContext):
        """ast.ValueRecord --> otBase.ValueRecord"""
        if not v:
            return None

        vr = {}
        for astName, (otName, isDevice) in self._VALUEREC_ATTRS.items():
            val = getattr(v, astName, None)
            if not val:
                continue
            if isDevice:
                vr[otName] = otl.buildDevice(dict(val))
            elif isinstance(val, VariableScalar):
                otDeviceName = otName[0:4] + "Device"
                feaDeviceName = otDeviceName[0].lower() + otDeviceName[1:]
                if getattr(v, feaDeviceName):
                    raise FeatureLibError(
                        "Can't define a device coordinate and variable scalar", location
                    )
                vr[otName], device = self.makeVariablePos(location, val)
                if device is not None:
                    vr[otDeviceName] = device
            else:
                vr[otName] = val

        if pairPosContext and not vr:
            vr = {"YAdvance": 0} if v.vertical else {"XAdvance": 0}
        valRec = otl.buildValue(vr)
        return valRec
