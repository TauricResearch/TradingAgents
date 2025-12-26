#!/usr/bin/env python3
"""
Error Analyzer Library - Analyze captured tool errors for GitHub issue creation.

Reads error registry from .claude/logs/errors/, classifies errors using
failure_classifier.py, deduplicates via fingerprinting, and returns
structured reports for actionable errors.

Key Features:
1. Error registry reading from JSONL files
2. Integration with failure_classifier.py for transient/permanent classification
3. Error fingerprinting for deduplication
4. Filtering for actionable errors (permanent only, not transient)
5. Structured error reports for issue creation

Security:
- CWE-117: Log injection prevention via existing sanitization
- CWE-532: Secret redaction for API keys, tokens
- CWE-22: Path validation via validation.py
- CWE-400: Resource limits (max errors per session)

Date: 2025-12-13
Issue: #124 (Automated error capture and analysis)
Agent: implementer

See error-handling-patterns skill for exception hierarchy and error handling best practices.

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import security utilities
try:
    from .security_utils import audit_log
except ImportError:
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from security_utils import audit_log

# Import failure classifier
try:
    from .failure_classifier import (
        classify_failure,
        FailureType,
        sanitize_error_message,
    )
except ImportError:
    from failure_classifier import (
        classify_failure,
        FailureType,
        sanitize_error_message,
    )

# Import path utilities
try:
    from .path_utils import get_project_root
except ImportError:
    from path_utils import get_project_root


# =============================================================================
# Constants
# =============================================================================

# Maximum errors to process per session (CWE-400 resource limit)
MAX_ERRORS_PER_SESSION = 500

# Maximum error message length (prevent memory exhaustion)
MAX_ERROR_MESSAGE_LENGTH = 1000

# Secret patterns for redaction (CWE-532)
SECRET_PATTERNS = [
    r"sk-[a-zA-Z0-9]{20,}",  # OpenAI API key
    r"anthropic_[a-zA-Z0-9_-]{20,}",  # Anthropic API key
    r"ghp_[a-zA-Z0-9]{20,}",  # GitHub PAT
    r"gho_[a-zA-Z0-9]{20,}",  # GitHub OAuth token
    r"ghr_[a-zA-Z0-9]{20,}",  # GitHub refresh token
    r"Bearer\s+[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",  # JWT
    r"api[_-]?key[\"']?\s*[=:]\s*[\"']?[a-zA-Z0-9_-]{16,}",  # Generic API key
    r"password[\"']?\s*[=:]\s*[\"']?[^\s\"']+",  # Password assignments
    r"secret[\"']?\s*[=:]\s*[\"']?[a-zA-Z0-9_-]{16,}",  # Generic secret
]


# =============================================================================
# Data Classes
# =============================================================================

class ErrorEntry:
    """Represents a single captured error."""

    def __init__(
        self,
        timestamp: str,
        tool_name: str,
        exit_code: Optional[int],
        error_message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.timestamp = timestamp
        self.tool_name = tool_name
        self.exit_code = exit_code
        self.error_message = error_message
        self.context = context or {}
        self.failure_type: Optional[FailureType] = None
        self.fingerprint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
            "context": self.context,
            "failure_type": self.failure_type.value if self.failure_type else None,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorEntry":
        """Create from dictionary."""
        entry = cls(
            timestamp=data.get("timestamp", ""),
            tool_name=data.get("tool_name", "unknown"),
            exit_code=data.get("exit_code"),
            error_message=data.get("error_message", ""),
            context=data.get("context", {}),
        )
        if data.get("failure_type"):
            entry.failure_type = FailureType(data["failure_type"])
        entry.fingerprint = data.get("fingerprint")
        return entry


class ErrorReport:
    """Structured report of analyzed errors for issue creation."""

    def __init__(
        self,
        actionable_errors: List[ErrorEntry],
        transient_errors: List[ErrorEntry],
        duplicate_fingerprints: List[str],
        total_errors: int,
        session_date: str,
    ):
        self.actionable_errors = actionable_errors
        self.transient_errors = transient_errors
        self.duplicate_fingerprints = duplicate_fingerprints
        self.total_errors = total_errors
        self.session_date = session_date

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "actionable_errors": [e.to_dict() for e in self.actionable_errors],
            "transient_errors": [e.to_dict() for e in self.transient_errors],
            "duplicate_fingerprints": self.duplicate_fingerprints,
            "total_errors": self.total_errors,
            "session_date": self.session_date,
            "actionable_count": len(self.actionable_errors),
            "transient_count": len(self.transient_errors),
        }


# =============================================================================
# Error Analyzer
# =============================================================================

class ErrorAnalyzer:
    """Analyzes captured errors for GitHub issue creation."""

    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize error analyzer.

        Args:
            project_root: Project root directory (auto-detected if not provided)
        """
        if project_root is None:
            project_root = get_project_root()
        self.project_root = Path(project_root)
        self.errors_dir = self.project_root / ".claude" / "logs" / "errors"
        self._seen_fingerprints: set = set()

    def read_error_registry(self, date: Optional[str] = None) -> List[ErrorEntry]:
        """
        Read errors from registry for a specific date.

        Args:
            date: Date string (YYYY-MM-DD). If None, uses today.

        Returns:
            List of ErrorEntry objects
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        error_file = self.errors_dir / f"{date}.jsonl"

        if not error_file.exists():
            return []

        errors = []
        try:
            with open(error_file, "r") as f:
                for i, line in enumerate(f):
                    if i >= MAX_ERRORS_PER_SESSION:
                        audit_log(
                            "error_analyzer_limit_reached",
                            "warning",
                            {"max": MAX_ERRORS_PER_SESSION, "file": str(error_file)},
                        )
                        break

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        errors.append(ErrorEntry.from_dict(data))
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines

        except (OSError, IOError) as e:
            audit_log(
                "error_analyzer_read_failed",
                "failure",
                {"file": str(error_file), "error": str(e)},
            )

        return errors

    def classify_errors(self, errors: List[ErrorEntry]) -> List[ErrorEntry]:
        """
        Classify errors as transient or permanent.

        Args:
            errors: List of errors to classify

        Returns:
            Same list with failure_type populated
        """
        for error in errors:
            error.failure_type = classify_failure(error.error_message)
        return errors

    def create_fingerprint(self, error: ErrorEntry) -> str:
        """
        Create unique fingerprint for error deduplication.

        Fingerprint = hash(tool_name + error_type + normalized_message)

        Args:
            error: Error to fingerprint

        Returns:
            SHA-256 fingerprint (first 16 chars)
        """
        # Normalize message: lowercase, remove numbers, collapse whitespace
        normalized = error.error_message.lower()
        normalized = re.sub(r"\d+", "N", normalized)  # Replace numbers
        normalized = re.sub(r"\s+", " ", normalized)  # Collapse whitespace
        normalized = normalized[:200]  # Cap length for hashing

        # Build fingerprint input
        fingerprint_input = f"{error.tool_name}:{error.failure_type.value if error.failure_type else 'unknown'}:{normalized}"

        # Hash and truncate
        hash_obj = hashlib.sha256(fingerprint_input.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def deduplicate_errors(self, errors: List[ErrorEntry]) -> Tuple[List[ErrorEntry], List[str]]:
        """
        Remove duplicate errors based on fingerprints.

        Args:
            errors: List of errors to deduplicate

        Returns:
            Tuple of (unique errors, duplicate fingerprints)
        """
        unique = []
        duplicates = []

        for error in errors:
            fingerprint = self.create_fingerprint(error)
            error.fingerprint = fingerprint

            if fingerprint in self._seen_fingerprints:
                duplicates.append(fingerprint)
            else:
                self._seen_fingerprints.add(fingerprint)
                unique.append(error)

        return unique, duplicates

    def filter_actionable(self, errors: List[ErrorEntry]) -> Tuple[List[ErrorEntry], List[ErrorEntry]]:
        """
        Filter for actionable errors (permanent only).

        Args:
            errors: List of classified errors

        Returns:
            Tuple of (actionable errors, transient errors)
        """
        actionable = []
        transient = []

        for error in errors:
            if error.failure_type == FailureType.PERMANENT:
                actionable.append(error)
            else:
                transient.append(error)

        return actionable, transient

    def analyze(self, date: Optional[str] = None) -> ErrorReport:
        """
        Full analysis pipeline: read, classify, deduplicate, filter.

        Args:
            date: Date to analyze (default: today)

        Returns:
            ErrorReport with actionable and transient errors
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        # Reset fingerprints for new analysis
        self._seen_fingerprints.clear()

        # Pipeline
        errors = self.read_error_registry(date)
        errors = self.classify_errors(errors)
        errors, duplicates = self.deduplicate_errors(errors)
        actionable, transient = self.filter_actionable(errors)

        audit_log(
            "error_analysis_complete",
            "success",
            {
                "date": date,
                "total": len(errors) + len(duplicates),
                "actionable": len(actionable),
                "transient": len(transient),
                "duplicates": len(duplicates),
            },
        )

        return ErrorReport(
            actionable_errors=actionable,
            transient_errors=transient,
            duplicate_fingerprints=duplicates,
            total_errors=len(errors) + len(duplicates),
            session_date=date,
        )


# =============================================================================
# Utility Functions
# =============================================================================

def redact_secrets(message: str) -> str:
    """
    Redact API keys, tokens, and secrets from error messages.

    Args:
        message: Error message that may contain secrets

    Returns:
        Message with secrets redacted
    """
    redacted = message
    for pattern in SECRET_PATTERNS:
        redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


def format_error_for_issue(error: ErrorEntry) -> str:
    """
    Format error for GitHub issue body.

    Args:
        error: Error to format

    Returns:
        Markdown-formatted error description
    """
    lines = [
        f"### Error Details",
        f"",
        f"**Tool**: {error.tool_name}",
        f"**Exit Code**: {error.exit_code if error.exit_code is not None else 'N/A'}",
        f"**Type**: {error.failure_type.value if error.failure_type else 'unknown'}",
        f"**Fingerprint**: `{error.fingerprint}`",
        f"**Timestamp**: {error.timestamp}",
        f"",
        f"### Error Message",
        f"```",
        redact_secrets(error.error_message[:MAX_ERROR_MESSAGE_LENGTH]),
        f"```",
    ]

    if error.context:
        lines.extend([
            f"",
            f"### Context",
            f"```json",
            json.dumps(error.context, indent=2)[:500],
            f"```",
        ])

    return "\n".join(lines)


def write_error_to_registry(
    tool_name: str,
    exit_code: Optional[int],
    error_message: str,
    context: Optional[Dict[str, Any]] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """
    Write an error to the registry (JSONL format).

    Args:
        tool_name: Name of the tool that failed
        exit_code: Exit code (None if not applicable)
        error_message: Error message
        context: Additional context
        project_root: Project root (auto-detected if not provided)

    Returns:
        True if written successfully, False otherwise
    """
    if project_root is None:
        project_root = get_project_root()

    errors_dir = Path(project_root) / ".claude" / "logs" / "errors"
    errors_dir.mkdir(parents=True, exist_ok=True)

    date = datetime.now().strftime("%Y-%m-%d")
    error_file = errors_dir / f"{date}.jsonl"

    # Sanitize and truncate message
    safe_message = sanitize_error_message(error_message)
    safe_message = redact_secrets(safe_message)
    if len(safe_message) > MAX_ERROR_MESSAGE_LENGTH:
        safe_message = safe_message[:MAX_ERROR_MESSAGE_LENGTH] + "...[truncated]"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool_name": tool_name,
        "exit_code": exit_code,
        "error_message": safe_message,
        "context": context or {},
    }

    try:
        with open(error_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        audit_log(
            "error_written_to_registry",
            "success",
            {"tool": tool_name, "file": str(error_file)},
        )
        return True

    except (OSError, IOError) as e:
        audit_log(
            "error_write_failed",
            "failure",
            {"tool": tool_name, "error": str(e)},
        )
        return False


# =============================================================================
# Module-level convenience functions
# =============================================================================

def analyze_errors(date: Optional[str] = None, project_root: Optional[Path] = None) -> ErrorReport:
    """
    Convenience function to analyze errors for a date.

    Args:
        date: Date to analyze (default: today)
        project_root: Project root (auto-detected if not provided)

    Returns:
        ErrorReport with analysis results
    """
    analyzer = ErrorAnalyzer(project_root)
    return analyzer.analyze(date)


def get_actionable_errors(date: Optional[str] = None, project_root: Optional[Path] = None) -> List[ErrorEntry]:
    """
    Get only actionable (permanent) errors for a date.

    Args:
        date: Date to analyze (default: today)
        project_root: Project root (auto-detected if not provided)

    Returns:
        List of actionable ErrorEntry objects
    """
    report = analyze_errors(date, project_root)
    return report.actionable_errors
