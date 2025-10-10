from __future__ import annotations

import numpy as np

# dtypes of arrays returned by ContourPy.
point_dtype = np.float64
code_dtype = np.uint8
offset_dtype = np.uint32

# Kind codes used in Matplotlib Paths.
MOVETO = 1
LINETO = 2
CLOSEPOLY = 79
