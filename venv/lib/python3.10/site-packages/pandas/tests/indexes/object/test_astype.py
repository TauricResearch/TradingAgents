import pytest

from pandas import (
    Index,
    NaT,
)


def test_astype_invalid_nas_to_tdt64_raises():
    # GH#45722 don't cast np.datetime64 NaTs to timedelta64 NaT
    idx = Index([NaT.asm8] * 2, dtype=object)

    msg = r"Invalid type for timedelta scalar: <class 'numpy.datetime64'>"
    with pytest.raises(TypeError, match=msg):
        idx.astype("m8[ns]")
