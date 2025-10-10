from fontTools.misc.psCharStrings import (
    SimpleT2Decompiler,
    T2WidthExtractor,
    calcSubrBias,
)


def _uniq_sort(l):
    return sorted(set(l))


class StopHintCountEvent(Exception):
    pass


class _DesubroutinizingT2Decompiler(SimpleT2Decompiler):
    stop_hintcount_ops = (
        "op_hintmask",
        "op_cntrmask",
        "op_rmoveto",
        "op_hmoveto",
        "op_vmoveto",
    )

    def __init__(self, localSubrs, globalSubrs, private=None):
        SimpleT2Decompiler.__init__(self, localSubrs, globalSubrs, private)

    def execute(self, charString):
        self.need_hintcount = True  # until proven otherwise
        for op_name in self.stop_hintcount_ops:
            setattr(self, op_name, self.stop_hint_count)

        if hasattr(charString, "_desubroutinized"):
            # If a charstring has already been desubroutinized, we will still
            # need to execute it if we need to count hints in order to
            # compute the byte length for mask arguments, and haven't finished
            # counting hints pairs.
            if self.need_hintcount and self.callingStack:
                try:
                    SimpleT2Decompiler.execute(self, charString)
                except StopHintCountEvent:
                    del self.callingStack[-1]
            return

        charString._patches = []
        SimpleT2Decompiler.execute(self, charString)
        desubroutinized = charString.program[:]
        for idx, expansion in reversed(charString._patches):
            assert idx >= 2
            assert desubroutinized[idx - 1] in [
                "callsubr",
                "callgsubr",
            ], desubroutinized[idx - 1]
            assert type(desubroutinized[idx - 2]) == int
            if expansion[-1] == "return":
                expansion = expansion[:-1]
            desubroutinized[idx - 2 : idx] = expansion
        if not self.private.in_cff2:
            if "endchar" in desubroutinized:
                # Cut off after first endchar
                desubroutinized = desubroutinized[
                    : desubroutinized.index("endchar") + 1
                ]

        charString._desubroutinized = desubroutinized
        del charString._patches

    def op_callsubr(self, index):
        subr = self.localSubrs[self.operandStack[-1] + self.localBias]
        SimpleT2Decompiler.op_callsubr(self, index)
        self.processSubr(index, subr)

    def op_callgsubr(self, index):
        subr = self.globalSubrs[self.operandStack[-1] + self.globalBias]
        SimpleT2Decompiler.op_callgsubr(self, index)
        self.processSubr(index, subr)

    def stop_hint_count(self, *args):
        self.need_hintcount = False
        for op_name in self.stop_hintcount_ops:
            setattr(self, op_name, None)
        cs = self.callingStack[-1]
        if hasattr(cs, "_desubroutinized"):
            raise StopHintCountEvent()

    def op_hintmask(self, index):
        SimpleT2Decompiler.op_hintmask(self, index)
        if self.need_hintcount:
            self.stop_hint_count()

    def processSubr(self, index, subr):
        cs = self.callingStack[-1]
        if not hasattr(cs, "_desubroutinized"):
            cs._patches.append((index, subr._desubroutinized))


def desubroutinizeCharString(cs):
    """Desubroutinize a charstring in-place."""
    cs.decompile()
    subrs = getattr(cs.private, "Subrs", [])
    decompiler = _DesubroutinizingT2Decompiler(subrs, cs.globalSubrs, cs.private)
    decompiler.execute(cs)
    cs.program = cs._desubroutinized
    del cs._desubroutinized


def desubroutinize(cff):
    for fontName in cff.fontNames:
        font = cff[fontName]
        cs = font.CharStrings
        for c in cs.values():
            desubroutinizeCharString(c)
        # Delete all the local subrs
        if hasattr(font, "FDArray"):
            for fd in font.FDArray:
                pd = fd.Private
                if hasattr(pd, "Subrs"):
                    del pd.Subrs
                if "Subrs" in pd.rawDict:
                    del pd.rawDict["Subrs"]
        else:
            pd = font.Private
            if hasattr(pd, "Subrs"):
                del pd.Subrs
            if "Subrs" in pd.rawDict:
                del pd.rawDict["Subrs"]
    # as well as the global subrs
    cff.GlobalSubrs.clear()


class _MarkingT2Decompiler(SimpleT2Decompiler):
    def __init__(self, localSubrs, globalSubrs, private):
        SimpleT2Decompiler.__init__(self, localSubrs, globalSubrs, private)
        for subrs in [localSubrs, globalSubrs]:
            if subrs and not hasattr(subrs, "_used"):
                subrs._used = set()

    def op_callsubr(self, index):
        self.localSubrs._used.add(self.operandStack[-1] + self.localBias)
        SimpleT2Decompiler.op_callsubr(self, index)

    def op_callgsubr(self, index):
        self.globalSubrs._used.add(self.operandStack[-1] + self.globalBias)
        SimpleT2Decompiler.op_callgsubr(self, index)


class _DehintingT2Decompiler(T2WidthExtractor):
    class Hints(object):
        def __init__(self):
            # Whether calling this charstring produces any hint stems
            # Note that if a charstring starts with hintmask, it will
            # have has_hint set to True, because it *might* produce an
            # implicit vstem if called under certain conditions.
            self.has_hint = False
            # Index to start at to drop all hints
            self.last_hint = 0
            # Index up to which we know more hints are possible.
            # Only relevant if status is 0 or 1.
            self.last_checked = 0
            # The status means:
            # 0: after dropping hints, this charstring is empty
            # 1: after dropping hints, there may be more hints
            # 	continuing after this, or there might be
            # 	other things.  Not clear yet.
            # 2: no more hints possible after this charstring
            self.status = 0
            # Has hintmask instructions; not recursive
            self.has_hintmask = False
            # List of indices of calls to empty subroutines to remove.
            self.deletions = []

        pass

    def __init__(
        self, css, localSubrs, globalSubrs, nominalWidthX, defaultWidthX, private=None
    ):
        self._css = css
        T2WidthExtractor.__init__(
            self, localSubrs, globalSubrs, nominalWidthX, defaultWidthX
        )
        self.private = private

    def execute(self, charString):
        old_hints = charString._hints if hasattr(charString, "_hints") else None
        charString._hints = self.Hints()

        T2WidthExtractor.execute(self, charString)

        hints = charString._hints

        if hints.has_hint or hints.has_hintmask:
            self._css.add(charString)

        if hints.status != 2:
            # Check from last_check, make sure we didn't have any operators.
            for i in range(hints.last_checked, len(charString.program) - 1):
                if isinstance(charString.program[i], str):
                    hints.status = 2
                    break
                else:
                    hints.status = 1  # There's *something* here
            hints.last_checked = len(charString.program)

        if old_hints:
            assert hints.__dict__ == old_hints.__dict__

    def op_callsubr(self, index):
        subr = self.localSubrs[self.operandStack[-1] + self.localBias]
        T2WidthExtractor.op_callsubr(self, index)
        self.processSubr(index, subr)

    def op_callgsubr(self, index):
        subr = self.globalSubrs[self.operandStack[-1] + self.globalBias]
        T2WidthExtractor.op_callgsubr(self, index)
        self.processSubr(index, subr)

    def op_hstem(self, index):
        T2WidthExtractor.op_hstem(self, index)
        self.processHint(index)

    def op_vstem(self, index):
        T2WidthExtractor.op_vstem(self, index)
        self.processHint(index)

    def op_hstemhm(self, index):
        T2WidthExtractor.op_hstemhm(self, index)
        self.processHint(index)

    def op_vstemhm(self, index):
        T2WidthExtractor.op_vstemhm(self, index)
        self.processHint(index)

    def op_hintmask(self, index):
        rv = T2WidthExtractor.op_hintmask(self, index)
        self.processHintmask(index)
        return rv

    def op_cntrmask(self, index):
        rv = T2WidthExtractor.op_cntrmask(self, index)
        self.processHintmask(index)
        return rv

    def processHintmask(self, index):
        cs = self.callingStack[-1]
        hints = cs._hints
        hints.has_hintmask = True
        if hints.status != 2:
            # Check from last_check, see if we may be an implicit vstem
            for i in range(hints.last_checked, index - 1):
                if isinstance(cs.program[i], str):
                    hints.status = 2
                    break
            else:
                # We are an implicit vstem
                hints.has_hint = True
                hints.last_hint = index + 1
                hints.status = 0
        hints.last_checked = index + 1

    def processHint(self, index):
        cs = self.callingStack[-1]
        hints = cs._hints
        hints.has_hint = True
        hints.last_hint = index
        hints.last_checked = index

    def processSubr(self, index, subr):
        cs = self.callingStack[-1]
        hints = cs._hints
        subr_hints = subr._hints

        # Check from last_check, make sure we didn't have
        # any operators.
        if hints.status != 2:
            for i in range(hints.last_checked, index - 1):
                if isinstance(cs.program[i], str):
                    hints.status = 2
                    break
            hints.last_checked = index

        if hints.status != 2:
            if subr_hints.has_hint:
                hints.has_hint = True

                # Decide where to chop off from
                if subr_hints.status == 0:
                    hints.last_hint = index
                else:
                    hints.last_hint = index - 2  # Leave the subr call in

        elif subr_hints.status == 0:
            hints.deletions.append(index)

        hints.status = max(hints.status, subr_hints.status)


def _cs_subset_subroutines(charstring, subrs, gsubrs):
    p = charstring.program
    for i in range(1, len(p)):
        if p[i] == "callsubr":
            assert isinstance(p[i - 1], int)
            p[i - 1] = subrs._used.index(p[i - 1] + subrs._old_bias) - subrs._new_bias
        elif p[i] == "callgsubr":
            assert isinstance(p[i - 1], int)
            p[i - 1] = (
                gsubrs._used.index(p[i - 1] + gsubrs._old_bias) - gsubrs._new_bias
            )


def _cs_drop_hints(charstring):
    hints = charstring._hints

    if hints.deletions:
        p = charstring.program
        for idx in reversed(hints.deletions):
            del p[idx - 2 : idx]

    if hints.has_hint:
        assert not hints.deletions or hints.last_hint <= hints.deletions[0]
        charstring.program = charstring.program[hints.last_hint :]
        if not charstring.program:
            # TODO CFF2 no need for endchar.
            charstring.program.append("endchar")
        if hasattr(charstring, "width"):
            # Insert width back if needed
            if charstring.width != charstring.private.defaultWidthX:
                # For CFF2 charstrings, this should never happen
                assert (
                    charstring.private.defaultWidthX is not None
                ), "CFF2 CharStrings must not have an initial width value"
                charstring.program.insert(
                    0, charstring.width - charstring.private.nominalWidthX
                )

    if hints.has_hintmask:
        i = 0
        p = charstring.program
        while i < len(p):
            if p[i] in ["hintmask", "cntrmask"]:
                assert i + 1 <= len(p)
                del p[i : i + 2]
                continue
            i += 1

    assert len(charstring.program)

    del charstring._hints


def remove_hints(cff, *, removeUnusedSubrs: bool = True):
    for fontname in cff.keys():
        font = cff[fontname]
        cs = font.CharStrings
        # This can be tricky, but doesn't have to. What we do is:
        #
        # - Run all used glyph charstrings and recurse into subroutines,
        # - For each charstring (including subroutines), if it has any
        #   of the hint stem operators, we mark it as such.
        #   Upon returning, for each charstring we note all the
        #   subroutine calls it makes that (recursively) contain a stem,
        # - Dropping hinting then consists of the following two ops:
        #   * Drop the piece of the program in each charstring before the
        #     last call to a stem op or a stem-calling subroutine,
        #   * Drop all hintmask operations.
        # - It's trickier... A hintmask right after hints and a few numbers
        #    will act as an implicit vstemhm. As such, we track whether
        #    we have seen any non-hint operators so far and do the right
        #    thing, recursively... Good luck understanding that :(
        css = set()
        for c in cs.values():
            c.decompile()
            subrs = getattr(c.private, "Subrs", [])
            decompiler = _DehintingT2Decompiler(
                css,
                subrs,
                c.globalSubrs,
                c.private.nominalWidthX,
                c.private.defaultWidthX,
                c.private,
            )
            decompiler.execute(c)
            c.width = decompiler.width
        for charstring in css:
            _cs_drop_hints(charstring)
        del css

        # Drop font-wide hinting values
        all_privs = []
        if hasattr(font, "FDArray"):
            all_privs.extend(fd.Private for fd in font.FDArray)
        else:
            all_privs.append(font.Private)
        for priv in all_privs:
            for k in [
                "BlueValues",
                "OtherBlues",
                "FamilyBlues",
                "FamilyOtherBlues",
                "BlueScale",
                "BlueShift",
                "BlueFuzz",
                "StemSnapH",
                "StemSnapV",
                "StdHW",
                "StdVW",
                "ForceBold",
                "LanguageGroup",
                "ExpansionFactor",
            ]:
                if hasattr(priv, k):
                    setattr(priv, k, None)
    if removeUnusedSubrs:
        remove_unused_subroutines(cff)


def _pd_delete_empty_subrs(private_dict):
    if hasattr(private_dict, "Subrs") and not private_dict.Subrs:
        if "Subrs" in private_dict.rawDict:
            del private_dict.rawDict["Subrs"]
        del private_dict.Subrs


def remove_unused_subroutines(cff):
    for fontname in cff.keys():
        font = cff[fontname]
        cs = font.CharStrings
        # Renumber subroutines to remove unused ones

        # Mark all used subroutines
        for c in cs.values():
            subrs = getattr(c.private, "Subrs", [])
            decompiler = _MarkingT2Decompiler(subrs, c.globalSubrs, c.private)
            decompiler.execute(c)

        all_subrs = [font.GlobalSubrs]
        if hasattr(font, "FDArray"):
            all_subrs.extend(
                fd.Private.Subrs
                for fd in font.FDArray
                if hasattr(fd.Private, "Subrs") and fd.Private.Subrs
            )
        elif hasattr(font.Private, "Subrs") and font.Private.Subrs:
            all_subrs.append(font.Private.Subrs)

        subrs = set(subrs)  # Remove duplicates

        # Prepare
        for subrs in all_subrs:
            if not hasattr(subrs, "_used"):
                subrs._used = set()
            subrs._used = _uniq_sort(subrs._used)
            subrs._old_bias = calcSubrBias(subrs)
            subrs._new_bias = calcSubrBias(subrs._used)

        # Renumber glyph charstrings
        for c in cs.values():
            subrs = getattr(c.private, "Subrs", None)
            _cs_subset_subroutines(c, subrs, font.GlobalSubrs)

        # Renumber subroutines themselves
        for subrs in all_subrs:
            if subrs == font.GlobalSubrs:
                if not hasattr(font, "FDArray") and hasattr(font.Private, "Subrs"):
                    local_subrs = font.Private.Subrs
                elif (
                    hasattr(font, "FDArray")
                    and len(font.FDArray) == 1
                    and hasattr(font.FDArray[0].Private, "Subrs")
                ):
                    # Technically we shouldn't do this. But I've run into fonts that do it.
                    local_subrs = font.FDArray[0].Private.Subrs
                else:
                    local_subrs = None
            else:
                local_subrs = subrs

            subrs.items = [subrs.items[i] for i in subrs._used]
            if hasattr(subrs, "file"):
                del subrs.file
            if hasattr(subrs, "offsets"):
                del subrs.offsets

            for subr in subrs.items:
                _cs_subset_subroutines(subr, local_subrs, font.GlobalSubrs)

        # Delete local SubrsIndex if empty
        if hasattr(font, "FDArray"):
            for fd in font.FDArray:
                _pd_delete_empty_subrs(fd.Private)
        else:
            _pd_delete_empty_subrs(font.Private)

        # Cleanup
        for subrs in all_subrs:
            del subrs._used, subrs._old_bias, subrs._new_bias
