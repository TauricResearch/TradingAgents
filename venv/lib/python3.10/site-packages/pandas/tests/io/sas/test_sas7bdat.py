import contextlib
from datetime import datetime
import io
import os
from pathlib import Path

import numpy as np
import pytest

from pandas.compat import IS64
from pandas.errors import EmptyDataError
import pandas.util._test_decorators as td

import pandas as pd
import pandas._testing as tm

from pandas.io.sas.sas7bdat import SAS7BDATReader


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "sas", "data")


@pytest.fixture(params=[(1, range(1, 16)), (2, [16])])
def data_test_ix(request, dirpath):
    i, test_ix = request.param
    fname = os.path.join(dirpath, f"test_sas7bdat_{i}.csv")
    df = pd.read_csv(fname)
    epoch = datetime(1960, 1, 1)
    t1 = pd.to_timedelta(df["Column4"], unit="d")
    df["Column4"] = (epoch + t1).astype("M8[s]")
    t2 = pd.to_timedelta(df["Column12"], unit="d")
    df["Column12"] = (epoch + t2).astype("M8[s]")
    for k in range(df.shape[1]):
        col = df.iloc[:, k]
        if col.dtype == np.int64:
            df.isetitem(k, df.iloc[:, k].astype(np.float64))
    return df, test_ix


# https://github.com/cython/cython/issues/1720
class TestSAS7BDAT:
    @pytest.mark.slow
    def test_from_file(self, dirpath, data_test_ix):
        expected, test_ix = data_test_ix
        for k in test_ix:
            fname = os.path.join(dirpath, f"test{k}.sas7bdat")
            df = pd.read_sas(fname, encoding="utf-8")
            tm.assert_frame_equal(df, expected)

    @pytest.mark.slow
    def test_from_buffer(self, dirpath, data_test_ix):
        expected, test_ix = data_test_ix
        for k in test_ix:
            fname = os.path.join(dirpath, f"test{k}.sas7bdat")
            with open(fname, "rb") as f:
                byts = f.read()
            buf = io.BytesIO(byts)
            with pd.read_sas(
                buf, format="sas7bdat", iterator=True, encoding="utf-8"
            ) as rdr:
                df = rdr.read()
            tm.assert_frame_equal(df, expected)

    @pytest.mark.slow
    def test_from_iterator(self, dirpath, data_test_ix):
        expected, test_ix = data_test_ix
        for k in test_ix:
            fname = os.path.join(dirpath, f"test{k}.sas7bdat")
            with pd.read_sas(fname, iterator=True, encoding="utf-8") as rdr:
                df = rdr.read(2)
                tm.assert_frame_equal(df, expected.iloc[0:2, :])
                df = rdr.read(3)
                tm.assert_frame_equal(df, expected.iloc[2:5, :])

    @pytest.mark.slow
    def test_path_pathlib(self, dirpath, data_test_ix):
        expected, test_ix = data_test_ix
        for k in test_ix:
            fname = Path(os.path.join(dirpath, f"test{k}.sas7bdat"))
            df = pd.read_sas(fname, encoding="utf-8")
            tm.assert_frame_equal(df, expected)

    @td.skip_if_no("py.path")
    @pytest.mark.slow
    def test_path_localpath(self, dirpath, data_test_ix):
        from py.path import local as LocalPath

        expected, test_ix = data_test_ix
        for k in test_ix:
            fname = LocalPath(os.path.join(dirpath, f"test{k}.sas7bdat"))
            df = pd.read_sas(fname, encoding="utf-8")
            tm.assert_frame_equal(df, expected)

    @pytest.mark.slow
    @pytest.mark.parametrize("chunksize", (3, 5, 10, 11))
    @pytest.mark.parametrize("k", range(1, 17))
    def test_iterator_loop(self, dirpath, k, chunksize):
        # github #13654
        fname = os.path.join(dirpath, f"test{k}.sas7bdat")
        with pd.read_sas(fname, chunksize=chunksize, encoding="utf-8") as rdr:
            y = 0
            for x in rdr:
                y += x.shape[0]
        assert y == rdr.row_count

    def test_iterator_read_too_much(self, dirpath):
        # github #14734
        fname = os.path.join(dirpath, "test1.sas7bdat")
        with pd.read_sas(
            fname, format="sas7bdat", iterator=True, encoding="utf-8"
        ) as rdr:
            d1 = rdr.read(rdr.row_count + 20)

        with pd.read_sas(fname, iterator=True, encoding="utf-8") as rdr:
            d2 = rdr.read(rdr.row_count + 20)
        tm.assert_frame_equal(d1, d2)


def test_encoding_options(datapath):
    fname = datapath("io", "sas", "data", "test1.sas7bdat")
    df1 = pd.read_sas(fname)
    df2 = pd.read_sas(fname, encoding="utf-8")
    for col in df1.columns:
        try:
            df1[col] = df1[col].str.decode("utf-8")
        except AttributeError:
            pass
    tm.assert_frame_equal(df1, df2)

    with contextlib.closing(SAS7BDATReader(fname, convert_header_text=False)) as rdr:
        df3 = rdr.read()
    for x, y in zip(df1.columns, df3.columns):
        assert x == y.decode()


def test_encoding_infer(datapath):
    fname = datapath("io", "sas", "data", "test1.sas7bdat")

    with pd.read_sas(fname, encoding="infer", iterator=True) as df1_reader:
        # check: is encoding inferred correctly from file
        assert df1_reader.inferred_encoding == "cp1252"
        df1 = df1_reader.read()

    with pd.read_sas(fname, encoding="cp1252", iterator=True) as df2_reader:
        df2 = df2_reader.read()

    # check: reader reads correct information
    tm.assert_frame_equal(df1, df2)


def test_productsales(datapath):
    fname = datapath("io", "sas", "data", "productsales.sas7bdat")
    df = pd.read_sas(fname, encoding="utf-8")
    fname = datapath("io", "sas", "data", "productsales.csv")
    df0 = pd.read_csv(fname, parse_dates=["MONTH"])
    vn = ["ACTUAL", "PREDICT", "QUARTER", "YEAR"]
    df0[vn] = df0[vn].astype(np.float64)

    df0["MONTH"] = df0["MONTH"].astype("M8[s]")
    tm.assert_frame_equal(df, df0)


def test_12659(datapath):
    fname = datapath("io", "sas", "data", "test_12659.sas7bdat")
    df = pd.read_sas(fname)
    fname = datapath("io", "sas", "data", "test_12659.csv")
    df0 = pd.read_csv(fname)
    df0 = df0.astype(np.float64)
    tm.assert_frame_equal(df, df0)


def test_airline(datapath):
    fname = datapath("io", "sas", "data", "airline.sas7bdat")
    df = pd.read_sas(fname)
    fname = datapath("io", "sas", "data", "airline.csv")
    df0 = pd.read_csv(fname)
    df0 = df0.astype(np.float64)
    tm.assert_frame_equal(df, df0)


def test_date_time(datapath):
    # Support of different SAS date/datetime formats (PR #15871)
    fname = datapath("io", "sas", "data", "datetime.sas7bdat")
    df = pd.read_sas(fname)
    fname = datapath("io", "sas", "data", "datetime.csv")
    df0 = pd.read_csv(
        fname, parse_dates=["Date1", "Date2", "DateTime", "DateTimeHi", "Taiw"]
    )
    # GH 19732: Timestamps imported from sas will incur floating point errors
    # See GH#56014 for discussion of the correct "expected" results
    #  We are really just testing that we are "close". This only seems to be
    #  an issue near the implementation bounds.

    df[df.columns[3]] = df.iloc[:, 3].dt.round("us")
    df0["Date1"] = df0["Date1"].astype("M8[s]")
    df0["Date2"] = df0["Date2"].astype("M8[s]")
    df0["DateTime"] = df0["DateTime"].astype("M8[ms]")
    df0["Taiw"] = df0["Taiw"].astype("M8[s]")

    res = df0["DateTimeHi"].astype("M8[us]").dt.round("ms")
    df0["DateTimeHi"] = res.astype("M8[ms]")

    if not IS64:
        # No good reason for this, just what we get on the CI
        df0.loc[0, "DateTimeHi"] += np.timedelta64(1, "ms")
        df0.loc[[2, 3], "DateTimeHi"] -= np.timedelta64(1, "ms")
    tm.assert_frame_equal(df, df0)


@pytest.mark.parametrize("column", ["WGT", "CYL"])
def test_compact_numerical_values(datapath, column):
    # Regression test for #21616
    fname = datapath("io", "sas", "data", "cars.sas7bdat")
    df = pd.read_sas(fname, encoding="latin-1")
    # The two columns CYL and WGT in cars.sas7bdat have column
    # width < 8 and only contain integral values.
    # Test that pandas doesn't corrupt the numbers by adding
    # decimals.
    result = df[column]
    expected = df[column].round()
    tm.assert_series_equal(result, expected, check_exact=True)


def test_many_columns(datapath):
    # Test for looking for column information in more places (PR #22628)
    fname = datapath("io", "sas", "data", "many_columns.sas7bdat")

    df = pd.read_sas(fname, encoding="latin-1")

    fname = datapath("io", "sas", "data", "many_columns.csv")
    df0 = pd.read_csv(fname, encoding="latin-1")
    tm.assert_frame_equal(df, df0)


def test_inconsistent_number_of_rows(datapath):
    # Regression test for issue #16615. (PR #22628)
    fname = datapath("io", "sas", "data", "load_log.sas7bdat")
    df = pd.read_sas(fname, encoding="latin-1")
    assert len(df) == 2097


def test_zero_variables(datapath):
    # Check if the SAS file has zero variables (PR #18184)
    fname = datapath("io", "sas", "data", "zero_variables.sas7bdat")
    with pytest.raises(EmptyDataError, match="No columns to parse from file"):
        pd.read_sas(fname)


@pytest.mark.parametrize("encoding", [None, "utf8"])
def test_zero_rows(datapath, encoding):
    # GH 18198
    fname = datapath("io", "sas", "data", "zero_rows.sas7bdat")
    result = pd.read_sas(fname, encoding=encoding)
    str_value = b"a" if encoding is None else "a"
    expected = pd.DataFrame([{"char_field": str_value, "num_field": 1.0}]).iloc[:0]
    tm.assert_frame_equal(result, expected)


def test_corrupt_read(datapath):
    # We don't really care about the exact failure, the important thing is
    # that the resource should be cleaned up afterwards (BUG #35566)
    fname = datapath("io", "sas", "data", "corrupt.sas7bdat")
    msg = "'SAS7BDATReader' object has no attribute 'row_count'"
    with pytest.raises(AttributeError, match=msg):
        pd.read_sas(fname)


def test_max_sas_date(datapath):
    # GH 20927
    # NB. max datetime in SAS dataset is 31DEC9999:23:59:59.999
    #    but this is read as 29DEC9999:23:59:59.998993 by a buggy
    #    sas7bdat module
    # See also GH#56014 for discussion of the correct "expected" results.
    fname = datapath("io", "sas", "data", "max_sas_date.sas7bdat")
    df = pd.read_sas(fname, encoding="iso-8859-1")

    expected = pd.DataFrame(
        {
            "text": ["max", "normal"],
            "dt_as_float": [253717747199.999, 1880323199.999],
            "dt_as_dt": np.array(
                [
                    datetime(9999, 12, 29, 23, 59, 59, 999000),
                    datetime(2019, 8, 1, 23, 59, 59, 999000),
                ],
                dtype="M8[ms]",
            ),
            "date_as_float": [2936547.0, 21762.0],
            "date_as_date": np.array(
                [
                    datetime(9999, 12, 29),
                    datetime(2019, 8, 1),
                ],
                dtype="M8[s]",
            ),
        },
        columns=["text", "dt_as_float", "dt_as_dt", "date_as_float", "date_as_date"],
    )

    if not IS64:
        # No good reason for this, just what we get on the CI
        expected.loc[:, "dt_as_dt"] -= np.timedelta64(1, "ms")

    tm.assert_frame_equal(df, expected)


def test_max_sas_date_iterator(datapath):
    # GH 20927
    # when called as an iterator, only those chunks with a date > pd.Timestamp.max
    # are returned as datetime.datetime, if this happens that whole chunk is returned
    # as datetime.datetime
    col_order = ["text", "dt_as_float", "dt_as_dt", "date_as_float", "date_as_date"]
    fname = datapath("io", "sas", "data", "max_sas_date.sas7bdat")
    results = []
    for df in pd.read_sas(fname, encoding="iso-8859-1", chunksize=1):
        # GH 19732: Timestamps imported from sas will incur floating point errors
        df.reset_index(inplace=True, drop=True)
        results.append(df)
    expected = [
        pd.DataFrame(
            {
                "text": ["max"],
                "dt_as_float": [253717747199.999],
                "dt_as_dt": np.array(
                    [datetime(9999, 12, 29, 23, 59, 59, 999000)], dtype="M8[ms]"
                ),
                "date_as_float": [2936547.0],
                "date_as_date": np.array([datetime(9999, 12, 29)], dtype="M8[s]"),
            },
            columns=col_order,
        ),
        pd.DataFrame(
            {
                "text": ["normal"],
                "dt_as_float": [1880323199.999],
                "dt_as_dt": np.array(["2019-08-01 23:59:59.999"], dtype="M8[ms]"),
                "date_as_float": [21762.0],
                "date_as_date": np.array(["2019-08-01"], dtype="M8[s]"),
            },
            columns=col_order,
        ),
    ]
    if not IS64:
        # No good reason for this, just what we get on the CI
        expected[0].loc[0, "dt_as_dt"] -= np.timedelta64(1, "ms")
        expected[1].loc[0, "dt_as_dt"] -= np.timedelta64(1, "ms")

    tm.assert_frame_equal(results[0], expected[0])
    tm.assert_frame_equal(results[1], expected[1])


def test_null_date(datapath):
    fname = datapath("io", "sas", "data", "dates_null.sas7bdat")
    df = pd.read_sas(fname, encoding="utf-8")

    expected = pd.DataFrame(
        {
            "datecol": np.array(
                [
                    datetime(9999, 12, 29),
                    np.datetime64("NaT"),
                ],
                dtype="M8[s]",
            ),
            "datetimecol": np.array(
                [
                    datetime(9999, 12, 29, 23, 59, 59, 999000),
                    np.datetime64("NaT"),
                ],
                dtype="M8[ms]",
            ),
        },
    )
    if not IS64:
        # No good reason for this, just what we get on the CI
        expected.loc[0, "datetimecol"] -= np.timedelta64(1, "ms")
    tm.assert_frame_equal(df, expected)


def test_meta2_page(datapath):
    # GH 35545
    fname = datapath("io", "sas", "data", "test_meta2_page.sas7bdat")
    df = pd.read_sas(fname)
    assert len(df) == 1000


@pytest.mark.parametrize(
    "test_file, override_offset, override_value, expected_msg",
    [
        ("test2.sas7bdat", 0x10000 + 55229, 0x80 | 0x0F, "Out of bounds"),
        ("test2.sas7bdat", 0x10000 + 55229, 0x10, "unknown control byte"),
        ("test3.sas7bdat", 118170, 184, "Out of bounds"),
    ],
)
def test_rle_rdc_exceptions(
    datapath, test_file, override_offset, override_value, expected_msg
):
    """Errors in RLE/RDC decompression should propagate."""
    with open(datapath("io", "sas", "data", test_file), "rb") as fd:
        data = bytearray(fd.read())
    data[override_offset] = override_value
    with pytest.raises(Exception, match=expected_msg):
        pd.read_sas(io.BytesIO(data), format="sas7bdat")


def test_0x40_control_byte(datapath):
    # GH 31243
    fname = datapath("io", "sas", "data", "0x40controlbyte.sas7bdat")
    df = pd.read_sas(fname, encoding="ascii")
    fname = datapath("io", "sas", "data", "0x40controlbyte.csv")
    df0 = pd.read_csv(fname, dtype="str")
    tm.assert_frame_equal(df, df0)


def test_0x00_control_byte(datapath):
    # GH 47099
    fname = datapath("io", "sas", "data", "0x00controlbyte.sas7bdat.bz2")
    df = next(pd.read_sas(fname, chunksize=11_000))
    assert df.shape == (11_000, 20)
