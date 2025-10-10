"""Module for reading TFM (TeX Font Metrics) files.

The TFM format is described in the TFtoPL WEB source code, whose typeset form
can be found on `CTAN <http://mirrors.ctan.org/info/knuth-pdf/texware/tftopl.pdf>`_.

	>>> from fontTools.tfmLib import TFM
	>>> tfm = TFM("Tests/tfmLib/data/cmr10.tfm")
	>>>
	>>> # Accessing an attribute gets you metadata.
	>>> tfm.checksum
	1274110073
	>>> tfm.designsize
	10.0
	>>> tfm.codingscheme
	'TeX text'
	>>> tfm.family
	'CMR'
	>>> tfm.seven_bit_safe_flag
	False
	>>> tfm.face
	234
	>>> tfm.extraheader
	{}
	>>> tfm.fontdimens
	{'SLANT': 0.0, 'SPACE': 0.33333396911621094, 'STRETCH': 0.16666698455810547, 'SHRINK': 0.11111164093017578, 'XHEIGHT': 0.4305553436279297, 'QUAD': 1.0000028610229492, 'EXTRASPACE': 0.11111164093017578}
	>>> # Accessing a character gets you its metrics.
	>>> # “width” is always available, other metrics are available only when
	>>> # applicable. All values are relative to “designsize”.
	>>> tfm.chars[ord("g")]
	{'width': 0.5000019073486328, 'height': 0.4305553436279297, 'depth': 0.1944446563720703, 'italic': 0.013888359069824219}
	>>> # Kerning and ligature can be accessed as well.
	>>> tfm.kerning[ord("c")]
	{104: -0.02777862548828125, 107: -0.02777862548828125}
	>>> tfm.ligatures[ord("f")]
	{105: ('LIG', 12), 102: ('LIG', 11), 108: ('LIG', 13)}
"""

from types import SimpleNamespace

from fontTools.misc.sstruct import calcsize, unpack, unpack2

SIZES_FORMAT = """
    >
    lf: h    # length of the entire file, in words
    lh: h    # length of the header data, in words
    bc: h    # smallest character code in the font
    ec: h    # largest character code in the font
    nw: h    # number of words in the width table
    nh: h    # number of words in the height table
    nd: h    # number of words in the depth table
    ni: h    # number of words in the italic correction table
    nl: h    # number of words in the ligature/kern table
    nk: h    # number of words in the kern table
    ne: h    # number of words in the extensible character table
    np: h    # number of font parameter words
"""

SIZES_SIZE = calcsize(SIZES_FORMAT)

FIXED_FORMAT = "12.20F"

HEADER_FORMAT1 = f"""
    >
    checksum:            L
    designsize:          {FIXED_FORMAT}
"""

HEADER_FORMAT2 = f"""
    {HEADER_FORMAT1}
    codingscheme:        40p
"""

HEADER_FORMAT3 = f"""
    {HEADER_FORMAT2}
    family:              20p
"""

HEADER_FORMAT4 = f"""
    {HEADER_FORMAT3}
    seven_bit_safe_flag: ?
    ignored:             x
    ignored:             x
    face:                B
"""

HEADER_SIZE1 = calcsize(HEADER_FORMAT1)
HEADER_SIZE2 = calcsize(HEADER_FORMAT2)
HEADER_SIZE3 = calcsize(HEADER_FORMAT3)
HEADER_SIZE4 = calcsize(HEADER_FORMAT4)

LIG_KERN_COMMAND = """
    >
    skip_byte: B
    next_char: B
    op_byte: B
    remainder: B
"""

BASE_PARAMS = [
    "SLANT",
    "SPACE",
    "STRETCH",
    "SHRINK",
    "XHEIGHT",
    "QUAD",
    "EXTRASPACE",
]

MATHSY_PARAMS = [
    "NUM1",
    "NUM2",
    "NUM3",
    "DENOM1",
    "DENOM2",
    "SUP1",
    "SUP2",
    "SUP3",
    "SUB1",
    "SUB2",
    "SUPDROP",
    "SUBDROP",
    "DELIM1",
    "DELIM2",
    "AXISHEIGHT",
]

MATHEX_PARAMS = [
    "DEFAULTRULETHICKNESS",
    "BIGOPSPACING1",
    "BIGOPSPACING2",
    "BIGOPSPACING3",
    "BIGOPSPACING4",
    "BIGOPSPACING5",
]

VANILLA = 0
MATHSY = 1
MATHEX = 2

UNREACHABLE = 0
PASSTHROUGH = 1
ACCESSABLE = 2

NO_TAG = 0
LIG_TAG = 1
LIST_TAG = 2
EXT_TAG = 3

STOP_FLAG = 128
KERN_FLAG = 128


class TFMException(Exception):
    def __init__(self, message):
        super().__init__(message)


class TFM:
    def __init__(self, file):
        self._read(file)

    def __repr__(self):
        return (
            f"<TFM"
            f" for {self.family}"
            f" in {self.codingscheme}"
            f" at {self.designsize:g}pt>"
        )

    def _read(self, file):
        if hasattr(file, "read"):
            data = file.read()
        else:
            with open(file, "rb") as fp:
                data = fp.read()

        self._data = data

        if len(data) < SIZES_SIZE:
            raise TFMException("Too short input file")

        sizes = SimpleNamespace()
        unpack2(SIZES_FORMAT, data, sizes)

        # Do some file structure sanity checks.
        # TeX and TFtoPL do additional functional checks and might even correct
        # “errors” in the input file, but we instead try to output the file as
        # it is as long as it is parsable, even if the data make no sense.

        if sizes.lf < 0:
            raise TFMException("The file claims to have negative or zero length!")

        if len(data) < sizes.lf * 4:
            raise TFMException("The file has fewer bytes than it claims!")

        for name, length in vars(sizes).items():
            if length < 0:
                raise TFMException("The subfile size: '{name}' is negative!")

        if sizes.lh < 2:
            raise TFMException(f"The header length is only {sizes.lh}!")

        if sizes.bc > sizes.ec + 1 or sizes.ec > 255:
            raise TFMException(
                f"The character code range {sizes.bc}..{sizes.ec} is illegal!"
            )

        if sizes.nw == 0 or sizes.nh == 0 or sizes.nd == 0 or sizes.ni == 0:
            raise TFMException("Incomplete subfiles for character dimensions!")

        if sizes.ne > 256:
            raise TFMException(f"There are {ne} extensible recipes!")

        if sizes.lf != (
            6
            + sizes.lh
            + (sizes.ec - sizes.bc + 1)
            + sizes.nw
            + sizes.nh
            + sizes.nd
            + sizes.ni
            + sizes.nl
            + sizes.nk
            + sizes.ne
            + sizes.np
        ):
            raise TFMException("Subfile sizes don’t add up to the stated total")

        # Subfile offsets, used in the helper function below. These all are
        # 32-bit word offsets not 8-bit byte offsets.
        char_base = 6 + sizes.lh - sizes.bc
        width_base = char_base + sizes.ec + 1
        height_base = width_base + sizes.nw
        depth_base = height_base + sizes.nh
        italic_base = depth_base + sizes.nd
        lig_kern_base = italic_base + sizes.ni
        kern_base = lig_kern_base + sizes.nl
        exten_base = kern_base + sizes.nk
        param_base = exten_base + sizes.ne

        # Helper functions for accessing individual data. If this looks
        # nonidiomatic Python, I blame the effect of reading the literate WEB
        # documentation of TFtoPL.
        def char_info(c):
            return 4 * (char_base + c)

        def width_index(c):
            return data[char_info(c)]

        def noneexistent(c):
            return c < sizes.bc or c > sizes.ec or width_index(c) == 0

        def height_index(c):
            return data[char_info(c) + 1] // 16

        def depth_index(c):
            return data[char_info(c) + 1] % 16

        def italic_index(c):
            return data[char_info(c) + 2] // 4

        def tag(c):
            return data[char_info(c) + 2] % 4

        def remainder(c):
            return data[char_info(c) + 3]

        def width(c):
            r = 4 * (width_base + width_index(c))
            return read_fixed(r, "v")["v"]

        def height(c):
            r = 4 * (height_base + height_index(c))
            return read_fixed(r, "v")["v"]

        def depth(c):
            r = 4 * (depth_base + depth_index(c))
            return read_fixed(r, "v")["v"]

        def italic(c):
            r = 4 * (italic_base + italic_index(c))
            return read_fixed(r, "v")["v"]

        def exten(c):
            return 4 * (exten_base + remainder(c))

        def lig_step(i):
            return 4 * (lig_kern_base + i)

        def lig_kern_command(i):
            command = SimpleNamespace()
            unpack2(LIG_KERN_COMMAND, data[i:], command)
            return command

        def kern(i):
            r = 4 * (kern_base + i)
            return read_fixed(r, "v")["v"]

        def param(i):
            return 4 * (param_base + i)

        def read_fixed(index, key, obj=None):
            ret = unpack2(f">;{key}:{FIXED_FORMAT}", data[index:], obj)
            return ret[0]

        # Set all attributes to empty values regardless of the header size.
        unpack(HEADER_FORMAT4, [0] * HEADER_SIZE4, self)

        offset = 24
        length = sizes.lh * 4
        self.extraheader = {}
        if length >= HEADER_SIZE4:
            rest = unpack2(HEADER_FORMAT4, data[offset:], self)[1]
            if self.face < 18:
                s = self.face % 2
                b = self.face // 2
                self.face = "MBL"[b % 3] + "RI"[s] + "RCE"[b // 3]
            for i in range(sizes.lh - HEADER_SIZE4 // 4):
                rest = unpack2(f">;HEADER{i + 18}:l", rest, self.extraheader)[1]
        elif length >= HEADER_SIZE3:
            unpack2(HEADER_FORMAT3, data[offset:], self)
        elif length >= HEADER_SIZE2:
            unpack2(HEADER_FORMAT2, data[offset:], self)
        elif length >= HEADER_SIZE1:
            unpack2(HEADER_FORMAT1, data[offset:], self)

        self.fonttype = VANILLA
        scheme = self.codingscheme.upper()
        if scheme.startswith("TEX MATH SY"):
            self.fonttype = MATHSY
        elif scheme.startswith("TEX MATH EX"):
            self.fonttype = MATHEX

        self.fontdimens = {}
        for i in range(sizes.np):
            name = f"PARAMETER{i+1}"
            if i <= 6:
                name = BASE_PARAMS[i]
            elif self.fonttype == MATHSY and i <= 21:
                name = MATHSY_PARAMS[i - 7]
            elif self.fonttype == MATHEX and i <= 12:
                name = MATHEX_PARAMS[i - 7]
            read_fixed(param(i), name, self.fontdimens)

        lig_kern_map = {}
        self.right_boundary_char = None
        self.left_boundary_char = None
        if sizes.nl > 0:
            cmd = lig_kern_command(lig_step(0))
            if cmd.skip_byte == 255:
                self.right_boundary_char = cmd.next_char

            cmd = lig_kern_command(lig_step((sizes.nl - 1)))
            if cmd.skip_byte == 255:
                self.left_boundary_char = 256
                r = 256 * cmd.op_byte + cmd.remainder
                lig_kern_map[self.left_boundary_char] = r

        self.chars = {}
        for c in range(sizes.bc, sizes.ec + 1):
            if width_index(c) > 0:
                self.chars[c] = info = {}
                info["width"] = width(c)
                if height_index(c) > 0:
                    info["height"] = height(c)
                if depth_index(c) > 0:
                    info["depth"] = depth(c)
                if italic_index(c) > 0:
                    info["italic"] = italic(c)
                char_tag = tag(c)
                if char_tag == NO_TAG:
                    pass
                elif char_tag == LIG_TAG:
                    lig_kern_map[c] = remainder(c)
                elif char_tag == LIST_TAG:
                    info["nextlarger"] = remainder(c)
                elif char_tag == EXT_TAG:
                    info["varchar"] = varchar = {}
                    for i in range(4):
                        part = data[exten(c) + i]
                        if i == 3 or part > 0:
                            name = "rep"
                            if i == 0:
                                name = "top"
                            elif i == 1:
                                name = "mid"
                            elif i == 2:
                                name = "bot"
                            if noneexistent(part):
                                varchar[name] = c
                            else:
                                varchar[name] = part

        self.ligatures = {}
        self.kerning = {}
        for c, i in sorted(lig_kern_map.items()):
            cmd = lig_kern_command(lig_step(i))
            if cmd.skip_byte > STOP_FLAG:
                i = 256 * cmd.op_byte + cmd.remainder

            while i < sizes.nl:
                cmd = lig_kern_command(lig_step(i))
                if cmd.skip_byte > STOP_FLAG:
                    pass
                else:
                    if cmd.op_byte >= KERN_FLAG:
                        r = 256 * (cmd.op_byte - KERN_FLAG) + cmd.remainder
                        self.kerning.setdefault(c, {})[cmd.next_char] = kern(r)
                    else:
                        r = cmd.op_byte
                        if r == 4 or (r > 7 and r != 11):
                            # Ligature step with nonstandard code, we output
                            # the code verbatim.
                            lig = r
                        else:
                            lig = ""
                            if r % 4 > 1:
                                lig += "/"
                            lig += "LIG"
                            if r % 2 != 0:
                                lig += "/"
                            while r > 3:
                                lig += ">"
                                r -= 4
                        self.ligatures.setdefault(c, {})[cmd.next_char] = (
                            lig,
                            cmd.remainder,
                        )

                if cmd.skip_byte >= STOP_FLAG:
                    break
                i += cmd.skip_byte + 1


if __name__ == "__main__":
    import sys

    tfm = TFM(sys.argv[1])
    print(
        "\n".join(
            x
            for x in [
                f"tfm.checksum={tfm.checksum}",
                f"tfm.designsize={tfm.designsize}",
                f"tfm.codingscheme={tfm.codingscheme}",
                f"tfm.fonttype={tfm.fonttype}",
                f"tfm.family={tfm.family}",
                f"tfm.seven_bit_safe_flag={tfm.seven_bit_safe_flag}",
                f"tfm.face={tfm.face}",
                f"tfm.extraheader={tfm.extraheader}",
                f"tfm.fontdimens={tfm.fontdimens}",
                f"tfm.right_boundary_char={tfm.right_boundary_char}",
                f"tfm.left_boundary_char={tfm.left_boundary_char}",
                f"tfm.kerning={tfm.kerning}",
                f"tfm.ligatures={tfm.ligatures}",
                f"tfm.chars={tfm.chars}",
            ]
        )
    )
    print(tfm)
