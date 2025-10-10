import pytest

from pandas.compat._optional import VERSIONS

import pandas as pd
from pandas.core.computation import expr
from pandas.core.computation.engines import ENGINES
from pandas.util.version import Version


def test_compat():
    # test we have compat with our version of numexpr

    from pandas.core.computation.check import NUMEXPR_INSTALLED

    ne = pytest.importorskip("numexpr")

    ver = ne.__version__
    if Version(ver) < Version(VERSIONS["numexpr"]):
        assert not NUMEXPR_INSTALLED
    else:
        assert NUMEXPR_INSTALLED


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("parser", expr.PARSERS)
def test_invalid_numexpr_version(engine, parser):
    if engine == "numexpr":
        pytest.importorskip("numexpr")
    a, b = 1, 2  # noqa: F841
    res = pd.eval("a + b", engine=engine, parser=parser)
    assert res == 3
