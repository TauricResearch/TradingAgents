from __future__ import annotations

from io import (
    BytesIO,
    StringIO,
)
import os

import numpy as np
import pytest

import pandas.util._test_decorators as td

from pandas import (
    NA,
    DataFrame,
    Index,
)
import pandas._testing as tm

from pandas.io.common import get_handle
from pandas.io.xml import read_xml

# CHECKLIST

# [x] - ValueError: "Values for parser can only be lxml or etree."

# etree
# [x] - ImportError: "lxml not found, please install or use the etree parser."
# [X] - TypeError: "...is not a valid type for attr_cols"
# [X] - TypeError: "...is not a valid type for elem_cols"
# [X] - LookupError: "unknown encoding"
# [X] - KeyError: "...is not included in namespaces"
# [X] - KeyError: "no valid column"
# [X] - ValueError: "To use stylesheet, you need lxml installed..."
# []  - OSError: (NEED PERMISSOIN ISSUE, DISK FULL, ETC.)
# [X] - FileNotFoundError: "No such file or directory"
# [X] - PermissionError: "Forbidden"

# lxml
# [X] - TypeError: "...is not a valid type for attr_cols"
# [X] - TypeError: "...is not a valid type for elem_cols"
# [X] - LookupError: "unknown encoding"
# []  - OSError: (NEED PERMISSOIN ISSUE, DISK FULL, ETC.)
# [X] - FileNotFoundError: "No such file or directory"
# [X] - KeyError: "...is not included in namespaces"
# [X] - KeyError: "no valid column"
# [X] - ValueError: "stylesheet is not a url, file, or xml string."
# []  - LookupError: (NEED WRONG ENCODING FOR FILE OUTPUT)
# []  - URLError: (USUALLY DUE TO NETWORKING)
# []  - HTTPError: (NEED AN ONLINE STYLESHEET)
# [X] - OSError: "failed to load external entity"
# [X] - XMLSyntaxError: "Opening and ending tag mismatch"
# [X] - XSLTApplyError: "Cannot resolve URI"
# [X] - XSLTParseError: "failed to compile"
# [X] - PermissionError: "Forbidden"


@pytest.fixture
def geom_df():
    return DataFrame(
        {
            "shape": ["square", "circle", "triangle"],
            "degrees": [360, 360, 180],
            "sides": [4, np.nan, 3],
        }
    )


@pytest.fixture
def planet_df():
    return DataFrame(
        {
            "planet": [
                "Mercury",
                "Venus",
                "Earth",
                "Mars",
                "Jupiter",
                "Saturn",
                "Uranus",
                "Neptune",
            ],
            "type": [
                "terrestrial",
                "terrestrial",
                "terrestrial",
                "terrestrial",
                "gas giant",
                "gas giant",
                "ice giant",
                "ice giant",
            ],
            "location": [
                "inner",
                "inner",
                "inner",
                "inner",
                "outer",
                "outer",
                "outer",
                "outer",
            ],
            "mass": [
                0.330114,
                4.86747,
                5.97237,
                0.641712,
                1898.187,
                568.3174,
                86.8127,
                102.4126,
            ],
        }
    )


@pytest.fixture
def from_file_expected():
    return """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <index>0</index>
    <category>cooking</category>
    <title>Everyday Italian</title>
    <author>Giada De Laurentiis</author>
    <year>2005</year>
    <price>30.0</price>
  </row>
  <row>
    <index>1</index>
    <category>children</category>
    <title>Harry Potter</title>
    <author>J K. Rowling</author>
    <year>2005</year>
    <price>29.99</price>
  </row>
  <row>
    <index>2</index>
    <category>web</category>
    <title>Learning XML</title>
    <author>Erik T. Ray</author>
    <year>2003</year>
    <price>39.95</price>
  </row>
</data>"""


def equalize_decl(doc):
    # etree and lxml differ on quotes and case in xml declaration
    if doc is not None:
        doc = doc.replace(
            '<?xml version="1.0" encoding="utf-8"?',
            "<?xml version='1.0' encoding='utf-8'?",
        )
    return doc


@pytest.fixture(params=["rb", "r"])
def mode(request):
    return request.param


@pytest.fixture(params=[pytest.param("lxml", marks=td.skip_if_no("lxml")), "etree"])
def parser(request):
    return request.param


# FILE OUTPUT


def test_file_output_str_read(xml_books, parser, from_file_expected):
    df_file = read_xml(xml_books, parser=parser)

    with tm.ensure_clean("test.xml") as path:
        df_file.to_xml(path, parser=parser)
        with open(path, "rb") as f:
            output = f.read().decode("utf-8").strip()

        output = equalize_decl(output)

        assert output == from_file_expected


def test_file_output_bytes_read(xml_books, parser, from_file_expected):
    df_file = read_xml(xml_books, parser=parser)

    with tm.ensure_clean("test.xml") as path:
        df_file.to_xml(path, parser=parser)
        with open(path, "rb") as f:
            output = f.read().decode("utf-8").strip()

        output = equalize_decl(output)

        assert output == from_file_expected


def test_str_output(xml_books, parser, from_file_expected):
    df_file = read_xml(xml_books, parser=parser)

    output = df_file.to_xml(parser=parser)
    output = equalize_decl(output)

    assert output == from_file_expected


def test_wrong_file_path(parser, geom_df):
    path = "/my/fake/path/output.xml"

    with pytest.raises(
        OSError,
        match=(r"Cannot save file into a non-existent directory: .*path"),
    ):
        geom_df.to_xml(path, parser=parser)


# INDEX


def test_index_false(xml_books, parser):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <category>cooking</category>
    <title>Everyday Italian</title>
    <author>Giada De Laurentiis</author>
    <year>2005</year>
    <price>30.0</price>
  </row>
  <row>
    <category>children</category>
    <title>Harry Potter</title>
    <author>J K. Rowling</author>
    <year>2005</year>
    <price>29.99</price>
  </row>
  <row>
    <category>web</category>
    <title>Learning XML</title>
    <author>Erik T. Ray</author>
    <year>2003</year>
    <price>39.95</price>
  </row>
</data>"""

    df_file = read_xml(xml_books, parser=parser)

    with tm.ensure_clean("test.xml") as path:
        df_file.to_xml(path, index=False, parser=parser)
        with open(path, "rb") as f:
            output = f.read().decode("utf-8").strip()

        output = equalize_decl(output)

        assert output == expected


def test_index_false_rename_row_root(xml_books, parser):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<books>
  <book>
    <category>cooking</category>
    <title>Everyday Italian</title>
    <author>Giada De Laurentiis</author>
    <year>2005</year>
    <price>30.0</price>
  </book>
  <book>
    <category>children</category>
    <title>Harry Potter</title>
    <author>J K. Rowling</author>
    <year>2005</year>
    <price>29.99</price>
  </book>
  <book>
    <category>web</category>
    <title>Learning XML</title>
    <author>Erik T. Ray</author>
    <year>2003</year>
    <price>39.95</price>
  </book>
</books>"""

    df_file = read_xml(xml_books, parser=parser)

    with tm.ensure_clean("test.xml") as path:
        df_file.to_xml(
            path, index=False, root_name="books", row_name="book", parser=parser
        )
        with open(path, "rb") as f:
            output = f.read().decode("utf-8").strip()

        output = equalize_decl(output)

        assert output == expected


@pytest.mark.parametrize(
    "offset_index", [list(range(10, 13)), [str(i) for i in range(10, 13)]]
)
def test_index_false_with_offset_input_index(parser, offset_index, geom_df):
    """
    Tests that the output does not contain the `<index>` field when the index of the
    input Dataframe has an offset.

    This is a regression test for issue #42458.
    """

    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""

    offset_geom_df = geom_df.copy()
    offset_geom_df.index = Index(offset_index)
    output = offset_geom_df.to_xml(index=False, parser=parser)
    output = equalize_decl(output)

    assert output == expected


# NA_REP

na_expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <index>0</index>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <index>1</index>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <index>2</index>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""


def test_na_elem_output(parser, geom_df):
    output = geom_df.to_xml(parser=parser)
    output = equalize_decl(output)

    assert output == na_expected


def test_na_empty_str_elem_option(parser, geom_df):
    output = geom_df.to_xml(na_rep="", parser=parser)
    output = equalize_decl(output)

    assert output == na_expected


def test_na_empty_elem_option(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <index>0</index>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <index>1</index>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides>0.0</sides>
  </row>
  <row>
    <index>2</index>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""

    output = geom_df.to_xml(na_rep="0.0", parser=parser)
    output = equalize_decl(output)

    assert output == expected


# ATTR_COLS


def test_attrs_cols_nan_output(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row index="0" shape="square" degrees="360" sides="4.0"/>
  <row index="1" shape="circle" degrees="360"/>
  <row index="2" shape="triangle" degrees="180" sides="3.0"/>
</data>"""

    output = geom_df.to_xml(attr_cols=["shape", "degrees", "sides"], parser=parser)
    output = equalize_decl(output)

    assert output == expected


def test_attrs_cols_prefix(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<doc:data xmlns:doc="http://example.xom">
  <doc:row doc:index="0" doc:shape="square" \
doc:degrees="360" doc:sides="4.0"/>
  <doc:row doc:index="1" doc:shape="circle" \
doc:degrees="360"/>
  <doc:row doc:index="2" doc:shape="triangle" \
doc:degrees="180" doc:sides="3.0"/>
</doc:data>"""

    output = geom_df.to_xml(
        attr_cols=["index", "shape", "degrees", "sides"],
        namespaces={"doc": "http://example.xom"},
        prefix="doc",
        parser=parser,
    )
    output = equalize_decl(output)

    assert output == expected


def test_attrs_unknown_column(parser, geom_df):
    with pytest.raises(KeyError, match=("no valid column")):
        geom_df.to_xml(attr_cols=["shape", "degree", "sides"], parser=parser)


def test_attrs_wrong_type(parser, geom_df):
    with pytest.raises(TypeError, match=("is not a valid type for attr_cols")):
        geom_df.to_xml(attr_cols='"shape", "degree", "sides"', parser=parser)


# ELEM_COLS


def test_elems_cols_nan_output(parser, geom_df):
    elems_cols_expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <degrees>360</degrees>
    <sides>4.0</sides>
    <shape>square</shape>
  </row>
  <row>
    <degrees>360</degrees>
    <sides/>
    <shape>circle</shape>
  </row>
  <row>
    <degrees>180</degrees>
    <sides>3.0</sides>
    <shape>triangle</shape>
  </row>
</data>"""

    output = geom_df.to_xml(
        index=False, elem_cols=["degrees", "sides", "shape"], parser=parser
    )
    output = equalize_decl(output)

    assert output == elems_cols_expected


def test_elems_unknown_column(parser, geom_df):
    with pytest.raises(KeyError, match=("no valid column")):
        geom_df.to_xml(elem_cols=["shape", "degree", "sides"], parser=parser)


def test_elems_wrong_type(parser, geom_df):
    with pytest.raises(TypeError, match=("is not a valid type for elem_cols")):
        geom_df.to_xml(elem_cols='"shape", "degree", "sides"', parser=parser)


def test_elems_and_attrs_cols(parser, geom_df):
    elems_cols_expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row shape="square">
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row shape="circle">
    <degrees>360</degrees>
    <sides/>
  </row>
  <row shape="triangle">
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""

    output = geom_df.to_xml(
        index=False,
        elem_cols=["degrees", "sides"],
        attr_cols=["shape"],
        parser=parser,
    )
    output = equalize_decl(output)

    assert output == elems_cols_expected


# HIERARCHICAL COLUMNS


def test_hierarchical_columns(parser, planet_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <location>inner</location>
    <type>terrestrial</type>
    <count_mass>4</count_mass>
    <sum_mass>11.81</sum_mass>
    <mean_mass>2.95</mean_mass>
  </row>
  <row>
    <location>outer</location>
    <type>gas giant</type>
    <count_mass>2</count_mass>
    <sum_mass>2466.5</sum_mass>
    <mean_mass>1233.25</mean_mass>
  </row>
  <row>
    <location>outer</location>
    <type>ice giant</type>
    <count_mass>2</count_mass>
    <sum_mass>189.23</sum_mass>
    <mean_mass>94.61</mean_mass>
  </row>
  <row>
    <location>All</location>
    <type/>
    <count_mass>8</count_mass>
    <sum_mass>2667.54</sum_mass>
    <mean_mass>333.44</mean_mass>
  </row>
</data>"""

    pvt = planet_df.pivot_table(
        index=["location", "type"],
        values="mass",
        aggfunc=["count", "sum", "mean"],
        margins=True,
    ).round(2)

    output = pvt.to_xml(parser=parser)
    output = equalize_decl(output)

    assert output == expected


def test_hierarchical_attrs_columns(parser, planet_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row location="inner" type="terrestrial" count_mass="4" \
sum_mass="11.81" mean_mass="2.95"/>
  <row location="outer" type="gas giant" count_mass="2" \
sum_mass="2466.5" mean_mass="1233.25"/>
  <row location="outer" type="ice giant" count_mass="2" \
sum_mass="189.23" mean_mass="94.61"/>
  <row location="All" type="" count_mass="8" \
sum_mass="2667.54" mean_mass="333.44"/>
</data>"""

    pvt = planet_df.pivot_table(
        index=["location", "type"],
        values="mass",
        aggfunc=["count", "sum", "mean"],
        margins=True,
    ).round(2)

    output = pvt.to_xml(attr_cols=list(pvt.reset_index().columns.values), parser=parser)
    output = equalize_decl(output)

    assert output == expected


# MULTIINDEX


def test_multi_index(parser, planet_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <location>inner</location>
    <type>terrestrial</type>
    <count>4</count>
    <sum>11.81</sum>
    <mean>2.95</mean>
  </row>
  <row>
    <location>outer</location>
    <type>gas giant</type>
    <count>2</count>
    <sum>2466.5</sum>
    <mean>1233.25</mean>
  </row>
  <row>
    <location>outer</location>
    <type>ice giant</type>
    <count>2</count>
    <sum>189.23</sum>
    <mean>94.61</mean>
  </row>
</data>"""

    agg = (
        planet_df.groupby(["location", "type"])["mass"]
        .agg(["count", "sum", "mean"])
        .round(2)
    )

    output = agg.to_xml(parser=parser)
    output = equalize_decl(output)

    assert output == expected


def test_multi_index_attrs_cols(parser, planet_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row location="inner" type="terrestrial" count="4" \
sum="11.81" mean="2.95"/>
  <row location="outer" type="gas giant" count="2" \
sum="2466.5" mean="1233.25"/>
  <row location="outer" type="ice giant" count="2" \
sum="189.23" mean="94.61"/>
</data>"""

    agg = (
        planet_df.groupby(["location", "type"])["mass"]
        .agg(["count", "sum", "mean"])
        .round(2)
    )
    output = agg.to_xml(attr_cols=list(agg.reset_index().columns.values), parser=parser)
    output = equalize_decl(output)

    assert output == expected


# NAMESPACE


def test_default_namespace(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data xmlns="http://example.com">
  <row>
    <index>0</index>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <index>1</index>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <index>2</index>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""

    output = geom_df.to_xml(namespaces={"": "http://example.com"}, parser=parser)
    output = equalize_decl(output)

    assert output == expected


def test_unused_namespaces(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<data xmlns:oth="http://other.org" xmlns:ex="http://example.com">
  <row>
    <index>0</index>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <index>1</index>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <index>2</index>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""

    output = geom_df.to_xml(
        namespaces={"oth": "http://other.org", "ex": "http://example.com"},
        parser=parser,
    )
    output = equalize_decl(output)

    assert output == expected


# PREFIX


def test_namespace_prefix(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<doc:data xmlns:doc="http://example.com">
  <doc:row>
    <doc:index>0</doc:index>
    <doc:shape>square</doc:shape>
    <doc:degrees>360</doc:degrees>
    <doc:sides>4.0</doc:sides>
  </doc:row>
  <doc:row>
    <doc:index>1</doc:index>
    <doc:shape>circle</doc:shape>
    <doc:degrees>360</doc:degrees>
    <doc:sides/>
  </doc:row>
  <doc:row>
    <doc:index>2</doc:index>
    <doc:shape>triangle</doc:shape>
    <doc:degrees>180</doc:degrees>
    <doc:sides>3.0</doc:sides>
  </doc:row>
</doc:data>"""

    output = geom_df.to_xml(
        namespaces={"doc": "http://example.com"}, prefix="doc", parser=parser
    )
    output = equalize_decl(output)

    assert output == expected


def test_missing_prefix_in_nmsp(parser, geom_df):
    with pytest.raises(KeyError, match=("doc is not included in namespaces")):
        geom_df.to_xml(
            namespaces={"": "http://example.com"}, prefix="doc", parser=parser
        )


def test_namespace_prefix_and_default(parser, geom_df):
    expected = """\
<?xml version='1.0' encoding='utf-8'?>
<doc:data xmlns:doc="http://other.org" xmlns="http://example.com">
  <doc:row>
    <doc:index>0</doc:index>
    <doc:shape>square</doc:shape>
    <doc:degrees>360</doc:degrees>
    <doc:sides>4.0</doc:sides>
  </doc:row>
  <doc:row>
    <doc:index>1</doc:index>
    <doc:shape>circle</doc:shape>
    <doc:degrees>360</doc:degrees>
    <doc:sides/>
  </doc:row>
  <doc:row>
    <doc:index>2</doc:index>
    <doc:shape>triangle</doc:shape>
    <doc:degrees>180</doc:degrees>
    <doc:sides>3.0</doc:sides>
  </doc:row>
</doc:data>"""

    output = geom_df.to_xml(
        namespaces={"": "http://example.com", "doc": "http://other.org"},
        prefix="doc",
        parser=parser,
    )
    output = equalize_decl(output)

    assert output == expected


# ENCODING

encoding_expected = """\
<?xml version='1.0' encoding='ISO-8859-1'?>
<data>
  <row>
    <index>0</index>
    <rank>1</rank>
    <malename>José</malename>
    <femalename>Sofía</femalename>
  </row>
  <row>
    <index>1</index>
    <rank>2</rank>
    <malename>Luis</malename>
    <femalename>Valentina</femalename>
  </row>
  <row>
    <index>2</index>
    <rank>3</rank>
    <malename>Carlos</malename>
    <femalename>Isabella</femalename>
  </row>
  <row>
    <index>3</index>
    <rank>4</rank>
    <malename>Juan</malename>
    <femalename>Camila</femalename>
  </row>
  <row>
    <index>4</index>
    <rank>5</rank>
    <malename>Jorge</malename>
    <femalename>Valeria</femalename>
  </row>
</data>"""


def test_encoding_option_str(xml_baby_names, parser):
    df_file = read_xml(xml_baby_names, parser=parser, encoding="ISO-8859-1").head(5)

    output = df_file.to_xml(encoding="ISO-8859-1", parser=parser)

    if output is not None:
        # etree and lxml differ on quotes and case in xml declaration
        output = output.replace(
            '<?xml version="1.0" encoding="ISO-8859-1"?',
            "<?xml version='1.0' encoding='ISO-8859-1'?",
        )

    assert output == encoding_expected


def test_correct_encoding_file(xml_baby_names):
    pytest.importorskip("lxml")
    df_file = read_xml(xml_baby_names, encoding="ISO-8859-1", parser="lxml")

    with tm.ensure_clean("test.xml") as path:
        df_file.to_xml(path, index=False, encoding="ISO-8859-1", parser="lxml")


@pytest.mark.parametrize("encoding", ["UTF-8", "UTF-16", "ISO-8859-1"])
def test_wrong_encoding_option_lxml(xml_baby_names, parser, encoding):
    pytest.importorskip("lxml")
    df_file = read_xml(xml_baby_names, encoding="ISO-8859-1", parser="lxml")

    with tm.ensure_clean("test.xml") as path:
        df_file.to_xml(path, index=False, encoding=encoding, parser=parser)


def test_misspelled_encoding(parser, geom_df):
    with pytest.raises(LookupError, match=("unknown encoding")):
        geom_df.to_xml(encoding="uft-8", parser=parser)


# PRETTY PRINT


def test_xml_declaration_pretty_print(geom_df):
    pytest.importorskip("lxml")
    expected = """\
<data>
  <row>
    <index>0</index>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <index>1</index>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <index>2</index>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""

    output = geom_df.to_xml(xml_declaration=False)

    assert output == expected


def test_no_pretty_print_with_decl(parser, geom_df):
    expected = (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<data><row><index>0</index><shape>square</shape>"
        "<degrees>360</degrees><sides>4.0</sides></row><row>"
        "<index>1</index><shape>circle</shape><degrees>360"
        "</degrees><sides/></row><row><index>2</index><shape>"
        "triangle</shape><degrees>180</degrees><sides>3.0</sides>"
        "</row></data>"
    )

    output = geom_df.to_xml(pretty_print=False, parser=parser)
    output = equalize_decl(output)

    # etree adds space for closed tags
    if output is not None:
        output = output.replace(" />", "/>")

    assert output == expected


def test_no_pretty_print_no_decl(parser, geom_df):
    expected = (
        "<data><row><index>0</index><shape>square</shape>"
        "<degrees>360</degrees><sides>4.0</sides></row><row>"
        "<index>1</index><shape>circle</shape><degrees>360"
        "</degrees><sides/></row><row><index>2</index><shape>"
        "triangle</shape><degrees>180</degrees><sides>3.0</sides>"
        "</row></data>"
    )

    output = geom_df.to_xml(xml_declaration=False, pretty_print=False, parser=parser)

    # etree adds space for closed tags
    if output is not None:
        output = output.replace(" />", "/>")

    assert output == expected


# PARSER


@td.skip_if_installed("lxml")
def test_default_parser_no_lxml(geom_df):
    with pytest.raises(
        ImportError, match=("lxml not found, please install or use the etree parser.")
    ):
        geom_df.to_xml()


def test_unknown_parser(geom_df):
    with pytest.raises(
        ValueError, match=("Values for parser can only be lxml or etree.")
    ):
        geom_df.to_xml(parser="bs4")


# STYLESHEET

xsl_expected = """\
<?xml version="1.0" encoding="utf-8"?>
<data>
  <row>
    <field field="index">0</field>
    <field field="shape">square</field>
    <field field="degrees">360</field>
    <field field="sides">4.0</field>
  </row>
  <row>
    <field field="index">1</field>
    <field field="shape">circle</field>
    <field field="degrees">360</field>
    <field field="sides"/>
  </row>
  <row>
    <field field="index">2</field>
    <field field="shape">triangle</field>
    <field field="degrees">180</field>
    <field field="sides">3.0</field>
  </row>
</data>"""


def test_stylesheet_file_like(xsl_row_field_output, mode, geom_df):
    pytest.importorskip("lxml")
    with open(
        xsl_row_field_output, mode, encoding="utf-8" if mode == "r" else None
    ) as f:
        assert geom_df.to_xml(stylesheet=f) == xsl_expected


def test_stylesheet_io(xsl_row_field_output, mode, geom_df):
    # note: By default the bodies of untyped functions are not checked,
    # consider using --check-untyped-defs
    pytest.importorskip("lxml")
    xsl_obj: BytesIO | StringIO  # type: ignore[annotation-unchecked]

    with open(
        xsl_row_field_output, mode, encoding="utf-8" if mode == "r" else None
    ) as f:
        if mode == "rb":
            xsl_obj = BytesIO(f.read())
        else:
            xsl_obj = StringIO(f.read())

    output = geom_df.to_xml(stylesheet=xsl_obj)

    assert output == xsl_expected


def test_stylesheet_buffered_reader(xsl_row_field_output, mode, geom_df):
    pytest.importorskip("lxml")
    with open(
        xsl_row_field_output, mode, encoding="utf-8" if mode == "r" else None
    ) as f:
        xsl_obj = f.read()

    output = geom_df.to_xml(stylesheet=xsl_obj)

    assert output == xsl_expected


def test_stylesheet_wrong_path(geom_df):
    lxml_etree = pytest.importorskip("lxml.etree")

    xsl = os.path.join("data", "xml", "row_field_output.xslt")

    with pytest.raises(
        lxml_etree.XMLSyntaxError,
        match=("Start tag expected, '<' not found"),
    ):
        geom_df.to_xml(stylesheet=xsl)


@pytest.mark.parametrize("val", ["", b""])
def test_empty_string_stylesheet(val, geom_df):
    lxml_etree = pytest.importorskip("lxml.etree")

    msg = "|".join(
        [
            "Document is empty",
            "Start tag expected, '<' not found",
            # Seen on Mac with lxml 4.9.1
            r"None \(line 0\)",
        ]
    )

    with pytest.raises(lxml_etree.XMLSyntaxError, match=msg):
        geom_df.to_xml(stylesheet=val)


def test_incorrect_xsl_syntax(geom_df):
    lxml_etree = pytest.importorskip("lxml.etree")

    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" encoding="utf-8" indent="yes" >
    <xsl:strip-space elements="*"/>

    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>

    <xsl:template match="row/*">
        <field>
            <xsl:attribute name="field">
                <xsl:value-of select="name()"/>
            </xsl:attribute>
            <xsl:value-of select="text()"/>
        </field>
    </xsl:template>
</xsl:stylesheet>"""

    with pytest.raises(
        lxml_etree.XMLSyntaxError, match=("Opening and ending tag mismatch")
    ):
        geom_df.to_xml(stylesheet=xsl)


def test_incorrect_xsl_eval(geom_df):
    lxml_etree = pytest.importorskip("lxml.etree")

    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" encoding="utf-8" indent="yes" />
    <xsl:strip-space elements="*"/>

    <xsl:template match="@*|node(*)">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>

    <xsl:template match="row/*">
        <field>
            <xsl:attribute name="field">
                <xsl:value-of select="name()"/>
            </xsl:attribute>
            <xsl:value-of select="text()"/>
        </field>
    </xsl:template>
</xsl:stylesheet>"""

    with pytest.raises(lxml_etree.XSLTParseError, match=("failed to compile")):
        geom_df.to_xml(stylesheet=xsl)


def test_incorrect_xsl_apply(geom_df):
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
        with tm.ensure_clean("test.xml") as path:
            geom_df.to_xml(path, stylesheet=xsl)


def test_stylesheet_with_etree(geom_df):
    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" encoding="utf-8" indent="yes" />
    <xsl:strip-space elements="*"/>

    <xsl:template match="@*|node(*)">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>"""

    with pytest.raises(
        ValueError, match=("To use stylesheet, you need lxml installed")
    ):
        geom_df.to_xml(parser="etree", stylesheet=xsl)


def test_style_to_csv(geom_df):
    pytest.importorskip("lxml")
    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="text" indent="yes" />
    <xsl:strip-space elements="*"/>

    <xsl:param name="delim">,</xsl:param>
    <xsl:template match="/data">
        <xsl:text>,shape,degrees,sides&#xa;</xsl:text>
        <xsl:apply-templates select="row"/>
    </xsl:template>

    <xsl:template match="row">
        <xsl:value-of select="concat(index, $delim, shape, $delim,
                                     degrees, $delim, sides)"/>
         <xsl:text>&#xa;</xsl:text>
    </xsl:template>
</xsl:stylesheet>"""

    out_csv = geom_df.to_csv(lineterminator="\n")

    if out_csv is not None:
        out_csv = out_csv.strip()
    out_xml = geom_df.to_xml(stylesheet=xsl)

    assert out_csv == out_xml


def test_style_to_string(geom_df):
    pytest.importorskip("lxml")
    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="text" indent="yes" />
    <xsl:strip-space elements="*"/>

    <xsl:param name="delim"><xsl:text>               </xsl:text></xsl:param>
    <xsl:template match="/data">
        <xsl:text>      shape  degrees  sides&#xa;</xsl:text>
        <xsl:apply-templates select="row"/>
    </xsl:template>

    <xsl:template match="row">
        <xsl:value-of select="concat(index, ' ',
                                     substring($delim, 1, string-length('triangle')
                                               - string-length(shape) + 1),
                                     shape,
                                     substring($delim, 1, string-length(name(degrees))
                                               - string-length(degrees) + 2),
                                     degrees,
                                     substring($delim, 1, string-length(name(sides))
                                               - string-length(sides) + 2),
                                     sides)"/>
         <xsl:text>&#xa;</xsl:text>
    </xsl:template>
</xsl:stylesheet>"""

    out_str = geom_df.to_string()
    out_xml = geom_df.to_xml(na_rep="NaN", stylesheet=xsl)

    assert out_xml == out_str


def test_style_to_json(geom_df):
    pytest.importorskip("lxml")
    xsl = """\
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="text" indent="yes" />
    <xsl:strip-space elements="*"/>

    <xsl:param name="quot">"</xsl:param>

    <xsl:template match="/data">
        <xsl:text>{"shape":{</xsl:text>
        <xsl:apply-templates select="descendant::row/shape"/>
        <xsl:text>},"degrees":{</xsl:text>
        <xsl:apply-templates select="descendant::row/degrees"/>
        <xsl:text>},"sides":{</xsl:text>
        <xsl:apply-templates select="descendant::row/sides"/>
        <xsl:text>}}</xsl:text>
    </xsl:template>

    <xsl:template match="shape|degrees|sides">
        <xsl:variable name="val">
            <xsl:if test = ".=''">
                <xsl:value-of select="'null'"/>
            </xsl:if>
            <xsl:if test = "number(text()) = text()">
                <xsl:value-of select="text()"/>
            </xsl:if>
            <xsl:if test = "number(text()) != text()">
                <xsl:value-of select="concat($quot, text(), $quot)"/>
            </xsl:if>
        </xsl:variable>
        <xsl:value-of select="concat($quot, preceding-sibling::index,
                                     $quot,':', $val)"/>
        <xsl:if test="preceding-sibling::index != //row[last()]/index">
            <xsl:text>,</xsl:text>
        </xsl:if>
    </xsl:template>
</xsl:stylesheet>"""

    out_json = geom_df.to_json()
    out_xml = geom_df.to_xml(stylesheet=xsl)

    assert out_json == out_xml


# COMPRESSION


geom_xml = """\
<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <index>0</index>
    <shape>square</shape>
    <degrees>360</degrees>
    <sides>4.0</sides>
  </row>
  <row>
    <index>1</index>
    <shape>circle</shape>
    <degrees>360</degrees>
    <sides/>
  </row>
  <row>
    <index>2</index>
    <shape>triangle</shape>
    <degrees>180</degrees>
    <sides>3.0</sides>
  </row>
</data>"""


def test_compression_output(parser, compression_only, geom_df):
    with tm.ensure_clean() as path:
        geom_df.to_xml(path, parser=parser, compression=compression_only)

        with get_handle(
            path,
            "r",
            compression=compression_only,
        ) as handle_obj:
            output = handle_obj.handle.read()

    output = equalize_decl(output)

    assert geom_xml == output.strip()


def test_filename_and_suffix_comp(
    parser, compression_only, geom_df, compression_to_extension
):
    compfile = "xml." + compression_to_extension[compression_only]
    with tm.ensure_clean(filename=compfile) as path:
        geom_df.to_xml(path, parser=parser, compression=compression_only)

        with get_handle(
            path,
            "r",
            compression=compression_only,
        ) as handle_obj:
            output = handle_obj.handle.read()

    output = equalize_decl(output)

    assert geom_xml == output.strip()


def test_ea_dtypes(any_numeric_ea_dtype, parser):
    # GH#43903
    expected = """<?xml version='1.0' encoding='utf-8'?>
<data>
  <row>
    <index>0</index>
    <a/>
  </row>
</data>"""
    df = DataFrame({"a": [NA]}).astype(any_numeric_ea_dtype)
    result = df.to_xml(parser=parser)
    assert equalize_decl(result).strip() == expected


def test_unsuported_compression(parser, geom_df):
    with pytest.raises(ValueError, match="Unrecognized compression type"):
        with tm.ensure_clean() as path:
            geom_df.to_xml(path, parser=parser, compression="7z")


# STORAGE OPTIONS


@pytest.mark.single_cpu
def test_s3_permission_output(parser, s3_public_bucket, geom_df):
    s3fs = pytest.importorskip("s3fs")
    pytest.importorskip("lxml")

    with tm.external_error_raised((PermissionError, FileNotFoundError)):
        fs = s3fs.S3FileSystem(anon=True)
        fs.ls(s3_public_bucket.name)

        geom_df.to_xml(
            f"s3://{s3_public_bucket.name}/geom.xml", compression="zip", parser=parser
        )
