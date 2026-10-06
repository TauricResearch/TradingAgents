"""A small XLSX writer on the standard library: ``zipfile`` and SpreadsheetML.

openpyxl and xlsxwriter are not dependencies, and pandas needs one of them to
write Excel, so the exports write the format themselves. Only what they use is
here: several sheets, numbers stored as numbers (so formulas work on them),
strings in a shared-string table, a bold header style, frozen panes, number
formats and column widths. Excel and LibreOffice both open the result.

A string beginning with ``= + - @`` (or a tab or carriage return) is written with
the ``quotePrefix`` style, the spreadsheet's own form of CSV's leading
apostrophe: the cell shows the text as it is, holds no formula, and stays text
if it is edited. A cell is a formula only when a ``<f>`` element says so, and
this writer never writes one.
"""

from __future__ import annotations

import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape, quoteattr

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
INTEGER, DECIMAL, PLAIN = 3, 4, 0  # built-in number formats: #,##0 and #,##0.00
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")


@dataclass
class Cell:
    """A value with its own style: ``fmt`` a built-in number format id, ``bold``."""

    value: object
    fmt: int | None = None
    bold: bool = False


@dataclass
class Sheet:
    name: str
    rows: list[list] = field(default_factory=list)
    header_rows: int = 1  # bold, and frozen above the scroll
    freeze_cols: int = 0  # columns frozen at the left
    widths: dict[int, float] = field(default_factory=dict)  # 0-based column -> width in characters
    number_format: int = DECIMAL  # for numbers without their own


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def clean_text(value: str) -> str:
    """The characters XML 1.0 can hold."""
    return _ILLEGAL.sub("", value)


def sheet_names(names: list[str]) -> list[str]:
    """Names Excel accepts: at most 31 characters, none of ``[]:*?/\\``, unique."""
    out: list[str] = []
    for name in names:
        base = _BAD_SHEET.sub(" ", clean_text(str(name))).strip().strip("'")[:31] or "Sheet"
        candidate, n = base, 2
        while candidate.casefold() in {o.casefold() for o in out}:
            suffix = f" ({n})"
            candidate, n = base[:31 - len(suffix)] + suffix, n + 1
        out.append(candidate)
    return out


class _Styles:
    """The cell formats used, numbered as the workbook's ``cellXfs`` list."""

    def __init__(self):
        self.xfs: list[tuple[int, bool, bool]] = [(PLAIN, False, False)]

    def index(self, fmt: int, bold: bool, quote: bool) -> int:
        key = (fmt, bold, quote)
        if key not in self.xfs:
            self.xfs.append(key)
        return self.xfs.index(key)

    def xml(self) -> str:
        xfs = "".join(
            f'<xf numFmtId="{fmt}" fontId="{1 if bold else 0}" fillId="0" borderId="0" xfId="0"'
            + (' applyNumberFormat="1"' if fmt else "") + (' applyFont="1"' if bold else "")
            + (' quotePrefix="1"' if quote else "") + "/>" for fmt, bold, quote in self.xfs)
        font = '<sz val="11"/><name val="Calibri"/><family val="2"/>'
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="{MAIN}">'
                f'<fonts count="2"><font>{font}</font><font><b/>{font}</font></fonts>'
                '<fills count="2"><fill><patternFill patternType="none"/></fill>'
                '<fill><patternFill patternType="gray125"/></fill></fills>'
                '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                f'<cellXfs count="{len(self.xfs)}">{xfs}</cellXfs>'
                '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                '</styleSheet>')


class _Strings:
    def __init__(self):
        self.order: list[str] = []
        self.ids: dict[str, int] = {}
        self.uses = 0

    def id(self, text: str) -> int:
        self.uses += 1
        if text not in self.ids:
            self.ids[text] = len(self.order)
            self.order.append(text)
        return self.ids[text]

    def xml(self) -> str:
        items = "".join(f'<si><t xml:space="preserve">{escape(t)}</t></si>' for t in self.order)
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="{MAIN}" '
                f'count="{self.uses}" uniqueCount="{len(self.order)}">{items}</sst>')


def _cell(ref: str, value, styles: _Styles, strings: _Strings, *, fmt: int, bold: bool) -> str:
    if isinstance(value, Cell):
        fmt = value.fmt if value.fmt is not None else fmt
        bold = value.bold or bold
        value = value.value
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return f'<c r="{ref}" s="{styles.index(PLAIN, True, False)}"/>' if bold else ""
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b" s="{styles.index(PLAIN, bold, False)}"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        number_format = INTEGER if fmt == DECIMAL and isinstance(value, int) else fmt
        return f'<c r="{ref}" s="{styles.index(number_format, bold, False)}"><v>{value!r}</v></c>'
    text = clean_text(value.isoformat() if isinstance(value, datetime) else str(value))
    style = styles.index(PLAIN, bold, text.startswith(FORMULA_LEAD))
    return f'<c r="{ref}" t="s" s="{style}"><v>{strings.id(text)}</v></c>'


def _sheet_xml(sheet: Sheet, styles: _Styles, strings: _Strings, selected: bool) -> str:
    width = max((len(r) for r in sheet.rows), default=1)
    rows = []
    for i, row in enumerate(sheet.rows):
        bold = i < sheet.header_rows
        cells = "".join(_cell(f"{column_letter(j)}{i + 1}", v, styles, strings, fmt=sheet.number_format, bold=bold)
                        for j, v in enumerate(row))
        rows.append(f'<row r="{i + 1}">{cells}</row>')
    last = f"{column_letter(width - 1)}{max(len(sheet.rows), 1)}"
    ys, xs = sheet.header_rows if sheet.rows else 0, sheet.freeze_cols
    if ys or xs:
        top_left = f"{column_letter(xs)}{ys + 1}"
        pane_name = "bottomRight" if ys and xs else "bottomLeft" if ys else "topRight"
        split = (f' xSplit="{xs}"' if xs else "") + (f' ySplit="{ys}"' if ys else "")
        pane = (f'<pane{split} topLeftCell="{top_left}" activePane="{pane_name}" state="frozen"/>'
                f'<selection pane="{pane_name}" activeCell="{top_left}" sqref="{top_left}"/>')
    else:
        pane = ""
    view = '<sheetView workbookViewId="0"' + (' tabSelected="1"' if selected else "") + f">{pane}</sheetView>"
    cols = "".join(f'<col min="{c + 1}" max="{c + 1}" width="{w:.1f}" customWidth="1"/>'
                   for c, w in sorted(sheet.widths.items()))
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{MAIN}" xmlns:r="{REL}">'
            f'<dimension ref="A1:{last}"/><sheetViews>{view}</sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'{f"<cols>{cols}</cols>" if cols else ""}<sheetData>{"".join(rows)}</sheetData></worksheet>')


def auto_widths(sheet: Sheet, *, minimum: float = 8, maximum: float = 60) -> Sheet:
    """Column widths from the longest text in each column, where none is set."""
    for row in sheet.rows:
        for j, v in enumerate(row):
            v = v.value if isinstance(v, Cell) else v
            if v is None:
                continue
            n = len(f"{v:,.2f}") if isinstance(v, float) else len(str(v))
            current = sheet.widths.get(j, minimum)
            sheet.widths[j] = min(maximum, max(current, n + 2))
    return sheet


def workbook(sheets: list[Sheet], *, title: str = "", created: datetime | None = None) -> bytes:
    """The ``.xlsx`` file's bytes."""
    if not sheets:
        raise ValueError("a workbook needs at least one sheet")
    created = created or datetime.now()
    names = sheet_names([s.name for s in sheets])
    styles, strings = _Styles(), _Strings()
    bodies = [_sheet_xml(s, styles, strings, i == 0) for i, s in enumerate(sheets)]
    n = len(sheets)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                  for i in range(n))
        + '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
    root_rels = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PKG}">'
        f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
        'core-properties" Target="docProps/core.xml"/>'
        f'<Relationship Id="rId3" Type="{REL}/extended-properties" Target="docProps/app.xml"/></Relationships>')
    book = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="{MAIN}" xmlns:r="{REL}">'
            '<bookViews><workbookView activeTab="0"/></bookViews><sheets>'
            + "".join(f'<sheet name={quoteattr(name)} sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                      for i, name in enumerate(names))
            + "</sheets></workbook>")
    book_rels = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PKG}">'
                 + "".join(f'<Relationship Id="rId{i + 1}" Type="{REL}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                           for i in range(n))
                 + f'<Relationship Id="rId{n + 1}" Type="{REL}/styles" Target="styles.xml"/>'
                 f'<Relationship Id="rId{n + 2}" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>'
                 "</Relationships>")
    stamp = created.replace(microsecond=0).isoformat() + "Z" if created.tzinfo is None else created.isoformat()
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(clean_text(title))}</dc:title><dc:creator>TradingAgents</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created></cp:coreProperties>')
    app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
           '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Application>TradingAgents</Application></Properties>')
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("xl/workbook.xml", book)
        z.writestr("xl/_rels/workbook.xml.rels", book_rels)
        for i, body in enumerate(bodies):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", body)
        z.writestr("xl/styles.xml", styles.xml())
        z.writestr("xl/sharedStrings.xml", strings.xml())
    return out.getvalue()
