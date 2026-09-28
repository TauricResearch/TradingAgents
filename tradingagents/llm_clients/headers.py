"""Validation for HTTP headers supplied by configuration (never log values)."""

import json
import re
from collections.abc import Mapping

_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")


def parse_llm_headers(value) -> dict[str, str]:
    """Accept a string-to-string mapping or a JSON object from an env var.

    Empty/unset values mean no additional headers. Reject invalid wire values
    before any requests and avoid echoing potentially secret header contents.
    Header spelling is preserved; duplicate names are checked case-insensitively.
    """
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value, object_pairs_hook=_unique_object)
        except (ValueError, TypeError):
            raise ValueError("llm_headers must be a valid JSON object with unique header names") from None
    if not isinstance(value, Mapping):
        raise ValueError("llm_headers must be a mapping of header names to string values")
    result = {}
    seen = set()
    for name, content in value.items():
        if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
            raise ValueError("llm_headers contains an invalid HTTP header name")
        if name.lower() in seen:
            raise ValueError("llm_headers contains duplicate case-insensitive header names")
        if not isinstance(content, str) or any(
            ch != "\t" and not 32 <= ord(ch) <= 126 for ch in content
        ):
            raise ValueError("llm_headers values must be ASCII strings without control characters")
        seen.add(name.lower())
        result[name] = content
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
