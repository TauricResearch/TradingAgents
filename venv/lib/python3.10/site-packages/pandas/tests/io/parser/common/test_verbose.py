"""
Tests that work on both the Python and C engines but do not have a
specific classification into the other test modules.
"""
from io import StringIO

import pytest

import pandas._testing as tm

depr_msg = "The 'verbose' keyword in pd.read_csv is deprecated"


def test_verbose_read(all_parsers, capsys):
    parser = all_parsers
    data = """a,b,c,d
one,1,2,3
one,1,2,3
,1,2,3
one,1,2,3
,1,2,3
,1,2,3
one,1,2,3
two,1,2,3"""

    if parser.engine == "pyarrow":
        msg = "The 'verbose' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_csv(StringIO(data), verbose=True)
        return

    # Engines are verbose in different ways.
    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        parser.read_csv(StringIO(data), verbose=True)
    captured = capsys.readouterr()

    if parser.engine == "c":
        assert "Tokenization took:" in captured.out
        assert "Parser memory cleanup took:" in captured.out
    else:  # Python engine
        assert captured.out == "Filled 3 NA values in column a\n"


def test_verbose_read2(all_parsers, capsys):
    parser = all_parsers
    data = """a,b,c,d
one,1,2,3
two,1,2,3
three,1,2,3
four,1,2,3
five,1,2,3
,1,2,3
seven,1,2,3
eight,1,2,3"""

    if parser.engine == "pyarrow":
        msg = "The 'verbose' option is not supported with the 'pyarrow' engine"
        with pytest.raises(ValueError, match=msg):
            with tm.assert_produces_warning(
                FutureWarning, match=depr_msg, check_stacklevel=False
            ):
                parser.read_csv(StringIO(data), verbose=True, index_col=0)
        return

    with tm.assert_produces_warning(
        FutureWarning, match=depr_msg, check_stacklevel=False
    ):
        parser.read_csv(StringIO(data), verbose=True, index_col=0)
    captured = capsys.readouterr()

    # Engines are verbose in different ways.
    if parser.engine == "c":
        assert "Tokenization took:" in captured.out
        assert "Parser memory cleanup took:" in captured.out
    else:  # Python engine
        assert captured.out == "Filled 1 NA values in column a\n"
