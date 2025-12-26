#!/usr/bin/env python3
"""
Protected File Detector - Detect user artifacts and protected files

This module identifies files that should be protected during installation,
including user-created artifacts, modified plugin files, and sensitive data.

Key Features:
- Always-protected files (.env, PROJECT.md, state files)
- Custom hook detection
- Plugin default comparison (hash-based)
- Glob pattern matching for protected patterns
- File categorization (config, state, custom_hook, modified_plugin)

Usage:
    from protected_file_detector import ProtectedFileDetector

    # Initialize with plugin defaults registry
    detector = ProtectedFileDetector(plugin_defaults={
        ".claude/hooks/auto_format.py": "abc123...",
    })

    # Detect protected files
    protected = detector.detect_protected_files(project_dir)

Date: 2025-12-09
Issue: #106 (GenAI-first installation system)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import hashlib
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Optional

# Security utilities for path validation
try:
    from plugins.autonomous_dev.lib.security_utils import audit_log
except ImportError:
    from security_utils import audit_log


# Always-protected files (never overwritten)
ALWAYS_PROTECTED = [
    ".claude/PROJECT.md",
    ".env",
    ".env.local",
    ".claude/batch_state.json",
    ".claude/session_state.json",
]

# Protected file patterns (glob patterns)
PROTECTED_PATTERNS = [
    ".claude/hooks/custom_*.py",  # Custom hooks
    "*.env",  # All .env files
    "**/*.secret",  # Secret files
]


class ProtectedFileDetector:
    """Detect user artifacts and protected files.

    This class identifies files that should be protected during installation,
    including user-created artifacts, modified plugin files, and sensitive data.

    Attributes:
        additional_patterns: Additional glob patterns to protect
        plugin_defaults: Dict mapping file paths to their default hashes

    Examples:
        >>> detector = ProtectedFileDetector()
        >>> protected = detector.detect_protected_files(project_dir)
        >>> print(f"Found {len(protected)} protected files")
    """

    def __init__(
        self,
        additional_patterns: Optional[List[str]] = None,
        plugin_defaults: Optional[Dict[str, str]] = None
    ):
        """Initialize protected file detector.

        Args:
            additional_patterns: Additional glob patterns to protect
            plugin_defaults: Dict mapping file paths to their default hashes
        """
        self.additional_patterns = additional_patterns or []
        self.plugin_defaults = plugin_defaults or {}

        # Audit log initialization
        audit_log("protected_file_detector", "initialized", {
            "additional_patterns": len(self.additional_patterns),
            "plugin_defaults": len(self.plugin_defaults)
        })

    def get_protected_patterns(self) -> List[str]:
        """Get all protected file patterns.

        Returns:
            List of glob patterns for protected files
        """
        return ALWAYS_PROTECTED + PROTECTED_PATTERNS + self.additional_patterns

    def has_plugin_default(self, file_path: str) -> bool:
        """Check if file has a known plugin default.

        Args:
            file_path: Relative file path

        Returns:
            True if file has plugin default registered
        """
        return file_path in self.plugin_defaults

    def detect_protected_files(self, project_dir: Path | str) -> List[Dict[str, Any]]:
        """Detect all protected files in project directory.

        Args:
            project_dir: Project directory to scan

        Returns:
            List of protected file dicts with:
            - path: Relative path from project dir
            - category: Type of protected file (config, state, custom_hook, modified_plugin)
            - modified: True if modified from plugin default
            - reason: Why file is protected

        Examples:
            >>> detector = ProtectedFileDetector()
            >>> protected = detector.detect_protected_files(project_dir)
            >>> for f in protected:
            ...     print(f"{f['path']} - {f['reason']}")
        """
        project_path = Path(project_dir) if isinstance(project_dir, str) else project_dir
        project_path = project_path.resolve()

        # Return empty list if project directory doesn't exist
        if not project_path.exists():
            return []

        protected_files = []

        # Scan project directory for files
        for file_path in project_path.rglob("*"):
            # Skip directories
            if file_path.is_dir():
                continue

            # Get relative path from project dir
            try:
                relative_path = file_path.relative_to(project_path)
                relative_str = str(relative_path).replace("\\", "/")
            except ValueError:
                continue

            # Check if file is protected
            protection_info = self._check_protection(relative_str, file_path)
            if protection_info:
                protected_files.append({
                    "path": relative_str,
                    **protection_info
                })

        return protected_files

    def matches_pattern(self, file_path: str) -> bool:
        """Check if file path matches any protected pattern.

        Args:
            file_path: Relative file path

        Returns:
            True if file matches a protected pattern

        Examples:
            >>> detector = ProtectedFileDetector(additional_patterns=["*.env"])
            >>> detector.matches_pattern("production.env")
            True
        """
        all_patterns = self.get_protected_patterns()

        for pattern in all_patterns:
            # Use fnmatch for glob pattern matching
            if fnmatch.fnmatch(file_path, pattern):
                return True

        return False

    def calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hex digest

        Examples:
            >>> detector = ProtectedFileDetector()
            >>> hash_val = detector.calculate_hash(Path("file.py"))
        """
        sha256 = hashlib.sha256()

        # Read file in chunks to handle large files
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        return sha256.hexdigest()

    def matches_plugin_default(self, file_path: Path, relative_path: str) -> bool:
        """Check if file matches its plugin default hash.

        Args:
            file_path: Absolute path to file
            relative_path: Relative path for lookup in plugin_defaults

        Returns:
            True if file hash matches plugin default

        Examples:
            >>> detector = ProtectedFileDetector(plugin_defaults={
            ...     "hook.py": "abc123..."
            ... })
            >>> detector.matches_plugin_default(Path("hook.py"), "hook.py")
        """
        # Check if we have a default hash for this file
        if relative_path not in self.plugin_defaults:
            return False

        # Calculate current file hash
        current_hash = self.calculate_hash(file_path)

        # Compare with default hash
        return current_hash == self.plugin_defaults[relative_path]

    def _check_protection(self, relative_path: str, full_path: Path) -> Optional[Dict[str, Any]]:
        """Check if file should be protected and categorize it.

        Args:
            relative_path: Relative path from project root
            full_path: Full path to file

        Returns:
            Dict with protection info or None if not protected
        """
        # Check if file is modified from plugin default (check this first)
        if self.has_plugin_default(relative_path):
            if not self.matches_plugin_default(full_path, relative_path):
                return {
                    "category": "modified",
                    "modified": True,
                    "reason": "Modified from plugin default"
                }
            # File matches plugin default, so it's not protected
            return None

        # Check always-protected files (these are user artifacts)
        if relative_path in ALWAYS_PROTECTED:
            # These are always user-created, so category is "new"
            return {
                "category": "new",
                "modified": False,
                "reason": "User artifact (always protected)"
            }

        # Check if file matches protected patterns
        if self.matches_pattern(relative_path):
            # Determine if it's a custom hook
            if "custom_" in relative_path and relative_path.endswith(".py"):
                return {
                    "category": "custom_hook",
                    "modified": False,
                    "reason": "Custom user hook"
                }

            # Other protected patterns - categorize appropriately
            category = self._categorize_file(relative_path)
            return {
                "category": category,
                "modified": False,
                "reason": f"Matches protected pattern"
            }

        return None

    def _categorize_file(self, file_path: str) -> str:
        """Categorize protected file type.

        Args:
            file_path: Relative file path

        Returns:
            Category string (config, state, custom_hook, modified, new)
        """
        # State files
        if "state.json" in file_path or "batch_" in file_path:
            return "state"

        # Config files
        if file_path.endswith("PROJECT.md") or ".env" in file_path:
            return "config"

        # Custom hooks
        if "custom_" in file_path and file_path.endswith(".py"):
            return "custom_hook"

        # Modified plugin files
        if self.has_plugin_default(file_path):
            return "modified"

        # New user files
        return "new"
