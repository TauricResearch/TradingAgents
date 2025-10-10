"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from io import (
    BytesIO,
    StringIO,
)
import os
import platform
from urllib.error import URLError
import uuid

import numpy as np
import pytest

from pandas.errors import (
    EmptyDataError,
    ParserError,
)
import pandas.util._test_decorators as td

from pandas import (
    DataFrame,
    Index,
)
import pandas._testing as tm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)

xfail_pyarrow = pytest.mark.usefixtures("pyarrow_xfail")
skip_pyarrow = pytest.mark.usefixtures("pyarrow_skip")


@pytest.mark.network
@pytest.mark.single_cpu
def test_url(all_parsers, csv_dir_path, httpserver):
    parser = all_parsers
    kwargs = {"sep": "\t"}

    local_path = os.path.join(csv_dir_path, "salaries.csv")
    with open(local_path, encoding="utf-8") as f:
        httpserver.serve_content(content=f.read())

    url_result = parser.read_csv(httpserver.url, **kwargs)

    local_result = parser.read_csv(local_path, **kwargs)
    tm.assert_frame_equal(url_result, local_result)


@pytest.mark.slow
def test_local_file(all_parsers, csv_dir_path):
    parser = all_parsers
    kwargs = {"sep": "\t"}

    local_path = os.path.join(csv_dir_path, "salaries.csv")
    local_result = parser.read_csv(local_path, **kwargs)
    url = "file://localhost/" + local_path

    try:
        url_result = parser.read_csv(url, **kwargs)
        tm.assert_frame_equal(url_result, local_result)
    except URLError:
        # Fails on some systems.
        pytest.skip("Failing on: " + " ".join(platform.uname()))


@xfail_pyarrow  # AssertionError: DataFrame.index are different
def test_path_path_lib(all_parsers):
    parser = all_parsers
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )
    result = tm.round_trip_pathlib(df.to_csv, lambda p: parser.read_csv(p, index_col=0))
    tm.assert_frame_equal(df, result)


@xfail_pyarrow  # AssertionError: DataFrame.index are different
def test_path_local_path(all_parsers):
    parser = all_parsers
    df = DataFrame(
        1.1 * np.arange(120).reshape((30, 4)),
        columns=Index(list("ABCD")),
        index=Index([f"i-{i}" for i in range(30)]),
    )
    result = tm.round_trip_localpath(
        df.to_csv, lambda p: parser.read_csv(p, index_col=0)
    )
    tm.assert_frame_equal(df, result)


def test_nonexistent_path(all_parsers):
    # gh-2428: pls no segfault
    # gh-14086: raise more helpful FileNotFoundError
    # GH#29233 "File foo" instead of "File b'foo'"
    parser = all_parsers
    path = f"{uuid.uuid4()}.csv"

    msg = r"\[Errno 2\]"
    with pytest.raises(FileNotFoundError, match=msg) as e:
        parser.read_csv(path)
    assert path == e.value.filename


@td.skip_if_windows  # os.chmod does not work in windows
def test_no_permission(all_parsers):
    # GH 23784
    parser = all_parsers

    msg = r"\[Errno 13\]"
    with tm.ensure_clean() as path:
        os.chmod(path, 0)  # make file unreadable

        # verify that this process cannot open the file (not running as sudo)
        try:
            with open(path, encoding="utf-8"):
                pass
            pytest.skip("Running as sudo.")
        except PermissionError:
            pass

        with pytest.raises(PermissionError, match=msg) as e:
            parser.read_csv(path)
        assert path == e.value.filename


@pytest.mark.parametrize(
    "data,kwargs,expected,msg",
    [
        # gh-10728: WHITESPACE_LINE
        (
            "a,b,c\n4,5,6\n ",
            {},
            DataFrame([[4, 5, 6]], columns=["a", "b", "c"]),
            None,
        ),
        # gh-10548: EAT_LINE_COMMENT
        (
            "a,b,c\n4,5,6\n#comment",
            {"comment": "#"},
            DataFrame([[4, 5, 6]], columns=["a", "b", "c"]),
            None,
        ),
        # EAT_CRNL_NOP
        (
            "a,b,c\n4,5,6\n\r",
            {},
            DataFrame([[4, 5, 6]], columns=["a", "b", "c"]),
            None,
        ),
        # EAT_COMMENT
        (
            "a,b,c\n4,5,6#comment",
            {"comment": "#"},
            DataFrame([[4, 5, 6]], columns=["a", "b", "c"]),
            None,
        ),
        # SKIP_LINE
        (
            "a,b,c\n4,5,6\nskipme",
            {"skiprows": [2]},
            DataFrame([[4, 5, 6]], columns=["a", "b", "c"]),
            None,
        ),
        # EAT_LINE_COMMENT
        (
            "a,b,c\n4,5,6\n#comment",
            {"comment": "#", "skip_blank_lines": False},
            DataFrame([[4, 5, 6]], columns=["a", "b", "c"]),
            None,
        ),
        # IN_FIELD
        (
            "a,b,c\n4,5,6\n ",
            {"skip_blank_lines": False},
            DataFrame([["4", 5, 6], [" ", None, None]], columns=["a", "b", "c"]),
            None,
        ),
        # EAT_CRNL
        (
            "a,b,c\n4,5,6\n\r",
            {"skip_blank_lines": False},
            DataFrame([[4, 5, 6], [None, None, None]], columns=["a", "b", "c"]),
            None,
        ),
        # ESCAPED_CHAR
        (
            "a,b,c\n4,5,6\n\\",
            {"escapechar": "\\"},
            None,
            "(EOF following escape character)|(unexpected end of data)",
        ),
        # ESCAPE_IN_QUOTED_FIELD
        (
            'a,b,c\n4,5,6\n"\\',
            {"escapechar": "\\"},
            None,
            "(EOF inside string starting at row 2)|(unexpected end of data)",
        ),
        # IN_QUOTED_FIELD
        (
            'a,b,c\n4,5,6\n"',
            {"escapechar": "\\"},
            None,
            "(EOF inside string starting at row 2)|(unexpected end of data)",
        ),
    ],
    ids=[
        "whitespace-line",
        "eat-line-comment",
        "eat-crnl-nop",
        "eat-comment",
        "skip-line",
        "eat-line-comment",
        "in-field",
        "eat-crnl",
        "escaped-char",
        "escape-in-quoted-field",
        "in-quoted-field",
    ],
)
def test_eof_states(all_parsers, data, kwargs, expected, msg, request):
    # see gh-10728, gh-10548
    parser = all_parsers

    if parser.engine == "pyarrow" and "comment" in kwargs:
        msg = "The 'comment' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(StringIO(data), **kwargs)
        return

    if parser.engine == "pyarrow" and "\r" not in data:
        # pandas.errors.ParserError: CSV parse error: Expected 3 columns, got 1:
        # ValueError: skiprows argument must be an integer when using engine='pyarrow'
        # AssertionError: Regex pattern did not match.
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    if expected is None:
        with pytest.raises(ParserError, match=msg):
            parser.read_csv(StringIO(data), **kwargs)
    else:
        result = parser.read_csv(StringIO(data), **kwargs)
        tm.assert_frame_equal(result, expected)


def test_temporary_file(all_parsers):
    # see gh-13398
    parser = all_parsers
    data = "0 0"

    with tm.ensure_clean(mode="w+", return_filelike=True) as new_file:
        new_file.write(data)
        new_file.flush()
        new_file.seek(0)

        if parser.engine == "pyarrow":
            msg = "the 'pyarrow' engine does not support regex separators"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(new_file, sep=r"\s+", header=None)
            return

        result = parser.read_csv(new_file, sep=r"\s+", header=None)

        expected = DataFrame([[0, 0]])
        tm.assert_frame_equal(result, expected)


def test_internal_eof_byte(all_parsers):
    # see gh-5500
    parser = all_parsers
    data = "a,b\n1\x1a,2"

    expected = DataFrame([["1\x1a", 2]], columns=["a", "b"])
    result = parser.read_csv(StringIO(data))
    tm.assert_frame_equal(result, expected)


def test_internal_eof_byte_to_file(all_parsers):
    # see gh-16559
    parser = all_parsers
    data = b'c1,c2\r\n"test \x1a    test", test\r\n'
    expected = DataFrame([["test \x1a    test", " test"]], columns=["c1", "c2"])
    path = f"__{uuid.uuid4()}__.csv"

    with tm.ensure_clean(path) as path:
        with open(path, "wb") as f:
            f.write(data)

        result = parser.read_csv(path)
        tm.assert_frame_equal(result, expected)


def test_file_handle_string_io(all_parsers):
    # gh-14418
    #
    # Don't close user provided file handles.
    parser = all_parsers
    data = "a,b\n1,2"

    fh = StringIO(data)
    parser.read_csv(fh)
    assert not fh.closed


def test_file_handles_with_open(all_parsers, csv1):
    # gh-14418
    #
    # Don't close user provided file handles.
    parser = all_parsers

    for mode in ["r", "rb"]:
        with open(csv1, mode, encoding="utf-8" if mode == "r" else None) as f:
            parser.read_csv(f)
            assert not f.closed


def test_invalid_file_buffer_class(all_parsers):
    # see gh-15337
    class InvalidBuffer:
        pass

    parser = all_parsers
    msg = "Invalid file path or buffer object type"

    with pytest.raises(ValueError, match=msg):
        parser.read_csv(InvalidBuffer())


def test_invalid_file_buffer_mock(all_parsers):
    # see gh-15337
    parser = all_parsers
    msg = "Invalid file path or buffer object type"

    class Foo:
        pass

    with pytest.raises(ValueError, match=msg):
        parser.read_csv(Foo())


def test_valid_file_buffer_seems_invalid(all_parsers):
    # gh-16135: we want to ensure that "tell" and "seek"
    # aren't actually being used when we call `read_csv`
    #
    # Thus, while the object may look "invalid" (these
    # methods are attributes of the `StringIO` class),
    # it is still a valid file-object for our purposes.
    class NoSeekTellBuffer(StringIO):
        def tell(self):
            raise AttributeError("No tell method")

        def seek(self, pos, whence=0):
            raise AttributeError("No seek method")

    data = "a\n1"
    parser = all_parsers
    expected = DataFrame({"a": [1]})

    result = parser.read_csv(NoSeekTellBuffer(data))
    tm.assert_frame_equal(result, expected)


@pytest.mark.parametrize("io_class", [StringIO, BytesIO])
@pytest.mark.parametrize("encoding", [None, "utf-8"])
def test_read_csv_file_handle(all_parsers, io_class, encoding):
    """
    Test whether read_csv does not close user-provided file handles.

    GH 36980
    """
    parser = all_parsers
    expected = DataFrame({"a": [1], "b": [2]})

    content = "a,b\n1,2"
    handle = io_class(content.encode("utf-8") if io_class == BytesIO else content)

    tm.assert_frame_equal(parser.read_csv(handle, encoding=encoding), expected)
    assert not handle.closed


def test_memory_map_compression(all_parsers, compression):
    """
    Support memory map for compressed files.

    GH 37621
    """
    parser = all_parsers
    expected = DataFrame({"a": [1], "b": [2]})

    with tm.ensure_clean() as path:
        expected.to_csv(path, index=False, compression=compression)

        if parser.engine == "pyarrow":
            msg = "The 'memory_map' option is not supported with the 'pyarrow' engine"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(path, memory_map=True, compression=compression)
            return

        result = parser.read_csv(path, memory_map=True, compression=compression)

    tm.assert_frame_equal(
        result,
        expected,
    )


def test_context_manager(all_parsers, datapath):
    # make sure that opened files are closed
    parser = all_parsers

    path = datapath("io", "data", "csv", "iris.csv")

    if parser.engine == "pyarrow":
        msg = "The 'chunksize' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(path, chunksize=1)
        return

    reader = parser.read_csv(path, chunksize=1)
    assert not reader.handles.handle.closed
    try:
        with reader:
            next(reader)
            assert False
    except AssertionError:
        assert reader.handles.handle.closed


def test_context_manageri_user_provided(all_parsers, datapath):
    # make sure that user-provided handles are not closed
    parser = all_parsers

    with open(datapath("io", "data", "csv", "iris.csv"), encoding="utf-8") as path:
        if parser.engine == "pyarrow":
            msg = "The 'chunksize' option is not supported with the 'pyarrow' engine"
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(path, chunksize=1)
            return

        reader = parser.read_csv(path, chunksize=1)
        assert not reader.handles.handle.closed
        try:
            with reader:
                next(reader)
                assert False
        except AssertionError:
            assert not reader.handles.handle.closed


@skip_pyarrow  # ParserError: Empty CSV file
def test_file_descriptor_leak(all_parsers, using_copy_on_write):
    # GH 31488
    parser = all_parsers
    with tm.ensure_clean() as path:
        with pytest.raises(EmptyDataError, match="No columns to parse from file"):
            parser.read_csv(path)


def test_memory_map(all_parsers, csv_dir_path):
    mmap_file = os.path.join(csv_dir_path, "test_mmap.csv")
    parser = all_parsers

    expected = DataFrame(
        {"a": [1, 2, 3], "b": ["one", "two", "three"], "c": ["I", "II", "III"]}
    )

    if parser.engine == "pyarrow":
        msg = "The 'memory_map' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            parser.read_csv(mmap_file, memory_map=True)
        return

    result = parser.read_csv(mmap_file, memory_map=True)
    tm.assert_frame_equal(result, expected)
