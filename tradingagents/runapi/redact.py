"""Conservative redaction for secrets at output and diagnostic boundaries."""

from __future__ import annotations

import os
import re

_SECRET_KEY = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization)"
)
_LABEL = r"(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization)"
_PATTERNS = (
    re.compile(r"(?i)(\b(?:Bearer|Basic)\s+)[A-Za-z0-9._~+/=-]+"),
    # Consume an entire quoted value, including whitespace and line breaks.
    re.compile(r"(?i)([\"']?\b" + _LABEL + r"\b[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;\"']+)"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
)


class Redactor:
    def __init__(self):
        # Snapshot values without logging them; match longest first for overlaps.
        self._secrets = tuple(sorted({value for key, value in os.environ.items()
                                     if value and _SECRET_KEY.search(key)},
                                    key=len, reverse=True))

    def scrub(self, value):
        if isinstance(value, str):
            text = value
            for secret in self._secrets:
                text = text.replace(secret, "[REDACTED]")
            for pattern in _PATTERNS:
                if pattern.groups:
                    text = pattern.sub(lambda match: match.group(1) + "[REDACTED]", text)
                else:
                    text = pattern.sub("[REDACTED]", text)
            return text
        if isinstance(value, dict):
            safe = {}
            secret_key = _SECRET_KEY
            for key, item in value.items():
                key_text = str(key)
                safe_key = self.scrub(key_text)
                safe[safe_key] = "[REDACTED]" if secret_key.search(key_text) else self.scrub(item)
            return safe
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.scrub(item) for item in value)
        return value

    def diagnostic(self, exc: BaseException) -> str:
        return self.scrub(f"{type(exc).__name__}: {exc}")
