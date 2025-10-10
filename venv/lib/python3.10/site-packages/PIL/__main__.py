from __future__ import annotations

import sys

from .features import pilinfo

pilinfo(supported_formats="--report" not in sys.argv)
