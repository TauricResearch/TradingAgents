from textwrap import dedent

import numpy as np
import pytest

from pandas.errors import (
    PyperclipException,
    PyperclipWindowsException,
)

import pandas as pd
from pandas import (
    NA,
    DataFrame,
    Series,
    get_option,
    read_clipboard,
)
import pandas._testing as tm

from pandas.io.clipboard import (
    CheckedCall,
    _stringifyText,
    init_qt_clipboard,
)


def build_kwargs(sep, excel):
    kwargs = {}
    if excel != "default":
        kwargs["excel"] = excel
    if sep != "default":
        kwargs["sep"] = sep
    return kwargs


@pytest.fixture(
    params=[
        "delims",
        "utf8",
        "utf16",
        "string",
        "long",
        "nonascii",
        "colwidth",
        "mixed",
        "float",
        "int",
    ]
)
def df(request):
    data_type = request.param

    if data_type == "delims":
        return DataFrame({"a": ['"a,\t"b|c', "d\tef`"], "b": ["hi'j", "k''lm"]})
    elif data_type == "utf8":
        return DataFrame({"a": ["µasd", "Ωœ∑`"], "b": ["øπ∆˚¬", "œ∑`®"]})
    elif data_type == "utf16":
        return DataFrame(
            {"a": ["\U0001f44d\U0001f44d", "\U0001f44d\U0001f44d"], "b": ["abc", "def"]}
        )
    elif data_type == "string":
        return DataFrame(
            np.array([f"i-{i}" for i in range(15)]).reshape(5, 3), columns=list("abc")
        )
    elif data_type == "long":
        max_rows = get_option("display.max_rows")
        return DataFrame(
            np.random.default_rng(2).integers(0, 10, size=(max_rows + 1, 3)),
            columns=list("abc"),
        )
    elif data_type == "nonascii":
        return DataFrame({"en": "in English".split(), "es": "en español".split()})
    elif data_type == "colwidth":
        _cw = get_option("display.max_colwidth") + 1
        return DataFrame(
            np.array(["x" * _cw for _ in range(15)]).reshape(5, 3), columns=list("abc")
        )
    elif data_type == "mixed":
        return DataFrame(
            {
                "a": np.arange(1.0, 6.0) + 0.01,
                "b": np.arange(1, 6).astype(np.int64),
                "c": list("abcde"),
            }
        )
    elif data_type == "float":
        return DataFrame(np.random.default_rng(2).random((5, 3)), columns=list("abc"))
    elif data_type == "int":
        return DataFrame(
            np.random.default_rng(2).integers(0, 10, (5, 3)), columns=list("abc")
        )
    else:
        raise ValueError


@pytest.fixture
def mock_ctypes(monkeypatch):
    """
    Mocks WinError to help with testing the clipboard.
    """

    def _mock_win_error():
        return "Window Error"

    # Set raising to False because WinError won't exist on non-windows platforms
    with monkeypatch.context() as m:
        m.setattr("ctypes.WinError", _mock_win_error, raising=False)
        yield


@pytest.mark.usefixtures("mock_ctypes")
def test_checked_call_with_bad_call(monkeypatch):
    """
    Give CheckCall a function that returns a falsey value and
    mock get_errno so it returns false so an exception is raised.
    """

    def _return_false():
        return False

    monkeypatch.setattr("pandas.io.clipboard.get_errno", lambda: True)
    msg = f"Error calling {_return_false.__name__} \\(Window Error\\)"

    with pytest.raises(PyperclipWindowsException, match=msg):
        CheckedCall(_return_false)()


@pytest.mark.usefixtures("mock_ctypes")
def test_checked_call_with_valid_call(monkeypatch):
    """
    Give CheckCall a function that returns a truthy value and
    mock get_errno so it returns true so an exception is not raised.
    The function should return the results from _return_true.
    """

    def _return_true():
        return True

    monkeypatch.setattr("pandas.io.clipboard.get_errno", lambda: False)

    # Give CheckedCall a callable that returns a truthy value s
    checked_call = CheckedCall(_return_true)
    assert checked_call() is True


@pytest.mark.parametrize(
    "text",
    [
        "String_test",
        True,
        1,
        1.0,
        1j,
    ],
)
def test_stringify_text(text):
    valid_types = (str, int, float, bool)

    if isinstance(text, valid_types):
        result = _stringifyText(text)
        assert result == str(text)
    else:
        msg = (
            "only str, int, float, and bool values "
            f"can be copied to the clipboard, not {type(text).__name__}"
        )
        with pytest.raises(PyperclipException, match=msg):
            _stringifyText(text)


@pytest.fixture
def set_pyqt_clipboard(monkeypatch):
    qt_cut, qt_paste = init_qt_clipboard()
    with monkeypatch.context() as m:
        m.setattr(pd.io.clipboard, "clipboard_set", qt_cut)
        m.setattr(pd.io.clipboard, "clipboard_get", qt_paste)
        yield


@pytest.fixture
def clipboard(qapp):
    clip = qapp.clipboard()
    yield clip
    clip.clear()


@pytest.mark.single_cpu
@pytest.mark.clipboard
@pytest.mark.usefixtures("set_pyqt_clipboard")
@pytest.mark.usefixtures("clipboard")
class TestClipboard:
    # Test that default arguments copy as tab delimited
    # Test that explicit delimiters are respected
    @pytest.mark.parametrize("sep", [None, "\t", ",", "|"])
    @pytest.mark.parametrize("encoding", [None, "UTF-8", "utf-8", "utf8"])
    def test_round_trip_frame_sep(self, df, sep, encoding):
        df.to_clipboard(excel=None, sep=sep, encoding=encoding)
        result = read_clipboard(sep=sep or "\t", index_col=0, encoding=encoding)
        tm.assert_frame_equal(df, result)

    # Test white space separator
    def test_round_trip_frame_string(self, df):
        df.to_clipboard(excel=False, sep=None)
        result = read_clipboard()
        assert df.to_string() == result.to_string()
        assert df.shape == result.shape

    # Two character separator is not supported in to_clipboard
    # Test that multi-character separators are not silently passed
    def test_excel_sep_warning(self, df):
        with tm.assert_produces_warning(
            UserWarning,
            match="to_clipboard in excel mode requires a single character separator.",
            check_stacklevel=False,
        ):
            df.to_clipboard(excel=True, sep=r"\t")

    # Separator is ignored when excel=False and should produce a warning
    def test_copy_delim_warning(self, df):
        with tm.assert_produces_warning():
            df.to_clipboard(excel=False, sep="\t")

    # Tests that the default behavior of to_clipboard is tab
    # delimited and excel="True"
    @pytest.mark.parametrize("sep", ["\t", None, "default"])
    @pytest.mark.parametrize("excel", [True, None, "default"])
    def test_clipboard_copy_tabs_default(self, sep, excel, df, clipboard):
        kwargs = build_kwargs(sep, excel)
        df.to_clipboard(**kwargs)
        assert clipboard.text() == df.to_csv(sep="\t")

    # Tests reading of white space separated tables
    @pytest.mark.parametrize("sep", [None, "default"])
    def test_clipboard_copy_strings(self, sep, df):
        kwargs = build_kwargs(sep, False)
        df.to_clipboard(**kwargs)
        result = read_clipboard(sep=r"\s+")
        assert result.to_string() == df.to_string()
        assert df.shape == result.shape

    def test_read_clipboard_infer_excel(self, clipboard):
        # gh-19010: avoid warnings
        clip_kwargs = {"engine": "python"}

        text = dedent(
            """
            John James\tCharlie Mingus
            1\t2
            4\tHarry Carney
            """.strip()
        )
        clipboard.setText(text)
        df = read_clipboard(**clip_kwargs)

        # excel data is parsed correctly
        assert df.iloc[1, 1] == "Harry Carney"

        # having diff tab counts doesn't trigger it
        text = dedent(
            """
            a\t b
            1  2
            3  4
            """.strip()
        )
        clipboard.setText(text)
        res = read_clipboard(**clip_kwargs)

        text = dedent(
            """
            a  b
            1  2
            3  4
            """.strip()
        )
        clipboard.setText(text)
        exp = read_clipboard(**clip_kwargs)

        tm.assert_frame_equal(res, exp)

    def test_infer_excel_with_nulls(self, clipboard):
        # GH41108
        text = "col1\tcol2\n1\tred\n\tblue\n2\tgreen"

        clipboard.setText(text)
        df = read_clipboard()
        df_expected = DataFrame(
            data={"col1": [1, None, 2], "col2": ["red", "blue", "green"]}
        )

        # excel data is parsed correctly
        tm.assert_frame_equal(df, df_expected)

    @pytest.mark.parametrize(
        "multiindex",
        [
            (  # Can't use `dedent` here as it will remove the leading `\t`
                "\n".join(
                    [
                        "\t\t\tcol1\tcol2",
                        "A\t0\tTrue\t1\tred",
                        "A\t1\tTrue\t\tblue",
                        "B\t0\tFalse\t2\tgreen",
                    ]
                ),
                [["A", "A", "B"], [0, 1, 0], [True, True, False]],
            ),
            (
                "\n".join(
                    ["\t\tcol1\tcol2", "A\t0\t1\tred", "A\t1\t\tblue", "B\t0\t2\tgreen"]
                ),
                [["A", "A", "B"], [0, 1, 0]],
            ),
        ],
    )
    def test_infer_excel_with_multiindex(self, clipboard, multiindex):
        # GH41108

        clipboard.setText(multiindex[0])
        df = read_clipboard()
        df_expected = DataFrame(
            data={"col1": [1, None, 2], "col2": ["red", "blue", "green"]},
            index=multiindex[1],
        )

        # excel data is parsed correctly
        tm.assert_frame_equal(df, df_expected)

    def test_invalid_encoding(self, df):
        msg = "clipboard only supports utf-8 encoding"
        # test case for testing invalid encoding
        with pytest.raises(ValueError, match=msg):
            df.to_clipboard(encoding="ascii")
        with pytest.raises(NotImplementedError, match=msg):
            read_clipboard(encoding="ascii")

    @pytest.mark.parametrize("data", ["\U0001f44d...", "Ωœ∑`...", "abcd..."])
    def test_raw_roundtrip(self, data):
        # PR #25040 wide unicode wasn't copied correctly on PY3 on windows
        df = DataFrame({"data": [data]})
        df.to_clipboard()
        result = read_clipboard()
        tm.assert_frame_equal(df, result)

    @pytest.mark.parametrize("engine", ["c", "python"])
    def test_read_clipboard_dtype_backend(
        self, clipboard, string_storage, dtype_backend, engine, using_infer_string
    ):
        # GH#50502
        if dtype_backend == "pyarrow":
            pa = pytest.importorskip("pyarrow")
            if engine == "c" and string_storage == "pyarrow":
                # TODO avoid this exception?
                string_dtype = pd.ArrowDtype(pa.large_string())
            else:
                string_dtype = pd.ArrowDtype(pa.string())
        else:
            string_dtype = pd.StringDtype(string_storage)

        text = """a,b,c,d,e,f,g,h,i
x,1,4.0,x,2,4.0,,True,False
y,2,5.0,,,,,False,"""
        clipboard.setText(text)

        with pd.option_context("mode.string_storage", string_storage):
            result = read_clipboard(sep=",", dtype_backend=dtype_backend, engine=engine)

        expected = DataFrame(
            {
                "a": Series(["x", "y"], dtype=string_dtype),
                "b": Series([1, 2], dtype="Int64"),
                "c": Series([4.0, 5.0], dtype="Float64"),
                "d": Series(["x", None], dtype=string_dtype),
                "e": Series([2, NA], dtype="Int64"),
                "f": Series([4.0, NA], dtype="Float64"),
                "g": Series([NA, NA], dtype="Int64"),
                "h": Series([True, False], dtype="boolean"),
                "i": Series([False, NA], dtype="boolean"),
            }
        )
        if dtype_backend == "pyarrow":
            from pandas.arrays import ArrowExtensionArray

            expected = DataFrame(
                {
                    col: ArrowExtensionArray(pa.array(expected[col], from_pandas=True))
                    for col in expected.columns
                }
            )
            expected["g"] = ArrowExtensionArray(pa.array([None, None]))

        if using_infer_string:
            expected.columns = expected.columns.astype(
                pd.StringDtype(string_storage, na_value=np.nan)
            )

        tm.assert_frame_equal(result, expected)

    def test_invalid_dtype_backend(self):
        msg = (
            "dtype_backend numpy is invalid, only 'numpy_nullable' and "
            "'pyarrow' are allowed."
        )
        with pytest.raises(ValueError, match=msg):
            read_clipboard(dtype_backend="numpy")

    def test_to_clipboard_pos_args_deprecation(self):
        # GH-54229
        df = DataFrame({"a": [1, 2, 3]})
        msg = (
            r"Starting with pandas version 3.0 all arguments of to_clipboard "
            r"will be keyword-only."
        )
        with tm.assert_produces_warning(FutureWarning, match=msg):
            df.to_clipboard(True, None)
