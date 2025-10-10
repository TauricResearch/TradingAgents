import pytest

import pandas as pd
import pandas._testing as tm

tables = pytest.importorskip("tables")


@pytest.fixture
def pytables_hdf5_file(tmp_path):
    """
    Use PyTables to create a simple HDF5 file.
    """
    table_schema = {
        "c0": tables.Time64Col(pos=0),
        "c1": tables.StringCol(5, pos=1),
        "c2": tables.Int64Col(pos=2),
    }

    t0 = 1_561_105_000.0

    testsamples = [
        {"c0": t0, "c1": "aaaaa", "c2": 1},
        {"c0": t0 + 1, "c1": "bbbbb", "c2": 2},
        {"c0": t0 + 2, "c1": "ccccc", "c2": 10**5},
        {"c0": t0 + 3, "c1": "ddddd", "c2": 4_294_967_295},
    ]

    objname = "pandas_test_timeseries"

    path = tmp_path / "written_with_pytables.h5"
    with tables.open_file(path, mode="w") as f:
        t = f.create_table("/", name=objname, description=table_schema)
        for sample in testsamples:
            for key, value in sample.items():
                t.row[key] = value
            t.row.append()

    yield path, objname, pd.DataFrame(testsamples)


class TestReadPyTablesHDF5:
    """
    A group of tests which covers reading HDF5 files written by plain PyTables
    (not written by pandas).

    Was introduced for regression-testing issue 11188.
    """

    def test_read_complete(self, pytables_hdf5_file):
        path, objname, df = pytables_hdf5_file
        result = pd.read_hdf(path, key=objname)
        expected = df
        tm.assert_frame_equal(result, expected, check_index_type=True)

    def test_read_with_start(self, pytables_hdf5_file):
        path, objname, df = pytables_hdf5_file
        # This is a regression test for pandas-dev/pandas/issues/11188
        result = pd.read_hdf(path, key=objname, start=1)
        expected = df[1:].reset_index(drop=True)
        tm.assert_frame_equal(result, expected, check_index_type=True)

    def test_read_with_stop(self, pytables_hdf5_file):
        path, objname, df = pytables_hdf5_file
        # This is a regression test for pandas-dev/pandas/issues/11188
        result = pd.read_hdf(path, key=objname, stop=1)
        expected = df[:1].reset_index(drop=True)
        tm.assert_frame_equal(result, expected, check_index_type=True)

    def test_read_with_startstop(self, pytables_hdf5_file):
        path, objname, df = pytables_hdf5_file
        # This is a regression test for pandas-dev/pandas/issues/11188
        result = pd.read_hdf(path, key=objname, start=1, stop=2)
        expected = df[1:2].reset_index(drop=True)
        tm.assert_frame_equal(result, expected, check_index_type=True)
