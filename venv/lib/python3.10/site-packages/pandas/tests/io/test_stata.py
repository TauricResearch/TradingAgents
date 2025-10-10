import bz2
import datetime as dt
from datetime import datetime
import gzip
import io
import os
import struct
import tarfile
import zipfile

import numpy as np
import pytest

import pandas.util._test_decorators as td

import pandas as pd
from pandas import CategoricalDtype
import pandas._testing as tm
from pandas.core.frame import (
    DataFrame,
    Series,
)

from pandas.io.parsers import read_csv
from pandas.io.stata import (
    CategoricalConversionWarning,
    InvalidColumnName,
    PossiblePrecisionLoss,
    StataMissingValue,
    StataReader,
    StataWriter,
    StataWriterUTF8,
    ValueLabelTypeMismatch,
    read_stata,
)


@pytest.fixture
def mixed_frame():
    return DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": [1.0, 3.0, 27.0, 81.0],
            "c": ["Atlanta", "Birmingham", "Cincinnati", "Detroit"],
        }
    )


@pytest.fixture
def parsed_114(datapath):
    dta14_114 = datapath("io", "data", "stata", "stata5_114.dta")
    parsed_114 = read_stata(dta14_114, convert_dates=True)
    parsed_114.index.name = "index"
    return parsed_114


class TestStata:
    def read_dta(self, file):
        # Legacy default reader configuration
        return read_stata(file, convert_dates=True)

    def read_csv(self, file):
        return read_csv(file, parse_dates=True)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_read_empty_dta(self, version):
        empty_ds = DataFrame(columns=["unit"])
        # GH 7369, make sure can read a 0-obs dta file
        with tm.ensure_clean() as path:
            empty_ds.to_stata(path, write_index=False, version=version)
            empty_ds2 = read_stata(path)
            tm.assert_frame_equal(empty_ds, empty_ds2)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_read_empty_dta_with_dtypes(self, version):
        # GH 46240
        # Fixing above bug revealed that types are not correctly preserved when
        # writing empty DataFrames
        empty_df_typed = DataFrame(
            {
                "i8": np.array([0], dtype=np.int8),
                "i16": np.array([0], dtype=np.int16),
                "i32": np.array([0], dtype=np.int32),
                "i64": np.array([0], dtype=np.int64),
                "u8": np.array([0], dtype=np.uint8),
                "u16": np.array([0], dtype=np.uint16),
                "u32": np.array([0], dtype=np.uint32),
                "u64": np.array([0], dtype=np.uint64),
                "f32": np.array([0], dtype=np.float32),
                "f64": np.array([0], dtype=np.float64),
            }
        )
        expected = empty_df_typed.copy()
        # No uint# support. Downcast since values in range for int#
        expected["u8"] = expected["u8"].astype(np.int8)
        expected["u16"] = expected["u16"].astype(np.int16)
        expected["u32"] = expected["u32"].astype(np.int32)
        # No int64 supported at all. Downcast since values in range for int32
        expected["u64"] = expected["u64"].astype(np.int32)
        expected["i64"] = expected["i64"].astype(np.int32)

        # GH 7369, make sure can read a 0-obs dta file
        with tm.ensure_clean() as path:
            empty_df_typed.to_stata(path, write_index=False, version=version)
            empty_reread = read_stata(path)
            tm.assert_frame_equal(expected, empty_reread)
            tm.assert_series_equal(expected.dtypes, empty_reread.dtypes)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_read_index_col_none(self, version):
        df = DataFrame({"a": range(5), "b": ["b1", "b2", "b3", "b4", "b5"]})
        # GH 7369, make sure can read a 0-obs dta file
        with tm.ensure_clean() as path:
            df.to_stata(path, write_index=False, version=version)
            read_df = read_stata(path)

        assert isinstance(read_df.index, pd.RangeIndex)
        expected = df.copy()
        expected["a"] = expected["a"].astype(np.int32)
        tm.assert_frame_equal(read_df, expected, check_index_type=True)

    @pytest.mark.parametrize("file", ["stata1_114", "stata1_117"])
    def test_read_dta1(self, file, datapath):
        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = self.read_dta(file)

        # Pandas uses np.nan as missing value.
        # Thus, all columns will be of type float, regardless of their name.
        expected = DataFrame(
            [(np.nan, np.nan, np.nan, np.nan, np.nan)],
            columns=["float_miss", "double_miss", "byte_miss", "int_miss", "long_miss"],
        )

        # this is an oddity as really the nan should be float64, but
        # the casting doesn't fail so need to match stata here
        expected["float_miss"] = expected["float_miss"].astype(np.float32)

        tm.assert_frame_equal(parsed, expected)

    def test_read_dta2(self, datapath):
        expected = DataFrame.from_records(
            [
                (
                    datetime(2006, 11, 19, 23, 13, 20),
                    1479596223000,
                    datetime(2010, 1, 20),
                    datetime(2010, 1, 8),
                    datetime(2010, 1, 1),
                    datetime(1974, 7, 1),
                    datetime(2010, 1, 1),
                    datetime(2010, 1, 1),
                ),
                (
                    datetime(1959, 12, 31, 20, 3, 20),
                    -1479590,
                    datetime(1953, 10, 2),
                    datetime(1948, 6, 10),
                    datetime(1955, 1, 1),
                    datetime(1955, 7, 1),
                    datetime(1955, 1, 1),
                    datetime(2, 1, 1),
                ),
                (pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT, pd.NaT),
            ],
            columns=[
                "datetime_c",
                "datetime_big_c",
                "date",
                "weekly_date",
                "monthly_date",
                "quarterly_date",
                "half_yearly_date",
                "yearly_date",
            ],
        )
        expected["yearly_date"] = expected["yearly_date"].astype("O")

        path1 = datapath("io", "data", "stata", "stata2_114.dta")
        path2 = datapath("io", "data", "stata", "stata2_115.dta")
        path3 = datapath("io", "data", "stata", "stata2_117.dta")

        with tm.assert_produces_warning(UserWarning):
            parsed_114 = self.read_dta(path1)
        with tm.assert_produces_warning(UserWarning):
            parsed_115 = self.read_dta(path2)
        with tm.assert_produces_warning(UserWarning):
            parsed_117 = self.read_dta(path3)
            # FIXME: don't leave commented-out
            # 113 is buggy due to limits of date format support in Stata
            # parsed_113 = self.read_dta(
            # datapath("io", "data", "stata", "stata2_113.dta")
            # )

        # FIXME: don't leave commented-out
        # buggy test because of the NaT comparison on certain platforms
        # Format 113 test fails since it does not support tc and tC formats
        # tm.assert_frame_equal(parsed_113, expected)
        tm.assert_frame_equal(parsed_114, expected, check_datetimelike_compat=True)
        tm.assert_frame_equal(parsed_115, expected, check_datetimelike_compat=True)
        tm.assert_frame_equal(parsed_117, expected, check_datetimelike_compat=True)

    @pytest.mark.parametrize(
        "file", ["stata3_113", "stata3_114", "stata3_115", "stata3_117"]
    )
    def test_read_dta3(self, file, datapath):
        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = self.read_dta(file)

        # match stata here
        expected = self.read_csv(datapath("io", "data", "stata", "stata3.csv"))
        expected = expected.astype(np.float32)
        expected["year"] = expected["year"].astype(np.int16)
        expected["quarter"] = expected["quarter"].astype(np.int8)

        tm.assert_frame_equal(parsed, expected)

    @pytest.mark.parametrize(
        "file", ["stata4_113", "stata4_114", "stata4_115", "stata4_117"]
    )
    def test_read_dta4(self, file, datapath):
        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = self.read_dta(file)

        expected = DataFrame.from_records(
            [
                ["one", "ten", "one", "one", "one"],
                ["two", "nine", "two", "two", "two"],
                ["three", "eight", "three", "three", "three"],
                ["four", "seven", 4, "four", "four"],
                ["five", "six", 5, np.nan, "five"],
                ["six", "five", 6, np.nan, "six"],
                ["seven", "four", 7, np.nan, "seven"],
                ["eight", "three", 8, np.nan, "eight"],
                ["nine", "two", 9, np.nan, "nine"],
                ["ten", "one", "ten", np.nan, "ten"],
            ],
            columns=[
                "fully_labeled",
                "fully_labeled2",
                "incompletely_labeled",
                "labeled_with_missings",
                "float_labelled",
            ],
        )

        # these are all categoricals
        for col in expected:
            orig = expected[col].copy()

            categories = np.asarray(expected["fully_labeled"][orig.notna()])
            if col == "incompletely_labeled":
                categories = orig

            cat = orig.astype("category")._values
            cat = cat.set_categories(categories, ordered=True)
            cat.categories.rename(None, inplace=True)

            expected[col] = cat

        # stata doesn't save .category metadata
        tm.assert_frame_equal(parsed, expected)

    # File containing strls
    def test_read_dta12(self, datapath):
        parsed_117 = self.read_dta(datapath("io", "data", "stata", "stata12_117.dta"))
        expected = DataFrame.from_records(
            [
                [1, "abc", "abcdefghi"],
                [3, "cba", "qwertywertyqwerty"],
                [93, "", "strl"],
            ],
            columns=["x", "y", "z"],
        )

        tm.assert_frame_equal(parsed_117, expected, check_dtype=False)

    def test_read_dta18(self, datapath):
        parsed_118 = self.read_dta(datapath("io", "data", "stata", "stata14_118.dta"))
        parsed_118["Bytes"] = parsed_118["Bytes"].astype("O")
        expected = DataFrame.from_records(
            [
                ["Cat", "Bogota", "Bogotá", 1, 1.0, "option b Ünicode", 1.0],
                ["Dog", "Boston", "Uzunköprü", np.nan, np.nan, np.nan, np.nan],
                ["Plane", "Rome", "Tromsø", 0, 0.0, "option a", 0.0],
                ["Potato", "Tokyo", "Elâzığ", -4, 4.0, 4, 4],  # noqa: RUF001
                ["", "", "", 0, 0.3332999, "option a", 1 / 3.0],
            ],
            columns=[
                "Things",
                "Cities",
                "Unicode_Cities_Strl",
                "Ints",
                "Floats",
                "Bytes",
                "Longs",
            ],
        )
        expected["Floats"] = expected["Floats"].astype(np.float32)
        for col in parsed_118.columns:
            tm.assert_almost_equal(parsed_118[col], expected[col])

        with StataReader(datapath("io", "data", "stata", "stata14_118.dta")) as rdr:
            vl = rdr.variable_labels()
            vl_expected = {
                "Unicode_Cities_Strl": "Here are some strls with Ünicode chars",
                "Longs": "long data",
                "Things": "Here are some things",
                "Bytes": "byte data",
                "Ints": "int data",
                "Cities": "Here are some cities",
                "Floats": "float data",
            }
            tm.assert_dict_equal(vl, vl_expected)

            assert rdr.data_label == "This is a  Ünicode data label"

    def test_read_write_dta5(self):
        original = DataFrame(
            [(np.nan, np.nan, np.nan, np.nan, np.nan)],
            columns=["float_miss", "double_miss", "byte_miss", "int_miss", "long_miss"],
        )
        original.index.name = "index"

        with tm.ensure_clean() as path:
            original.to_stata(path, convert_dates=None)
            written_and_read_again = self.read_dta(path)

        expected = original.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    def test_write_dta6(self, datapath):
        original = self.read_csv(datapath("io", "data", "stata", "stata3.csv"))
        original.index.name = "index"
        original.index = original.index.astype(np.int32)
        original["year"] = original["year"].astype(np.int32)
        original["quarter"] = original["quarter"].astype(np.int32)

        with tm.ensure_clean() as path:
            original.to_stata(path, convert_dates=None)
            written_and_read_again = self.read_dta(path)
            tm.assert_frame_equal(
                written_and_read_again.set_index("index"),
                original,
                check_index_type=False,
            )

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_read_write_dta10(self, version, using_infer_string):
        original = DataFrame(
            data=[["string", "object", 1, 1.1, np.datetime64("2003-12-25")]],
            columns=["string", "object", "integer", "floating", "datetime"],
        )
        original["object"] = Series(original["object"], dtype=object)
        original.index.name = "index"
        original.index = original.index.astype(np.int32)
        original["integer"] = original["integer"].astype(np.int32)

        with tm.ensure_clean() as path:
            original.to_stata(path, convert_dates={"datetime": "tc"}, version=version)
            written_and_read_again = self.read_dta(path)

        expected = original.copy()
        if using_infer_string:
            expected["object"] = expected["object"].astype("str")

        # original.index is np.int32, read index is np.int64
        tm.assert_frame_equal(
            written_and_read_again.set_index("index"),
            expected,
            check_index_type=False,
        )

    def test_stata_doc_examples(self):
        with tm.ensure_clean() as path:
            df = DataFrame(
                np.random.default_rng(2).standard_normal((10, 2)), columns=list("AB")
            )
            df.to_stata(path)

    def test_write_preserves_original(self):
        # 9795

        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, 4)), columns=list("abcd")
        )
        df.loc[2, "a":"c"] = np.nan
        df_copy = df.copy()
        with tm.ensure_clean() as path:
            df.to_stata(path, write_index=False)
        tm.assert_frame_equal(df, df_copy)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_encoding(self, version, datapath):
        # GH 4626, proper encoding handling
        raw = read_stata(datapath("io", "data", "stata", "stata1_encoding.dta"))
        encoded = read_stata(datapath("io", "data", "stata", "stata1_encoding.dta"))
        result = encoded.kreis1849[0]

        expected = raw.kreis1849[0]
        assert result == expected
        assert isinstance(result, str)

        with tm.ensure_clean() as path:
            encoded.to_stata(path, write_index=False, version=version)
            reread_encoded = read_stata(path)
            tm.assert_frame_equal(encoded, reread_encoded)

    def test_read_write_dta11(self):
        original = DataFrame(
            [(1, 2, 3, 4)],
            columns=[
                "good",
                "b\u00E4d",
                "8number",
                "astringwithmorethan32characters______",
            ],
        )
        formatted = DataFrame(
            [(1, 2, 3, 4)],
            columns=["good", "b_d", "_8number", "astringwithmorethan32characters_"],
        )
        formatted.index.name = "index"
        formatted = formatted.astype(np.int32)

        with tm.ensure_clean() as path:
            with tm.assert_produces_warning(InvalidColumnName):
                original.to_stata(path, convert_dates=None)

            written_and_read_again = self.read_dta(path)

        expected = formatted.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_read_write_dta12(self, version):
        original = DataFrame(
            [(1, 2, 3, 4, 5, 6)],
            columns=[
                "astringwithmorethan32characters_1",
                "astringwithmorethan32characters_2",
                "+",
                "-",
                "short",
                "delete",
            ],
        )
        formatted = DataFrame(
            [(1, 2, 3, 4, 5, 6)],
            columns=[
                "astringwithmorethan32characters_",
                "_0astringwithmorethan32character",
                "_",
                "_1_",
                "_short",
                "_delete",
            ],
        )
        formatted.index.name = "index"
        formatted = formatted.astype(np.int32)

        with tm.ensure_clean() as path:
            with tm.assert_produces_warning(InvalidColumnName):
                original.to_stata(path, convert_dates=None, version=version)
                # should get a warning for that format.

            written_and_read_again = self.read_dta(path)

        expected = formatted.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    def test_read_write_dta13(self):
        s1 = Series(2**9, dtype=np.int16)
        s2 = Series(2**17, dtype=np.int32)
        s3 = Series(2**33, dtype=np.int64)
        original = DataFrame({"int16": s1, "int32": s2, "int64": s3})
        original.index.name = "index"

        formatted = original
        formatted["int64"] = formatted["int64"].astype(np.float64)

        with tm.ensure_clean() as path:
            original.to_stata(path)
            written_and_read_again = self.read_dta(path)

        expected = formatted.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    @pytest.mark.parametrize(
        "file", ["stata5_113", "stata5_114", "stata5_115", "stata5_117"]
    )
    def test_read_write_reread_dta14(self, file, parsed_114, version, datapath):
        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = self.read_dta(file)
        parsed.index.name = "index"

        tm.assert_frame_equal(parsed_114, parsed)

        with tm.ensure_clean() as path:
            parsed_114.to_stata(path, convert_dates={"date_td": "td"}, version=version)
            written_and_read_again = self.read_dta(path)

        expected = parsed_114.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    @pytest.mark.parametrize(
        "file", ["stata6_113", "stata6_114", "stata6_115", "stata6_117"]
    )
    def test_read_write_reread_dta15(self, file, datapath):
        expected = self.read_csv(datapath("io", "data", "stata", "stata6.csv"))
        expected["byte_"] = expected["byte_"].astype(np.int8)
        expected["int_"] = expected["int_"].astype(np.int16)
        expected["long_"] = expected["long_"].astype(np.int32)
        expected["float_"] = expected["float_"].astype(np.float32)
        expected["double_"] = expected["double_"].astype(np.float64)
        expected["date_td"] = expected["date_td"].apply(
            datetime.strptime, args=("%Y-%m-%d",)
        )

        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = self.read_dta(file)

        tm.assert_frame_equal(expected, parsed)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_timestamp_and_label(self, version):
        original = DataFrame([(1,)], columns=["variable"])
        time_stamp = datetime(2000, 2, 29, 14, 21)
        data_label = "This is a data file."
        with tm.ensure_clean() as path:
            original.to_stata(
                path, time_stamp=time_stamp, data_label=data_label, version=version
            )

            with StataReader(path) as reader:
                assert reader.time_stamp == "29 Feb 2000 14:21"
                assert reader.data_label == data_label

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_invalid_timestamp(self, version):
        original = DataFrame([(1,)], columns=["variable"])
        time_stamp = "01 Jan 2000, 00:00:00"
        with tm.ensure_clean() as path:
            msg = "time_stamp should be datetime type"
            with pytest.raises(ValueError, match=msg):
                original.to_stata(path, time_stamp=time_stamp, version=version)
            assert not os.path.isfile(path)

    def test_numeric_column_names(self):
        original = DataFrame(np.reshape(np.arange(25.0), (5, 5)))
        original.index.name = "index"
        with tm.ensure_clean() as path:
            # should get a warning for that format.
            with tm.assert_produces_warning(InvalidColumnName):
                original.to_stata(path)

            written_and_read_again = self.read_dta(path)

        written_and_read_again = written_and_read_again.set_index("index")
        columns = list(written_and_read_again.columns)
        convert_col_name = lambda x: int(x[1])
        written_and_read_again.columns = map(convert_col_name, columns)

        expected = original.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(expected, written_and_read_again)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_nan_to_missing_value(self, version):
        s1 = Series(np.arange(4.0), dtype=np.float32)
        s2 = Series(np.arange(4.0), dtype=np.float64)
        s1[::2] = np.nan
        s2[1::2] = np.nan
        original = DataFrame({"s1": s1, "s2": s2})
        original.index.name = "index"

        with tm.ensure_clean() as path:
            original.to_stata(path, version=version)
            written_and_read_again = self.read_dta(path)

        written_and_read_again = written_and_read_again.set_index("index")
        expected = original.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again, expected)

    def test_no_index(self):
        columns = ["x", "y"]
        original = DataFrame(np.reshape(np.arange(10.0), (5, 2)), columns=columns)
        original.index.name = "index_not_written"
        with tm.ensure_clean() as path:
            original.to_stata(path, write_index=False)
            written_and_read_again = self.read_dta(path)
            with pytest.raises(KeyError, match=original.index.name):
                written_and_read_again["index_not_written"]

    def test_string_no_dates(self):
        s1 = Series(["a", "A longer string"])
        s2 = Series([1.0, 2.0], dtype=np.float64)
        original = DataFrame({"s1": s1, "s2": s2})
        original.index.name = "index"
        with tm.ensure_clean() as path:
            original.to_stata(path)
            written_and_read_again = self.read_dta(path)

        expected = original.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    def test_large_value_conversion(self):
        s0 = Series([1, 99], dtype=np.int8)
        s1 = Series([1, 127], dtype=np.int8)
        s2 = Series([1, 2**15 - 1], dtype=np.int16)
        s3 = Series([1, 2**63 - 1], dtype=np.int64)
        original = DataFrame({"s0": s0, "s1": s1, "s2": s2, "s3": s3})
        original.index.name = "index"
        with tm.ensure_clean() as path:
            with tm.assert_produces_warning(PossiblePrecisionLoss):
                original.to_stata(path)

            written_and_read_again = self.read_dta(path)

        modified = original.copy()
        modified["s1"] = Series(modified["s1"], dtype=np.int16)
        modified["s2"] = Series(modified["s2"], dtype=np.int32)
        modified["s3"] = Series(modified["s3"], dtype=np.float64)
        modified.index = original.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), modified)

    def test_dates_invalid_column(self):
        original = DataFrame([datetime(2006, 11, 19, 23, 13, 20)])
        original.index.name = "index"
        with tm.ensure_clean() as path:
            with tm.assert_produces_warning(InvalidColumnName):
                original.to_stata(path, convert_dates={0: "tc"})

            written_and_read_again = self.read_dta(path)

        modified = original.copy()
        modified.columns = ["_0"]
        modified.index = original.index.astype(np.int32)
        tm.assert_frame_equal(written_and_read_again.set_index("index"), modified)

    def test_105(self, datapath):
        # Data obtained from:
        # http://go.worldbank.org/ZXY29PVJ21
        dpath = datapath("io", "data", "stata", "S4_EDUC1.dta")
        df = read_stata(dpath)
        df0 = [[1, 1, 3, -2], [2, 1, 2, -2], [4, 1, 1, -2]]
        df0 = DataFrame(df0)
        df0.columns = ["clustnum", "pri_schl", "psch_num", "psch_dis"]
        df0["clustnum"] = df0["clustnum"].astype(np.int16)
        df0["pri_schl"] = df0["pri_schl"].astype(np.int8)
        df0["psch_num"] = df0["psch_num"].astype(np.int8)
        df0["psch_dis"] = df0["psch_dis"].astype(np.float32)
        tm.assert_frame_equal(df.head(3), df0)

    def test_value_labels_old_format(self, datapath):
        # GH 19417
        #
        # Test that value_labels() returns an empty dict if the file format
        # predates supporting value labels.
        dpath = datapath("io", "data", "stata", "S4_EDUC1.dta")
        with StataReader(dpath) as reader:
            assert reader.value_labels() == {}

    def test_date_export_formats(self):
        columns = ["tc", "td", "tw", "tm", "tq", "th", "ty"]
        conversions = {c: c for c in columns}
        data = [datetime(2006, 11, 20, 23, 13, 20)] * len(columns)
        original = DataFrame([data], columns=columns)
        original.index.name = "index"
        expected_values = [
            datetime(2006, 11, 20, 23, 13, 20),  # Time
            datetime(2006, 11, 20),  # Day
            datetime(2006, 11, 19),  # Week
            datetime(2006, 11, 1),  # Month
            datetime(2006, 10, 1),  # Quarter year
            datetime(2006, 7, 1),  # Half year
            datetime(2006, 1, 1),
        ]  # Year

        expected = DataFrame(
            [expected_values],
            index=pd.Index([0], dtype=np.int32, name="index"),
            columns=columns,
        )

        with tm.ensure_clean() as path:
            original.to_stata(path, convert_dates=conversions)
            written_and_read_again = self.read_dta(path)

        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    def test_write_missing_strings(self):
        original = DataFrame([["1"], [None]], columns=["foo"])

        expected = DataFrame(
            [["1"], [""]],
            index=pd.Index([0, 1], dtype=np.int32, name="index"),
            columns=["foo"],
        )

        with tm.ensure_clean() as path:
            original.to_stata(path)
            written_and_read_again = self.read_dta(path)

        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    @pytest.mark.parametrize("byteorder", [">", "<"])
    def test_bool_uint(self, byteorder, version):
        s0 = Series([0, 1, True], dtype=np.bool_)
        s1 = Series([0, 1, 100], dtype=np.uint8)
        s2 = Series([0, 1, 255], dtype=np.uint8)
        s3 = Series([0, 1, 2**15 - 100], dtype=np.uint16)
        s4 = Series([0, 1, 2**16 - 1], dtype=np.uint16)
        s5 = Series([0, 1, 2**31 - 100], dtype=np.uint32)
        s6 = Series([0, 1, 2**32 - 1], dtype=np.uint32)

        original = DataFrame(
            {"s0": s0, "s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5, "s6": s6}
        )
        original.index.name = "index"
        expected = original.copy()
        expected.index = original.index.astype(np.int32)
        expected_types = (
            np.int8,
            np.int8,
            np.int16,
            np.int16,
            np.int32,
            np.int32,
            np.float64,
        )
        for c, t in zip(expected.columns, expected_types):
            expected[c] = expected[c].astype(t)

        with tm.ensure_clean() as path:
            original.to_stata(path, byteorder=byteorder, version=version)
            written_and_read_again = self.read_dta(path)

        written_and_read_again = written_and_read_again.set_index("index")
        tm.assert_frame_equal(written_and_read_again, expected)

    def test_variable_labels(self, datapath):
        with StataReader(datapath("io", "data", "stata", "stata7_115.dta")) as rdr:
            sr_115 = rdr.variable_labels()
        with StataReader(datapath("io", "data", "stata", "stata7_117.dta")) as rdr:
            sr_117 = rdr.variable_labels()
        keys = ("var1", "var2", "var3")
        labels = ("label1", "label2", "label3")
        for k, v in sr_115.items():
            assert k in sr_117
            assert v == sr_117[k]
            assert k in keys
            assert v in labels

    def test_minimal_size_col(self):
        str_lens = (1, 100, 244)
        s = {}
        for str_len in str_lens:
            s["s" + str(str_len)] = Series(
                ["a" * str_len, "b" * str_len, "c" * str_len]
            )
        original = DataFrame(s)
        with tm.ensure_clean() as path:
            original.to_stata(path, write_index=False)

            with StataReader(path) as sr:
                sr._ensure_open()  # The `_*list` variables are initialized here
                for variable, fmt, typ in zip(sr._varlist, sr._fmtlist, sr._typlist):
                    assert int(variable[1:]) == int(fmt[1:-1])
                    assert int(variable[1:]) == typ

    def test_excessively_long_string(self):
        str_lens = (1, 244, 500)
        s = {}
        for str_len in str_lens:
            s["s" + str(str_len)] = Series(
                ["a" * str_len, "b" * str_len, "c" * str_len]
            )
        original = DataFrame(s)
        msg = (
            r"Fixed width strings in Stata \.dta files are limited to 244 "
            r"\(or fewer\)\ncharacters\.  Column 's500' does not satisfy "
            r"this restriction\. Use the\n'version=117' parameter to write "
            r"the newer \(Stata 13 and later\) format\."
        )
        with pytest.raises(ValueError, match=msg):
            with tm.ensure_clean() as path:
                original.to_stata(path)

    def test_missing_value_generator(self):
        types = ("b", "h", "l")
        df = DataFrame([[0.0]], columns=["float_"])
        with tm.ensure_clean() as path:
            df.to_stata(path)
            with StataReader(path) as rdr:
                valid_range = rdr.VALID_RANGE
        expected_values = ["." + chr(97 + i) for i in range(26)]
        expected_values.insert(0, ".")
        for t in types:
            offset = valid_range[t][1]
            for i in range(27):
                val = StataMissingValue(offset + 1 + i)
                assert val.string == expected_values[i]

        # Test extremes for floats
        val = StataMissingValue(struct.unpack("<f", b"\x00\x00\x00\x7f")[0])
        assert val.string == "."
        val = StataMissingValue(struct.unpack("<f", b"\x00\xd0\x00\x7f")[0])
        assert val.string == ".z"

        # Test extremes for floats
        val = StataMissingValue(
            struct.unpack("<d", b"\x00\x00\x00\x00\x00\x00\xe0\x7f")[0]
        )
        assert val.string == "."
        val = StataMissingValue(
            struct.unpack("<d", b"\x00\x00\x00\x00\x00\x1a\xe0\x7f")[0]
        )
        assert val.string == ".z"

    @pytest.mark.parametrize("file", ["stata8_113", "stata8_115", "stata8_117"])
    def test_missing_value_conversion(self, file, datapath):
        columns = ["int8_", "int16_", "int32_", "float32_", "float64_"]
        smv = StataMissingValue(101)
        keys = sorted(smv.MISSING_VALUES.keys())
        data = []
        for i in range(27):
            row = [StataMissingValue(keys[i + (j * 27)]) for j in range(5)]
            data.append(row)
        expected = DataFrame(data, columns=columns)

        parsed = read_stata(
            datapath("io", "data", "stata", f"{file}.dta"), convert_missing=True
        )
        tm.assert_frame_equal(parsed, expected)

    def test_big_dates(self, datapath):
        yr = [1960, 2000, 9999, 100, 2262, 1677]
        mo = [1, 1, 12, 1, 4, 9]
        dd = [1, 1, 31, 1, 22, 23]
        hr = [0, 0, 23, 0, 0, 0]
        mm = [0, 0, 59, 0, 0, 0]
        ss = [0, 0, 59, 0, 0, 0]
        expected = []
        for year, month, day, hour, minute, second in zip(yr, mo, dd, hr, mm, ss):
            row = []
            for j in range(7):
                if j == 0:
                    row.append(datetime(year, month, day, hour, minute, second))
                elif j == 6:
                    row.append(datetime(year, 1, 1))
                else:
                    row.append(datetime(year, month, day))
            expected.append(row)
        expected.append([pd.NaT] * 7)
        columns = [
            "date_tc",
            "date_td",
            "date_tw",
            "date_tm",
            "date_tq",
            "date_th",
            "date_ty",
        ]

        # Fixes for weekly, quarterly,half,year
        expected[2][2] = datetime(9999, 12, 24)
        expected[2][3] = datetime(9999, 12, 1)
        expected[2][4] = datetime(9999, 10, 1)
        expected[2][5] = datetime(9999, 7, 1)
        expected[4][2] = datetime(2262, 4, 16)
        expected[4][3] = expected[4][4] = datetime(2262, 4, 1)
        expected[4][5] = expected[4][6] = datetime(2262, 1, 1)
        expected[5][2] = expected[5][3] = expected[5][4] = datetime(1677, 10, 1)
        expected[5][5] = expected[5][6] = datetime(1678, 1, 1)

        expected = DataFrame(expected, columns=columns, dtype=object)
        parsed_115 = read_stata(datapath("io", "data", "stata", "stata9_115.dta"))
        parsed_117 = read_stata(datapath("io", "data", "stata", "stata9_117.dta"))
        tm.assert_frame_equal(expected, parsed_115, check_datetimelike_compat=True)
        tm.assert_frame_equal(expected, parsed_117, check_datetimelike_compat=True)

        date_conversion = {c: c[-2:] for c in columns}
        # {c : c[-2:] for c in columns}
        with tm.ensure_clean() as path:
            expected.index.name = "index"
            expected.to_stata(path, convert_dates=date_conversion)
            written_and_read_again = self.read_dta(path)

        tm.assert_frame_equal(
            written_and_read_again.set_index("index"),
            expected.set_index(expected.index.astype(np.int32)),
            check_datetimelike_compat=True,
        )

    def test_dtype_conversion(self, datapath):
        expected = self.read_csv(datapath("io", "data", "stata", "stata6.csv"))
        expected["byte_"] = expected["byte_"].astype(np.int8)
        expected["int_"] = expected["int_"].astype(np.int16)
        expected["long_"] = expected["long_"].astype(np.int32)
        expected["float_"] = expected["float_"].astype(np.float32)
        expected["double_"] = expected["double_"].astype(np.float64)
        expected["date_td"] = expected["date_td"].apply(
            datetime.strptime, args=("%Y-%m-%d",)
        )

        no_conversion = read_stata(
            datapath("io", "data", "stata", "stata6_117.dta"), convert_dates=True
        )
        tm.assert_frame_equal(expected, no_conversion)

        conversion = read_stata(
            datapath("io", "data", "stata", "stata6_117.dta"),
            convert_dates=True,
            preserve_dtypes=False,
        )

        # read_csv types are the same
        expected = self.read_csv(datapath("io", "data", "stata", "stata6.csv"))
        expected["date_td"] = expected["date_td"].apply(
            datetime.strptime, args=("%Y-%m-%d",)
        )

        tm.assert_frame_equal(expected, conversion)

    def test_drop_column(self, datapath):
        expected = self.read_csv(datapath("io", "data", "stata", "stata6.csv"))
        expected["byte_"] = expected["byte_"].astype(np.int8)
        expected["int_"] = expected["int_"].astype(np.int16)
        expected["long_"] = expected["long_"].astype(np.int32)
        expected["float_"] = expected["float_"].astype(np.float32)
        expected["double_"] = expected["double_"].astype(np.float64)
        expected["date_td"] = expected["date_td"].apply(
            datetime.strptime, args=("%Y-%m-%d",)
        )

        columns = ["byte_", "int_", "long_"]
        expected = expected[columns]
        dropped = read_stata(
            datapath("io", "data", "stata", "stata6_117.dta"),
            convert_dates=True,
            columns=columns,
        )

        tm.assert_frame_equal(expected, dropped)

        # See PR 10757
        columns = ["int_", "long_", "byte_"]
        expected = expected[columns]
        reordered = read_stata(
            datapath("io", "data", "stata", "stata6_117.dta"),
            convert_dates=True,
            columns=columns,
        )
        tm.assert_frame_equal(expected, reordered)

        msg = "columns contains duplicate entries"
        with pytest.raises(ValueError, match=msg):
            columns = ["byte_", "byte_"]
            read_stata(
                datapath("io", "data", "stata", "stata6_117.dta"),
                convert_dates=True,
                columns=columns,
            )

        msg = "The following columns were not found in the Stata data set: not_found"
        with pytest.raises(ValueError, match=msg):
            columns = ["byte_", "int_", "long_", "not_found"]
            read_stata(
                datapath("io", "data", "stata", "stata6_117.dta"),
                convert_dates=True,
                columns=columns,
            )

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    @pytest.mark.filterwarnings(
        "ignore:\\nStata value:pandas.io.stata.ValueLabelTypeMismatch"
    )
    def test_categorical_writing(self, version):
        original = DataFrame.from_records(
            [
                ["one", "ten", "one", "one", "one", 1],
                ["two", "nine", "two", "two", "two", 2],
                ["three", "eight", "three", "three", "three", 3],
                ["four", "seven", 4, "four", "four", 4],
                ["five", "six", 5, np.nan, "five", 5],
                ["six", "five", 6, np.nan, "six", 6],
                ["seven", "four", 7, np.nan, "seven", 7],
                ["eight", "three", 8, np.nan, "eight", 8],
                ["nine", "two", 9, np.nan, "nine", 9],
                ["ten", "one", "ten", np.nan, "ten", 10],
            ],
            columns=[
                "fully_labeled",
                "fully_labeled2",
                "incompletely_labeled",
                "labeled_with_missings",
                "float_labelled",
                "unlabeled",
            ],
        )
        expected = original.copy()

        # these are all categoricals
        original = pd.concat(
            [original[col].astype("category") for col in original], axis=1
        )
        expected.index = expected.index.set_names("index").astype(np.int32)

        expected["incompletely_labeled"] = expected["incompletely_labeled"].apply(str)
        expected["unlabeled"] = expected["unlabeled"].apply(str)
        for col in expected:
            orig = expected[col].copy()

            cat = orig.astype("category")._values
            cat = cat.as_ordered()
            if col == "unlabeled":
                cat = cat.set_categories(orig, ordered=True)

            cat.categories.rename(None, inplace=True)

            expected[col] = cat

        with tm.ensure_clean() as path:
            original.to_stata(path, version=version)
            written_and_read_again = self.read_dta(path)

        res = written_and_read_again.set_index("index")
        tm.assert_frame_equal(res, expected)

    def test_categorical_warnings_and_errors(self):
        # Warning for non-string labels
        # Error for labels too long
        original = DataFrame.from_records(
            [["a" * 10000], ["b" * 10000], ["c" * 10000], ["d" * 10000]],
            columns=["Too_long"],
        )

        original = pd.concat(
            [original[col].astype("category") for col in original], axis=1
        )
        with tm.ensure_clean() as path:
            msg = (
                "Stata value labels for a single variable must have "
                r"a combined length less than 32,000 characters\."
            )
            with pytest.raises(ValueError, match=msg):
                original.to_stata(path)

        original = DataFrame.from_records(
            [["a"], ["b"], ["c"], ["d"], [1]], columns=["Too_long"]
        )
        original = pd.concat(
            [original[col].astype("category") for col in original], axis=1
        )

        with tm.assert_produces_warning(ValueLabelTypeMismatch):
            original.to_stata(path)
            # should get a warning for mixed content

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_categorical_with_stata_missing_values(self, version):
        values = [["a" + str(i)] for i in range(120)]
        values.append([np.nan])
        original = DataFrame.from_records(values, columns=["many_labels"])
        original = pd.concat(
            [original[col].astype("category") for col in original], axis=1
        )
        original.index.name = "index"
        with tm.ensure_clean() as path:
            original.to_stata(path, version=version)
            written_and_read_again = self.read_dta(path)

        res = written_and_read_again.set_index("index")

        expected = original.copy()
        for col in expected:
            cat = expected[col]._values
            new_cats = cat.remove_unused_categories().categories
            cat = cat.set_categories(new_cats, ordered=True)
            expected[col] = cat
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(res, expected)

    @pytest.mark.parametrize("file", ["stata10_115", "stata10_117"])
    def test_categorical_order(self, file, datapath):
        # Directly construct using expected codes
        # Format is is_cat, col_name, labels (in order), underlying data
        expected = [
            (True, "ordered", ["a", "b", "c", "d", "e"], np.arange(5)),
            (True, "reverse", ["a", "b", "c", "d", "e"], np.arange(5)[::-1]),
            (True, "noorder", ["a", "b", "c", "d", "e"], np.array([2, 1, 4, 0, 3])),
            (True, "floating", ["a", "b", "c", "d", "e"], np.arange(0, 5)),
            (True, "float_missing", ["a", "d", "e"], np.array([0, 1, 2, -1, -1])),
            (False, "nolabel", [1.0, 2.0, 3.0, 4.0, 5.0], np.arange(5)),
            (True, "int32_mixed", ["d", 2, "e", "b", "a"], np.arange(5)),
        ]
        cols = []
        for is_cat, col, labels, codes in expected:
            if is_cat:
                cols.append(
                    (col, pd.Categorical.from_codes(codes, labels, ordered=True))
                )
            else:
                cols.append((col, Series(labels, dtype=np.float32)))
        expected = DataFrame.from_dict(dict(cols))

        # Read with and with out categoricals, ensure order is identical
        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = read_stata(file)
        tm.assert_frame_equal(expected, parsed)

        # Check identity of codes
        for col in expected:
            if isinstance(expected[col].dtype, CategoricalDtype):
                tm.assert_series_equal(expected[col].cat.codes, parsed[col].cat.codes)
                tm.assert_index_equal(
                    expected[col].cat.categories, parsed[col].cat.categories
                )

    @pytest.mark.parametrize("file", ["stata11_115", "stata11_117"])
    def test_categorical_sorting(self, file, datapath):
        parsed = read_stata(datapath("io", "data", "stata", f"{file}.dta"))

        # Sort based on codes, not strings
        parsed = parsed.sort_values("srh", na_position="first")

        # Don't sort index
        parsed.index = pd.RangeIndex(len(parsed))
        codes = [-1, -1, 0, 1, 1, 1, 2, 2, 3, 4]
        categories = ["Poor", "Fair", "Good", "Very good", "Excellent"]
        cat = pd.Categorical.from_codes(
            codes=codes, categories=categories, ordered=True
        )
        expected = Series(cat, name="srh")
        tm.assert_series_equal(expected, parsed["srh"])

    @pytest.mark.parametrize("file", ["stata10_115", "stata10_117"])
    def test_categorical_ordering(self, file, datapath):
        file = datapath("io", "data", "stata", f"{file}.dta")
        parsed = read_stata(file)

        parsed_unordered = read_stata(file, order_categoricals=False)
        for col in parsed:
            if not isinstance(parsed[col].dtype, CategoricalDtype):
                continue
            assert parsed[col].cat.ordered
            assert not parsed_unordered[col].cat.ordered

    @pytest.mark.filterwarnings("ignore::UserWarning")
    @pytest.mark.parametrize(
        "file",
        [
            "stata1_117",
            "stata2_117",
            "stata3_117",
            "stata4_117",
            "stata5_117",
            "stata6_117",
            "stata7_117",
            "stata8_117",
            "stata9_117",
            "stata10_117",
            "stata11_117",
        ],
    )
    @pytest.mark.parametrize("chunksize", [1, 2])
    @pytest.mark.parametrize("convert_categoricals", [False, True])
    @pytest.mark.parametrize("convert_dates", [False, True])
    def test_read_chunks_117(
        self, file, chunksize, convert_categoricals, convert_dates, datapath
    ):
        fname = datapath("io", "data", "stata", f"{file}.dta")

        parsed = read_stata(
            fname,
            convert_categoricals=convert_categoricals,
            convert_dates=convert_dates,
        )
        with read_stata(
            fname,
            iterator=True,
            convert_categoricals=convert_categoricals,
            convert_dates=convert_dates,
        ) as itr:
            pos = 0
            for j in range(5):
                try:
                    chunk = itr.read(chunksize)
                except StopIteration:
                    break
                from_frame = parsed.iloc[pos : pos + chunksize, :].copy()
                from_frame = self._convert_categorical(from_frame)
                tm.assert_frame_equal(
                    from_frame, chunk, check_dtype=False, check_datetimelike_compat=True
                )
                pos += chunksize

    @staticmethod
    def _convert_categorical(from_frame: DataFrame) -> DataFrame:
        """
        Emulate the categorical casting behavior we expect from roundtripping.
        """
        for col in from_frame:
            ser = from_frame[col]
            if isinstance(ser.dtype, CategoricalDtype):
                cat = ser._values.remove_unused_categories()
                if cat.categories.dtype == object:
                    categories = pd.Index._with_infer(cat.categories._values)
                    cat = cat.set_categories(categories)
                elif cat.categories.dtype == "string" and len(cat.categories) == 0:
                    # if the read categories are empty, it comes back as object dtype
                    categories = cat.categories.astype(object)
                    cat = cat.set_categories(categories)
                from_frame[col] = cat
        return from_frame

    def test_iterator(self, datapath):
        fname = datapath("io", "data", "stata", "stata3_117.dta")

        parsed = read_stata(fname)

        with read_stata(fname, iterator=True) as itr:
            chunk = itr.read(5)
            tm.assert_frame_equal(parsed.iloc[0:5, :], chunk)

        with read_stata(fname, chunksize=5) as itr:
            chunk = list(itr)
            tm.assert_frame_equal(parsed.iloc[0:5, :], chunk[0])

        with read_stata(fname, iterator=True) as itr:
            chunk = itr.get_chunk(5)
            tm.assert_frame_equal(parsed.iloc[0:5, :], chunk)

        with read_stata(fname, chunksize=5) as itr:
            chunk = itr.get_chunk()
            tm.assert_frame_equal(parsed.iloc[0:5, :], chunk)

        # GH12153
        with read_stata(fname, chunksize=4) as itr:
            from_chunks = pd.concat(itr)
        tm.assert_frame_equal(parsed, from_chunks)

    @pytest.mark.filterwarnings("ignore::UserWarning")
    @pytest.mark.parametrize(
        "file",
        [
            "stata2_115",
            "stata3_115",
            "stata4_115",
            "stata5_115",
            "stata6_115",
            "stata7_115",
            "stata8_115",
            "stata9_115",
            "stata10_115",
            "stata11_115",
        ],
    )
    @pytest.mark.parametrize("chunksize", [1, 2])
    @pytest.mark.parametrize("convert_categoricals", [False, True])
    @pytest.mark.parametrize("convert_dates", [False, True])
    def test_read_chunks_115(
        self, file, chunksize, convert_categoricals, convert_dates, datapath
    ):
        fname = datapath("io", "data", "stata", f"{file}.dta")

        # Read the whole file
        parsed = read_stata(
            fname,
            convert_categoricals=convert_categoricals,
            convert_dates=convert_dates,
        )

        # Compare to what we get when reading by chunk
        with read_stata(
            fname,
            iterator=True,
            convert_dates=convert_dates,
            convert_categoricals=convert_categoricals,
        ) as itr:
            pos = 0
            for j in range(5):
                try:
                    chunk = itr.read(chunksize)
                except StopIteration:
                    break
                from_frame = parsed.iloc[pos : pos + chunksize, :].copy()
                from_frame = self._convert_categorical(from_frame)
                tm.assert_frame_equal(
                    from_frame, chunk, check_dtype=False, check_datetimelike_compat=True
                )
                pos += chunksize

    def test_read_chunks_columns(self, datapath):
        fname = datapath("io", "data", "stata", "stata3_117.dta")
        columns = ["quarter", "cpi", "m1"]
        chunksize = 2

        parsed = read_stata(fname, columns=columns)
        with read_stata(fname, iterator=True) as itr:
            pos = 0
            for j in range(5):
                chunk = itr.read(chunksize, columns=columns)
                if chunk is None:
                    break
                from_frame = parsed.iloc[pos : pos + chunksize, :]
                tm.assert_frame_equal(from_frame, chunk, check_dtype=False)
                pos += chunksize

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_write_variable_labels(self, version, mixed_frame):
        # GH 13631, add support for writing variable labels
        mixed_frame.index.name = "index"
        variable_labels = {"a": "City Rank", "b": "City Exponent", "c": "City"}
        with tm.ensure_clean() as path:
            mixed_frame.to_stata(path, variable_labels=variable_labels, version=version)
            with StataReader(path) as sr:
                read_labels = sr.variable_labels()
            expected_labels = {
                "index": "",
                "a": "City Rank",
                "b": "City Exponent",
                "c": "City",
            }
            assert read_labels == expected_labels

        variable_labels["index"] = "The Index"
        with tm.ensure_clean() as path:
            mixed_frame.to_stata(path, variable_labels=variable_labels, version=version)
            with StataReader(path) as sr:
                read_labels = sr.variable_labels()
            assert read_labels == variable_labels

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_invalid_variable_labels(self, version, mixed_frame):
        mixed_frame.index.name = "index"
        variable_labels = {"a": "very long" * 10, "b": "City Exponent", "c": "City"}
        with tm.ensure_clean() as path:
            msg = "Variable labels must be 80 characters or fewer"
            with pytest.raises(ValueError, match=msg):
                mixed_frame.to_stata(
                    path, variable_labels=variable_labels, version=version
                )

    @pytest.mark.parametrize("version", [114, 117])
    def test_invalid_variable_label_encoding(self, version, mixed_frame):
        mixed_frame.index.name = "index"
        variable_labels = {"a": "very long" * 10, "b": "City Exponent", "c": "City"}
        variable_labels["a"] = "invalid character Œ"
        with tm.ensure_clean() as path:
            with pytest.raises(
                ValueError, match="Variable labels must contain only characters"
            ):
                mixed_frame.to_stata(
                    path, variable_labels=variable_labels, version=version
                )

    def test_write_variable_label_errors(self, mixed_frame):
        values = ["\u03A1", "\u0391", "\u039D", "\u0394", "\u0391", "\u03A3"]

        variable_labels_utf8 = {
            "a": "City Rank",
            "b": "City Exponent",
            "c": "".join(values),
        }

        msg = (
            "Variable labels must contain only characters that can be "
            "encoded in Latin-1"
        )
        with pytest.raises(ValueError, match=msg):
            with tm.ensure_clean() as path:
                mixed_frame.to_stata(path, variable_labels=variable_labels_utf8)

        variable_labels_long = {
            "a": "City Rank",
            "b": "City Exponent",
            "c": "A very, very, very long variable label "
            "that is too long for Stata which means "
            "that it has more than 80 characters",
        }

        msg = "Variable labels must be 80 characters or fewer"
        with pytest.raises(ValueError, match=msg):
            with tm.ensure_clean() as path:
                mixed_frame.to_stata(path, variable_labels=variable_labels_long)

    def test_default_date_conversion(self):
        # GH 12259
        dates = [
            dt.datetime(1999, 12, 31, 12, 12, 12, 12000),
            dt.datetime(2012, 12, 21, 12, 21, 12, 21000),
            dt.datetime(1776, 7, 4, 7, 4, 7, 4000),
        ]
        original = DataFrame(
            {
                "nums": [1.0, 2.0, 3.0],
                "strs": ["apple", "banana", "cherry"],
                "dates": dates,
            }
        )

        with tm.ensure_clean() as path:
            original.to_stata(path, write_index=False)
            reread = read_stata(path, convert_dates=True)
            tm.assert_frame_equal(original, reread)

            original.to_stata(path, write_index=False, convert_dates={"dates": "tc"})
            direct = read_stata(path, convert_dates=True)
            tm.assert_frame_equal(reread, direct)

            dates_idx = original.columns.tolist().index("dates")
            original.to_stata(path, write_index=False, convert_dates={dates_idx: "tc"})
            direct = read_stata(path, convert_dates=True)
            tm.assert_frame_equal(reread, direct)

    def test_unsupported_type(self):
        original = DataFrame({"a": [1 + 2j, 2 + 4j]})

        msg = "Data type complex128 not supported"
        with pytest.raises(NotImplementedError, match=msg):
            with tm.ensure_clean() as path:
                original.to_stata(path)

    def test_unsupported_datetype(self):
        dates = [
            dt.datetime(1999, 12, 31, 12, 12, 12, 12000),
            dt.datetime(2012, 12, 21, 12, 21, 12, 21000),
            dt.datetime(1776, 7, 4, 7, 4, 7, 4000),
        ]
        original = DataFrame(
            {
                "nums": [1.0, 2.0, 3.0],
                "strs": ["apple", "banana", "cherry"],
                "dates": dates,
            }
        )

        msg = "Format %tC not implemented"
        with pytest.raises(NotImplementedError, match=msg):
            with tm.ensure_clean() as path:
                original.to_stata(path, convert_dates={"dates": "tC"})

        dates = pd.date_range("1-1-1990", periods=3, tz="Asia/Hong_Kong")
        original = DataFrame(
            {
                "nums": [1.0, 2.0, 3.0],
                "strs": ["apple", "banana", "cherry"],
                "dates": dates,
            }
        )
        with pytest.raises(NotImplementedError, match="Data type datetime64"):
            with tm.ensure_clean() as path:
                original.to_stata(path)

    def test_repeated_column_labels(self, datapath):
        # GH 13923, 25772
        msg = """
Value labels for column ethnicsn are not unique. These cannot be converted to
pandas categoricals.

Either read the file with `convert_categoricals` set to False or use the
low level interface in `StataReader` to separately read the values and the
value_labels.

The repeated labels are:\n-+\nwolof
"""
        with pytest.raises(ValueError, match=msg):
            read_stata(
                datapath("io", "data", "stata", "stata15.dta"),
                convert_categoricals=True,
            )

    def test_stata_111(self, datapath):
        # 111 is an old version but still used by current versions of
        # SAS when exporting to Stata format. We do not know of any
        # on-line documentation for this version.
        df = read_stata(datapath("io", "data", "stata", "stata7_111.dta"))
        original = DataFrame(
            {
                "y": [1, 1, 1, 1, 1, 0, 0, np.nan, 0, 0],
                "x": [1, 2, 1, 3, np.nan, 4, 3, 5, 1, 6],
                "w": [2, np.nan, 5, 2, 4, 4, 3, 1, 2, 3],
                "z": ["a", "b", "c", "d", "e", "", "g", "h", "i", "j"],
            }
        )
        original = original[["y", "x", "w", "z"]]
        tm.assert_frame_equal(original, df)

    def test_out_of_range_double(self):
        # GH 14618
        df = DataFrame(
            {
                "ColumnOk": [0.0, np.finfo(np.double).eps, 4.49423283715579e307],
                "ColumnTooBig": [0.0, np.finfo(np.double).eps, np.finfo(np.double).max],
            }
        )
        msg = (
            r"Column ColumnTooBig has a maximum value \(.+\) outside the range "
            r"supported by Stata \(.+\)"
        )
        with pytest.raises(ValueError, match=msg):
            with tm.ensure_clean() as path:
                df.to_stata(path)

    def test_out_of_range_float(self):
        original = DataFrame(
            {
                "ColumnOk": [
                    0.0,
                    np.finfo(np.float32).eps,
                    np.finfo(np.float32).max / 10.0,
                ],
                "ColumnTooBig": [
                    0.0,
                    np.finfo(np.float32).eps,
                    np.finfo(np.float32).max,
                ],
            }
        )
        original.index.name = "index"
        for col in original:
            original[col] = original[col].astype(np.float32)

        with tm.ensure_clean() as path:
            original.to_stata(path)
            reread = read_stata(path)

        original["ColumnTooBig"] = original["ColumnTooBig"].astype(np.float64)
        expected = original.copy()
        expected.index = expected.index.astype(np.int32)
        tm.assert_frame_equal(reread.set_index("index"), expected)

    @pytest.mark.parametrize("infval", [np.inf, -np.inf])
    def test_inf(self, infval):
        # GH 45350
        df = DataFrame({"WithoutInf": [0.0, 1.0], "WithInf": [2.0, infval]})
        msg = (
            "Column WithInf contains infinity or -infinity"
            "which is outside the range supported by Stata."
        )
        with pytest.raises(ValueError, match=msg):
            with tm.ensure_clean() as path:
                df.to_stata(path)

    def test_path_pathlib(self):
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=pd.Index(list("ABCD")),
            index=pd.Index([f"i-{i}" for i in range(30)]),
        )
        df.index.name = "index"
        reader = lambda x: read_stata(x).set_index("index")
        result = tm.round_trip_pathlib(df.to_stata, reader)
        tm.assert_frame_equal(df, result)

    def test_pickle_path_localpath(self):
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=pd.Index(list("ABCD")),
            index=pd.Index([f"i-{i}" for i in range(30)]),
        )
        df.index.name = "index"
        reader = lambda x: read_stata(x).set_index("index")
        result = tm.round_trip_localpath(df.to_stata, reader)
        tm.assert_frame_equal(df, result)

    @pytest.mark.parametrize("write_index", [True, False])
    def test_value_labels_iterator(self, write_index):
        # GH 16923
        d = {"A": ["B", "E", "C", "A", "E"]}
        df = DataFrame(data=d)
        df["A"] = df["A"].astype("category")
        with tm.ensure_clean() as path:
            df.to_stata(path, write_index=write_index)

            with read_stata(path, iterator=True) as dta_iter:
                value_labels = dta_iter.value_labels()
        assert value_labels == {"A": {0: "A", 1: "B", 2: "C", 3: "E"}}

    def test_set_index(self):
        # GH 17328
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=pd.Index(list("ABCD")),
            index=pd.Index([f"i-{i}" for i in range(30)]),
        )
        df.index.name = "index"
        with tm.ensure_clean() as path:
            df.to_stata(path)
            reread = read_stata(path, index_col="index")
        tm.assert_frame_equal(df, reread)

    @pytest.mark.parametrize(
        "column", ["ms", "day", "week", "month", "qtr", "half", "yr"]
    )
    def test_date_parsing_ignores_format_details(self, column, datapath):
        # GH 17797
        #
        # Test that display formats are ignored when determining if a numeric
        # column is a date value.
        #
        # All date types are stored as numbers and format associated with the
        # column denotes both the type of the date and the display format.
        #
        # STATA supports 9 date types which each have distinct units. We test 7
        # of the 9 types, ignoring %tC and %tb. %tC is a variant of %tc that
        # accounts for leap seconds and %tb relies on STATAs business calendar.
        df = read_stata(datapath("io", "data", "stata", "stata13_dates.dta"))
        unformatted = df.loc[0, column]
        formatted = df.loc[0, column + "_fmt"]
        assert unformatted == formatted

    def test_writer_117(self, using_infer_string):
        original = DataFrame(
            data=[
                [
                    "string",
                    "object",
                    1,
                    1,
                    1,
                    1.1,
                    1.1,
                    np.datetime64("2003-12-25"),
                    "a",
                    "a" * 2045,
                    "a" * 5000,
                    "a",
                ],
                [
                    "string-1",
                    "object-1",
                    1,
                    1,
                    1,
                    1.1,
                    1.1,
                    np.datetime64("2003-12-26"),
                    "b",
                    "b" * 2045,
                    "",
                    "",
                ],
            ],
            columns=[
                "string",
                "object",
                "int8",
                "int16",
                "int32",
                "float32",
                "float64",
                "datetime",
                "s1",
                "s2045",
                "srtl",
                "forced_strl",
            ],
        )
        original["object"] = Series(original["object"], dtype=object)
        original["int8"] = Series(original["int8"], dtype=np.int8)
        original["int16"] = Series(original["int16"], dtype=np.int16)
        original["int32"] = original["int32"].astype(np.int32)
        original["float32"] = Series(original["float32"], dtype=np.float32)
        original.index.name = "index"
        original.index = original.index.astype(np.int32)
        copy = original.copy()
        with tm.ensure_clean() as path:
            original.to_stata(
                path,
                convert_dates={"datetime": "tc"},
                convert_strl=["forced_strl"],
                version=117,
            )
            written_and_read_again = self.read_dta(path)

        expected = original[:]
        if using_infer_string:
            # object dtype (with only strings/None) comes back as string dtype
            expected["object"] = expected["object"].astype("str")

        tm.assert_frame_equal(
            written_and_read_again.set_index("index"),
            expected,
        )
        tm.assert_frame_equal(original, copy)

    def test_convert_strl_name_swap(self):
        original = DataFrame(
            [["a" * 3000, "A", "apple"], ["b" * 1000, "B", "banana"]],
            columns=["long1" * 10, "long", 1],
        )
        original.index.name = "index"

        with tm.assert_produces_warning(InvalidColumnName):
            with tm.ensure_clean() as path:
                original.to_stata(path, convert_strl=["long", 1], version=117)
                reread = self.read_dta(path)
                reread = reread.set_index("index")
                reread.columns = original.columns
                tm.assert_frame_equal(reread, original, check_index_type=False)

    def test_invalid_date_conversion(self):
        # GH 12259
        dates = [
            dt.datetime(1999, 12, 31, 12, 12, 12, 12000),
            dt.datetime(2012, 12, 21, 12, 21, 12, 21000),
            dt.datetime(1776, 7, 4, 7, 4, 7, 4000),
        ]
        original = DataFrame(
            {
                "nums": [1.0, 2.0, 3.0],
                "strs": ["apple", "banana", "cherry"],
                "dates": dates,
            }
        )

        with tm.ensure_clean() as path:
            msg = "convert_dates key must be a column or an integer"
            with pytest.raises(ValueError, match=msg):
                original.to_stata(path, convert_dates={"wrong_name": "tc"})

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_nonfile_writing(self, version):
        # GH 21041
        bio = io.BytesIO()
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=pd.Index(list("ABCD")),
            index=pd.Index([f"i-{i}" for i in range(30)]),
        )
        df.index.name = "index"
        with tm.ensure_clean() as path:
            df.to_stata(bio, version=version)
            bio.seek(0)
            with open(path, "wb") as dta:
                dta.write(bio.read())
            reread = read_stata(path, index_col="index")
        tm.assert_frame_equal(df, reread)

    def test_gzip_writing(self):
        # writing version 117 requires seek and cannot be used with gzip
        df = DataFrame(
            1.1 * np.arange(120).reshape((30, 4)),
            columns=pd.Index(list("ABCD")),
            index=pd.Index([f"i-{i}" for i in range(30)]),
        )
        df.index.name = "index"
        with tm.ensure_clean() as path:
            with gzip.GzipFile(path, "wb") as gz:
                df.to_stata(gz, version=114)
            with gzip.GzipFile(path, "rb") as gz:
                reread = read_stata(gz, index_col="index")
        tm.assert_frame_equal(df, reread)

    def test_unicode_dta_118(self, datapath):
        unicode_df = self.read_dta(datapath("io", "data", "stata", "stata16_118.dta"))

        columns = ["utf8", "latin1", "ascii", "utf8_strl", "ascii_strl"]
        values = [
            ["ραηδας", "PÄNDÄS", "p", "ραηδας", "p"],
            ["ƤĀńĐąŜ", "Ö", "a", "ƤĀńĐąŜ", "a"],
            ["ᴘᴀᴎᴅᴀS", "Ü", "n", "ᴘᴀᴎᴅᴀS", "n"],
            ["      ", "      ", "d", "      ", "d"],
            [" ", "", "a", " ", "a"],
            ["", "", "s", "", "s"],
            ["", "", " ", "", " "],
        ]
        expected = DataFrame(values, columns=columns)

        tm.assert_frame_equal(unicode_df, expected)

    def test_mixed_string_strl(self, using_infer_string):
        # GH 23633
        output = [{"mixed": "string" * 500, "number": 0}, {"mixed": None, "number": 1}]
        output = DataFrame(output)
        output.number = output.number.astype("int32")

        with tm.ensure_clean() as path:
            output.to_stata(path, write_index=False, version=117)
            reread = read_stata(path)
            expected = output.fillna("")
            tm.assert_frame_equal(reread, expected)

            # Check strl supports all None (null)
            output["mixed"] = None
            output.to_stata(
                path, write_index=False, convert_strl=["mixed"], version=117
            )
            reread = read_stata(path)
            expected = output.copy()
            if using_infer_string:
                expected["mixed"] = expected["mixed"].astype("str")
            expected = expected.fillna("")
            tm.assert_frame_equal(reread, expected)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_all_none_exception(self, version):
        output = [{"none": "none", "number": 0}, {"none": None, "number": 1}]
        output = DataFrame(output)
        output["none"] = None
        with tm.ensure_clean() as path:
            with pytest.raises(ValueError, match="Column `none` cannot be exported"):
                output.to_stata(path, version=version)

    @pytest.mark.parametrize("version", [114, 117, 118, 119, None])
    def test_invalid_file_not_written(self, version):
        content = "Here is one __�__ Another one __·__ Another one __½__"
        df = DataFrame([content], columns=["invalid"])
        with tm.ensure_clean() as path:
            msg1 = (
                r"'latin-1' codec can't encode character '\\ufffd' "
                r"in position 14: ordinal not in range\(256\)"
            )
            msg2 = (
                "'ascii' codec can't decode byte 0xef in position 14: "
                r"ordinal not in range\(128\)"
            )
            with pytest.raises(UnicodeEncodeError, match=f"{msg1}|{msg2}"):
                df.to_stata(path)

    def test_strl_latin1(self):
        # GH 23573, correct GSO data to reflect correct size
        output = DataFrame(
            [["pandas"] * 2, ["þâÑÐÅ§"] * 2], columns=["var_str", "var_strl"]
        )

        with tm.ensure_clean() as path:
            output.to_stata(path, version=117, convert_strl=["var_strl"])
            with open(path, "rb") as reread:
                content = reread.read()
                expected = "þâÑÐÅ§"
                assert expected.encode("latin-1") in content
                assert expected.encode("utf-8") in content
                gsos = content.split(b"strls")[1][1:-2]
                for gso in gsos.split(b"GSO")[1:]:
                    val = gso.split(b"\x00")[-2]
                    size = gso[gso.find(b"\x82") + 1]
                    assert len(val) == size - 1

    def test_encoding_latin1_118(self, datapath):
        # GH 25960
        msg = """
One or more strings in the dta file could not be decoded using utf-8, and
so the fallback encoding of latin-1 is being used.  This can happen when a file
has been incorrectly encoded by Stata or some other software. You should verify
the string values returned are correct."""
        # Move path outside of read_stata, or else assert_produces_warning
        # will block pytests skip mechanism from triggering (failing the test)
        # if the path is not present
        path = datapath("io", "data", "stata", "stata1_encoding_118.dta")
        with tm.assert_produces_warning(UnicodeWarning, filter_level="once") as w:
            encoded = read_stata(path)
            # with filter_level="always", produces 151 warnings which can be slow
            assert len(w) == 1
            assert w[0].message.args[0] == msg

        expected = DataFrame([["Düsseldorf"]] * 151, columns=["kreis1849"])
        tm.assert_frame_equal(encoded, expected)

    @pytest.mark.slow
    def test_stata_119(self, datapath):
        # Gzipped since contains 32,999 variables and uncompressed is 20MiB
        # Just validate that the reader reports correct number of variables
        # to avoid high peak memory
        with gzip.open(
            datapath("io", "data", "stata", "stata1_119.dta.gz"), "rb"
        ) as gz:
            with StataReader(gz) as reader:
                reader._ensure_open()
                assert reader._nvar == 32999

    @pytest.mark.filterwarnings("ignore:Downcasting behavior:FutureWarning")
    @pytest.mark.parametrize("version", [118, 119, None])
    def test_utf8_writer(self, version):
        cat = pd.Categorical(["a", "β", "ĉ"], ordered=True)
        data = DataFrame(
            [
                [1.0, 1, "ᴬ", "ᴀ relatively long ŝtring"],
                [2.0, 2, "ᴮ", ""],
                [3.0, 3, "ᴰ", None],
            ],
            columns=["Å", "β", "ĉ", "strls"],
        )
        data["ᴐᴬᵀ"] = cat
        variable_labels = {
            "Å": "apple",
            "β": "ᵈᵉᵊ",
            "ĉ": "ᴎტჄႲႳႴႶႺ",
            "strls": "Long Strings",
            "ᴐᴬᵀ": "",
        }
        data_label = "ᴅaᵀa-label"
        value_labels = {"β": {1: "label", 2: "æøå", 3: "ŋot valid latin-1"}}
        data["β"] = data["β"].astype(np.int32)
        with tm.ensure_clean() as path:
            writer = StataWriterUTF8(
                path,
                data,
                data_label=data_label,
                convert_strl=["strls"],
                variable_labels=variable_labels,
                write_index=False,
                version=version,
                value_labels=value_labels,
            )
            writer.write_file()
            reread_encoded = read_stata(path)
            # Missing is intentionally converted to empty strl
            data["strls"] = data["strls"].fillna("")
            # Variable with value labels is reread as categorical
            data["β"] = (
                data["β"].replace(value_labels["β"]).astype("category").cat.as_ordered()
            )
            tm.assert_frame_equal(data, reread_encoded)
            with StataReader(path) as reader:
                assert reader.data_label == data_label
                assert reader.variable_labels() == variable_labels

            data.to_stata(path, version=version, write_index=False)
            reread_to_stata = read_stata(path)
            tm.assert_frame_equal(data, reread_to_stata)

    def test_writer_118_exceptions(self):
        df = DataFrame(np.zeros((1, 33000), dtype=np.int8))
        with tm.ensure_clean() as path:
            with pytest.raises(ValueError, match="version must be either 118 or 119."):
                StataWriterUTF8(path, df, version=117)
        with tm.ensure_clean() as path:
            with pytest.raises(ValueError, match="You must use version 119"):
                StataWriterUTF8(path, df, version=118)

    @pytest.mark.parametrize(
        "dtype_backend",
        ["numpy_nullable", pytest.param("pyarrow", marks=td.skip_if_no("pyarrow"))],
    )
    def test_read_write_ea_dtypes(self, dtype_backend):
        df = DataFrame(
            {
                "a": [1, 2, None],
                "b": ["a", "b", "c"],
                "c": [True, False, None],
                "d": [1.5, 2.5, 3.5],
                "e": pd.date_range("2020-12-31", periods=3, freq="D"),
            },
            index=pd.Index([0, 1, 2], name="index"),
        )
        df = df.convert_dtypes(dtype_backend=dtype_backend)
        df.to_stata("test_stata.dta", version=118)

        with tm.ensure_clean() as path:
            df.to_stata(path)
            written_and_read_again = self.read_dta(path)

        expected = DataFrame(
            {
                "a": [1, 2, np.nan],
                "b": ["a", "b", "c"],
                "c": [1.0, 0, np.nan],
                "d": [1.5, 2.5, 3.5],
                "e": pd.date_range("2020-12-31", periods=3, freq="D"),
            },
            index=pd.Index([0, 1, 2], name="index", dtype=np.int32),
        )

        tm.assert_frame_equal(written_and_read_again.set_index("index"), expected)


@pytest.mark.parametrize("version", [105, 108, 111, 113, 114])
def test_backward_compat(version, datapath):
    data_base = datapath("io", "data", "stata")
    ref = os.path.join(data_base, "stata-compat-118.dta")
    old = os.path.join(data_base, f"stata-compat-{version}.dta")
    expected = read_stata(ref)
    old_dta = read_stata(old)
    tm.assert_frame_equal(old_dta, expected, check_dtype=False)


def test_direct_read(datapath, monkeypatch):
    file_path = datapath("io", "data", "stata", "stata-compat-118.dta")

    # Test that opening a file path doesn't buffer the file.
    with StataReader(file_path) as reader:
        # Must not have been buffered to memory
        assert not reader.read().empty
        assert not isinstance(reader._path_or_buf, io.BytesIO)

    # Test that we use a given fp exactly, if possible.
    with open(file_path, "rb") as fp:
        with StataReader(fp) as reader:
            assert not reader.read().empty
            assert reader._path_or_buf is fp

    # Test that we use a given BytesIO exactly, if possible.
    with open(file_path, "rb") as fp:
        with io.BytesIO(fp.read()) as bio:
            with StataReader(bio) as reader:
                assert not reader.read().empty
                assert reader._path_or_buf is bio


def test_statareader_warns_when_used_without_context(datapath):
    file_path = datapath("io", "data", "stata", "stata-compat-118.dta")
    with tm.assert_produces_warning(
        ResourceWarning,
        match="without using a context manager",
    ):
        sr = StataReader(file_path)
        sr.read()
    with tm.assert_produces_warning(
        FutureWarning,
        match="is not part of the public API",
    ):
        sr.close()


@pytest.mark.parametrize("version", [114, 117, 118, 119, None])
@pytest.mark.parametrize("use_dict", [True, False])
@pytest.mark.parametrize("infer", [True, False])
def test_compression(compression, version, use_dict, infer, compression_to_extension):
    file_name = "dta_inferred_compression.dta"
    if compression:
        if use_dict:
            file_ext = compression
        else:
            file_ext = compression_to_extension[compression]
        file_name += f".{file_ext}"
    compression_arg = compression
    if infer:
        compression_arg = "infer"
    if use_dict:
        compression_arg = {"method": compression}

    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 2)), columns=list("AB")
    )
    df.index.name = "index"
    with tm.ensure_clean(file_name) as path:
        df.to_stata(path, version=version, compression=compression_arg)
        if compression == "gzip":
            with gzip.open(path, "rb") as comp:
                fp = io.BytesIO(comp.read())
        elif compression == "zip":
            with zipfile.ZipFile(path, "r") as comp:
                fp = io.BytesIO(comp.read(comp.filelist[0]))
        elif compression == "tar":
            with tarfile.open(path) as tar:
                fp = io.BytesIO(tar.extractfile(tar.getnames()[0]).read())
        elif compression == "bz2":
            with bz2.open(path, "rb") as comp:
                fp = io.BytesIO(comp.read())
        elif compression == "zstd":
            zstd = pytest.importorskip("zstandard")
            with zstd.open(path, "rb") as comp:
                fp = io.BytesIO(comp.read())
        elif compression == "xz":
            lzma = pytest.importorskip("lzma")
            with lzma.open(path, "rb") as comp:
                fp = io.BytesIO(comp.read())
        elif compression is None:
            fp = path
        reread = read_stata(fp, index_col="index")

    expected = df.copy()
    expected.index = expected.index.astype(np.int32)
    tm.assert_frame_equal(reread, expected)


@pytest.mark.parametrize("method", ["zip", "infer"])
@pytest.mark.parametrize("file_ext", [None, "dta", "zip"])
def test_compression_dict(method, file_ext):
    file_name = f"test.{file_ext}"
    archive_name = "test.dta"
    df = DataFrame(
        np.random.default_rng(2).standard_normal((10, 2)), columns=list("AB")
    )
    df.index.name = "index"
    with tm.ensure_clean(file_name) as path:
        compression = {"method": method, "archive_name": archive_name}
        df.to_stata(path, compression=compression)
        if method == "zip" or file_ext == "zip":
            with zipfile.ZipFile(path, "r") as zp:
                assert len(zp.filelist) == 1
                assert zp.filelist[0].filename == archive_name
                fp = io.BytesIO(zp.read(zp.filelist[0]))
        else:
            fp = path
        reread = read_stata(fp, index_col="index")

    expected = df.copy()
    expected.index = expected.index.astype(np.int32)
    tm.assert_frame_equal(reread, expected)


@pytest.mark.parametrize("version", [114, 117, 118, 119, None])
def test_chunked_categorical(version):
    df = DataFrame({"cats": Series(["a", "b", "a", "b", "c"], dtype="category")})
    df.index.name = "index"

    expected = df.copy()
    expected.index = expected.index.astype(np.int32)

    with tm.ensure_clean() as path:
        df.to_stata(path, version=version)
        with StataReader(path, chunksize=2, order_categoricals=False) as reader:
            for i, block in enumerate(reader):
                block = block.set_index("index")
                assert "cats" in block
                tm.assert_series_equal(
                    block.cats, expected.cats.iloc[2 * i : 2 * (i + 1)]
                )


def test_chunked_categorical_partial(datapath):
    dta_file = datapath("io", "data", "stata", "stata-dta-partially-labeled.dta")
    values = ["a", "b", "a", "b", 3.0]
    with StataReader(dta_file, chunksize=2) as reader:
        with tm.assert_produces_warning(CategoricalConversionWarning):
            for i, block in enumerate(reader):
                assert list(block.cats) == values[2 * i : 2 * (i + 1)]
                if i < 2:
                    idx = pd.Index(["a", "b"])
                else:
                    idx = pd.Index([3.0], dtype="float64")
                tm.assert_index_equal(block.cats.cat.categories, idx)
    with tm.assert_produces_warning(CategoricalConversionWarning):
        with StataReader(dta_file, chunksize=5) as reader:
            large_chunk = reader.__next__()
    direct = read_stata(dta_file)
    tm.assert_frame_equal(direct, large_chunk)


@pytest.mark.parametrize("chunksize", (-1, 0, "apple"))
def test_iterator_errors(datapath, chunksize):
    dta_file = datapath("io", "data", "stata", "stata-dta-partially-labeled.dta")
    with pytest.raises(ValueError, match="chunksize must be a positive"):
        with StataReader(dta_file, chunksize=chunksize):
            pass


def test_iterator_value_labels():
    # GH 31544
    values = ["c_label", "b_label"] + ["a_label"] * 500
    df = DataFrame({f"col{k}": pd.Categorical(values, ordered=True) for k in range(2)})
    with tm.ensure_clean() as path:
        df.to_stata(path, write_index=False)
        expected = pd.Index(["a_label", "b_label", "c_label"])
        with read_stata(path, chunksize=100) as reader:
            for j, chunk in enumerate(reader):
                for i in range(2):
                    tm.assert_index_equal(chunk.dtypes.iloc[i].categories, expected)
                tm.assert_frame_equal(chunk, df.iloc[j * 100 : (j + 1) * 100])


def test_precision_loss():
    df = DataFrame(
        [[sum(2**i for i in range(60)), sum(2**i for i in range(52))]],
        columns=["big", "little"],
    )
    with tm.ensure_clean() as path:
        with tm.assert_produces_warning(
            PossiblePrecisionLoss, match="Column converted from int64 to float64"
        ):
            df.to_stata(path, write_index=False)
        reread = read_stata(path)
        expected_dt = Series([np.float64, np.float64], index=["big", "little"])
        tm.assert_series_equal(reread.dtypes, expected_dt)
        assert reread.loc[0, "little"] == df.loc[0, "little"]
        assert reread.loc[0, "big"] == float(df.loc[0, "big"])


def test_compression_roundtrip(compression):
    df = DataFrame(
        [[0.123456, 0.234567, 0.567567], [12.32112, 123123.2, 321321.2]],
        index=["A", "B"],
        columns=["X", "Y", "Z"],
    )
    df.index.name = "index"

    with tm.ensure_clean() as path:
        df.to_stata(path, compression=compression)
        reread = read_stata(path, compression=compression, index_col="index")
        tm.assert_frame_equal(df, reread)

        # explicitly ensure file was compressed.
        with tm.decompress_file(path, compression) as fh:
            contents = io.BytesIO(fh.read())
        reread = read_stata(contents, index_col="index")
        tm.assert_frame_equal(df, reread)


@pytest.mark.parametrize("to_infer", [True, False])
@pytest.mark.parametrize("read_infer", [True, False])
def test_stata_compression(
    compression_only, read_infer, to_infer, compression_to_extension
):
    compression = compression_only

    ext = compression_to_extension[compression]
    filename = f"test.{ext}"

    df = DataFrame(
        [[0.123456, 0.234567, 0.567567], [12.32112, 123123.2, 321321.2]],
        index=["A", "B"],
        columns=["X", "Y", "Z"],
    )
    df.index.name = "index"

    to_compression = "infer" if to_infer else compression
    read_compression = "infer" if read_infer else compression

    with tm.ensure_clean(filename) as path:
        df.to_stata(path, compression=to_compression)
        result = read_stata(path, compression=read_compression, index_col="index")
        tm.assert_frame_equal(result, df)


def test_non_categorical_value_labels():
    data = DataFrame(
        {
            "fully_labelled": [1, 2, 3, 3, 1],
            "partially_labelled": [1.0, 2.0, np.nan, 9.0, np.nan],
            "Y": [7, 7, 9, 8, 10],
            "Z": pd.Categorical(["j", "k", "l", "k", "j"]),
        }
    )

    with tm.ensure_clean() as path:
        value_labels = {
            "fully_labelled": {1: "one", 2: "two", 3: "three"},
            "partially_labelled": {1.0: "one", 2.0: "two"},
        }
        expected = {**value_labels, "Z": {0: "j", 1: "k", 2: "l"}}

        writer = StataWriter(path, data, value_labels=value_labels)
        writer.write_file()

        with StataReader(path) as reader:
            reader_value_labels = reader.value_labels()
            assert reader_value_labels == expected

        msg = "Can't create value labels for notY, it wasn't found in the dataset."
        with pytest.raises(KeyError, match=msg):
            value_labels = {"notY": {7: "label1", 8: "label2"}}
            StataWriter(path, data, value_labels=value_labels)

        msg = (
            "Can't create value labels for Z, value labels "
            "can only be applied to numeric columns."
        )
        with pytest.raises(ValueError, match=msg):
            value_labels = {"Z": {1: "a", 2: "k", 3: "j", 4: "i"}}
            StataWriter(path, data, value_labels=value_labels)


def test_non_categorical_value_label_name_conversion():
    # Check conversion of invalid variable names
    data = DataFrame(
        {
            "invalid~!": [1, 1, 2, 3, 5, 8],  # Only alphanumeric and _
            "6_invalid": [1, 1, 2, 3, 5, 8],  # Must start with letter or _
            "invalid_name_longer_than_32_characters": [8, 8, 9, 9, 8, 8],  # Too long
            "aggregate": [2, 5, 5, 6, 6, 9],  # Reserved words
            (1, 2): [1, 2, 3, 4, 5, 6],  # Hashable non-string
        }
    )

    value_labels = {
        "invalid~!": {1: "label1", 2: "label2"},
        "6_invalid": {1: "label1", 2: "label2"},
        "invalid_name_longer_than_32_characters": {8: "eight", 9: "nine"},
        "aggregate": {5: "five"},
        (1, 2): {3: "three"},
    }

    expected = {
        "invalid__": {1: "label1", 2: "label2"},
        "_6_invalid": {1: "label1", 2: "label2"},
        "invalid_name_longer_than_32_char": {8: "eight", 9: "nine"},
        "_aggregate": {5: "five"},
        "_1__2_": {3: "three"},
    }

    with tm.ensure_clean() as path:
        with tm.assert_produces_warning(InvalidColumnName):
            data.to_stata(path, value_labels=value_labels)

        with StataReader(path) as reader:
            reader_value_labels = reader.value_labels()
            assert reader_value_labels == expected


def test_non_categorical_value_label_convert_categoricals_error():
    # Mapping more than one value to the same label is valid for Stata
    # labels, but can't be read with convert_categoricals=True
    value_labels = {
        "repeated_labels": {10: "Ten", 20: "More than ten", 40: "More than ten"}
    }

    data = DataFrame(
        {
            "repeated_labels": [10, 10, 20, 20, 40, 40],
        }
    )

    with tm.ensure_clean() as path:
        data.to_stata(path, value_labels=value_labels)

        with StataReader(path, convert_categoricals=False) as reader:
            reader_value_labels = reader.value_labels()
        assert reader_value_labels == value_labels

        col = "repeated_labels"
        repeats = "-" * 80 + "\n" + "\n".join(["More than ten"])

        msg = f"""
Value labels for column {col} are not unique. These cannot be converted to
pandas categoricals.

Either read the file with `convert_categoricals` set to False or use the
low level interface in `StataReader` to separately read the values and the
value_labels.

The repeated labels are:
{repeats}
"""
        with pytest.raises(ValueError, match=msg):
            read_stata(path, convert_categoricals=True)


@pytest.mark.parametrize("version", [114, 117, 118, 119, None])
@pytest.mark.parametrize(
    "dtype",
    [
        pd.BooleanDtype,
        pd.Int8Dtype,
        pd.Int16Dtype,
        pd.Int32Dtype,
        pd.Int64Dtype,
        pd.UInt8Dtype,
        pd.UInt16Dtype,
        pd.UInt32Dtype,
        pd.UInt64Dtype,
    ],
)
def test_nullable_support(dtype, version):
    df = DataFrame(
        {
            "a": Series([1.0, 2.0, 3.0]),
            "b": Series([1, pd.NA, pd.NA], dtype=dtype.name),
            "c": Series(["a", "b", None]),
        }
    )
    dtype_name = df.b.dtype.numpy_dtype.name
    # Only use supported names: no uint, bool or int64
    dtype_name = dtype_name.replace("u", "")
    if dtype_name == "int64":
        dtype_name = "int32"
    elif dtype_name == "bool":
        dtype_name = "int8"
    value = StataMissingValue.BASE_MISSING_VALUES[dtype_name]
    smv = StataMissingValue(value)
    expected_b = Series([1, smv, smv], dtype=object, name="b")
    expected_c = Series(["a", "b", ""], name="c")
    with tm.ensure_clean() as path:
        df.to_stata(path, write_index=False, version=version)
        reread = read_stata(path, convert_missing=True)
        tm.assert_series_equal(df.a, reread.a)
        tm.assert_series_equal(reread.b, expected_b)
        tm.assert_series_equal(reread.c, expected_c)


def test_empty_frame():
    # GH 46240
    # create an empty DataFrame with int64 and float64 dtypes
    df = DataFrame(data={"a": range(3), "b": [1.0, 2.0, 3.0]}).head(0)
    with tm.ensure_clean() as path:
        df.to_stata(path, write_index=False, version=117)
        # Read entire dataframe
        df2 = read_stata(path)
        assert "b" in df2
        # Dtypes don't match since no support for int32
        dtypes = Series({"a": np.dtype("int32"), "b": np.dtype("float64")})
        tm.assert_series_equal(df2.dtypes, dtypes)
        # read one column of empty .dta file
        df3 = read_stata(path, columns=["a"])
        assert "b" not in df3
        tm.assert_series_equal(df3.dtypes, dtypes.loc[["a"]])
