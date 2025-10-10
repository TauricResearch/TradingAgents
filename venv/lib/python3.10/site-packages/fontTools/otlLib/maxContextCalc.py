__all__ = ["maxCtxFont"]


def maxCtxFont(font):
    """Calculate the usMaxContext value for an entire font."""

    maxCtx = 0
    for tag in ("GSUB", "GPOS"):
        if tag not in font:
            continue
        table = font[tag].table
        if not table.LookupList:
            continue
        for lookup in table.LookupList.Lookup:
            for st in lookup.SubTable:
                maxCtx = maxCtxSubtable(maxCtx, tag, lookup.LookupType, st)
    return maxCtx


def maxCtxSubtable(maxCtx, tag, lookupType, st):
    """Calculate usMaxContext based on a single lookup table (and an existing
    max value).
    """

    # single positioning, single / multiple substitution
    if (tag == "GPOS" and lookupType == 1) or (
        tag == "GSUB" and lookupType in (1, 2, 3)
    ):
        maxCtx = max(maxCtx, 1)

    # pair positioning
    elif tag == "GPOS" and lookupType == 2:
        maxCtx = max(maxCtx, 2)

    # ligatures
    elif tag == "GSUB" and lookupType == 4:
        for ligatures in st.ligatures.values():
            for ligature in ligatures:
                maxCtx = max(maxCtx, ligature.CompCount)

    # context
    elif (tag == "GPOS" and lookupType == 7) or (tag == "GSUB" and lookupType == 5):
        maxCtx = maxCtxContextualSubtable(maxCtx, st, "Pos" if tag == "GPOS" else "Sub")

    # chained context
    elif (tag == "GPOS" and lookupType == 8) or (tag == "GSUB" and lookupType == 6):
        maxCtx = maxCtxContextualSubtable(
            maxCtx, st, "Pos" if tag == "GPOS" else "Sub", "Chain"
        )

    # extensions
    elif (tag == "GPOS" and lookupType == 9) or (tag == "GSUB" and lookupType == 7):
        maxCtx = maxCtxSubtable(maxCtx, tag, st.ExtensionLookupType, st.ExtSubTable)

    # reverse-chained context
    elif tag == "GSUB" and lookupType == 8:
        maxCtx = maxCtxContextualRule(maxCtx, st, "Reverse")

    return maxCtx


def maxCtxContextualSubtable(maxCtx, st, ruleType, chain=""):
    """Calculate usMaxContext based on a contextual feature subtable."""

    if st.Format == 1:
        for ruleset in getattr(st, "%s%sRuleSet" % (chain, ruleType)):
            if ruleset is None:
                continue
            for rule in getattr(ruleset, "%s%sRule" % (chain, ruleType)):
                if rule is None:
                    continue
                maxCtx = maxCtxContextualRule(maxCtx, rule, chain)

    elif st.Format == 2:
        for ruleset in getattr(st, "%s%sClassSet" % (chain, ruleType)):
            if ruleset is None:
                continue
            for rule in getattr(ruleset, "%s%sClassRule" % (chain, ruleType)):
                if rule is None:
                    continue
                maxCtx = maxCtxContextualRule(maxCtx, rule, chain)

    elif st.Format == 3:
        maxCtx = maxCtxContextualRule(maxCtx, st, chain)

    return maxCtx


def maxCtxContextualRule(maxCtx, st, chain):
    """Calculate usMaxContext based on a contextual feature rule."""

    if not chain:
        return max(maxCtx, st.GlyphCount)
    elif chain == "Reverse":
        return max(maxCtx, 1 + st.LookAheadGlyphCount)
    return max(maxCtx, st.InputGlyphCount + st.LookAheadGlyphCount)
