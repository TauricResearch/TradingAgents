import itertools
import io
from pathlib import Path

import numpy as np
import pytest

import matplotlib as mpl
from matplotlib import ft2font
from matplotlib.testing.decorators import check_figures_equal
import matplotlib.font_manager as fm
import matplotlib.path as mpath
import matplotlib.pyplot as plt


def test_ft2image_draw_rect_filled():
    width = 23
    height = 42
    for x0, y0, x1, y1 in itertools.product([1, 100], [2, 200], [4, 400], [8, 800]):
        im = ft2font.FT2Image(width, height)
        im.draw_rect_filled(x0, y0, x1, y1)
        a = np.asarray(im)
        assert a.dtype == np.uint8
        assert a.shape == (height, width)
        if x0 == 100 or y0 == 200:
            # All the out-of-bounds starts should get automatically clipped.
            assert np.sum(a) == 0
        else:
            # Otherwise, ends are clipped to the dimension, but are also _inclusive_.
            filled = (min(x1 + 1, width) - x0) * (min(y1 + 1, height) - y0)
            assert np.sum(a) == 255 * filled


def test_ft2font_dejavu_attrs():
    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file)
    assert font.fname == file
    # Names extracted from FontForge: Font Information → PS Names tab.
    assert font.postscript_name == 'DejaVuSans'
    assert font.family_name == 'DejaVu Sans'
    assert font.style_name == 'Book'
    assert font.num_faces == 1  # Single TTF.
    assert font.num_named_instances == 0  # Not a variable font.
    assert font.num_glyphs == 6241  # From compact encoding view in FontForge.
    assert font.num_fixed_sizes == 0  # All glyphs are scalable.
    assert font.num_charmaps == 5
    # Other internal flags are set, so only check the ones we're allowed to test.
    expected_flags = (ft2font.FaceFlags.SCALABLE | ft2font.FaceFlags.SFNT |
                      ft2font.FaceFlags.HORIZONTAL | ft2font.FaceFlags.KERNING |
                      ft2font.FaceFlags.GLYPH_NAMES)
    assert expected_flags in font.face_flags
    assert font.style_flags == ft2font.StyleFlags.NORMAL
    assert font.scalable
    # From FontForge: Font Information → General tab → entry name below.
    assert font.units_per_EM == 2048  # Em Size.
    assert font.underline_position == -175  # Underline position.
    assert font.underline_thickness == 90  # Underline height.
    # From FontForge: Font Information → OS/2 tab → Metrics tab → entry name below.
    assert font.ascender == 1901  # HHead Ascent.
    assert font.descender == -483  # HHead Descent.
    # Unconfirmed values.
    assert font.height == 2384
    assert font.max_advance_width == 3838
    assert font.max_advance_height == 2384
    assert font.bbox == (-2090, -948, 3673, 2524)


def test_ft2font_cm_attrs():
    file = fm.findfont('cmtt10')
    font = ft2font.FT2Font(file)
    assert font.fname == file
    # Names extracted from FontForge: Font Information → PS Names tab.
    assert font.postscript_name == 'Cmtt10'
    assert font.family_name == 'cmtt10'
    assert font.style_name == 'Regular'
    assert font.num_faces == 1  # Single TTF.
    assert font.num_named_instances == 0  # Not a variable font.
    assert font.num_glyphs == 133  # From compact encoding view in FontForge.
    assert font.num_fixed_sizes == 0  # All glyphs are scalable.
    assert font.num_charmaps == 2
    # Other internal flags are set, so only check the ones we're allowed to test.
    expected_flags = (ft2font.FaceFlags.SCALABLE | ft2font.FaceFlags.SFNT |
                      ft2font.FaceFlags.HORIZONTAL | ft2font.FaceFlags.GLYPH_NAMES)
    assert expected_flags in font.face_flags
    assert font.style_flags == ft2font.StyleFlags.NORMAL
    assert font.scalable
    # From FontForge: Font Information → General tab → entry name below.
    assert font.units_per_EM == 2048  # Em Size.
    assert font.underline_position == -143  # Underline position.
    assert font.underline_thickness == 20  # Underline height.
    # From FontForge: Font Information → OS/2 tab → Metrics tab → entry name below.
    assert font.ascender == 1276  # HHead Ascent.
    assert font.descender == -489  # HHead Descent.
    # Unconfirmed values.
    assert font.height == 1765
    assert font.max_advance_width == 1536
    assert font.max_advance_height == 1765
    assert font.bbox == (-12, -477, 1280, 1430)


def test_ft2font_stix_bold_attrs():
    file = fm.findfont('STIXSizeTwoSym:bold')
    font = ft2font.FT2Font(file)
    assert font.fname == file
    # Names extracted from FontForge: Font Information → PS Names tab.
    assert font.postscript_name == 'STIXSizeTwoSym-Bold'
    assert font.family_name == 'STIXSizeTwoSym'
    assert font.style_name == 'Bold'
    assert font.num_faces == 1  # Single TTF.
    assert font.num_named_instances == 0  # Not a variable font.
    assert font.num_glyphs == 20  # From compact encoding view in FontForge.
    assert font.num_fixed_sizes == 0  # All glyphs are scalable.
    assert font.num_charmaps == 3
    # Other internal flags are set, so only check the ones we're allowed to test.
    expected_flags = (ft2font.FaceFlags.SCALABLE | ft2font.FaceFlags.SFNT |
                      ft2font.FaceFlags.HORIZONTAL | ft2font.FaceFlags.GLYPH_NAMES)
    assert expected_flags in font.face_flags
    assert font.style_flags == ft2font.StyleFlags.BOLD
    assert font.scalable
    # From FontForge: Font Information → General tab → entry name below.
    assert font.units_per_EM == 1000  # Em Size.
    assert font.underline_position == -133  # Underline position.
    assert font.underline_thickness == 20  # Underline height.
    # From FontForge: Font Information → OS/2 tab → Metrics tab → entry name below.
    assert font.ascender == 2095  # HHead Ascent.
    assert font.descender == -404  # HHead Descent.
    # Unconfirmed values.
    assert font.height == 2499
    assert font.max_advance_width == 1130
    assert font.max_advance_height == 2499
    assert font.bbox == (4, -355, 1185, 2095)


def test_ft2font_invalid_args(tmp_path):
    # filename argument.
    with pytest.raises(TypeError, match='to a font file or a binary-mode file object'):
        ft2font.FT2Font(None)
    with pytest.raises(TypeError, match='to a font file or a binary-mode file object'):
        ft2font.FT2Font(object())  # Not bytes or string, and has no read() method.
    file = tmp_path / 'invalid-font.ttf'
    file.write_text('This is not a valid font file.')
    with (pytest.raises(TypeError, match='to a font file or a binary-mode file object'),
          file.open('rt') as fd):
        ft2font.FT2Font(fd)
    with (pytest.raises(TypeError, match='to a font file or a binary-mode file object'),
          file.open('wt') as fd):
        ft2font.FT2Font(fd)
    with (pytest.raises(TypeError, match='to a font file or a binary-mode file object'),
          file.open('wb') as fd):
        ft2font.FT2Font(fd)

    file = fm.findfont('DejaVu Sans')

    # hinting_factor argument.
    with pytest.raises(TypeError, match='incompatible constructor arguments'):
        ft2font.FT2Font(file, 1.3)
    with pytest.raises(ValueError, match='hinting_factor must be greater than 0'):
        ft2font.FT2Font(file, 0)

    with pytest.raises(TypeError, match='incompatible constructor arguments'):
        # failing to be a list will fail before the 0
        ft2font.FT2Font(file, _fallback_list=(0,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match='incompatible constructor arguments'):
        ft2font.FT2Font(file, _fallback_list=[0])  # type: ignore[list-item]

    # kerning_factor argument.
    with pytest.raises(TypeError, match='incompatible constructor arguments'):
        ft2font.FT2Font(file, _kerning_factor=1.3)


def test_ft2font_clear():
    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file)
    assert font.get_num_glyphs() == 0
    assert font.get_width_height() == (0, 0)
    assert font.get_bitmap_offset() == (0, 0)
    font.set_text('ABabCDcd')
    assert font.get_num_glyphs() == 8
    assert font.get_width_height() != (0, 0)
    assert font.get_bitmap_offset() != (0, 0)
    font.clear()
    assert font.get_num_glyphs() == 0
    assert font.get_width_height() == (0, 0)
    assert font.get_bitmap_offset() == (0, 0)


def test_ft2font_set_size():
    file = fm.findfont('DejaVu Sans')
    # Default is 12pt @ 72 dpi.
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=1)
    font.set_text('ABabCDcd')
    orig = font.get_width_height()
    font.set_size(24, 72)
    font.set_text('ABabCDcd')
    assert font.get_width_height() == tuple(pytest.approx(2 * x, 1e-1) for x in orig)
    font.set_size(12, 144)
    font.set_text('ABabCDcd')
    assert font.get_width_height() == tuple(pytest.approx(2 * x, 1e-1) for x in orig)


def test_ft2font_charmaps():
    def enc(name):
        # We don't expose the encoding enum from FreeType, but can generate it here.
        # For DejaVu, there are 5 charmaps, but only 2 have enum entries in FreeType.
        e = 0
        for x in name:
            e <<= 8
            e += ord(x)
        return e

    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file)
    assert font.num_charmaps == 5

    # Unicode.
    font.select_charmap(enc('unic'))
    unic = font.get_charmap()
    font.set_charmap(0)  # Unicode platform, Unicode BMP only.
    after = font.get_charmap()
    assert len(after) <= len(unic)
    for chr, glyph in after.items():
        assert unic[chr] == glyph == font.get_char_index(chr)
    font.set_charmap(1)  # Unicode platform, modern subtable.
    after = font.get_charmap()
    assert unic == after
    font.set_charmap(3)  # Windows platform, Unicode BMP only.
    after = font.get_charmap()
    assert len(after) <= len(unic)
    for chr, glyph in after.items():
        assert unic[chr] == glyph == font.get_char_index(chr)
    font.set_charmap(4)  # Windows platform, Unicode full repertoire, modern subtable.
    after = font.get_charmap()
    assert unic == after

    # This is just a random sample from FontForge.
    glyph_names = {
        'non-existent-glyph-name': 0,
        'plusminus': 115,
        'Racute': 278,
        'perthousand': 2834,
        'seveneighths': 3057,
        'triagup': 3721,
        'uni01D3': 405,
        'uni0417': 939,
        'uni2A02': 4464,
        'u1D305': 5410,
        'u1F0A1': 5784,
    }
    for name, index in glyph_names.items():
        assert font.get_name_index(name) == index
        if name == 'non-existent-glyph-name':
            name = '.notdef'
        # This doesn't always apply, but it does for DejaVu Sans.
        assert font.get_glyph_name(index) == name

    # Apple Roman.
    font.select_charmap(enc('armn'))
    armn = font.get_charmap()
    font.set_charmap(2)  # Macintosh platform, Roman.
    after = font.get_charmap()
    assert armn == after
    assert len(armn) <= 256  # 8-bit encoding.
    # The first 128 characters of Apple Roman match ASCII, which also matches Unicode.
    for o in range(1, 128):
        if o not in armn or o not in unic:
            continue
        assert unic[o] == armn[o]
    # Check a couple things outside the ASCII set that are different in each charset.
    examples = [
        # (Unicode, Macintosh)
        (0x2020, 0xA0),  # Dagger.
        (0x00B0, 0xA1),  # Degree symbol.
        (0x00A3, 0xA3),  # Pound sign.
        (0x00A7, 0xA4),  # Section sign.
        (0x00B6, 0xA6),  # Pilcrow.
        (0x221E, 0xB0),  # Infinity symbol.
    ]
    for u, m in examples:
        # Though the encoding is different, the glyph should be the same.
        assert unic[u] == armn[m]


_expected_sfnt_names = {
    'DejaVu Sans': {
        0: 'Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved.\n'
           'Copyright (c) 2006 by Tavmjong Bah. All Rights Reserved.\n'
           'DejaVu changes are in public domain\n',
        1: 'DejaVu Sans',
        2: 'Book',
        3: 'DejaVu Sans',
        4: 'DejaVu Sans',
        5: 'Version 2.35',
        6: 'DejaVuSans',
        8: 'DejaVu fonts team',
        11: 'http://dejavu.sourceforge.net',
        13: 'Fonts are (c) Bitstream (see below). '
            'DejaVu changes are in public domain. '
            '''Glyphs imported from Arev fonts are (c) Tavmjung Bah (see below)

Bitstream Vera Fonts Copyright
------------------------------

Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved. Bitstream Vera is
a trademark of Bitstream, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of the fonts accompanying this license ("Fonts") and associated
documentation files (the "Font Software"), to reproduce and distribute the
Font Software, including without limitation the rights to use, copy, merge,
publish, distribute, and/or sell copies of the Font Software, and to permit
persons to whom the Font Software is furnished to do so, subject to the
following conditions:

The above copyright and trademark notices and this permission notice shall
be included in all copies of one or more of the Font Software typefaces.

The Font Software may be modified, altered, or added to, and in particular
the designs of glyphs or characters in the Fonts may be modified and
additional glyphs or characters may be added to the Fonts, only if the fonts
are renamed to names not containing either the words "Bitstream" or the word
"Vera".

This License becomes null and void to the extent applicable to Fonts or Font
Software that has been modified and is distributed under the "Bitstream
Vera" names.

The Font Software may be sold as part of a larger software package but no
copy of one or more of the Font Software typefaces may be sold by itself.

THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF COPYRIGHT, PATENT,
TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL BITSTREAM OR THE GNOME
FOUNDATION BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, INCLUDING
ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF
THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM OTHER DEALINGS IN THE
FONT SOFTWARE.

Except as contained in this notice, the names of Gnome, the Gnome
Foundation, and Bitstream Inc., shall not be used in advertising or
otherwise to promote the sale, use or other dealings in this Font Software
without prior written authorization from the Gnome Foundation or Bitstream
Inc., respectively. For further information, contact: fonts at gnome dot
org. ''' '''

Arev Fonts Copyright
------------------------------

Copyright (c) 2006 by Tavmjong Bah. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining
a copy of the fonts accompanying this license ("Fonts") and
associated documentation files (the "Font Software"), to reproduce
and distribute the modifications to the Bitstream Vera Font Software,
including without limitation the rights to use, copy, merge, publish,
distribute, and/or sell copies of the Font Software, and to permit
persons to whom the Font Software is furnished to do so, subject to
the following conditions:

The above copyright and trademark notices and this permission notice
shall be included in all copies of one or more of the Font Software
typefaces.

The Font Software may be modified, altered, or added to, and in
particular the designs of glyphs or characters in the Fonts may be
modified and additional glyphs or characters may be added to the
Fonts, only if the fonts are renamed to names not containing either
the words "Tavmjong Bah" or the word "Arev".

This License becomes null and void to the extent applicable to Fonts
or Font Software that has been modified and is distributed under the ''' '''
"Tavmjong Bah Arev" names.

The Font Software may be sold as part of a larger software package but
no copy of one or more of the Font Software typefaces may be sold by
itself.

THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL
TAVMJONG BAH BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.

Except as contained in this notice, the name of Tavmjong Bah shall not
be used in advertising or otherwise to promote the sale, use or other
dealings in this Font Software without prior written authorization
from Tavmjong Bah. For further information, contact: tavmjong @ free
. fr.''',
        14: 'http://dejavu.sourceforge.net/wiki/index.php/License',
        16: 'DejaVu Sans',
        17: 'Book',
    },
    'cmtt10': {
        0: 'Copyright (C) 1994, Basil K. Malyshev. All Rights Reserved.'
           '012BaKoMa Fonts Collection, Level-B.',
        1: 'cmtt10',
        2: 'Regular',
        3: 'FontMonger:cmtt10',
        4: 'cmtt10',
        5: '1.1/12-Nov-94',
        6: 'Cmtt10',
    },
    'STIXSizeTwoSym:bold': {
        0: 'Copyright (c) 2001-2010 by the STI Pub Companies, consisting of the '
           'American Chemical Society, the American Institute of Physics, the American '
           'Mathematical Society, the American Physical Society, Elsevier, Inc., and '
           'The Institute of Electrical and Electronic Engineers, Inc. Portions '
           'copyright (c) 1998-2003 by MicroPress, Inc. Portions copyright (c) 1990 by '
           'Elsevier, Inc. All rights reserved.',
        1: 'STIXSizeTwoSym',
        2: 'Bold',
        3: 'FontMaster:STIXSizeTwoSym-Bold:1.0.0',
        4: 'STIXSizeTwoSym-Bold',
        5: 'Version 1.0.0',
        6: 'STIXSizeTwoSym-Bold',
        7: 'STIX Fonts(TM) is a trademark of The Institute of Electrical and '
           'Electronics Engineers, Inc.',
        9: 'MicroPress Inc., with final additions and corrections provided by Coen '
           'Hoffman, Elsevier (retired)',
        10: 'Arie de Ruiter, who in 1995 was Head of Information Technology '
            'Development at Elsevier Science, made a proposal to the STI Pub group, an '
            'informal group of publishers consisting of representatives from the '
            'American Chemical Society (ACS), American Institute of Physics (AIP), '
            'American Mathematical Society (AMS), American Physical Society (APS), '
            'Elsevier, and Institute of Electrical and Electronics Engineers (IEEE). '
            'De Ruiter encouraged the members to consider development of a series of '
            'Web fonts, which he proposed should be called the Scientific and '
            'Technical Information eXchange, or STIX, Fonts. All STI Pub member '
            'organizations enthusiastically endorsed this proposal, and the STI Pub '
            'group agreed to embark on what has become a twelve-year project. The goal '
            'of the project was to identify all alphabetic, symbolic, and other '
            'special characters used in any facet of scientific publishing and to '
            'create a set of Unicode-based fonts that would be distributed free to '
            'every scientist, student, and other interested party worldwide. The fonts '
            'would be consistent with the emerging Unicode standard, and would permit '
            'universal representation of every character. With the release of the STIX '
            "fonts, de Ruiter's vision has been realized.",
        11: 'http://www.stixfonts.org',
        12: 'http://www.micropress-inc.com',
        13: 'As a condition for receiving these fonts at no charge, each person '
            'downloading the fonts must agree to some simple license terms. The '
            'license is based on the SIL Open Font License '
            '<http://scripts.sil.org/cms/scripts/page.php?site_id=nrsi&id=OFL>. The '
            'SIL License is a free and open source license specifically designed for '
            'fonts and related software. The basic terms are that the recipient will '
            'not remove the copyright and trademark statements from the fonts and '
            'that, if the person decides to create a derivative work based on the STIX '
            'Fonts but incorporating some changes or enhancements, the derivative work '
            '("Modified Version") will carry a different name. The copyright and '
            'trademark restrictions are part of the agreement between the STI Pub '
            'companies and the typeface designer. The "renaming" restriction results '
            'from the desire of the STI Pub companies to assure that the STIX Fonts '
            'will continue to function in a predictable fashion for all that use them. '
            'No copy of one or more of the individual Font typefaces that form the '
            'STIX Fonts(TM) set may be sold by itself, but other than this one '
            'restriction, licensees are free to sell the fonts either separately or as '
            'part of a package that combines other software or fonts with this font '
            'set.',
        14: 'http://www.stixfonts.org/user_license.html',
    },
}


@pytest.mark.parametrize('font_name, expected', _expected_sfnt_names.items(),
                         ids=_expected_sfnt_names.keys())
def test_ft2font_get_sfnt(font_name, expected):
    file = fm.findfont(font_name)
    font = ft2font.FT2Font(file)
    sfnt = font.get_sfnt()
    for name, value in expected.items():
        # Macintosh, Unicode 1.0, English, name.
        assert sfnt.pop((1, 0, 0, name)) == value.encode('ascii')
        # Microsoft, Unicode, English United States, name.
        assert sfnt.pop((3, 1, 1033, name)) == value.encode('utf-16be')
    assert sfnt == {}


_expected_sfnt_tables = {
    'DejaVu Sans': {
        'invalid': None,
        'head': {
            'version': (1, 0),
            'fontRevision': (2, 22937),
            'checkSumAdjustment': -175678572,
            'magicNumber': 0x5F0F3CF5,
            'flags': 31,
            'unitsPerEm': 2048,
            'created': (0, 3514699492), 'modified': (0, 3514699492),
            'xMin': -2090, 'yMin': -948, 'xMax': 3673, 'yMax': 2524,
            'macStyle': 0,
            'lowestRecPPEM': 8,
            'fontDirectionHint': 0,
            'indexToLocFormat': 1,
            'glyphDataFormat': 0,
        },
        'maxp': {
            'version': (1, 0),
            'numGlyphs': 6241,
            'maxPoints': 852, 'maxComponentPoints': 104, 'maxTwilightPoints': 16,
            'maxContours': 43, 'maxComponentContours': 12,
            'maxZones': 2,
            'maxStorage': 153,
            'maxFunctionDefs': 64,
            'maxInstructionDefs': 0,
            'maxStackElements': 1045,
            'maxSizeOfInstructions': 534,
            'maxComponentElements': 8,
            'maxComponentDepth': 4,
        },
        'OS/2': {
            'version': 1,
            'xAvgCharWidth': 1038,
            'usWeightClass': 400, 'usWidthClass': 5,
            'fsType': 0,
            'ySubscriptXSize': 1331, 'ySubscriptYSize': 1433,
            'ySubscriptXOffset': 0, 'ySubscriptYOffset': 286,
            'ySuperscriptXSize': 1331, 'ySuperscriptYSize': 1433,
            'ySuperscriptXOffset': 0, 'ySuperscriptYOffset': 983,
            'yStrikeoutSize': 102, 'yStrikeoutPosition': 530,
            'sFamilyClass': 0,
            'panose': b'\x02\x0b\x06\x03\x03\x08\x04\x02\x02\x04',
            'ulCharRange': (3875565311, 3523280383, 170156073, 67117068),
            'achVendID': b'PfEd',
            'fsSelection': 64, 'fsFirstCharIndex': 32, 'fsLastCharIndex': 65535,
        },
        'hhea': {
            'version': (1, 0),
            'ascent': 1901, 'descent': -483, 'lineGap': 0,
            'advanceWidthMax': 3838,
            'minLeftBearing': -2090, 'minRightBearing': -1455,
            'xMaxExtent': 3673,
            'caretSlopeRise': 1, 'caretSlopeRun': 0, 'caretOffset': 0,
            'metricDataFormat': 0, 'numOfLongHorMetrics': 6226,
        },
        'vhea': None,
        'post': {
            'format': (2, 0),
            'isFixedPitch': 0, 'italicAngle': (0, 0),
            'underlinePosition': -130, 'underlineThickness': 90,
            'minMemType42': 0, 'maxMemType42': 0,
            'minMemType1': 0, 'maxMemType1': 0,
        },
        'pclt': None,
    },
    'cmtt10': {
        'invalid': None,
        'head': {
            'version': (1, 0),
            'fontRevision': (1, 0),
            'checkSumAdjustment': 555110277,
            'magicNumber': 0x5F0F3CF5,
            'flags': 3,
            'unitsPerEm': 2048,
            'created': (0, 0), 'modified': (0, 0),
            'xMin': -12, 'yMin': -477, 'xMax': 1280, 'yMax': 1430,
            'macStyle': 0,
            'lowestRecPPEM': 6,
            'fontDirectionHint': 2,
            'indexToLocFormat': 1,
            'glyphDataFormat': 0,
        },
        'maxp': {
            'version': (1, 0),
            'numGlyphs': 133,
            'maxPoints': 94, 'maxComponentPoints': 0, 'maxTwilightPoints': 12,
            'maxContours': 5, 'maxComponentContours': 0,
            'maxZones': 2,
            'maxStorage': 6,
            'maxFunctionDefs': 64,
            'maxInstructionDefs': 0,
            'maxStackElements': 200,
            'maxSizeOfInstructions': 100,
            'maxComponentElements': 4,
            'maxComponentDepth': 1,
        },
        'OS/2': {
            'version': 0,
            'xAvgCharWidth': 1075,
            'usWeightClass': 400, 'usWidthClass': 5,
            'fsType': 0,
            'ySubscriptXSize': 410, 'ySubscriptYSize': 369,
            'ySubscriptXOffset': 0, 'ySubscriptYOffset': -469,
            'ySuperscriptXSize': 410, 'ySuperscriptYSize': 369,
            'ySuperscriptXOffset': 0, 'ySuperscriptYOffset': 1090,
            'yStrikeoutSize': 102, 'yStrikeoutPosition': 530,
            'sFamilyClass': 0,
            'panose': b'\x02\x0b\x05\x00\x00\x00\x00\x00\x00\x00',
            'ulCharRange': (0, 0, 0, 0),
            'achVendID': b'\x00\x00\x00\x00',
            'fsSelection': 64, 'fsFirstCharIndex': 32, 'fsLastCharIndex': 9835,
        },
        'hhea': {
            'version': (1, 0),
            'ascent': 1276, 'descent': -489, 'lineGap': 0,
            'advanceWidthMax': 1536,
            'minLeftBearing': -12, 'minRightBearing': -29,
            'xMaxExtent': 1280,
            'caretSlopeRise': 1, 'caretSlopeRun': 0, 'caretOffset': 0,
            'metricDataFormat': 0, 'numOfLongHorMetrics': 133,
        },
        'vhea': None,
        'post': {
            'format': (2, 0),
            'isFixedPitch': 0, 'italicAngle': (0, 0),
            'underlinePosition': -133, 'underlineThickness': 20,
            'minMemType42': 0, 'maxMemType42': 0,
            'minMemType1': 0, 'maxMemType1': 0,
        },
        'pclt': {
            'version': (1, 0),
            'fontNumber': 2147483648,
            'pitch': 1075,
            'xHeight': 905,
            'style': 0,
            'typeFamily': 0,
            'capHeight': 1276,
            'symbolSet': 0,
            'typeFace': b'cmtt10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
            'characterComplement': b'\xff\xff\xff\xff7\xff\xff\xfe',
            'strokeWeight': 0,
            'widthType': -5,
            'serifStyle': 64,
        },
    },
    'STIXSizeTwoSym:bold': {
        'invalid': None,
        'head': {
            'version': (1, 0),
            'fontRevision': (1, 0),
            'checkSumAdjustment': 1803408080,
            'magicNumber': 0x5F0F3CF5,
            'flags': 11,
            'unitsPerEm': 1000,
            'created': (0, 3359035786), 'modified': (0, 3359035786),
            'xMin': 4, 'yMin': -355, 'xMax': 1185, 'yMax': 2095,
            'macStyle': 1,
            'lowestRecPPEM': 8,
            'fontDirectionHint': 2,
            'indexToLocFormat': 0,
            'glyphDataFormat': 0,
        },
        'maxp': {
            'version': (1, 0),
            'numGlyphs': 20,
            'maxPoints': 37, 'maxComponentPoints': 0, 'maxTwilightPoints': 0,
            'maxContours': 1, 'maxComponentContours': 0,
            'maxZones': 2,
            'maxStorage': 1,
            'maxFunctionDefs': 64,
            'maxInstructionDefs': 0,
            'maxStackElements': 64,
            'maxSizeOfInstructions': 0,
            'maxComponentElements': 0,
            'maxComponentDepth': 0,
        },
        'OS/2': {
            'version': 2,
            'xAvgCharWidth': 598,
            'usWeightClass': 700, 'usWidthClass': 5,
            'fsType': 0,
            'ySubscriptXSize': 500, 'ySubscriptYSize': 500,
            'ySubscriptXOffset': 0, 'ySubscriptYOffset': 250,
            'ySuperscriptXSize': 500, 'ySuperscriptYSize': 500,
            'ySuperscriptXOffset': 0, 'ySuperscriptYOffset': 500,
            'yStrikeoutSize': 20, 'yStrikeoutPosition': 1037,
            'sFamilyClass': 0,
            'panose': b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
            'ulCharRange': (3, 192, 0, 0),
            'achVendID': b'STIX',
            'fsSelection': 32, 'fsFirstCharIndex': 32, 'fsLastCharIndex': 10217,
        },
        'hhea': {
            'version': (1, 0),
            'ascent': 2095, 'descent': -404, 'lineGap': 0,
            'advanceWidthMax': 1130,
            'minLeftBearing': 0, 'minRightBearing': -55,
            'xMaxExtent': 1185,
            'caretSlopeRise': 1, 'caretSlopeRun': 0, 'caretOffset': 0,
            'metricDataFormat': 0, 'numOfLongHorMetrics': 19,
        },
        'vhea': None,
        'post': {
            'format': (2, 0),
            'isFixedPitch': 0, 'italicAngle': (0, 0),
            'underlinePosition': -123, 'underlineThickness': 20,
            'minMemType42': 0, 'maxMemType42': 0,
            'minMemType1': 0, 'maxMemType1': 0,
        },
        'pclt': None,
    },
}


@pytest.mark.parametrize('font_name', _expected_sfnt_tables.keys())
@pytest.mark.parametrize('header', _expected_sfnt_tables['DejaVu Sans'].keys())
def test_ft2font_get_sfnt_table(font_name, header):
    file = fm.findfont(font_name)
    font = ft2font.FT2Font(file)
    assert font.get_sfnt_table(header) == _expected_sfnt_tables[font_name][header]


@pytest.mark.parametrize('left, right, unscaled, unfitted, default', [
    # These are all the same class.
    ('A', 'A', 57, 248, 256), ('A', 'À', 57, 248, 256), ('A', 'Á', 57, 248, 256),
    ('A', 'Â', 57, 248, 256), ('A', 'Ã', 57, 248, 256), ('A', 'Ä', 57, 248, 256),
    # And a few other random ones.
    ('D', 'A', -36, -156, -128), ('T', '.', -243, -1056, -1024),
    ('X', 'C', -149, -647, -640), ('-', 'J', 114, 495, 512),
])
def test_ft2font_get_kerning(left, right, unscaled, unfitted, default):
    file = fm.findfont('DejaVu Sans')
    # With unscaled, these settings should produce exact values found in FontForge.
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=0)
    font.set_size(100, 100)
    assert font.get_kerning(font.get_char_index(ord(left)),
                            font.get_char_index(ord(right)),
                            ft2font.Kerning.UNSCALED) == unscaled
    assert font.get_kerning(font.get_char_index(ord(left)),
                            font.get_char_index(ord(right)),
                            ft2font.Kerning.UNFITTED) == unfitted
    assert font.get_kerning(font.get_char_index(ord(left)),
                            font.get_char_index(ord(right)),
                            ft2font.Kerning.DEFAULT) == default
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Use Kerning.UNSCALED instead'):
        k = ft2font.KERNING_UNSCALED
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Use Kerning enum values instead'):
        assert font.get_kerning(font.get_char_index(ord(left)),
                                font.get_char_index(ord(right)),
                                int(k)) == unscaled
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Use Kerning.UNFITTED instead'):
        k = ft2font.KERNING_UNFITTED
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Use Kerning enum values instead'):
        assert font.get_kerning(font.get_char_index(ord(left)),
                                font.get_char_index(ord(right)),
                                int(k)) == unfitted
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Use Kerning.DEFAULT instead'):
        k = ft2font.KERNING_DEFAULT
    with pytest.warns(mpl.MatplotlibDeprecationWarning,
                      match='Use Kerning enum values instead'):
        assert font.get_kerning(font.get_char_index(ord(left)),
                                font.get_char_index(ord(right)),
                                int(k)) == default


def test_ft2font_set_text():
    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=0)
    xys = font.set_text('')
    np.testing.assert_array_equal(xys, np.empty((0, 2)))
    assert font.get_width_height() == (0, 0)
    assert font.get_num_glyphs() == 0
    assert font.get_descent() == 0
    assert font.get_bitmap_offset() == (0, 0)
    # This string uses all the kerning pairs defined for test_ft2font_get_kerning.
    xys = font.set_text('AADAT.XC-J')
    np.testing.assert_array_equal(
        xys,
        [(0, 0), (512, 0), (1024, 0), (1600, 0), (2112, 0), (2496, 0), (2688, 0),
         (3200, 0), (3712, 0), (4032, 0)])
    assert font.get_width_height() == (4288, 768)
    assert font.get_num_glyphs() == 10
    assert font.get_descent() == 192
    assert font.get_bitmap_offset() == (6, 0)


def test_ft2font_loading():
    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=0)
    for glyph in [font.load_char(ord('M')),
                  font.load_glyph(font.get_char_index(ord('M')))]:
        assert glyph is not None
        assert glyph.width == 576
        assert glyph.height == 576
        assert glyph.horiBearingX == 0
        assert glyph.horiBearingY == 576
        assert glyph.horiAdvance == 640
        assert glyph.linearHoriAdvance == 678528
        assert glyph.vertBearingX == -384
        assert glyph.vertBearingY == 64
        assert glyph.vertAdvance == 832
        assert glyph.bbox == (54, 0, 574, 576)
    assert font.get_num_glyphs() == 2  # Both count as loaded.
    # But neither has been placed anywhere.
    assert font.get_width_height() == (0, 0)
    assert font.get_descent() == 0
    assert font.get_bitmap_offset() == (0, 0)


def test_ft2font_drawing():
    expected_str = (
        '          ',
        '11    11  ',
        '11    11  ',
        '1 1  1 1  ',
        '1 1  1 1  ',
        '1 1  1 1  ',
        '1  11  1  ',
        '1  11  1  ',
        '1      1  ',
        '1      1  ',
        '          ',
    )
    expected = np.array([
        [int(c) for c in line.replace(' ', '0')] for line in expected_str
    ])
    expected *= 255
    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=0)
    font.set_text('M')
    font.draw_glyphs_to_bitmap(antialiased=False)
    image = font.get_image()
    np.testing.assert_array_equal(image, expected)
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=0)
    glyph = font.load_char(ord('M'))
    image = ft2font.FT2Image(expected.shape[1], expected.shape[0])
    font.draw_glyph_to_bitmap(image, -1, 1, glyph, antialiased=False)
    np.testing.assert_array_equal(image, expected)


def test_ft2font_get_path():
    file = fm.findfont('DejaVu Sans')
    font = ft2font.FT2Font(file, hinting_factor=1, _kerning_factor=0)
    vertices, codes = font.get_path()
    assert vertices.shape == (0, 2)
    assert codes.shape == (0, )
    font.load_char(ord('M'))
    vertices, codes = font.get_path()
    expected_vertices = np.array([
        (0.843750, 9.000000), (2.609375, 9.000000),  # Top left.
        (4.906250, 2.875000),  # Top of midpoint.
        (7.218750, 9.000000), (8.968750, 9.000000),  # Top right.
        (8.968750, 0.000000), (7.843750, 0.000000),  # Bottom right.
        (7.843750, 7.906250),  # Point under top right.
        (5.531250, 1.734375), (4.296875, 1.734375),  # Bar under midpoint.
        (1.984375, 7.906250),  # Point under top left.
        (1.984375, 0.000000), (0.843750, 0.000000),  # Bottom left.
        (0.843750, 9.000000),  # Back to top left corner.
        (0.000000, 0.000000),
    ])
    np.testing.assert_array_equal(vertices, expected_vertices)
    expected_codes = np.full(expected_vertices.shape[0], mpath.Path.LINETO,
                             dtype=mpath.Path.code_type)
    expected_codes[0] = mpath.Path.MOVETO
    expected_codes[-1] = mpath.Path.CLOSEPOLY
    np.testing.assert_array_equal(codes, expected_codes)


@pytest.mark.parametrize('family_name, file_name',
                          [("WenQuanYi Zen Hei",  "wqy-zenhei.ttc"),
                           ("Noto Sans CJK JP", "NotoSansCJK.ttc"),
                           ("Noto Sans TC", "NotoSansTC-Regular.otf")]
                         )
def test_fallback_smoke(family_name, file_name):
    fp = fm.FontProperties(family=[family_name])
    if Path(fm.findfont(fp)).name != file_name:
        pytest.skip(f"Font {family_name} ({file_name}) is missing")
    plt.rcParams['font.size'] = 20
    fig = plt.figure(figsize=(4.75, 1.85))
    fig.text(0.05, 0.45, "There are 几个汉字 in between!",
             family=['DejaVu Sans', family_name])
    fig.text(0.05, 0.85, "There are 几个汉字 in between!",
             family=[family_name])

    # TODO enable fallback for other backends!
    for fmt in ['png', 'raw']:  # ["svg", "pdf", "ps"]:
        fig.savefig(io.BytesIO(), format=fmt)


@pytest.mark.parametrize('family_name, file_name',
                         [("WenQuanYi Zen Hei",  "wqy-zenhei"),
                          ("Noto Sans CJK JP", "NotoSansCJK"),
                          ("Noto Sans TC", "NotoSansTC-Regular.otf")]
                         )
@check_figures_equal(extensions=["png", "pdf", "eps", "svg"])
def test_font_fallback_chinese(fig_test, fig_ref, family_name, file_name):
    fp = fm.FontProperties(family=[family_name])
    if file_name not in Path(fm.findfont(fp)).name:
        pytest.skip(f"Font {family_name} ({file_name}) is missing")

    text = ["There are", "几个汉字", "in between!"]

    plt.rcParams["font.size"] = 20
    test_fonts = [["DejaVu Sans", family_name]] * 3
    ref_fonts = [["DejaVu Sans"], [family_name], ["DejaVu Sans"]]

    for j, (txt, test_font, ref_font) in enumerate(
            zip(text, test_fonts, ref_fonts)
    ):
        fig_ref.text(0.05, .85 - 0.15*j, txt, family=ref_font)
        fig_test.text(0.05, .85 - 0.15*j, txt, family=test_font)


@pytest.mark.parametrize("font_list",
                          [['DejaVu Serif', 'DejaVu Sans'],
                           ['DejaVu Sans Mono']],
                         ids=["two fonts", "one font"])
def test_fallback_missing(recwarn, font_list):
    fig = plt.figure()
    fig.text(.5, .5, "Hello 🙃 World!", family=font_list)
    fig.canvas.draw()
    assert all(isinstance(warn.message, UserWarning) for warn in recwarn)
    # not sure order is guaranteed on the font listing so
    assert recwarn[0].message.args[0].startswith(
           "Glyph 128579 (\\N{UPSIDE-DOWN FACE}) missing from font(s)")
    assert all([font in recwarn[0].message.args[0] for font in font_list])


@pytest.mark.parametrize(
    "family_name, file_name",
    [
        ("WenQuanYi Zen Hei", "wqy-zenhei"),
        ("Noto Sans CJK JP", "NotoSansCJK"),
        ("Noto Sans TC", "NotoSansTC-Regular.otf")
    ],
)
def test__get_fontmap(family_name, file_name):
    fp = fm.FontProperties(family=[family_name])
    found_file_name = Path(fm.findfont(fp)).name
    if file_name not in found_file_name:
        pytest.skip(f"Font {family_name} ({file_name}) is missing")

    text = "There are 几个汉字 in between!"
    ft = fm.get_font(
        fm.fontManager._find_fonts_by_props(
            fm.FontProperties(family=["DejaVu Sans", family_name])
        )
    )
    fontmap = ft._get_fontmap(text)
    for char, font in fontmap.items():
        if ord(char) > 127:
            assert Path(font.fname).name == found_file_name
        else:
            assert Path(font.fname).name == "DejaVuSans.ttf"
