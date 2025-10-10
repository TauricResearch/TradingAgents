"""
Tests for the file pandas.io.formats.format, *not* tests for general formatting
of pandas objects.
"""
from datetime import datetime
from io import StringIO
from pathlib import Path
import re
from shutil import get_terminal_size

import numpy as np
import pytest

from pandas._config import using_string_dtype

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    MultiIndex,
    NaT,
    Series,
    Timestamp,
    date_range,
    get_option,
    option_context,
    read_csv,
    reset_option,
)

from pandas.io.formats import printing
import pandas.io.formats.format as fmt


@pytest.fixture(params=["string", "pathlike", "buffer"])
def filepath_or_buffer_id(request):
    """
    A fixture yielding test ids for filepath_or_buffer testing.
    """
    return request.param


@pytest.fixture
def filepath_or_buffer(filepath_or_buffer_id, tmp_path):
    """
    A fixture yielding a string representing a filepath, a path-like object
    and a StringIO buffer. Also checks that buffer is not closed.
    """
    if filepath_or_buffer_id == "buffer":
        buf = StringIO()
        yield buf
        assert not buf.closed
    else:
        assert isinstance(tmp_path, Path)
        if filepath_or_buffer_id == "pathlike":
            yield tmp_path / "foo"
        else:
            yield str(tmp_path / "foo")


@pytest.fixture
def assert_filepath_or_buffer_equals(
    filepath_or_buffer, filepath_or_buffer_id, encoding
):
    """
    Assertion helper for checking filepath_or_buffer.
    """
    if encoding is None:
        encoding = "utf-8"

    def _assert_filepath_or_buffer_equals(expected):
        if filepath_or_buffer_id == "string":
            with open(filepath_or_buffer, encoding=encoding) as f:
                result = f.read()
        elif filepath_or_buffer_id == "pathlike":
            result = filepath_or_buffer.read_text(encoding=encoding)
        elif filepath_or_buffer_id == "buffer":
            result = filepath_or_buffer.getvalue()
        assert result == expected

    return _assert_filepath_or_buffer_equals


def has_info_repr(df):
    r = repr(df)
    c1 = r.split("\n")[0].startswith("<class")
    c2 = r.split("\n")[0].startswith(r"&lt;class")  # _repr_html_
    return c1 or c2


def has_non_verbose_info_repr(df):
    has_info = has_info_repr(df)
    r = repr(df)

    # 1. <class>
    # 2. Index
    # 3. Columns
    # 4. dtype
    # 5. memory usage
    # 6. trailing newline
    nv = len(r.split("\n")) == 6
    return has_info and nv


def has_horizontally_truncated_repr(df):
    try:  # Check header row
        fst_line = np.array(repr(df).splitlines()[0].split())
        cand_col = np.where(fst_line == "...")[0][0]
    except IndexError:
        return False
    # Make sure each row has this ... in the same place
    r = repr(df)
    for ix, _ in enumerate(r.splitlines()):
        if not r.split()[cand_col] == "...":
            return False
    return True


def has_vertically_truncated_repr(df):
    r = repr(df)
    only_dot_row = False
    for row in r.splitlines():
        if re.match(r"^[\.\ ]+$", row):
            only_dot_row = True
    return only_dot_row


def has_truncated_repr(df):
    return has_horizontally_truncated_repr(df) or has_vertically_truncated_repr(df)


def has_doubly_truncated_repr(df):
    return has_horizontally_truncated_repr(df) and has_vertically_truncated_repr(df)


def has_expanded_repr(df):
    r = repr(df)
    for line in r.split("\n"):
        if line.endswith("\\"):
            return True
    return False


class TestDataFrameFormatting:
    def test_repr_truncation(self):
        max_len = 20
        with option_context("display.max_colwidth", max_len):
            df = DataFrame(
                {
                    "A": np.random.default_rng(2).standard_normal(10),
                    "B": [
                        "a"
                        * np.random.default_rng(2).integers(max_len - 1, max_len + 1)
                        for _ in range(10)
                    ],
                }
            )
            r = repr(df)
            r = r[r.find("\n") + 1 :]

            adj = printing.get_adjustment()

            for line, value in zip(r.split("\n"), df["B"]):
                if adj.len(value) + 1 > max_len:
                    assert "..." in line
                else:
                    assert "..." not in line

        with option_context("display.max_colwidth", 999999):
            assert "..." not in repr(df)

        with option_context("display.max_colwidth", max_len + 2):
            assert "..." not in repr(df)

    def test_repr_truncation_preserves_na(self):
        # https://github.com/pandas-dev/pandas/issues/55630
        df = DataFrame({"a": [pd.NA for _ in range(10)]})
        with option_context("display.max_rows", 2, "display.show_dimensions", False):
            assert repr(df) == "       a\n0   <NA>\n..   ...\n9   <NA>"

    def test_max_colwidth_negative_int_raises(self):
        # Deprecation enforced from:
        # https://github.com/pandas-dev/pandas/issues/31532
        with pytest.raises(
            ValueError, match="Value must be a nonnegative integer or None"
        ):
            with option_context("display.max_colwidth", -1):
                pass

    def test_repr_chop_threshold(self):
        df = DataFrame([[0.1, 0.5], [0.5, -0.1]])
        reset_option("display.chop_threshold")  # default None
        assert repr(df) == "     0    1\n0  0.1  0.5\n1  0.5 -0.1"

        with option_context("display.chop_threshold", 0.2):
            assert repr(df) == "     0    1\n0  0.0  0.5\n1  0.5  0.0"

        with option_context("display.chop_threshold", 0.6):
            assert repr(df) == "     0    1\n0  0.0  0.0\n1  0.0  0.0"

        with option_context("display.chop_threshold", None):
            assert repr(df) == "     0    1\n0  0.1  0.5\n1  0.5 -0.1"

    def test_repr_chop_threshold_column_below(self):
        # GH 6839: validation case

        df = DataFrame([[10, 20, 30, 40], [8e-10, -1e-11, 2e-9, -2e-11]]).T

        with option_context("display.chop_threshold", 0):
            assert repr(df) == (
                "      0             1\n"
                "0  10.0  8.000000e-10\n"
                "1  20.0 -1.000000e-11\n"
                "2  30.0  2.000000e-09\n"
                "3  40.0 -2.000000e-11"
            )

        with option_context("display.chop_threshold", 1e-8):
            assert repr(df) == (
                "      0             1\n"
                "0  10.0  0.000000e+00\n"
                "1  20.0  0.000000e+00\n"
                "2  30.0  0.000000e+00\n"
                "3  40.0  0.000000e+00"
            )

        with option_context("display.chop_threshold", 5e-11):
            assert repr(df) == (
                "      0             1\n"
                "0  10.0  8.000000e-10\n"
                "1  20.0  0.000000e+00\n"
                "2  30.0  2.000000e-09\n"
                "3  40.0  0.000000e+00"
            )

    def test_repr_no_backslash(self):
        with option_context("mode.sim_interactive", True):
            df = DataFrame(np.random.default_rng(2).standard_normal((10, 4)))
            assert "\\" not in repr(df)

    def test_expand_frame_repr(self):
        df_small = DataFrame("hello", index=[0], columns=[0])
        df_wide = DataFrame("hello", index=[0], columns=range(10))
        df_tall = DataFrame("hello", index=range(30), columns=range(5))

        with option_context("mode.sim_interactive", True):
            with option_context(
                "display.max_columns",
                10,
                "display.width",
                20,
                "display.max_rows",
                20,
                "display.show_dimensions",
                True,
            ):
                with option_context("display.expand_frame_repr", True):
                    assert not has_truncated_repr(df_small)
                    assert not has_expanded_repr(df_small)
                    assert not has_truncated_repr(df_wide)
                    assert has_expanded_repr(df_wide)
                    assert has_vertically_truncated_repr(df_tall)
                    assert has_expanded_repr(df_tall)

                with option_context("display.expand_frame_repr", False):
                    assert not has_truncated_repr(df_small)
                    assert not has_expanded_repr(df_small)
                    assert not has_horizontally_truncated_repr(df_wide)
                    assert not has_expanded_repr(df_wide)
                    assert has_vertically_truncated_repr(df_tall)
                    assert not has_expanded_repr(df_tall)

    def test_repr_non_interactive(self):
        # in non interactive mode, there can be no dependency on the
        # result of terminal auto size detection
        df = DataFrame("hello", index=range(1000), columns=range(5))

        with option_context(
            "mode.sim_interactive", False, "display.width", 0, "display.max_rows", 5000
        ):
            assert not has_truncated_repr(df)
            assert not has_expanded_repr(df)

    def test_repr_truncates_terminal_size(self, monkeypatch):
        # see gh-21180

        terminal_size = (118, 96)
        monkeypatch.setattr(
            "pandas.io.formats.format.get_terminal_size", lambda: terminal_size
        )

        index = range(5)
        columns = MultiIndex.from_tuples(
            [
                ("This is a long title with > 37 chars.", "cat"),
                ("This is a loooooonger title with > 43 chars.", "dog"),
            ]
        )
        df = DataFrame(1, index=index, columns=columns)

        result = repr(df)

        h1, h2 = result.split("\n")[:2]
        assert "long" in h1
        assert "loooooonger" in h1
        assert "cat" in h2
        assert "dog" in h2

        # regular columns
        df2 = DataFrame({"A" * 41: [1, 2], "B" * 41: [1, 2]})
        result = repr(df2)

        assert df2.columns[0] in result.split("\n")[0]

    def test_repr_truncates_terminal_size_full(self, monkeypatch):
        # GH 22984 ensure entire window is filled
        terminal_size = (80, 24)
        df = DataFrame(np.random.default_rng(2).random((1, 7)))

        monkeypatch.setattr(
            "pandas.io.formats.format.get_terminal_size", lambda: terminal_size
        )
        assert "..." not in str(df)

    def test_repr_truncation_column_size(self):
        # dataframe with last column very wide -> check it is not used to
        # determine size of truncation (...) column
        df = DataFrame(
            {
                "a": [108480, 30830],
                "b": [12345, 12345],
                "c": [12345, 12345],
                "d": [12345, 12345],
                "e": ["a" * 50] * 2,
            }
        )
        assert "..." in str(df)
        assert "    ...    " not in str(df)

    def test_repr_max_columns_max_rows(self):
        term_width, term_height = get_terminal_size()
        if term_width < 10 or term_height < 10:
            pytest.skip(f"terminal size too small, {term_width} x {term_height}")

        def mkframe(n):
            index = [f"{i:05d}" for i in range(n)]
            return DataFrame(0, index, index)

        df6 = mkframe(6)
        df10 = mkframe(10)
        with option_context("mode.sim_interactive", True):
            with option_context("display.width", term_width * 2):
                with option_context("display.max_rows", 5, "display.max_columns", 5):
                    assert not has_expanded_repr(mkframe(4))
                    assert not has_expanded_repr(mkframe(5))
                    assert not has_expanded_repr(df6)
                    assert has_doubly_truncated_repr(df6)

                with option_context("display.max_rows", 20, "display.max_columns", 10):
                    # Out off max_columns boundary, but no extending
                    # since not exceeding width
                    assert not has_expanded_repr(df6)
                    assert not has_truncated_repr(df6)

                with option_context("display.max_rows", 9, "display.max_columns", 10):
                    # out vertical bounds can not result in expanded repr
                    assert not has_expanded_repr(df10)
                    assert has_vertically_truncated_repr(df10)

            # width=None in terminal, auto detection
            with option_context(
                "display.max_columns",
                100,
                "display.max_rows",
                term_width * 20,
                "display.width",
                None,
            ):
                df = mkframe((term_width // 7) - 2)
                assert not has_expanded_repr(df)
                df = mkframe((term_width // 7) + 2)
                printing.pprint_thing(df._repr_fits_horizontal_())
                assert has_expanded_repr(df)

    def test_repr_min_rows(self):
        df = DataFrame({"a": range(20)})

        # default setting no truncation even if above min_rows
        assert ".." not in repr(df)
        assert ".." not in df._repr_html_()

        df = DataFrame({"a": range(61)})

        # default of max_rows 60 triggers truncation if above
        assert ".." in repr(df)
        assert ".." in df._repr_html_()

        with option_context("display.max_rows", 10, "display.min_rows", 4):
            # truncated after first two rows
            assert ".." in repr(df)
            assert "2  " not in repr(df)
            assert "..." in df._repr_html_()
            assert "<td>2</td>" not in df._repr_html_()

        with option_context("display.max_rows", 12, "display.min_rows", None):
            # when set to None, follow value of max_rows
            assert "5    5" in repr(df)
            assert "<td>5</td>" in df._repr_html_()

        with option_context("display.max_rows", 10, "display.min_rows", 12):
            # when set value higher as max_rows, use the minimum
            assert "5    5" not in repr(df)
            assert "<td>5</td>" not in df._repr_html_()

        with option_context("display.max_rows", None, "display.min_rows", 12):
            # max_rows of None -> never truncate
            assert ".." not in repr(df)
            assert ".." not in df._repr_html_()

    def test_str_max_colwidth(self):
        # GH 7856
        df = DataFrame(
            [
                {
                    "a": "foo",
                    "b": "bar",
                    "c": "uncomfortably long line with lots of stuff",
                    "d": 1,
                },
                {"a": "foo", "b": "bar", "c": "stuff", "d": 1},
            ]
        )
        df.set_index(["a", "b", "c"])
        assert str(df) == (
            "     a    b                                           c  d\n"
            "0  foo  bar  uncomfortably long line with lots of stuff  1\n"
            "1  foo  bar                                       stuff  1"
        )
        with option_context("max_colwidth", 20):
            assert str(df) == (
                "     a    b                    c  d\n"
                "0  foo  bar  uncomfortably lo...  1\n"
                "1  foo  bar                stuff  1"
            )

    def test_auto_detect(self):
        term_width, term_height = get_terminal_size()
        fac = 1.05  # Arbitrary large factor to exceed term width
        cols = range(int(term_width * fac))
        index = range(10)
        df = DataFrame(index=index, columns=cols)
        with option_context("mode.sim_interactive", True):
            with option_context("display.max_rows", None):
                with option_context("display.max_columns", None):
                    # Wrap around with None
                    assert has_expanded_repr(df)
            with option_context("display.max_rows", 0):
                with option_context("display.max_columns", 0):
                    # Truncate with auto detection.
                    assert has_horizontally_truncated_repr(df)

            index = range(int(term_height * fac))
            df = DataFrame(index=index, columns=cols)
            with option_context("display.max_rows", 0):
                with option_context("display.max_columns", None):
                    # Wrap around with None
                    assert has_expanded_repr(df)
                    # Truncate vertically
                    assert has_vertically_truncated_repr(df)

            with option_context("display.max_rows", None):
                with option_context("display.max_columns", 0):
                    assert has_horizontally_truncated_repr(df)

    def test_to_string_repr_unicode2(self):
        idx = Index(["abc", "\u03c3a", "aegdvg"])
        ser = Series(np.random.default_rng(2).standard_normal(len(idx)), idx)
        rs = repr(ser).split("\n")
        line_len = len(rs[0])
        for line in rs[1:]:
            try:
                line = line.decode(get_option("display.encoding"))
            except AttributeError:
                pass
            if not line.startswith("dtype:"):
                assert len(line) == line_len

    def test_east_asian_unicode_false(self):
        # not aligned properly because of east asian width

        # mid col
        df = DataFrame(
            {"a": ["あ", "いいい", "う", "ええええええ"], "b": [1, 222, 33333, 4]},
            index=["a", "bb", "c", "ddd"],
        )
        expected = (
            "          a      b\na         あ      1\n"
            "bb      いいい    222\nc         う  33333\n"
            "ddd  ええええええ      4"
        )
        assert repr(df) == expected

        # last col
        df = DataFrame(
            {"a": [1, 222, 33333, 4], "b": ["あ", "いいい", "う", "ええええええ"]},
            index=["a", "bb", "c", "ddd"],
        )
        expected = (
            "         a       b\na        1       あ\n"
            "bb     222     いいい\nc    33333       う\n"
            "ddd      4  ええええええ"
        )
        assert repr(df) == expected

        # all col
        df = DataFrame(
            {
                "a": ["あああああ", "い", "う", "えええ"],
                "b": ["あ", "いいい", "う", "ええええええ"],
            },
            index=["a", "bb", "c", "ddd"],
        )
        expected = (
            "         a       b\na    あああああ       あ\n"
            "bb       い     いいい\nc        う       う\n"
            "ddd    えええ  ええええええ"
        )
        assert repr(df) == expected

        # column name
        df = DataFrame(
            {
                "b": ["あ", "いいい", "う", "ええええええ"],
                "あああああ": [1, 222, 33333, 4],
            },
            index=["a", "bb", "c", "ddd"],
        )
        expected = (
            "          b  あああああ\na         あ      1\n"
            "bb      いいい    222\nc         う  33333\n"
            "ddd  ええええええ      4"
        )
        assert repr(df) == expected

        # index
        df = DataFrame(
            {
                "a": ["あああああ", "い", "う", "えええ"],
                "b": ["あ", "いいい", "う", "ええええええ"],
            },
            index=["あああ", "いいいいいい", "うう", "え"],
        )
        expected = (
            "            a       b\nあああ     あああああ       あ\n"
            "いいいいいい      い     いいい\nうう          う       う\n"
            "え         えええ  ええええええ"
        )
        assert repr(df) == expected

        # index name
        df = DataFrame(
            {
                "a": ["あああああ", "い", "う", "えええ"],
                "b": ["あ", "いいい", "う", "ええええええ"],
            },
            index=Index(["あ", "い", "うう", "え"], name="おおおお"),
        )
        expected = (
            "          a       b\n"
            "おおおお               \n"
            "あ     あああああ       あ\n"
            "い         い     いいい\n"
            "うう        う       う\n"
            "え       えええ  ええええええ"
        )
        assert repr(df) == expected

        # all
        df = DataFrame(
            {
                "あああ": ["あああ", "い", "う", "えええええ"],
                "いいいいい": ["あ", "いいい", "う", "ええ"],
            },
            index=Index(["あ", "いいい", "うう", "え"], name="お"),
        )
        expected = (
            "       あああ いいいいい\n"
            "お               \n"
            "あ      あああ     あ\n"
            "いいい      い   いいい\n"
            "うう       う     う\n"
            "え    えええええ    ええ"
        )
        assert repr(df) == expected

        # MultiIndex
        idx = MultiIndex.from_tuples(
            [("あ", "いい"), ("う", "え"), ("おおお", "かかかか"), ("き", "くく")]
        )
        df = DataFrame(
            {
                "a": ["あああああ", "い", "う", "えええ"],
                "b": ["あ", "いいい", "う", "ええええええ"],
            },
            index=idx,
        )
        expected = (
            "              a       b\n"
            "あ   いい    あああああ       あ\n"
            "う   え         い     いいい\n"
            "おおお かかかか      う       う\n"
            "き   くく      えええ  ええええええ"
        )
        assert repr(df) == expected

        # truncate
        with option_context("display.max_rows", 3, "display.max_columns", 3):
            df = DataFrame(
                {
                    "a": ["あああああ", "い", "う", "えええ"],
                    "b": ["あ", "いいい", "う", "ええええええ"],
                    "c": ["お", "か", "ききき", "くくくくくく"],
                    "ああああ": ["さ", "し", "す", "せ"],
                },
                columns=["a", "b", "c", "ああああ"],
            )

            expected = (
                "        a  ... ああああ\n0   あああああ  ...    さ\n"
                "..    ...  ...  ...\n3     えええ  ...    せ\n"
                "\n[4 rows x 4 columns]"
            )
            assert repr(df) == expected

            df.index = ["あああ", "いいいい", "う", "aaa"]
            expected = (
                "         a  ... ああああ\nあああ  あああああ  ...    さ\n"
                "..     ...  ...  ...\naaa    えええ  ...    せ\n"
                "\n[4 rows x 4 columns]"
            )
            assert repr(df) == expected

    def test_east_asian_unicode_true(self):
        # Enable Unicode option -----------------------------------------
        with option_context("display.unicode.east_asian_width", True):
            # mid col
            df = DataFrame(
                {"a": ["あ", "いいい", "う", "ええええええ"], "b": [1, 222, 33333, 4]},
                index=["a", "bb", "c", "ddd"],
            )
            expected = (
                "                a      b\na              あ      1\n"
                "bb         いいい    222\nc              う  33333\n"
                "ddd  ええええええ      4"
            )
            assert repr(df) == expected

            # last col
            df = DataFrame(
                {"a": [1, 222, 33333, 4], "b": ["あ", "いいい", "う", "ええええええ"]},
                index=["a", "bb", "c", "ddd"],
            )
            expected = (
                "         a             b\na        1            あ\n"
                "bb     222        いいい\nc    33333            う\n"
                "ddd      4  ええええええ"
            )
            assert repr(df) == expected

            # all col
            df = DataFrame(
                {
                    "a": ["あああああ", "い", "う", "えええ"],
                    "b": ["あ", "いいい", "う", "ええええええ"],
                },
                index=["a", "bb", "c", "ddd"],
            )
            expected = (
                "              a             b\n"
                "a    あああああ            あ\n"
                "bb           い        いいい\n"
                "c            う            う\n"
                "ddd      えええ  ええええええ"
            )
            assert repr(df) == expected

            # column name
            df = DataFrame(
                {
                    "b": ["あ", "いいい", "う", "ええええええ"],
                    "あああああ": [1, 222, 33333, 4],
                },
                index=["a", "bb", "c", "ddd"],
            )
            expected = (
                "                b  あああああ\n"
                "a              あ           1\n"
                "bb         いいい         222\n"
                "c              う       33333\n"
                "ddd  ええええええ           4"
            )
            assert repr(df) == expected

            # index
            df = DataFrame(
                {
                    "a": ["あああああ", "い", "う", "えええ"],
                    "b": ["あ", "いいい", "う", "ええええええ"],
                },
                index=["あああ", "いいいいいい", "うう", "え"],
            )
            expected = (
                "                       a             b\n"
                "あああ        あああああ            あ\n"
                "いいいいいい          い        いいい\n"
                "うう                  う            う\n"
                "え                えええ  ええええええ"
            )
            assert repr(df) == expected

            # index name
            df = DataFrame(
                {
                    "a": ["あああああ", "い", "う", "えええ"],
                    "b": ["あ", "いいい", "う", "ええええええ"],
                },
                index=Index(["あ", "い", "うう", "え"], name="おおおお"),
            )
            expected = (
                "                   a             b\n"
                "おおおお                          \n"
                "あ        あああああ            あ\n"
                "い                い        いいい\n"
                "うう              う            う\n"
                "え            えええ  ええええええ"
            )
            assert repr(df) == expected

            # all
            df = DataFrame(
                {
                    "あああ": ["あああ", "い", "う", "えええええ"],
                    "いいいいい": ["あ", "いいい", "う", "ええ"],
                },
                index=Index(["あ", "いいい", "うう", "え"], name="お"),
            )
            expected = (
                "            あああ いいいいい\n"
                "お                           \n"
                "あ          あああ         あ\n"
                "いいい          い     いいい\n"
                "うう            う         う\n"
                "え      えええええ       ええ"
            )
            assert repr(df) == expected

            # MultiIndex
            idx = MultiIndex.from_tuples(
                [("あ", "いい"), ("う", "え"), ("おおお", "かかかか"), ("き", "くく")]
            )
            df = DataFrame(
                {
                    "a": ["あああああ", "い", "う", "えええ"],
                    "b": ["あ", "いいい", "う", "ええええええ"],
                },
                index=idx,
            )
            expected = (
                "                          a             b\n"
                "あ     いい      あああああ            あ\n"
                "う     え                い        いいい\n"
                "おおお かかかか          う            う\n"
                "き     くく          えええ  ええええええ"
            )
            assert repr(df) == expected

            # truncate
            with option_context("display.max_rows", 3, "display.max_columns", 3):
                df = DataFrame(
                    {
                        "a": ["あああああ", "い", "う", "えええ"],
                        "b": ["あ", "いいい", "う", "ええええええ"],
                        "c": ["お", "か", "ききき", "くくくくくく"],
                        "ああああ": ["さ", "し", "す", "せ"],
                    },
                    columns=["a", "b", "c", "ああああ"],
                )

                expected = (
                    "             a  ... ああああ\n"
                    "0   あああああ  ...       さ\n"
                    "..         ...  ...      ...\n"
                    "3       えええ  ...       せ\n"
                    "\n[4 rows x 4 columns]"
                )
                assert repr(df) == expected

                df.index = ["あああ", "いいいい", "う", "aaa"]
                expected = (
                    "                 a  ... ああああ\n"
                    "あああ  あああああ  ...       さ\n"
                    "...            ...  ...      ...\n"
                    "aaa         えええ  ...       せ\n"
                    "\n[4 rows x 4 columns]"
                )
                assert repr(df) == expected

            # ambiguous unicode
            df = DataFrame(
                {
                    "b": ["あ", "いいい", "¡¡", "ええええええ"],
                    "あああああ": [1, 222, 33333, 4],
                },
                index=["a", "bb", "c", "¡¡¡"],
            )
            expected = (
                "                b  あああああ\n"
                "a              あ           1\n"
                "bb         いいい         222\n"
                "c              ¡¡       33333\n"
                "¡¡¡  ええええええ           4"
            )
            assert repr(df) == expected

    def test_to_string_buffer_all_unicode(self):
        buf = StringIO()

        empty = DataFrame({"c/\u03c3": Series(dtype=object)})
        nonempty = DataFrame({"c/\u03c3": Series([1, 2, 3])})

        print(empty, file=buf)
        print(nonempty, file=buf)

        # this should work
        buf.getvalue()

    @pytest.mark.parametrize(
        "index_scalar",
        [
            "a" * 10,
            1,
            Timestamp(2020, 1, 1),
            pd.Period("2020-01-01"),
        ],
    )
    @pytest.mark.parametrize("h", [10, 20])
    @pytest.mark.parametrize("w", [10, 20])
    def test_to_string_truncate_indices(self, index_scalar, h, w):
        with option_context("display.expand_frame_repr", False):
            df = DataFrame(
                index=[index_scalar] * h, columns=[str(i) * 10 for i in range(w)]
            )
            with option_context("display.max_rows", 15):
                if h == 20:
                    assert has_vertically_truncated_repr(df)
                else:
                    assert not has_vertically_truncated_repr(df)
            with option_context("display.max_columns", 15):
                if w == 20:
                    assert has_horizontally_truncated_repr(df)
                else:
                    assert not has_horizontally_truncated_repr(df)
            with option_context("display.max_rows", 15, "display.max_columns", 15):
                if h == 20 and w == 20:
                    assert has_doubly_truncated_repr(df)
                else:
                    assert not has_doubly_truncated_repr(df)

    def test_to_string_truncate_multilevel(self):
        arrays = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            ["one", "two", "one", "two", "one", "two", "one", "two"],
        ]
        df = DataFrame(index=arrays, columns=arrays)
        with option_context("display.max_rows", 7, "display.max_columns", 7):
            assert has_doubly_truncated_repr(df)

    @pytest.mark.parametrize("dtype", ["object", "datetime64[us]"])
    def test_truncate_with_different_dtypes(self, dtype):
        # 11594, 12045
        # when truncated the dtypes of the splits can differ

        # 11594
        ser = Series(
            [datetime(2012, 1, 1)] * 10
            + [datetime(1012, 1, 2)]
            + [datetime(2012, 1, 3)] * 10,
            dtype=dtype,
        )

        with option_context("display.max_rows", 8):
            result = str(ser)
        assert dtype in result

    def test_truncate_with_different_dtypes2(self):
        # 12045
        df = DataFrame({"text": ["some words"] + [None] * 9}, dtype=object)

        with option_context("display.max_rows", 8, "display.max_columns", 3):
            result = str(df)
            assert "None" in result
            assert "NaN" not in result

    def test_truncate_with_different_dtypes_multiindex(self):
        # GH#13000
        df = DataFrame({"Vals": range(100)})
        frame = pd.concat([df], keys=["Sweep"], names=["Sweep", "Index"])
        result = repr(frame)

        result2 = repr(frame.iloc[:5])
        assert result.startswith(result2)

    def test_datetimelike_frame(self):
        # GH 12211
        df = DataFrame({"date": [Timestamp("20130101").tz_localize("UTC")] + [NaT] * 5})

        with option_context("display.max_rows", 5):
            result = str(df)
            assert "2013-01-01 00:00:00+00:00" in result
            assert "NaT" in result
            assert "..." in result
            assert "[6 rows x 1 columns]" in result

        dts = [Timestamp("2011-01-01", tz="US/Eastern")] * 5 + [NaT] * 5
        df = DataFrame({"dt": dts, "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        with option_context("display.max_rows", 5):
            expected = (
                "                          dt   x\n"
                "0  2011-01-01 00:00:00-05:00   1\n"
                "1  2011-01-01 00:00:00-05:00   2\n"
                "..                       ...  ..\n"
                "8                        NaT   9\n"
                "9                        NaT  10\n\n"
                "[10 rows x 2 columns]"
            )
            assert repr(df) == expected

        dts = [NaT] * 5 + [Timestamp("2011-01-01", tz="US/Eastern")] * 5
        df = DataFrame({"dt": dts, "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        with option_context("display.max_rows", 5):
            expected = (
                "                          dt   x\n"
                "0                        NaT   1\n"
                "1                        NaT   2\n"
                "..                       ...  ..\n"
                "8  2011-01-01 00:00:00-05:00   9\n"
                "9  2011-01-01 00:00:00-05:00  10\n\n"
                "[10 rows x 2 columns]"
            )
            assert repr(df) == expected

        dts = [Timestamp("2011-01-01", tz="Asia/Tokyo")] * 5 + [
            Timestamp("2011-01-01", tz="US/Eastern")
        ] * 5
        df = DataFrame({"dt": dts, "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
        with option_context("display.max_rows", 5):
            expected = (
                "                           dt   x\n"
                "0   2011-01-01 00:00:00+09:00   1\n"
                "1   2011-01-01 00:00:00+09:00   2\n"
                "..                        ...  ..\n"
                "8   2011-01-01 00:00:00-05:00   9\n"
                "9   2011-01-01 00:00:00-05:00  10\n\n"
                "[10 rows x 2 columns]"
            )
            assert repr(df) == expected

    @pytest.mark.parametrize(
        "start_date",
        [
            "2017-01-01 23:59:59.999999999",
            "2017-01-01 23:59:59.99999999",
            "2017-01-01 23:59:59.9999999",
            "2017-01-01 23:59:59.999999",
            "2017-01-01 23:59:59.99999",
            "2017-01-01 23:59:59.9999",
        ],
    )
    def test_datetimeindex_highprecision(self, start_date):
        # GH19030
        # Check that high-precision time values for the end of day are
        # included in repr for DatetimeIndex
        df = DataFrame({"A": date_range(start=start_date, freq="D", periods=5)})
        result = str(df)
        assert start_date in result

        dti = date_range(start=start_date, freq="D", periods=5)
        df = DataFrame({"A": range(5)}, index=dti)
        result = str(df.index)
        assert start_date in result

    def test_string_repr_encoding(self, datapath):
        filepath = datapath("io", "parser", "data", "unicode_series.csv")
        df = read_csv(filepath, header=None, encoding="latin1")
        repr(df)
        repr(df[1])

    def test_repr_corner(self):
        # representing infs poses no problems
        df = DataFrame({"foo": [-np.inf, np.inf]})
        repr(df)

    def test_frame_info_encoding(self):
        index = ["'Til There Was You (1997)", "ldum klaka (Cold Fever) (1994)"]
        with option_context("display.max_rows", 1):
            df = DataFrame(columns=["a", "b", "c"], index=index)
            repr(df)
            repr(df.T)

    def test_wide_repr(self):
        with option_context(
            "mode.sim_interactive",
            True,
            "display.show_dimensions",
            True,
            "display.max_columns",
            20,
        ):
            max_cols = get_option("display.max_columns")
            df = DataFrame([["a" * 25] * (max_cols - 1)] * 10)
            with option_context("display.expand_frame_repr", False):
                rep_str = repr(df)

            assert f"10 rows x {max_cols - 1} columns" in rep_str
            with option_context("display.expand_frame_repr", True):
                wide_repr = repr(df)
            assert rep_str != wide_repr

            with option_context("display.width", 120):
                wider_repr = repr(df)
                assert len(wider_repr) < len(wide_repr)

    def test_wide_repr_wide_columns(self):
        with option_context("mode.sim_interactive", True, "display.max_columns", 20):
            df = DataFrame(
                np.random.default_rng(2).standard_normal((5, 3)),
                columns=["a" * 90, "b" * 90, "c" * 90],
            )
            rep_str = repr(df)

            assert len(rep_str.splitlines()) == 20

    def test_wide_repr_named(self):
        with option_context("mode.sim_interactive", True, "display.max_columns", 20):
            max_cols = get_option("display.max_columns")
            df = DataFrame([["a" * 25] * (max_cols - 1)] * 10)
            df.index.name = "DataFrame Index"
            with option_context("display.expand_frame_repr", False):
                rep_str = repr(df)
            with option_context("display.expand_frame_repr", True):
                wide_repr = repr(df)
            assert rep_str != wide_repr

            with option_context("display.width", 150):
                wider_repr = repr(df)
                assert len(wider_repr) < len(wide_repr)

            for line in wide_repr.splitlines()[1::13]:
                assert "DataFrame Index" in line

    def test_wide_repr_multiindex(self):
        with option_context("mode.sim_interactive", True, "display.max_columns", 20):
            midx = MultiIndex.from_arrays([["a" * 5] * 10] * 2)
            max_cols = get_option("display.max_columns")
            df = DataFrame([["a" * 25] * (max_cols - 1)] * 10, index=midx)
            df.index.names = ["Level 0", "Level 1"]
            with option_context("display.expand_frame_repr", False):
                rep_str = repr(df)
            with option_context("display.expand_frame_repr", True):
                wide_repr = repr(df)
            assert rep_str != wide_repr

            with option_context("display.width", 150):
                wider_repr = repr(df)
                assert len(wider_repr) < len(wide_repr)

            for line in wide_repr.splitlines()[1::13]:
                assert "Level 0 Level 1" in line

    def test_wide_repr_multiindex_cols(self):
        with option_context("mode.sim_interactive", True, "display.max_columns", 20):
            max_cols = get_option("display.max_columns")
            midx = MultiIndex.from_arrays([["a" * 5] * 10] * 2)
            mcols = MultiIndex.from_arrays([["b" * 3] * (max_cols - 1)] * 2)
            df = DataFrame(
                [["c" * 25] * (max_cols - 1)] * 10, index=midx, columns=mcols
            )
            df.index.names = ["Level 0", "Level 1"]
            with option_context("display.expand_frame_repr", False):
                rep_str = repr(df)
            with option_context("display.expand_frame_repr", True):
                wide_repr = repr(df)
            assert rep_str != wide_repr

        with option_context("display.width", 150, "display.max_columns", 20):
            wider_repr = repr(df)
            assert len(wider_repr) < len(wide_repr)

    def test_wide_repr_unicode(self):
        with option_context("mode.sim_interactive", True, "display.max_columns", 20):
            max_cols = 20
            df = DataFrame([["a" * 25] * 10] * (max_cols - 1))
            with option_context("display.expand_frame_repr", False):
                rep_str = repr(df)
            with option_context("display.expand_frame_repr", True):
                wide_repr = repr(df)
            assert rep_str != wide_repr

            with option_context("display.width", 150):
                wider_repr = repr(df)
                assert len(wider_repr) < len(wide_repr)

    def test_wide_repr_wide_long_columns(self):
        with option_context("mode.sim_interactive", True):
            df = DataFrame({"a": ["a" * 30, "b" * 30], "b": ["c" * 70, "d" * 80]})

            result = repr(df)
            assert "ccccc" in result
            assert "ddddd" in result

    def test_long_series(self):
        n = 1000
        s = Series(
            np.random.default_rng(2).integers(-50, 50, n),
            index=[f"s{x:04d}" for x in range(n)],
            dtype="int64",
        )

        str_rep = str(s)
        nmatches = len(re.findall("dtype", str_rep))
        assert nmatches == 1

    def test_to_string_ascii_error(self):
        data = [
            (
                "0  ",
                "                        .gitignore ",
                "     5 ",
                " \xe2\x80\xa2\xe2\x80\xa2\xe2\x80\xa2\xe2\x80\xa2\xe2\x80\xa2",
            )
        ]
        df = DataFrame(data)

        # it works!
        repr(df)

    def test_show_dimensions(self):
        df = DataFrame(123, index=range(10, 15), columns=range(30))

        with option_context(
            "display.max_rows",
            10,
            "display.max_columns",
            40,
            "display.width",
            500,
            "display.expand_frame_repr",
            "info",
            "display.show_dimensions",
            True,
        ):
            assert "5 rows" in str(df)
            assert "5 rows" in df._repr_html_()
        with option_context(
            "display.max_rows",
            10,
            "display.max_columns",
            40,
            "display.width",
            500,
            "display.expand_frame_repr",
            "info",
            "display.show_dimensions",
            False,
        ):
            assert "5 rows" not in str(df)
            assert "5 rows" not in df._repr_html_()
        with option_context(
            "display.max_rows",
            2,
            "display.max_columns",
            2,
            "display.width",
            500,
            "display.expand_frame_repr",
            "info",
            "display.show_dimensions",
            "truncate",
        ):
            assert "5 rows" in str(df)
            assert "5 rows" in df._repr_html_()
        with option_context(
            "display.max_rows",
            10,
            "display.max_columns",
            40,
            "display.width",
            500,
            "display.expand_frame_repr",
            "info",
            "display.show_dimensions",
            "truncate",
        ):
            assert "5 rows" not in str(df)
            assert "5 rows" not in df._repr_html_()

    def test_info_repr(self):
        # GH#21746 For tests inside a terminal (i.e. not CI) we need to detect
        # the terminal size to ensure that we try to print something "too big"
        term_width, term_height = get_terminal_size()

        max_rows = 60
        max_cols = 20 + (max(term_width, 80) - 80) // 4
        # Long
        h, w = max_rows + 1, max_cols - 1
        df = DataFrame({k: np.arange(1, 1 + h) for k in np.arange(w)})
        assert has_vertically_truncated_repr(df)
        with option_context("display.large_repr", "info"):
            assert has_info_repr(df)

        # Wide
        h, w = max_rows - 1, max_cols + 1
        df = DataFrame({k: np.arange(1, 1 + h) for k in np.arange(w)})
        assert has_horizontally_truncated_repr(df)
        with option_context(
            "display.large_repr", "info", "display.max_columns", max_cols
        ):
            assert has_info_repr(df)

    def test_info_repr_max_cols(self):
        # GH #6939
        df = DataFrame(np.random.default_rng(2).standard_normal((10, 5)))
        with option_context(
            "display.large_repr",
            "info",
            "display.max_columns",
            1,
            "display.max_info_columns",
            4,
        ):
            assert has_non_verbose_info_repr(df)

        with option_context(
            "display.large_repr",
            "info",
            "display.max_columns",
            1,
            "display.max_info_columns",
            5,
        ):
            assert not has_non_verbose_info_repr(df)

        # FIXME: don't leave commented-out
        # test verbose overrides
        # set_option('display.max_info_columns', 4)  # exceeded

    def test_pprint_pathological_object(self):
        """
        If the test fails, it at least won't hang.
        """

        class A:
            def __getitem__(self, key):
                return 3  # obviously simplified

        df = DataFrame([A()])
        repr(df)  # just don't die

    def test_float_trim_zeros(self):
        vals = [
            2.08430917305e10,
            3.52205017305e10,
            2.30674817305e10,
            2.03954217305e10,
            5.59897817305e10,
        ]
        skip = True
        for line in repr(DataFrame({"A": vals})).split("\n")[:-2]:
            if line.startswith("dtype:"):
                continue
            if _three_digit_exp():
                assert ("+010" in line) or skip
            else:
                assert ("+10" in line) or skip
            skip = False

    @pytest.mark.parametrize(
        "data, expected",
        [
            (["3.50"], "0    3.50\ndtype: object"),
            ([1.20, "1.00"], "0     1.2\n1    1.00\ndtype: object"),
            ([np.nan], "0   NaN\ndtype: float64"),
            ([None], "0    None\ndtype: object"),
            (["3.50", np.nan], "0    3.50\n1     NaN\ndtype: object"),
            ([3.50, np.nan], "0    3.5\n1    NaN\ndtype: float64"),
            ([3.50, np.nan, "3.50"], "0     3.5\n1     NaN\n2    3.50\ndtype: object"),
            ([3.50, None, "3.50"], "0     3.5\n1    None\n2    3.50\ndtype: object"),
        ],
    )
    def test_repr_str_float_truncation(self, data, expected, using_infer_string):
        # GH#38708
        series = Series(data, dtype=object if "3.50" in data else None)
        result = repr(series)
        assert result == expected

    @pytest.mark.parametrize(
        "float_format,expected",
        [
            ("{:,.0f}".format, "0   1,000\n1    test\ndtype: object"),
            ("{:.4f}".format, "0   1000.0000\n1        test\ndtype: object"),
        ],
    )
    def test_repr_float_format_in_object_col(self, float_format, expected):
        # GH#40024
        df = Series([1000.0, "test"])
        with option_context("display.float_format", float_format):
            result = repr(df)

        assert result == expected

    def test_period(self):
        # GH 12615
        df = DataFrame(
            {
                "A": pd.period_range("2013-01", periods=4, freq="M"),
                "B": [
                    pd.Period("2011-01", freq="M"),
                    pd.Period("2011-02-01", freq="D"),
                    pd.Period("2011-03-01 09:00", freq="h"),
                    pd.Period("2011-04", freq="M"),
                ],
                "C": list("abcd"),
            }
        )
        exp = (
            "         A                 B  C\n"
            "0  2013-01           2011-01  a\n"
            "1  2013-02        2011-02-01  b\n"
            "2  2013-03  2011-03-01 09:00  c\n"
            "3  2013-04           2011-04  d"
        )
        assert str(df) == exp

    @pytest.mark.parametrize(
        "length, max_rows, min_rows, expected",
        [
            (10, 10, 10, 10),
            (10, 10, None, 10),
            (10, 8, None, 8),
            (20, 30, 10, 30),  # max_rows > len(frame), hence max_rows
            (50, 30, 10, 10),  # max_rows < len(frame), hence min_rows
            (100, 60, 10, 10),  # same
            (60, 60, 10, 60),  # edge case
            (61, 60, 10, 10),  # edge case
        ],
    )
    def test_max_rows_fitted(self, length, min_rows, max_rows, expected):
        """Check that display logic is correct.

        GH #37359

        See description here:
        https://pandas.pydata.org/docs/dev/user_guide/options.html#frequently-used-options
        """
        formatter = fmt.DataFrameFormatter(
            DataFrame(np.random.default_rng(2).random((length, 3))),
            max_rows=max_rows,
            min_rows=min_rows,
        )
        result = formatter.max_rows_fitted
        assert result == expected


def gen_series_formatting():
    s1 = Series(["a"] * 100)
    s2 = Series(["ab"] * 100)
    s3 = Series(["a", "ab", "abc", "abcd", "abcde", "abcdef"])
    s4 = s3[::-1]
    test_sers = {"onel": s1, "twol": s2, "asc": s3, "desc": s4}
    return test_sers


class TestSeriesFormatting:
    def test_freq_name_separation(self):
        s = Series(
            np.random.default_rng(2).standard_normal(10),
            index=date_range("1/1/2000", periods=10),
            name=0,
        )

        result = repr(s)
        assert "Freq: D, Name: 0" in result

    def test_unicode_name_in_footer(self):
        s = Series([1, 2], name="\u05e2\u05d1\u05e8\u05d9\u05ea")
        sf = fmt.SeriesFormatter(s, name="\u05e2\u05d1\u05e8\u05d9\u05ea")
        sf._get_footer()  # should not raise exception

    @pytest.mark.xfail(using_string_dtype(), reason="Fixup when arrow is default")
    def test_east_asian_unicode_series(self):
        # not aligned properly because of east asian width

        # unicode index
        s = Series(["a", "bb", "CCC", "D"], index=["あ", "いい", "ううう", "ええええ"])
        expected = "".join(
            [
                "あ         a\n",
                "いい       bb\n",
                "ううう     CCC\n",
                "ええええ      D\ndtype: object",
            ]
        )
        assert repr(s) == expected

        # unicode values
        s = Series(["あ", "いい", "ううう", "ええええ"], index=["a", "bb", "c", "ddd"])
        expected = "".join(
            [
                "a         あ\n",
                "bb       いい\n",
                "c       ううう\n",
                "ddd    ええええ\n",
                "dtype: object",
            ]
        )

        assert repr(s) == expected

        # both
        s = Series(
            ["あ", "いい", "ううう", "ええええ"],
            index=["ああ", "いいいい", "う", "えええ"],
        )
        expected = "".join(
            [
                "ああ         あ\n",
                "いいいい      いい\n",
                "う        ううう\n",
                "えええ     ええええ\n",
                "dtype: object",
            ]
        )

        assert repr(s) == expected

        # unicode footer
        s = Series(
            ["あ", "いい", "ううう", "ええええ"],
            index=["ああ", "いいいい", "う", "えええ"],
            name="おおおおおおお",
        )
        expected = (
            "ああ         あ\nいいいい      いい\nう        ううう\n"
            "えええ     ええええ\nName: おおおおおおお, dtype: object"
        )
        assert repr(s) == expected

        # MultiIndex
        idx = MultiIndex.from_tuples(
            [("あ", "いい"), ("う", "え"), ("おおお", "かかかか"), ("き", "くく")]
        )
        s = Series([1, 22, 3333, 44444], index=idx)
        expected = (
            "あ    いい          1\n"
            "う    え          22\n"
            "おおお  かかかか     3333\n"
            "き    くく      44444\ndtype: int64"
        )
        assert repr(s) == expected

        # object dtype, shorter than unicode repr
        s = Series([1, 22, 3333, 44444], index=[1, "AB", np.nan, "あああ"])
        expected = (
            "1          1\nAB        22\nNaN     3333\nあああ    44444\ndtype: int64"
        )
        assert repr(s) == expected

        # object dtype, longer than unicode repr
        s = Series(
            [1, 22, 3333, 44444], index=[1, "AB", Timestamp("2011-01-01"), "あああ"]
        )
        expected = (
            "1                          1\n"
            "AB                        22\n"
            "2011-01-01 00:00:00     3333\n"
            "あああ                    44444\ndtype: int64"
        )
        assert repr(s) == expected

        # truncate
        with option_context("display.max_rows", 3):
            s = Series(["あ", "いい", "ううう", "ええええ"], name="おおおおおおお")

            expected = (
                "0       あ\n     ... \n"
                "3    ええええ\n"
                "Name: おおおおおおお, Length: 4, dtype: object"
            )
            assert repr(s) == expected

            s.index = ["ああ", "いいいい", "う", "えええ"]
            expected = (
                "ああ        あ\n       ... \n"
                "えええ    ええええ\n"
                "Name: おおおおおおお, Length: 4, dtype: object"
            )
            assert repr(s) == expected

        # Enable Unicode option -----------------------------------------
        with option_context("display.unicode.east_asian_width", True):
            # unicode index
            s = Series(
                ["a", "bb", "CCC", "D"],
                index=["あ", "いい", "ううう", "ええええ"],
            )
            expected = (
                "あ            a\nいい         bb\nううう      CCC\n"
                "ええええ      D\ndtype: object"
            )
            assert repr(s) == expected

            # unicode values
            s = Series(
                ["あ", "いい", "ううう", "ええええ"],
                index=["a", "bb", "c", "ddd"],
            )
            expected = (
                "a            あ\nbb         いい\nc        ううう\n"
                "ddd    ええええ\ndtype: object"
            )
            assert repr(s) == expected
            # both
            s = Series(
                ["あ", "いい", "ううう", "ええええ"],
                index=["ああ", "いいいい", "う", "えええ"],
            )
            expected = (
                "ああ              あ\n"
                "いいいい        いい\n"
                "う            ううう\n"
                "えええ      ええええ\ndtype: object"
            )
            assert repr(s) == expected

            # unicode footer
            s = Series(
                ["あ", "いい", "ううう", "ええええ"],
                index=["ああ", "いいいい", "う", "えええ"],
                name="おおおおおおお",
            )
            expected = (
                "ああ              あ\n"
                "いいいい        いい\n"
                "う            ううう\n"
                "えええ      ええええ\n"
                "Name: おおおおおおお, dtype: object"
            )
            assert repr(s) == expected

            # MultiIndex
            idx = MultiIndex.from_tuples(
                [("あ", "いい"), ("う", "え"), ("おおお", "かかかか"), ("き", "くく")]
            )
            s = Series([1, 22, 3333, 44444], index=idx)
            expected = (
                "あ      いい            1\n"
                "う      え             22\n"
                "おおお  かかかか     3333\n"
                "き      くく        44444\n"
                "dtype: int64"
            )
            assert repr(s) == expected

            # object dtype, shorter than unicode repr
            s = Series([1, 22, 3333, 44444], index=[1, "AB", np.nan, "あああ"])
            expected = (
                "1             1\nAB           22\nNaN        3333\n"
                "あああ    44444\ndtype: int64"
            )
            assert repr(s) == expected

            # object dtype, longer than unicode repr
            s = Series(
                [1, 22, 3333, 44444],
                index=[1, "AB", Timestamp("2011-01-01"), "あああ"],
            )
            expected = (
                "1                          1\n"
                "AB                        22\n"
                "2011-01-01 00:00:00     3333\n"
                "あああ                 44444\ndtype: int64"
            )
            assert repr(s) == expected

            # truncate
            with option_context("display.max_rows", 3):
                s = Series(["あ", "いい", "ううう", "ええええ"], name="おおおおおおお")
                expected = (
                    "0          あ\n       ...   \n"
                    "3    ええええ\n"
                    "Name: おおおおおおお, Length: 4, dtype: object"
                )
                assert repr(s) == expected

                s.index = ["ああ", "いいいい", "う", "えええ"]
                expected = (
                    "ああ            あ\n"
                    "            ...   \n"
                    "えええ    ええええ\n"
                    "Name: おおおおおおお, Length: 4, dtype: object"
                )
                assert repr(s) == expected

            # ambiguous unicode
            s = Series(
                ["¡¡", "い¡¡", "ううう", "ええええ"],
                index=["ああ", "¡¡¡¡いい", "¡¡", "えええ"],
            )
            expected = (
                "ああ              ¡¡\n"
                "¡¡¡¡いい        い¡¡\n"
                "¡¡            ううう\n"
                "えええ      ええええ\ndtype: object"
            )
            assert repr(s) == expected

    def test_float_trim_zeros(self):
        vals = [
            2.08430917305e10,
            3.52205017305e10,
            2.30674817305e10,
            2.03954217305e10,
            5.59897817305e10,
        ]
        for line in repr(Series(vals)).split("\n"):
            if line.startswith("dtype:"):
                continue
            if _three_digit_exp():
                assert "+010" in line
            else:
                assert "+10" in line

    @pytest.mark.parametrize(
        "start_date",
        [
            "2017-01-01 23:59:59.999999999",
            "2017-01-01 23:59:59.99999999",
            "2017-01-01 23:59:59.9999999",
            "2017-01-01 23:59:59.999999",
            "2017-01-01 23:59:59.99999",
            "2017-01-01 23:59:59.9999",
        ],
    )
    def test_datetimeindex_highprecision(self, start_date):
        # GH19030
        # Check that high-precision time values for the end of day are
        # included in repr for DatetimeIndex
        s1 = Series(date_range(start=start_date, freq="D", periods=5))
        result = str(s1)
        assert start_date in result

        dti = date_range(start=start_date, freq="D", periods=5)
        s2 = Series(3, index=dti)
        result = str(s2.index)
        assert start_date in result

    def test_mixed_datetime64(self):
        df = DataFrame({"A": [1, 2], "B": ["2012-01-01", "2012-01-02"]})
        df["B"] = pd.to_datetime(df.B)

        result = repr(df.loc[0])
        assert "2012-01-01" in result

    def test_period(self):
        # GH 12615
        index = pd.period_range("2013-01", periods=6, freq="M")
        s = Series(np.arange(6, dtype="int64"), index=index)
        exp = (
            "2013-01    0\n"
            "2013-02    1\n"
            "2013-03    2\n"
            "2013-04    3\n"
            "2013-05    4\n"
            "2013-06    5\n"
            "Freq: M, dtype: int64"
        )
        assert str(s) == exp

        s = Series(index)
        exp = (
            "0    2013-01\n"
            "1    2013-02\n"
            "2    2013-03\n"
            "3    2013-04\n"
            "4    2013-05\n"
            "5    2013-06\n"
            "dtype: period[M]"
        )
        assert str(s) == exp

        # periods with mixed freq
        s = Series(
            [
                pd.Period("2011-01", freq="M"),
                pd.Period("2011-02-01", freq="D"),
                pd.Period("2011-03-01 09:00", freq="h"),
            ]
        )
        exp = (
            "0             2011-01\n1          2011-02-01\n"
            "2    2011-03-01 09:00\ndtype: object"
        )
        assert str(s) == exp

    def test_max_multi_index_display(self):
        # GH 7101

        # doc example (indexing.rst)

        # multi-index
        arrays = [
            ["bar", "bar", "baz", "baz", "foo", "foo", "qux", "qux"],
            ["one", "two", "one", "two", "one", "two", "one", "two"],
        ]
        tuples = list(zip(*arrays))
        index = MultiIndex.from_tuples(tuples, names=["first", "second"])
        s = Series(np.random.default_rng(2).standard_normal(8), index=index)

        with option_context("display.max_rows", 10):
            assert len(str(s).split("\n")) == 10
        with option_context("display.max_rows", 3):
            assert len(str(s).split("\n")) == 5
        with option_context("display.max_rows", 2):
            assert len(str(s).split("\n")) == 5
        with option_context("display.max_rows", 1):
            assert len(str(s).split("\n")) == 4
        with option_context("display.max_rows", 0):
            assert len(str(s).split("\n")) == 10

        # index
        s = Series(np.random.default_rng(2).standard_normal(8), None)

        with option_context("display.max_rows", 10):
            assert len(str(s).split("\n")) == 9
        with option_context("display.max_rows", 3):
            assert len(str(s).split("\n")) == 4
        with option_context("display.max_rows", 2):
            assert len(str(s).split("\n")) == 4
        with option_context("display.max_rows", 1):
            assert len(str(s).split("\n")) == 3
        with option_context("display.max_rows", 0):
            assert len(str(s).split("\n")) == 9

    # Make sure #8532 is fixed
    def test_consistent_format(self):
        s = Series([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0.9999, 1, 1] * 10)
        with option_context("display.max_rows", 10, "display.show_dimensions", False):
            res = repr(s)
        exp = (
            "0      1.0000\n1      1.0000\n2      1.0000\n3      "
            "1.0000\n4      1.0000\n        ...  \n125    "
            "1.0000\n126    1.0000\n127    0.9999\n128    "
            "1.0000\n129    1.0000\ndtype: float64"
        )
        assert res == exp

    def chck_ncols(self, s):
        lines = [
            line for line in repr(s).split("\n") if not re.match(r"[^\.]*\.+", line)
        ][:-1]
        ncolsizes = len({len(line.strip()) for line in lines})
        assert ncolsizes == 1

    @pytest.mark.xfail(using_string_dtype(), reason="change when arrow is default")
    def test_format_explicit(self):
        test_sers = gen_series_formatting()
        with option_context("display.max_rows", 4, "display.show_dimensions", False):
            res = repr(test_sers["onel"])
            exp = "0     a\n1     a\n     ..\n98    a\n99    a\ndtype: object"
            assert exp == res
            res = repr(test_sers["twol"])
            exp = "0     ab\n1     ab\n      ..\n98    ab\n99    ab\ndtype: object"
            assert exp == res
            res = repr(test_sers["asc"])
            exp = (
                "0         a\n1        ab\n      ...  \n4     abcde\n5    "
                "abcdef\ndtype: object"
            )
            assert exp == res
            res = repr(test_sers["desc"])
            exp = (
                "5    abcdef\n4     abcde\n      ...  \n1        ab\n0         "
                "a\ndtype: object"
            )
            assert exp == res

    def test_ncols(self):
        test_sers = gen_series_formatting()
        for s in test_sers.values():
            self.chck_ncols(s)

    def test_max_rows_eq_one(self):
        s = Series(range(10), dtype="int64")
        with option_context("display.max_rows", 1):
            strrepr = repr(s).split("\n")
        exp1 = ["0", "0"]
        res1 = strrepr[0].split()
        assert exp1 == res1
        exp2 = [".."]
        res2 = strrepr[1].split()
        assert exp2 == res2

    def test_truncate_ndots(self):
        def getndots(s):
            return len(re.match(r"[^\.]*(\.*)", s).groups()[0])

        s = Series([0, 2, 3, 6])
        with option_context("display.max_rows", 2):
            strrepr = repr(s).replace("\n", "")
        assert getndots(strrepr) == 2

        s = Series([0, 100, 200, 400])
        with option_context("display.max_rows", 2):
            strrepr = repr(s).replace("\n", "")
        assert getndots(strrepr) == 3

    def test_show_dimensions(self):
        # gh-7117
        s = Series(range(5))

        assert "Length" not in repr(s)

        with option_context("display.max_rows", 4):
            assert "Length" in repr(s)

        with option_context("display.show_dimensions", True):
            assert "Length" in repr(s)

        with option_context("display.max_rows", 4, "display.show_dimensions", False):
            assert "Length" not in repr(s)

    def test_repr_min_rows(self):
        s = Series(range(20))

        # default setting no truncation even if above min_rows
        assert ".." not in repr(s)

        s = Series(range(61))

        # default of max_rows 60 triggers truncation if above
        assert ".." in repr(s)

        with option_context("display.max_rows", 10, "display.min_rows", 4):
            # truncated after first two rows
            assert ".." in repr(s)
            assert "2  " not in repr(s)

        with option_context("display.max_rows", 12, "display.min_rows", None):
            # when set to None, follow value of max_rows
            assert "5      5" in repr(s)

        with option_context("display.max_rows", 10, "display.min_rows", 12):
            # when set value higher as max_rows, use the minimum
            assert "5      5" not in repr(s)

        with option_context("display.max_rows", None, "display.min_rows", 12):
            # max_rows of None -> never truncate
            assert ".." not in repr(s)


class TestGenericArrayFormatter:
    def test_1d_array(self):
        # _GenericArrayFormatter is used on types for which there isn't a dedicated
        # formatter. np.bool_ is one of those types.
        obj = fmt._GenericArrayFormatter(np.array([True, False]))
        res = obj.get_result()
        assert len(res) == 2
        # Results should be right-justified.
        assert res[0] == "  True"
        assert res[1] == " False"

    def test_2d_array(self):
        obj = fmt._GenericArrayFormatter(np.array([[True, False], [False, True]]))
        res = obj.get_result()
        assert len(res) == 2
        assert res[0] == " [True, False]"
        assert res[1] == " [False, True]"

    def test_3d_array(self):
        obj = fmt._GenericArrayFormatter(
            np.array([[[True, True], [False, False]], [[False, True], [True, False]]])
        )
        res = obj.get_result()
        assert len(res) == 2
        assert res[0] == " [[True, True], [False, False]]"
        assert res[1] == " [[False, True], [True, False]]"

    def test_2d_extension_type(self):
        # GH 33770

        # Define a stub extension type with just enough code to run Series.__repr__()
        class DtypeStub(pd.api.extensions.ExtensionDtype):
            @property
            def type(self):
                return np.ndarray

            @property
            def name(self):
                return "DtypeStub"

        class ExtTypeStub(pd.api.extensions.ExtensionArray):
            def __len__(self) -> int:
                return 2

            def __getitem__(self, ix):
                return [ix == 1, ix == 0]

            @property
            def dtype(self):
                return DtypeStub()

        series = Series(ExtTypeStub(), copy=False)
        res = repr(series)  # This line crashed before #33770 was fixed.
        expected = "\n".join(
            ["0    [False True]", "1    [True False]", "dtype: DtypeStub"]
        )
        assert res == expected


def _three_digit_exp():
    return f"{1.7e8:.4g}" == "1.7e+008"


class TestFloatArrayFormatter:
    def test_misc(self):
        obj = fmt.FloatArrayFormatter(np.array([], dtype=np.float64))
        result = obj.get_result()
        assert len(result) == 0

    def test_format(self):
        obj = fmt.FloatArrayFormatter(np.array([12, 0], dtype=np.float64))
        result = obj.get_result()
        assert result[0] == " 12.0"
        assert result[1] == "  0.0"

    def test_output_display_precision_trailing_zeroes(self):
        # Issue #20359: trimming zeros while there is no decimal point

        # Happens when display precision is set to zero
        with option_context("display.precision", 0):
            s = Series([840.0, 4200.0])
            expected_output = "0     840\n1    4200\ndtype: float64"
            assert str(s) == expected_output

    @pytest.mark.parametrize(
        "value,expected",
        [
            ([9.4444], "   0\n0  9"),
            ([0.49], "       0\n0  5e-01"),
            ([10.9999], "    0\n0  11"),
            ([9.5444, 9.6], "    0\n0  10\n1  10"),
            ([0.46, 0.78, -9.9999], "       0\n0  5e-01\n1  8e-01\n2 -1e+01"),
        ],
    )
    def test_set_option_precision(self, value, expected):
        # Issue #30122
        # Precision was incorrectly shown

        with option_context("display.precision", 0):
            df_value = DataFrame(value)
            assert str(df_value) == expected

    def test_output_significant_digits(self):
        # Issue #9764

        # In case default display precision changes:
        with option_context("display.precision", 6):
            # DataFrame example from issue #9764
            d = DataFrame(
                {
                    "col1": [
                        9.999e-8,
                        1e-7,
                        1.0001e-7,
                        2e-7,
                        4.999e-7,
                        5e-7,
                        5.0001e-7,
                        6e-7,
                        9.999e-7,
                        1e-6,
                        1.0001e-6,
                        2e-6,
                        4.999e-6,
                        5e-6,
                        5.0001e-6,
                        6e-6,
                    ]
                }
            )

            expected_output = {
                (0, 6): "           col1\n"
                "0  9.999000e-08\n"
                "1  1.000000e-07\n"
                "2  1.000100e-07\n"
                "3  2.000000e-07\n"
                "4  4.999000e-07\n"
                "5  5.000000e-07",
                (1, 6): "           col1\n"
                "1  1.000000e-07\n"
                "2  1.000100e-07\n"
                "3  2.000000e-07\n"
                "4  4.999000e-07\n"
                "5  5.000000e-07",
                (1, 8): "           col1\n"
                "1  1.000000e-07\n"
                "2  1.000100e-07\n"
                "3  2.000000e-07\n"
                "4  4.999000e-07\n"
                "5  5.000000e-07\n"
                "6  5.000100e-07\n"
                "7  6.000000e-07",
                (8, 16): "            col1\n"
                "8   9.999000e-07\n"
                "9   1.000000e-06\n"
                "10  1.000100e-06\n"
                "11  2.000000e-06\n"
                "12  4.999000e-06\n"
                "13  5.000000e-06\n"
                "14  5.000100e-06\n"
                "15  6.000000e-06",
                (9, 16): "        col1\n"
                "9   0.000001\n"
                "10  0.000001\n"
                "11  0.000002\n"
                "12  0.000005\n"
                "13  0.000005\n"
                "14  0.000005\n"
                "15  0.000006",
            }

            for (start, stop), v in expected_output.items():
                assert str(d[start:stop]) == v

    def test_too_long(self):
        # GH 10451
        with option_context("display.precision", 4):
            # need both a number > 1e6 and something that normally formats to
            # having length > display.precision + 6
            df = DataFrame({"x": [12345.6789]})
            assert str(df) == "            x\n0  12345.6789"
            df = DataFrame({"x": [2e6]})
            assert str(df) == "           x\n0  2000000.0"
            df = DataFrame({"x": [12345.6789, 2e6]})
            assert str(df) == "            x\n0  1.2346e+04\n1  2.0000e+06"


class TestTimedelta64Formatter:
    def test_days(self):
        x = pd.to_timedelta(list(range(5)) + [NaT], unit="D")._values
        result = fmt._Timedelta64Formatter(x).get_result()
        assert result[0].strip() == "0 days"
        assert result[1].strip() == "1 days"

        result = fmt._Timedelta64Formatter(x[1:2]).get_result()
        assert result[0].strip() == "1 days"

        result = fmt._Timedelta64Formatter(x).get_result()
        assert result[0].strip() == "0 days"
        assert result[1].strip() == "1 days"

        result = fmt._Timedelta64Formatter(x[1:2]).get_result()
        assert result[0].strip() == "1 days"

    def test_days_neg(self):
        x = pd.to_timedelta(list(range(5)) + [NaT], unit="D")._values
        result = fmt._Timedelta64Formatter(-x).get_result()
        assert result[0].strip() == "0 days"
        assert result[1].strip() == "-1 days"

    def test_subdays(self):
        y = pd.to_timedelta(list(range(5)) + [NaT], unit="s")._values
        result = fmt._Timedelta64Formatter(y).get_result()
        assert result[0].strip() == "0 days 00:00:00"
        assert result[1].strip() == "0 days 00:00:01"

    def test_subdays_neg(self):
        y = pd.to_timedelta(list(range(5)) + [NaT], unit="s")._values
        result = fmt._Timedelta64Formatter(-y).get_result()
        assert result[0].strip() == "0 days 00:00:00"
        assert result[1].strip() == "-1 days +23:59:59"

    def test_zero(self):
        x = pd.to_timedelta(list(range(1)) + [NaT], unit="D")._values
        result = fmt._Timedelta64Formatter(x).get_result()
        assert result[0].strip() == "0 days"

        x = pd.to_timedelta(list(range(1)), unit="D")._values
        result = fmt._Timedelta64Formatter(x).get_result()
        assert result[0].strip() == "0 days"


class TestDatetime64Formatter:
    def test_mixed(self):
        x = Series([datetime(2013, 1, 1), datetime(2013, 1, 1, 12), NaT])._values
        result = fmt._Datetime64Formatter(x).get_result()
        assert result[0].strip() == "2013-01-01 00:00:00"
        assert result[1].strip() == "2013-01-01 12:00:00"

    def test_dates(self):
        x = Series([datetime(2013, 1, 1), datetime(2013, 1, 2), NaT])._values
        result = fmt._Datetime64Formatter(x).get_result()
        assert result[0].strip() == "2013-01-01"
        assert result[1].strip() == "2013-01-02"

    def test_date_nanos(self):
        x = Series([Timestamp(200)])._values
        result = fmt._Datetime64Formatter(x).get_result()
        assert result[0].strip() == "1970-01-01 00:00:00.000000200"

    def test_dates_display(self):
        # 10170
        # make sure that we are consistently display date formatting
        x = Series(date_range("20130101 09:00:00", periods=5, freq="D"))
        x.iloc[1] = np.nan
        result = fmt._Datetime64Formatter(x._values).get_result()
        assert result[0].strip() == "2013-01-01 09:00:00"
        assert result[1].strip() == "NaT"
        assert result[4].strip() == "2013-01-05 09:00:00"

        x = Series(date_range("20130101 09:00:00", periods=5, freq="s"))
        x.iloc[1] = np.nan
        result = fmt._Datetime64Formatter(x._values).get_result()
        assert result[0].strip() == "2013-01-01 09:00:00"
        assert result[1].strip() == "NaT"
        assert result[4].strip() == "2013-01-01 09:00:04"

        x = Series(date_range("20130101 09:00:00", periods=5, freq="ms"))
        x.iloc[1] = np.nan
        result = fmt._Datetime64Formatter(x._values).get_result()
        assert result[0].strip() == "2013-01-01 09:00:00.000"
        assert result[1].strip() == "NaT"
        assert result[4].strip() == "2013-01-01 09:00:00.004"

        x = Series(date_range("20130101 09:00:00", periods=5, freq="us"))
        x.iloc[1] = np.nan
        result = fmt._Datetime64Formatter(x._values).get_result()
        assert result[0].strip() == "2013-01-01 09:00:00.000000"
        assert result[1].strip() == "NaT"
        assert result[4].strip() == "2013-01-01 09:00:00.000004"

        x = Series(date_range("20130101 09:00:00", periods=5, freq="ns"))
        x.iloc[1] = np.nan
        result = fmt._Datetime64Formatter(x._values).get_result()
        assert result[0].strip() == "2013-01-01 09:00:00.000000000"
        assert result[1].strip() == "NaT"
        assert result[4].strip() == "2013-01-01 09:00:00.000000004"

    def test_datetime64formatter_yearmonth(self):
        x = Series([datetime(2016, 1, 1), datetime(2016, 2, 2)])._values

        def format_func(x):
            return x.strftime("%Y-%m")

        formatter = fmt._Datetime64Formatter(x, formatter=format_func)
        result = formatter.get_result()
        assert result == ["2016-01", "2016-02"]

    def test_datetime64formatter_hoursecond(self):
        x = Series(
            pd.to_datetime(["10:10:10.100", "12:12:12.120"], format="%H:%M:%S.%f")
        )._values

        def format_func(x):
            return x.strftime("%H:%M")

        formatter = fmt._Datetime64Formatter(x, formatter=format_func)
        result = formatter.get_result()
        assert result == ["10:10", "12:12"]

    def test_datetime64formatter_tz_ms(self):
        x = (
            Series(
                np.array(["2999-01-01", "2999-01-02", "NaT"], dtype="datetime64[ms]")
            )
            .dt.tz_localize("US/Pacific")
            ._values
        )
        result = fmt._Datetime64TZFormatter(x).get_result()
        assert result[0].strip() == "2999-01-01 00:00:00-08:00"
        assert result[1].strip() == "2999-01-02 00:00:00-08:00"


class TestFormatPercentiles:
    @pytest.mark.parametrize(
        "percentiles, expected",
        [
            (
                [0.01999, 0.02001, 0.5, 0.666666, 0.9999],
                ["1.999%", "2.001%", "50%", "66.667%", "99.99%"],
            ),
            (
                [0, 0.5, 0.02001, 0.5, 0.666666, 0.9999],
                ["0%", "50%", "2.0%", "50%", "66.67%", "99.99%"],
            ),
            ([0.281, 0.29, 0.57, 0.58], ["28.1%", "29%", "57%", "58%"]),
            ([0.28, 0.29, 0.57, 0.58], ["28%", "29%", "57%", "58%"]),
            (
                [0.9, 0.99, 0.999, 0.9999, 0.99999],
                ["90%", "99%", "99.9%", "99.99%", "99.999%"],
            ),
        ],
    )
    def test_format_percentiles(self, percentiles, expected):
        result = fmt.format_percentiles(percentiles)
        assert result == expected

    @pytest.mark.parametrize(
        "percentiles",
        [
            ([0.1, np.nan, 0.5]),
            ([-0.001, 0.1, 0.5]),
            ([2, 0.1, 0.5]),
            ([0.1, 0.5, "a"]),
        ],
    )
    def test_error_format_percentiles(self, percentiles):
        msg = r"percentiles should all be in the interval \[0,1\]"
        with pytest.raises(ValueError, match=msg):
            fmt.format_percentiles(percentiles)

    def test_format_percentiles_integer_idx(self):
        # Issue #26660
        result = fmt.format_percentiles(np.linspace(0, 1, 10 + 1))
        expected = [
            "0%",
            "10%",
            "20%",
            "30%",
            "40%",
            "50%",
            "60%",
            "70%",
            "80%",
            "90%",
            "100%",
        ]
        assert result == expected


@pytest.mark.parametrize("method", ["to_string", "to_html", "to_latex"])
@pytest.mark.parametrize(
    "encoding, data",
    [(None, "abc"), ("utf-8", "abc"), ("gbk", "造成输出中文显示乱码"), ("foo", "abc")],
)
def test_filepath_or_buffer_arg(
    method,
    filepath_or_buffer,
    assert_filepath_or_buffer_equals,
    encoding,
    data,
    filepath_or_buffer_id,
):
    df = DataFrame([data])
    if method in ["to_latex"]:  # uses styler implementation
        pytest.importorskip("jinja2")

    if filepath_or_buffer_id not in ["string", "pathlike"] and encoding is not None:
        with pytest.raises(
            ValueError, match="buf is not a file name and encoding is specified."
        ):
            getattr(df, method)(buf=filepath_or_buffer, encoding=encoding)
    elif encoding == "foo":
        with pytest.raises(LookupError, match="unknown encoding"):
            getattr(df, method)(buf=filepath_or_buffer, encoding=encoding)
    else:
        expected = getattr(df, method)()
        getattr(df, method)(buf=filepath_or_buffer, encoding=encoding)
        assert_filepath_or_buffer_equals(expected)


@pytest.mark.parametrize("method", ["to_string", "to_html", "to_latex"])
def test_filepath_or_buffer_bad_arg_raises(float_frame, method):
    if method in ["to_latex"]:  # uses styler implementation
        pytest.importorskip("jinja2")
    msg = "buf is not a file name and it has no write method"
    with pytest.raises(TypeError, match=msg):
        getattr(float_frame, method)(buf=object())
