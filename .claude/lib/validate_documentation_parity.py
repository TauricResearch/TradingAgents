#!/usr/bin/env python3
"""
Documentation Parity Validator - Validate documentation consistency

DEPRECATED: This regex-based validator is deprecated as of v3.44.0.
Use hybrid_validator.py instead, which provides GenAI-powered semantic
validation with automatic fallback to regex if no API key is available.

Migration:
    # Old (deprecated):
    from validate_documentation_parity import validate_documentation_parity
    report = validate_documentation_parity(project_root)

    # New (recommended):
    from hybrid_validator import validate_manifest_alignment
    report = validate_manifest_alignment(repo_root)

Removal planned: v3.45.0

---

This module validates documentation consistency across CLAUDE.md, PROJECT.md,
README.md, and CHANGELOG.md to prevent documentation drift and ensure accuracy.

Validation Categories:
1. Version consistency - Detect when CLAUDE.md date != PROJECT.md date
2. Count discrepancies - Detect when documented counts != actual counts (agents, commands, skills, hooks)
3. Cross-references - Detect when documented features don't exist in codebase (or vice versa)
4. CHANGELOG parity - Detect when plugin.json version missing from CHANGELOG
5. Security documentation - Detect missing or incomplete security docs

Security Features:
- Path validation via security_utils (CWE-22, CWE-59 prevention)
- File size limits to prevent DoS (max 10MB per file)
- Safe file reading (no execution of file content)
- Audit logging for validation operations

Usage:
    from validate_documentation_parity import validate_documentation_parity

    # Validate documentation
    report = validate_documentation_parity(project_root)

    if report.has_errors:
        print(report.generate_report())
        sys.exit(report.exit_code)

CLI Usage:
    python validate_documentation_parity.py --project-root /path/to/project
    python validate_documentation_parity.py --verbose
    python validate_documentation_parity.py --json

Date: 2025-11-09
Related: Documentation parity validation feature
Agent: implementer

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import re
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any

# Emit deprecation warning on module import
warnings.warn(
    "validate_documentation_parity is deprecated as of v3.44.0. "
    "Use hybrid_validator.validate_manifest_alignment() instead. "
    "This module will be removed in v3.45.0.",
    DeprecationWarning,
    stacklevel=2,
)

# Import security utilities
try:
    from plugins.autonomous_dev.lib.security_utils import (
        validate_path,
        audit_log,
        PROJECT_ROOT,
    )
except ImportError:
    # Fallback for testing
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()

    def validate_path(path: Path, context: str) -> Path:
        """Fallback path validation for testing."""
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")
        resolved = path.resolve()
        if not str(resolved).startswith(str(PROJECT_ROOT)):
            raise ValueError(f"Path outside project root: {resolved}")
        return resolved

    def audit_log(event_type: str, status: str, context: Dict[str, Any]) -> None:
        """Fallback audit logging for testing."""
        pass


# File size limit to prevent DoS attacks (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


class ValidationLevel(Enum):
    """Validation issue severity levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class ParityIssue:
    """Represents a single documentation parity issue."""

    level: ValidationLevel
    message: str
    details: str = ""

    def __str__(self) -> str:
        """Human-readable string representation."""
        if self.details:
            return f"[{self.level.value}] {self.message}\n  Details: {self.details}"
        return f"[{self.level.value}] {self.message}"


@dataclass
class ParityReport:
    """Comprehensive documentation parity validation report."""

    version_issues: List[ParityIssue] = field(default_factory=list)
    count_issues: List[ParityIssue] = field(default_factory=list)
    cross_reference_issues: List[ParityIssue] = field(default_factory=list)
    changelog_issues: List[ParityIssue] = field(default_factory=list)
    security_issues: List[ParityIssue] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        """Total number of issues across all categories."""
        return (
            len(self.version_issues)
            + len(self.count_issues)
            + len(self.cross_reference_issues)
            + len(self.changelog_issues)
            + len(self.security_issues)
        )

    @property
    def error_count(self) -> int:
        """Count of ERROR level issues."""
        all_issues = (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )
        return sum(1 for issue in all_issues if issue.level == ValidationLevel.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of WARNING level issues."""
        all_issues = (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )
        return sum(1 for issue in all_issues if issue.level == ValidationLevel.WARNING)

    @property
    def info_count(self) -> int:
        """Count of INFO level issues."""
        all_issues = (
            self.version_issues
            + self.count_issues
            + self.cross_reference_issues
            + self.changelog_issues
            + self.security_issues
        )
        return sum(1 for issue in all_issues if issue.level == ValidationLevel.INFO)

    @property
    def has_errors(self) -> bool:
        """True if any ERROR level issues exist."""
        return self.error_count > 0

    @property
    def has_warnings(self) -> bool:
        """True if any WARNING level issues exist."""
        return self.warning_count > 0

    @property
    def exit_code(self) -> int:
        """Exit code for CLI integration (0=success, 1=errors)."""
        return 1 if self.has_errors else 0

    def generate_report(self) -> str:
        """Generate human-readable markdown report."""
        lines = ["# Documentation Parity Validation Report", ""]

        # Summary
        lines.append(f"**Total Issues**: {self.total_issues}")
        lines.append(f"- Errors: {self.error_count}")
        lines.append(f"- Warnings: {self.warning_count}")
        lines.append(f"- Info: {self.info_count}")
        lines.append("")

        # Version issues
        if self.version_issues:
            lines.append("## Version Consistency Issues")
            lines.append("")
            for issue in self.version_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Count issues
        if self.count_issues:
            lines.append("## Count Discrepancy Issues")
            lines.append("")
            for issue in self.count_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Cross-reference issues
        if self.cross_reference_issues:
            lines.append("## Cross-Reference Issues")
            lines.append("")
            for issue in self.cross_reference_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # CHANGELOG issues
        if self.changelog_issues:
            lines.append("## CHANGELOG Parity Issues")
            lines.append("")
            for issue in self.changelog_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Security documentation issues
        if self.security_issues:
            lines.append("## Security Documentation Issues")
            lines.append("")
            for issue in self.security_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Status
        if self.total_issues == 0:
            lines.append("**Status**: ✓ All documentation checks passed")
        elif self.has_errors:
            lines.append("**Status**: ✗ Documentation has errors that must be fixed")
        else:
            lines.append("**Status**: ⚠ Documentation has warnings")

        return "\n".join(lines)


class DocumentationParityValidator:
    """Validates documentation consistency across project files."""

    def __init__(self, project_root: Path):
        """Initialize validator with project root path.

        Args:
            project_root: Path to project root directory

        Raises:
            ValueError: If path validation fails (CWE-22, CWE-59 prevention)
        """
        # Validate project root path
        self.project_root = validate_path(Path(project_root), "project root")

        # Define documentation file paths
        self.claude_md = self.project_root / "CLAUDE.md"
        self.project_md = self.project_root / ".claude" / "PROJECT.md"
        self.readme_md = self.project_root / "README.md"
        self.changelog_md = self.project_root / "CHANGELOG.md"
        self.security_md = self.project_root / "docs" / "SECURITY.md"

        # Define plugin paths
        self.plugin_dir = self.project_root / "plugins" / "autonomous-dev"
        self.agents_dir = self.plugin_dir / "agents"
        self.commands_dir = self.plugin_dir / "commands"
        self.skills_dir = self.plugin_dir / "skills"
        self.hooks_dir = self.plugin_dir / "hooks"
        self.lib_dir = self.plugin_dir / "lib"
        self.plugin_json = self.plugin_dir / "plugin.json"

        # Audit log initialization
        audit_log(
            "documentation_validation",
            "initialized",
            {"project_root": str(self.project_root)},
        )

    def _read_file_safe(self, file_path: Path) -> Optional[str]:
        """Safely read file content with size limit.

        Args:
            file_path: Path to file to read

        Returns:
            File content as string, or None if file doesn't exist or exceeds size limit

        Security:
            - Checks file size to prevent DoS attacks
            - Reads file as text (no execution)
            - Returns None for oversized files
        """
        if not file_path.exists():
            return None

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            audit_log(
                "documentation_validation",
                "file_too_large",
                {"file": str(file_path), "size": file_size},
            )
            return None

        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            audit_log(
                "documentation_validation",
                "read_error",
                {"file": str(file_path), "error": str(e)},
            )
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string in YYYY-MM-DD format.

        Args:
            date_str: Date string to parse

        Returns:
            datetime object or None if parsing fails
        """
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except ValueError:
            return None

    def _has_malformed_date(self, content: str) -> Optional[str]:
        """Check if content has Last Updated field with malformed date.

        Args:
            content: Markdown file content

        Returns:
            The malformed date string if found, None otherwise
        """
        # Pattern: **Last Updated**: anything that's not YYYY-MM-DD
        match = re.search(r"\*\*Last Updated:?\*\*:?\s*([^\n]+)", content)
        if match:
            date_str = match.group(1).strip()
            # Check if it's NOT in YYYY-MM-DD format
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                return date_str
        return None

    def _extract_version_date(self, content: str, filename: str) -> Optional[str]:
        """Extract version date from markdown content.

        Args:
            content: Markdown file content
            filename: Filename for error reporting

        Returns:
            Date string in YYYY-MM-DD format, or None if not found
        """
        # Pattern: **Last Updated**: YYYY-MM-DD or **Last Updated:** YYYY-MM-DD
        # Support both single colon (:) and double colon (::) after "Last Updated"
        match = re.search(r"\*\*Last Updated:?\*\*:?\s*(\d{4}-\d{2}-\d{2})", content)
        if match:
            return match.group(1)
        return None

    def validate_version_consistency(self) -> List[ParityIssue]:
        """Validate version consistency between CLAUDE.md and PROJECT.md.

        Returns:
            List of validation issues

        Checks:
        - CLAUDE.md has version date
        - PROJECT.md has version date
        - Dates are in sync (no drift)
        """
        issues = []

        # Read files
        claude_content = self._read_file_safe(self.claude_md)
        project_content = self._read_file_safe(self.project_md)

        # Check files exist
        if claude_content is None:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    "CLAUDE.md is missing",
                    f"Expected at: {self.claude_md}",
                )
            )
        if project_content is None:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    "PROJECT.md is missing",
                    f"Expected at: {self.project_md}",
                )
            )

        if not claude_content or not project_content:
            return issues

        # Extract version dates
        claude_date_str = self._extract_version_date(claude_content, "CLAUDE.md")
        project_date_str = self._extract_version_date(project_content, "PROJECT.md")

        # Check for malformed dates
        claude_malformed = self._has_malformed_date(claude_content)
        project_malformed = self._has_malformed_date(project_content)

        # Check version dates exist or are malformed
        if claude_date_str is None:
            if claude_malformed:
                issues.append(
                    ParityIssue(
                        ValidationLevel.ERROR,
                        "CLAUDE.md has malformed date format",
                        f"Found: {claude_malformed}, Expected format: YYYY-MM-DD",
                    )
                )
            else:
                issues.append(
                    ParityIssue(
                        ValidationLevel.ERROR,
                        "CLAUDE.md is missing version date",
                        "Expected format: **Last Updated**: YYYY-MM-DD",
                    )
                )
        if project_date_str is None:
            if project_malformed:
                issues.append(
                    ParityIssue(
                        ValidationLevel.ERROR,
                        "PROJECT.md has malformed date format",
                        f"Found: {project_malformed}, Expected format: YYYY-MM-DD",
                    )
                )
            else:
                issues.append(
                    ParityIssue(
                        ValidationLevel.ERROR,
                        "PROJECT.md is missing version date",
                        "Expected format: **Last Updated**: YYYY-MM-DD",
                    )
                )

        if not claude_date_str or not project_date_str:
            return issues

        # Parse dates
        claude_date = self._parse_date(claude_date_str)
        project_date = self._parse_date(project_date_str)

        if claude_date is None:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    "CLAUDE.md has malformed date format",
                    f"Found: {claude_date_str}, Expected: YYYY-MM-DD",
                )
            )
        if project_date is None:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    "PROJECT.md has malformed date format",
                    f"Found: {project_date_str}, Expected: YYYY-MM-DD",
                )
            )

        if not claude_date or not project_date:
            return issues

        # Compare dates
        if claude_date < project_date:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    "CLAUDE.md is outdated relative to PROJECT.md",
                    f"CLAUDE.md: {claude_date_str}, PROJECT.md: {project_date_str}",
                )
            )
        elif project_date < claude_date:
            issues.append(
                ParityIssue(
                    ValidationLevel.WARNING,
                    "PROJECT.md is outdated relative to CLAUDE.md",
                    f"PROJECT.md: {project_date_str}, CLAUDE.md: {claude_date_str}",
                )
            )

        return issues

    def _count_files_in_dir(self, directory: Path, extension: str) -> int:
        """Count files with given extension in directory.

        Args:
            directory: Directory to search
            extension: File extension (e.g., '.md', '.py')

        Returns:
            Count of files with extension
        """
        if not directory.exists():
            return 0
        return len(list(directory.glob(f"*{extension}")))

    def _extract_count_from_text(
        self, content: str, pattern: str
    ) -> Optional[int]:
        """Extract count from text using regex pattern.

        Args:
            content: Text to search
            pattern: Regex pattern with count capture group

        Returns:
            Extracted count or None if not found
        """
        match = re.search(pattern, content)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                return None
        return None

    def validate_count_discrepancies(self) -> List[ParityIssue]:
        """Validate documented counts match actual counts.

        Returns:
            List of validation issues

        Checks:
        - Agent count (documented vs actual)
        - Command count (documented vs actual)
        - Skill count (documented vs actual)
        - Hook count (documented vs actual)
        """
        issues = []

        # Read CLAUDE.md
        claude_content = self._read_file_safe(self.claude_md)
        if claude_content is None:
            return issues  # Already flagged in version validation

        # Count actual files
        actual_agents = self._count_files_in_dir(self.agents_dir, ".md")
        actual_commands = self._count_files_in_dir(self.commands_dir, ".md")
        actual_skills = self._count_files_in_dir(self.skills_dir, ".md")
        actual_hooks = self._count_files_in_dir(self.hooks_dir, ".py")

        # Extract documented counts
        # Pattern: "### Agents (5 specialists)" or "Agents (5)"
        doc_agents = self._extract_count_from_text(
            claude_content, r"Agents?\s*\((\d+)\s+(?:specialists?|active)?\)"
        )
        # Pattern: "**Commands (10 active)**:" or "Commands (10)"
        doc_commands = self._extract_count_from_text(
            claude_content, r"Commands?\s*\((\d+)\s+(?:active|total)?\)"
        )
        # Pattern: "### Skills (19 Active)" or "Skills (19)"
        doc_skills = self._extract_count_from_text(
            claude_content, r"Skills?\s*\((\d+)\s+(?:Active|active|total)?\)"
        )
        # Pattern: "### Hooks (29 total automation)" or "Hooks (29)"
        doc_hooks = self._extract_count_from_text(
            claude_content, r"Hooks?\s*\((\d+)\s+(?:total|active)?\s*(?:automation)?\)"
        )

        # Validate agent count
        if doc_agents is not None and doc_agents != actual_agents:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    f"Agent count mismatch: documented {doc_agents}, actual {actual_agents}",
                    f"Found {actual_agents} agent files in {self.agents_dir}",
                )
            )

        # Validate command count
        if doc_commands is not None and doc_commands != actual_commands:
            issues.append(
                ParityIssue(
                    ValidationLevel.ERROR,
                    f"Command count mismatch: documented {doc_commands}, actual {actual_commands}",
                    f"Found {actual_commands} command files in {self.commands_dir}",
                )
            )

        # Validate skill count (WARNING level - less critical)
        if doc_skills is not None and doc_skills != actual_skills:
            issues.append(
                ParityIssue(
                    ValidationLevel.WARNING,
                    f"Skill count mismatch: documented {doc_skills}, actual {actual_skills}",
                    f"Found {actual_skills} skill files in {self.skills_dir}",
                )
            )

        # Validate hook count (WARNING level - less critical)
        if doc_hooks is not None and doc_hooks != actual_hooks:
            issues.append(
                ParityIssue(
                    ValidationLevel.WARNING,
                    f"Hook count mismatch: documented {doc_hooks}, actual {actual_hooks}",
                    f"Found {actual_hooks} hook files in {self.hooks_dir}",
                )
            )

        return issues

    def _extract_documented_features(
        self, content: str, feature_type: str
    ) -> List[str]:
        """Extract documented feature names from markdown content.

        Args:
            content: Markdown content to parse
            feature_type: Type of feature ('agent', 'command', 'library')

        Returns:
            List of feature names
        """
        features = []

        if feature_type == "agent":
            # Pattern: "- **researcher**: Web research for patterns"
            # Pattern: "**researcher**: Web research"
            matches = re.findall(r"\*\*([a-z-]+)\*\*:\s*[A-Z]", content)
            features.extend(matches)

        elif feature_type == "command":
            # Pattern: "- `/auto-implement` - Autonomous feature development"
            # Pattern: "`/auto-implement`"
            matches = re.findall(r"`/([a-z-]+)`", content)
            # Exclude built-in CLI commands (not part of plugin)
            built_in_commands = {"clear", "exit", "help"}
            features.extend([m for m in matches if m not in built_in_commands])

        elif feature_type == "library":
            # Pattern: "1. **security_utils.py** - Centralized security validation"
            # Pattern: "**security_utils.py**"
            matches = re.findall(r"\*\*([a-z_]+\.py)\*\*", content)
            features.extend(matches)

        return list(set(features))  # Remove duplicates

    def validate_cross_references(self) -> List[ParityIssue]:
        """Validate documented features exist in codebase.

        Returns:
            List of validation issues

        Checks:
        - Documented agents exist as files
        - Documented commands exist as files
        - Documented libraries exist as files
        - Undocumented features in codebase (reverse check)
        """
        issues = []

        # Read CLAUDE.md
        claude_content = self._read_file_safe(self.claude_md)
        if claude_content is None:
            return issues

        # Extract documented features
        doc_agents = self._extract_documented_features(claude_content, "agent")
        doc_commands = self._extract_documented_features(claude_content, "command")
        doc_libraries = self._extract_documented_features(claude_content, "library")

        # Get actual features
        actual_agents = (
            [f.stem for f in self.agents_dir.glob("*.md")]
            if self.agents_dir.exists()
            else []
        )
        actual_commands = (
            [f.stem for f in self.commands_dir.glob("*.md")]
            if self.commands_dir.exists()
            else []
        )
        actual_libraries = (
            [f.name for f in self.lib_dir.glob("*.py")]
            if self.lib_dir.exists()
            else []
        )

        # Check documented agents exist
        for agent in doc_agents:
            if agent not in actual_agents:
                issues.append(
                    ParityIssue(
                        ValidationLevel.ERROR,
                        f"Documented agent '{agent}' not found in codebase",
                        f"Expected file: {self.agents_dir / agent}.md",
                    )
                )

        # Check documented commands exist
        for command in doc_commands:
            if command not in actual_commands:
                issues.append(
                    ParityIssue(
                        ValidationLevel.ERROR,
                        f"Documented command '{command}' not found in codebase",
                        f"Expected file: {self.commands_dir / command}.md",
                    )
                )

        # Check documented libraries exist
        for library in doc_libraries:
            if library not in actual_libraries:
                issues.append(
                    ParityIssue(
                        ValidationLevel.WARNING,
                        f"Documented library '{library}' not found in codebase",
                        f"Expected file: {self.lib_dir / library}",
                    )
                )

        # Reverse check: undocumented features
        for agent in actual_agents:
            if agent not in doc_agents and not agent.startswith("_"):
                issues.append(
                    ParityIssue(
                        ValidationLevel.INFO,
                        f"Agent '{agent}' exists in codebase but not documented",
                        f"Consider adding to CLAUDE.md",
                    )
                )

        for command in actual_commands:
            if command not in doc_commands and not command.startswith("_"):
                issues.append(
                    ParityIssue(
                        ValidationLevel.INFO,
                        f"Command '{command}' exists in codebase but not documented",
                        f"Consider adding to CLAUDE.md",
                    )
                )

        return issues

    def validate_changelog_parity(self) -> List[ParityIssue]:
        """Validate CHANGELOG contains current plugin version.

        Returns:
            List of validation issues

        Checks:
        - CHANGELOG.md exists
        - Current version from plugin.json is documented in CHANGELOG
        """
        issues = []

        # Read plugin.json for current version
        plugin_json_content = self._read_file_safe(self.plugin_json)
        if plugin_json_content is None:
            # plugin.json missing is not critical for this check
            return issues

        try:
            plugin_data = json.loads(plugin_json_content)
            current_version = plugin_data.get("version", "")
        except json.JSONDecodeError:
            issues.append(
                ParityIssue(
                    ValidationLevel.WARNING,
                    "plugin.json is malformed",
                    f"Could not parse JSON from {self.plugin_json}",
                )
            )
            return issues

        if not current_version:
            return issues

        # Read CHANGELOG.md
        changelog_content = self._read_file_safe(self.changelog_md)
        if changelog_content is None:
            issues.append(
                ParityIssue(
                    ValidationLevel.WARNING,
                    "CHANGELOG.md is missing",
                    f"Expected at: {self.changelog_md}",
                )
            )
            return issues

        # Check if current version is documented in CHANGELOG
        # Pattern: ## [3.8.0] or ## [3.8.0-beta.1]
        version_pattern = re.escape(current_version)
        if not re.search(rf"##\s*\[{version_pattern}\]", changelog_content):
            issues.append(
                ParityIssue(
                    ValidationLevel.WARNING,
                    f"Version {current_version} not found in CHANGELOG.md",
                    f"Add entry for version {current_version} to CHANGELOG.md",
                )
            )

        return issues

    def validate_security_documentation(self) -> List[ParityIssue]:
        """Validate security documentation completeness.

        Returns:
            List of validation issues

        Checks:
        - Security practices mentioned in CLAUDE.md
        - SECURITY.md exists
        - CWE coverage documented
        """
        issues = []

        # Read CLAUDE.md
        claude_content = self._read_file_safe(self.claude_md)
        security_md_content = self._read_file_safe(self.security_md)

        # Check if security is mentioned in CLAUDE.md
        if claude_content:
            if (
                "security" not in claude_content.lower()
                and security_md_content is None
            ):
                issues.append(
                    ParityIssue(
                        ValidationLevel.WARNING,
                        "Security documentation is missing",
                        "No security section in CLAUDE.md and SECURITY.md not found",
                    )
                )

        # Check SECURITY.md exists
        if security_md_content is None:
            # Only flag if CLAUDE.md mentions security but SECURITY.md missing
            if claude_content and "security" in claude_content.lower():
                issues.append(
                    ParityIssue(
                        ValidationLevel.WARNING,
                        "SECURITY.md is missing",
                        f"Expected at: {self.security_md}",
                    )
                )

        return issues

    def validate(self) -> ParityReport:
        """Run all validation checks and generate comprehensive report.

        Returns:
            ParityReport with all validation results
        """
        audit_log(
            "documentation_validation",
            "started",
            {"project_root": str(self.project_root)},
        )

        report = ParityReport(
            version_issues=self.validate_version_consistency(),
            count_issues=self.validate_count_discrepancies(),
            cross_reference_issues=self.validate_cross_references(),
            changelog_issues=self.validate_changelog_parity(),
            security_issues=self.validate_security_documentation(),
        )

        audit_log(
            "documentation_validation",
            "completed",
            {
                "project_root": str(self.project_root),
                "total_issues": report.total_issues,
                "errors": report.error_count,
                "warnings": report.warning_count,
            },
        )

        return report


def validate_documentation_parity(project_root: Path) -> ParityReport:
    """Convenience function for documentation validation.

    Args:
        project_root: Path to project root directory

    Returns:
        ParityReport with all validation results
    """
    validator = DocumentationParityValidator(project_root)
    return validator.validate()


def main():
    """CLI entry point for documentation parity validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate documentation parity across project files"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to project root (default: current directory)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output JSON for scripting"
    )

    args = parser.parse_args()

    try:
        # Validate documentation
        report = validate_documentation_parity(args.project_root)

        if args.json:
            # JSON output for scripting
            output = {
                "total_issues": report.total_issues,
                "errors": report.error_count,
                "warnings": report.warning_count,
                "info": report.info_count,
                "exit_code": report.exit_code,
                "version_issues": [str(i) for i in report.version_issues],
                "count_issues": [str(i) for i in report.count_issues],
                "cross_reference_issues": [
                    str(i) for i in report.cross_reference_issues
                ],
                "changelog_issues": [str(i) for i in report.changelog_issues],
                "security_issues": [str(i) for i in report.security_issues],
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            print(report.generate_report())

        sys.exit(report.exit_code)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
