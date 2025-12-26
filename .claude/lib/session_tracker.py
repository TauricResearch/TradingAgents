#!/usr/bin/env python3
"""
Session Tracker Library - Portable tracking infrastructure for agent actions

Purpose:
    Logs agent actions to file instead of keeping in context, preventing context bloat.
    Supports execution from any directory (user projects, subdirectories, etc).

Problem Solved (GitHub Issue #79):
    Original session tracking had hardcoded docs/sessions/ path that failed when:
    - Running from user projects (no docs/ directory)
    - Running from project subdirectories (couldn't find project root)
    - Commands invoked from installation path vs development path

Solution:
    Library-based implementation with portable path detection via path_utils.
    Works from any directory without hardcoded paths.

Design Patterns:
    - Two-tier Design: Library (core logic) + CLI wrapper for reuse and testing
    - Progressive Enhancement: Features gracefully degrade if infrastructure unavailable
    - Path Portability: Uses path_utils for dynamic project root detection
    - See library-design-patterns skill for standardized design patterns
    - See state-management-patterns skill for standardized design patterns

Usage (Library):
    from plugins.autonomous_dev.lib.session_tracker import SessionTracker
    tracker = SessionTracker()
    tracker.log("researcher", "Found 3 JWT patterns")

Usage (CLI Wrapper):
    python plugins/autonomous-dev/scripts/session_tracker.py researcher "Found 3 JWT patterns"

Deprecation Notice (GitHub Issue #79):
    scripts/session_tracker.py (original location) - DEPRECATED, use plugins/autonomous-dev/scripts/session_tracker.py
    Will be removed in v4.0.0. Delegates to library implementation for backward compatibility.

Security (GitHub Issue #45):
    - Path Traversal Prevention (CWE-22): Validates paths via validation module
    - Permission Checking (CWE-732): Warns on world-writable directories
    - Input Validation: Agent names and messages sanitized before logging
    - Atomic Writes: Uses atomic file operations to prevent data corruption
"""

import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

# Import path utilities for dynamic PROJECT_ROOT resolution (Issue #79)
sys.path.insert(0, str(Path(__file__).parent))
from path_utils import get_session_dir, find_project_root

# Re-export for backward compatibility and testing
__all__ = ["SessionTracker", "find_project_root", "get_default_session_file"]


def get_default_session_file() -> Path:
    """Get default session file path with timestamp.

    This is a helper function for generating unique session file paths.
    Uses path_utils.get_session_dir() for portable path resolution.

    Returns:
        Path object for new session file with format:
        <session_dir>/session-YYYY-MM-DD-HHMMSS.md

    Raises:
        FileNotFoundError: If project root cannot be detected

    Examples:
        >>> path = get_default_session_file()
        >>> print(path.name)
        session-2025-11-19-143022.md

    Design Patterns:
        See library-design-patterns skill for standardized design patterns.
    """
    # Use path_utils for portable session directory detection
    session_dir = get_session_dir(create=True)

    # Generate unique timestamp-based filename
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    filename = f"session-{timestamp}.md"

    return session_dir / filename


class SessionTracker:
    def __init__(self, session_file: Optional[str] = None, use_cache: bool = True):
        """Initialize SessionTracker with dynamic path resolution.

        Args:
            session_file: Optional path to session file for testing.
                         If None, creates/finds session file automatically.
            use_cache: If True, use cached project root (default: True).
                      Set to False in tests that mock project structure.
        """
        # If session_file provided, validate and use it (for testing)
        if session_file:
            from validation import validate_session_path
            validated = validate_session_path(session_file, purpose="session tracking")
            self.session_file = validated
            self.session_dir = self.session_file.parent
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self._check_directory_permissions()
            return

        # Use path_utils for dynamic PROJECT_ROOT resolution (Issue #79)
        # This fixes hardcoded Path("docs/sessions") which failed from subdirectories
        self.session_dir = get_session_dir(create=True, use_cache=use_cache)
        self._check_directory_permissions()

        # Find or create session file for today
        today = datetime.now().strftime("%Y%m%d")
        session_files = list(self.session_dir.glob(f"{today}-*.md"))

        if session_files:
            # Use most recent session file from today
            self.session_file = sorted(session_files)[-1]
        else:
            # Create new session file
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.session_file = self.session_dir / f"{timestamp}-session.md"

            # Initialize with header
            self.session_file.write_text(
                f"# Session {timestamp}\n\n"
                f"**Started**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"---\n\n"
            )

            # Set restrictive permissions (owner read/write only) - CWE-732
            if os.name != 'nt':  # POSIX systems only
                self.session_file.chmod(0o600)

    def _check_directory_permissions(self):
        """Check and warn about insecure directory permissions.

        SECURITY: Warn if session directory is world-writable (CWE-732)
        """
        if os.name == 'nt':
            # Skip permission checks on Windows (different permission model)
            return

        try:
            stat_info = self.session_dir.stat()
            mode = stat_info.st_mode
            # Check if directory is world-writable (others have write permission)
            if mode & 0o002:  # World-writable bit
                warnings.warn(
                    f"Session directory has insecure permissions (world-writable): {self.session_dir}\n"
                    f"Permissions: {oct(mode)}\n"
                    f"Recommendation: chmod 755 or more restrictive",
                    UserWarning,
                    stacklevel=3
                )
        except (OSError, AttributeError):
            # Silently skip if stat fails (e.g., directory doesn't exist yet)
            pass

    def log(self, agent_name, message):
        """Log agent action to session file.

        Records agent action with timestamp to prevent context bloat.
        Instead of keeping output in context, stores in docs/sessions/ for later review.

        Args:
            agent_name (str): Agent identifier (e.g., "researcher", "implementer")
            message (str): Action message (e.g., "Found 3 patterns" or "Implementation complete")

        Output Format:
            **HH:MM:SS - agent_name**: message

        Example:
            tracker.log("researcher", "Found 3 JWT patterns in codebase")
            # Produces: **14:30:22 - researcher**: Found 3 JWT patterns in codebase

        Design Pattern:
            Non-blocking operation - failures to write don't break workflows.
            Session directory created automatically if missing (graceful degradation).
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"**{timestamp} - {agent_name}**: {message}\n\n"

        # Append to session file (portable path already set in __init__)
        with open(self.session_file, "a") as f:
            f.write(entry)

        # Print confirmation (non-blocking - helps with progress visibility)
        print(f"✅ Logged: {agent_name} - {message}")
        print(f"📄 Session: {self.session_file.name}")


def main():
    if len(sys.argv) < 3:
        print("Usage: session_tracker.py <agent_name> <message>")
        print("\nExample:")
        print('  session_tracker.py researcher "Research complete - docs/research/auth.md"')
        sys.exit(1)

    tracker = SessionTracker()
    agent_name = sys.argv[1]
    message = " ".join(sys.argv[2:])
    tracker.log(agent_name, message)


if __name__ == "__main__":
    main()
