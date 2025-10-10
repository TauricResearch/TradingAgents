import matplotlib._type1font as t1f
import os.path
import difflib
import pytest


def test_Type1Font():
    filename = os.path.join(os.path.dirname(__file__), 'cmr10.pfb')
    font = t1f.Type1Font(filename)
    slanted = font.transform({'slant': 1})
    condensed = font.transform({'extend': 0.5})
    with open(filename, 'rb') as fd:
        rawdata = fd.read()
    assert font.parts[0] == rawdata[0x0006:0x10c5]
    assert font.parts[1] == rawdata[0x10cb:0x897f]
    assert font.parts[2] == rawdata[0x8985:0x8ba6]
    assert font.decrypted.startswith(b'dup\n/Private 18 dict dup begin')
    assert font.decrypted.endswith(b'mark currentfile closefile\n')
    assert slanted.decrypted.startswith(b'dup\n/Private 18 dict dup begin')
    assert slanted.decrypted.endswith(b'mark currentfile closefile\n')
    assert b'UniqueID 5000793' in font.parts[0]
    assert b'UniqueID 5000793' in font.decrypted
    assert font._pos['UniqueID'] == [(797, 818), (4483, 4504)]

    len0 = len(font.parts[0])
    for key in font._pos.keys():
        for pos0, pos1 in font._pos[key]:
            if pos0 < len0:
                data = font.parts[0][pos0:pos1]
            else:
                data = font.decrypted[pos0-len0:pos1-len0]
            assert data.startswith(f'/{key}'.encode('ascii'))
    assert {'FontType', 'FontMatrix', 'PaintType', 'ItalicAngle', 'RD'
            } < set(font._pos.keys())

    assert b'UniqueID 5000793' not in slanted.parts[0]
    assert b'UniqueID 5000793' not in slanted.decrypted
    assert 'UniqueID' not in slanted._pos
    assert font.prop['Weight'] == 'Medium'
    assert not font.prop['isFixedPitch']
    assert font.prop['ItalicAngle'] == 0
    assert slanted.prop['ItalicAngle'] == -45
    assert font.prop['Encoding'][5] == 'Pi'
    assert isinstance(font.prop['CharStrings']['Pi'], bytes)
    assert font._abbr['ND'] == 'ND'

    differ = difflib.Differ()
    diff = list(differ.compare(
        font.parts[0].decode('latin-1').splitlines(),
        slanted.parts[0].decode('latin-1').splitlines()))
    for line in (
         # Removes UniqueID
         '- /UniqueID 5000793 def',
         # Changes the font name
         '- /FontName /CMR10 def',
         '+ /FontName/CMR10_Slant_1000 def',
         # Alters FontMatrix
         '- /FontMatrix [0.001 0 0 0.001 0 0 ]readonly def',
         '+ /FontMatrix [0.001 0 0.001 0.001 0 0] readonly def',
         # Alters ItalicAngle
         '-  /ItalicAngle 0 def',
         '+  /ItalicAngle -45.0 def'):
        assert line in diff, 'diff to slanted font must contain %s' % line

    diff = list(differ.compare(
        font.parts[0].decode('latin-1').splitlines(),
        condensed.parts[0].decode('latin-1').splitlines()))
    for line in (
         # Removes UniqueID
         '- /UniqueID 5000793 def',
         # Changes the font name
         '- /FontName /CMR10 def',
         '+ /FontName/CMR10_Extend_500 def',
         # Alters FontMatrix
         '- /FontMatrix [0.001 0 0 0.001 0 0 ]readonly def',
         '+ /FontMatrix [0.0005 0 0 0.001 0 0] readonly def'):
        assert line in diff, 'diff to condensed font must contain %s' % line


def test_Type1Font_2():
    filename = os.path.join(os.path.dirname(__file__),
                            'Courier10PitchBT-Bold.pfb')
    font = t1f.Type1Font(filename)
    assert font.prop['Weight'] == 'Bold'
    assert font.prop['isFixedPitch']
    assert font.prop['Encoding'][65] == 'A'  # the font uses StandardEncoding
    (pos0, pos1), = font._pos['Encoding']
    assert font.parts[0][pos0:pos1] == b'/Encoding StandardEncoding'
    assert font._abbr['ND'] == '|-'


def test_tokenize():
    data = (b'1234/abc false -9.81  Foo <<[0 1 2]<0 1ef a\t>>>\n'
            b'(string with(nested\t\\) par)ens\\\\)')
    #         1           2          x    2     xx1
    # 1 and 2 are matching parens, x means escaped character
    n, w, num, kw, d = 'name', 'whitespace', 'number', 'keyword', 'delimiter'
    b, s = 'boolean', 'string'
    correct = [
        (num, 1234), (n, 'abc'), (w, ' '), (b, False), (w, ' '), (num, -9.81),
        (w, '  '), (kw, 'Foo'), (w, ' '), (d, '<<'), (d, '['), (num, 0),
        (w, ' '), (num, 1), (w, ' '), (num, 2), (d, ']'), (s, b'\x01\xef\xa0'),
        (d, '>>'), (w, '\n'), (s, 'string with(nested\t) par)ens\\')
    ]
    correct_no_ws = [x for x in correct if x[0] != w]

    def convert(tokens):
        return [(t.kind, t.value()) for t in tokens]

    assert convert(t1f._tokenize(data, False)) == correct
    assert convert(t1f._tokenize(data, True)) == correct_no_ws

    def bin_after(n):
        tokens = t1f._tokenize(data, True)
        result = []
        for _ in range(n):
            result.append(next(tokens))
        result.append(tokens.send(10))
        return convert(result)

    for n in range(1, len(correct_no_ws)):
        result = bin_after(n)
        assert result[:-1] == correct_no_ws[:n]
        assert result[-1][0] == 'binary'
        assert isinstance(result[-1][1], bytes)


def test_tokenize_errors():
    with pytest.raises(ValueError):
        list(t1f._tokenize(b'1234 (this (string) is unterminated\\)', True))
    with pytest.raises(ValueError):
        list(t1f._tokenize(b'/Foo<01234', True))
    with pytest.raises(ValueError):
        list(t1f._tokenize(b'/Foo<01234abcg>/Bar', True))


def test_overprecision():
    # We used to output too many digits in FontMatrix entries and
    # ItalicAngle, which could make Type-1 parsers unhappy.
    filename = os.path.join(os.path.dirname(__file__), 'cmr10.pfb')
    font = t1f.Type1Font(filename)
    slanted = font.transform({'slant': .167})
    lines = slanted.parts[0].decode('ascii').splitlines()
    matrix, = (line[line.index('[')+1:line.index(']')]
               for line in lines if '/FontMatrix' in line)
    angle, = (word
              for line in lines if '/ItalicAngle' in line
              for word in line.split() if word[0] in '-0123456789')
    # the following used to include 0.00016700000000000002
    assert matrix == '0.001 0 0.000167 0.001 0 0'
    # and here we had -9.48090361795083
    assert angle == '-9.4809'


def test_encrypt_decrypt_roundtrip():
    data = b'this is my plaintext \0\1\2\3'
    encrypted = t1f.Type1Font._encrypt(data, 'eexec')
    decrypted = t1f.Type1Font._decrypt(encrypted, 'eexec')
    assert encrypted != decrypted
    assert data == decrypted
