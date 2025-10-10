"""ttLib.tables.ttProgram.py -- Assembler/disassembler for TrueType bytecode programs."""

from __future__ import annotations

from fontTools.misc.textTools import num2binary, binary2num, readHex, strjoin
import array
from io import StringIO
from typing import List
import re
import logging


log = logging.getLogger(__name__)

# fmt: off

# first, the list of instructions that eat bytes or words from the instruction stream

streamInstructions = [
#
#   opcode  mnemonic   argBits    descriptive name         pops  pushes         eats from instruction stream          pushes
#
    (0x40,  'NPUSHB',        0,   'PushNBytes',              0, -1),    #                      n, b1, b2,...bn      b1,b2...bn
    (0x41,  'NPUSHW',        0,   'PushNWords',              0, -1),    #                       n, w1, w2,...w      w1,w2...wn
    (0xb0,  'PUSHB',         3,   'PushBytes',               0, -1),    #                          b0, b1,..bn  b0, b1, ...,bn
    (0xb8,  'PUSHW',         3,   'PushWords',               0, -1),    #                           w0,w1,..wn   w0 ,w1, ...wn
]


# next,    the list of "normal" instructions

instructions = [
#
#   opcode  mnemonic   argBits     descriptive name        pops  pushes         eats from instruction stream          pushes
#
    (0x7f,  'AA',            0,    'AdjustAngle',            1,  0),    #                                    p               -
    (0x64,  'ABS',           0,    'Absolute',               1,  1),    #                                    n             |n|
    (0x60,  'ADD',           0,    'Add',                    2,  1),    #                               n2, n1       (n1 + n2)
    (0x27,  'ALIGNPTS',      0,    'AlignPts',               2,  0),    #                               p2, p1               -
    (0x3c,  'ALIGNRP',       0,    'AlignRelativePt',       -1,  0),    #             p1, p2, ... , ploopvalue               -
    (0x5a,  'AND',           0,    'LogicalAnd',             2,  1),    #                               e2, e1               b
    (0x2b,  'CALL',          0,    'CallFunction',           1,  0),    #                                    f               -
    (0x67,  'CEILING',       0,    'Ceiling',                1,  1),    #                                    n         ceil(n)
    (0x25,  'CINDEX',        0,    'CopyXToTopStack',        1,  1),    #                                    k              ek
    (0x22,  'CLEAR',         0,    'ClearStack',            -1,  0),    #               all items on the stack               -
    (0x4f,  'DEBUG',         0,    'DebugCall',              1,  0),    #                                    n               -
    (0x73,  'DELTAC1',       0,    'DeltaExceptionC1',      -1,  0),    #    argn, cn, argn-1,cn-1, , arg1, c1               -
    (0x74,  'DELTAC2',       0,    'DeltaExceptionC2',      -1,  0),    #    argn, cn, argn-1,cn-1, , arg1, c1               -
    (0x75,  'DELTAC3',       0,    'DeltaExceptionC3',      -1,  0),    #    argn, cn, argn-1,cn-1, , arg1, c1               -
    (0x5d,  'DELTAP1',       0,    'DeltaExceptionP1',      -1,  0),    #   argn, pn, argn-1, pn-1, , arg1, p1               -
    (0x71,  'DELTAP2',       0,    'DeltaExceptionP2',      -1,  0),    #   argn, pn, argn-1, pn-1, , arg1, p1               -
    (0x72,  'DELTAP3',       0,    'DeltaExceptionP3',      -1,  0),    #   argn, pn, argn-1, pn-1, , arg1, p1               -
    (0x24,  'DEPTH',         0,    'GetDepthStack',          0,  1),    #                                    -               n
    (0x62,  'DIV',           0,    'Divide',                 2,  1),    #                               n2, n1   (n1 * 64)/ n2
    (0x20,  'DUP',           0,    'DuplicateTopStack',      1,  2),    #                                    e            e, e
    (0x59,  'EIF',           0,    'EndIf',                  0,  0),    #                                    -               -
    (0x1b,  'ELSE',          0,    'Else',                   0,  0),    #                                    -               -
    (0x2d,  'ENDF',          0,    'EndFunctionDefinition',  0,  0),    #                                    -               -
    (0x54,  'EQ',            0,    'Equal',                  2,  1),    #                               e2, e1               b
    (0x57,  'EVEN',          0,    'Even',                   1,  1),    #                                    e               b
    (0x2c,  'FDEF',          0,    'FunctionDefinition',     1,  0),    #                                    f               -
    (0x4e,  'FLIPOFF',       0,    'SetAutoFlipOff',         0,  0),    #                                    -               -
    (0x4d,  'FLIPON',        0,    'SetAutoFlipOn',          0,  0),    #                                    -               -
    (0x80,  'FLIPPT',        0,    'FlipPoint',             -1,  0),    #              p1, p2, ..., ploopvalue               -
    (0x82,  'FLIPRGOFF',     0,    'FlipRangeOff',           2,  0),    #                                 h, l               -
    (0x81,  'FLIPRGON',      0,    'FlipRangeOn',            2,  0),    #                                 h, l               -
    (0x66,  'FLOOR',         0,    'Floor',                  1,  1),    #                                    n        floor(n)
    (0x46,  'GC',            1,    'GetCoordOnPVector',      1,  1),    #                                    p               c
    (0x88,  'GETINFO',       0,    'GetInfo',                1,  1),    #                             selector          result
    (0x91,  'GETVARIATION',  0,    'GetVariation',           0, -1),    #                                    -        a1,..,an
    (0x0d,  'GFV',           0,    'GetFVector',             0,  2),    #                                    -          px, py
    (0x0c,  'GPV',           0,    'GetPVector',             0,  2),    #                                    -          px, py
    (0x52,  'GT',            0,    'GreaterThan',            2,  1),    #                               e2, e1               b
    (0x53,  'GTEQ',          0,    'GreaterThanOrEqual',     2,  1),    #                               e2, e1               b
    (0x89,  'IDEF',          0,    'InstructionDefinition',  1,  0),    #                                    f               -
    (0x58,  'IF',            0,    'If',                     1,  0),    #                                    e               -
    (0x8e,  'INSTCTRL',      0,    'SetInstrExecControl',    2,  0),    #                                 s, v               -
    (0x39,  'IP',            0,    'InterpolatePts',        -1,  0),    #             p1, p2, ... , ploopvalue               -
    (0x0f,  'ISECT',         0,    'MovePtToIntersect',      5,  0),    #                    a1, a0, b1, b0, p               -
    (0x30,  'IUP',           1,    'InterpolateUntPts',      0,  0),    #                                    -               -
    (0x1c,  'JMPR',          0,    'Jump',                   1,  0),    #                               offset               -
    (0x79,  'JROF',          0,    'JumpRelativeOnFalse',    2,  0),    #                            e, offset               -
    (0x78,  'JROT',          0,    'JumpRelativeOnTrue',     2,  0),    #                            e, offset               -
    (0x2a,  'LOOPCALL',      0,    'LoopAndCallFunction',    2,  0),    #                             f, count               -
    (0x50,  'LT',            0,    'LessThan',               2,  1),    #                               e2, e1               b
    (0x51,  'LTEQ',          0,    'LessThenOrEqual',        2,  1),    #                               e2, e1               b
    (0x8b,  'MAX',           0,    'Maximum',                2,  1),    #                               e2, e1     max(e1, e2)
    (0x49,  'MD',            1,    'MeasureDistance',        2,  1),    #                                p2,p1               d
    (0x2e,  'MDAP',          1,    'MoveDirectAbsPt',        1,  0),    #                                    p               -
    (0xc0,  'MDRP',          5,    'MoveDirectRelPt',        1,  0),    #                                    p               -
    (0x3e,  'MIAP',          1,    'MoveIndirectAbsPt',      2,  0),    #                                 n, p               -
    (0x8c,  'MIN',           0,    'Minimum',                2,  1),    #                               e2, e1     min(e1, e2)
    (0x26,  'MINDEX',        0,    'MoveXToTopStack',        1,  1),    #                                    k              ek
    (0xe0,  'MIRP',          5,    'MoveIndirectRelPt',      2,  0),    #                                 n, p               -
    (0x4b,  'MPPEM',         0,    'MeasurePixelPerEm',      0,  1),    #                                    -            ppem
    (0x4c,  'MPS',           0,    'MeasurePointSize',       0,  1),    #                                    -       pointSize
    (0x3a,  'MSIRP',         1,    'MoveStackIndirRelPt',    2,  0),    #                                 d, p               -
    (0x63,  'MUL',           0,    'Multiply',               2,  1),    #                               n2, n1    (n1 * n2)/64
    (0x65,  'NEG',           0,    'Negate',                 1,  1),    #                                    n              -n
    (0x55,  'NEQ',           0,    'NotEqual',               2,  1),    #                               e2, e1               b
    (0x5c,  'NOT',           0,    'LogicalNot',             1,  1),    #                                    e       ( not e )
    (0x6c,  'NROUND',        2,    'NoRound',                1,  1),    #                                   n1              n2
    (0x56,  'ODD',           0,    'Odd',                    1,  1),    #                                    e               b
    (0x5b,  'OR',            0,    'LogicalOr',              2,  1),    #                               e2, e1               b
    (0x21,  'POP',           0,    'PopTopStack',            1,  0),    #                                    e               -
    (0x45,  'RCVT',          0,    'ReadCVT',                1,  1),    #                             location           value
    (0x7d,  'RDTG',          0,    'RoundDownToGrid',        0,  0),    #                                    -               -
    (0x7a,  'ROFF',          0,    'RoundOff',               0,  0),    #                                    -               -
    (0x8a,  'ROLL',          0,    'RollTopThreeStack',      3,  3),    #                                a,b,c           b,a,c
    (0x68,  'ROUND',         2,    'Round',                  1,  1),    #                                   n1              n2
    (0x43,  'RS',            0,    'ReadStore',              1,  1),    #                                    n               v
    (0x3d,  'RTDG',          0,    'RoundToDoubleGrid',      0,  0),    #                                    -               -
    (0x18,  'RTG',           0,    'RoundToGrid',            0,  0),    #                                    -               -
    (0x19,  'RTHG',          0,    'RoundToHalfGrid',        0,  0),    #                                    -               -
    (0x7c,  'RUTG',          0,    'RoundUpToGrid',          0,  0),    #                                    -               -
    (0x77,  'S45ROUND',      0,    'SuperRound45Degrees',    1,  0),    #                                    n               -
    (0x7e,  'SANGW',         0,    'SetAngleWeight',         1,  0),    #                               weight               -
    (0x85,  'SCANCTRL',      0,    'ScanConversionControl',  1,  0),    #                                    n               -
    (0x8d,  'SCANTYPE',      0,    'ScanType',               1,  0),    #                                    n               -
    (0x48,  'SCFS',          0,    'SetCoordFromStackFP',    2,  0),    #                                 c, p               -
    (0x1d,  'SCVTCI',        0,    'SetCVTCutIn',            1,  0),    #                                    n               -
    (0x5e,  'SDB',           0,    'SetDeltaBaseInGState',   1,  0),    #                                    n               -
    (0x86,  'SDPVTL',        1,    'SetDualPVectorToLine',   2,  0),    #                               p2, p1               -
    (0x5f,  'SDS',           0,    'SetDeltaShiftInGState',  1,  0),    #                                    n               -
    (0x0b,  'SFVFS',         0,    'SetFVectorFromStack',    2,  0),    #                                 y, x               -
    (0x04,  'SFVTCA',        1,    'SetFVectorToAxis',       0,  0),    #                                    -               -
    (0x08,  'SFVTL',         1,    'SetFVectorToLine',       2,  0),    #                               p2, p1               -
    (0x0e,  'SFVTPV',        0,    'SetFVectorToPVector',    0,  0),    #                                    -               -
    (0x34,  'SHC',           1,    'ShiftContourByLastPt',   1,  0),    #                                    c               -
    (0x32,  'SHP',           1,    'ShiftPointByLastPoint', -1,  0),    #              p1, p2, ..., ploopvalue               -
    (0x38,  'SHPIX',         0,    'ShiftZoneByPixel',      -1,  0),    #           d, p1, p2, ..., ploopvalue               -
    (0x36,  'SHZ',           1,    'ShiftZoneByLastPoint',   1,  0),    #                                    e               -
    (0x17,  'SLOOP',         0,    'SetLoopVariable',        1,  0),    #                                    n               -
    (0x1a,  'SMD',           0,    'SetMinimumDistance',     1,  0),    #                             distance               -
    (0x0a,  'SPVFS',         0,    'SetPVectorFromStack',    2,  0),    #                                 y, x               -
    (0x02,  'SPVTCA',        1,    'SetPVectorToAxis',       0,  0),    #                                    -               -
    (0x06,  'SPVTL',         1,    'SetPVectorToLine',       2,  0),    #                               p2, p1               -
    (0x76,  'SROUND',        0,    'SuperRound',             1,  0),    #                                    n               -
    (0x10,  'SRP0',          0,    'SetRefPoint0',           1,  0),    #                                    p               -
    (0x11,  'SRP1',          0,    'SetRefPoint1',           1,  0),    #                                    p               -
    (0x12,  'SRP2',          0,    'SetRefPoint2',           1,  0),    #                                    p               -
    (0x1f,  'SSW',           0,    'SetSingleWidth',         1,  0),    #                                    n               -
    (0x1e,  'SSWCI',         0,    'SetSingleWidthCutIn',    1,  0),    #                                    n               -
    (0x61,  'SUB',           0,    'Subtract',               2,  1),    #                               n2, n1       (n1 - n2)
    (0x00,  'SVTCA',         1,    'SetFPVectorToAxis',      0,  0),    #                                    -               -
    (0x23,  'SWAP',          0,    'SwapTopStack',           2,  2),    #                               e2, e1          e1, e2
    (0x13,  'SZP0',          0,    'SetZonePointer0',        1,  0),    #                                    n               -
    (0x14,  'SZP1',          0,    'SetZonePointer1',        1,  0),    #                                    n               -
    (0x15,  'SZP2',          0,    'SetZonePointer2',        1,  0),    #                                    n               -
    (0x16,  'SZPS',          0,    'SetZonePointerS',        1,  0),    #                                    n               -
    (0x29,  'UTP',           0,    'UnTouchPt',              1,  0),    #                                    p               -
    (0x70,  'WCVTF',         0,    'WriteCVTInFUnits',       2,  0),    #                                 n, l               -
    (0x44,  'WCVTP',         0,    'WriteCVTInPixels',       2,  0),    #                                 v, l               -
    (0x42,  'WS',            0,    'WriteStore',             2,  0),    #                                 v, l               -
]

# fmt: on


def bitRepr(value, bits):
    s = ""
    for i in range(bits):
        s = "01"[value & 0x1] + s
        value = value >> 1
    return s


_mnemonicPat = re.compile(r"[A-Z][A-Z0-9]*$")


def _makeDict(instructionList):
    opcodeDict = {}
    mnemonicDict = {}
    for op, mnemonic, argBits, name, pops, pushes in instructionList:
        assert _mnemonicPat.match(mnemonic)
        mnemonicDict[mnemonic] = op, argBits, name
        if argBits:
            argoffset = op
            for i in range(1 << argBits):
                opcodeDict[op + i] = mnemonic, argBits, argoffset, name
        else:
            opcodeDict[op] = mnemonic, 0, 0, name
    return opcodeDict, mnemonicDict


streamOpcodeDict, streamMnemonicDict = _makeDict(streamInstructions)
opcodeDict, mnemonicDict = _makeDict(instructions)


class tt_instructions_error(Exception):
    def __init__(self, error):
        self.error = error

    def __str__(self):
        return "TT instructions error: %s" % repr(self.error)


_comment = r"/\*.*?\*/"
_instruction = r"([A-Z][A-Z0-9]*)\s*\[(.*?)\]"
_number = r"-?[0-9]+"
_token = "(%s)|(%s)|(%s)" % (_instruction, _number, _comment)

_tokenRE = re.compile(_token)
_whiteRE = re.compile(r"\s*")

_pushCountPat = re.compile(r"[A-Z][A-Z0-9]*\s*\[.*?\]\s*/\* ([0-9]+).*?\*/")

_indentRE = re.compile(r"^FDEF|IF|ELSE\[ \]\t.+")
_unindentRE = re.compile(r"^ELSE|ENDF|EIF\[ \]\t.+")


def _skipWhite(data, pos):
    m = _whiteRE.match(data, pos)
    newPos = m.regs[0][1]
    assert newPos >= pos
    return newPos


class Program(object):
    def __init__(self) -> None:
        pass

    def fromBytecode(self, bytecode: bytes) -> None:
        self.bytecode = array.array("B", bytecode)
        if hasattr(self, "assembly"):
            del self.assembly

    def fromAssembly(self, assembly: List[str] | str) -> None:
        if isinstance(assembly, list):
            self.assembly = assembly
        elif isinstance(assembly, str):
            self.assembly = assembly.splitlines()
        else:
            raise TypeError(f"expected str or List[str], got {type(assembly).__name__}")
        if hasattr(self, "bytecode"):
            del self.bytecode

    def getBytecode(self) -> bytes:
        if not hasattr(self, "bytecode"):
            self._assemble()
        return self.bytecode.tobytes()

    def getAssembly(self, preserve=True) -> List[str]:
        if not hasattr(self, "assembly"):
            self._disassemble(preserve=preserve)
        return self.assembly

    def toXML(self, writer, ttFont) -> None:
        if (
            not hasattr(ttFont, "disassembleInstructions")
            or ttFont.disassembleInstructions
        ):
            try:
                assembly = self.getAssembly()
            except:
                import traceback

                tmp = StringIO()
                traceback.print_exc(file=tmp)
                msg = "An exception occurred during the decompilation of glyph program:\n\n"
                msg += tmp.getvalue()
                log.error(msg)
                writer.begintag("bytecode")
                writer.newline()
                writer.comment(msg.strip())
                writer.newline()
                writer.dumphex(self.getBytecode())
                writer.endtag("bytecode")
                writer.newline()
            else:
                if not assembly:
                    return
                writer.begintag("assembly")
                writer.newline()
                i = 0
                indent = 0
                nInstr = len(assembly)
                while i < nInstr:
                    instr = assembly[i]
                    if _unindentRE.match(instr):
                        indent -= 1
                    writer.write(writer.indentwhite * indent)
                    writer.write(instr)
                    writer.newline()
                    m = _pushCountPat.match(instr)
                    i = i + 1
                    if m:
                        nValues = int(m.group(1))
                        line: List[str] = []
                        j = 0
                        for j in range(nValues):
                            if j and not (j % 25):
                                writer.write(writer.indentwhite * indent)
                                writer.write(" ".join(line))
                                writer.newline()
                                line = []
                            line.append(assembly[i + j])
                        writer.write(writer.indentwhite * indent)
                        writer.write(" ".join(line))
                        writer.newline()
                        i = i + j + 1
                    if _indentRE.match(instr):
                        indent += 1
                writer.endtag("assembly")
                writer.newline()
        else:
            bytecode = self.getBytecode()
            if not bytecode:
                return
            writer.begintag("bytecode")
            writer.newline()
            writer.dumphex(bytecode)
            writer.endtag("bytecode")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont) -> None:
        if name == "assembly":
            self.fromAssembly(strjoin(content))
            self._assemble()
            del self.assembly
        else:
            assert name == "bytecode"
            self.fromBytecode(readHex(content))

    def _assemble(self) -> None:
        assembly = " ".join(getattr(self, "assembly", []))
        bytecode: List[int] = []
        push = bytecode.append
        lenAssembly = len(assembly)
        pos = _skipWhite(assembly, 0)
        while pos < lenAssembly:
            m = _tokenRE.match(assembly, pos)
            if m is None:
                raise tt_instructions_error(
                    "Syntax error in TT program (%s)" % assembly[pos - 5 : pos + 15]
                )
            dummy, mnemonic, arg, number, comment = m.groups()
            pos = m.regs[0][1]
            if comment:
                pos = _skipWhite(assembly, pos)
                continue

            arg = arg.strip()
            if mnemonic.startswith("INSTR"):
                # Unknown instruction
                op = int(mnemonic[5:])
                push(op)
            elif mnemonic not in ("PUSH", "NPUSHB", "NPUSHW", "PUSHB", "PUSHW"):
                op, argBits, name = mnemonicDict[mnemonic]
                if len(arg) != argBits:
                    raise tt_instructions_error(
                        "Incorrect number of argument bits (%s[%s])" % (mnemonic, arg)
                    )
                if arg:
                    arg = binary2num(arg)
                    push(op + arg)
                else:
                    push(op)
            else:
                args = []
                pos = _skipWhite(assembly, pos)
                while pos < lenAssembly:
                    m = _tokenRE.match(assembly, pos)
                    if m is None:
                        raise tt_instructions_error(
                            "Syntax error in TT program (%s)" % assembly[pos : pos + 15]
                        )
                    dummy, _mnemonic, arg, number, comment = m.groups()
                    if number is None and comment is None:
                        break
                    pos = m.regs[0][1]
                    pos = _skipWhite(assembly, pos)
                    if comment is not None:
                        continue
                    args.append(int(number))
                nArgs = len(args)
                if mnemonic == "PUSH":
                    # Automatically choose the most compact representation
                    nWords = 0
                    while nArgs:
                        while (
                            nWords < nArgs
                            and nWords < 255
                            and not (0 <= args[nWords] <= 255)
                        ):
                            nWords += 1
                        nBytes = 0
                        while (
                            nWords + nBytes < nArgs
                            and nBytes < 255
                            and 0 <= args[nWords + nBytes] <= 255
                        ):
                            nBytes += 1
                        if (
                            nBytes < 2
                            and nWords + nBytes < 255
                            and nWords + nBytes != nArgs
                        ):
                            # Will write bytes as words
                            nWords += nBytes
                            continue

                        # Write words
                        if nWords:
                            if nWords <= 8:
                                op, argBits, name = streamMnemonicDict["PUSHW"]
                                op = op + nWords - 1
                                push(op)
                            else:
                                op, argBits, name = streamMnemonicDict["NPUSHW"]
                                push(op)
                                push(nWords)
                            for value in args[:nWords]:
                                assert -32768 <= value < 32768, (
                                    "PUSH value out of range %d" % value
                                )
                                push((value >> 8) & 0xFF)
                                push(value & 0xFF)

                        # Write bytes
                        if nBytes:
                            pass
                            if nBytes <= 8:
                                op, argBits, name = streamMnemonicDict["PUSHB"]
                                op = op + nBytes - 1
                                push(op)
                            else:
                                op, argBits, name = streamMnemonicDict["NPUSHB"]
                                push(op)
                                push(nBytes)
                            for value in args[nWords : nWords + nBytes]:
                                push(value)

                        nTotal = nWords + nBytes
                        args = args[nTotal:]
                        nArgs -= nTotal
                        nWords = 0
                else:
                    # Write exactly what we've been asked to
                    words = mnemonic[-1] == "W"
                    op, argBits, name = streamMnemonicDict[mnemonic]
                    if mnemonic[0] != "N":
                        assert nArgs <= 8, nArgs
                        op = op + nArgs - 1
                        push(op)
                    else:
                        assert nArgs < 256
                        push(op)
                        push(nArgs)
                    if words:
                        for value in args:
                            assert -32768 <= value < 32768, (
                                "PUSHW value out of range %d" % value
                            )
                            push((value >> 8) & 0xFF)
                            push(value & 0xFF)
                    else:
                        for value in args:
                            assert 0 <= value < 256, (
                                "PUSHB value out of range %d" % value
                            )
                            push(value)

            pos = _skipWhite(assembly, pos)

        if bytecode:
            assert max(bytecode) < 256 and min(bytecode) >= 0
        self.bytecode = array.array("B", bytecode)

    def _disassemble(self, preserve=False) -> None:
        assembly = []
        i = 0
        bytecode = getattr(self, "bytecode", [])
        numBytecode = len(bytecode)
        while i < numBytecode:
            op = bytecode[i]
            try:
                mnemonic, argBits, argoffset, name = opcodeDict[op]
            except KeyError:
                if op in streamOpcodeDict:
                    values = []

                    # Merge consecutive PUSH operations
                    while bytecode[i] in streamOpcodeDict:
                        op = bytecode[i]
                        mnemonic, argBits, argoffset, name = streamOpcodeDict[op]
                        words = mnemonic[-1] == "W"
                        if argBits:
                            nValues = op - argoffset + 1
                        else:
                            i = i + 1
                            nValues = bytecode[i]
                        i = i + 1
                        assert nValues > 0
                        if not words:
                            for j in range(nValues):
                                value = bytecode[i]
                                values.append(repr(value))
                                i = i + 1
                        else:
                            for j in range(nValues):
                                # cast to signed int16
                                value = (bytecode[i] << 8) | bytecode[i + 1]
                                if value >= 0x8000:
                                    value = value - 0x10000
                                values.append(repr(value))
                                i = i + 2
                        if preserve:
                            break

                    if not preserve:
                        mnemonic = "PUSH"
                    nValues = len(values)
                    if nValues == 1:
                        assembly.append("%s[ ]	/* 1 value pushed */" % mnemonic)
                    else:
                        assembly.append(
                            "%s[ ]	/* %s values pushed */" % (mnemonic, nValues)
                        )
                    assembly.extend(values)
                else:
                    assembly.append("INSTR%d[ ]" % op)
                    i = i + 1
            else:
                if argBits:
                    assembly.append(
                        mnemonic
                        + "[%s]	/* %s */" % (num2binary(op - argoffset, argBits), name)
                    )
                else:
                    assembly.append(mnemonic + "[ ]	/* %s */" % name)
                i = i + 1
        self.assembly = assembly

    def __bool__(self) -> bool:
        """
        >>> p = Program()
        >>> bool(p)
        False
        >>> bc = array.array("B", [0])
        >>> p.fromBytecode(bc)
        >>> bool(p)
        True
        >>> p.bytecode.pop()
        0
        >>> bool(p)
        False

        >>> p = Program()
        >>> asm = ['SVTCA[0]']
        >>> p.fromAssembly(asm)
        >>> bool(p)
        True
        >>> p.assembly.pop()
        'SVTCA[0]'
        >>> bool(p)
        False
        """
        return (hasattr(self, "assembly") and len(self.assembly) > 0) or (
            hasattr(self, "bytecode") and len(self.bytecode) > 0
        )

    __nonzero__ = __bool__

    def __eq__(self, other) -> bool:
        if type(self) != type(other):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        return result if result is NotImplemented else not result


def _test():
    """
    >>> _test()
    True
    """

    bc = b"""@;:9876543210/.-,+*)(\'&%$#"! \037\036\035\034\033\032\031\030\027\026\025\024\023\022\021\020\017\016\015\014\013\012\011\010\007\006\005\004\003\002\001\000,\001\260\030CXEj\260\031C`\260F#D#\020 \260FN\360M/\260\000\022\033!#\0213Y-,\001\260\030CX\260\005+\260\000\023K\260\024PX\261\000@8Y\260\006+\033!#\0213Y-,\001\260\030CXN\260\003%\020\362!\260\000\022M\033 E\260\004%\260\004%#Jad\260(RX!#\020\326\033\260\003%\020\362!\260\000\022YY-,\260\032CX!!\033\260\002%\260\002%I\260\003%\260\003%Ja d\260\020PX!!!\033\260\003%\260\003%I\260\000PX\260\000PX\270\377\3428!\033\260\0208!Y\033\260\000RX\260\0368!\033\270\377\3608!YYYY-,\001\260\030CX\260\005+\260\000\023K\260\024PX\271\000\000\377\3008Y\260\006+\033!#\0213Y-,N\001\212\020\261F\031CD\260\000\024\261\000F\342\260\000\025\271\000\000\377\3608\000\260\000<\260(+\260\002%\020\260\000<-,\001\030\260\000/\260\001\024\362\260\001\023\260\001\025M\260\000\022-,\001\260\030CX\260\005+\260\000\023\271\000\000\377\3408\260\006+\033!#\0213Y-,\001\260\030CXEdj#Edi\260\031Cd``\260F#D#\020 \260F\360/\260\000\022\033!! \212 \212RX\0213\033!!YY-,\001\261\013\012C#Ce\012-,\000\261\012\013C#C\013-,\000\260F#p\261\001F>\001\260F#p\261\002FE:\261\002\000\010\015-,\260\022+\260\002%E\260\002%Ej\260@\213`\260\002%#D!!!-,\260\023+\260\002%E\260\002%Ej\270\377\300\214`\260\002%#D!!!-,\260\000\260\022+!!!-,\260\000\260\023+!!!-,\001\260\006C\260\007Ce\012-, i\260@a\260\000\213 \261,\300\212\214\270\020\000b`+\014d#da\\X\260\003aY-,\261\000\003%EhT\260\034KPZX\260\003%E\260\003%E`h \260\004%#D\260\004%#D\033\260\003% Eh \212#D\260\003%Eh`\260\003%#DY-,\260\003% Eh \212#D\260\003%Edhe`\260\004%\260\001`#D-,\260\011CX\207!\300\033\260\022CX\207E\260\021+\260G#D\260Gz\344\033\003\212E\030i \260G#D\212\212\207 \260\240QX\260\021+\260G#D\260Gz\344\033!\260Gz\344YYY\030-, \212E#Eh`D-,EjB-,\001\030/-,\001\260\030CX\260\004%\260\004%Id#Edi\260@\213a \260\200bj\260\002%\260\002%a\214\260\031C`\260F#D!\212\020\260F\366!\033!!!!Y-,\001\260\030CX\260\002%E\260\002%Ed`j\260\003%Eja \260\004%Ej \212\213e\260\004%#D\214\260\003%#D!!\033 EjD EjDY-,\001 E\260\000U\260\030CZXEh#Ei\260@\213a \260\200bj \212#a \260\003%\213e\260\004%#D\214\260\003%#D!!\033!!\260\031+Y-,\001\212\212Ed#EdadB-,\260\004%\260\004%\260\031+\260\030CX\260\004%\260\004%\260\003%\260\033+\001\260\002%C\260@T\260\002%C\260\000TZX\260\003% E\260@aDY\260\002%C\260\000T\260\002%C\260@TZX\260\004% E\260@`DYY!!!!-,\001KRXC\260\002%E#aD\033!!Y-,\001KRXC\260\002%E#`D\033!!Y-,KRXED\033!!Y-,\001 \260\003%#I\260@`\260 c \260\000RX#\260\002%8#\260\002%e8\000\212c8\033!!!!!Y\001-,KPXED\033!!Y-,\001\260\005%\020# \212\365\000\260\001`#\355\354-,\001\260\005%\020# \212\365\000\260\001a#\355\354-,\001\260\006%\020\365\000\355\354-,F#F`\212\212F# F\212`\212a\270\377\200b# \020#\212\261KK\212pE` \260\000PX\260\001a\270\377\272\213\033\260F\214Y\260\020`h\001:-, E\260\003%FRX\260\002%F ha\260\003%\260\003%?#!8\033!\021Y-, E\260\003%FPX\260\002%F ha\260\003%\260\003%?#!8\033!\021Y-,\000\260\007C\260\006C\013-,\212\020\354-,\260\014CX!\033 F\260\000RX\270\377\3608\033\260\0208YY-, \260\000UX\270\020\000c\260\003%Ed\260\003%Eda\260\000SX\260\002\033\260@a\260\003Y%EiSXED\033!!Y\033!\260\002%E\260\002%Ead\260(QXED\033!!YY-,!!\014d#d\213\270@\000b-,!\260\200QX\014d#d\213\270 \000b\033\262\000@/+Y\260\002`-,!\260\300QX\014d#d\213\270\025Ub\033\262\000\200/+Y\260\002`-,\014d#d\213\270@\000b`#!-,KSX\260\004%\260\004%Id#Edi\260@\213a \260\200bj\260\002%\260\002%a\214\260F#D!\212\020\260F\366!\033!\212\021#\022 9/Y-,\260\002%\260\002%Id\260\300TX\270\377\3708\260\0108\033!!Y-,\260\023CX\003\033\002Y-,\260\023CX\002\033\003Y-,\260\012+#\020 <\260\027+-,\260\002%\270\377\3608\260(+\212\020# \320#\260\020+\260\005CX\300\033<Y \020\021\260\000\022\001-,KS#KQZX8\033!!Y-,\001\260\002%\020\320#\311\001\260\001\023\260\000\024\020\260\001<\260\001\026-,\001\260\000\023\260\001\260\003%I\260\003\0278\260\001\023-,KS#KQZX E\212`D\033!!Y-, 9/-"""

    p = Program()
    p.fromBytecode(bc)
    asm = p.getAssembly(preserve=True)
    p.fromAssembly(asm)
    print(bc == p.getBytecode())


if __name__ == "__main__":
    import sys
    import doctest

    sys.exit(doctest.testmod().failed)
