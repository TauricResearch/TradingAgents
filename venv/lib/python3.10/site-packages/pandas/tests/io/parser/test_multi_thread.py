"""
Tests multithreading behaviour for reading and
parsing files for each parser defined in parsers.py
"""
from contextlib import ExitStack
from io import BytesIO
from multiprocessing.pool import ThreadPool

import numpy as np
import pytest

import pandas as pd
from pandas import DataFrame
import pandas._testing as tm
from pandas.util.version import Version

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")

# We'll probably always skip these for pyarrow
# Maybe we'll add our own tests for pyarrow too
pytestmark = [
    pytest.mark.single_cpu,
    pytest.mark.slow,
]


@pytest.mark.filterwarnings("ignore:Passing a BlockManager:DeprecationWarning")
def test_multi_thread_string_io_read_csv(all_parsers, request):
    # see gh-11786
    parser = all_parsers
    if parser.engine == "pyarrow":
        pa = pytest.importorskip("pyarrow")
        if Version(pa.__version__) < Version("16.0"):
            request.applymarker(
                pytest.mark.xfail(reason="# ValueError: Found non-unique column index")
            )
    max_row_range = 100
    num_files = 10

    bytes_to_df = (
        "\n".join([f"{i:d},{i:d},{i:d}" for i in range(max_row_range)]).encode()
        for _ in range(num_files)
    )

    # Read all files in many threads.
    with ExitStack() as stack:
        files = [stack.enter_context(BytesIO(b)) for b in bytes_to_df]

        pool = stack.enter_context(ThreadPool(8))

        results = pool.map(parser.read_csv, files)
        first_result = results[0]

        for result in results:
            tm.assert_frame_equal(first_result, result)


def _generate_multi_thread_dataframe(parser, path, num_rows, num_tasks):
    """
    Generate a DataFrame via multi-thread.

    Parameters
    ----------
    parser : BaseParser
        The parser object to use for reading the data.
    path : str
        The location of the CSV file to read.
    num_rows : int
        The number of rows to read per task.
    num_tasks : int
        The number of tasks to use for reading this DataFrame.

    Returns
    -------
    df : DataFrame
    """

    def reader(arg):
        """
        Create a reader for part of the CSV.

        Parameters
        ----------
        arg : tuple
            A tuple of the following:

            * start : int
                The starting row to start for parsing CSV
            * nrows : int
                The number of rows to read.

        Returns
        -------
        df : DataFrame
        """
        start, nrows = arg

        if not start:
            return parser.read_csv(
                path, index_col=0, header=0, nrows=nrows, parse_dates=["date"]
            )

        return parser.read_csv(
            path,
            index_col=0,
            header=None,
            skiprows=int(start) + 1,
            nrows=nrows,
            parse_dates=[9],
        )

    tasks = [
        (num_rows * i // num_tasks, num_rows // num_tasks) for i in range(num_tasks)
    ]

    with ThreadPool(processes=num_tasks) as pool:
        results = pool.map(reader, tasks)

    header = results[0].columns

    for r in results[1:]:
        r.columns = header

    final_dataframe = pd.concat(results)
    return final_dataframe


@xfail_pyarrow  # ValueError: The 'nrows' option is not supported
def test_multi_thread_path_multipart_read_csv(all_parsers):
    # see gh-11786
    num_tasks = 4
    num_rows = 48

    parser = all_parsers
    file_name = "__thread_pool_reader__.csv"
    df = DataFrame(
        {
            "a": np.random.default_rng(2).random(num_rows),
            "b": np.random.default_rng(2).random(num_rows),
            "c": np.random.default_rng(2).random(num_rows),
            "d": np.random.default_rng(2).random(num_rows),
            "e": np.random.default_rng(2).random(num_rows),
            "foo": ["foo"] * num_rows,
            "bar": ["bar"] * num_rows,
            "baz": ["baz"] * num_rows,
            "date": pd.date_range("20000101 09:00:00", periods=num_rows, freq="s"),
            "int": np.arange(num_rows, dtype="int64"),
        }
    )

    with tm.ensure_clean(file_name) as path:
        df.to_csv(path)

        final_dataframe = _generate_multi_thread_dataframe(
            parser, path, num_rows, num_tasks
        )
        tm.assert_frame_equal(df, final_dataframe)
