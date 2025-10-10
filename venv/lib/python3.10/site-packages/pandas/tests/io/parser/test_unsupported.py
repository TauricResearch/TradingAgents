"""
Tests that features that are currently unsupported in
either the Python or C parser are actually enforced
and are clearly communicated to the user.

Ultimately, the goal is to remove test cases from this
test suite as new feature support is added to the parsers.
"""
from io import StringIO
import os
from pathlib import Path

import pytest

from pandas.errors import ParserError

import pandas._testing as tm

from pandas.io.parsers import read_csv
import pandas.io.parsers.readers as parsers

pytestmark = pytest.mark.filterwarnings(
    "ignore:Passing a BlockManager to DataFrame:DeprecationWarning"
)


@pytest.fixture(params=["python", "python-fwf"], ids=lambda val: val)
def python_engine(request):
    return request.param


class TestUnsupportedFeatures:
    def test_mangle_dupe_cols_false(self):
        # see gh-12935
        data = "a b c\n1 2 3"

        for engine in ("c", "python"):
            with pytest.raises(TypeError, match="unexpected keyword"):
                read_csv(StringIO(data), engine=engine, mangle_dupe_cols=True)

    def test_c_engine(self):
        # see gh-6607
        data = "a b c\n1 2 3"
        msg = "does not support"

        depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"

        # specify C engine with unsupported options (raise)
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(FutureWarning, match=depr_msg):
                read_csv(StringIO(data), engine="c", sep=None, delim_whitespace=False)
        with pytest.raises(ValueError, match=msg):
            read_csv(StringIO(data), engine="c", sep=r"\s")
        with pytest.raises(ValueError, match=msg):
            read_csv(StringIO(data), engine="c", sep="\t", quotechar=chr(128))
        with pytest.raises(ValueError, match=msg):
            read_csv(StringIO(data), engine="c", skipfooter=1)

        # specify C-unsupported options without python-unsupported options
        with tm.assert_produces_warning((parsers.ParserWarning, FutureWarning)):
            read_csv(StringIO(data), sep=None, delim_whitespace=False)
        with tm.assert_produces_warning(parsers.ParserWarning):
            read_csv(StringIO(data), sep=r"\s")
        with tm.assert_produces_warning(parsers.ParserWarning):
            read_csv(StringIO(data), sep="\t", quotechar=chr(128))
        with tm.assert_produces_warning(parsers.ParserWarning):
            read_csv(StringIO(data), skipfooter=1)

        text = """                      A       B       C       D        E
one two three   four
a   b   10.0032 5    -0.5109 -2.3358 -0.4645  0.05076  0.3640
a   q   20      4     0.4473  1.4152  0.2834  1.00661  0.1744
x   q   30      3    -0.6662 -0.5243 -0.3580  0.89145  2.5838"""
        msg = "Error tokenizing data"

        with pytest.raises(ParserError, match=msg):
            read_csv(StringIO(text), sep="\\s+")
        with pytest.raises(ParserError, match=msg):
            read_csv(StringIO(text), engine="c", sep="\\s+")

        msg = "Only length-1 thousands markers supported"
        data = """A|B|C
1|2,334|5
10|13|10.
"""
        with pytest.raises(ValueError, match=msg):
            read_csv(StringIO(data), thousands=",,")
        with pytest.raises(ValueError, match=msg):
            read_csv(StringIO(data), thousands="")

        msg = "Only length-1 line terminators supported"
        data = "a,b,c~~1,2,3~~4,5,6"
        with pytest.raises(ValueError, match=msg):
            read_csv(StringIO(data), lineterminator="~~")

    def test_python_engine(self, python_engine):
        from pandas.io.parsers.readers import _python_unsupported as py_unsupported

        data = """1,2,3,,
1,2,3,4,
1,2,3,4,5
1,2,,,
1,2,3,4,"""

        for default in py_unsupported:
            msg = (
                f"The {repr(default)} option is not "
                f"supported with the {repr(python_engine)} engine"
            )

            kwargs = {default: object()}
            with pytest.raises(ValueError, match=msg):
                read_csv(StringIO(data), engine=python_engine, **kwargs)

    def test_python_engine_file_no_iter(self, python_engine):
        # see gh-16530
        class NoNextBuffer:
            def __init__(self, csv_data) -> None:
                self.data = csv_data

            def __next__(self):
                return self.data.__next__()

            def read(self):
                return self.data

            def readline(self):
                return self.data

        data = "a\n1"
        msg = "'NoNextBuffer' object is not iterable|argument 1 must be an iterator"

        with pytest.raises(TypeError, match=msg):
            read_csv(NoNextBuffer(data), engine=python_engine)

    def test_pyarrow_engine(self):
        from pandas.io.parsers.readers import _pyarrow_unsupported as pa_unsupported

        data = """1,2,3,,
        1,2,3,4,
        1,2,3,4,5
        1,2,,,
        1,2,3,4,"""

        for default in pa_unsupported:
            msg = (
                f"The {repr(default)} option is not "
                f"supported with the 'pyarrow' engine"
            )
            kwargs = {default: object()}
            default_needs_bool = {"warn_bad_lines", "error_bad_lines"}
            if default == "dialect":
                kwargs[default] = "excel"  # test a random dialect
            elif default in default_needs_bool:
                kwargs[default] = True
            elif default == "on_bad_lines":
                kwargs[default] = "warn"

            warn = None
            depr_msg = None
            if "delim_whitespace" in kwargs:
                depr_msg = "The 'delim_whitespace' keyword in pd.read_csv is deprecated"
                warn = FutureWarning
            if "verbose" in kwargs:
                depr_msg = "The 'verbose' keyword in pd.read_csv is deprecated"
                warn = FutureWarning

            with pytest.raises(ValueError, match=msg):
                with tm.assert_produces_warning(warn, match=depr_msg):
                    read_csv(StringIO(data), engine="pyarrow", **kwargs)

    def test_on_bad_lines_callable_python_or_pyarrow(self, all_parsers):
        # GH 5686
        # GH 54643
        sio = StringIO("a,b\n1,2")
        bad_lines_func = lambda x: x
        parser = all_parsers
        if all_parsers.engine not in ["python", "pyarrow"]:
            msg = (
                "on_bad_line can only be a callable "
                "function if engine='python' or 'pyarrow'"
            )
            with pytest.raises(ValueError, match=msg):
                parser.read_csv(sio, on_bad_lines=bad_lines_func)
        else:
            parser.read_csv(sio, on_bad_lines=bad_lines_func)


def test_close_file_handle_on_invalid_usecols(all_parsers):
    # GH 45384
    parser = all_parsers

    error = ValueError
    if parser.engine == "pyarrow":
        # Raises pyarrow.lib.ArrowKeyError
        pytest.skip(reason="https://github.com/apache/arrow/issues/38676")

    with tm.ensure_clean("test.csv") as fname:
        Path(fname).write_text("col1,col2\na,b\n1,2", encoding="utf-8")
        with tm.assert_produces_warning(False):
            with pytest.raises(error, match="col3"):
                parser.read_csv(fname, usecols=["col1", "col2", "col3"])
        # unlink fails on windows if file handles still point to it
        os.unlink(fname)


def test_invalid_file_inputs(request, all_parsers):
    # GH#45957
    parser = all_parsers
    if parser.engine == "python":
        request.applymarker(
            pytest.mark.xfail(reason=f"{parser.engine} engine supports lists.")
        )

    with pytest.raises(ValueError, match="Invalid"):
        parser.read_csv([])


def test_invalid_dtype_backend(all_parsers):
    parser = all_parsers
    msg = (
        "dtype_backend numpy is invalid, only 'numpy_nullable' and "
        "'pyarrow' are allowed."
    )
    with pytest.raises(ValueError, match=msg):
        parser.read_csv("test", dtype_backend="numpy")
