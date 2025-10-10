import json
from pathlib import Path
import shutil

import matplotlib.dviread as dr
import pytest


def test_PsfontsMap(monkeypatch):
    monkeypatch.setattr(dr, 'find_tex_file', lambda x: x.decode())

    filename = str(Path(__file__).parent / 'baseline_images/dviread/test.map')
    fontmap = dr.PsfontsMap(filename)
    # Check all properties of a few fonts
    for n in [1, 2, 3, 4, 5]:
        key = b'TeXfont%d' % n
        entry = fontmap[key]
        assert entry.texname == key
        assert entry.psname == b'PSfont%d' % n
        if n not in [3, 5]:
            assert entry.encoding == 'font%d.enc' % n
        elif n == 3:
            assert entry.encoding == 'enc3.foo'
        # We don't care about the encoding of TeXfont5, which specifies
        # multiple encodings.
        if n not in [1, 5]:
            assert entry.filename == 'font%d.pfa' % n
        else:
            assert entry.filename == 'font%d.pfb' % n
        if n == 4:
            assert entry.effects == {'slant': -0.1, 'extend': 1.2}
        else:
            assert entry.effects == {}
    # Some special cases
    entry = fontmap[b'TeXfont6']
    assert entry.filename is None
    assert entry.encoding is None
    entry = fontmap[b'TeXfont7']
    assert entry.filename is None
    assert entry.encoding == 'font7.enc'
    entry = fontmap[b'TeXfont8']
    assert entry.filename == 'font8.pfb'
    assert entry.encoding is None
    entry = fontmap[b'TeXfont9']
    assert entry.psname == b'TeXfont9'
    assert entry.filename == '/absolute/font9.pfb'
    # First of duplicates only.
    entry = fontmap[b'TeXfontA']
    assert entry.psname == b'PSfontA1'
    # Slant/Extend only works for T1 fonts.
    entry = fontmap[b'TeXfontB']
    assert entry.psname == b'PSfontB6'
    # Subsetted TrueType must have encoding.
    entry = fontmap[b'TeXfontC']
    assert entry.psname == b'PSfontC3'
    # Missing font
    with pytest.raises(LookupError, match='no-such-font'):
        fontmap[b'no-such-font']
    with pytest.raises(LookupError, match='%'):
        fontmap[b'%']


@pytest.mark.skipif(shutil.which("kpsewhich") is None,
                    reason="kpsewhich is not available")
def test_dviread():
    dirpath = Path(__file__).parent / 'baseline_images/dviread'
    with (dirpath / 'test.json').open() as f:
        correct = json.load(f)
    with dr.Dvi(str(dirpath / 'test.dvi'), None) as dvi:
        data = [{'text': [[t.x, t.y,
                           chr(t.glyph),
                           t.font.texname.decode('ascii'),
                           round(t.font.size, 2)]
                          for t in page.text],
                 'boxes': [[b.x, b.y, b.height, b.width] for b in page.boxes]}
                for page in dvi]
    assert data == correct
