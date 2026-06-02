"""Rate-aware retry helpers used by web.server.runner.

Pure functions, no I/O, no module state. Kept separate from the runner
so detection/parsing can be unit-tested without spinning up the queue
worker and so new providers can be supported by editing this file
alone.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


# Substrings (case-insensitive) that identify a rate-limit exception class.
# Order doesn't matter — first match wins.
_RATE_LIMIT_CLASS_NAMES = (
    "ratelimiterror",
    "resourceexhausted",
    "quotaexceeded",
    "quotafailure",
    "toomanyrequests",
    "throttlingerror",
)

# Regex patterns matched against str(exc), in priority order.
# Patterns that need a qualifier word (e.g. 503 alone is too generic) include it
# inside the same regex.
_RATE_LIMIT_STRING_PATTERNS = (
    r"\b429\b",
    r"\bRESOURCE_EXHAUSTED\b",
    r'"code"\s*:\s*429',
    r'"type"\s*:\s*["\']rate_limit["\']',
    r"\b503\b.*\b(throttle|quota|rate[\s-]?limit)\b",
    r"\bquota[_ ]?exceeded\b",
)


def detect_rate_limit(exc: BaseException) -> bool:
    """True if exc looks like a 429 / quota error from any supported provider.

    Detection layers, cheapest first:
      1. Exception class name contains a known substring.
      2. str(exc) matches one of the known rate-limit regex patterns.
    """
    cls_name = type(exc).__name__.lower()
    for needle in _RATE_LIMIT_CLASS_NAMES:
        if needle in cls_name:
            return True
    msg = str(exc)
    for pattern in _RATE_LIMIT_STRING_PATTERNS:
        if re.search(pattern, msg, re.IGNORECASE):
            return True
    return False
