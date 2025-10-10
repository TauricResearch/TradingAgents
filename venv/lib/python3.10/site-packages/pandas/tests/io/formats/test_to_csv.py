import io
import os
import sys
from zipfile import ZipFile

from _csv import Error
import numpy as np
import pytest

import pandas as pd
from pandas import (
    DataFrame,
    Index,
    compat,
)
import pandas._testing as tm


class TestToCSV:
    def test_to_csv_with_single_column(self):
        # see gh-18676, https://bugs.python.org/issue32255
        #
        # Python's CSV library adds an extraneous '""'
        # before the newline when the NaN-value is in
        # the first row. Otherwise, only the newline
        # character is added. This behavior is inconsistent
        # and was patched in https://bugs.python.org/pull_request4672.
        df1 = DataFrame([None, 1])
        expected1 = """\
""
1.0
"""
        with tm.ensure_clean("test.csv") as path:
            df1.to_csv(path, header=None, index=None)
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected1

        df2 = DataFrame([1, None])
        expected2 = """\
1.0
""
"""
        with tm.ensure_clean("test.csv") as path:
            df2.to_csv(path, header=None, index=None)
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected2

    def test_to_csv_default_encoding(self):
        # GH17097
        df = DataFrame({"col": ["AAAAA", "ÄÄÄÄÄ", "ßßßßß", "聞聞聞聞聞"]})

        with tm.ensure_clean("test.csv") as path:
            # the default to_csv encoding is uft-8.
            df.to_csv(path)
            tm.assert_frame_equal(pd.read_csv(path, index_col=0), df)

    def test_to_csv_quotechar(self):
        df = DataFrame({"col": [1, 2]})
        expected = """\
"","col"
"0","1"
"1","2"
"""

        with tm.ensure_clean("test.csv") as path:
            df.to_csv(path, quoting=1)  # 1=QUOTE_ALL
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected

        expected = """\
$$,$col$
$0$,$1$
$1$,$2$
"""

        with tm.ensure_clean("test.csv") as path:
            df.to_csv(path, quoting=1, quotechar="$")
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected

        with tm.ensure_clean("test.csv") as path:
            with pytest.raises(TypeError, match="quotechar"):
                df.to_csv(path, quoting=1, quotechar=None)

    def test_to_csv_doublequote(self):
        df = DataFrame({"col": ['a"a', '"bb"']})
        expected = '''\
"","col"
"0","a""a"
"1","""bb"""
'''

        with tm.ensure_clean("test.csv") as path:
            df.to_csv(path, quoting=1, doublequote=True)  # QUOTE_ALL
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected

        with tm.ensure_clean("test.csv") as path:
            with pytest.raises(Error, match="escapechar"):
                df.to_csv(path, doublequote=False)  # no escapechar set

    def test_to_csv_escapechar(self):
        df = DataFrame({"col": ['a"a', '"bb"']})
        expected = """\
"","col"
"0","a\\"a"
"1","\\"bb\\""
"""

        with tm.ensure_clean("test.csv") as path:  # QUOTE_ALL
            df.to_csv(path, quoting=1, doublequote=False, escapechar="\\")
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected

        df = DataFrame({"col": ["a,a", ",bb,"]})
        expected = """\
,col
0,a\\,a
1,\\,bb\\,
"""

        with tm.ensure_clean("test.csv") as path:
            df.to_csv(path, quoting=3, escapechar="\\")  # QUOTE_NONE
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected

    def test_csv_to_string(self):
        df = DataFrame({"col": [1, 2]})
        expected_rows = [",col", "0,1", "1,2"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.to_csv() == expected

    def test_to_csv_decimal(self):
        # see gh-781
        df = DataFrame({"col1": [1], "col2": ["a"], "col3": [10.1]})

        expected_rows = [",col1,col2,col3", "0,1,a,10.1"]
        expected_default = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.to_csv() == expected_default

        expected_rows = [";col1;col2;col3", "0;1;a;10,1"]
        expected_european_excel = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.to_csv(decimal=",", sep=";") == expected_european_excel

        expected_rows = [",col1,col2,col3", "0,1,a,10.10"]
        expected_float_format_default = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.to_csv(float_format="%.2f") == expected_float_format_default

        expected_rows = [";col1;col2;col3", "0;1;a;10,10"]
        expected_float_format = tm.convert_rows_list_to_csv_str(expected_rows)
        assert (
            df.to_csv(decimal=",", sep=";", float_format="%.2f")
            == expected_float_format
        )

        # see gh-11553: testing if decimal is taken into account for '0.0'
        df = DataFrame({"a": [0, 1.1], "b": [2.2, 3.3], "c": 1})

        expected_rows = ["a,b,c", "0^0,2^2,1", "1^1,3^3,1"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.to_csv(index=False, decimal="^") == expected

        # same but for an index
        assert df.set_index("a").to_csv(decimal="^") == expected

        # same for a multi-index
        assert df.set_index(["a", "b"]).to_csv(decimal="^") == expected

    def test_to_csv_float_format(self):
        # testing if float_format is taken into account for the index
        # GH 11553
        df = DataFrame({"a": [0, 1], "b": [2.2, 3.3], "c": 1})

        expected_rows = ["a,b,c", "0,2.20,1", "1,3.30,1"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.set_index("a").to_csv(float_format="%.2f") == expected

        # same for a multi-index
        assert df.set_index(["a", "b"]).to_csv(float_format="%.2f") == expected

    def test_to_csv_na_rep(self):
        # see gh-11553
        #
        # Testing if NaN values are correctly represented in the index.
        df = DataFrame({"a": [0, np.nan], "b": [0, 1], "c": [2, 3]})
        expected_rows = ["a,b,c", "0.0,0,2", "_,1,3"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)

        assert df.set_index("a").to_csv(na_rep="_") == expected
        assert df.set_index(["a", "b"]).to_csv(na_rep="_") == expected

        # now with an index containing only NaNs
        df = DataFrame({"a": np.nan, "b": [0, 1], "c": [2, 3]})
        expected_rows = ["a,b,c", "_,0,2", "_,1,3"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)

        assert df.set_index("a").to_csv(na_rep="_") == expected
        assert df.set_index(["a", "b"]).to_csv(na_rep="_") == expected

        # check if na_rep parameter does not break anything when no NaN
        df = DataFrame({"a": 0, "b": [0, 1], "c": [2, 3]})
        expected_rows = ["a,b,c", "0,0,2", "0,1,3"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)

        assert df.set_index("a").to_csv(na_rep="_") == expected
        assert df.set_index(["a", "b"]).to_csv(na_rep="_") == expected

        csv = pd.Series(["a", pd.NA, "c"]).to_csv(na_rep="ZZZZZ")
        expected = tm.convert_rows_list_to_csv_str([",0", "0,a", "1,ZZZZZ", "2,c"])
        assert expected == csv

    def test_to_csv_na_rep_nullable_string(self, nullable_string_dtype):
        # GH 29975
        # Make sure full na_rep shows up when a dtype is provided
        expected = tm.convert_rows_list_to_csv_str([",0", "0,a", "1,ZZZZZ", "2,c"])
        csv = pd.Series(["a", pd.NA, "c"], dtype=nullable_string_dtype).to_csv(
            na_rep="ZZZZZ"
        )
        assert expected == csv

    def test_to_csv_date_format(self):
        # GH 10209
        df_sec = DataFrame({"A": pd.date_range("20130101", periods=5, freq="s")})
        df_day = DataFrame({"A": pd.date_range("20130101", periods=5, freq="d")})

        expected_rows = [
            ",A",
            "0,2013-01-01 00:00:00",
            "1,2013-01-01 00:00:01",
            "2,2013-01-01 00:00:02",
            "3,2013-01-01 00:00:03",
            "4,2013-01-01 00:00:04",
        ]
        expected_default_sec = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df_sec.to_csv() == expected_default_sec

        expected_rows = [
            ",A",
            "0,2013-01-01 00:00:00",
            "1,2013-01-02 00:00:00",
            "2,2013-01-03 00:00:00",
            "3,2013-01-04 00:00:00",
            "4,2013-01-05 00:00:00",
        ]
        expected_ymdhms_day = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df_day.to_csv(date_format="%Y-%m-%d %H:%M:%S") == expected_ymdhms_day

        expected_rows = [
            ",A",
            "0,2013-01-01",
            "1,2013-01-01",
            "2,2013-01-01",
            "3,2013-01-01",
            "4,2013-01-01",
        ]
        expected_ymd_sec = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df_sec.to_csv(date_format="%Y-%m-%d") == expected_ymd_sec

        expected_rows = [
            ",A",
            "0,2013-01-01",
            "1,2013-01-02",
            "2,2013-01-03",
            "3,2013-01-04",
            "4,2013-01-05",
        ]
        expected_default_day = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df_day.to_csv() == expected_default_day
        assert df_day.to_csv(date_format="%Y-%m-%d") == expected_default_day

        # see gh-7791
        #
        # Testing if date_format parameter is taken into account
        # for multi-indexed DataFrames.
        df_sec["B"] = 0
        df_sec["C"] = 1

        expected_rows = ["A,B,C", "2013-01-01,0,1.0"]
        expected_ymd_sec = tm.convert_rows_list_to_csv_str(expected_rows)

        df_sec_grouped = df_sec.groupby([pd.Grouper(key="A", freq="1h"), "B"])
        assert df_sec_grouped.mean().to_csv(date_format="%Y-%m-%d") == expected_ymd_sec

    def test_to_csv_different_datetime_formats(self):
        # GH#21734
        df = DataFrame(
            {
                "date": pd.to_datetime("1970-01-01"),
                "datetime": pd.date_range("1970-01-01", periods=2, freq="h"),
            }
        )
        expected_rows = [
            "date,datetime",
            "1970-01-01,1970-01-01 00:00:00",
            "1970-01-01,1970-01-01 01:00:00",
        ]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)
        assert df.to_csv(index=False) == expected

    def test_to_csv_date_format_in_categorical(self):
        # GH#40754
        ser = pd.Series(pd.to_datetime(["2021-03-27", pd.NaT], format="%Y-%m-%d"))
        ser = ser.astype("category")
        expected = tm.convert_rows_list_to_csv_str(["0", "2021-03-27", '""'])
        assert ser.to_csv(index=False) == expected

        ser = pd.Series(
            pd.date_range(
                start="2021-03-27", freq="D", periods=1, tz="Europe/Berlin"
            ).append(pd.DatetimeIndex([pd.NaT]))
        )
        ser = ser.astype("category")
        assert ser.to_csv(index=False, date_format="%Y-%m-%d") == expected

    def test_to_csv_float_ea_float_format(self):
        # GH#45991
        df = DataFrame({"a": [1.1, 2.02, pd.NA, 6.000006], "b": "c"})
        df["a"] = df["a"].astype("Float64")
        result = df.to_csv(index=False, float_format="%.5f")
        expected = tm.convert_rows_list_to_csv_str(
            ["a,b", "1.10000,c", "2.02000,c", ",c", "6.00001,c"]
        )
        assert result == expected

    def test_to_csv_float_ea_no_float_format(self):
        # GH#45991
        df = DataFrame({"a": [1.1, 2.02, pd.NA, 6.000006], "b": "c"})
        df["a"] = df["a"].astype("Float64")
        result = df.to_csv(index=False)
        expected = tm.convert_rows_list_to_csv_str(
            ["a,b", "1.1,c", "2.02,c", ",c", "6.000006,c"]
        )
        assert result == expected

    def test_to_csv_multi_index(self):
        # see gh-6618
        df = DataFrame([1], columns=pd.MultiIndex.from_arrays([[1], [2]]))

        exp_rows = [",1", ",2", "0,1"]
        exp = tm.convert_rows_list_to_csv_str(exp_rows)
        assert df.to_csv() == exp

        exp_rows = ["1", "2", "1"]
        exp = tm.convert_rows_list_to_csv_str(exp_rows)
        assert df.to_csv(index=False) == exp

        df = DataFrame(
            [1],
            columns=pd.MultiIndex.from_arrays([[1], [2]]),
            index=pd.MultiIndex.from_arrays([[1], [2]]),
        )

        exp_rows = [",,1", ",,2", "1,2,1"]
        exp = tm.convert_rows_list_to_csv_str(exp_rows)
        assert df.to_csv() == exp

        exp_rows = ["1", "2", "1"]
        exp = tm.convert_rows_list_to_csv_str(exp_rows)
        assert df.to_csv(index=False) == exp

        df = DataFrame([1], columns=pd.MultiIndex.from_arrays([["foo"], ["bar"]]))

        exp_rows = [",foo", ",bar", "0,1"]
        exp = tm.convert_rows_list_to_csv_str(exp_rows)
        assert df.to_csv() == exp

        exp_rows = ["foo", "bar", "1"]
        exp = tm.convert_rows_list_to_csv_str(exp_rows)
        assert df.to_csv(index=False) == exp

    @pytest.mark.parametrize(
        "ind,expected",
        [
            (
                pd.MultiIndex(levels=[[1.0]], codes=[[0]], names=["x"]),
                "x,data\n1.0,1\n",
            ),
            (
                pd.MultiIndex(
                    levels=[[1.0], [2.0]], codes=[[0], [0]], names=["x", "y"]
                ),
                "x,y,data\n1.0,2.0,1\n",
            ),
        ],
    )
    def test_to_csv_single_level_multi_index(self, ind, expected, frame_or_series):
        # see gh-19589
        obj = frame_or_series(pd.Series([1], ind, name="data"))

        result = obj.to_csv(lineterminator="\n", header=True)
        assert result == expected

    def test_to_csv_string_array_ascii(self):
        # GH 10813
        str_array = [{"names": ["foo", "bar"]}, {"names": ["baz", "qux"]}]
        df = DataFrame(str_array)
        expected_ascii = """\
,names
0,"['foo', 'bar']"
1,"['baz', 'qux']"
"""
        with tm.ensure_clean("str_test.csv") as path:
            df.to_csv(path, encoding="ascii")
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected_ascii

    def test_to_csv_string_array_utf8(self):
        # GH 10813
        str_array = [{"names": ["foo", "bar"]}, {"names": ["baz", "qux"]}]
        df = DataFrame(str_array)
        expected_utf8 = """\
,names
0,"['foo', 'bar']"
1,"['baz', 'qux']"
"""
        with tm.ensure_clean("unicode_test.csv") as path:
            df.to_csv(path, encoding="utf-8")
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected_utf8

    def test_to_csv_string_with_lf(self):
        # GH 20353
        data = {"int": [1, 2, 3], "str_lf": ["abc", "d\nef", "g\nh\n\ni"]}
        df = DataFrame(data)
        with tm.ensure_clean("lf_test.csv") as path:
            # case 1: The default line terminator(=os.linesep)(PR 21406)
            os_linesep = os.linesep.encode("utf-8")
            expected_noarg = (
                b"int,str_lf"
                + os_linesep
                + b"1,abc"
                + os_linesep
                + b'2,"d\nef"'
                + os_linesep
                + b'3,"g\nh\n\ni"'
                + os_linesep
            )
            df.to_csv(path, index=False)
            with open(path, "rb") as f:
                assert f.read() == expected_noarg
        with tm.ensure_clean("lf_test.csv") as path:
            # case 2: LF as line terminator
            expected_lf = b'int,str_lf\n1,abc\n2,"d\nef"\n3,"g\nh\n\ni"\n'
            df.to_csv(path, lineterminator="\n", index=False)
            with open(path, "rb") as f:
                assert f.read() == expected_lf
        with tm.ensure_clean("lf_test.csv") as path:
            # case 3: CRLF as line terminator
            # 'lineterminator' should not change inner element
            expected_crlf = b'int,str_lf\r\n1,abc\r\n2,"d\nef"\r\n3,"g\nh\n\ni"\r\n'
            df.to_csv(path, lineterminator="\r\n", index=False)
            with open(path, "rb") as f:
                assert f.read() == expected_crlf

    def test_to_csv_string_with_crlf(self):
        # GH 20353
        data = {"int": [1, 2, 3], "str_crlf": ["abc", "d\r\nef", "g\r\nh\r\n\r\ni"]}
        df = DataFrame(data)
        with tm.ensure_clean("crlf_test.csv") as path:
            # case 1: The default line terminator(=os.linesep)(PR 21406)
            os_linesep = os.linesep.encode("utf-8")
            expected_noarg = (
                b"int,str_crlf"
                + os_linesep
                + b"1,abc"
                + os_linesep
                + b'2,"d\r\nef"'
                + os_linesep
                + b'3,"g\r\nh\r\n\r\ni"'
                + os_linesep
            )
            df.to_csv(path, index=False)
            with open(path, "rb") as f:
                assert f.read() == expected_noarg
        with tm.ensure_clean("crlf_test.csv") as path:
            # case 2: LF as line terminator
            expected_lf = b'int,str_crlf\n1,abc\n2,"d\r\nef"\n3,"g\r\nh\r\n\r\ni"\n'
            df.to_csv(path, lineterminator="\n", index=False)
            with open(path, "rb") as f:
                assert f.read() == expected_lf
        with tm.ensure_clean("crlf_test.csv") as path:
            # case 3: CRLF as line terminator
            # 'lineterminator' should not change inner element
            expected_crlf = (
                b"int,str_crlf\r\n"
                b"1,abc\r\n"
                b'2,"d\r\nef"\r\n'
                b'3,"g\r\nh\r\n\r\ni"\r\n'
            )
            df.to_csv(path, lineterminator="\r\n", index=False)
            with open(path, "rb") as f:
                assert f.read() == expected_crlf

    def test_to_csv_stdout_file(self, capsys):
        # GH 21561
        df = DataFrame([["foo", "bar"], ["baz", "qux"]], columns=["name_1", "name_2"])
        expected_rows = [",name_1,name_2", "0,foo,bar", "1,baz,qux"]
        expected_ascii = tm.convert_rows_list_to_csv_str(expected_rows)

        df.to_csv(sys.stdout, encoding="ascii")
        captured = capsys.readouterr()

        assert captured.out == expected_ascii
        assert not sys.stdout.closed

    @pytest.mark.xfail(
        compat.is_platform_windows(),
        reason=(
            "Especially in Windows, file stream should not be passed"
            "to csv writer without newline='' option."
            "(https://docs.python.org/3/library/csv.html#csv.writer)"
        ),
    )
    def test_to_csv_write_to_open_file(self):
        # GH 21696
        df = DataFrame({"a": ["x", "y", "z"]})
        expected = """\
manual header
x
y
z
"""
        with tm.ensure_clean("test.txt") as path:
            with open(path, "w", encoding="utf-8") as f:
                f.write("manual header\n")
                df.to_csv(f, header=None, index=None)
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected

    def test_to_csv_write_to_open_file_with_newline_py3(self):
        # see gh-21696
        # see gh-20353
        df = DataFrame({"a": ["x", "y", "z"]})
        expected_rows = ["x", "y", "z"]
        expected = "manual header\n" + tm.convert_rows_list_to_csv_str(expected_rows)
        with tm.ensure_clean("test.txt") as path:
            with open(path, "w", newline="", encoding="utf-8") as f:
                f.write("manual header\n")
                df.to_csv(f, header=None, index=None)

            with open(path, "rb") as f:
                assert f.read() == bytes(expected, "utf-8")

    @pytest.mark.parametrize("to_infer", [True, False])
    @pytest.mark.parametrize("read_infer", [True, False])
    def test_to_csv_compression(
        self, compression_only, read_infer, to_infer, compression_to_extension
    ):
        # see gh-15008
        compression = compression_only

        # We'll complete file extension subsequently.
        filename = "test."
        filename += compression_to_extension[compression]

        df = DataFrame({"A": [1]})

        to_compression = "infer" if to_infer else compression
        read_compression = "infer" if read_infer else compression

        with tm.ensure_clean(filename) as path:
            df.to_csv(path, compression=to_compression)
            result = pd.read_csv(path, index_col=0, compression=read_compression)
            tm.assert_frame_equal(result, df)

    def test_to_csv_compression_dict(self, compression_only):
        # GH 26023
        method = compression_only
        df = DataFrame({"ABC": [1]})
        filename = "to_csv_compress_as_dict."
        extension = {
            "gzip": "gz",
            "zstd": "zst",
        }.get(method, method)
        filename += extension
        with tm.ensure_clean(filename) as path:
            df.to_csv(path, compression={"method": method})
            read_df = pd.read_csv(path, index_col=0)
            tm.assert_frame_equal(read_df, df)

    def test_to_csv_compression_dict_no_method_raises(self):
        # GH 26023
        df = DataFrame({"ABC": [1]})
        compression = {"some_option": True}
        msg = "must have key 'method'"

        with tm.ensure_clean("out.zip") as path:
            with pytest.raises(ValueError, match=msg):
                df.to_csv(path, compression=compression)

    @pytest.mark.parametrize("compression", ["zip", "infer"])
    @pytest.mark.parametrize("archive_name", ["test_to_csv.csv", "test_to_csv.zip"])
    def test_to_csv_zip_arguments(self, compression, archive_name):
        # GH 26023
        df = DataFrame({"ABC": [1]})
        with tm.ensure_clean("to_csv_archive_name.zip") as path:
            df.to_csv(
                path, compression={"method": compression, "archive_name": archive_name}
            )
            with ZipFile(path) as zp:
                assert len(zp.filelist) == 1
                archived_file = zp.filelist[0].filename
                assert archived_file == archive_name

    @pytest.mark.parametrize(
        "filename,expected_arcname",
        [
            ("archive.csv", "archive.csv"),
            ("archive.tsv", "archive.tsv"),
            ("archive.csv.zip", "archive.csv"),
            ("archive.tsv.zip", "archive.tsv"),
            ("archive.zip", "archive"),
        ],
    )
    def test_to_csv_zip_infer_name(self, tmp_path, filename, expected_arcname):
        # GH 39465
        df = DataFrame({"ABC": [1]})
        path = tmp_path / filename
        df.to_csv(path, compression="zip")
        with ZipFile(path) as zp:
            assert len(zp.filelist) == 1
            archived_file = zp.filelist[0].filename
            assert archived_file == expected_arcname

    @pytest.mark.parametrize("df_new_type", ["Int64"])
    def test_to_csv_na_rep_long_string(self, df_new_type):
        # see gh-25099
        df = DataFrame({"c": [float("nan")] * 3})
        df = df.astype(df_new_type)
        expected_rows = ["c", "mynull", "mynull", "mynull"]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)

        result = df.to_csv(index=False, na_rep="mynull", encoding="ascii")

        assert expected == result

    def test_to_csv_timedelta_precision(self):
        # GH 6783
        s = pd.Series([1, 1]).astype("timedelta64[ns]")
        buf = io.StringIO()
        s.to_csv(buf)
        result = buf.getvalue()
        expected_rows = [
            ",0",
            "0,0 days 00:00:00.000000001",
            "1,0 days 00:00:00.000000001",
        ]
        expected = tm.convert_rows_list_to_csv_str(expected_rows)
        assert result == expected

    def test_na_rep_truncated(self):
        # https://github.com/pandas-dev/pandas/issues/31447
        result = pd.Series(range(8, 12)).to_csv(na_rep="-")
        expected = tm.convert_rows_list_to_csv_str([",0", "0,8", "1,9", "2,10", "3,11"])
        assert result == expected

        result = pd.Series([True, False]).to_csv(na_rep="nan")
        expected = tm.convert_rows_list_to_csv_str([",0", "0,True", "1,False"])
        assert result == expected

        result = pd.Series([1.1, 2.2]).to_csv(na_rep=".")
        expected = tm.convert_rows_list_to_csv_str([",0", "0,1.1", "1,2.2"])
        assert result == expected

    @pytest.mark.parametrize("errors", ["surrogatepass", "ignore", "replace"])
    def test_to_csv_errors(self, errors):
        # GH 22610
        data = ["\ud800foo"]
        ser = pd.Series(data, index=Index(data, dtype=object), dtype=object)
        with tm.ensure_clean("test.csv") as path:
            ser.to_csv(path, errors=errors)
        # No use in reading back the data as it is not the same anymore
        # due to the error handling

    @pytest.mark.parametrize("mode", ["wb", "w"])
    def test_to_csv_binary_handle(self, mode):
        """
        Binary file objects should work (if 'mode' contains a 'b') or even without
        it in most cases.

        GH 35058 and GH 19827
        """
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=Index(list("ABCD")),
            index=Index([f"i-{i}" for i in range(30)]),
        )
        with tm.ensure_clean() as path:
            with open(path, mode="w+b") as handle:
                df.to_csv(handle, mode=mode)
            tm.assert_frame_equal(df, pd.read_csv(path, index_col=0))

    @pytest.mark.parametrize("mode", ["wb", "w"])
    def test_to_csv_encoding_binary_handle(self, mode):
        """
        Binary file objects should honor a specified encoding.

        GH 23854 and GH 13068 with binary handles
        """
        # example from GH 23854
        content = "a, b, 🐟".encode("utf-8-sig")
        buffer = io.BytesIO(content)
        df = pd.read_csv(buffer, encoding="utf-8-sig")

        buffer = io.BytesIO()
        df.to_csv(buffer, mode=mode, encoding="utf-8-sig", index=False)
        buffer.seek(0)  # tests whether file handle wasn't closed
        assert buffer.getvalue().startswith(content)

        # example from GH 13068
        with tm.ensure_clean() as path:
            with open(path, "w+b") as handle:
                DataFrame().to_csv(handle, mode=mode, encoding="utf-8-sig")

                handle.seek(0)
                assert handle.read().startswith(b'\xef\xbb\xbf""')


def test_to_csv_iterative_compression_name(compression):
    # GH 38714
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )
    with tm.ensure_clean() as path:
        df.to_csv(path, compression=compression, chunksize=1)
        tm.assert_frame_equal(
            pd.read_csv(path, compression=compression, index_col=0), df
        )


def test_to_csv_iterative_compression_buffer(compression):
    # GH 38714
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )
    with io.BytesIO() as buffer:
        df.to_csv(buffer, compression=compression, chunksize=1)
        buffer.seek(0)
        tm.assert_frame_equal(
            pd.read_csv(buffer, compression=compression, index_col=0), df
        )
        assert not buffer.closed


def test_to_csv_pos_args_deprecation():
    # GH-54229
    df = DataFrame({"a": [1, 2, 3]})
    msg = (
        r"Starting with pandas version 3.0 all arguments of to_csv except for the "
        r"argument 'path_or_buf' will be keyword-only."
    )
    with tm.assert_produces_warning(FutureWarning, match=msg):
        buffer = io.BytesIO()
        df.to_csv(buffer, ";")
