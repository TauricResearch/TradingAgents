"""
Behavioral based tests for offsets and date_range.

This file is adapted from https://github.com/pandas-dev/pandas/pull/18761 -
which was more ambitious but less idiomatic in its use of Hypothesis.

You may wish to consult the previous version for inspiration on further
tests, or when trying to pin down the bugs exposed by the tests below.
"""
from hypothesis import (
    assume,
    given,
)
import pytest
import pytz

import pandas as pd
from pandas._testing._hypothesis import (
    DATETIME_JAN_1_1900_OPTIONAL_TZ,
    YQM_OFFSET,
)

# ----------------------------------------------------------------
# Offset-specific behaviour tests


@pytest.mark.arm_slow
@given(DATETIME_JAN_1_1900_OPTIONAL_TZ, YQM_OFFSET)
def test_on_offset_implementations(dt, offset):
    assume(not offset.normalize)
    # check that the class-specific implementations of is_on_offset match
    # the general case definition:
    #   (dt + offset) - offset == dt
    try:
        compare = (dt + offset) - offset
    except (pytz.NonExistentTimeError, pytz.AmbiguousTimeError):
        # When dt + offset does not exist or is DST-ambiguous, assume(False) to
        # indicate to hypothesis that this is not a valid test case
        # DST-ambiguous example (GH41906):
        # dt = datetime.datetime(1900, 1, 1, tzinfo=pytz.timezone('Africa/Kinshasa'))
        # offset = MonthBegin(66)
        assume(False)

    assert offset.is_on_offset(dt) == (compare == dt)


@given(YQM_OFFSET)
def test_shift_across_dst(offset):
    # GH#18319 check that 1) timezone is correctly normalized and
    # 2) that hour is not incorrectly changed by this normalization
    assume(not offset.normalize)

    # Note that dti includes a transition across DST boundary
    dti = pd.date_range(
        start="2017-10-30 12:00:00", end="2017-11-06", freq="D", tz="US/Eastern"
    )
    assert (dti.hour == 12).all()  # we haven't screwed up yet

    res = dti + offset
    assert (res.hour == 12).all()
