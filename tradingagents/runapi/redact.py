"""Conservative redaction for secrets at output and diagnostic boundaries."""

from __future__ import annotations

import re

_PATTERNS = (
    re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)([\"']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)\b[\"']?\s*[:=]\s*[\"']?)[^\s,;\"']+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b"),
)


class Redactor:
    def scrub(self, value):
        if isinstance(value, str):
            text = value
            for pattern in _PATTERNS:
                if pattern.groups:
                    text = pattern.sub(lambda match: match.group(1) + "[REDACTED]", text)
                else:
                    text = pattern.sub("[REDACTED]", text)
            return text
        if isinstance(value, dict):
            safe = {}
            secret_key = re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization)")
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
