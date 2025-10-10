# Copyright 2021 Behdad Esfahbod. All Rights Reserved.


def is_Default_Ignorable(u):
    # http://www.unicode.org/reports/tr44/#Default_Ignorable_Code_Point
    #
    # TODO Move me to unicodedata module and autogenerate.
    #
    # Unicode 14.0:
    # $ grep '; Default_Ignorable_Code_Point ' DerivedCoreProperties.txt | sed 's/;.*#/#/'
    # 00AD          # Cf       SOFT HYPHEN
    # 034F          # Mn       COMBINING GRAPHEME JOINER
    # 061C          # Cf       ARABIC LETTER MARK
    # 115F..1160    # Lo   [2] HANGUL CHOSEONG FILLER..HANGUL JUNGSEONG FILLER
    # 17B4..17B5    # Mn   [2] KHMER VOWEL INHERENT AQ..KHMER VOWEL INHERENT AA
    # 180B..180D    # Mn   [3] MONGOLIAN FREE VARIATION SELECTOR ONE..MONGOLIAN FREE VARIATION SELECTOR THREE
    # 180E          # Cf       MONGOLIAN VOWEL SEPARATOR
    # 180F          # Mn       MONGOLIAN FREE VARIATION SELECTOR FOUR
    # 200B..200F    # Cf   [5] ZERO WIDTH SPACE..RIGHT-TO-LEFT MARK
    # 202A..202E    # Cf   [5] LEFT-TO-RIGHT EMBEDDING..RIGHT-TO-LEFT OVERRIDE
    # 2060..2064    # Cf   [5] WORD JOINER..INVISIBLE PLUS
    # 2065          # Cn       <reserved-2065>
    # 2066..206F    # Cf  [10] LEFT-TO-RIGHT ISOLATE..NOMINAL DIGIT SHAPES
    # 3164          # Lo       HANGUL FILLER
    # FE00..FE0F    # Mn  [16] VARIATION SELECTOR-1..VARIATION SELECTOR-16
    # FEFF          # Cf       ZERO WIDTH NO-BREAK SPACE
    # FFA0          # Lo       HALFWIDTH HANGUL FILLER
    # FFF0..FFF8    # Cn   [9] <reserved-FFF0>..<reserved-FFF8>
    # 1BCA0..1BCA3  # Cf   [4] SHORTHAND FORMAT LETTER OVERLAP..SHORTHAND FORMAT UP STEP
    # 1D173..1D17A  # Cf   [8] MUSICAL SYMBOL BEGIN BEAM..MUSICAL SYMBOL END PHRASE
    # E0000         # Cn       <reserved-E0000>
    # E0001         # Cf       LANGUAGE TAG
    # E0002..E001F  # Cn  [30] <reserved-E0002>..<reserved-E001F>
    # E0020..E007F  # Cf  [96] TAG SPACE..CANCEL TAG
    # E0080..E00FF  # Cn [128] <reserved-E0080>..<reserved-E00FF>
    # E0100..E01EF  # Mn [240] VARIATION SELECTOR-17..VARIATION SELECTOR-256
    # E01F0..E0FFF  # Cn [3600] <reserved-E01F0>..<reserved-E0FFF>
    return (
        u == 0x00AD
        or u == 0x034F  # Cf       SOFT HYPHEN
        or u == 0x061C  # Mn       COMBINING GRAPHEME JOINER
        or 0x115F <= u <= 0x1160  # Cf       ARABIC LETTER MARK
        or 0x17B4  # Lo   [2] HANGUL CHOSEONG FILLER..HANGUL JUNGSEONG FILLER
        <= u
        <= 0x17B5
        or 0x180B  # Mn   [2] KHMER VOWEL INHERENT AQ..KHMER VOWEL INHERENT AA
        <= u
        <= 0x180D
        or u  # Mn   [3] MONGOLIAN FREE VARIATION SELECTOR ONE..MONGOLIAN FREE VARIATION SELECTOR THREE
        == 0x180E
        or u == 0x180F  # Cf       MONGOLIAN VOWEL SEPARATOR
        or 0x200B <= u <= 0x200F  # Mn       MONGOLIAN FREE VARIATION SELECTOR FOUR
        or 0x202A <= u <= 0x202E  # Cf   [5] ZERO WIDTH SPACE..RIGHT-TO-LEFT MARK
        or 0x2060  # Cf   [5] LEFT-TO-RIGHT EMBEDDING..RIGHT-TO-LEFT OVERRIDE
        <= u
        <= 0x2064
        or u == 0x2065  # Cf   [5] WORD JOINER..INVISIBLE PLUS
        or 0x2066 <= u <= 0x206F  # Cn       <reserved-2065>
        or u == 0x3164  # Cf  [10] LEFT-TO-RIGHT ISOLATE..NOMINAL DIGIT SHAPES
        or 0xFE00 <= u <= 0xFE0F  # Lo       HANGUL FILLER
        or u == 0xFEFF  # Mn  [16] VARIATION SELECTOR-1..VARIATION SELECTOR-16
        or u == 0xFFA0  # Cf       ZERO WIDTH NO-BREAK SPACE
        or 0xFFF0 <= u <= 0xFFF8  # Lo       HALFWIDTH HANGUL FILLER
        or 0x1BCA0 <= u <= 0x1BCA3  # Cn   [9] <reserved-FFF0>..<reserved-FFF8>
        or 0x1D173  # Cf   [4] SHORTHAND FORMAT LETTER OVERLAP..SHORTHAND FORMAT UP STEP
        <= u
        <= 0x1D17A
        or u == 0xE0000  # Cf   [8] MUSICAL SYMBOL BEGIN BEAM..MUSICAL SYMBOL END PHRASE
        or u == 0xE0001  # Cn       <reserved-E0000>
        or 0xE0002 <= u <= 0xE001F  # Cf       LANGUAGE TAG
        or 0xE0020 <= u <= 0xE007F  # Cn  [30] <reserved-E0002>..<reserved-E001F>
        or 0xE0080 <= u <= 0xE00FF  # Cf  [96] TAG SPACE..CANCEL TAG
        or 0xE0100 <= u <= 0xE01EF  # Cn [128] <reserved-E0080>..<reserved-E00FF>
        or 0xE01F0  # Mn [240] VARIATION SELECTOR-17..VARIATION SELECTOR-256
        <= u
        <= 0xE0FFF
        or False  # Cn [3600] <reserved-E01F0>..<reserved-E0FFF>
    )
