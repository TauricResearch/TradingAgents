from __future__ import annotations

from io import (
    BytesIO,
    StringIO,
)
from lzma import LZMAError
import os
from tarfile import ReadError
from urllib.error import HTTPError
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import numpy as np
import pytest

from pandas.compat._optional import import_optional_dependency
from pandas.errors import (
    EmptyDataError,
    ParserError,
)
import pandas.util._test_decorators as td

import pandas as pd
from pandas import (
    NA,
    DataFrame,
    Series,
)
import pandas._testing as tm

from pandas.io.common import get_handle
from pandas.io.xml import read_xml

# CHECK LIST

# [x] - ValueError: "Values for parser can only be lxml or etree."

# etree
# [X] - ImportError: "lxml not found, please install or use the etree parser."
# [X] - TypeError: "expected str, bytes or os.PathLike object, not NoneType"
# [X] - ValueError: "Either element or attributes can be parsed not both."
# [X] - ValueError: "xpath does not return any nodes..."
# [X] - SyntaxError: "You have used an incorrect or unsupported XPath"
# [X] - ValueError: "names does not match length of child elements in xpath."
# [X] - TypeError: "...is not a valid type for names"
# [X] - ValueError: "To use stylesheet, you need lxml installed..."
# []  - URLError: (GENERAL ERROR WITH HTTPError AS SUBCLASS)
# [X] - HTTPError: "HTTP Error 404: Not Found"
# []  - OSError: (GENERAL ERROR WITH FileNotFoundError AS SUBCLASS)
# [X] - FileNotFoundError: "No such file or directory"
# []  - ParseError    (FAILSAFE CATCH ALL FOR VERY COMPLEX XML)
# [X] - UnicodeDecodeError: "'utf-8' codec can't decode byte 0xe9..."
# [X] - UnicodeError: "UTF-16 stream does not start with BOM"
# [X] - BadZipFile: "File is not a zip file"
# [X] - OSError: "Invalid data stream"
# [X] - LZMAError: "Input format not supported by decoder"
# [X] - ValueError: "Unrecognized compression type"
# [X] - PermissionError: "Forbidden"

# lxml
# [X] - ValueError: "Either element or attributes can be parsed not both."
# [X] - AttributeError: "__enter__"
# [X] - XSLTApplyError: "Cannot resolve URI"
# [X] - XSLTParseError: "document is not a stylesheet"
# [X] - ValueError: "xpath does not return any nodes."
# [X] - XPathEvalError: "Invalid expression"
# []  - XPathSyntaxError: (OLD VERSION IN lxml FOR XPATH ERRORS)
# [X] - TypeError: "empty namespace prefix is not supported in XPath"
# [X] - ValueError: "names does not match length of child elements in xpath."
# [X] - TypeError: "...is not a valid type for names"
# [X] - LookupError: "unknown encoding"
# []  - URLError: (USUALLY DUE TO NETWORKING)
# [X  - HTTPError: "HTTP Error 404: Not Found"
# [X] - OSError: "failed to load external entity"
# [X] - XMLSyntaxError: "Start tag expected, '<' not found"
# []  - ParserError: (FAILSAFE CATCH ALL FOR VERY COMPLEX XML
# [X] - ValueError: "Values for parser can only be lxml or etree."
# [X] - UnicodeDecodeError: "'utf-8' codec can't decode byte 0xe9..."
# [X] - UnicodeError: "UTF-16 stream does not start with BOM"
# [X] - BadZipFile: "File is not a zip file"
# [X] - OSError: "Invalid data stream"
# [X] - LZMAError: "Input format not supported by decoder"
# [X] - ValueError: "Unrecognized compression type"
# [X] - PermissionError: "Forbidden"

geom_df = DataFrame(
    {
        "shape": ["square", "circle", "triangle"],
        "degrees": [360, 360, 180],
        "sides": [4, np.nan, 3],
    }
)

xml_default_nmsp = """\
<?xml version='1.0' encoding='utf-8'?>
<data xmlns="http://example.com">
  <row>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4</sides>
  </row>
  <row>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3</sides>
  </row>
</data>"""

xml_prefix_nmsp = """\
<?xml version='1.0' encoding='utf-8'?>
<doc:data xmlns:doc="http://example.com">
  <doc:row>
    <doc:shape>square</doc:shape>
    <doc:degrees>360</doc:degrees>
    <doc:sides>4.0</doc:sides>
  </doc:row>
  <doc:row>
    <doc:shape>circle</doc:shape>
    <doc:degrees>360</doc:degrees>
    <doc:sides/>
  </doc:row>
  <doc:row>
    <doc:shape>triangle</doc:shape>
    <doc:degrees>180</doc:degrees>
    <doc:sides>3.0</doc:sides>
  </doc:row>
</doc:data>"""


df_kml = DataFrame(
    {
        "id": {
            0: "ID_00001",
            1: "ID_00002",
            2: "ID_00003",
            3: "ID_00004",
            4: "ID_00005",
        },
        "name": {
            0: "Blue Line (Forest Park)",
            1: "Red, Purple Line",
            2: "Red, Purple Line",
            3: "Red, Purple Line",
            4: "Red, Purple Line",
        },
        "styleUrl": {
            0: "#LineStyle01",
            1: "#LineStyle01",
            2: "#LineStyle01",
            3: "#LineStyle01",
            4: "#LineStyle01",
        },
        "extrude": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
        "altitudeMode": {
            0: "clampedToGround",
            1: "clampedToGround",
            2: "clampedToGround",
            3: "clampedToGround",
            4: "clampedToGround",
        },
        "coordinates": {
            0: (
                "-87.77678526964958,41.8708863930319,0 "
                "-87.77826234150609,41.87097820122218,0 "
                "-87.78251583439344,41.87130129991005,0 "
                "-87.78418294588424,41.87145055520308,0 "
                "-87.7872369165933,41.8717239119163,0 "
                "-87.79160214925886,41.87210797280065,0"
            ),
            1: (
                "-87.65758750947528,41.96427269188822,0 "
                "-87.65802133507393,41.96581929055245,0 "
                "-87.65819033925305,41.96621846093642,0 "
                "-87.6583189819129,41.96650362897086,0 "
                "-87.65835858701473,41.96669002089185,0 "
                "-87.65838428411853,41.96688150295095,0 "
                "-87.65842208882658,41.96745896091846,0 "
                "-87.65846556843937,41.9683761425439,0 "
                "-87.65849296214573,41.96913893870342,0"
            ),
            2: (
                "-87.65492939166126,41.95377494531437,0 "
                "-87.65557043199591,41.95376544118533,0 "
                "-87.65606302030132,41.95376391658746,0 "
                "-87.65623502146268,41.95377379126367,0 "
                "-87.65634748981634,41.95380103566435,0 "
                "-87.65646537904269,41.95387703994676,0 "
                "-87.65656532461145,41.95396622645799,0 "
                "-87.65664760856414,41.95404201996044,0 "
                "-87.65671750555913,41.95416647054043,0 "
                "-87.65673983607117,41.95429949810849,0 "
                "-87.65673866475777,41.95441024240925,0 "
                "-87.6567690255541,41.95490657227902,0 "
                "-87.65683672482363,41.95692259283837,0 "
                "-87.6568900886376,41.95861070983142,0 "
                "-87.65699865558875,41.96181418669004,0 "
                "-87.65756347177603,41.96397045777844,0 "
                "-87.65758750947528,41.96427269188822,0"
            ),
            3: (
                "-87.65362593118043,41.94742799535678,0 "
                "-87.65363554415794,41.94819886386848,0 "
                "-87.6536456393239,41.95059994675451,0 "
                "-87.65365831235026,41.95108288489359,0 "
                "-87.6536604873874,41.9519954657554,0 "
                "-87.65362592053201,41.95245597302328,0 "
                "-87.65367158496069,41.95311153649393,0 "
                "-87.65368468595476,41.9533202828916,0 "
                "-87.65369271253692,41.95343095587119,0 "
                "-87.65373335834569,41.95351536301472,0 "
                "-87.65378605844126,41.95358212680591,0 "
                "-87.65385067928185,41.95364452823767,0 "
                "-87.6539390793817,41.95370263886964,0 "
                "-87.6540786298351,41.95373403675265,0 "
                "-87.65430648647626,41.9537535411832,0 "
                "-87.65492939166126,41.95377494531437,0"
            ),
            4: (
                "-87.65345391792157,41.94217681262115,0 "
                "-87.65342448305786,41.94237224420864,0 "
                "-87.65339745703922,41.94268217746244,0 "
                "-87.65337753982941,41.94288140770284,0 "
                "-87.65336256753105,41.94317369618263,0 "
                "-87.65338799707138,41.94357253961736,0 "
                "-87.65340240886648,41.94389158188269,0 "
                "-87.65341837392448,41.94406444407721,0 "
                "-87.65342275247338,41.94421065714904,0 "
                "-87.65347469646018,41.94434829382345,0 "
                "-87.65351486483024,41.94447699917548,0 "
                "-87.65353483605053,41.9453896864472,0 "
                "-87.65361975532807,41.94689193720703,0 "
                "-87.65362593118043,41.94742799535678,0"
            ),
        },
    }
)


def test_literal_xml_deprecation():
    # GH 53809
    pytest.importorskip("lxml")
    msg = (
        "Passing literal xml to 'read_xml' is deprecated and "
        "will be removed in a future version. To read from a "
        "literal string, wrap it in a 'StringIO' object."
    )

    with tm.assert_produces_warning(FutureWarning, match=msg):
        read_xml(xml_default_nmsp)


@pytest.fixture(params=["rb", "r"])
def mode(request):
    return request.param


@pytest.fixture(params=[pytest.param("lxml", marks=td.skip_if_no("lxml")), "etree"])
def parser(request):
    return request.param


def read_xml_iterparse(data, **kwargs):
    with tm.ensure_clean() as path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        return read_xml(path, **kwargs)


def read_xml_iterparse_comp(comp_path, compression_only, **kwargs):
    with get_handle(comp_path, "r", compression=compression_only) as handles:
        with tm.ensure_clean() as path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(handles.handle.read())
            return read_xml(path, **kwargs)


# FILE / URL


def test_parser_consistency_file(xml_books):
    pytest.importorskip("lxml")
    df_file_lxml = read_xml(xml_books, parser="lxml")
    df_file_etree = read_xml(xml_books, parser="etree")

    df_iter_lxml = read_xml(
        xml_books,
        parser="lxml",
        iterparse={"book": ["category", "title", "year", "author", "price"]},
    )
    df_iter_etree = read_xml(
        xml_books,
        parser="etree",
        iterparse={"book": ["category", "title", "year", "author", "price"]},
    )

    tm.assert_frame_equal(df_file_lxml, df_file_etree)
    tm.assert_frame_equal(df_file_lxml, df_iter_lxml)
    tm.assert_frame_equal(df_iter_lxml, df_iter_etree)


@pytest.mark.network
@pytest.mark.single_cpu
def test_parser_consistency_url(parser, httpserver):
    httpserver.serve_content(content=xml_default_nmsp)

    df_xpath = read_xml(StringIO(xml_default_nmsp), parser=parser)
    df_iter = read_xml(
        BytesIO(xml_default_nmsp.encode()),
        parser=parser,
        iterparse={"row": ["shape", "degrees", "sides"]},
    )

    tm.assert_frame_equal(df_xpath, df_iter)


def test_file_like(xml_books, parser, mode):
    with open(xml_books, mode, encoding="utf-8" if mode == "r" else None) as f:
        df_file = read_xml(f, parser=parser)

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_file, df_expected)


def test_file_io(xml_books, parser, mode):
    with open(xml_books, mode, encoding="utf-8" if mode == "r" else None) as f:
        xml_obj = f.read()

    df_io = read_xml(
        (BytesIO(xml_obj) if isinstance(xml_obj, bytes) else StringIO(xml_obj)),
        parser=parser,
    )

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_io, df_expected)


def test_file_buffered_reader_string(xml_books, parser, mode):
    with open(xml_books, mode, encoding="utf-8" if mode == "r" else None) as f:
        xml_obj = f.read()

    if mode == "rb":
        xml_obj = StringIO(xml_obj.decode())
    elif mode == "r":
        xml_obj = StringIO(xml_obj)

    df_str = read_xml(xml_obj, parser=parser)

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_str, df_expected)


def test_file_buffered_reader_no_xml_declaration(xml_books, parser, mode):
    with open(xml_books, mode, encoding="utf-8" if mode == "r" else None) as f:
        next(f)
        xml_obj = f.read()

    if mode == "rb":
        xml_obj = StringIO(xml_obj.decode())
    elif mode == "r":
        xml_obj = StringIO(xml_obj)

    df_str = read_xml(xml_obj, parser=parser)

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_str, df_expected)


def test_string_charset(parser):
    txt = "<中文標籤><row><c1>1</c1><c2>2</c2></row></中文標籤>"

    df_str = read_xml(StringIO(txt), parser=parser)

    df_expected = DataFrame({"c1": 1, "c2": 2}, index=[0])

    tm.assert_frame_equal(df_str, df_expected)


def test_file_charset(xml_doc_ch_utf, parser):
    df_file = read_xml(xml_doc_ch_utf, parser=parser)

    df_expected = DataFrame(
        {
            "問": [
                "問  若箇是邪而言破邪 何者是正而道(Sorry, this is Big5 only)申正",
                "問 既破有得申無得 亦應但破性執申假名以不",
                "問 既破性申假 亦應但破有申無 若有無兩洗 亦應性假雙破耶",
            ],
            "答": [
                "".join(
                    [
                        "答  邪既無量 正亦多途  大略為言不出二種 謂",
                        "有得與無得 有得是邪須破 無得是正須申\n\t\t故",
                    ]
                ),
                None,
                "答  不例  有無皆是性 所以須雙破 既分性假異 故有破不破",
            ],
            "a": [
                None,
                "答 性執是有得 假名是無得  今破有得申無得 即是破性執申假名也",
                None,
            ],
        }
    )

    tm.assert_frame_equal(df_file, df_expected)


def test_file_handle_close(xml_books, parser):
    with open(xml_books, "rb") as f:
        read_xml(BytesIO(f.read()), parser=parser)

        assert not f.closed


@pytest.mark.parametrize("val", ["", b""])
def test_empty_string_lxml(val):
    lxml_etree = pytest.importorskip("lxml.etree")

    msg = "|".join(
        [
            "Document is empty",
            # Seen on Mac with lxml 4.91
            r"None \(line 0\)",
        ]
    )
    with pytest.raises(lxml_etree.XMLSyntaxError, match=msg):
        if isinstance(val, str):
            read_xml(StringIO(val), parser="lxml")
        else:
            read_xml(BytesIO(val), parser="lxml")


@pytest.mark.parametrize("val", ["", b""])
def test_empty_string_etree(val):
    with pytest.raises(ParseError, match="no element found"):
        if isinstance(val, str):
            read_xml(StringIO(val), parser="etree")
        else:
            read_xml(BytesIO(val), parser="etree")


def test_wrong_file_path(parser):
    msg = (
        "Passing literal xml to 'read_xml' is deprecated and "
        "will be removed in a future version. To read from a "
        "literal string, wrap it in a 'StringIO' object."
    )
    filename = os.path.join("data", "html", "books.xml")

    with pytest.raises(
        FutureWarning,
        match=msg,
    ):
        read_xml(filename, parser=parser)


@pytest.mark.network
@pytest.mark.single_cpu
def test_url(httpserver, xml_file):
    pytest.importorskip("lxml")
    with open(xml_file, encoding="utf-8") as f:
        httpserver.serve_content(content=f.read())
        df_url = read_xml(httpserver.url, xpath=".//book[count(*)=4]")

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_url, df_expected)


@pytest.mark.network
@pytest.mark.single_cpu
def test_wrong_url(parser, httpserver):
    httpserver.serve_content("NOT FOUND", code=404)
    with pytest.raises(HTTPError, match=("HTTP Error 404: NOT FOUND")):
        read_xml(httpserver.url, xpath=".//book[count(*)=4]", parser=parser)


# CONTENT


def test_whitespace(parser):
    xml = """
      <data>
        <row sides=" 4 ">
          <shape>
              square
          </shape>
          <degrees>&#009;360&#009;</degrees>
        </row>
        <row sides=" 0 ">
          <shape>
              circle
          </shape>
          <degrees>&#009;360&#009;</degrees>
        </row>
        <row sides=" 3 ">
          <shape>
              triangle
          </shape>
          <degrees>&#009;180&#009;</degrees>
        </row>
      </data>"""

    df_xpath = read_xml(StringIO(xml), parser=parser, dtype="string")

    df_iter = read_xml_iterparse(
        xml,
        parser=parser,
        iterparse={"row": ["sides", "shape", "degrees"]},
        dtype="string",
    )

    df_expected = DataFrame(
        {
            "sides": [" 4 ", " 0 ", " 3 "],
            "shape": [
                "\n              square\n          ",
                "\n              circle\n          ",
                "\n              triangle\n          ",
            ],
            "degrees": ["\t360\t", "\t360\t", "\t180\t"],
        },
        dtype="string",
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


# XPATH


def test_empty_xpath_lxml(xml_books):
    pytest.importorskip("lxml")
    with pytest.raises(ValueError, match=("xpath does not return any nodes")):
        read_xml(xml_books, xpath=".//python", parser="lxml")


def test_bad_xpath_etree(xml_books):
    with pytest.raises(
        SyntaxError, match=("You have used an incorrect or unsupported XPath")
    ):
        read_xml(xml_books, xpath=".//[book]", parser="etree")


def test_bad_xpath_lxml(xml_books):
    lxml_etree = pytest.importorskip("lxml.etree")

    with pytest.raises(lxml_etree.XPathEvalError, match=("Invalid expression")):
        read_xml(xml_books, xpath=".//[book]", parser="lxml")


# NAMESPACE


def test_default_namespace(parser):
    df_nmsp = read_xml(
        StringIO(xml_default_nmsp),
        xpath=".//ns:row",
        namespaces={"ns": "http://example.com"},
        parser=parser,
    )

    df_iter = read_xml_iterparse(
        xml_default_nmsp,
        parser=parser,
        iterparse={"row": ["shape", "degrees", "sides"]},
    )

    df_expected = DataFrame(
        {
            "shape": ["square", "circle", "triangle"],
            "degrees": [360, 360, 180],
            "sides": [4.0, float("nan"), 3.0],
        }
    )

    tm.assert_frame_equal(df_nmsp, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_prefix_namespace(parser):
    df_nmsp = read_xml(
        StringIO(xml_prefix_nmsp),
        xpath=".//doc:row",
        namespaces={"doc": "http://example.com"},
        parser=parser,
    )
    df_iter = read_xml_iterparse(
        xml_prefix_nmsp, parser=parser, iterparse={"row": ["shape", "degrees", "sides"]}
    )

    df_expected = DataFrame(
        {
            "shape": ["square", "circle", "triangle"],
            "degrees": [360, 360, 180],
            "sides": [4.0, float("nan"), 3.0],
        }
    )

    tm.assert_frame_equal(df_nmsp, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_consistency_default_namespace():
    pytest.importorskip("lxml")
    df_lxml = read_xml(
        StringIO(xml_default_nmsp),
        xpath=".//ns:row",
        namespaces={"ns": "http://example.com"},
        parser="lxml",
    )

    df_etree = read_xml(
        StringIO(xml_default_nmsp),
        xpath=".//doc:row",
        namespaces={"doc": "http://example.com"},
        parser="etree",
    )

    tm.assert_frame_equal(df_lxml, df_etree)


def test_consistency_prefix_namespace():
    pytest.importorskip("lxml")
    df_lxml = read_xml(
        StringIO(xml_prefix_nmsp),
        xpath=".//doc:row",
        namespaces={"doc": "http://example.com"},
        parser="lxml",
    )

    df_etree = read_xml(
        StringIO(xml_prefix_nmsp),
        xpath=".//doc:row",
        namespaces={"doc": "http://example.com"},
        parser="etree",
    )

    tm.assert_frame_equal(df_lxml, df_etree)


# PREFIX


def test_missing_prefix_with_default_namespace(xml_books, parser):
    with pytest.raises(ValueError, match=("xpath does not return any nodes")):
        read_xml(xml_books, xpath=".//Placemark", parser=parser)


def test_missing_prefix_definition_etree(kml_cta_rail_lines):
    with pytest.raises(SyntaxError, match=("you used an undeclared namespace prefix")):
        read_xml(kml_cta_rail_lines, xpath=".//kml:Placemark", parser="etree")


def test_missing_prefix_definition_lxml(kml_cta_rail_lines):
    lxml_etree = pytest.importorskip("lxml.etree")

    with pytest.raises(lxml_etree.XPathEvalError, match=("Undefined namespace prefix")):
        read_xml(kml_cta_rail_lines, xpath=".//kml:Placemark", parser="lxml")


@pytest.mark.parametrize("key", ["", None])
def test_none_namespace_prefix(key):
    pytest.importorskip("lxml")
    with pytest.raises(
        TypeError, match=("empty namespace prefix is not supported in XPath")
    ):
        read_xml(
            StringIO(xml_default_nmsp),
            xpath=".//kml:Placemark",
            namespaces={key: "http://www.opengis.net/kml/2.2"},
            parser="lxml",
        )


# ELEMS AND ATTRS


def test_file_elems_and_attrs(xml_books, parser):
    df_file = read_xml(xml_books, parser=parser)
    df_iter = read_xml(
        xml_books,
        parser=parser,
        iterparse={"book": ["category", "title", "author", "year", "price"]},
    )
    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_file, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_file_only_attrs(xml_books, parser):
    df_file = read_xml(xml_books, attrs_only=True, parser=parser)
    df_iter = read_xml(xml_books, parser=parser, iterparse={"book": ["category"]})
    df_expected = DataFrame({"category": ["cooking", "children", "web"]})

    tm.assert_frame_equal(df_file, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_file_only_elems(xml_books, parser):
    df_file = read_xml(xml_books, elems_only=True, parser=parser)
    df_iter = read_xml(
        xml_books,
        parser=parser,
        iterparse={"book": ["title", "author", "year", "price"]},
    )
    df_expected = DataFrame(
        {
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_file, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_elem_and_attrs_only(kml_cta_rail_lines, parser):
    with pytest.raises(
        ValueError,
        match=("Either element or attributes can be parsed not both"),
    ):
        read_xml(kml_cta_rail_lines, elems_only=True, attrs_only=True, parser=parser)


def test_empty_attrs_only(parser):
    xml = """
      <data>
        <row>
          <shape sides="4">square</shape>
          <degrees>360</degrees>
        </row>
        <row>
          <shape sides="0">circle</shape>
          <degrees>360</degrees>
        </row>
        <row>
          <shape sides="3">triangle</shape>
          <degrees>180</degrees>
        </row>
      </data>"""

    with pytest.raises(
        ValueError,
        match=("xpath does not return any nodes or attributes"),
    ):
        read_xml(StringIO(xml), xpath="./row", attrs_only=True, parser=parser)


def test_empty_elems_only(parser):
    xml = """
      <data>
        <row sides="4" shape="square" degrees="360"/>
        <row sides="0" shape="circle" degrees="360"/>
        <row sides="3" shape="triangle" degrees="180"/>
      </data>"""

    with pytest.raises(
        ValueError,
        match=("xpath does not return any nodes or attributes"),
    ):
        read_xml(StringIO(xml), xpath="./row", elems_only=True, parser=parser)


def test_attribute_centric_xml():
    pytest.importorskip("lxml")
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<TrainSchedule>
      <Stations>
         <station Name="Manhattan" coords="31,460,195,498"/>
         <station Name="Laraway Road" coords="63,409,194,455"/>
         <station Name="179th St (Orland Park)" coords="0,364,110,395"/>
         <station Name="153rd St (Orland Park)" coords="7,333,113,362"/>
         <station Name="143rd St (Orland Park)" coords="17,297,115,330"/>
         <station Name="Palos Park" coords="128,281,239,303"/>
         <station Name="Palos Heights" coords="148,257,283,279"/>
         <station Name="Worth" coords="170,230,248,255"/>
         <station Name="Chicago Ridge" coords="70,187,208,214"/>
         <station Name="Oak Lawn" coords="166,159,266,185"/>
         <station Name="Ashburn" coords="197,133,336,157"/>
         <station Name="Wrightwood" coords="219,106,340,133"/>
         <station Name="Chicago Union Sta" coords="220,0,360,43"/>
      </Stations>
</TrainSchedule>"""

    df_lxml = read_xml(StringIO(xml), xpath=".//station")
    df_etree = read_xml(StringIO(xml), xpath=".//station", parser="etree")

    df_iter_lx = read_xml_iterparse(xml, iterparse={"station": ["Name", "coords"]})
    df_iter_et = read_xml_iterparse(
        xml, parser="etree", iterparse={"station": ["Name", "coords"]}
    )

    tm.assert_frame_equal(df_lxml, df_etree)
    tm.assert_frame_equal(df_iter_lx, df_iter_et)


# NAMES


def test_names_option_output(xml_books, parser):
    df_file = read_xml(
        xml_books, names=["Col1", "Col2", "Col3", "Col4", "Col5"], parser=parser
    )
    df_iter = read_xml(
        xml_books,
        parser=parser,
        names=["Col1", "Col2", "Col3", "Col4", "Col5"],
        iterparse={"book": ["category", "title", "author", "year", "price"]},
    )

    df_expected = DataFrame(
        {
            "Col1": ["cooking", "children", "web"],
            "Col2": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "Col3": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "Col4": [2005, 2005, 2003],
            "Col5": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_file, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_repeat_names(parser):
    xml = """\
<shapes>
  <shape type="2D">
    <name>circle</name>
    <type>curved</type>
  </shape>
  <shape type="3D">
    <name>sphere</name>
    <type>curved</type>
  </shape>
</shapes>"""
    df_xpath = read_xml(
        StringIO(xml),
        xpath=".//shape",
        parser=parser,
        names=["type_dim", "shape", "type_edge"],
    )

    df_iter = read_xml_iterparse(
        xml,
        parser=parser,
        iterparse={"shape": ["type", "name", "type"]},
        names=["type_dim", "shape", "type_edge"],
    )

    df_expected = DataFrame(
        {
            "type_dim": ["2D", "3D"],
            "shape": ["circle", "sphere"],
            "type_edge": ["curved", "curved"],
        }
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_repeat_values_new_names(parser):
    xml = """\
<shapes>
  <shape>
    <name>rectangle</name>
    <family>rectangle</family>
  </shape>
  <shape>
    <name>square</name>
    <family>rectangle</family>
  </shape>
  <shape>
    <name>ellipse</name>
    <family>ellipse</family>
  </shape>
  <shape>
    <name>circle</name>
    <family>ellipse</family>
  </shape>
</shapes>"""
    df_xpath = read_xml(
        StringIO(xml), xpath=".//shape", parser=parser, names=["name", "group"]
    )

    df_iter = read_xml_iterparse(
        xml,
        parser=parser,
        iterparse={"shape": ["name", "family"]},
        names=["name", "group"],
    )

    df_expected = DataFrame(
        {
            "name": ["rectangle", "square", "ellipse", "circle"],
            "group": ["rectangle", "rectangle", "ellipse", "ellipse"],
        }
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_repeat_elements(parser):
    xml = """\
<shapes>
  <shape>
    <value item="name">circle</value>
    <value item="family">ellipse</value>
    <value item="degrees">360</value>
    <value item="sides">0</value>
  </shape>
  <shape>
    <value item="name">triangle</value>
    <value item="family">polygon</value>
    <value item="degrees">180</value>
    <value item="sides">3</value>
  </shape>
  <shape>
    <value item="name">square</value>
    <value item="family">polygon</value>
    <value item="degrees">360</value>
    <value item="sides">4</value>
  </shape>
</shapes>"""
    df_xpath = read_xml(
        StringIO(xml),
        xpath=".//shape",
        parser=parser,
        names=["name", "family", "degrees", "sides"],
    )

    df_iter = read_xml_iterparse(
        xml,
        parser=parser,
        iterparse={"shape": ["value", "value", "value", "value"]},
        names=["name", "family", "degrees", "sides"],
    )

    df_expected = DataFrame(
        {
            "name": ["circle", "triangle", "square"],
            "family": ["ellipse", "polygon", "polygon"],
            "degrees": [360, 180, 360],
            "sides": [0, 3, 4],
        }
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_names_option_wrong_length(xml_books, parser):
    with pytest.raises(ValueError, match=("names does not match length")):
        read_xml(xml_books, names=["Col1", "Col2", "Col3"], parser=parser)


def test_names_option_wrong_type(xml_books, parser):
    with pytest.raises(TypeError, match=("is not a valid type for names")):
        read_xml(xml_books, names="Col1, Col2, Col3", parser=parser)


# ENCODING


def test_wrong_encoding(xml_baby_names, parser):
    with pytest.raises(UnicodeDecodeError, match=("'utf-8' codec can't decode")):
        read_xml(xml_baby_names, parser=parser)


def test_utf16_encoding(xml_baby_names, parser):
    with pytest.raises(
        UnicodeError,
        match=(
            "UTF-16 stream does not start with BOM|"
            "'utf-16(-le)?' codec can't decode byte"
        ),
    ):
        read_xml(xml_baby_names, encoding="UTF-16", parser=parser)


def test_unknown_encoding(xml_baby_names, parser):
    with pytest.raises(LookupError, match=("unknown encoding: UFT-8")):
        read_xml(xml_baby_names, encoding="UFT-8", parser=parser)


def test_ascii_encoding(xml_baby_names, parser):
    with pytest.raises(UnicodeDecodeError, match=("'ascii' codec can't decode byte")):
        read_xml(xml_baby_names, encoding="ascii", parser=parser)


def test_parser_consistency_with_encoding(xml_baby_names):
    pytest.importorskip("lxml")
    df_xpath_lxml = read_xml(xml_baby_names, parser="lxml", encoding="ISO-8859-1")
    df_xpath_etree = read_xml(xml_baby_names, parser="etree", encoding="iso-8859-1")

    df_iter_lxml = read_xml(
        xml_baby_names,
        parser="lxml",
        encoding="ISO-8859-1",
        iterparse={"row": ["rank", "malename", "femalename"]},
    )
    df_iter_etree = read_xml(
        xml_baby_names,
        parser="etree",
        encoding="ISO-8859-1",
        iterparse={"row": ["rank", "malename", "femalename"]},
    )

    tm.assert_frame_equal(df_xpath_lxml, df_xpath_etree)
    tm.assert_frame_equal(df_xpath_etree, df_iter_etree)
    tm.assert_frame_equal(df_iter_lxml, df_iter_etree)


def test_wrong_encoding_for_lxml():
    pytest.importorskip("lxml")
    # GH#45133
    data = """<data>
  <row>
    <a>c</a>
  </row>
</data>
"""
    with pytest.raises(TypeError, match="encoding None"):
        read_xml(StringIO(data), parser="lxml", encoding=None)


def test_none_encoding_etree():
    # GH#45133
    data = """<data>
  <row>
    <a>c</a>
  </row>
</data>
"""
    result = read_xml(StringIO(data), parser="etree", encoding=None)
    expected = DataFrame({"a": ["c"]})
    tm.assert_frame_equal(result, expected)


# PARSER


@td.skip_if_installed("lxml")
def test_default_parser_no_lxml(xml_books):
    with pytest.raises(
        ImportError, match=("lxml not found, please install or use the etree parser.")
    ):
        read_xml(xml_books)


def test_wrong_parser(xml_books):
    with pytest.raises(
        ValueError, match=("Values for parser can only be lxml or etree.")
    ):
        read_xml(xml_books, parser="bs4")


# STYLESHEET


def test_stylesheet_file(kml_cta_rail_lines, xsl_flatten_doc):
    pytest.importorskip("lxml")
    df_style = read_xml(
        kml_cta_rail_lines,
        xpath=".//k:Placemark",
        namespaces={"k": "http://www.opengis.net/kml/2.2"},
        stylesheet=xsl_flatten_doc,
    )

    df_iter = read_xml(
        kml_cta_rail_lines,
        iterparse={
            "Placemark": [
                "id",
                "name",
                "styleUrl",
                "extrude",
                "altitudeMode",
                "coordinates",
            ]
        },
    )

    tm.assert_frame_equal(df_kml, df_style)
    tm.assert_frame_equal(df_kml, df_iter)


def test_stylesheet_file_like(kml_cta_rail_lines, xsl_flatten_doc, mode):
    pytest.importorskip("lxml")
    with open(xsl_flatten_doc, mode, encoding="utf-8" if mode == "r" else None) as f:
        df_style = read_xml(
            kml_cta_rail_lines,
            xpath=".//k:Placemark",
            namespaces={"k": "http://www.opengis.net/kml/2.2"},
            stylesheet=f,
        )

    tm.assert_frame_equal(df_kml, df_style)


def test_stylesheet_io(kml_cta_rail_lines, xsl_flatten_doc, mode):
    # note: By default the bodies of untyped functions are not checked,
    # consider using --check-untyped-defs
    pytest.importorskip("lxml")
    xsl_obj: BytesIO | StringIO  # type: ignore[annotation-unchecked]

    with open(xsl_flatten_doc, mode, encoding="utf-8" if mode == "r" else None) as f:
        if mode == "rb":
            xsl_obj = BytesIO(f.read())
        else:
            xsl_obj = StringIO(f.read())

    df_style = read_xml(
        kml_cta_rail_lines,
        xpath=".//k:Placemark",
        namespaces={"k": "http://www.opengis.net/kml/2.2"},
        stylesheet=xsl_obj,
    )

    tm.assert_frame_equal(df_kml, df_style)


def test_stylesheet_buffered_reader(kml_cta_rail_lines, xsl_flatten_doc, mode):
    pytest.importorskip("lxml")
    with open(xsl_flatten_doc, mode, encoding="utf-8" if mode == "r" else None) as f:
        xsl_obj = f.read()

    df_style = read_xml(
        kml_cta_rail_lines,
        xpath=".//k:Placemark",
        namespaces={"k": "http://www.opengis.net/kml/2.2"},
        stylesheet=xsl_obj,
    )

    tm.assert_frame_equal(df_kml, df_style)


def test_style_charset():
    pytest.importorskip("lxml")
    xml = "<中文標籤><row><c1>1</c1><c2>2</c2></row></中文標籤>"

    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
 <xsl:output omit-xml-declaration="yes" indent="yes"/>
 <xsl:strip-space elements="*"/>

 <xsl:template match="node()|@*">
     <xsl:copy>
       <xsl:apply-templates select="node()|@*"/>
     </xsl:copy>
 </xsl:template>

 <xsl:template match="中文標籤">
     <根>
       <xsl:apply-templates />
     </根>
 </xsl:template>

</xsl:stylesheet>"""

    df_orig = read_xml(StringIO(xml))
    df_style = read_xml(StringIO(xml), stylesheet=xsl)

    tm.assert_frame_equal(df_orig, df_style)


def test_not_stylesheet(kml_cta_rail_lines, xml_books):
    lxml_etree = pytest.importorskip("lxml.etree")

    with pytest.raises(
        lxml_etree.XSLTParseError, match=("document is not a stylesheet")
    ):
        read_xml(kml_cta_rail_lines, stylesheet=xml_books)


def test_incorrect_xsl_syntax(kml_cta_rail_lines):
    lxml_etree = pytest.importorskip("lxml.etree")

    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                              xmlns:k="http://www.opengis.net/kml/2.2"/>
    <xsl:output method="xml" omit-xml-declaration="yes"
                cdata-section-elements="k:description" indent="yes"/>
    <xsl:strip-space elements="*"/>

    <xsl:template match="node()|@*">
     <xsl:copy>
       <xsl:apply-templates select="node()|@*"/>
     </xsl:copy>
    </xsl:template>

    <xsl:template match="k:MultiGeometry|k:LineString">
        <xsl:apply-templates select='*'/>
    </xsl:template>

    <xsl:template match="k:description|k:Snippet|k:Style"/>
</xsl:stylesheet>"""

    with pytest.raises(
        lxml_etree.XMLSyntaxError, match=("Extra content at the end of the document")
    ):
        read_xml(kml_cta_rail_lines, stylesheet=xsl)


def test_incorrect_xsl_eval(kml_cta_rail_lines):
    lxml_etree = pytest.importorskip("lxml.etree")

    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                              xmlns:k="http://www.opengis.net/kml/2.2">
    <xsl:output method="xml" omit-xml-declaration="yes"
                cdata-section-elements="k:description" indent="yes"/>
    <xsl:strip-space elements="*"/>

    <xsl:template match="node(*)|@*">
     <xsl:copy>
       <xsl:apply-templates select="node()|@*"/>
     </xsl:copy>
    </xsl:template>

    <xsl:template match="k:MultiGeometry|k:LineString">
        <xsl:apply-templates select='*'/>
    </xsl:template>

    <xsl:template match="k:description|k:Snippet|k:Style"/>
</xsl:stylesheet>"""

    with pytest.raises(lxml_etree.XSLTParseError, match=("failed to compile")):
        read_xml(kml_cta_rail_lines, stylesheet=xsl)


def test_incorrect_xsl_apply(kml_cta_rail_lines):
    lxml_etree = pytest.importorskip("lxml.etree")

    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" encoding="utf-8" indent="yes" />
    <xsl:strip-space elements="*"/>

    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:copy-of select="document('non_existent.xml')/*"/>
        </xsl:copy>
    </xsl:template>
</xsl:stylesheet>"""

    with pytest.raises(lxml_etree.XSLTApplyError, match=("Cannot resolve URI")):
        read_xml(kml_cta_rail_lines, stylesheet=xsl)


def test_wrong_stylesheet(kml_cta_rail_lines, xml_data_path):
    xml_etree = pytest.importorskip("lxml.etree")

    xsl = xml_data_path / "flatten.xsl"

    with pytest.raises(
        xml_etree.XMLSyntaxError,
        match=("Start tag expected, '<' not found"),
    ):
        read_xml(kml_cta_rail_lines, stylesheet=xsl)


def test_stylesheet_file_close(kml_cta_rail_lines, xsl_flatten_doc, mode):
    # note: By default the bodies of untyped functions are not checked,
    # consider using --check-untyped-defs
    pytest.importorskip("lxml")
    xsl_obj: BytesIO | StringIO  # type: ignore[annotation-unchecked]

    with open(xsl_flatten_doc, mode, encoding="utf-8" if mode == "r" else None) as f:
        if mode == "rb":
            xsl_obj = BytesIO(f.read())
        else:
            xsl_obj = StringIO(f.read())

        read_xml(kml_cta_rail_lines, stylesheet=xsl_obj)

        assert not f.closed


def test_stylesheet_with_etree(kml_cta_rail_lines, xsl_flatten_doc):
    pytest.importorskip("lxml")
    with pytest.raises(
        ValueError, match=("To use stylesheet, you need lxml installed")
    ):
        read_xml(kml_cta_rail_lines, parser="etree", stylesheet=xsl_flatten_doc)


@pytest.mark.parametrize("val", ["", b""])
def test_empty_stylesheet(val):
    pytest.importorskip("lxml")
    msg = (
        "Passing literal xml to 'read_xml' is deprecated and "
        "will be removed in a future version. To read from a "
        "literal string, wrap it in a 'StringIO' object."
    )
    kml = os.path.join("data", "xml", "cta_rail_lines.kml")

    with pytest.raises(FutureWarning, match=msg):
        read_xml(kml, stylesheet=val)


# ITERPARSE
def test_file_like_iterparse(xml_books, parser, mode):
    with open(xml_books, mode, encoding="utf-8" if mode == "r" else None) as f:
        if mode == "r" and parser == "lxml":
            with pytest.raises(
                TypeError, match=("reading file objects must return bytes objects")
            ):
                read_xml(
                    f,
                    parser=parser,
                    iterparse={
                        "book": ["category", "title", "year", "author", "price"]
                    },
                )
            return None
        else:
            df_filelike = read_xml(
                f,
                parser=parser,
                iterparse={"book": ["category", "title", "year", "author", "price"]},
            )

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_filelike, df_expected)


def test_file_io_iterparse(xml_books, parser, mode):
    funcIO = StringIO if mode == "r" else BytesIO
    with open(
        xml_books,
        mode,
        encoding="utf-8" if mode == "r" else None,
    ) as f:
        with funcIO(f.read()) as b:
            if mode == "r" and parser == "lxml":
                with pytest.raises(
                    TypeError, match=("reading file objects must return bytes objects")
                ):
                    read_xml(
                        b,
                        parser=parser,
                        iterparse={
                            "book": ["category", "title", "year", "author", "price"]
                        },
                    )
                return None
            else:
                df_fileio = read_xml(
                    b,
                    parser=parser,
                    iterparse={
                        "book": ["category", "title", "year", "author", "price"]
                    },
                )

    df_expected = DataFrame(
        {
            "category": ["cooking", "children", "web"],
            "title": ["Everyday Italian", "Harry Potter", "Learning XML"],
            "author": ["Giada De Laurentiis", "J K. Rowling", "Erik T. Ray"],
            "year": [2005, 2005, 2003],
            "price": [30.00, 29.99, 39.95],
        }
    )

    tm.assert_frame_equal(df_fileio, df_expected)


@pytest.mark.network
@pytest.mark.single_cpu
def test_url_path_error(parser, httpserver, xml_file):
    with open(xml_file, encoding="utf-8") as f:
        httpserver.serve_content(content=f.read())
        with pytest.raises(
            ParserError, match=("iterparse is designed for large XML files")
        ):
            read_xml(
                httpserver.url,
                parser=parser,
                iterparse={"row": ["shape", "degrees", "sides", "date"]},
            )


def test_compression_error(parser, compression_only):
    with tm.ensure_clean(filename="geom_xml.zip") as path:
        geom_df.to_xml(path, parser=parser, compression=compression_only)

        with pytest.raises(
            ParserError, match=("iterparse is designed for large XML files")
        ):
            read_xml(
                path,
                parser=parser,
                iterparse={"row": ["shape", "degrees", "sides", "date"]},
                compression=compression_only,
            )


def test_wrong_dict_type(xml_books, parser):
    with pytest.raises(TypeError, match="list is not a valid type for iterparse"):
        read_xml(
            xml_books,
            parser=parser,
            iterparse=["category", "title", "year", "author", "price"],
        )


def test_wrong_dict_value(xml_books, parser):
    with pytest.raises(
        TypeError, match="<class 'str'> is not a valid type for value in iterparse"
    ):
        read_xml(xml_books, parser=parser, iterparse={"book": "category"})


def test_bad_xml(parser):
    bad_xml = """\
<?xml version='1.0' encoding='utf-8'?>
  <row>
    <shape>square</shape>
    <degrees>00360</degrees>
    <sides>4.0</sides>
    <date>2020-01-01</date>
   </row>
  <row>
    <shape>circle</shape>
    <degrees>00360</degrees>
    <sides/>
    <date>2021-01-01</date>
  </row>
  <row>
    <shape>triangle</shape>
    <degrees>00180</degrees>
    <sides>3.0</sides>
    <date>2022-01-01</date>
  </row>
"""
    with tm.ensure_clean(filename="bad.xml") as path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(bad_xml)

        with pytest.raises(
            SyntaxError,
            match=(
                "Extra content at the end of the document|"
                "junk after document element"
            ),
        ):
            read_xml(
                path,
                parser=parser,
                parse_dates=["date"],
                iterparse={"row": ["shape", "degrees", "sides", "date"]},
            )


def test_comment(parser):
    xml = """\
<!-- comment before root -->
<shapes>
  <!-- comment within root -->
  <shape>
    <name>circle</name>
    <type>2D</type>
  </shape>
  <shape>
    <name>sphere</name>
    <type>3D</type>
    <!-- comment within child -->
  </shape>
  <!-- comment within root -->
</shapes>
<!-- comment after root -->"""

    df_xpath = read_xml(StringIO(xml), xpath=".//shape", parser=parser)

    df_iter = read_xml_iterparse(
        xml, parser=parser, iterparse={"shape": ["name", "type"]}
    )

    df_expected = DataFrame(
        {
            "name": ["circle", "sphere"],
            "type": ["2D", "3D"],
        }
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_dtd(parser):
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE non-profits [
    <!ELEMENT shapes (shape*) >
    <!ELEMENT shape ( name, type )>
    <!ELEMENT name (#PCDATA)>
]>
<shapes>
  <shape>
    <name>circle</name>
    <type>2D</type>
  </shape>
  <shape>
    <name>sphere</name>
    <type>3D</type>
  </shape>
</shapes>"""

    df_xpath = read_xml(StringIO(xml), xpath=".//shape", parser=parser)

    df_iter = read_xml_iterparse(
        xml, parser=parser, iterparse={"shape": ["name", "type"]}
    )

    df_expected = DataFrame(
        {
            "name": ["circle", "sphere"],
            "type": ["2D", "3D"],
        }
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_processing_instruction(parser):
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="style.xsl"?>
<?display table-view?>
<?sort alpha-ascending?>
<?textinfo whitespace is allowed ?>
<?elementnames <shape>, <name>, <type> ?>
<shapes>
  <shape>
    <name>circle</name>
    <type>2D</type>
  </shape>
  <shape>
    <name>sphere</name>
    <type>3D</type>
  </shape>
</shapes>"""

    df_xpath = read_xml(StringIO(xml), xpath=".//shape", parser=parser)

    df_iter = read_xml_iterparse(
        xml, parser=parser, iterparse={"shape": ["name", "type"]}
    )

    df_expected = DataFrame(
        {
            "name": ["circle", "sphere"],
            "type": ["2D", "3D"],
        }
    )

    tm.assert_frame_equal(df_xpath, df_expected)
    tm.assert_frame_equal(df_iter, df_expected)


def test_no_result(xml_books, parser):
    with pytest.raises(
        ParserError, match="No result from selected items in iterparse."
    ):
        read_xml(
            xml_books,
            parser=parser,
            iterparse={"node": ["attr1", "elem1", "elem2", "elem3"]},
        )


def test_empty_data(xml_books, parser):
    with pytest.raises(EmptyDataError, match="No columns to parse from file"):
        read_xml(
            xml_books,
            parser=parser,
            iterparse={"book": ["attr1", "elem1", "elem2", "elem3"]},
        )


def test_online_stylesheet():
    pytest.importorskip("lxml")
    xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<catalog>
  <cd>
    <title>Empire Burlesque</title>
    <artist>Bob Dylan</artist>
    <country>USA</country>
    <company>Columbia</company>
    <price>10.90</price>
    <year>1985</year>
  </cd>
  <cd>
    <title>Hide your heart</title>
    <artist>Bonnie Tyler</artist>
    <country>UK</country>
    <company>CBS Records</company>
    <price>9.90</price>
    <year>1988</year>
  </cd>
  <cd>
    <title>Greatest Hits</title>
    <artist>Dolly Parton</artist>
    <country>USA</country>
    <company>RCA</company>
    <price>9.90</price>
    <year>1982</year>
  </cd>
  <cd>
    <title>Still got the blues</title>
    <artist>Gary Moore</artist>
    <country>UK</country>
    <company>Virgin records</company>
    <price>10.20</price>
    <year>1990</year>
  </cd>
  <cd>
    <title>Eros</title>
    <artist>Eros Ramazzotti</artist>
    <country>EU</country>
    <company>BMG</company>
    <price>9.90</price>
    <year>1997</year>
  </cd>
  <cd>
    <title>One night only</title>
    <artist>Bee Gees</artist>
    <country>UK</country>
    <company>Polydor</company>
    <price>10.90</price>
    <year>1998</year>
  </cd>
  <cd>
    <title>Sylvias Mother</title>
    <artist>Dr.Hook</artist>
    <country>UK</country>
    <company>CBS</company>
    <price>8.10</price>
    <year>1973</year>
  </cd>
  <cd>
    <title>Maggie May</title>
    <artist>Rod Stewart</artist>
    <country>UK</country>
    <company>Pickwick</company>
    <price>8.50</price>
    <year>1990</year>
  </cd>
  <cd>
    <title>Romanza</title>
    <artist>Andrea Bocelli</artist>
    <country>EU</country>
    <company>Polydor</company>
    <price>10.80</price>
    <year>1996</year>
  </cd>
  <cd>
    <title>When a man loves a woman</title>
    <artist>Percy Sledge</artist>
    <country>USA</country>
    <company>Atlantic</company>
    <price>8.70</price>
    <year>1987</year>
  </cd>
  <cd>
    <title>Black angel</title>
    <artist>Savage Rose</artist>
    <country>EU</country>
    <company>Mega</company>
    <price>10.90</price>
    <year>1995</year>
  </cd>
  <cd>
    <title>1999 Grammy Nominees</title>
    <artist>Many</artist>
    <country>USA</country>
    <company>Grammy</company>
    <price>10.20</price>
    <year>1999</year>
  </cd>
  <cd>
    <title>For the good times</title>
    <artist>Kenny Rogers</artist>
    <country>UK</country>
    <company>Mucik Master</company>
    <price>8.70</price>
    <year>1995</year>
  </cd>
  <cd>
    <title>Big Willie style</title>
    <artist>Will Smith</artist>
    <country>USA</country>
    <company>Columbia</company>
    <price>9.90</price>
    <year>1997</year>
  </cd>
  <cd>
    <title>Tupelo Honey</title>
    <artist>Van Morrison</artist>
    <country>UK</country>
    <company>Polydor</company>
    <price>8.20</price>
    <year>1971</year>
  </cd>
  <cd>
    <title>Soulsville</title>
    <artist>Jorn Hoel</artist>
    <country>Norway</country>
    <company>WEA</company>
    <price>7.90</price>
    <year>1996</year>
  </cd>
  <cd>
    <title>The very best of</title>
    <artist>Cat Stevens</artist>
    <country>UK</country>
    <company>Island</company>
    <price>8.90</price>
    <year>1990</year>
  </cd>
  <cd>
    <title>Stop</title>
    <artist>Sam Brown</artist>
    <country>UK</country>
    <company>A and M</company>
    <price>8.90</price>
    <year>1988</year>
  </cd>
  <cd>
    <title>Bridge of Spies</title>
    <artist>T`Pau</artist>
    <country>UK</country>
    <company>Siren</company>
    <price>7.90</price>
    <year>1987</year>
  </cd>
  <cd>
    <title>Private Dancer</title>
    <artist>Tina Turner</artist>
    <country>UK</country>
    <company>Capitol</company>
    <price>8.90</price>
    <year>1983</year>
  </cd>
  <cd>
    <title>Midt om natten</title>
    <artist>Kim Larsen</artist>
    <country>EU</country>
    <company>Medley</company>
    <price>7.80</price>
    <year>1983</year>
  </cd>
  <cd>
    <title>Pavarotti Gala Concert</title>
    <artist>Luciano Pavarotti</artist>
    <country>UK</country>
    <company>DECCA</company>
    <price>9.90</price>
    <year>1991</year>
  </cd>
  <cd>
    <title>The dock of the bay</title>
    <artist>Otis Redding</artist>
    <country>USA</country>
    <COMPANY>Stax Records</COMPANY>
    <PRICE>7.90</PRICE>
    <YEAR>1968</YEAR>
  </cd>
  <cd>
    <title>Picture book</title>
    <artist>Simply Red</artist>
    <country>EU</country>
    <company>Elektra</company>
    <price>7.20</price>
    <year>1985</year>
  </cd>
  <cd>
    <title>Red</title>
    <artist>The Communards</artist>
    <country>UK</country>
    <company>London</company>
    <price>7.80</price>
    <year>1987</year>
  </cd>
  <cd>
    <title>Unchain my heart</title>
    <artist>Joe Cocker</artist>
    <country>USA</country>
    <company>EMI</company>
    <price>8.20</price>
    <year>1987</year>
  </cd>
</catalog>
"""
    xsl = """\
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:template match="/">
<html>
<body>
  <h2>My CD Collection</h2>
  <table border="1">
    <tr bgcolor="#9acd32">
      <th style="text-align:left">Title</th>
      <th style="text-align:left">Artist</th>
    </tr>
    <xsl:for-each select="catalog/cd">
    <tr>
      <td><xsl:value-of select="title"/></td>
      <td><xsl:value-of select="artist"/></td>
    </tr>
    </xsl:for-each>
  </table>
</body>
</html>
</xsl:template>
</xsl:stylesheet>
"""

    df_xsl = read_xml(
        StringIO(xml),
        xpath=".//tr[td and position() <= 6]",
        names=["title", "artist"],
        stylesheet=xsl,
    )

    df_expected = DataFrame(
        {
            "title": {
                0: "Empire Burlesque",
                1: "Hide your heart",
                2: "Greatest Hits",
                3: "Still got the blues",
                4: "Eros",
            },
            "artist": {
                0: "Bob Dylan",
                1: "Bonnie Tyler",
                2: "Dolly Parton",
                3: "Gary Moore",
                4: "Eros Ramazzotti",
            },
        }
    )

    tm.assert_frame_equal(df_expected, df_xsl)


# COMPRESSION


def test_compression_read(parser, compression_only):
    with tm.ensure_clean() as comp_path:
        geom_df.to_xml(
            comp_path, index=False, parser=parser, compression=compression_only
        )

        df_xpath = read_xml(comp_path, parser=parser, compression=compression_only)

        df_iter = read_xml_iterparse_comp(
            comp_path,
            compression_only,
            parser=parser,
            iterparse={"row": ["shape", "degrees", "sides"]},
            compression=compression_only,
        )

    tm.assert_frame_equal(df_xpath, geom_df)
    tm.assert_frame_equal(df_iter, geom_df)


def test_wrong_compression(parser, compression, compression_only):
    actual_compression = compression
    attempted_compression = compression_only

    if actual_compression == attempted_compression:
        pytest.skip(f"{actual_compression} == {attempted_compression}")

    errors = {
        "bz2": (OSError, "Invalid data stream"),
        "gzip": (OSError, "Not a gzipped file"),
        "zip": (BadZipFile, "File is not a zip file"),
        "tar": (ReadError, "file could not be opened successfully"),
    }
    zstd = import_optional_dependency("zstandard", errors="ignore")
    if zstd is not None:
        errors["zstd"] = (zstd.ZstdError, "Unknown frame descriptor")
    lzma = import_optional_dependency("lzma", errors="ignore")
    if lzma is not None:
        errors["xz"] = (LZMAError, "Input format not supported by decoder")
    error_cls, error_str = errors[attempted_compression]

    with tm.ensure_clean() as path:
        geom_df.to_xml(path, parser=parser, compression=actual_compression)

        with pytest.raises(error_cls, match=error_str):
            read_xml(path, parser=parser, compression=attempted_compression)


def test_unsuported_compression(parser):
    with pytest.raises(ValueError, match="Unrecognized compression type"):
        with tm.ensure_clean() as path:
            read_xml(path, parser=parser, compression="7z")


# STORAGE OPTIONS


@pytest.mark.network
@pytest.mark.single_cpu
def test_s3_parser_consistency(s3_public_bucket_with_data, s3so):
    pytest.importorskip("s3fs")
    pytest.importorskip("lxml")
    s3 = f"s3://{s3_public_bucket_with_data.name}/books.xml"

    df_lxml = read_xml(s3, parser="lxml", storage_options=s3so)

    df_etree = read_xml(s3, parser="etree", storage_options=s3so)

    tm.assert_frame_equal(df_lxml, df_etree)


def test_read_xml_nullable_dtypes(
    parser, string_storage, dtype_backend, using_infer_string
):
    # GH#50500
    data = """<?xml version='1.0' encoding='utf-8'?>
<data xmlns="http://example.com">
<row>
  <a>x</a>
  <b>1</b>
  <c>4.0</c>
  <d>x</d>
  <e>2</e>
  <f>4.0</f>
  <g></g>
  <h>True</h>
  <i>False</i>
</row>
<row>
  <a>y</a>
  <b>2</b>
  <c>5.0</c>
  <d></d>
  <e></e>
  <f></f>
  <g></g>
  <h>False</h>
  <i></i>
</row>
</data>"""

    with pd.option_context("mode.string_storage", string_storage):
        result = read_xml(StringIO(data), parser=parser, dtype_backend=dtype_backend)

    if dtype_backend == "pyarrow":
        pa = pytest.importorskip("pyarrow")
        string_dtype = pd.ArrowDtype(pa.string())
    else:
        string_dtype = pd.StringDtype(string_storage)

    expected = DataFrame(
        {
            "a": Series(["x", "y"], dtype=string_dtype),
            "b": Series([1, 2], dtype="Int64"),
            "c": Series([4.0, 5.0], dtype="Float64"),
            "d": Series(["x", None], dtype=string_dtype),
            "e": Series([2, NA], dtype="Int64"),
            "f": Series([4.0, NA], dtype="Float64"),
            "g": Series([NA, NA], dtype="Int64"),
            "h": Series([True, False], dtype="boolean"),
            "i": Series([False, NA], dtype="boolean"),
        }
    )

    if dtype_backend == "pyarrow":
        pa = pytest.importorskip("pyarrow")
        from pandas.arrays import ArrowExtensionArray

        expected = DataFrame(
            {
                col: ArrowExtensionArray(pa.array(expected[col], from_pandas=True))
                for col in expected.columns
            }
        )
        expected["g"] = ArrowExtensionArray(pa.array([None, None]))

    # the storage of the str columns' Index is also affected by the
    # string_storage setting -> ignore that for checking the result
    tm.assert_frame_equal(result, expected, check_column_type=False)


def test_invalid_dtype_backend():
    msg = (
        "dtype_backend numpy is invalid, only 'numpy_nullable' and "
        "'pyarrow' are allowed."
    )
    with pytest.raises(ValueError, match=msg):
        read_xml("test", dtype_backend="numpy")
