otData = [
    #
    # common
    #
    ("LookupOrder", []),
    (
        "ScriptList",
        [
            ("uint16", "ScriptCount", None, None, "Number of ScriptRecords"),
            (
                "struct",
                "ScriptRecord",
                "ScriptCount",
                0,
                "Array of ScriptRecords -listed alphabetically by ScriptTag",
            ),
        ],
    ),
    (
        "ScriptRecord",
        [
            ("Tag", "ScriptTag", None, None, "4-byte ScriptTag identifier"),
            (
                "Offset",
                "Script",
                None,
                None,
                "Offset to Script table-from beginning of ScriptList",
            ),
        ],
    ),
    (
        "Script",
        [
            (
                "Offset",
                "DefaultLangSys",
                None,
                None,
                "Offset to DefaultLangSys table-from beginning of Script table-may be NULL",
            ),
            (
                "uint16",
                "LangSysCount",
                None,
                None,
                "Number of LangSysRecords for this script-excluding the DefaultLangSys",
            ),
            (
                "struct",
                "LangSysRecord",
                "LangSysCount",
                0,
                "Array of LangSysRecords-listed alphabetically by LangSysTag",
            ),
        ],
    ),
    (
        "LangSysRecord",
        [
            ("Tag", "LangSysTag", None, None, "4-byte LangSysTag identifier"),
            (
                "Offset",
                "LangSys",
                None,
                None,
                "Offset to LangSys table-from beginning of Script table",
            ),
        ],
    ),
    (
        "LangSys",
        [
            (
                "Offset",
                "LookupOrder",
                None,
                None,
                "= NULL (reserved for an offset to a reordering table)",
            ),
            (
                "uint16",
                "ReqFeatureIndex",
                None,
                None,
                "Index of a feature required for this language system- if no required features = 0xFFFF",
            ),
            (
                "uint16",
                "FeatureCount",
                None,
                None,
                "Number of FeatureIndex values for this language system-excludes the required feature",
            ),
            (
                "uint16",
                "FeatureIndex",
                "FeatureCount",
                0,
                "Array of indices into the FeatureList-in arbitrary order",
            ),
        ],
    ),
    (
        "FeatureList",
        [
            (
                "uint16",
                "FeatureCount",
                None,
                None,
                "Number of FeatureRecords in this table",
            ),
            (
                "struct",
                "FeatureRecord",
                "FeatureCount",
                0,
                "Array of FeatureRecords-zero-based (first feature has FeatureIndex = 0)-listed alphabetically by FeatureTag",
            ),
        ],
    ),
    (
        "FeatureRecord",
        [
            ("Tag", "FeatureTag", None, None, "4-byte feature identification tag"),
            (
                "Offset",
                "Feature",
                None,
                None,
                "Offset to Feature table-from beginning of FeatureList",
            ),
        ],
    ),
    (
        "Feature",
        [
            (
                "Offset",
                "FeatureParams",
                None,
                None,
                "= NULL (reserved for offset to FeatureParams)",
            ),
            (
                "uint16",
                "LookupCount",
                None,
                None,
                "Number of LookupList indices for this feature",
            ),
            (
                "uint16",
                "LookupListIndex",
                "LookupCount",
                0,
                "Array of LookupList indices for this feature -zero-based (first lookup is LookupListIndex = 0)",
            ),
        ],
    ),
    ("FeatureParams", []),
    (
        "FeatureParamsSize",
        [
            (
                "DeciPoints",
                "DesignSize",
                None,
                None,
                "The design size in 720/inch units (decipoints).",
            ),
            (
                "uint16",
                "SubfamilyID",
                None,
                None,
                "Serves as an identifier that associates fonts in a subfamily.",
            ),
            ("NameID", "SubfamilyNameID", None, None, "Subfamily NameID."),
            (
                "DeciPoints",
                "RangeStart",
                None,
                None,
                "Small end of recommended usage range (exclusive) in 720/inch units.",
            ),
            (
                "DeciPoints",
                "RangeEnd",
                None,
                None,
                "Large end of recommended usage range (inclusive) in 720/inch units.",
            ),
        ],
    ),
    (
        "FeatureParamsStylisticSet",
        [
            ("uint16", "Version", None, None, "Set to 0."),
            ("NameID", "UINameID", None, None, "UI NameID."),
        ],
    ),
    (
        "FeatureParamsCharacterVariants",
        [
            ("uint16", "Format", None, None, "Set to 0."),
            ("NameID", "FeatUILabelNameID", None, None, "Feature UI label NameID."),
            (
                "NameID",
                "FeatUITooltipTextNameID",
                None,
                None,
                "Feature UI tooltip text NameID.",
            ),
            ("NameID", "SampleTextNameID", None, None, "Sample text NameID."),
            ("uint16", "NumNamedParameters", None, None, "Number of named parameters."),
            (
                "NameID",
                "FirstParamUILabelNameID",
                None,
                None,
                "First NameID of UI feature parameters.",
            ),
            (
                "uint16",
                "CharCount",
                None,
                None,
                "Count of characters this feature provides glyph variants for.",
            ),
            (
                "uint24",
                "Character",
                "CharCount",
                0,
                "Unicode characters for which this feature provides glyph variants.",
            ),
        ],
    ),
    (
        "LookupList",
        [
            ("uint16", "LookupCount", None, None, "Number of lookups in this table"),
            (
                "Offset",
                "Lookup",
                "LookupCount",
                0,
                "Array of offsets to Lookup tables-from beginning of LookupList -zero based (first lookup is Lookup index = 0)",
            ),
        ],
    ),
    (
        "Lookup",
        [
            (
                "uint16",
                "LookupType",
                None,
                None,
                "Different enumerations for GSUB and GPOS",
            ),
            ("LookupFlag", "LookupFlag", None, None, "Lookup qualifiers"),
            (
                "uint16",
                "SubTableCount",
                None,
                None,
                "Number of SubTables for this lookup",
            ),
            (
                "Offset",
                "SubTable",
                "SubTableCount",
                0,
                "Array of offsets to SubTables-from beginning of Lookup table",
            ),
            (
                "uint16",
                "MarkFilteringSet",
                None,
                "LookupFlag & 0x0010",
                "If set, indicates that the lookup table structure is followed by a MarkFilteringSet field. The layout engine skips over all mark glyphs not in the mark filtering set indicated.",
            ),
        ],
    ),
    (
        "CoverageFormat1",
        [
            ("uint16", "CoverageFormat", None, None, "Format identifier-format = 1"),
            ("uint16", "GlyphCount", None, None, "Number of glyphs in the GlyphArray"),
            (
                "GlyphID",
                "GlyphArray",
                "GlyphCount",
                0,
                "Array of GlyphIDs-in numerical order",
            ),
        ],
    ),
    (
        "CoverageFormat2",
        [
            ("uint16", "CoverageFormat", None, None, "Format identifier-format = 2"),
            ("uint16", "RangeCount", None, None, "Number of RangeRecords"),
            (
                "struct",
                "RangeRecord",
                "RangeCount",
                0,
                "Array of glyph ranges-ordered by Start GlyphID",
            ),
        ],
    ),
    (
        "RangeRecord",
        [
            ("GlyphID", "Start", None, None, "First GlyphID in the range"),
            ("GlyphID", "End", None, None, "Last GlyphID in the range"),
            (
                "uint16",
                "StartCoverageIndex",
                None,
                None,
                "Coverage Index of first GlyphID in range",
            ),
        ],
    ),
    (
        "ClassDefFormat1",
        [
            ("uint16", "ClassFormat", None, None, "Format identifier-format = 1"),
            (
                "GlyphID",
                "StartGlyph",
                None,
                None,
                "First GlyphID of the ClassValueArray",
            ),
            ("uint16", "GlyphCount", None, None, "Size of the ClassValueArray"),
            (
                "uint16",
                "ClassValueArray",
                "GlyphCount",
                0,
                "Array of Class Values-one per GlyphID",
            ),
        ],
    ),
    (
        "ClassDefFormat2",
        [
            ("uint16", "ClassFormat", None, None, "Format identifier-format = 2"),
            ("uint16", "ClassRangeCount", None, None, "Number of ClassRangeRecords"),
            (
                "struct",
                "ClassRangeRecord",
                "ClassRangeCount",
                0,
                "Array of ClassRangeRecords-ordered by Start GlyphID",
            ),
        ],
    ),
    (
        "ClassRangeRecord",
        [
            ("GlyphID", "Start", None, None, "First GlyphID in the range"),
            ("GlyphID", "End", None, None, "Last GlyphID in the range"),
            ("uint16", "Class", None, None, "Applied to all glyphs in the range"),
        ],
    ),
    (
        "Device",
        [
            ("uint16", "StartSize", None, None, "Smallest size to correct-in ppem"),
            ("uint16", "EndSize", None, None, "Largest size to correct-in ppem"),
            (
                "uint16",
                "DeltaFormat",
                None,
                None,
                "Format of DeltaValue array data: 1, 2, or 3",
            ),
            (
                "DeltaValue",
                "DeltaValue",
                None,
                "DeltaFormat in (1,2,3)",
                "Array of compressed data",
            ),
        ],
    ),
    #
    # gpos
    #
    (
        "GPOS",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the GPOS table- 0x00010000 or 0x00010001",
            ),
            (
                "Offset",
                "ScriptList",
                None,
                None,
                "Offset to ScriptList table-from beginning of GPOS table",
            ),
            (
                "Offset",
                "FeatureList",
                None,
                None,
                "Offset to FeatureList table-from beginning of GPOS table",
            ),
            (
                "Offset",
                "LookupList",
                None,
                None,
                "Offset to LookupList table-from beginning of GPOS table",
            ),
            (
                "LOffset",
                "FeatureVariations",
                None,
                "Version >= 0x00010001",
                "Offset to FeatureVariations table-from beginning of GPOS table",
            ),
        ],
    ),
    (
        "SinglePosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of SinglePos subtable",
            ),
            (
                "uint16",
                "ValueFormat",
                None,
                None,
                "Defines the types of data in the ValueRecord",
            ),
            (
                "ValueRecord",
                "Value",
                None,
                None,
                "Defines positioning value(s)-applied to all glyphs in the Coverage table",
            ),
        ],
    ),
    (
        "SinglePosFormat2",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of SinglePos subtable",
            ),
            (
                "uint16",
                "ValueFormat",
                None,
                None,
                "Defines the types of data in the ValueRecord",
            ),
            ("uint16", "ValueCount", None, None, "Number of ValueRecords"),
            (
                "ValueRecord",
                "Value",
                "ValueCount",
                0,
                "Array of ValueRecords-positioning values applied to glyphs",
            ),
        ],
    ),
    (
        "PairPosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of PairPos subtable-only the first glyph in each pair",
            ),
            (
                "uint16",
                "ValueFormat1",
                None,
                None,
                "Defines the types of data in ValueRecord1-for the first glyph in the pair -may be zero (0)",
            ),
            (
                "uint16",
                "ValueFormat2",
                None,
                None,
                "Defines the types of data in ValueRecord2-for the second glyph in the pair -may be zero (0)",
            ),
            ("uint16", "PairSetCount", None, None, "Number of PairSet tables"),
            (
                "Offset",
                "PairSet",
                "PairSetCount",
                0,
                "Array of offsets to PairSet tables-from beginning of PairPos subtable-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "PairSet",
        [
            ("uint16", "PairValueCount", None, None, "Number of PairValueRecords"),
            (
                "struct",
                "PairValueRecord",
                "PairValueCount",
                0,
                "Array of PairValueRecords-ordered by GlyphID of the second glyph",
            ),
        ],
    ),
    (
        "PairValueRecord",
        [
            (
                "GlyphID",
                "SecondGlyph",
                None,
                None,
                "GlyphID of second glyph in the pair-first glyph is listed in the Coverage table",
            ),
            (
                "ValueRecord",
                "Value1",
                None,
                None,
                "Positioning data for the first glyph in the pair",
            ),
            (
                "ValueRecord",
                "Value2",
                None,
                None,
                "Positioning data for the second glyph in the pair",
            ),
        ],
    ),
    (
        "PairPosFormat2",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of PairPos subtable-for the first glyph of the pair",
            ),
            (
                "uint16",
                "ValueFormat1",
                None,
                None,
                "ValueRecord definition-for the first glyph of the pair-may be zero (0)",
            ),
            (
                "uint16",
                "ValueFormat2",
                None,
                None,
                "ValueRecord definition-for the second glyph of the pair-may be zero (0)",
            ),
            (
                "Offset",
                "ClassDef1",
                None,
                None,
                "Offset to ClassDef table-from beginning of PairPos subtable-for the first glyph of the pair",
            ),
            (
                "Offset",
                "ClassDef2",
                None,
                None,
                "Offset to ClassDef table-from beginning of PairPos subtable-for the second glyph of the pair",
            ),
            (
                "uint16",
                "Class1Count",
                None,
                None,
                "Number of classes in ClassDef1 table-includes Class0",
            ),
            (
                "uint16",
                "Class2Count",
                None,
                None,
                "Number of classes in ClassDef2 table-includes Class0",
            ),
            (
                "struct",
                "Class1Record",
                "Class1Count",
                0,
                "Array of Class1 records-ordered by Class1",
            ),
        ],
    ),
    (
        "Class1Record",
        [
            (
                "struct",
                "Class2Record",
                "Class2Count",
                0,
                "Array of Class2 records-ordered by Class2",
            ),
        ],
    ),
    (
        "Class2Record",
        [
            (
                "ValueRecord",
                "Value1",
                None,
                None,
                "Positioning for first glyph-empty if ValueFormat1 = 0",
            ),
            (
                "ValueRecord",
                "Value2",
                None,
                None,
                "Positioning for second glyph-empty if ValueFormat2 = 0",
            ),
        ],
    ),
    (
        "CursivePosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of CursivePos subtable",
            ),
            ("uint16", "EntryExitCount", None, None, "Number of EntryExit records"),
            (
                "struct",
                "EntryExitRecord",
                "EntryExitCount",
                0,
                "Array of EntryExit records-in Coverage Index order",
            ),
        ],
    ),
    (
        "EntryExitRecord",
        [
            (
                "Offset",
                "EntryAnchor",
                None,
                None,
                "Offset to EntryAnchor table-from beginning of CursivePos subtable-may be NULL",
            ),
            (
                "Offset",
                "ExitAnchor",
                None,
                None,
                "Offset to ExitAnchor table-from beginning of CursivePos subtable-may be NULL",
            ),
        ],
    ),
    (
        "MarkBasePosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "MarkCoverage",
                None,
                None,
                "Offset to MarkCoverage table-from beginning of MarkBasePos subtable",
            ),
            (
                "Offset",
                "BaseCoverage",
                None,
                None,
                "Offset to BaseCoverage table-from beginning of MarkBasePos subtable",
            ),
            ("uint16", "ClassCount", None, None, "Number of classes defined for marks"),
            (
                "Offset",
                "MarkArray",
                None,
                None,
                "Offset to MarkArray table-from beginning of MarkBasePos subtable",
            ),
            (
                "Offset",
                "BaseArray",
                None,
                None,
                "Offset to BaseArray table-from beginning of MarkBasePos subtable",
            ),
        ],
    ),
    (
        "BaseArray",
        [
            ("uint16", "BaseCount", None, None, "Number of BaseRecords"),
            (
                "struct",
                "BaseRecord",
                "BaseCount",
                0,
                "Array of BaseRecords-in order of BaseCoverage Index",
            ),
        ],
    ),
    (
        "BaseRecord",
        [
            (
                "Offset",
                "BaseAnchor",
                "ClassCount",
                0,
                "Array of offsets (one per class) to Anchor tables-from beginning of BaseArray table-ordered by class-zero-based",
            ),
        ],
    ),
    (
        "MarkLigPosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "MarkCoverage",
                None,
                None,
                "Offset to Mark Coverage table-from beginning of MarkLigPos subtable",
            ),
            (
                "Offset",
                "LigatureCoverage",
                None,
                None,
                "Offset to Ligature Coverage table-from beginning of MarkLigPos subtable",
            ),
            ("uint16", "ClassCount", None, None, "Number of defined mark classes"),
            (
                "Offset",
                "MarkArray",
                None,
                None,
                "Offset to MarkArray table-from beginning of MarkLigPos subtable",
            ),
            (
                "Offset",
                "LigatureArray",
                None,
                None,
                "Offset to LigatureArray table-from beginning of MarkLigPos subtable",
            ),
        ],
    ),
    (
        "LigatureArray",
        [
            (
                "uint16",
                "LigatureCount",
                None,
                None,
                "Number of LigatureAttach table offsets",
            ),
            (
                "Offset",
                "LigatureAttach",
                "LigatureCount",
                0,
                "Array of offsets to LigatureAttach tables-from beginning of LigatureArray table-ordered by LigatureCoverage Index",
            ),
        ],
    ),
    (
        "LigatureAttach",
        [
            (
                "uint16",
                "ComponentCount",
                None,
                None,
                "Number of ComponentRecords in this ligature",
            ),
            (
                "struct",
                "ComponentRecord",
                "ComponentCount",
                0,
                "Array of Component records-ordered in writing direction",
            ),
        ],
    ),
    (
        "ComponentRecord",
        [
            (
                "Offset",
                "LigatureAnchor",
                "ClassCount",
                0,
                "Array of offsets (one per class) to Anchor tables-from beginning of LigatureAttach table-ordered by class-NULL if a component does not have an attachment for a class-zero-based array",
            ),
        ],
    ),
    (
        "MarkMarkPosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Mark1Coverage",
                None,
                None,
                "Offset to Combining Mark Coverage table-from beginning of MarkMarkPos subtable",
            ),
            (
                "Offset",
                "Mark2Coverage",
                None,
                None,
                "Offset to Base Mark Coverage table-from beginning of MarkMarkPos subtable",
            ),
            (
                "uint16",
                "ClassCount",
                None,
                None,
                "Number of Combining Mark classes defined",
            ),
            (
                "Offset",
                "Mark1Array",
                None,
                None,
                "Offset to MarkArray table for Mark1-from beginning of MarkMarkPos subtable",
            ),
            (
                "Offset",
                "Mark2Array",
                None,
                None,
                "Offset to Mark2Array table for Mark2-from beginning of MarkMarkPos subtable",
            ),
        ],
    ),
    (
        "Mark2Array",
        [
            ("uint16", "Mark2Count", None, None, "Number of Mark2 records"),
            (
                "struct",
                "Mark2Record",
                "Mark2Count",
                0,
                "Array of Mark2 records-in Coverage order",
            ),
        ],
    ),
    (
        "Mark2Record",
        [
            (
                "Offset",
                "Mark2Anchor",
                "ClassCount",
                0,
                "Array of offsets (one per class) to Anchor tables-from beginning of Mark2Array table-zero-based array",
            ),
        ],
    ),
    (
        "PosLookupRecord",
        [
            (
                "uint16",
                "SequenceIndex",
                None,
                None,
                "Index to input glyph sequence-first glyph = 0",
            ),
            (
                "uint16",
                "LookupListIndex",
                None,
                None,
                "Lookup to apply to that position-zero-based",
            ),
        ],
    ),
    (
        "ContextPosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of ContextPos subtable",
            ),
            ("uint16", "PosRuleSetCount", None, None, "Number of PosRuleSet tables"),
            (
                "Offset",
                "PosRuleSet",
                "PosRuleSetCount",
                0,
                "Array of offsets to PosRuleSet tables-from beginning of ContextPos subtable-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "PosRuleSet",
        [
            ("uint16", "PosRuleCount", None, None, "Number of PosRule tables"),
            (
                "Offset",
                "PosRule",
                "PosRuleCount",
                0,
                "Array of offsets to PosRule tables-from beginning of PosRuleSet-ordered by preference",
            ),
        ],
    ),
    (
        "PosRule",
        [
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of glyphs in the Input glyph sequence",
            ),
            ("uint16", "PosCount", None, None, "Number of PosLookupRecords"),
            (
                "GlyphID",
                "Input",
                "GlyphCount",
                -1,
                "Array of input GlyphIDs-starting with the second glyph",
            ),
            (
                "struct",
                "PosLookupRecord",
                "PosCount",
                0,
                "Array of positioning lookups-in design order",
            ),
        ],
    ),
    (
        "ContextPosFormat2",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of ContextPos subtable",
            ),
            (
                "Offset",
                "ClassDef",
                None,
                None,
                "Offset to ClassDef table-from beginning of ContextPos subtable",
            ),
            ("uint16", "PosClassSetCount", None, None, "Number of PosClassSet tables"),
            (
                "Offset",
                "PosClassSet",
                "PosClassSetCount",
                0,
                "Array of offsets to PosClassSet tables-from beginning of ContextPos subtable-ordered by class-may be NULL",
            ),
        ],
    ),
    (
        "PosClassSet",
        [
            (
                "uint16",
                "PosClassRuleCount",
                None,
                None,
                "Number of PosClassRule tables",
            ),
            (
                "Offset",
                "PosClassRule",
                "PosClassRuleCount",
                0,
                "Array of offsets to PosClassRule tables-from beginning of PosClassSet-ordered by preference",
            ),
        ],
    ),
    (
        "PosClassRule",
        [
            ("uint16", "GlyphCount", None, None, "Number of glyphs to be matched"),
            ("uint16", "PosCount", None, None, "Number of PosLookupRecords"),
            (
                "uint16",
                "Class",
                "GlyphCount",
                -1,
                "Array of classes-beginning with the second class-to be matched to the input glyph sequence",
            ),
            (
                "struct",
                "PosLookupRecord",
                "PosCount",
                0,
                "Array of positioning lookups-in design order",
            ),
        ],
    ),
    (
        "ContextPosFormat3",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 3"),
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of glyphs in the input sequence",
            ),
            ("uint16", "PosCount", None, None, "Number of PosLookupRecords"),
            (
                "Offset",
                "Coverage",
                "GlyphCount",
                0,
                "Array of offsets to Coverage tables-from beginning of ContextPos subtable",
            ),
            (
                "struct",
                "PosLookupRecord",
                "PosCount",
                0,
                "Array of positioning lookups-in design order",
            ),
        ],
    ),
    (
        "ChainContextPosFormat1",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of ContextPos subtable",
            ),
            (
                "uint16",
                "ChainPosRuleSetCount",
                None,
                None,
                "Number of ChainPosRuleSet tables",
            ),
            (
                "Offset",
                "ChainPosRuleSet",
                "ChainPosRuleSetCount",
                0,
                "Array of offsets to ChainPosRuleSet tables-from beginning of ContextPos subtable-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "ChainPosRuleSet",
        [
            (
                "uint16",
                "ChainPosRuleCount",
                None,
                None,
                "Number of ChainPosRule tables",
            ),
            (
                "Offset",
                "ChainPosRule",
                "ChainPosRuleCount",
                0,
                "Array of offsets to ChainPosRule tables-from beginning of ChainPosRuleSet-ordered by preference",
            ),
        ],
    ),
    (
        "ChainPosRule",
        [
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Total number of glyphs in the backtrack sequence (number of glyphs to be matched before the first glyph)",
            ),
            (
                "GlyphID",
                "Backtrack",
                "BacktrackGlyphCount",
                0,
                "Array of backtracking GlyphID's (to be matched before the input sequence)",
            ),
            (
                "uint16",
                "InputGlyphCount",
                None,
                None,
                "Total number of glyphs in the input sequence (includes the first glyph)",
            ),
            (
                "GlyphID",
                "Input",
                "InputGlyphCount",
                -1,
                "Array of input GlyphIDs (start with second glyph)",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Total number of glyphs in the look ahead sequence (number of glyphs to be matched after the input sequence)",
            ),
            (
                "GlyphID",
                "LookAhead",
                "LookAheadGlyphCount",
                0,
                "Array of lookahead GlyphID's (to be matched after the input sequence)",
            ),
            ("uint16", "PosCount", None, None, "Number of PosLookupRecords"),
            (
                "struct",
                "PosLookupRecord",
                "PosCount",
                0,
                "Array of PosLookupRecords (in design order)",
            ),
        ],
    ),
    (
        "ChainContextPosFormat2",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of ChainContextPos subtable",
            ),
            (
                "Offset",
                "BacktrackClassDef",
                None,
                None,
                "Offset to ClassDef table containing backtrack sequence context-from beginning of ChainContextPos subtable",
            ),
            (
                "Offset",
                "InputClassDef",
                None,
                None,
                "Offset to ClassDef table containing input sequence context-from beginning of ChainContextPos subtable",
            ),
            (
                "Offset",
                "LookAheadClassDef",
                None,
                None,
                "Offset to ClassDef table containing lookahead sequence context-from beginning of ChainContextPos subtable",
            ),
            (
                "uint16",
                "ChainPosClassSetCount",
                None,
                None,
                "Number of ChainPosClassSet tables",
            ),
            (
                "Offset",
                "ChainPosClassSet",
                "ChainPosClassSetCount",
                0,
                "Array of offsets to ChainPosClassSet tables-from beginning of ChainContextPos subtable-ordered by input class-may be NULL",
            ),
        ],
    ),
    (
        "ChainPosClassSet",
        [
            (
                "uint16",
                "ChainPosClassRuleCount",
                None,
                None,
                "Number of ChainPosClassRule tables",
            ),
            (
                "Offset",
                "ChainPosClassRule",
                "ChainPosClassRuleCount",
                0,
                "Array of offsets to ChainPosClassRule tables-from beginning of ChainPosClassSet-ordered by preference",
            ),
        ],
    ),
    (
        "ChainPosClassRule",
        [
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Total number of glyphs in the backtrack sequence (number of glyphs to be matched before the first glyph)",
            ),
            (
                "uint16",
                "Backtrack",
                "BacktrackGlyphCount",
                0,
                "Array of backtracking classes(to be matched before the input sequence)",
            ),
            (
                "uint16",
                "InputGlyphCount",
                None,
                None,
                "Total number of classes in the input sequence (includes the first class)",
            ),
            (
                "uint16",
                "Input",
                "InputGlyphCount",
                -1,
                "Array of input classes(start with second class; to be matched with the input glyph sequence)",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Total number of classes in the look ahead sequence (number of classes to be matched after the input sequence)",
            ),
            (
                "uint16",
                "LookAhead",
                "LookAheadGlyphCount",
                0,
                "Array of lookahead classes(to be matched after the input sequence)",
            ),
            ("uint16", "PosCount", None, None, "Number of PosLookupRecords"),
            (
                "struct",
                "PosLookupRecord",
                "PosCount",
                0,
                "Array of PosLookupRecords (in design order)",
            ),
        ],
    ),
    (
        "ChainContextPosFormat3",
        [
            ("uint16", "PosFormat", None, None, "Format identifier-format = 3"),
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Number of glyphs in the backtracking sequence",
            ),
            (
                "Offset",
                "BacktrackCoverage",
                "BacktrackGlyphCount",
                0,
                "Array of offsets to coverage tables in backtracking sequence, in glyph sequence order",
            ),
            (
                "uint16",
                "InputGlyphCount",
                None,
                None,
                "Number of glyphs in input sequence",
            ),
            (
                "Offset",
                "InputCoverage",
                "InputGlyphCount",
                0,
                "Array of offsets to coverage tables in input sequence, in glyph sequence order",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Number of glyphs in lookahead sequence",
            ),
            (
                "Offset",
                "LookAheadCoverage",
                "LookAheadGlyphCount",
                0,
                "Array of offsets to coverage tables in lookahead sequence, in glyph sequence order",
            ),
            ("uint16", "PosCount", None, None, "Number of PosLookupRecords"),
            (
                "struct",
                "PosLookupRecord",
                "PosCount",
                0,
                "Array of PosLookupRecords,in design order",
            ),
        ],
    ),
    (
        "ExtensionPosFormat1",
        [
            ("uint16", "ExtFormat", None, None, "Format identifier. Set to 1."),
            (
                "uint16",
                "ExtensionLookupType",
                None,
                None,
                "Lookup type of subtable referenced by ExtensionOffset (i.e. the extension subtable).",
            ),
            ("LOffset", "ExtSubTable", None, None, "Offset to SubTable"),
        ],
    ),
    # 	('ValueRecord', [
    # 		('int16', 'XPlacement', None, None, 'Horizontal adjustment for placement-in design units'),
    # 		('int16', 'YPlacement', None, None, 'Vertical adjustment for placement-in design units'),
    # 		('int16', 'XAdvance', None, None, 'Horizontal adjustment for advance-in design units (only used for horizontal writing)'),
    # 		('int16', 'YAdvance', None, None, 'Vertical adjustment for advance-in design units (only used for vertical writing)'),
    # 		('Offset', 'XPlaDevice', None, None, 'Offset to Device table for horizontal placement-measured from beginning of PosTable (may be NULL)'),
    # 		('Offset', 'YPlaDevice', None, None, 'Offset to Device table for vertical placement-measured from beginning of PosTable (may be NULL)'),
    # 		('Offset', 'XAdvDevice', None, None, 'Offset to Device table for horizontal advance-measured from beginning of PosTable (may be NULL)'),
    # 		('Offset', 'YAdvDevice', None, None, 'Offset to Device table for vertical advance-measured from beginning of PosTable (may be NULL)'),
    # 	]),
    (
        "AnchorFormat1",
        [
            ("uint16", "AnchorFormat", None, None, "Format identifier-format = 1"),
            ("int16", "XCoordinate", None, None, "Horizontal value-in design units"),
            ("int16", "YCoordinate", None, None, "Vertical value-in design units"),
        ],
    ),
    (
        "AnchorFormat2",
        [
            ("uint16", "AnchorFormat", None, None, "Format identifier-format = 2"),
            ("int16", "XCoordinate", None, None, "Horizontal value-in design units"),
            ("int16", "YCoordinate", None, None, "Vertical value-in design units"),
            ("uint16", "AnchorPoint", None, None, "Index to glyph contour point"),
        ],
    ),
    (
        "AnchorFormat3",
        [
            ("uint16", "AnchorFormat", None, None, "Format identifier-format = 3"),
            ("int16", "XCoordinate", None, None, "Horizontal value-in design units"),
            ("int16", "YCoordinate", None, None, "Vertical value-in design units"),
            (
                "Offset",
                "XDeviceTable",
                None,
                None,
                "Offset to Device table for X coordinate- from beginning of Anchor table (may be NULL)",
            ),
            (
                "Offset",
                "YDeviceTable",
                None,
                None,
                "Offset to Device table for Y coordinate- from beginning of Anchor table (may be NULL)",
            ),
        ],
    ),
    (
        "MarkArray",
        [
            ("uint16", "MarkCount", None, None, "Number of MarkRecords"),
            (
                "struct",
                "MarkRecord",
                "MarkCount",
                0,
                "Array of MarkRecords-in Coverage order",
            ),
        ],
    ),
    (
        "MarkRecord",
        [
            ("uint16", "Class", None, None, "Class defined for this mark"),
            (
                "Offset",
                "MarkAnchor",
                None,
                None,
                "Offset to Anchor table-from beginning of MarkArray table",
            ),
        ],
    ),
    #
    # gsub
    #
    (
        "GSUB",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the GSUB table- 0x00010000 or 0x00010001",
            ),
            (
                "Offset",
                "ScriptList",
                None,
                None,
                "Offset to ScriptList table-from beginning of GSUB table",
            ),
            (
                "Offset",
                "FeatureList",
                None,
                None,
                "Offset to FeatureList table-from beginning of GSUB table",
            ),
            (
                "Offset",
                "LookupList",
                None,
                None,
                "Offset to LookupList table-from beginning of GSUB table",
            ),
            (
                "LOffset",
                "FeatureVariations",
                None,
                "Version >= 0x00010001",
                "Offset to FeatureVariations table-from beginning of GSUB table",
            ),
        ],
    ),
    (
        "SingleSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "uint16",
                "DeltaGlyphID",
                None,
                None,
                "Add to original GlyphID modulo 65536 to get substitute GlyphID",
            ),
        ],
    ),
    (
        "SingleSubstFormat2",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of GlyphIDs in the Substitute array",
            ),
            (
                "GlyphID",
                "Substitute",
                "GlyphCount",
                0,
                "Array of substitute GlyphIDs-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "MultipleSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "uint16",
                "SequenceCount",
                None,
                None,
                "Number of Sequence table offsets in the Sequence array",
            ),
            (
                "Offset",
                "Sequence",
                "SequenceCount",
                0,
                "Array of offsets to Sequence tables-from beginning of Substitution table-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "Sequence",
        [
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of GlyphIDs in the Substitute array. This should always be greater than 0.",
            ),
            (
                "GlyphID",
                "Substitute",
                "GlyphCount",
                0,
                "String of GlyphIDs to substitute",
            ),
        ],
    ),
    (
        "AlternateSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "uint16",
                "AlternateSetCount",
                None,
                None,
                "Number of AlternateSet tables",
            ),
            (
                "Offset",
                "AlternateSet",
                "AlternateSetCount",
                0,
                "Array of offsets to AlternateSet tables-from beginning of Substitution table-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "AlternateSet",
        [
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of GlyphIDs in the Alternate array",
            ),
            (
                "GlyphID",
                "Alternate",
                "GlyphCount",
                0,
                "Array of alternate GlyphIDs-in arbitrary order",
            ),
        ],
    ),
    (
        "LigatureSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            ("uint16", "LigSetCount", None, None, "Number of LigatureSet tables"),
            (
                "Offset",
                "LigatureSet",
                "LigSetCount",
                0,
                "Array of offsets to LigatureSet tables-from beginning of Substitution table-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "LigatureSet",
        [
            ("uint16", "LigatureCount", None, None, "Number of Ligature tables"),
            (
                "Offset",
                "Ligature",
                "LigatureCount",
                0,
                "Array of offsets to Ligature tables-from beginning of LigatureSet table-ordered by preference",
            ),
        ],
    ),
    (
        "Ligature",
        [
            ("GlyphID", "LigGlyph", None, None, "GlyphID of ligature to substitute"),
            ("uint16", "CompCount", None, None, "Number of components in the ligature"),
            (
                "GlyphID",
                "Component",
                "CompCount",
                -1,
                "Array of component GlyphIDs-start with the second component-ordered in writing direction",
            ),
        ],
    ),
    (
        "SubstLookupRecord",
        [
            (
                "uint16",
                "SequenceIndex",
                None,
                None,
                "Index into current glyph sequence-first glyph = 0",
            ),
            (
                "uint16",
                "LookupListIndex",
                None,
                None,
                "Lookup to apply to that position-zero-based",
            ),
        ],
    ),
    (
        "ContextSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "uint16",
                "SubRuleSetCount",
                None,
                None,
                "Number of SubRuleSet tables-must equal GlyphCount in Coverage table",
            ),
            (
                "Offset",
                "SubRuleSet",
                "SubRuleSetCount",
                0,
                "Array of offsets to SubRuleSet tables-from beginning of Substitution table-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "SubRuleSet",
        [
            ("uint16", "SubRuleCount", None, None, "Number of SubRule tables"),
            (
                "Offset",
                "SubRule",
                "SubRuleCount",
                0,
                "Array of offsets to SubRule tables-from beginning of SubRuleSet table-ordered by preference",
            ),
        ],
    ),
    (
        "SubRule",
        [
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Total number of glyphs in input glyph sequence-includes the first glyph",
            ),
            ("uint16", "SubstCount", None, None, "Number of SubstLookupRecords"),
            (
                "GlyphID",
                "Input",
                "GlyphCount",
                -1,
                "Array of input GlyphIDs-start with second glyph",
            ),
            (
                "struct",
                "SubstLookupRecord",
                "SubstCount",
                0,
                "Array of SubstLookupRecords-in design order",
            ),
        ],
    ),
    (
        "ContextSubstFormat2",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "Offset",
                "ClassDef",
                None,
                None,
                "Offset to glyph ClassDef table-from beginning of Substitution table",
            ),
            ("uint16", "SubClassSetCount", None, None, "Number of SubClassSet tables"),
            (
                "Offset",
                "SubClassSet",
                "SubClassSetCount",
                0,
                "Array of offsets to SubClassSet tables-from beginning of Substitution table-ordered by class-may be NULL",
            ),
        ],
    ),
    (
        "SubClassSet",
        [
            (
                "uint16",
                "SubClassRuleCount",
                None,
                None,
                "Number of SubClassRule tables",
            ),
            (
                "Offset",
                "SubClassRule",
                "SubClassRuleCount",
                0,
                "Array of offsets to SubClassRule tables-from beginning of SubClassSet-ordered by preference",
            ),
        ],
    ),
    (
        "SubClassRule",
        [
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Total number of classes specified for the context in the rule-includes the first class",
            ),
            ("uint16", "SubstCount", None, None, "Number of SubstLookupRecords"),
            (
                "uint16",
                "Class",
                "GlyphCount",
                -1,
                "Array of classes-beginning with the second class-to be matched to the input glyph class sequence",
            ),
            (
                "struct",
                "SubstLookupRecord",
                "SubstCount",
                0,
                "Array of Substitution lookups-in design order",
            ),
        ],
    ),
    (
        "ContextSubstFormat3",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 3"),
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of glyphs in the input glyph sequence",
            ),
            ("uint16", "SubstCount", None, None, "Number of SubstLookupRecords"),
            (
                "Offset",
                "Coverage",
                "GlyphCount",
                0,
                "Array of offsets to Coverage table-from beginning of Substitution table-in glyph sequence order",
            ),
            (
                "struct",
                "SubstLookupRecord",
                "SubstCount",
                0,
                "Array of SubstLookupRecords-in design order",
            ),
        ],
    ),
    (
        "ChainContextSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "uint16",
                "ChainSubRuleSetCount",
                None,
                None,
                "Number of ChainSubRuleSet tables-must equal GlyphCount in Coverage table",
            ),
            (
                "Offset",
                "ChainSubRuleSet",
                "ChainSubRuleSetCount",
                0,
                "Array of offsets to ChainSubRuleSet tables-from beginning of Substitution table-ordered by Coverage Index",
            ),
        ],
    ),
    (
        "ChainSubRuleSet",
        [
            (
                "uint16",
                "ChainSubRuleCount",
                None,
                None,
                "Number of ChainSubRule tables",
            ),
            (
                "Offset",
                "ChainSubRule",
                "ChainSubRuleCount",
                0,
                "Array of offsets to ChainSubRule tables-from beginning of ChainSubRuleSet table-ordered by preference",
            ),
        ],
    ),
    (
        "ChainSubRule",
        [
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Total number of glyphs in the backtrack sequence (number of glyphs to be matched before the first glyph)",
            ),
            (
                "GlyphID",
                "Backtrack",
                "BacktrackGlyphCount",
                0,
                "Array of backtracking GlyphID's (to be matched before the input sequence)",
            ),
            (
                "uint16",
                "InputGlyphCount",
                None,
                None,
                "Total number of glyphs in the input sequence (includes the first glyph)",
            ),
            (
                "GlyphID",
                "Input",
                "InputGlyphCount",
                -1,
                "Array of input GlyphIDs (start with second glyph)",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Total number of glyphs in the look ahead sequence (number of glyphs to be matched after the input sequence)",
            ),
            (
                "GlyphID",
                "LookAhead",
                "LookAheadGlyphCount",
                0,
                "Array of lookahead GlyphID's (to be matched after the input sequence)",
            ),
            ("uint16", "SubstCount", None, None, "Number of SubstLookupRecords"),
            (
                "struct",
                "SubstLookupRecord",
                "SubstCount",
                0,
                "Array of SubstLookupRecords (in design order)",
            ),
        ],
    ),
    (
        "ChainContextSubstFormat2",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 2"),
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table-from beginning of Substitution table",
            ),
            (
                "Offset",
                "BacktrackClassDef",
                None,
                None,
                "Offset to glyph ClassDef table containing backtrack sequence data-from beginning of Substitution table",
            ),
            (
                "Offset",
                "InputClassDef",
                None,
                None,
                "Offset to glyph ClassDef table containing input sequence data-from beginning of Substitution table",
            ),
            (
                "Offset",
                "LookAheadClassDef",
                None,
                None,
                "Offset to glyph ClassDef table containing lookahead sequence data-from beginning of Substitution table",
            ),
            (
                "uint16",
                "ChainSubClassSetCount",
                None,
                None,
                "Number of ChainSubClassSet tables",
            ),
            (
                "Offset",
                "ChainSubClassSet",
                "ChainSubClassSetCount",
                0,
                "Array of offsets to ChainSubClassSet tables-from beginning of Substitution table-ordered by input class-may be NULL",
            ),
        ],
    ),
    (
        "ChainSubClassSet",
        [
            (
                "uint16",
                "ChainSubClassRuleCount",
                None,
                None,
                "Number of ChainSubClassRule tables",
            ),
            (
                "Offset",
                "ChainSubClassRule",
                "ChainSubClassRuleCount",
                0,
                "Array of offsets to ChainSubClassRule tables-from beginning of ChainSubClassSet-ordered by preference",
            ),
        ],
    ),
    (
        "ChainSubClassRule",
        [
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Total number of glyphs in the backtrack sequence (number of glyphs to be matched before the first glyph)",
            ),
            (
                "uint16",
                "Backtrack",
                "BacktrackGlyphCount",
                0,
                "Array of backtracking classes(to be matched before the input sequence)",
            ),
            (
                "uint16",
                "InputGlyphCount",
                None,
                None,
                "Total number of classes in the input sequence (includes the first class)",
            ),
            (
                "uint16",
                "Input",
                "InputGlyphCount",
                -1,
                "Array of input classes(start with second class; to be matched with the input glyph sequence)",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Total number of classes in the look ahead sequence (number of classes to be matched after the input sequence)",
            ),
            (
                "uint16",
                "LookAhead",
                "LookAheadGlyphCount",
                0,
                "Array of lookahead classes(to be matched after the input sequence)",
            ),
            ("uint16", "SubstCount", None, None, "Number of SubstLookupRecords"),
            (
                "struct",
                "SubstLookupRecord",
                "SubstCount",
                0,
                "Array of SubstLookupRecords (in design order)",
            ),
        ],
    ),
    (
        "ChainContextSubstFormat3",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 3"),
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Number of glyphs in the backtracking sequence",
            ),
            (
                "Offset",
                "BacktrackCoverage",
                "BacktrackGlyphCount",
                0,
                "Array of offsets to coverage tables in backtracking sequence, in glyph sequence order",
            ),
            (
                "uint16",
                "InputGlyphCount",
                None,
                None,
                "Number of glyphs in input sequence",
            ),
            (
                "Offset",
                "InputCoverage",
                "InputGlyphCount",
                0,
                "Array of offsets to coverage tables in input sequence, in glyph sequence order",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Number of glyphs in lookahead sequence",
            ),
            (
                "Offset",
                "LookAheadCoverage",
                "LookAheadGlyphCount",
                0,
                "Array of offsets to coverage tables in lookahead sequence, in glyph sequence order",
            ),
            ("uint16", "SubstCount", None, None, "Number of SubstLookupRecords"),
            (
                "struct",
                "SubstLookupRecord",
                "SubstCount",
                0,
                "Array of SubstLookupRecords, in design order",
            ),
        ],
    ),
    (
        "ExtensionSubstFormat1",
        [
            ("uint16", "ExtFormat", None, None, "Format identifier. Set to 1."),
            (
                "uint16",
                "ExtensionLookupType",
                None,
                None,
                "Lookup type of subtable referenced by ExtensionOffset (i.e. the extension subtable).",
            ),
            (
                "LOffset",
                "ExtSubTable",
                None,
                None,
                "Array of offsets to Lookup tables-from beginning of LookupList -zero based (first lookup is Lookup index = 0)",
            ),
        ],
    ),
    (
        "ReverseChainSingleSubstFormat1",
        [
            ("uint16", "SubstFormat", None, None, "Format identifier-format = 1"),
            (
                "Offset",
                "Coverage",
                None,
                0,
                "Offset to Coverage table - from beginning of Substitution table",
            ),
            (
                "uint16",
                "BacktrackGlyphCount",
                None,
                None,
                "Number of glyphs in the backtracking sequence",
            ),
            (
                "Offset",
                "BacktrackCoverage",
                "BacktrackGlyphCount",
                0,
                "Array of offsets to coverage tables in backtracking sequence, in glyph sequence order",
            ),
            (
                "uint16",
                "LookAheadGlyphCount",
                None,
                None,
                "Number of glyphs in lookahead sequence",
            ),
            (
                "Offset",
                "LookAheadCoverage",
                "LookAheadGlyphCount",
                0,
                "Array of offsets to coverage tables in lookahead sequence, in glyph sequence order",
            ),
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of GlyphIDs in the Substitute array",
            ),
            (
                "GlyphID",
                "Substitute",
                "GlyphCount",
                0,
                "Array of substitute GlyphIDs-ordered by Coverage index",
            ),
        ],
    ),
    #
    # gdef
    #
    (
        "GDEF",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the GDEF table- 0x00010000, 0x00010002, or 0x00010003",
            ),
            (
                "Offset",
                "GlyphClassDef",
                None,
                None,
                "Offset to class definition table for glyph type-from beginning of GDEF header (may be NULL)",
            ),
            (
                "Offset",
                "AttachList",
                None,
                None,
                "Offset to list of glyphs with attachment points-from beginning of GDEF header (may be NULL)",
            ),
            (
                "Offset",
                "LigCaretList",
                None,
                None,
                "Offset to list of positioning points for ligature carets-from beginning of GDEF header (may be NULL)",
            ),
            (
                "Offset",
                "MarkAttachClassDef",
                None,
                None,
                "Offset to class definition table for mark attachment type-from beginning of GDEF header (may be NULL)",
            ),
            (
                "Offset",
                "MarkGlyphSetsDef",
                None,
                "Version >= 0x00010002",
                "Offset to the table of mark set definitions-from beginning of GDEF header (may be NULL)",
            ),
            (
                "LOffset",
                "VarStore",
                None,
                "Version >= 0x00010003",
                "Offset to variation store (may be NULL)",
            ),
        ],
    ),
    (
        "AttachList",
        [
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table - from beginning of AttachList table",
            ),
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of glyphs with attachment points",
            ),
            (
                "Offset",
                "AttachPoint",
                "GlyphCount",
                0,
                "Array of offsets to AttachPoint tables-from beginning of AttachList table-in Coverage Index order",
            ),
        ],
    ),
    (
        "AttachPoint",
        [
            (
                "uint16",
                "PointCount",
                None,
                None,
                "Number of attachment points on this glyph",
            ),
            (
                "uint16",
                "PointIndex",
                "PointCount",
                0,
                "Array of contour point indices -in increasing numerical order",
            ),
        ],
    ),
    (
        "LigCaretList",
        [
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table - from beginning of LigCaretList table",
            ),
            ("uint16", "LigGlyphCount", None, None, "Number of ligature glyphs"),
            (
                "Offset",
                "LigGlyph",
                "LigGlyphCount",
                0,
                "Array of offsets to LigGlyph tables-from beginning of LigCaretList table-in Coverage Index order",
            ),
        ],
    ),
    (
        "LigGlyph",
        [
            (
                "uint16",
                "CaretCount",
                None,
                None,
                "Number of CaretValues for this ligature (components - 1)",
            ),
            (
                "Offset",
                "CaretValue",
                "CaretCount",
                0,
                "Array of offsets to CaretValue tables-from beginning of LigGlyph table-in increasing coordinate order",
            ),
        ],
    ),
    (
        "CaretValueFormat1",
        [
            ("uint16", "CaretValueFormat", None, None, "Format identifier-format = 1"),
            ("int16", "Coordinate", None, None, "X or Y value, in design units"),
        ],
    ),
    (
        "CaretValueFormat2",
        [
            ("uint16", "CaretValueFormat", None, None, "Format identifier-format = 2"),
            ("uint16", "CaretValuePoint", None, None, "Contour point index on glyph"),
        ],
    ),
    (
        "CaretValueFormat3",
        [
            ("uint16", "CaretValueFormat", None, None, "Format identifier-format = 3"),
            ("int16", "Coordinate", None, None, "X or Y value, in design units"),
            (
                "Offset",
                "DeviceTable",
                None,
                None,
                "Offset to Device table for X or Y value-from beginning of CaretValue table",
            ),
        ],
    ),
    (
        "MarkGlyphSetsDef",
        [
            ("uint16", "MarkSetTableFormat", None, None, "Format identifier == 1"),
            ("uint16", "MarkSetCount", None, None, "Number of mark sets defined"),
            (
                "LOffset",
                "Coverage",
                "MarkSetCount",
                0,
                "Array of offsets to mark set coverage tables.",
            ),
        ],
    ),
    #
    # base
    #
    (
        "BASE",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the BASE table-initially 0x00010000",
            ),
            (
                "Offset",
                "HorizAxis",
                None,
                None,
                "Offset to horizontal Axis table-from beginning of BASE table-may be NULL",
            ),
            (
                "Offset",
                "VertAxis",
                None,
                None,
                "Offset to vertical Axis table-from beginning of BASE table-may be NULL",
            ),
            (
                "LOffset",
                "VarStore",
                None,
                "Version >= 0x00010001",
                "Offset to variation store (may be NULL)",
            ),
        ],
    ),
    (
        "Axis",
        [
            (
                "Offset",
                "BaseTagList",
                None,
                None,
                "Offset to BaseTagList table-from beginning of Axis table-may be NULL",
            ),
            (
                "Offset",
                "BaseScriptList",
                None,
                None,
                "Offset to BaseScriptList table-from beginning of Axis table",
            ),
        ],
    ),
    (
        "BaseTagList",
        [
            (
                "uint16",
                "BaseTagCount",
                None,
                None,
                "Number of baseline identification tags in this text direction-may be zero (0)",
            ),
            (
                "Tag",
                "BaselineTag",
                "BaseTagCount",
                0,
                "Array of 4-byte baseline identification tags-must be in alphabetical order",
            ),
        ],
    ),
    (
        "BaseScriptList",
        [
            (
                "uint16",
                "BaseScriptCount",
                None,
                None,
                "Number of BaseScriptRecords defined",
            ),
            (
                "struct",
                "BaseScriptRecord",
                "BaseScriptCount",
                0,
                "Array of BaseScriptRecords-in alphabetical order by BaseScriptTag",
            ),
        ],
    ),
    (
        "BaseScriptRecord",
        [
            ("Tag", "BaseScriptTag", None, None, "4-byte script identification tag"),
            (
                "Offset",
                "BaseScript",
                None,
                None,
                "Offset to BaseScript table-from beginning of BaseScriptList",
            ),
        ],
    ),
    (
        "BaseScript",
        [
            (
                "Offset",
                "BaseValues",
                None,
                None,
                "Offset to BaseValues table-from beginning of BaseScript table-may be NULL",
            ),
            (
                "Offset",
                "DefaultMinMax",
                None,
                None,
                "Offset to MinMax table- from beginning of BaseScript table-may be NULL",
            ),
            (
                "uint16",
                "BaseLangSysCount",
                None,
                None,
                "Number of BaseLangSysRecords defined-may be zero (0)",
            ),
            (
                "struct",
                "BaseLangSysRecord",
                "BaseLangSysCount",
                0,
                "Array of BaseLangSysRecords-in alphabetical order by BaseLangSysTag",
            ),
        ],
    ),
    (
        "BaseLangSysRecord",
        [
            (
                "Tag",
                "BaseLangSysTag",
                None,
                None,
                "4-byte language system identification tag",
            ),
            (
                "Offset",
                "MinMax",
                None,
                None,
                "Offset to MinMax table-from beginning of BaseScript table",
            ),
        ],
    ),
    (
        "BaseValues",
        [
            (
                "uint16",
                "DefaultIndex",
                None,
                None,
                "Index number of default baseline for this script-equals index position of baseline tag in BaselineArray of the BaseTagList",
            ),
            (
                "uint16",
                "BaseCoordCount",
                None,
                None,
                "Number of BaseCoord tables defined-should equal BaseTagCount in the BaseTagList",
            ),
            (
                "Offset",
                "BaseCoord",
                "BaseCoordCount",
                0,
                "Array of offsets to BaseCoord-from beginning of BaseValues table-order matches BaselineTag array in the BaseTagList",
            ),
        ],
    ),
    (
        "MinMax",
        [
            (
                "Offset",
                "MinCoord",
                None,
                None,
                "Offset to BaseCoord table-defines minimum extent value-from the beginning of MinMax table-may be NULL",
            ),
            (
                "Offset",
                "MaxCoord",
                None,
                None,
                "Offset to BaseCoord table-defines maximum extent value-from the beginning of MinMax table-may be NULL",
            ),
            (
                "uint16",
                "FeatMinMaxCount",
                None,
                None,
                "Number of FeatMinMaxRecords-may be zero (0)",
            ),
            (
                "struct",
                "FeatMinMaxRecord",
                "FeatMinMaxCount",
                0,
                "Array of FeatMinMaxRecords-in alphabetical order, by FeatureTableTag",
            ),
        ],
    ),
    (
        "FeatMinMaxRecord",
        [
            (
                "Tag",
                "FeatureTableTag",
                None,
                None,
                "4-byte feature identification tag-must match FeatureTag in FeatureList",
            ),
            (
                "Offset",
                "MinCoord",
                None,
                None,
                "Offset to BaseCoord table-defines minimum extent value-from beginning of MinMax table-may be NULL",
            ),
            (
                "Offset",
                "MaxCoord",
                None,
                None,
                "Offset to BaseCoord table-defines maximum extent value-from beginning of MinMax table-may be NULL",
            ),
        ],
    ),
    (
        "BaseCoordFormat1",
        [
            ("uint16", "BaseCoordFormat", None, None, "Format identifier-format = 1"),
            ("int16", "Coordinate", None, None, "X or Y value, in design units"),
        ],
    ),
    (
        "BaseCoordFormat2",
        [
            ("uint16", "BaseCoordFormat", None, None, "Format identifier-format = 2"),
            ("int16", "Coordinate", None, None, "X or Y value, in design units"),
            ("GlyphID", "ReferenceGlyph", None, None, "GlyphID of control glyph"),
            (
                "uint16",
                "BaseCoordPoint",
                None,
                None,
                "Index of contour point on the ReferenceGlyph",
            ),
        ],
    ),
    (
        "BaseCoordFormat3",
        [
            ("uint16", "BaseCoordFormat", None, None, "Format identifier-format = 3"),
            ("int16", "Coordinate", None, None, "X or Y value, in design units"),
            (
                "Offset",
                "DeviceTable",
                None,
                None,
                "Offset to Device table for X or Y value",
            ),
        ],
    ),
    #
    # jstf
    #
    (
        "JSTF",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the JSTF table-initially set to 0x00010000",
            ),
            (
                "uint16",
                "JstfScriptCount",
                None,
                None,
                "Number of JstfScriptRecords in this table",
            ),
            (
                "struct",
                "JstfScriptRecord",
                "JstfScriptCount",
                0,
                "Array of JstfScriptRecords-in alphabetical order, by JstfScriptTag",
            ),
        ],
    ),
    (
        "JstfScriptRecord",
        [
            ("Tag", "JstfScriptTag", None, None, "4-byte JstfScript identification"),
            (
                "Offset",
                "JstfScript",
                None,
                None,
                "Offset to JstfScript table-from beginning of JSTF Header",
            ),
        ],
    ),
    (
        "JstfScript",
        [
            (
                "Offset",
                "ExtenderGlyph",
                None,
                None,
                "Offset to ExtenderGlyph table-from beginning of JstfScript table-may be NULL",
            ),
            (
                "Offset",
                "DefJstfLangSys",
                None,
                None,
                "Offset to Default JstfLangSys table-from beginning of JstfScript table-may be NULL",
            ),
            (
                "uint16",
                "JstfLangSysCount",
                None,
                None,
                "Number of JstfLangSysRecords in this table- may be zero (0)",
            ),
            (
                "struct",
                "JstfLangSysRecord",
                "JstfLangSysCount",
                0,
                "Array of JstfLangSysRecords-in alphabetical order, by JstfLangSysTag",
            ),
        ],
    ),
    (
        "JstfLangSysRecord",
        [
            ("Tag", "JstfLangSysTag", None, None, "4-byte JstfLangSys identifier"),
            (
                "Offset",
                "JstfLangSys",
                None,
                None,
                "Offset to JstfLangSys table-from beginning of JstfScript table",
            ),
        ],
    ),
    (
        "ExtenderGlyph",
        [
            (
                "uint16",
                "GlyphCount",
                None,
                None,
                "Number of Extender Glyphs in this script",
            ),
            (
                "GlyphID",
                "ExtenderGlyph",
                "GlyphCount",
                0,
                "GlyphIDs-in increasing numerical order",
            ),
        ],
    ),
    (
        "JstfLangSys",
        [
            (
                "uint16",
                "JstfPriorityCount",
                None,
                None,
                "Number of JstfPriority tables",
            ),
            (
                "Offset",
                "JstfPriority",
                "JstfPriorityCount",
                0,
                "Array of offsets to JstfPriority tables-from beginning of JstfLangSys table-in priority order",
            ),
        ],
    ),
    (
        "JstfPriority",
        [
            (
                "Offset",
                "ShrinkageEnableGSUB",
                None,
                None,
                "Offset to Shrinkage Enable JstfGSUBModList table-from beginning of JstfPriority table-may be NULL",
            ),
            (
                "Offset",
                "ShrinkageDisableGSUB",
                None,
                None,
                "Offset to Shrinkage Disable JstfGSUBModList table-from beginning of JstfPriority table-may be NULL",
            ),
            (
                "Offset",
                "ShrinkageEnableGPOS",
                None,
                None,
                "Offset to Shrinkage Enable JstfGPOSModList table-from beginning of JstfPriority table-may be NULL",
            ),
            (
                "Offset",
                "ShrinkageDisableGPOS",
                None,
                None,
                "Offset to Shrinkage Disable JstfGPOSModList table-from beginning of JstfPriority table-may be NULL",
            ),
            (
                "Offset",
                "ShrinkageJstfMax",
                None,
                None,
                "Offset to Shrinkage JstfMax table-from beginning of JstfPriority table -may be NULL",
            ),
            (
                "Offset",
                "ExtensionEnableGSUB",
                None,
                None,
                "Offset to Extension Enable JstfGSUBModList table-may be NULL",
            ),
            (
                "Offset",
                "ExtensionDisableGSUB",
                None,
                None,
                "Offset to Extension Disable JstfGSUBModList table-from beginning of JstfPriority table-may be NULL",
            ),
            (
                "Offset",
                "ExtensionEnableGPOS",
                None,
                None,
                "Offset to Extension Enable JstfGSUBModList table-may be NULL",
            ),
            (
                "Offset",
                "ExtensionDisableGPOS",
                None,
                None,
                "Offset to Extension Disable JstfGSUBModList table-from beginning of JstfPriority table-may be NULL",
            ),
            (
                "Offset",
                "ExtensionJstfMax",
                None,
                None,
                "Offset to Extension JstfMax table-from beginning of JstfPriority table -may be NULL",
            ),
        ],
    ),
    (
        "JstfGSUBModList",
        [
            (
                "uint16",
                "LookupCount",
                None,
                None,
                "Number of lookups for this modification",
            ),
            (
                "uint16",
                "GSUBLookupIndex",
                "LookupCount",
                0,
                "Array of LookupIndex identifiers in GSUB-in increasing numerical order",
            ),
        ],
    ),
    (
        "JstfGPOSModList",
        [
            (
                "uint16",
                "LookupCount",
                None,
                None,
                "Number of lookups for this modification",
            ),
            (
                "uint16",
                "GPOSLookupIndex",
                "LookupCount",
                0,
                "Array of LookupIndex identifiers in GPOS-in increasing numerical order",
            ),
        ],
    ),
    (
        "JstfMax",
        [
            (
                "uint16",
                "LookupCount",
                None,
                None,
                "Number of lookup Indices for this modification",
            ),
            (
                "Offset",
                "Lookup",
                "LookupCount",
                0,
                "Array of offsets to GPOS-type lookup tables-from beginning of JstfMax table-in design order",
            ),
        ],
    ),
    #
    # STAT
    #
    (
        "STAT",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the table-initially set to 0x00010000, currently 0x00010002.",
            ),
            (
                "uint16",
                "DesignAxisRecordSize",
                None,
                None,
                "Size in bytes of each design axis record",
            ),
            ("uint16", "DesignAxisCount", None, None, "Number of design axis records"),
            (
                "LOffsetTo(AxisRecordArray)",
                "DesignAxisRecord",
                None,
                None,
                "Offset in bytes from the beginning of the STAT table to the start of the design axes array",
            ),
            ("uint16", "AxisValueCount", None, None, "Number of axis value tables"),
            (
                "LOffsetTo(AxisValueArray)",
                "AxisValueArray",
                None,
                None,
                "Offset in bytes from the beginning of the STAT table to the start of the axes value offset array",
            ),
            (
                "NameID",
                "ElidedFallbackNameID",
                None,
                "Version >= 0x00010001",
                "NameID to use when all style attributes are elided.",
            ),
        ],
    ),
    (
        "AxisRecordArray",
        [
            ("AxisRecord", "Axis", "DesignAxisCount", 0, "Axis records"),
        ],
    ),
    (
        "AxisRecord",
        [
            (
                "Tag",
                "AxisTag",
                None,
                None,
                "A tag identifying the axis of design variation",
            ),
            (
                "NameID",
                "AxisNameID",
                None,
                None,
                'The name ID for entries in the "name" table that provide a display string for this axis',
            ),
            (
                "uint16",
                "AxisOrdering",
                None,
                None,
                "A value that applications can use to determine primary sorting of face names, or for ordering of descriptors when composing family or face names",
            ),
            (
                "uint8",
                "MoreBytes",
                "DesignAxisRecordSize",
                -8,
                "Extra bytes.  Set to empty array.",
            ),
        ],
    ),
    (
        "AxisValueArray",
        [
            ("Offset", "AxisValue", "AxisValueCount", 0, "Axis values"),
        ],
    ),
    (
        "AxisValueFormat1",
        [
            ("uint16", "Format", None, None, "Format, = 1"),
            (
                "uint16",
                "AxisIndex",
                None,
                None,
                "Index into the axis record array identifying the axis of design variation to which the axis value record applies.",
            ),
            ("STATFlags", "Flags", None, None, "Flags."),
            ("NameID", "ValueNameID", None, None, ""),
            ("Fixed", "Value", None, None, ""),
        ],
    ),
    (
        "AxisValueFormat2",
        [
            ("uint16", "Format", None, None, "Format, = 2"),
            (
                "uint16",
                "AxisIndex",
                None,
                None,
                "Index into the axis record array identifying the axis of design variation to which the axis value record applies.",
            ),
            ("STATFlags", "Flags", None, None, "Flags."),
            ("NameID", "ValueNameID", None, None, ""),
            ("Fixed", "NominalValue", None, None, ""),
            ("Fixed", "RangeMinValue", None, None, ""),
            ("Fixed", "RangeMaxValue", None, None, ""),
        ],
    ),
    (
        "AxisValueFormat3",
        [
            ("uint16", "Format", None, None, "Format, = 3"),
            (
                "uint16",
                "AxisIndex",
                None,
                None,
                "Index into the axis record array identifying the axis of design variation to which the axis value record applies.",
            ),
            ("STATFlags", "Flags", None, None, "Flags."),
            ("NameID", "ValueNameID", None, None, ""),
            ("Fixed", "Value", None, None, ""),
            ("Fixed", "LinkedValue", None, None, ""),
        ],
    ),
    (
        "AxisValueFormat4",
        [
            ("uint16", "Format", None, None, "Format, = 4"),
            (
                "uint16",
                "AxisCount",
                None,
                None,
                "The total number of axes contributing to this axis-values combination.",
            ),
            ("STATFlags", "Flags", None, None, "Flags."),
            ("NameID", "ValueNameID", None, None, ""),
            (
                "struct",
                "AxisValueRecord",
                "AxisCount",
                0,
                "Array of AxisValue records that provide the combination of axis values, one for each contributing axis. ",
            ),
        ],
    ),
    (
        "AxisValueRecord",
        [
            (
                "uint16",
                "AxisIndex",
                None,
                None,
                "Index into the axis record array identifying the axis of design variation to which the axis value record applies.",
            ),
            ("Fixed", "Value", None, None, "A numeric value for this attribute value."),
        ],
    ),
    #
    # Variation fonts
    #
    # GSUB/GPOS FeatureVariations
    (
        "FeatureVariations",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the table-initially set to 0x00010000",
            ),
            (
                "uint32",
                "FeatureVariationCount",
                None,
                None,
                "Number of records in the FeatureVariationRecord array",
            ),
            (
                "struct",
                "FeatureVariationRecord",
                "FeatureVariationCount",
                0,
                "Array of FeatureVariationRecord",
            ),
        ],
    ),
    (
        "FeatureVariationRecord",
        [
            (
                "LOffset",
                "ConditionSet",
                None,
                None,
                "Offset to a ConditionSet table, from beginning of the FeatureVariations table.",
            ),
            (
                "LOffset",
                "FeatureTableSubstitution",
                None,
                None,
                "Offset to a FeatureTableSubstitution table, from beginning of the FeatureVariations table",
            ),
        ],
    ),
    (
        "ConditionList",
        [
            (
                "uint32",
                "ConditionCount",
                None,
                None,
                "Number of condition tables in the ConditionTable array",
            ),
            (
                "LOffset",
                "ConditionTable",
                "ConditionCount",
                0,
                "Array of offset to condition tables, from the beginning of the ConditionList table.",
            ),
        ],
    ),
    (
        "ConditionSet",
        [
            (
                "uint16",
                "ConditionCount",
                None,
                None,
                "Number of condition tables in the ConditionTable array",
            ),
            (
                "LOffset",
                "ConditionTable",
                "ConditionCount",
                0,
                "Array of offset to condition tables, from the beginning of the ConditionSet table.",
            ),
        ],
    ),
    (
        "ConditionTableFormat1",
        [
            ("uint16", "Format", None, None, "Format, = 1"),
            (
                "uint16",
                "AxisIndex",
                None,
                None,
                "Index for the variation axis within the fvar table, base 0.",
            ),
            (
                "F2Dot14",
                "FilterRangeMinValue",
                None,
                None,
                "Minimum normalized axis value of the font variation instances that satisfy this condition.",
            ),
            (
                "F2Dot14",
                "FilterRangeMaxValue",
                None,
                None,
                "Maximum value that satisfies this condition.",
            ),
        ],
    ),
    (
        "ConditionTableFormat2",
        [
            ("uint16", "Format", None, None, "Format, = 2"),
            (
                "int16",
                "DefaultValue",
                None,
                None,
                "Value at default instance.",
            ),
            (
                "uint32",
                "VarIdx",
                None,
                None,
                "Variation index to vary the value based on current designspace location.",
            ),
        ],
    ),
    (
        "ConditionTableFormat3",
        [
            ("uint16", "Format", None, None, "Format, = 3"),
            (
                "uint8",
                "ConditionCount",
                None,
                None,
                "Index for the variation axis within the fvar table, base 0.",
            ),
            (
                "Offset24",
                "ConditionTable",
                "ConditionCount",
                0,
                "Array of condition tables for this conjunction (AND) expression.",
            ),
        ],
    ),
    (
        "ConditionTableFormat4",
        [
            ("uint16", "Format", None, None, "Format, = 4"),
            (
                "uint8",
                "ConditionCount",
                None,
                None,
                "Index for the variation axis within the fvar table, base 0.",
            ),
            (
                "Offset24",
                "ConditionTable",
                "ConditionCount",
                0,
                "Array of condition tables for this disjunction (OR) expression.",
            ),
        ],
    ),
    (
        "ConditionTableFormat5",
        [
            ("uint16", "Format", None, None, "Format, = 5"),
            (
                "Offset24",
                "ConditionTable",
                None,
                None,
                "Condition to negate.",
            ),
        ],
    ),
    (
        "FeatureTableSubstitution",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the table-initially set to 0x00010000",
            ),
            (
                "uint16",
                "SubstitutionCount",
                None,
                None,
                "Number of records in the FeatureVariationRecords array",
            ),
            (
                "FeatureTableSubstitutionRecord",
                "SubstitutionRecord",
                "SubstitutionCount",
                0,
                "Array of FeatureTableSubstitutionRecord",
            ),
        ],
    ),
    (
        "FeatureTableSubstitutionRecord",
        [
            ("uint16", "FeatureIndex", None, None, "The feature table index to match."),
            (
                "LOffset",
                "Feature",
                None,
                None,
                "Offset to an alternate feature table, from start of the FeatureTableSubstitution table.",
            ),
        ],
    ),
    # VariationStore
    (
        "VarRegionAxis",
        [
            ("F2Dot14", "StartCoord", None, None, ""),
            ("F2Dot14", "PeakCoord", None, None, ""),
            ("F2Dot14", "EndCoord", None, None, ""),
        ],
    ),
    (
        "VarRegion",
        [
            ("struct", "VarRegionAxis", "RegionAxisCount", 0, ""),
        ],
    ),
    (
        "VarRegionList",
        [
            ("uint16", "RegionAxisCount", None, None, ""),
            ("uint16", "RegionCount", None, None, ""),
            ("VarRegion", "Region", "RegionCount", 0, ""),
        ],
    ),
    (
        "VarData",
        [
            ("uint16", "ItemCount", None, None, ""),
            ("uint16", "NumShorts", None, None, ""),
            ("uint16", "VarRegionCount", None, None, ""),
            ("uint16", "VarRegionIndex", "VarRegionCount", 0, ""),
            ("VarDataValue", "Item", "ItemCount", 0, ""),
        ],
    ),
    (
        "VarStore",
        [
            ("uint16", "Format", None, None, "Set to 1."),
            ("LOffset", "VarRegionList", None, None, ""),
            ("uint16", "VarDataCount", None, None, ""),
            ("LOffset", "VarData", "VarDataCount", 0, ""),
        ],
    ),
    # Variation helpers
    (
        "VarIdxMap",
        [
            ("uint16", "EntryFormat", None, None, ""),  # Automatically computed
            ("uint16", "MappingCount", None, None, ""),  # Automatically computed
            ("VarIdxMapValue", "mapping", "", 0, "Array of compressed data"),
        ],
    ),
    (
        "DeltaSetIndexMapFormat0",
        [
            ("uint8", "Format", None, None, "Format of the DeltaSetIndexMap = 0"),
            ("uint8", "EntryFormat", None, None, ""),  # Automatically computed
            ("uint16", "MappingCount", None, None, ""),  # Automatically computed
            ("VarIdxMapValue", "mapping", "", 0, "Array of compressed data"),
        ],
    ),
    (
        "DeltaSetIndexMapFormat1",
        [
            ("uint8", "Format", None, None, "Format of the DeltaSetIndexMap = 1"),
            ("uint8", "EntryFormat", None, None, ""),  # Automatically computed
            ("uint32", "MappingCount", None, None, ""),  # Automatically computed
            ("VarIdxMapValue", "mapping", "", 0, "Array of compressed data"),
        ],
    ),
    # MultiVariationStore
    (
        "SparseVarRegionAxis",
        [
            ("uint16", "AxisIndex", None, None, ""),
            ("F2Dot14", "StartCoord", None, None, ""),
            ("F2Dot14", "PeakCoord", None, None, ""),
            ("F2Dot14", "EndCoord", None, None, ""),
        ],
    ),
    (
        "SparseVarRegion",
        [
            ("uint16", "SparseRegionCount", None, None, ""),
            ("struct", "SparseVarRegionAxis", "SparseRegionCount", 0, ""),
        ],
    ),
    (
        "SparseVarRegionList",
        [
            ("uint16", "RegionCount", None, None, ""),
            ("LOffsetTo(SparseVarRegion)", "Region", "RegionCount", 0, ""),
        ],
    ),
    (
        "MultiVarData",
        [
            ("uint8", "Format", None, None, "Set to 1."),
            ("uint16", "VarRegionCount", None, None, ""),
            ("uint16", "VarRegionIndex", "VarRegionCount", 0, ""),
            ("TupleList", "Item", "", 0, ""),
        ],
    ),
    (
        "MultiVarStore",
        [
            ("uint16", "Format", None, None, "Set to 1."),
            ("LOffset", "SparseVarRegionList", None, None, ""),
            ("uint16", "MultiVarDataCount", None, None, ""),
            ("LOffset", "MultiVarData", "MultiVarDataCount", 0, ""),
        ],
    ),
    # VariableComposites
    (
        "VARC",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the HVAR table-initially = 0x00010000",
            ),
            ("LOffset", "Coverage", None, None, ""),
            ("LOffset", "MultiVarStore", None, None, "(may be NULL)"),
            ("LOffset", "ConditionList", None, None, "(may be NULL)"),
            ("LOffset", "AxisIndicesList", None, None, "(may be NULL)"),
            ("LOffset", "VarCompositeGlyphs", None, None, ""),
        ],
    ),
    (
        "AxisIndicesList",
        [
            ("TupleList", "Item", "", 0, ""),
        ],
    ),
    (
        "VarCompositeGlyphs",
        [
            ("VarCompositeGlyphList", "VarCompositeGlyph", "", None, ""),
        ],
    ),
    # Glyph advance variations
    (
        "HVAR",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the HVAR table-initially = 0x00010000",
            ),
            ("LOffset", "VarStore", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "AdvWidthMap", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "LsbMap", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "RsbMap", None, None, ""),
        ],
    ),
    (
        "VVAR",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the VVAR table-initially = 0x00010000",
            ),
            ("LOffset", "VarStore", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "AdvHeightMap", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "TsbMap", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "BsbMap", None, None, ""),
            ("LOffsetTo(VarIdxMap)", "VOrgMap", None, None, "Vertical origin mapping."),
        ],
    ),
    # Font-wide metrics variations
    (
        "MetricsValueRecord",
        [
            ("Tag", "ValueTag", None, None, "4-byte font-wide measure identifier"),
            ("uint32", "VarIdx", None, None, "Combined outer-inner variation index"),
            (
                "uint8",
                "MoreBytes",
                "ValueRecordSize",
                -8,
                "Extra bytes.  Set to empty array.",
            ),
        ],
    ),
    (
        "MVAR",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the MVAR table-initially = 0x00010000",
            ),
            ("uint16", "Reserved", None, None, "Set to 0"),
            ("uint16", "ValueRecordSize", None, None, ""),
            ("uint16", "ValueRecordCount", None, None, ""),
            ("Offset", "VarStore", None, None, ""),
            ("MetricsValueRecord", "ValueRecord", "ValueRecordCount", 0, ""),
        ],
    ),
    #
    # math
    #
    (
        "MATH",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the MATH table-initially set to 0x00010000.",
            ),
            (
                "Offset",
                "MathConstants",
                None,
                None,
                "Offset to MathConstants table - from the beginning of MATH table.",
            ),
            (
                "Offset",
                "MathGlyphInfo",
                None,
                None,
                "Offset to MathGlyphInfo table - from the beginning of MATH table.",
            ),
            (
                "Offset",
                "MathVariants",
                None,
                None,
                "Offset to MathVariants table - from the beginning of MATH table.",
            ),
        ],
    ),
    (
        "MathValueRecord",
        [
            ("int16", "Value", None, None, "The X or Y value in design units."),
            (
                "Offset",
                "DeviceTable",
                None,
                None,
                "Offset to the device table - from the beginning of parent table. May be NULL. Suggested format for device table is 1.",
            ),
        ],
    ),
    (
        "MathConstants",
        [
            (
                "int16",
                "ScriptPercentScaleDown",
                None,
                None,
                "Percentage of scaling down for script level 1. Suggested value: 80%.",
            ),
            (
                "int16",
                "ScriptScriptPercentScaleDown",
                None,
                None,
                "Percentage of scaling down for script level 2 (ScriptScript). Suggested value: 60%.",
            ),
            (
                "uint16",
                "DelimitedSubFormulaMinHeight",
                None,
                None,
                "Minimum height required for a delimited expression to be treated as a subformula. Suggested value: normal line height x1.5.",
            ),
            (
                "uint16",
                "DisplayOperatorMinHeight",
                None,
                None,
                "Minimum height of n-ary operators (such as integral and summation) for formulas in display mode.",
            ),
            (
                "MathValueRecord",
                "MathLeading",
                None,
                None,
                "White space to be left between math formulas to ensure proper line spacing. For example, for applications that treat line gap as a part of line ascender, formulas with ink  going above (os2.sTypoAscender + os2.sTypoLineGap - MathLeading) or with ink going below os2.sTypoDescender will result in increasing line height.",
            ),
            ("MathValueRecord", "AxisHeight", None, None, "Axis height of the font."),
            (
                "MathValueRecord",
                "AccentBaseHeight",
                None,
                None,
                "Maximum (ink) height of accent base that does not require raising the accents. Suggested: x-height of the font (os2.sxHeight) plus any possible overshots.",
            ),
            (
                "MathValueRecord",
                "FlattenedAccentBaseHeight",
                None,
                None,
                "Maximum (ink) height of accent base that does not require flattening the accents. Suggested: cap height of the font (os2.sCapHeight).",
            ),
            (
                "MathValueRecord",
                "SubscriptShiftDown",
                None,
                None,
                "The standard shift down applied to subscript elements. Positive for moving in the downward direction. Suggested: os2.ySubscriptYOffset.",
            ),
            (
                "MathValueRecord",
                "SubscriptTopMax",
                None,
                None,
                "Maximum allowed height of the (ink) top of subscripts that does not require moving subscripts further down. Suggested: 4/5 x-height.",
            ),
            (
                "MathValueRecord",
                "SubscriptBaselineDropMin",
                None,
                None,
                "Minimum allowed drop of the baseline of subscripts relative to the (ink) bottom of the base. Checked for bases that are treated as a box or extended shape. Positive for subscript baseline dropped below the base bottom.",
            ),
            (
                "MathValueRecord",
                "SuperscriptShiftUp",
                None,
                None,
                "Standard shift up applied to superscript elements. Suggested: os2.ySuperscriptYOffset.",
            ),
            (
                "MathValueRecord",
                "SuperscriptShiftUpCramped",
                None,
                None,
                "Standard shift of superscripts relative to the base, in cramped style.",
            ),
            (
                "MathValueRecord",
                "SuperscriptBottomMin",
                None,
                None,
                "Minimum allowed height of the (ink) bottom of superscripts that does not require moving subscripts further up. Suggested: 1/4 x-height.",
            ),
            (
                "MathValueRecord",
                "SuperscriptBaselineDropMax",
                None,
                None,
                "Maximum allowed drop of the baseline of superscripts relative to the (ink) top of the base. Checked for bases that are treated as a box or extended shape. Positive for superscript baseline below the base top.",
            ),
            (
                "MathValueRecord",
                "SubSuperscriptGapMin",
                None,
                None,
                "Minimum gap between the superscript and subscript ink. Suggested: 4x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "SuperscriptBottomMaxWithSubscript",
                None,
                None,
                "The maximum level to which the (ink) bottom of superscript can be pushed to increase the gap between superscript and subscript, before subscript starts being moved down. Suggested: 4/5 x-height.",
            ),
            (
                "MathValueRecord",
                "SpaceAfterScript",
                None,
                None,
                "Extra white space to be added after each subscript and superscript. Suggested: 0.5pt for a 12 pt font.",
            ),
            (
                "MathValueRecord",
                "UpperLimitGapMin",
                None,
                None,
                "Minimum gap between the (ink) bottom of the upper limit, and the (ink) top of the base operator.",
            ),
            (
                "MathValueRecord",
                "UpperLimitBaselineRiseMin",
                None,
                None,
                "Minimum distance between baseline of upper limit and (ink) top of the base operator.",
            ),
            (
                "MathValueRecord",
                "LowerLimitGapMin",
                None,
                None,
                "Minimum gap between (ink) top of the lower limit, and (ink) bottom of the base operator.",
            ),
            (
                "MathValueRecord",
                "LowerLimitBaselineDropMin",
                None,
                None,
                "Minimum distance between baseline of the lower limit and (ink) bottom of the base operator.",
            ),
            (
                "MathValueRecord",
                "StackTopShiftUp",
                None,
                None,
                "Standard shift up applied to the top element of a stack.",
            ),
            (
                "MathValueRecord",
                "StackTopDisplayStyleShiftUp",
                None,
                None,
                "Standard shift up applied to the top element of a stack in display style.",
            ),
            (
                "MathValueRecord",
                "StackBottomShiftDown",
                None,
                None,
                "Standard shift down applied to the bottom element of a stack. Positive for moving in the downward direction.",
            ),
            (
                "MathValueRecord",
                "StackBottomDisplayStyleShiftDown",
                None,
                None,
                "Standard shift down applied to the bottom element of a stack in display style. Positive for moving in the downward direction.",
            ),
            (
                "MathValueRecord",
                "StackGapMin",
                None,
                None,
                "Minimum gap between (ink) bottom of the top element of a stack, and the (ink) top of the bottom element. Suggested: 3x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "StackDisplayStyleGapMin",
                None,
                None,
                "Minimum gap between (ink) bottom of the top element of a stack, and the (ink) top of the bottom element in display style. Suggested: 7x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "StretchStackTopShiftUp",
                None,
                None,
                "Standard shift up applied to the top element of the stretch stack.",
            ),
            (
                "MathValueRecord",
                "StretchStackBottomShiftDown",
                None,
                None,
                "Standard shift down applied to the bottom element of the stretch stack. Positive for moving in the downward direction.",
            ),
            (
                "MathValueRecord",
                "StretchStackGapAboveMin",
                None,
                None,
                "Minimum gap between the ink of the stretched element, and the (ink) bottom of the element above. Suggested: UpperLimitGapMin",
            ),
            (
                "MathValueRecord",
                "StretchStackGapBelowMin",
                None,
                None,
                "Minimum gap between the ink of the stretched element, and the (ink) top of the element below. Suggested: LowerLimitGapMin.",
            ),
            (
                "MathValueRecord",
                "FractionNumeratorShiftUp",
                None,
                None,
                "Standard shift up applied to the numerator.",
            ),
            (
                "MathValueRecord",
                "FractionNumeratorDisplayStyleShiftUp",
                None,
                None,
                "Standard shift up applied to the numerator in display style. Suggested: StackTopDisplayStyleShiftUp.",
            ),
            (
                "MathValueRecord",
                "FractionDenominatorShiftDown",
                None,
                None,
                "Standard shift down applied to the denominator. Positive for moving in the downward direction.",
            ),
            (
                "MathValueRecord",
                "FractionDenominatorDisplayStyleShiftDown",
                None,
                None,
                "Standard shift down applied to the denominator in display style. Positive for moving in the downward direction. Suggested: StackBottomDisplayStyleShiftDown.",
            ),
            (
                "MathValueRecord",
                "FractionNumeratorGapMin",
                None,
                None,
                "Minimum tolerated gap between the (ink) bottom of the numerator and the ink of the fraction bar. Suggested: default rule thickness",
            ),
            (
                "MathValueRecord",
                "FractionNumDisplayStyleGapMin",
                None,
                None,
                "Minimum tolerated gap between the (ink) bottom of the numerator and the ink of the fraction bar in display style. Suggested: 3x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "FractionRuleThickness",
                None,
                None,
                "Thickness of the fraction bar. Suggested: default rule thickness.",
            ),
            (
                "MathValueRecord",
                "FractionDenominatorGapMin",
                None,
                None,
                "Minimum tolerated gap between the (ink) top of the denominator and the ink of the fraction bar. Suggested: default rule thickness",
            ),
            (
                "MathValueRecord",
                "FractionDenomDisplayStyleGapMin",
                None,
                None,
                "Minimum tolerated gap between the (ink) top of the denominator and the ink of the fraction bar in display style. Suggested: 3x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "SkewedFractionHorizontalGap",
                None,
                None,
                "Horizontal distance between the top and bottom elements of a skewed fraction.",
            ),
            (
                "MathValueRecord",
                "SkewedFractionVerticalGap",
                None,
                None,
                "Vertical distance between the ink of the top and bottom elements of a skewed fraction.",
            ),
            (
                "MathValueRecord",
                "OverbarVerticalGap",
                None,
                None,
                "Distance between the overbar and the (ink) top of he base. Suggested: 3x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "OverbarRuleThickness",
                None,
                None,
                "Thickness of overbar. Suggested: default rule thickness.",
            ),
            (
                "MathValueRecord",
                "OverbarExtraAscender",
                None,
                None,
                "Extra white space reserved above the overbar. Suggested: default rule thickness.",
            ),
            (
                "MathValueRecord",
                "UnderbarVerticalGap",
                None,
                None,
                "Distance between underbar and (ink) bottom of the base. Suggested: 3x default rule thickness.",
            ),
            (
                "MathValueRecord",
                "UnderbarRuleThickness",
                None,
                None,
                "Thickness of underbar. Suggested: default rule thickness.",
            ),
            (
                "MathValueRecord",
                "UnderbarExtraDescender",
                None,
                None,
                "Extra white space reserved below the underbar. Always positive. Suggested: default rule thickness.",
            ),
            (
                "MathValueRecord",
                "RadicalVerticalGap",
                None,
                None,
                "Space between the (ink) top of the expression and the bar over it. Suggested: 1 1/4 default rule thickness.",
            ),
            (
                "MathValueRecord",
                "RadicalDisplayStyleVerticalGap",
                None,
                None,
                "Space between the (ink) top of the expression and the bar over it. Suggested: default rule thickness + 1/4 x-height.",
            ),
            (
                "MathValueRecord",
                "RadicalRuleThickness",
                None,
                None,
                "Thickness of the radical rule. This is the thickness of the rule in designed or constructed radical signs. Suggested: default rule thickness.",
            ),
            (
                "MathValueRecord",
                "RadicalExtraAscender",
                None,
                None,
                "Extra white space reserved above the radical. Suggested: RadicalRuleThickness.",
            ),
            (
                "MathValueRecord",
                "RadicalKernBeforeDegree",
                None,
                None,
                "Extra horizontal kern before the degree of a radical, if such is present. Suggested: 5/18 of em.",
            ),
            (
                "MathValueRecord",
                "RadicalKernAfterDegree",
                None,
                None,
                "Negative kern after the degree of a radical, if such is present. Suggested: 10/18 of em.",
            ),
            (
                "uint16",
                "RadicalDegreeBottomRaisePercent",
                None,
                None,
                "Height of the bottom of the radical degree, if such is present, in proportion to the ascender of the radical sign. Suggested: 60%.",
            ),
        ],
    ),
    (
        "MathGlyphInfo",
        [
            (
                "Offset",
                "MathItalicsCorrectionInfo",
                None,
                None,
                "Offset to MathItalicsCorrectionInfo table - from the beginning of MathGlyphInfo table.",
            ),
            (
                "Offset",
                "MathTopAccentAttachment",
                None,
                None,
                "Offset to MathTopAccentAttachment table - from the beginning of MathGlyphInfo table.",
            ),
            (
                "Offset",
                "ExtendedShapeCoverage",
                None,
                None,
                "Offset to coverage table for Extended Shape glyphs - from the  beginning of MathGlyphInfo table. When the left or right glyph of a box is an extended shape variant, the (ink) box (and not the default position defined by values in MathConstants table) should be used for vertical positioning purposes. May be NULL.",
            ),
            (
                "Offset",
                "MathKernInfo",
                None,
                None,
                "Offset to MathKernInfo table - from the beginning of MathGlyphInfo table.",
            ),
        ],
    ),
    (
        "MathItalicsCorrectionInfo",
        [
            (
                "Offset",
                "Coverage",
                None,
                None,
                "Offset to Coverage table - from the beginning of MathItalicsCorrectionInfo table.",
            ),
            (
                "uint16",
                "ItalicsCorrectionCount",
                None,
                None,
                "Number of italics correction values. Should coincide with the number of covered glyphs.",
            ),
            (
                "MathValueRecord",
                "ItalicsCorrection",
                "ItalicsCorrectionCount",
                0,
                "Array of MathValueRecords defining italics correction values for each covered glyph.",
            ),
        ],
    ),
    (
        "MathTopAccentAttachment",
        [
            (
                "Offset",
                "TopAccentCoverage",
                None,
                None,
                "Offset to Coverage table - from the beginning of  MathTopAccentAttachment table.",
            ),
            (
                "uint16",
                "TopAccentAttachmentCount",
                None,
                None,
                "Number of top accent attachment point values. Should coincide with the number of covered glyphs",
            ),
            (
                "MathValueRecord",
                "TopAccentAttachment",
                "TopAccentAttachmentCount",
                0,
                "Array of MathValueRecords defining top accent attachment points for each covered glyph",
            ),
        ],
    ),
    (
        "MathKernInfo",
        [
            (
                "Offset",
                "MathKernCoverage",
                None,
                None,
                "Offset to Coverage table - from the beginning of the MathKernInfo table.",
            ),
            ("uint16", "MathKernCount", None, None, "Number of MathKernInfoRecords."),
            (
                "MathKernInfoRecord",
                "MathKernInfoRecords",
                "MathKernCount",
                0,
                "Array of MathKernInfoRecords, per-glyph information for mathematical positioning of subscripts and superscripts.",
            ),
        ],
    ),
    (
        "MathKernInfoRecord",
        [
            (
                "Offset",
                "TopRightMathKern",
                None,
                None,
                "Offset to MathKern table for top right corner - from the beginning of MathKernInfo table. May be NULL.",
            ),
            (
                "Offset",
                "TopLeftMathKern",
                None,
                None,
                "Offset to MathKern table for the top left corner - from the beginning of MathKernInfo table. May be NULL.",
            ),
            (
                "Offset",
                "BottomRightMathKern",
                None,
                None,
                "Offset to MathKern table for bottom right corner - from the beginning of MathKernInfo table. May be NULL.",
            ),
            (
                "Offset",
                "BottomLeftMathKern",
                None,
                None,
                "Offset to MathKern table for bottom left corner - from the beginning of MathKernInfo table. May be NULL.",
            ),
        ],
    ),
    (
        "MathKern",
        [
            (
                "uint16",
                "HeightCount",
                None,
                None,
                "Number of heights on which the kern value changes.",
            ),
            (
                "MathValueRecord",
                "CorrectionHeight",
                "HeightCount",
                0,
                "Array of correction heights at which the kern value changes. Sorted by the height value in design units.",
            ),
            (
                "MathValueRecord",
                "KernValue",
                "HeightCount",
                1,
                "Array of kern values corresponding to heights. First value is the kern value for all heights less or equal than the first height in this table.Last value is the value to be applied for all heights greater than the last height in this table. Negative values are interpreted as move glyphs closer to each other.",
            ),
        ],
    ),
    (
        "MathVariants",
        [
            (
                "uint16",
                "MinConnectorOverlap",
                None,
                None,
                "Minimum overlap of connecting glyphs during glyph construction,  in design units.",
            ),
            (
                "Offset",
                "VertGlyphCoverage",
                None,
                None,
                "Offset to Coverage table - from the beginning of MathVariants table.",
            ),
            (
                "Offset",
                "HorizGlyphCoverage",
                None,
                None,
                "Offset to Coverage table - from the beginning of MathVariants table.",
            ),
            (
                "uint16",
                "VertGlyphCount",
                None,
                None,
                "Number of glyphs for which information is provided for vertically growing variants.",
            ),
            (
                "uint16",
                "HorizGlyphCount",
                None,
                None,
                "Number of glyphs for which information is provided for horizontally growing variants.",
            ),
            (
                "Offset",
                "VertGlyphConstruction",
                "VertGlyphCount",
                0,
                "Array of offsets to MathGlyphConstruction tables - from the beginning of the MathVariants table, for shapes growing in vertical direction.",
            ),
            (
                "Offset",
                "HorizGlyphConstruction",
                "HorizGlyphCount",
                0,
                "Array of offsets to MathGlyphConstruction tables - from the beginning of the MathVariants table, for shapes growing in horizontal direction.",
            ),
        ],
    ),
    (
        "MathGlyphConstruction",
        [
            (
                "Offset",
                "GlyphAssembly",
                None,
                None,
                "Offset to GlyphAssembly table for this shape - from the beginning of MathGlyphConstruction table. May be NULL",
            ),
            (
                "uint16",
                "VariantCount",
                None,
                None,
                "Count of glyph growing variants for this glyph.",
            ),
            (
                "MathGlyphVariantRecord",
                "MathGlyphVariantRecord",
                "VariantCount",
                0,
                "MathGlyphVariantRecords for alternative variants of the glyphs.",
            ),
        ],
    ),
    (
        "MathGlyphVariantRecord",
        [
            ("GlyphID", "VariantGlyph", None, None, "Glyph ID for the variant."),
            (
                "uint16",
                "AdvanceMeasurement",
                None,
                None,
                "Advance width/height, in design units, of the variant, in the direction of requested glyph extension.",
            ),
        ],
    ),
    (
        "GlyphAssembly",
        [
            (
                "MathValueRecord",
                "ItalicsCorrection",
                None,
                None,
                "Italics correction of this GlyphAssembly. Should not depend on the assembly size.",
            ),
            ("uint16", "PartCount", None, None, "Number of parts in this assembly."),
            (
                "GlyphPartRecord",
                "PartRecords",
                "PartCount",
                0,
                "Array of part records, from left to right and bottom to top.",
            ),
        ],
    ),
    (
        "GlyphPartRecord",
        [
            ("GlyphID", "glyph", None, None, "Glyph ID for the part."),
            (
                "uint16",
                "StartConnectorLength",
                None,
                None,
                "Advance width/ height of the straight bar connector material, in design units, is at the beginning of the glyph, in the direction of the extension.",
            ),
            (
                "uint16",
                "EndConnectorLength",
                None,
                None,
                "Advance width/ height of the straight bar connector material, in design units, is at the end of the glyph, in the direction of the extension.",
            ),
            (
                "uint16",
                "FullAdvance",
                None,
                None,
                "Full advance width/height for this part, in the direction of the extension. In design units.",
            ),
            (
                "uint16",
                "PartFlags",
                None,
                None,
                "Part qualifiers. PartFlags enumeration currently uses only one bit: 0x0001 fExtender: If set, the part can be skipped or repeated. 0xFFFE Reserved",
            ),
        ],
    ),
    ##
    ## Apple Advanced Typography (AAT) tables
    ##
    (
        "AATLookupSegment",
        [
            ("uint16", "lastGlyph", None, None, "Last glyph index in this segment."),
            ("uint16", "firstGlyph", None, None, "First glyph index in this segment."),
            (
                "uint16",
                "value",
                None,
                None,
                "A 16-bit offset from the start of the table to the data.",
            ),
        ],
    ),
    #
    # ankr
    #
    (
        "ankr",
        [
            ("struct", "AnchorPoints", None, None, "Anchor points table."),
        ],
    ),
    (
        "AnchorPointsFormat0",
        [
            ("uint16", "Format", None, None, "Format of the anchor points table, = 0."),
            ("uint16", "Flags", None, None, "Flags. Currenty unused, set to zero."),
            (
                "AATLookupWithDataOffset(AnchorGlyphData)",
                "Anchors",
                None,
                None,
                "Table of with anchor overrides for each glyph.",
            ),
        ],
    ),
    (
        "AnchorGlyphData",
        [
            (
                "uint32",
                "AnchorPointCount",
                None,
                None,
                "Number of anchor points for this glyph.",
            ),
            (
                "struct",
                "AnchorPoint",
                "AnchorPointCount",
                0,
                "Individual anchor points.",
            ),
        ],
    ),
    (
        "AnchorPoint",
        [
            ("int16", "XCoordinate", None, None, "X coordinate of this anchor point."),
            ("int16", "YCoordinate", None, None, "Y coordinate of this anchor point."),
        ],
    ),
    #
    # bsln
    #
    (
        "bsln",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version number of the AAT baseline table (0x00010000 for the initial version).",
            ),
            ("struct", "Baseline", None, None, "Baseline table."),
        ],
    ),
    (
        "BaselineFormat0",
        [
            ("uint16", "Format", None, None, "Format of the baseline table, = 0."),
            (
                "uint16",
                "DefaultBaseline",
                None,
                None,
                "Default baseline value for all glyphs. This value can be from 0 through 31.",
            ),
            (
                "uint16",
                "Delta",
                32,
                0,
                "These are the FUnit distance deltas from the font’s natural baseline to the other baselines used in the font. A total of 32 deltas must be assigned.",
            ),
        ],
    ),
    (
        "BaselineFormat1",
        [
            ("uint16", "Format", None, None, "Format of the baseline table, = 1."),
            (
                "uint16",
                "DefaultBaseline",
                None,
                None,
                "Default baseline value for all glyphs. This value can be from 0 through 31.",
            ),
            (
                "uint16",
                "Delta",
                32,
                0,
                "These are the FUnit distance deltas from the font’s natural baseline to the other baselines used in the font. A total of 32 deltas must be assigned.",
            ),
            (
                "AATLookup(uint16)",
                "BaselineValues",
                None,
                None,
                "Lookup table that maps glyphs to their baseline values.",
            ),
        ],
    ),
    (
        "BaselineFormat2",
        [
            ("uint16", "Format", None, None, "Format of the baseline table, = 1."),
            (
                "uint16",
                "DefaultBaseline",
                None,
                None,
                "Default baseline value for all glyphs. This value can be from 0 through 31.",
            ),
            (
                "GlyphID",
                "StandardGlyph",
                None,
                None,
                "Glyph index of the glyph in this font to be used to set the baseline values. This glyph must contain a set of control points (whose numbers are contained in the following field) that determines baseline distances.",
            ),
            (
                "uint16",
                "ControlPoint",
                32,
                0,
                "Array of 32 control point numbers, associated with the standard glyph. A value of 0xFFFF means there is no corresponding control point in the standard glyph.",
            ),
        ],
    ),
    (
        "BaselineFormat3",
        [
            ("uint16", "Format", None, None, "Format of the baseline table, = 1."),
            (
                "uint16",
                "DefaultBaseline",
                None,
                None,
                "Default baseline value for all glyphs. This value can be from 0 through 31.",
            ),
            (
                "GlyphID",
                "StandardGlyph",
                None,
                None,
                "Glyph index of the glyph in this font to be used to set the baseline values. This glyph must contain a set of control points (whose numbers are contained in the following field) that determines baseline distances.",
            ),
            (
                "uint16",
                "ControlPoint",
                32,
                0,
                "Array of 32 control point numbers, associated with the standard glyph. A value of 0xFFFF means there is no corresponding control point in the standard glyph.",
            ),
            (
                "AATLookup(uint16)",
                "BaselineValues",
                None,
                None,
                "Lookup table that maps glyphs to their baseline values.",
            ),
        ],
    ),
    #
    # cidg
    #
    (
        "cidg",
        [
            ("struct", "CIDGlyphMapping", None, None, "CID-to-glyph mapping table."),
        ],
    ),
    (
        "CIDGlyphMappingFormat0",
        [
            (
                "uint16",
                "Format",
                None,
                None,
                "Format of the CID-to-glyph mapping table, = 0.",
            ),
            ("uint16", "DataFormat", None, None, "Currenty unused, set to zero."),
            ("uint32", "StructLength", None, None, "Size of the table in bytes."),
            ("uint16", "Registry", None, None, "The registry ID."),
            (
                "char64",
                "RegistryName",
                None,
                None,
                "The registry name in ASCII; unused bytes should be set to 0.",
            ),
            ("uint16", "Order", None, None, "The order ID."),
            (
                "char64",
                "OrderName",
                None,
                None,
                "The order name in ASCII; unused bytes should be set to 0.",
            ),
            ("uint16", "SupplementVersion", None, None, "The supplement version."),
            (
                "CIDGlyphMap",
                "Mapping",
                None,
                None,
                "A mapping from CIDs to the glyphs in the font, starting with CID 0. If a CID from the identified collection has no glyph in the font, 0xFFFF is used",
            ),
        ],
    ),
    #
    # feat
    #
    (
        "feat",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the feat table-initially set to 0x00010000.",
            ),
            ("FeatureNames", "FeatureNames", None, None, "The feature names."),
        ],
    ),
    (
        "FeatureNames",
        [
            (
                "uint16",
                "FeatureNameCount",
                None,
                None,
                "Number of entries in the feature name array.",
            ),
            ("uint16", "Reserved1", None, None, "Reserved (set to zero)."),
            ("uint32", "Reserved2", None, None, "Reserved (set to zero)."),
            (
                "FeatureName",
                "FeatureName",
                "FeatureNameCount",
                0,
                "The feature name array.",
            ),
        ],
    ),
    (
        "FeatureName",
        [
            ("uint16", "FeatureType", None, None, "Feature type."),
            (
                "uint16",
                "SettingsCount",
                None,
                None,
                "The number of records in the setting name array.",
            ),
            (
                "LOffset",
                "Settings",
                None,
                None,
                "Offset to setting table for this feature.",
            ),
            (
                "uint16",
                "FeatureFlags",
                None,
                None,
                "Single-bit flags associated with the feature type.",
            ),
            (
                "NameID",
                "FeatureNameID",
                None,
                None,
                "The name table index for the feature name.",
            ),
        ],
    ),
    (
        "Settings",
        [
            ("Setting", "Setting", "SettingsCount", 0, "The setting array."),
        ],
    ),
    (
        "Setting",
        [
            ("uint16", "SettingValue", None, None, "The setting."),
            (
                "NameID",
                "SettingNameID",
                None,
                None,
                "The name table index for the setting name.",
            ),
        ],
    ),
    #
    # gcid
    #
    (
        "gcid",
        [
            ("struct", "GlyphCIDMapping", None, None, "Glyph to CID mapping table."),
        ],
    ),
    (
        "GlyphCIDMappingFormat0",
        [
            (
                "uint16",
                "Format",
                None,
                None,
                "Format of the glyph-to-CID mapping table, = 0.",
            ),
            ("uint16", "DataFormat", None, None, "Currenty unused, set to zero."),
            ("uint32", "StructLength", None, None, "Size of the table in bytes."),
            ("uint16", "Registry", None, None, "The registry ID."),
            (
                "char64",
                "RegistryName",
                None,
                None,
                "The registry name in ASCII; unused bytes should be set to 0.",
            ),
            ("uint16", "Order", None, None, "The order ID."),
            (
                "char64",
                "OrderName",
                None,
                None,
                "The order name in ASCII; unused bytes should be set to 0.",
            ),
            ("uint16", "SupplementVersion", None, None, "The supplement version."),
            (
                "GlyphCIDMap",
                "Mapping",
                None,
                None,
                "The CIDs for the glyphs in the font, starting with glyph 0. If a glyph does not correspond to a CID in the identified collection, 0xFFFF is used",
            ),
        ],
    ),
    #
    # lcar
    #
    (
        "lcar",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version number of the ligature caret table (0x00010000 for the initial version).",
            ),
            ("struct", "LigatureCarets", None, None, "Ligature carets table."),
        ],
    ),
    (
        "LigatureCaretsFormat0",
        [
            (
                "uint16",
                "Format",
                None,
                None,
                "Format of the ligature caret table. Format 0 indicates division points are distances in font units, Format 1 indicates division points are indexes of control points.",
            ),
            (
                "AATLookup(LigCaretDistances)",
                "Carets",
                None,
                None,
                "Lookup table associating ligature glyphs with their caret positions, in font unit distances.",
            ),
        ],
    ),
    (
        "LigatureCaretsFormat1",
        [
            (
                "uint16",
                "Format",
                None,
                None,
                "Format of the ligature caret table. Format 0 indicates division points are distances in font units, Format 1 indicates division points are indexes of control points.",
            ),
            (
                "AATLookup(LigCaretPoints)",
                "Carets",
                None,
                None,
                "Lookup table associating ligature glyphs with their caret positions, as control points.",
            ),
        ],
    ),
    (
        "LigCaretDistances",
        [
            ("uint16", "DivsionPointCount", None, None, "Number of division points."),
            (
                "int16",
                "DivisionPoint",
                "DivsionPointCount",
                0,
                "Distance in font units through which a subdivision is made orthogonally to the baseline.",
            ),
        ],
    ),
    (
        "LigCaretPoints",
        [
            ("uint16", "DivsionPointCount", None, None, "Number of division points."),
            (
                "int16",
                "DivisionPoint",
                "DivsionPointCount",
                0,
                "The number of the control point through which a subdivision is made orthogonally to the baseline.",
            ),
        ],
    ),
    #
    # mort
    #
    (
        "mort",
        [
            ("Version", "Version", None, None, "Version of the mort table."),
            (
                "uint32",
                "MorphChainCount",
                None,
                None,
                "Number of metamorphosis chains.",
            ),
            (
                "MortChain",
                "MorphChain",
                "MorphChainCount",
                0,
                "Array of metamorphosis chains.",
            ),
        ],
    ),
    (
        "MortChain",
        [
            (
                "Flags32",
                "DefaultFlags",
                None,
                None,
                "The default specification for subtables.",
            ),
            (
                "uint32",
                "StructLength",
                None,
                None,
                "Total byte count, including this header; must be a multiple of 4.",
            ),
            (
                "uint16",
                "MorphFeatureCount",
                None,
                None,
                "Number of metamorphosis feature entries.",
            ),
            (
                "uint16",
                "MorphSubtableCount",
                None,
                None,
                "The number of subtables in the chain.",
            ),
            (
                "struct",
                "MorphFeature",
                "MorphFeatureCount",
                0,
                "Array of metamorphosis features.",
            ),
            (
                "MortSubtable",
                "MorphSubtable",
                "MorphSubtableCount",
                0,
                "Array of metamorphosis subtables.",
            ),
        ],
    ),
    (
        "MortSubtable",
        [
            (
                "uint16",
                "StructLength",
                None,
                None,
                "Total subtable length, including this header.",
            ),
            (
                "uint8",
                "CoverageFlags",
                None,
                None,
                "Most significant byte of coverage flags.",
            ),
            ("uint8", "MorphType", None, None, "Subtable type."),
            (
                "Flags32",
                "SubFeatureFlags",
                None,
                None,
                "The 32-bit mask identifying which subtable this is (the subtable being executed if the AND of this value and the processed defaultFlags is nonzero).",
            ),
            ("SubStruct", "SubStruct", None, None, "SubTable."),
        ],
    ),
    #
    # morx
    #
    (
        "morx",
        [
            ("uint16", "Version", None, None, "Version of the morx table."),
            ("uint16", "Reserved", None, None, "Reserved (set to zero)."),
            (
                "uint32",
                "MorphChainCount",
                None,
                None,
                "Number of extended metamorphosis chains.",
            ),
            (
                "MorxChain",
                "MorphChain",
                "MorphChainCount",
                0,
                "Array of extended metamorphosis chains.",
            ),
        ],
    ),
    (
        "MorxChain",
        [
            (
                "Flags32",
                "DefaultFlags",
                None,
                None,
                "The default specification for subtables.",
            ),
            (
                "uint32",
                "StructLength",
                None,
                None,
                "Total byte count, including this header; must be a multiple of 4.",
            ),
            (
                "uint32",
                "MorphFeatureCount",
                None,
                None,
                "Number of feature subtable entries.",
            ),
            (
                "uint32",
                "MorphSubtableCount",
                None,
                None,
                "The number of subtables in the chain.",
            ),
            (
                "MorphFeature",
                "MorphFeature",
                "MorphFeatureCount",
                0,
                "Array of metamorphosis features.",
            ),
            (
                "MorxSubtable",
                "MorphSubtable",
                "MorphSubtableCount",
                0,
                "Array of extended metamorphosis subtables.",
            ),
        ],
    ),
    (
        "MorphFeature",
        [
            ("uint16", "FeatureType", None, None, "The type of feature."),
            (
                "uint16",
                "FeatureSetting",
                None,
                None,
                "The feature's setting (aka selector).",
            ),
            (
                "Flags32",
                "EnableFlags",
                None,
                None,
                "Flags for the settings that this feature and setting enables.",
            ),
            (
                "Flags32",
                "DisableFlags",
                None,
                None,
                "Complement of flags for the settings that this feature and setting disable.",
            ),
        ],
    ),
    # Apple TrueType Reference Manual, chapter “The ‘morx’ table”,
    # section “Metamorphosis Subtables”.
    # https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6morx.html
    (
        "MorxSubtable",
        [
            (
                "uint32",
                "StructLength",
                None,
                None,
                "Total subtable length, including this header.",
            ),
            (
                "uint8",
                "CoverageFlags",
                None,
                None,
                "Most significant byte of coverage flags.",
            ),
            ("uint16", "Reserved", None, None, "Unused."),
            ("uint8", "MorphType", None, None, "Subtable type."),
            (
                "Flags32",
                "SubFeatureFlags",
                None,
                None,
                "The 32-bit mask identifying which subtable this is (the subtable being executed if the AND of this value and the processed defaultFlags is nonzero).",
            ),
            ("SubStruct", "SubStruct", None, None, "SubTable."),
        ],
    ),
    (
        "StateHeader",
        [
            (
                "uint32",
                "ClassCount",
                None,
                None,
                "Number of classes, which is the number of 16-bit entry indices in a single line in the state array.",
            ),
            (
                "uint32",
                "MorphClass",
                None,
                None,
                "Offset from the start of this state table header to the start of the class table.",
            ),
            (
                "uint32",
                "StateArrayOffset",
                None,
                None,
                "Offset from the start of this state table header to the start of the state array.",
            ),
            (
                "uint32",
                "EntryTableOffset",
                None,
                None,
                "Offset from the start of this state table header to the start of the entry table.",
            ),
        ],
    ),
    (
        "RearrangementMorph",
        [
            (
                "STXHeader(RearrangementMorphAction)",
                "StateTable",
                None,
                None,
                "Finite-state transducer table for indic rearrangement.",
            ),
        ],
    ),
    (
        "ContextualMorph",
        [
            (
                "STXHeader(ContextualMorphAction)",
                "StateTable",
                None,
                None,
                "Finite-state transducer for contextual glyph substitution.",
            ),
        ],
    ),
    (
        "LigatureMorph",
        [
            (
                "STXHeader(LigatureMorphAction)",
                "StateTable",
                None,
                None,
                "Finite-state transducer for ligature substitution.",
            ),
        ],
    ),
    (
        "NoncontextualMorph",
        [
            (
                "AATLookup(GlyphID)",
                "Substitution",
                None,
                None,
                "The noncontextual glyph substitution table.",
            ),
        ],
    ),
    (
        "InsertionMorph",
        [
            (
                "STXHeader(InsertionMorphAction)",
                "StateTable",
                None,
                None,
                "Finite-state transducer for glyph insertion.",
            ),
        ],
    ),
    (
        "MorphClass",
        [
            (
                "uint16",
                "FirstGlyph",
                None,
                None,
                "Glyph index of the first glyph in the class table.",
            ),
            # ('uint16', 'GlyphCount', None, None, 'Number of glyphs in class table.'),
            # ('uint8', 'GlyphClass', 'GlyphCount', 0, 'The class codes (indexed by glyph index minus firstGlyph). Class codes range from 0 to the value of stateSize minus 1.'),
        ],
    ),
    # If the 'morx' table version is 3 or greater, then the last subtable in the chain is followed by a subtableGlyphCoverageArray, as described below.
    # 		('Offset', 'MarkGlyphSetsDef', None, 'round(Version*0x10000) >= 0x00010002', 'Offset to the table of mark set definitions-from beginning of GDEF header (may be NULL)'),
    #
    # prop
    #
    (
        "prop",
        [
            (
                "Fixed",
                "Version",
                None,
                None,
                "Version number of the AAT glyphs property table. Version 1.0 is the initial table version. Version 2.0, which is recognized by macOS 8.5 and later, adds support for the “attaches on right” bit. Version 3.0, which gets recognized by macOS X and iOS, adds support for the additional directional properties defined in Unicode 3.0.",
            ),
            ("struct", "GlyphProperties", None, None, "Glyph properties."),
        ],
    ),
    (
        "GlyphPropertiesFormat0",
        [
            ("uint16", "Format", None, None, "Format, = 0."),
            (
                "uint16",
                "DefaultProperties",
                None,
                None,
                "Default properties applied to a glyph. Since there is no lookup table in prop format 0, the default properties get applied to every glyph in the font.",
            ),
        ],
    ),
    (
        "GlyphPropertiesFormat1",
        [
            ("uint16", "Format", None, None, "Format, = 1."),
            (
                "uint16",
                "DefaultProperties",
                None,
                None,
                "Default properties applied to a glyph if that glyph is not present in the Properties lookup table.",
            ),
            (
                "AATLookup(uint16)",
                "Properties",
                None,
                None,
                "Lookup data associating glyphs with their properties.",
            ),
        ],
    ),
    #
    # opbd
    #
    (
        "opbd",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version number of the optical bounds table (0x00010000 for the initial version).",
            ),
            ("struct", "OpticalBounds", None, None, "Optical bounds table."),
        ],
    ),
    (
        "OpticalBoundsFormat0",
        [
            (
                "uint16",
                "Format",
                None,
                None,
                "Format of the optical bounds table, = 0.",
            ),
            (
                "AATLookup(OpticalBoundsDeltas)",
                "OpticalBoundsDeltas",
                None,
                None,
                "Lookup table associating glyphs with their optical bounds, given as deltas in font units.",
            ),
        ],
    ),
    (
        "OpticalBoundsFormat1",
        [
            (
                "uint16",
                "Format",
                None,
                None,
                "Format of the optical bounds table, = 1.",
            ),
            (
                "AATLookup(OpticalBoundsPoints)",
                "OpticalBoundsPoints",
                None,
                None,
                "Lookup table associating glyphs with their optical bounds, given as references to control points.",
            ),
        ],
    ),
    (
        "OpticalBoundsDeltas",
        [
            (
                "int16",
                "Left",
                None,
                None,
                "Delta value for the left-side optical edge.",
            ),
            ("int16", "Top", None, None, "Delta value for the top-side optical edge."),
            (
                "int16",
                "Right",
                None,
                None,
                "Delta value for the right-side optical edge.",
            ),
            (
                "int16",
                "Bottom",
                None,
                None,
                "Delta value for the bottom-side optical edge.",
            ),
        ],
    ),
    (
        "OpticalBoundsPoints",
        [
            (
                "int16",
                "Left",
                None,
                None,
                "Control point index for the left-side optical edge, or -1 if this glyph has none.",
            ),
            (
                "int16",
                "Top",
                None,
                None,
                "Control point index for the top-side optical edge, or -1 if this glyph has none.",
            ),
            (
                "int16",
                "Right",
                None,
                None,
                "Control point index for the right-side optical edge, or -1 if this glyph has none.",
            ),
            (
                "int16",
                "Bottom",
                None,
                None,
                "Control point index for the bottom-side optical edge, or -1 if this glyph has none.",
            ),
        ],
    ),
    #
    # TSIC
    #
    (
        "TSIC",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of table initially set to 0x00010000.",
            ),
            ("uint16", "Flags", None, None, "TSIC flags - set to 0"),
            ("uint16", "AxisCount", None, None, "Axis count from fvar"),
            ("uint16", "RecordCount", None, None, "TSIC record count"),
            ("uint16", "Reserved", None, None, "Set to 0"),
            ("Tag", "AxisArray", "AxisCount", 0, "Array of axis tags in fvar order"),
            (
                "LocationRecord",
                "RecordLocations",
                "RecordCount",
                0,
                "Location in variation space of TSIC record",
            ),
            ("TSICRecord", "Record", "RecordCount", 0, "Array of TSIC records"),
        ],
    ),
    (
        "LocationRecord",
        [
            ("F2Dot14", "Axis", "AxisCount", 0, "Axis record"),
        ],
    ),
    (
        "TSICRecord",
        [
            ("uint16", "Flags", None, None, "Record flags - set to 0"),
            ("uint16", "NumCVTEntries", None, None, "Number of CVT number value pairs"),
            ("uint16", "NameLength", None, None, "Length of optional user record name"),
            ("uint16", "NameArray", "NameLength", 0, "Unicode 16 name"),
            ("uint16", "CVTArray", "NumCVTEntries", 0, "CVT number array"),
            ("int16", "CVTValueArray", "NumCVTEntries", 0, "CVT value"),
        ],
    ),
    #
    # COLR
    #
    (
        "COLR",
        [
            ("uint16", "Version", None, None, "Table version number (starts at 0)."),
            (
                "uint16",
                "BaseGlyphRecordCount",
                None,
                None,
                "Number of Base Glyph Records.",
            ),
            (
                "LOffset",
                "BaseGlyphRecordArray",
                None,
                None,
                "Offset (from beginning of COLR table) to Base Glyph records.",
            ),
            (
                "LOffset",
                "LayerRecordArray",
                None,
                None,
                "Offset (from beginning of COLR table) to Layer Records.",
            ),
            ("uint16", "LayerRecordCount", None, None, "Number of Layer Records."),
            (
                "LOffset",
                "BaseGlyphList",
                None,
                "Version >= 1",
                "Offset (from beginning of COLR table) to array of Version-1 Base Glyph records.",
            ),
            (
                "LOffset",
                "LayerList",
                None,
                "Version >= 1",
                "Offset (from beginning of COLR table) to LayerList.",
            ),
            (
                "LOffset",
                "ClipList",
                None,
                "Version >= 1",
                "Offset to ClipList table (may be NULL)",
            ),
            (
                "LOffsetTo(DeltaSetIndexMap)",
                "VarIndexMap",
                None,
                "Version >= 1",
                "Offset to DeltaSetIndexMap table (may be NULL)",
            ),
            (
                "LOffset",
                "VarStore",
                None,
                "Version >= 1",
                "Offset to variation store (may be NULL)",
            ),
        ],
    ),
    (
        "BaseGlyphRecordArray",
        [
            (
                "BaseGlyphRecord",
                "BaseGlyphRecord",
                "BaseGlyphRecordCount",
                0,
                "Base Glyph records.",
            ),
        ],
    ),
    (
        "BaseGlyphRecord",
        [
            (
                "GlyphID",
                "BaseGlyph",
                None,
                None,
                "Glyph ID of reference glyph. This glyph is for reference only and is not rendered for color.",
            ),
            (
                "uint16",
                "FirstLayerIndex",
                None,
                None,
                "Index (from beginning of the Layer Records) to the layer record. There will be numLayers consecutive entries for this base glyph.",
            ),
            (
                "uint16",
                "NumLayers",
                None,
                None,
                "Number of color layers associated with this glyph.",
            ),
        ],
    ),
    (
        "LayerRecordArray",
        [
            ("LayerRecord", "LayerRecord", "LayerRecordCount", 0, "Layer records."),
        ],
    ),
    (
        "LayerRecord",
        [
            (
                "GlyphID",
                "LayerGlyph",
                None,
                None,
                "Glyph ID of layer glyph (must be in z-order from bottom to top).",
            ),
            (
                "uint16",
                "PaletteIndex",
                None,
                None,
                "Index value to use with a selected color palette.",
            ),
        ],
    ),
    (
        "BaseGlyphList",
        [
            (
                "uint32",
                "BaseGlyphCount",
                None,
                None,
                "Number of Version-1 Base Glyph records",
            ),
            (
                "struct",
                "BaseGlyphPaintRecord",
                "BaseGlyphCount",
                0,
                "Array of Version-1 Base Glyph records",
            ),
        ],
    ),
    (
        "BaseGlyphPaintRecord",
        [
            ("GlyphID", "BaseGlyph", None, None, "Glyph ID of reference glyph."),
            (
                "LOffset",
                "Paint",
                None,
                None,
                "Offset (from beginning of BaseGlyphPaintRecord) to Paint, typically a PaintColrLayers.",
            ),
        ],
    ),
    (
        "LayerList",
        [
            ("uint32", "LayerCount", None, None, "Number of Version-1 Layers"),
            (
                "LOffset",
                "Paint",
                "LayerCount",
                0,
                "Array of offsets to Paint tables, from the start of the LayerList table.",
            ),
        ],
    ),
    (
        "ClipListFormat1",
        [
            (
                "uint8",
                "Format",
                None,
                None,
                "Format for ClipList with 16bit glyph IDs: 1",
            ),
            ("uint32", "ClipCount", None, None, "Number of Clip records."),
            (
                "struct",
                "ClipRecord",
                "ClipCount",
                0,
                "Array of Clip records sorted by glyph ID.",
            ),
        ],
    ),
    (
        "ClipRecord",
        [
            ("uint16", "StartGlyphID", None, None, "First glyph ID in the range."),
            ("uint16", "EndGlyphID", None, None, "Last glyph ID in the range."),
            ("Offset24", "ClipBox", None, None, "Offset to a ClipBox table."),
        ],
    ),
    (
        "ClipBoxFormat1",
        [
            (
                "uint8",
                "Format",
                None,
                None,
                "Format for ClipBox without variation: set to 1.",
            ),
            ("int16", "xMin", None, None, "Minimum x of clip box."),
            ("int16", "yMin", None, None, "Minimum y of clip box."),
            ("int16", "xMax", None, None, "Maximum x of clip box."),
            ("int16", "yMax", None, None, "Maximum y of clip box."),
        ],
    ),
    (
        "ClipBoxFormat2",
        [
            ("uint8", "Format", None, None, "Format for variable ClipBox: set to 2."),
            ("int16", "xMin", None, None, "Minimum x of clip box. VarIndexBase + 0."),
            ("int16", "yMin", None, None, "Minimum y of clip box. VarIndexBase + 1."),
            ("int16", "xMax", None, None, "Maximum x of clip box. VarIndexBase + 2."),
            ("int16", "yMax", None, None, "Maximum y of clip box. VarIndexBase + 3."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # COLRv1 Affine2x3 uses the same column-major order to serialize a 2D
    # Affine Transformation as the one used by fontTools.misc.transform.
    # However, for historical reasons, the labels 'xy' and 'yx' are swapped.
    # Their fundamental meaning is the same though.
    # COLRv1 Affine2x3 follows the names found in FreeType and Cairo.
    # In all case, the second element in the 6-tuple correspond to the
    # y-part of the x basis vector, and the third to the x-part of the y
    # basis vector.
    # See https://github.com/googlefonts/colr-gradients-spec/pull/85
    (
        "Affine2x3",
        [
            ("Fixed", "xx", None, None, "x-part of x basis vector"),
            ("Fixed", "yx", None, None, "y-part of x basis vector"),
            ("Fixed", "xy", None, None, "x-part of y basis vector"),
            ("Fixed", "yy", None, None, "y-part of y basis vector"),
            ("Fixed", "dx", None, None, "Translation in x direction"),
            ("Fixed", "dy", None, None, "Translation in y direction"),
        ],
    ),
    (
        "VarAffine2x3",
        [
            ("Fixed", "xx", None, None, "x-part of x basis vector. VarIndexBase + 0."),
            ("Fixed", "yx", None, None, "y-part of x basis vector. VarIndexBase + 1."),
            ("Fixed", "xy", None, None, "x-part of y basis vector. VarIndexBase + 2."),
            ("Fixed", "yy", None, None, "y-part of y basis vector. VarIndexBase + 3."),
            (
                "Fixed",
                "dx",
                None,
                None,
                "Translation in x direction. VarIndexBase + 4.",
            ),
            (
                "Fixed",
                "dy",
                None,
                None,
                "Translation in y direction. VarIndexBase + 5.",
            ),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    (
        "ColorStop",
        [
            ("F2Dot14", "StopOffset", None, None, ""),
            ("uint16", "PaletteIndex", None, None, "Index for a CPAL palette entry."),
            ("F2Dot14", "Alpha", None, None, "Values outsided [0.,1.] reserved"),
        ],
    ),
    (
        "VarColorStop",
        [
            ("F2Dot14", "StopOffset", None, None, "VarIndexBase + 0."),
            ("uint16", "PaletteIndex", None, None, "Index for a CPAL palette entry."),
            (
                "F2Dot14",
                "Alpha",
                None,
                None,
                "Values outsided [0.,1.] reserved. VarIndexBase + 1.",
            ),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    (
        "ColorLine",
        [
            (
                "ExtendMode",
                "Extend",
                None,
                None,
                "Enum {PAD = 0, REPEAT = 1, REFLECT = 2}",
            ),
            ("uint16", "StopCount", None, None, "Number of Color stops."),
            ("ColorStop", "ColorStop", "StopCount", 0, "Array of Color stops."),
        ],
    ),
    (
        "VarColorLine",
        [
            (
                "ExtendMode",
                "Extend",
                None,
                None,
                "Enum {PAD = 0, REPEAT = 1, REFLECT = 2}",
            ),
            ("uint16", "StopCount", None, None, "Number of Color stops."),
            ("VarColorStop", "ColorStop", "StopCount", 0, "Array of Color stops."),
        ],
    ),
    # PaintColrLayers
    (
        "PaintFormat1",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 1"),
            (
                "uint8",
                "NumLayers",
                None,
                None,
                "Number of offsets to Paint to read from LayerList.",
            ),
            ("uint32", "FirstLayerIndex", None, None, "Index into LayerList."),
        ],
    ),
    # PaintSolid
    (
        "PaintFormat2",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 2"),
            ("uint16", "PaletteIndex", None, None, "Index for a CPAL palette entry."),
            ("F2Dot14", "Alpha", None, None, "Values outsided [0.,1.] reserved"),
        ],
    ),
    # PaintVarSolid
    (
        "PaintFormat3",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 3"),
            ("uint16", "PaletteIndex", None, None, "Index for a CPAL palette entry."),
            (
                "F2Dot14",
                "Alpha",
                None,
                None,
                "Values outsided [0.,1.] reserved. VarIndexBase + 0.",
            ),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintLinearGradient
    (
        "PaintFormat4",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 4"),
            (
                "Offset24",
                "ColorLine",
                None,
                None,
                "Offset (from beginning of PaintLinearGradient table) to ColorLine subtable.",
            ),
            ("int16", "x0", None, None, ""),
            ("int16", "y0", None, None, ""),
            ("int16", "x1", None, None, ""),
            ("int16", "y1", None, None, ""),
            ("int16", "x2", None, None, ""),
            ("int16", "y2", None, None, ""),
        ],
    ),
    # PaintVarLinearGradient
    (
        "PaintFormat5",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 5"),
            (
                "LOffset24To(VarColorLine)",
                "ColorLine",
                None,
                None,
                "Offset (from beginning of PaintVarLinearGradient table) to VarColorLine subtable.",
            ),
            ("int16", "x0", None, None, "VarIndexBase + 0."),
            ("int16", "y0", None, None, "VarIndexBase + 1."),
            ("int16", "x1", None, None, "VarIndexBase + 2."),
            ("int16", "y1", None, None, "VarIndexBase + 3."),
            ("int16", "x2", None, None, "VarIndexBase + 4."),
            ("int16", "y2", None, None, "VarIndexBase + 5."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintRadialGradient
    (
        "PaintFormat6",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 6"),
            (
                "Offset24",
                "ColorLine",
                None,
                None,
                "Offset (from beginning of PaintRadialGradient table) to ColorLine subtable.",
            ),
            ("int16", "x0", None, None, ""),
            ("int16", "y0", None, None, ""),
            ("uint16", "r0", None, None, ""),
            ("int16", "x1", None, None, ""),
            ("int16", "y1", None, None, ""),
            ("uint16", "r1", None, None, ""),
        ],
    ),
    # PaintVarRadialGradient
    (
        "PaintFormat7",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 7"),
            (
                "LOffset24To(VarColorLine)",
                "ColorLine",
                None,
                None,
                "Offset (from beginning of PaintVarRadialGradient table) to VarColorLine subtable.",
            ),
            ("int16", "x0", None, None, "VarIndexBase + 0."),
            ("int16", "y0", None, None, "VarIndexBase + 1."),
            ("uint16", "r0", None, None, "VarIndexBase + 2."),
            ("int16", "x1", None, None, "VarIndexBase + 3."),
            ("int16", "y1", None, None, "VarIndexBase + 4."),
            ("uint16", "r1", None, None, "VarIndexBase + 5."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintSweepGradient
    (
        "PaintFormat8",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 8"),
            (
                "Offset24",
                "ColorLine",
                None,
                None,
                "Offset (from beginning of PaintSweepGradient table) to ColorLine subtable.",
            ),
            ("int16", "centerX", None, None, "Center x coordinate."),
            ("int16", "centerY", None, None, "Center y coordinate."),
            (
                "BiasedAngle",
                "startAngle",
                None,
                None,
                "Start of the angular range of the gradient.",
            ),
            (
                "BiasedAngle",
                "endAngle",
                None,
                None,
                "End of the angular range of the gradient.",
            ),
        ],
    ),
    # PaintVarSweepGradient
    (
        "PaintFormat9",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 9"),
            (
                "LOffset24To(VarColorLine)",
                "ColorLine",
                None,
                None,
                "Offset (from beginning of PaintVarSweepGradient table) to VarColorLine subtable.",
            ),
            ("int16", "centerX", None, None, "Center x coordinate. VarIndexBase + 0."),
            ("int16", "centerY", None, None, "Center y coordinate. VarIndexBase + 1."),
            (
                "BiasedAngle",
                "startAngle",
                None,
                None,
                "Start of the angular range of the gradient. VarIndexBase + 2.",
            ),
            (
                "BiasedAngle",
                "endAngle",
                None,
                None,
                "End of the angular range of the gradient. VarIndexBase + 3.",
            ),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintGlyph
    (
        "PaintFormat10",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 10"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintGlyph table) to Paint subtable.",
            ),
            ("GlyphID", "Glyph", None, None, "Glyph ID for the source outline."),
        ],
    ),
    # PaintColrGlyph
    (
        "PaintFormat11",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 11"),
            (
                "GlyphID",
                "Glyph",
                None,
                None,
                "Virtual glyph ID for a BaseGlyphList base glyph.",
            ),
        ],
    ),
    # PaintTransform
    (
        "PaintFormat12",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 12"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintTransform table) to Paint subtable.",
            ),
            (
                "LOffset24To(Affine2x3)",
                "Transform",
                None,
                None,
                "2x3 matrix for 2D affine transformations.",
            ),
        ],
    ),
    # PaintVarTransform
    (
        "PaintFormat13",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 13"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarTransform table) to Paint subtable.",
            ),
            (
                "LOffset24To(VarAffine2x3)",
                "Transform",
                None,
                None,
                "2x3 matrix for 2D affine transformations.",
            ),
        ],
    ),
    # PaintTranslate
    (
        "PaintFormat14",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 14"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintTranslate table) to Paint subtable.",
            ),
            ("int16", "dx", None, None, "Translation in x direction."),
            ("int16", "dy", None, None, "Translation in y direction."),
        ],
    ),
    # PaintVarTranslate
    (
        "PaintFormat15",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 15"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarTranslate table) to Paint subtable.",
            ),
            (
                "int16",
                "dx",
                None,
                None,
                "Translation in x direction. VarIndexBase + 0.",
            ),
            (
                "int16",
                "dy",
                None,
                None,
                "Translation in y direction. VarIndexBase + 1.",
            ),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintScale
    (
        "PaintFormat16",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 16"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintScale table) to Paint subtable.",
            ),
            ("F2Dot14", "scaleX", None, None, ""),
            ("F2Dot14", "scaleY", None, None, ""),
        ],
    ),
    # PaintVarScale
    (
        "PaintFormat17",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 17"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarScale table) to Paint subtable.",
            ),
            ("F2Dot14", "scaleX", None, None, "VarIndexBase + 0."),
            ("F2Dot14", "scaleY", None, None, "VarIndexBase + 1."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintScaleAroundCenter
    (
        "PaintFormat18",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 18"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintScaleAroundCenter table) to Paint subtable.",
            ),
            ("F2Dot14", "scaleX", None, None, ""),
            ("F2Dot14", "scaleY", None, None, ""),
            ("int16", "centerX", None, None, ""),
            ("int16", "centerY", None, None, ""),
        ],
    ),
    # PaintVarScaleAroundCenter
    (
        "PaintFormat19",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 19"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarScaleAroundCenter table) to Paint subtable.",
            ),
            ("F2Dot14", "scaleX", None, None, "VarIndexBase + 0."),
            ("F2Dot14", "scaleY", None, None, "VarIndexBase + 1."),
            ("int16", "centerX", None, None, "VarIndexBase + 2."),
            ("int16", "centerY", None, None, "VarIndexBase + 3."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintScaleUniform
    (
        "PaintFormat20",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 20"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintScaleUniform table) to Paint subtable.",
            ),
            ("F2Dot14", "scale", None, None, ""),
        ],
    ),
    # PaintVarScaleUniform
    (
        "PaintFormat21",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 21"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarScaleUniform table) to Paint subtable.",
            ),
            ("F2Dot14", "scale", None, None, "VarIndexBase + 0."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintScaleUniformAroundCenter
    (
        "PaintFormat22",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 22"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintScaleUniformAroundCenter table) to Paint subtable.",
            ),
            ("F2Dot14", "scale", None, None, ""),
            ("int16", "centerX", None, None, ""),
            ("int16", "centerY", None, None, ""),
        ],
    ),
    # PaintVarScaleUniformAroundCenter
    (
        "PaintFormat23",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 23"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarScaleUniformAroundCenter table) to Paint subtable.",
            ),
            ("F2Dot14", "scale", None, None, "VarIndexBase + 0"),
            ("int16", "centerX", None, None, "VarIndexBase + 1"),
            ("int16", "centerY", None, None, "VarIndexBase + 2"),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintRotate
    (
        "PaintFormat24",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 24"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintRotate table) to Paint subtable.",
            ),
            ("Angle", "angle", None, None, ""),
        ],
    ),
    # PaintVarRotate
    (
        "PaintFormat25",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 25"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarRotate table) to Paint subtable.",
            ),
            ("Angle", "angle", None, None, "VarIndexBase + 0."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintRotateAroundCenter
    (
        "PaintFormat26",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 26"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintRotateAroundCenter table) to Paint subtable.",
            ),
            ("Angle", "angle", None, None, ""),
            ("int16", "centerX", None, None, ""),
            ("int16", "centerY", None, None, ""),
        ],
    ),
    # PaintVarRotateAroundCenter
    (
        "PaintFormat27",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 27"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarRotateAroundCenter table) to Paint subtable.",
            ),
            ("Angle", "angle", None, None, "VarIndexBase + 0."),
            ("int16", "centerX", None, None, "VarIndexBase + 1."),
            ("int16", "centerY", None, None, "VarIndexBase + 2."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintSkew
    (
        "PaintFormat28",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 28"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintSkew table) to Paint subtable.",
            ),
            ("Angle", "xSkewAngle", None, None, ""),
            ("Angle", "ySkewAngle", None, None, ""),
        ],
    ),
    # PaintVarSkew
    (
        "PaintFormat29",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 29"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarSkew table) to Paint subtable.",
            ),
            ("Angle", "xSkewAngle", None, None, "VarIndexBase + 0."),
            ("Angle", "ySkewAngle", None, None, "VarIndexBase + 1."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintSkewAroundCenter
    (
        "PaintFormat30",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 30"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintSkewAroundCenter table) to Paint subtable.",
            ),
            ("Angle", "xSkewAngle", None, None, ""),
            ("Angle", "ySkewAngle", None, None, ""),
            ("int16", "centerX", None, None, ""),
            ("int16", "centerY", None, None, ""),
        ],
    ),
    # PaintVarSkewAroundCenter
    (
        "PaintFormat31",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 31"),
            (
                "Offset24",
                "Paint",
                None,
                None,
                "Offset (from beginning of PaintVarSkewAroundCenter table) to Paint subtable.",
            ),
            ("Angle", "xSkewAngle", None, None, "VarIndexBase + 0."),
            ("Angle", "ySkewAngle", None, None, "VarIndexBase + 1."),
            ("int16", "centerX", None, None, "VarIndexBase + 2."),
            ("int16", "centerY", None, None, "VarIndexBase + 3."),
            (
                "VarIndex",
                "VarIndexBase",
                None,
                None,
                "Base index into DeltaSetIndexMap.",
            ),
        ],
    ),
    # PaintComposite
    (
        "PaintFormat32",
        [
            ("uint8", "PaintFormat", None, None, "Format identifier-format = 32"),
            (
                "LOffset24To(Paint)",
                "SourcePaint",
                None,
                None,
                "Offset (from beginning of PaintComposite table) to source Paint subtable.",
            ),
            (
                "CompositeMode",
                "CompositeMode",
                None,
                None,
                "A CompositeMode enumeration value.",
            ),
            (
                "LOffset24To(Paint)",
                "BackdropPaint",
                None,
                None,
                "Offset (from beginning of PaintComposite table) to backdrop Paint subtable.",
            ),
        ],
    ),
    #
    # avar
    #
    (
        "AxisValueMap",
        [
            (
                "F2Dot14",
                "FromCoordinate",
                None,
                None,
                "A normalized coordinate value obtained using default normalization",
            ),
            (
                "F2Dot14",
                "ToCoordinate",
                None,
                None,
                "The modified, normalized coordinate value",
            ),
        ],
    ),
    (
        "AxisSegmentMap",
        [
            (
                "uint16",
                "PositionMapCount",
                None,
                None,
                "The number of correspondence pairs for this axis",
            ),
            (
                "AxisValueMap",
                "AxisValueMap",
                "PositionMapCount",
                0,
                "The array of axis value map records for this axis",
            ),
        ],
    ),
    (
        "avar",
        [
            (
                "Version",
                "Version",
                None,
                None,
                "Version of the avar table- 0x00010000 or 0x00020000",
            ),
            ("uint16", "Reserved", None, None, "Permanently reserved; set to zero"),
            (
                "uint16",
                "AxisCount",
                None,
                None,
                'The number of variation axes for this font. This must be the same number as axisCount in the "fvar" table',
            ),
            (
                "AxisSegmentMap",
                "AxisSegmentMap",
                "AxisCount",
                0,
                'The segment maps array — one segment map for each axis, in the order of axes specified in the "fvar" table',
            ),
            (
                "LOffsetTo(DeltaSetIndexMap)",
                "VarIdxMap",
                None,
                "Version >= 0x00020000",
                "",
            ),
            ("LOffset", "VarStore", None, "Version >= 0x00020000", ""),
        ],
    ),
]
