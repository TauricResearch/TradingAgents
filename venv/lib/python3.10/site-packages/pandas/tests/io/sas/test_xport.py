import numpy as np
import pytest

import pandas as pd
import pandas._testing as tm

from pandas.io.sas.sasreader import read_sas

# CSV versions of test xpt files were obtained using the R foreign library

# Numbers in a SAS xport file are always float64, so need to convert
# before making comparisons.


def numeric_as_float(data):
    for v in data.columns:
        if data[v].dtype is np.dtype("int64"):
            data[v] = data[v].astype(np.float64)


class TestXport:
    @pytest.fixture
    def file01(self, datapath):
        return datapath("io", "sas", "data", "DEMO_G.xpt")

    @pytest.fixture
    def file02(self, datapath):
        return datapath("io", "sas", "data", "SSHSV1_A.xpt")

    @pytest.fixture
    def file03(self, datapath):
        return datapath("io", "sas", "data", "DRXFCD_G.xpt")

    @pytest.fixture
    def file04(self, datapath):
        return datapath("io", "sas", "data", "paxraw_d_short.xpt")

    @pytest.fixture
    def file05(self, datapath):
        return datapath("io", "sas", "data", "DEMO_PUF.cpt")

    @pytest.mark.slow
    def test1_basic(self, file01):
        # Tests with DEMO_G.xpt (all numeric file)

        # Compare to this
        data_csv = pd.read_csv(file01.replace(".xpt", ".csv"))
        numeric_as_float(data_csv)

        # Read full file
        data = read_sas(file01, format="xport")
        tm.assert_frame_equal(data, data_csv)
        num_rows = data.shape[0]

        # Test reading beyond end of file
        with read_sas(file01, format="xport", iterator=True) as reader:
            data = reader.read(num_rows + 100)
        assert data.shape[0] == num_rows

        # Test incremental read with `read` method.
        with read_sas(file01, format="xport", iterator=True) as reader:
            data = reader.read(10)
        tm.assert_frame_equal(data, data_csv.iloc[0:10, :])

        # Test incremental read with `get_chunk` method.
        with read_sas(file01, format="xport", chunksize=10) as reader:
            data = reader.get_chunk()
        tm.assert_frame_equal(data, data_csv.iloc[0:10, :])

        # Test read in loop
        m = 0
        with read_sas(file01, format="xport", chunksize=100) as reader:
            for x in reader:
                m += x.shape[0]
        assert m == num_rows

        # Read full file with `read_sas` method
        data = read_sas(file01)
        tm.assert_frame_equal(data, data_csv)

    def test1_index(self, file01):
        # Tests with DEMO_G.xpt using index (all numeric file)

        # Compare to this
        data_csv = pd.read_csv(file01.replace(".xpt", ".csv"))
        data_csv = data_csv.set_index("SEQN")
        numeric_as_float(data_csv)

        # Read full file
        data = read_sas(file01, index="SEQN", format="xport")
        tm.assert_frame_equal(data, data_csv, check_index_type=False)

        # Test incremental read with `read` method.
        with read_sas(file01, index="SEQN", format="xport", iterator=True) as reader:
            data = reader.read(10)
        tm.assert_frame_equal(data, data_csv.iloc[0:10, :], check_index_type=False)

        # Test incremental read with `get_chunk` method.
        with read_sas(file01, index="SEQN", format="xport", chunksize=10) as reader:
            data = reader.get_chunk()
        tm.assert_frame_equal(data, data_csv.iloc[0:10, :], check_index_type=False)

    def test1_incremental(self, file01):
        # Test with DEMO_G.xpt, reading full file incrementally

        data_csv = pd.read_csv(file01.replace(".xpt", ".csv"))
        data_csv = data_csv.set_index("SEQN")
        numeric_as_float(data_csv)

        with read_sas(file01, index="SEQN", chunksize=1000) as reader:
            all_data = list(reader)
        data = pd.concat(all_data, axis=0)

        tm.assert_frame_equal(data, data_csv, check_index_type=False)

    def test2(self, file02):
        # Test with SSHSV1_A.xpt

        # Compare to this
        data_csv = pd.read_csv(file02.replace(".xpt", ".csv"))
        numeric_as_float(data_csv)

        data = read_sas(file02)
        tm.assert_frame_equal(data, data_csv)

    def test2_binary(self, file02):
        # Test with SSHSV1_A.xpt, read as a binary file

        # Compare to this
        data_csv = pd.read_csv(file02.replace(".xpt", ".csv"))
        numeric_as_float(data_csv)

        with open(file02, "rb") as fd:
            # GH#35693 ensure that if we pass an open file, we
            #  dont incorrectly close it in read_sas
            data = read_sas(fd, format="xport")

        tm.assert_frame_equal(data, data_csv)

    def test_multiple_types(self, file03):
        # Test with DRXFCD_G.xpt (contains text and numeric variables)

        # Compare to this
        data_csv = pd.read_csv(file03.replace(".xpt", ".csv"))

        data = read_sas(file03, encoding="utf-8")
        tm.assert_frame_equal(data, data_csv)

    def test_truncated_float_support(self, file04):
        # Test with paxraw_d_short.xpt, a shortened version of:
        # http://wwwn.cdc.gov/Nchs/Nhanes/2005-2006/PAXRAW_D.ZIP
        # This file has truncated floats (5 bytes in this case).

        # GH 11713

        data_csv = pd.read_csv(file04.replace(".xpt", ".csv"))

        data = read_sas(file04, format="xport")
        tm.assert_frame_equal(data.astype("int64"), data_csv)

    def test_cport_header_found_raises(self, file05):
        # Test with DEMO_PUF.cpt, the beginning of puf2019_1_fall.xpt
        # from https://www.cms.gov/files/zip/puf2019.zip
        # (despite the extension, it's a cpt file)
        msg = "Header record indicates a CPORT file, which is not readable."
        with pytest.raises(ValueError, match=msg):
            read_sas(file05, format="xport")
