# NB: This is for the Timestamp.timestamp *method* specifically, not
# the Timestamp class in general.

from pytz import utc

from pandas._libs.tslibs import Timestamp
import pandas.util._test_decorators as td

import pandas._testing as tm


class TestTimestampMethod:
    @td.skip_if_windows
    def test_timestamp(self, fixed_now_ts):
        # GH#17329
        # tz-naive --> treat it as if it were UTC for purposes of timestamp()
        ts = fixed_now_ts
        uts = ts.replace(tzinfo=utc)
        assert ts.timestamp() == uts.timestamp()

        tsc = Timestamp("2014-10-11 11:00:01.12345678", tz="US/Central")
        utsc = tsc.tz_convert("UTC")

        # utsc is a different representation of the same time
        assert tsc.timestamp() == utsc.timestamp()

        # datetime.timestamp() converts in the local timezone
        with tm.set_timezone("UTC"):
            # should agree with datetime.timestamp method
            dt = ts.to_pydatetime()
            assert dt.timestamp() == ts.timestamp()
