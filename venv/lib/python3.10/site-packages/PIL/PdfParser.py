from __future__ import annotations

import calendar
import codecs
import collections
import mmap
import os
import re
import time
import zlib
from typing import IO, Any, NamedTuple, Union


# see 7.9.2.2 Text String Type on page 86 and D.3 PDFDocEncoding Character Set
# on page 656
def encode_text(s: str) -> bytes:
    return codecs.BOM_UTF16_BE + s.encode("utf_16_be")


PDFDocEncoding = {
    0x16: "\u0017",
    0x18: "\u02d8",
    0x19: "\u02c7",
    0x1A: "\u02c6",
    0x1B: "\u02d9",
    0x1C: "\u02dd",
    0x1D: "\u02db",
    0x1E: "\u02da",
    0x1F: "\u02dc",
    0x80: "\u2022",
    0x81: "\u2020",
    0x82: "\u2021",
    0x83: "\u2026",
    0x84: "\u2014",
    0x85: "\u2013",
    0x86: "\u0192",
    0x87: "\u2044",
    0x88: "\u2039",
    0x89: "\u203a",
    0x8A: "\u2212",
    0x8B: "\u2030",
    0x8C: "\u201e",
    0x8D: "\u201c",
    0x8E: "\u201d",
    0x8F: "\u2018",
    0x90: "\u2019",
    0x91: "\u201a",
    0x92: "\u2122",
    0x93: "\ufb01",
    0x94: "\ufb02",
    0x95: "\u0141",
    0x96: "\u0152",
    0x97: "\u0160",
    0x98: "\u0178",
    0x99: "\u017d",
    0x9A: "\u0131",
    0x9B: "\u0142",
    0x9C: "\u0153",
    0x9D: "\u0161",
    0x9E: "\u017e",
    0xA0: "\u20ac",
}


def decode_text(b: bytes) -> str:
    if b[: len(codecs.BOM_UTF16_BE)] == codecs.BOM_UTF16_BE:
        return b[len(codecs.BOM_UTF16_BE) :].decode("utf_16_be")
    else:
        return "".join(PDFDocEncoding.get(byte, chr(byte)) for byte in b)


class PdfFormatError(RuntimeError):
    """An error that probably indicates a syntactic or semantic error in the
    PDF file structure"""

    pass


def check_format_condition(condition: bool, error_message: str) -> None:
    if not condition:
        raise PdfFormatError(error_message)


class IndirectReferenceTuple(NamedTuple):
    object_id: int
    generation: int


class IndirectReference(IndirectReferenceTuple):
    def __str__(self) -> str:
        return f"{self.object_id} {self.generation} R"

    def __bytes__(self) -> bytes:
        return self.__str__().encode("us-ascii")

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        assert isinstance(other, IndirectReference)
        return other.object_id == self.object_id and other.generation == self.generation

    def __ne__(self, other: object) -> bool:
        return not (self == other)

    def __hash__(self) -> int:
        return hash((self.object_id, self.generation))


class IndirectObjectDef(IndirectReference):
    def __str__(self) -> str:
        return f"{self.object_id} {self.generation} obj"


class XrefTable:
    def __init__(self) -> None:
        self.existing_entries: dict[int, tuple[int, int]] = (
            {}
        )  # object ID => (offset, generation)
        self.new_entries: dict[int, tuple[int, int]] = (
            {}
        )  # object ID => (offset, generation)
        self.deleted_entries = {0: 65536}  # object ID => generation
        self.reading_finished = False

    def __setitem__(self, key: int, value: tuple[int, int]) -> None:
        if self.reading_finished:
            self.new_entries[key] = value
        else:
            self.existing_entries[key] = value
        if key in self.deleted_entries:
            del self.deleted_entries[key]

    def __getitem__(self, key: int) -> tuple[int, int]:
        try:
            return self.new_entries[key]
        except KeyError:
            return self.existing_entries[key]

    def __delitem__(self, key: int) -> None:
        if key in self.new_entries:
            generation = self.new_entries[key][1] + 1
            del self.new_entries[key]
            self.deleted_entries[key] = generation
        elif key in self.existing_entries:
            generation = self.existing_entries[key][1] + 1
            self.deleted_entries[key] = generation
        elif key in self.deleted_entries:
            generation = self.deleted_entries[key]
        else:
            msg = f"object ID {key} cannot be deleted because it doesn't exist"
            raise IndexError(msg)

    def __contains__(self, key: int) -> bool:
        return key in self.existing_entries or key in self.new_entries

    def __len__(self) -> int:
        return len(
            set(self.existing_entries.keys())
            | set(self.new_entries.keys())
            | set(self.deleted_entries.keys())
        )

    def keys(self) -> set[int]:
        return (
            set(self.existing_entries.keys()) - set(self.deleted_entries.keys())
        ) | set(self.new_entries.keys())

    def write(self, f: IO[bytes]) -> int:
        keys = sorted(set(self.new_entries.keys()) | set(self.deleted_entries.keys()))
        deleted_keys = sorted(set(self.deleted_entries.keys()))
        startxref = f.tell()
        f.write(b"xref\n")
        while keys:
            # find a contiguous sequence of object IDs
            prev: int | None = None
            for index, key in enumerate(keys):
                if prev is None or prev + 1 == key:
                    prev = key
                else:
                    contiguous_keys = keys[:index]
                    keys = keys[index:]
                    break
            else:
                contiguous_keys = keys
                keys = []
            f.write(b"%d %d\n" % (contiguous_keys[0], len(contiguous_keys)))
            for object_id in contiguous_keys:
                if object_id in self.new_entries:
                    f.write(b"%010d %05d n \n" % self.new_entries[object_id])
                else:
                    this_deleted_object_id = deleted_keys.pop(0)
                    check_format_condition(
                        object_id == this_deleted_object_id,
                        f"expected the next deleted object ID to be {object_id}, "
                        f"instead found {this_deleted_object_id}",
                    )
                    try:
                        next_in_linked_list = deleted_keys[0]
                    except IndexError:
                        next_in_linked_list = 0
                    f.write(
                        b"%010d %05d f \n"
                        % (next_in_linked_list, self.deleted_entries[object_id])
                    )
        return startxref


class PdfName:
    name: bytes

    def __init__(self, name: PdfName | bytes | str) -> None:
        if isinstance(name, PdfName):
            self.name = name.name
        elif isinstance(name, bytes):
            self.name = name
        else:
            self.name = name.encode("us-ascii")

    def name_as_str(self) -> str:
        return self.name.decode("us-ascii")

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, PdfName) and other.name == self.name
        ) or other == self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.name)})"

    @classmethod
    def from_pdf_stream(cls, data: bytes) -> PdfName:
        return cls(PdfParser.interpret_name(data))

    allowed_chars = set(range(33, 127)) - {ord(c) for c in "#%/()<>[]{}"}

    def __bytes__(self) -> bytes:
        result = bytearray(b"/")
        for b in self.name:
            if b in self.allowed_chars:
                result.append(b)
            else:
                result.extend(b"#%02X" % b)
        return bytes(result)


class PdfArray(list[Any]):
    def __bytes__(self) -> bytes:
        return b"[ " + b" ".join(pdf_repr(x) for x in self) + b" ]"


TYPE_CHECKING = False
if TYPE_CHECKING:
    _DictBase = collections.UserDict[Union[str, bytes], Any]
else:
    _DictBase = collections.UserDict


class PdfDict(_DictBase):
    def __setattr__(self, key: str, value: Any) -> None:
        if key == "data":
            collections.UserDict.__setattr__(self, key, value)
        else:
            self[key.encode("us-ascii")] = value

    def __getattr__(self, key: str) -> str | time.struct_time:
        try:
            value = self[key.encode("us-ascii")]
        except KeyError as e:
            raise AttributeError(key) from e
        if isinstance(value, bytes):
            value = decode_text(value)
        if key.endswith("Date"):
            if value.startswith("D:"):
                value = value[2:]

            relationship = "Z"
            if len(value) > 17:
                relationship = value[14]
                offset = int(value[15:17]) * 60
                if len(value) > 20:
                    offset += int(value[18:20])

            format = "%Y%m%d%H%M%S"[: len(value) - 2]
            value = time.strptime(value[: len(format) + 2], format)
            if relationship in ["+", "-"]:
                offset *= 60
                if relationship == "+":
                    offset *= -1
                value = time.gmtime(calendar.timegm(value) + offset)
        return value

    def __bytes__(self) -> bytes:
        out = bytearray(b"<<")
        for key, value in self.items():
            if value is None:
                continue
            value = pdf_repr(value)
            out.extend(b"\n")
            out.extend(bytes(PdfName(key)))
            out.extend(b" ")
            out.extend(value)
        out.extend(b"\n>>")
        return bytes(out)


class PdfBinary:
    def __init__(self, data: list[int] | bytes) -> None:
        self.data = data

    def __bytes__(self) -> bytes:
        return b"<%s>" % b"".join(b"%02X" % b for b in self.data)


class PdfStream:
    def __init__(self, dictionary: PdfDict, buf: bytes) -> None:
        self.dictionary = dictionary
        self.buf = buf

    def decode(self) -> bytes:
        try:
            filter = self.dictionary[b"Filter"]
        except KeyError:
            return self.buf
        if filter == b"FlateDecode":
            try:
                expected_length = self.dictionary[b"DL"]
            except KeyError:
                expected_length = self.dictionary[b"Length"]
            return zlib.decompress(self.buf, bufsize=int(expected_length))
        else:
            msg = f"stream filter {repr(filter)} unknown/unsupported"
            raise NotImplementedError(msg)


def pdf_repr(x: Any) -> bytes:
    if x is True:
        return b"true"
    elif x is False:
        return b"false"
    elif x is None:
        return b"null"
    elif isinstance(x, (PdfName, PdfDict, PdfArray, PdfBinary)):
        return bytes(x)
    elif isinstance(x, (int, float)):
        return str(x).encode("us-ascii")
    elif isinstance(x, time.struct_time):
        return b"(D:" + time.strftime("%Y%m%d%H%M%SZ", x).encode("us-ascii") + b")"
    elif isinstance(x, dict):
        return bytes(PdfDict(x))
    elif isinstance(x, list):
        return bytes(PdfArray(x))
    elif isinstance(x, str):
        return pdf_repr(encode_text(x))
    elif isinstance(x, bytes):
        # XXX escape more chars? handle binary garbage
        x = x.replace(b"\\", b"\\\\")
        x = x.replace(b"(", b"\\(")
        x = x.replace(b")", b"\\)")
        return b"(" + x + b")"
    else:
        return bytes(x)


class PdfParser:
    """Based on
    https://www.adobe.com/content/dam/acom/en/devnet/acrobat/pdfs/PDF32000_2008.pdf
    Supports PDF up to 1.4
    """

    def __init__(
        self,
        filename: str | None = None,
        f: IO[bytes] | None = None,
        buf: bytes | bytearray | None = None,
        start_offset: int = 0,
        mode: str = "rb",
    ) -> None:
        if buf and f:
            msg = "specify buf or f or filename, but not both buf and f"
            raise RuntimeError(msg)
        self.filename = filename
        self.buf: bytes | bytearray | mmap.mmap | None = buf
        self.f = f
        self.start_offset = start_offset
        self.should_close_buf = False
        self.should_close_file = False
        if filename is not None and f is None:
            self.f = f = open(filename, mode)
            self.should_close_file = True
        if f is not None:
            self.buf = self.get_buf_from_file(f)
            self.should_close_buf = True
            if not filename and hasattr(f, "name"):
                self.filename = f.name
        self.cached_objects: dict[IndirectReference, Any] = {}
        self.root_ref: IndirectReference | None
        self.info_ref: IndirectReference | None
        self.pages_ref: IndirectReference | None
        self.last_xref_section_offset: int | None
        if self.buf:
            self.read_pdf_info()
        else:
            self.file_size_total = self.file_size_this = 0
            self.root = PdfDict()
            self.root_ref = None
            self.info = PdfDict()
            self.info_ref = None
            self.page_tree_root = PdfDict()
            self.pages: list[IndirectReference] = []
            self.orig_pages: list[IndirectReference] = []
            self.pages_ref = None
            self.last_xref_section_offset = None
            self.trailer_dict: dict[bytes, Any] = {}
            self.xref_table = XrefTable()
        self.xref_table.reading_finished = True
        if f:
            self.seek_end()

    def __enter__(self) -> PdfParser:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def start_writing(self) -> None:
        self.close_buf()
        self.seek_end()

    def close_buf(self) -> None:
        if isinstance(self.buf, mmap.mmap):
            self.buf.close()
        self.buf = None

    def close(self) -> None:
        if self.should_close_buf:
            self.close_buf()
        if self.f is not None and self.should_close_file:
            self.f.close()
            self.f = None

    def seek_end(self) -> None:
        assert self.f is not None
        self.f.seek(0, os.SEEK_END)

    def write_header(self) -> None:
        assert self.f is not None
        self.f.write(b"%PDF-1.4\n")

    def write_comment(self, s: str) -> None:
        assert self.f is not None
        self.f.write(f"% {s}\n".encode())

    def write_catalog(self) -> IndirectReference:
        assert self.f is not None
        self.del_root()
        self.root_ref = self.next_object_id(self.f.tell())
        self.pages_ref = self.next_object_id(0)
        self.rewrite_pages()
        self.write_obj(self.root_ref, Type=PdfName(b"Catalog"), Pages=self.pages_ref)
        self.write_obj(
            self.pages_ref,
            Type=PdfName(b"Pages"),
            Count=len(self.pages),
            Kids=self.pages,
        )
        return self.root_ref

    def rewrite_pages(self) -> None:
        pages_tree_nodes_to_delete = []
        for i, page_ref in enumerate(self.orig_pages):
            page_info = self.cached_objects[page_ref]
            del self.xref_table[page_ref.object_id]
            pages_tree_nodes_to_delete.append(page_info[PdfName(b"Parent")])
            if page_ref not in self.pages:
                # the page has been deleted
                continue
            # make dict keys into strings for passing to write_page
            stringified_page_info = {}
            for key, value in page_info.items():
                # key should be a PdfName
                stringified_page_info[key.name_as_str()] = value
            stringified_page_info["Parent"] = self.pages_ref
            new_page_ref = self.write_page(None, **stringified_page_info)
            for j, cur_page_ref in enumerate(self.pages):
                if cur_page_ref == page_ref:
                    # replace the page reference with the new one
                    self.pages[j] = new_page_ref
        # delete redundant Pages tree nodes from xref table
        for pages_tree_node_ref in pages_tree_nodes_to_delete:
            while pages_tree_node_ref:
                pages_tree_node = self.cached_objects[pages_tree_node_ref]
                if pages_tree_node_ref.object_id in self.xref_table:
                    del self.xref_table[pages_tree_node_ref.object_id]
                pages_tree_node_ref = pages_tree_node.get(b"Parent", None)
        self.orig_pages = []

    def write_xref_and_trailer(
        self, new_root_ref: IndirectReference | None = None
    ) -> None:
        assert self.f is not None
        if new_root_ref:
            self.del_root()
            self.root_ref = new_root_ref
        if self.info:
            self.info_ref = self.write_obj(None, self.info)
        start_xref = self.xref_table.write(self.f)
        num_entries = len(self.xref_table)
        trailer_dict: dict[str | bytes, Any] = {
            b"Root": self.root_ref,
            b"Size": num_entries,
        }
        if self.last_xref_section_offset is not None:
            trailer_dict[b"Prev"] = self.last_xref_section_offset
        if self.info:
            trailer_dict[b"Info"] = self.info_ref
        self.last_xref_section_offset = start_xref
        self.f.write(
            b"trailer\n"
            + bytes(PdfDict(trailer_dict))
            + b"\nstartxref\n%d\n%%%%EOF" % start_xref
        )

    def write_page(
        self, ref: int | IndirectReference | None, *objs: Any, **dict_obj: Any
    ) -> IndirectReference:
        obj_ref = self.pages[ref] if isinstance(ref, int) else ref
        if "Type" not in dict_obj:
            dict_obj["Type"] = PdfName(b"Page")
        if "Parent" not in dict_obj:
            dict_obj["Parent"] = self.pages_ref
        return self.write_obj(obj_ref, *objs, **dict_obj)

    def write_obj(
        self, ref: IndirectReference | None, *objs: Any, **dict_obj: Any
    ) -> IndirectReference:
        assert self.f is not None
        f = self.f
        if ref is None:
            ref = self.next_object_id(f.tell())
        else:
            self.xref_table[ref.object_id] = (f.tell(), ref.generation)
        f.write(bytes(IndirectObjectDef(*ref)))
        stream = dict_obj.pop("stream", None)
        if stream is not None:
            dict_obj["Length"] = len(stream)
        if dict_obj:
            f.write(pdf_repr(dict_obj))
        for obj in objs:
            f.write(pdf_repr(obj))
        if stream is not None:
            f.write(b"stream\n")
            f.write(stream)
            f.write(b"\nendstream\n")
        f.write(b"endobj\n")
        return ref

    def del_root(self) -> None:
        if self.root_ref is None:
            return
        del self.xref_table[self.root_ref.object_id]
        del self.xref_table[self.root[b"Pages"].object_id]

    @staticmethod
    def get_buf_from_file(f: IO[bytes]) -> bytes | mmap.mmap:
        if hasattr(f, "getbuffer"):
            return f.getbuffer()
        elif hasattr(f, "getvalue"):
            return f.getvalue()
        else:
            try:
                return mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            except ValueError:  # cannot mmap an empty file
                return b""

    def read_pdf_info(self) -> None:
        assert self.buf is not None
        self.file_size_total = len(self.buf)
        self.file_size_this = self.file_size_total - self.start_offset
        self.read_trailer()
        check_format_condition(
            self.trailer_dict.get(b"Root") is not None, "Root is missing"
        )
        self.root_ref = self.trailer_dict[b"Root"]
        assert self.root_ref is not None
        self.info_ref = self.trailer_dict.get(b"Info", None)
        self.root = PdfDict(self.read_indirect(self.root_ref))
        if self.info_ref is None:
            self.info = PdfDict()
        else:
            self.info = PdfDict(self.read_indirect(self.info_ref))
        check_format_condition(b"Type" in self.root, "/Type missing in Root")
        check_format_condition(
            self.root[b"Type"] == b"Catalog", "/Type in Root is not /Catalog"
        )
        check_format_condition(
            self.root.get(b"Pages") is not None, "/Pages missing in Root"
        )
        check_format_condition(
            isinstance(self.root[b"Pages"], IndirectReference),
            "/Pages in Root is not an indirect reference",
        )
        self.pages_ref = self.root[b"Pages"]
        assert self.pages_ref is not None
        self.page_tree_root = self.read_indirect(self.pages_ref)
        self.pages = self.linearize_page_tree(self.page_tree_root)
        # save the original list of page references
        # in case the user modifies, adds or deletes some pages
        # and we need to rewrite the pages and their list
        self.orig_pages = self.pages[:]

    def next_object_id(self, offset: int | None = None) -> IndirectReference:
        try:
            # TODO: support reuse of deleted objects
            reference = IndirectReference(max(self.xref_table.keys()) + 1, 0)
        except ValueError:
            reference = IndirectReference(1, 0)
        if offset is not None:
            self.xref_table[reference.object_id] = (offset, 0)
        return reference

    delimiter = rb"[][()<>{}/%]"
    delimiter_or_ws = rb"[][()<>{}/%\000\011\012\014\015\040]"
    whitespace = rb"[\000\011\012\014\015\040]"
    whitespace_or_hex = rb"[\000\011\012\014\015\0400-9a-fA-F]"
    whitespace_optional = whitespace + b"*"
    whitespace_mandatory = whitespace + b"+"
    # No "\012" aka "\n" or "\015" aka "\r":
    whitespace_optional_no_nl = rb"[\000\011\014\040]*"
    newline_only = rb"[\r\n]+"
    newline = whitespace_optional_no_nl + newline_only + whitespace_optional_no_nl
    re_trailer_end = re.compile(
        whitespace_mandatory
        + rb"trailer"
        + whitespace_optional
        + rb"<<(.*>>)"
        + newline
        + rb"startxref"
        + newline
        + rb"([0-9]+)"
        + newline
        + rb"%%EOF"
        + whitespace_optional
        + rb"$",
        re.DOTALL,
    )
    re_trailer_prev = re.compile(
        whitespace_optional
        + rb"trailer"
        + whitespace_optional
        + rb"<<(.*?>>)"
        + newline
        + rb"startxref"
        + newline
        + rb"([0-9]+)"
        + newline
        + rb"%%EOF"
        + whitespace_optional,
        re.DOTALL,
    )

    def read_trailer(self) -> None:
        assert self.buf is not None
        search_start_offset = len(self.buf) - 16384
        if search_start_offset < self.start_offset:
            search_start_offset = self.start_offset
        m = self.re_trailer_end.search(self.buf, search_start_offset)
        check_format_condition(m is not None, "trailer end not found")
        # make sure we found the LAST trailer
        last_match = m
        while m:
            last_match = m
            m = self.re_trailer_end.search(self.buf, m.start() + 16)
        if not m:
            m = last_match
        assert m is not None
        trailer_data = m.group(1)
        self.last_xref_section_offset = int(m.group(2))
        self.trailer_dict = self.interpret_trailer(trailer_data)
        self.xref_table = XrefTable()
        self.read_xref_table(xref_section_offset=self.last_xref_section_offset)
        if b"Prev" in self.trailer_dict:
            self.read_prev_trailer(self.trailer_dict[b"Prev"])

    def read_prev_trailer(self, xref_section_offset: int) -> None:
        assert self.buf is not None
        trailer_offset = self.read_xref_table(xref_section_offset=xref_section_offset)
        m = self.re_trailer_prev.search(
            self.buf[trailer_offset : trailer_offset + 16384]
        )
        check_format_condition(m is not None, "previous trailer not found")
        assert m is not None
        trailer_data = m.group(1)
        check_format_condition(
            int(m.group(2)) == xref_section_offset,
            "xref section offset in previous trailer doesn't match what was expected",
        )
        trailer_dict = self.interpret_trailer(trailer_data)
        if b"Prev" in trailer_dict:
            self.read_prev_trailer(trailer_dict[b"Prev"])

    re_whitespace_optional = re.compile(whitespace_optional)
    re_name = re.compile(
        whitespace_optional
        + rb"/([!-$&'*-.0-;=?-Z\\^-z|~]+)(?="
        + delimiter_or_ws
        + rb")"
    )
    re_dict_start = re.compile(whitespace_optional + rb"<<")
    re_dict_end = re.compile(whitespace_optional + rb">>" + whitespace_optional)

    @classmethod
    def interpret_trailer(cls, trailer_data: bytes) -> dict[bytes, Any]:
        trailer = {}
        offset = 0
        while True:
            m = cls.re_name.match(trailer_data, offset)
            if not m:
                m = cls.re_dict_end.match(trailer_data, offset)
                check_format_condition(
                    m is not None and m.end() == len(trailer_data),
                    "name not found in trailer, remaining data: "
                    + repr(trailer_data[offset:]),
                )
                break
            key = cls.interpret_name(m.group(1))
            assert isinstance(key, bytes)
            value, value_offset = cls.get_value(trailer_data, m.end())
            trailer[key] = value
            if value_offset is None:
                break
            offset = value_offset
        check_format_condition(
            b"Size" in trailer and isinstance(trailer[b"Size"], int),
            "/Size not in trailer or not an integer",
        )
        check_format_condition(
            b"Root" in trailer and isinstance(trailer[b"Root"], IndirectReference),
            "/Root not in trailer or not an indirect reference",
        )
        return trailer

    re_hashes_in_name = re.compile(rb"([^#]*)(#([0-9a-fA-F]{2}))?")

    @classmethod
    def interpret_name(cls, raw: bytes, as_text: bool = False) -> str | bytes:
        name = b""
        for m in cls.re_hashes_in_name.finditer(raw):
            if m.group(3):
                name += m.group(1) + bytearray.fromhex(m.group(3).decode("us-ascii"))
            else:
                name += m.group(1)
        if as_text:
            return name.decode("utf-8")
        else:
            return bytes(name)

    re_null = re.compile(whitespace_optional + rb"null(?=" + delimiter_or_ws + rb")")
    re_true = re.compile(whitespace_optional + rb"true(?=" + delimiter_or_ws + rb")")
    re_false = re.compile(whitespace_optional + rb"false(?=" + delimiter_or_ws + rb")")
    re_int = re.compile(
        whitespace_optional + rb"([-+]?[0-9]+)(?=" + delimiter_or_ws + rb")"
    )
    re_real = re.compile(
        whitespace_optional
        + rb"([-+]?([0-9]+\.[0-9]*|[0-9]*\.[0-9]+))(?="
        + delimiter_or_ws
        + rb")"
    )
    re_array_start = re.compile(whitespace_optional + rb"\[")
    re_array_end = re.compile(whitespace_optional + rb"]")
    re_string_hex = re.compile(
        whitespace_optional + rb"<(" + whitespace_or_hex + rb"*)>"
    )
    re_string_lit = re.compile(whitespace_optional + rb"\(")
    re_indirect_reference = re.compile(
        whitespace_optional
        + rb"([-+]?[0-9]+)"
        + whitespace_mandatory
        + rb"([-+]?[0-9]+)"
        + whitespace_mandatory
        + rb"R(?="
        + delimiter_or_ws
        + rb")"
    )
    re_indirect_def_start = re.compile(
        whitespace_optional
        + rb"([-+]?[0-9]+)"
        + whitespace_mandatory
        + rb"([-+]?[0-9]+)"
        + whitespace_mandatory
        + rb"obj(?="
        + delimiter_or_ws
        + rb")"
    )
    re_indirect_def_end = re.compile(
        whitespace_optional + rb"endobj(?=" + delimiter_or_ws + rb")"
    )
    re_comment = re.compile(
        rb"(" + whitespace_optional + rb"%[^\r\n]*" + newline + rb")*"
    )
    re_stream_start = re.compile(whitespace_optional + rb"stream\r?\n")
    re_stream_end = re.compile(
        whitespace_optional + rb"endstream(?=" + delimiter_or_ws + rb")"
    )

    @classmethod
    def get_value(
        cls,
        data: bytes | bytearray | mmap.mmap,
        offset: int,
        expect_indirect: IndirectReference | None = None,
        max_nesting: int = -1,
    ) -> tuple[Any, int | None]:
        if max_nesting == 0:
            return None, None
        m = cls.re_comment.match(data, offset)
        if m:
            offset = m.end()
        m = cls.re_indirect_def_start.match(data, offset)
        if m:
            check_format_condition(
                int(m.group(1)) > 0,
                "indirect object definition: object ID must be greater than 0",
            )
            check_format_condition(
                int(m.group(2)) >= 0,
                "indirect object definition: generation must be non-negative",
            )
            check_format_condition(
                expect_indirect is None
                or expect_indirect
                == IndirectReference(int(m.group(1)), int(m.group(2))),
                "indirect object definition different than expected",
            )
            object, object_offset = cls.get_value(
                data, m.end(), max_nesting=max_nesting - 1
            )
            if object_offset is None:
                return object, None
            m = cls.re_indirect_def_end.match(data, object_offset)
            check_format_condition(
                m is not None, "indirect object definition end not found"
            )
            assert m is not None
            return object, m.end()
        check_format_condition(
            not expect_indirect, "indirect object definition not found"
        )
        m = cls.re_indirect_reference.match(data, offset)
        if m:
            check_format_condition(
                int(m.group(1)) > 0,
                "indirect object reference: object ID must be greater than 0",
            )
            check_format_condition(
                int(m.group(2)) >= 0,
                "indirect object reference: generation must be non-negative",
            )
            return IndirectReference(int(m.group(1)), int(m.group(2))), m.end()
        m = cls.re_dict_start.match(data, offset)
        if m:
            offset = m.end()
            result: dict[Any, Any] = {}
            m = cls.re_dict_end.match(data, offset)
            current_offset: int | None = offset
            while not m:
                assert current_offset is not None
                key, current_offset = cls.get_value(
                    data, current_offset, max_nesting=max_nesting - 1
                )
                if current_offset is None:
                    return result, None
                value, current_offset = cls.get_value(
                    data, current_offset, max_nesting=max_nesting - 1
                )
                result[key] = value
                if current_offset is None:
                    return result, None
                m = cls.re_dict_end.match(data, current_offset)
            current_offset = m.end()
            m = cls.re_stream_start.match(data, current_offset)
            if m:
                stream_len = result.get(b"Length")
                if stream_len is None or not isinstance(stream_len, int):
                    msg = f"bad or missing Length in stream dict ({stream_len})"
                    raise PdfFormatError(msg)
                stream_data = data[m.end() : m.end() + stream_len]
                m = cls.re_stream_end.match(data, m.end() + stream_len)
                check_format_condition(m is not None, "stream end not found")
                assert m is not None
                current_offset = m.end()
                return PdfStream(PdfDict(result), stream_data), current_offset
            return PdfDict(result), current_offset
        m = cls.re_array_start.match(data, offset)
        if m:
            offset = m.end()
            results = []
            m = cls.re_array_end.match(data, offset)
            current_offset = offset
            while not m:
                assert current_offset is not None
                value, current_offset = cls.get_value(
                    data, current_offset, max_nesting=max_nesting - 1
                )
                results.append(value)
                if current_offset is None:
                    return results, None
                m = cls.re_array_end.match(data, current_offset)
            return results, m.end()
        m = cls.re_null.match(data, offset)
        if m:
            return None, m.end()
        m = cls.re_true.match(data, offset)
        if m:
            return True, m.end()
        m = cls.re_false.match(data, offset)
        if m:
            return False, m.end()
        m = cls.re_name.match(data, offset)
        if m:
            return PdfName(cls.interpret_name(m.group(1))), m.end()
        m = cls.re_int.match(data, offset)
        if m:
            return int(m.group(1)), m.end()
        m = cls.re_real.match(data, offset)
        if m:
            # XXX Decimal instead of float???
            return float(m.group(1)), m.end()
        m = cls.re_string_hex.match(data, offset)
        if m:
            # filter out whitespace
            hex_string = bytearray(
                b for b in m.group(1) if b in b"0123456789abcdefABCDEF"
            )
            if len(hex_string) % 2 == 1:
                # append a 0 if the length is not even - yes, at the end
                hex_string.append(ord(b"0"))
            return bytearray.fromhex(hex_string.decode("us-ascii")), m.end()
        m = cls.re_string_lit.match(data, offset)
        if m:
            return cls.get_literal_string(data, m.end())
        # return None, offset  # fallback (only for debugging)
        msg = f"unrecognized object: {repr(data[offset : offset + 32])}"
        raise PdfFormatError(msg)

    re_lit_str_token = re.compile(
        rb"(\\[nrtbf()\\])|(\\[0-9]{1,3})|(\\(\r\n|\r|\n))|(\r\n|\r|\n)|(\()|(\))"
    )
    escaped_chars = {
        b"n": b"\n",
        b"r": b"\r",
        b"t": b"\t",
        b"b": b"\b",
        b"f": b"\f",
        b"(": b"(",
        b")": b")",
        b"\\": b"\\",
        ord(b"n"): b"\n",
        ord(b"r"): b"\r",
        ord(b"t"): b"\t",
        ord(b"b"): b"\b",
        ord(b"f"): b"\f",
        ord(b"("): b"(",
        ord(b")"): b")",
        ord(b"\\"): b"\\",
    }

    @classmethod
    def get_literal_string(
        cls, data: bytes | bytearray | mmap.mmap, offset: int
    ) -> tuple[bytes, int]:
        nesting_depth = 0
        result = bytearray()
        for m in cls.re_lit_str_token.finditer(data, offset):
            result.extend(data[offset : m.start()])
            if m.group(1):
                result.extend(cls.escaped_chars[m.group(1)[1]])
            elif m.group(2):
                result.append(int(m.group(2)[1:], 8))
            elif m.group(3):
                pass
            elif m.group(5):
                result.extend(b"\n")
            elif m.group(6):
                result.extend(b"(")
                nesting_depth += 1
            elif m.group(7):
                if nesting_depth == 0:
                    return bytes(result), m.end()
                result.extend(b")")
                nesting_depth -= 1
            offset = m.end()
        msg = "unfinished literal string"
        raise PdfFormatError(msg)

    re_xref_section_start = re.compile(whitespace_optional + rb"xref" + newline)
    re_xref_subsection_start = re.compile(
        whitespace_optional
        + rb"([0-9]+)"
        + whitespace_mandatory
        + rb"([0-9]+)"
        + whitespace_optional
        + newline_only
    )
    re_xref_entry = re.compile(rb"([0-9]{10}) ([0-9]{5}) ([fn])( \r| \n|\r\n)")

    def read_xref_table(self, xref_section_offset: int) -> int:
        assert self.buf is not None
        subsection_found = False
        m = self.re_xref_section_start.match(
            self.buf, xref_section_offset + self.start_offset
        )
        check_format_condition(m is not None, "xref section start not found")
        assert m is not None
        offset = m.end()
        while True:
            m = self.re_xref_subsection_start.match(self.buf, offset)
            if not m:
                check_format_condition(
                    subsection_found, "xref subsection start not found"
                )
                break
            subsection_found = True
            offset = m.end()
            first_object = int(m.group(1))
            num_objects = int(m.group(2))
            for i in range(first_object, first_object + num_objects):
                m = self.re_xref_entry.match(self.buf, offset)
                check_format_condition(m is not None, "xref entry not found")
                assert m is not None
                offset = m.end()
                is_free = m.group(3) == b"f"
                if not is_free:
                    generation = int(m.group(2))
                    new_entry = (int(m.group(1)), generation)
                    if i not in self.xref_table:
                        self.xref_table[i] = new_entry
        return offset

    def read_indirect(self, ref: IndirectReference, max_nesting: int = -1) -> Any:
        offset, generation = self.xref_table[ref[0]]
        check_format_condition(
            generation == ref[1],
            f"expected to find generation {ref[1]} for object ID {ref[0]} in xref "
            f"table, instead found generation {generation} at offset {offset}",
        )
        assert self.buf is not None
        value = self.get_value(
            self.buf,
            offset + self.start_offset,
            expect_indirect=IndirectReference(*ref),
            max_nesting=max_nesting,
        )[0]
        self.cached_objects[ref] = value
        return value

    def linearize_page_tree(
        self, node: PdfDict | None = None
    ) -> list[IndirectReference]:
        page_node = node if node is not None else self.page_tree_root
        check_format_condition(
            page_node[b"Type"] == b"Pages", "/Type of page tree node is not /Pages"
        )
        pages = []
        for kid in page_node[b"Kids"]:
            kid_object = self.read_indirect(kid)
            if kid_object[b"Type"] == b"Page":
                pages.append(kid)
            else:
                pages.extend(self.linearize_page_tree(node=kid_object))
        return pages
