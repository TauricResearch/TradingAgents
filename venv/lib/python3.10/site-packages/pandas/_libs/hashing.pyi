import numpy as np

from pandas._typing import npt

def hash_object_array(
    arr: npt.NDArray[np.object_],
    key: str,
    encoding: str = ...,
) -> npt.NDArray[np.uint64]: ...
