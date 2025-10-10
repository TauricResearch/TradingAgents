import pytest

import pandas._testing as tm


class TestCategoricalWarnings:
    def test_tab_complete_warning(self, ip):
        # https://github.com/pandas-dev/pandas/issues/16409
        pytest.importorskip("IPython", minversion="6.0.0")
        from IPython.core.completer import provisionalcompleter

        code = "import pandas as pd; c = pd.Categorical([])"
        ip.run_cell(code)

        # GH 31324 newer jedi version raises Deprecation warning;
        #  appears resolved 2021-02-02
        with tm.assert_produces_warning(None, raise_on_extra_warnings=False):
            with provisionalcompleter("ignore"):
                list(ip.Completer.completions("c.", 1))
