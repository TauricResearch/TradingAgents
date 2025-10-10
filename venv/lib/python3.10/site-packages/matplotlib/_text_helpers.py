"""
Low-level text helper utilities.
"""

from __future__ import annotations

import dataclasses

from . import _api
from .ft2font import FT2Font, Kerning, LoadFlags


@dataclasses.dataclass(frozen=True)
class LayoutItem:
    ft_object: FT2Font
    char: str
    glyph_idx: int
    x: float
    prev_kern: float


def warn_on_missing_glyph(codepoint, fontnames):
    _api.warn_external(
        f"Glyph {codepoint} "
        f"({chr(codepoint).encode('ascii', 'namereplace').decode('ascii')}) "
        f"missing from font(s) {fontnames}.")

    block = ("Hebrew" if 0x0590 <= codepoint <= 0x05ff else
             "Arabic" if 0x0600 <= codepoint <= 0x06ff else
             "Devanagari" if 0x0900 <= codepoint <= 0x097f else
             "Bengali" if 0x0980 <= codepoint <= 0x09ff else
             "Gurmukhi" if 0x0a00 <= codepoint <= 0x0a7f else
             "Gujarati" if 0x0a80 <= codepoint <= 0x0aff else
             "Oriya" if 0x0b00 <= codepoint <= 0x0b7f else
             "Tamil" if 0x0b80 <= codepoint <= 0x0bff else
             "Telugu" if 0x0c00 <= codepoint <= 0x0c7f else
             "Kannada" if 0x0c80 <= codepoint <= 0x0cff else
             "Malayalam" if 0x0d00 <= codepoint <= 0x0d7f else
             "Sinhala" if 0x0d80 <= codepoint <= 0x0dff else
             None)
    if block:
        _api.warn_external(
            f"Matplotlib currently does not support {block} natively.")


def layout(string, font, *, kern_mode=Kerning.DEFAULT):
    """
    Render *string* with *font*.

    For each character in *string*, yield a LayoutItem instance. When such an instance
    is yielded, the font's glyph is set to the corresponding character.

    Parameters
    ----------
    string : str
        The string to be rendered.
    font : FT2Font
        The font.
    kern_mode : Kerning
        A FreeType kerning mode.

    Yields
    ------
    LayoutItem
    """
    x = 0
    prev_glyph_idx = None
    char_to_font = font._get_fontmap(string)
    base_font = font
    for char in string:
        # This has done the fallback logic
        font = char_to_font.get(char, base_font)
        glyph_idx = font.get_char_index(ord(char))
        kern = (
            base_font.get_kerning(prev_glyph_idx, glyph_idx, kern_mode) / 64
            if prev_glyph_idx is not None else 0.
        )
        x += kern
        glyph = font.load_glyph(glyph_idx, flags=LoadFlags.NO_HINTING)
        yield LayoutItem(font, char, glyph_idx, x, kern)
        x += glyph.linearHoriAdvance / 65536
        prev_glyph_idx = glyph_idx
