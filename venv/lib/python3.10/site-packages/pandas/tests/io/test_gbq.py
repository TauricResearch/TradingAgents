import pandas as pd
import pandas._testing as tm


def test_read_gbq_deprecated():
    with tm.assert_produces_warning(FutureWarning):
        with tm.external_error_raised(Exception):
            pd.read_gbq("fake")


def test_to_gbq_deprecated():
    with tm.assert_produces_warning(FutureWarning):
        with tm.external_error_raised(Exception):
            pd.DataFrame(range(1)).to_gbq("fake")
