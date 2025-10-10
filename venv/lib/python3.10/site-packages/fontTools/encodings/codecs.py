"""Extend the Python codecs module with a few encodings that are used in OpenType (name table)
but missing from Python.  See https://github.com/fonttools/fonttools/issues/236 for details."""

import codecs
import encodings


class ExtendCodec(codecs.Codec):
    def __init__(self, name, base_encoding, mapping):
        self.name = name
        self.base_encoding = base_encoding
        self.mapping = mapping
        self.reverse = {v: k for k, v in mapping.items()}
        self.max_len = max(len(v) for v in mapping.values())
        self.info = codecs.CodecInfo(
            name=self.name, encode=self.encode, decode=self.decode
        )
        codecs.register_error(name, self.error)

    def _map(self, mapper, output_type, exc_type, input, errors):
        base_error_handler = codecs.lookup_error(errors)
        length = len(input)
        out = output_type()
        while input:
            # first try to use self.error as the error handler
            try:
                part = mapper(input, self.base_encoding, errors=self.name)
                out += part
                break  # All converted
            except exc_type as e:
                # else convert the correct part, handle error as requested and continue
                out += mapper(input[: e.start], self.base_encoding, self.name)
                replacement, pos = base_error_handler(e)
                out += replacement
                input = input[pos:]
        return out, length

    def encode(self, input, errors="strict"):
        return self._map(codecs.encode, bytes, UnicodeEncodeError, input, errors)

    def decode(self, input, errors="strict"):
        return self._map(codecs.decode, str, UnicodeDecodeError, input, errors)

    def error(self, e):
        if isinstance(e, UnicodeDecodeError):
            for end in range(e.start + 1, e.end + 1):
                s = e.object[e.start : end]
                if s in self.mapping:
                    return self.mapping[s], end
        elif isinstance(e, UnicodeEncodeError):
            for end in range(e.start + 1, e.start + self.max_len + 1):
                s = e.object[e.start : end]
                if s in self.reverse:
                    return self.reverse[s], end
        e.encoding = self.name
        raise e


_extended_encodings = {
    "x_mac_japanese_ttx": (
        "shift_jis",
        {
            b"\xFC": chr(0x007C),
            b"\x7E": chr(0x007E),
            b"\x80": chr(0x005C),
            b"\xA0": chr(0x00A0),
            b"\xFD": chr(0x00A9),
            b"\xFE": chr(0x2122),
            b"\xFF": chr(0x2026),
        },
    ),
    "x_mac_trad_chinese_ttx": (
        "big5",
        {
            b"\x80": chr(0x005C),
            b"\xA0": chr(0x00A0),
            b"\xFD": chr(0x00A9),
            b"\xFE": chr(0x2122),
            b"\xFF": chr(0x2026),
        },
    ),
    "x_mac_korean_ttx": (
        "euc_kr",
        {
            b"\x80": chr(0x00A0),
            b"\x81": chr(0x20A9),
            b"\x82": chr(0x2014),
            b"\x83": chr(0x00A9),
            b"\xFE": chr(0x2122),
            b"\xFF": chr(0x2026),
        },
    ),
    "x_mac_simp_chinese_ttx": (
        "gb2312",
        {
            b"\x80": chr(0x00FC),
            b"\xA0": chr(0x00A0),
            b"\xFD": chr(0x00A9),
            b"\xFE": chr(0x2122),
            b"\xFF": chr(0x2026),
        },
    ),
}

_cache = {}


def search_function(name):
    name = encodings.normalize_encoding(name)  # Rather undocumented...
    if name in _extended_encodings:
        if name not in _cache:
            base_encoding, mapping = _extended_encodings[name]
            assert name[-4:] == "_ttx"
            # Python 2 didn't have any of the encodings that we are implementing
            # in this file.  Python 3 added aliases for the East Asian ones, mapping
            # them "temporarily" to the same base encoding as us, with a comment
            # suggesting that full implementation will appear some time later.
            # As such, try the Python version of the x_mac_... first, if that is found,
            # use *that* as our base encoding.  This would make our encoding upgrade
            # to the full encoding when and if Python finally implements that.
            # http://bugs.python.org/issue24041
            base_encodings = [name[:-4], base_encoding]
            for base_encoding in base_encodings:
                try:
                    codecs.lookup(base_encoding)
                except LookupError:
                    continue
                _cache[name] = ExtendCodec(name, base_encoding, mapping)
                break
        return _cache[name].info

    return None


codecs.register(search_function)
