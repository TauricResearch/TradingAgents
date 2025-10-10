import numpy as np
import pytest
import pytz

from pandas._libs.tslibs.tzconversion import tz_localize_to_utc


class TestTZLocalizeToUTC:
    def test_tz_localize_to_utc_ambiguous_infer(self):
        # val is a timestamp that is ambiguous when localized to US/Eastern
        val = 1_320_541_200_000_000_000
        vals = np.array([val, val - 1, val], dtype=np.int64)

        with pytest.raises(pytz.AmbiguousTimeError, match="2011-11-06 01:00:00"):
            tz_localize_to_utc(vals, pytz.timezone("US/Eastern"), ambiguous="infer")

        with pytest.raises(pytz.AmbiguousTimeError, match="are no repeated times"):
            tz_localize_to_utc(vals[:1], pytz.timezone("US/Eastern"), ambiguous="infer")

        vals[1] += 1
        msg = "There are 2 dst switches when there should only be 1"
        with pytest.raises(pytz.AmbiguousTimeError, match=msg):
            tz_localize_to_utc(vals, pytz.timezone("US/Eastern"), ambiguous="infer")
