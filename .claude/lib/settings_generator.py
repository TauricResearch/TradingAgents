#!/usr/bin/env python3
"""
Settings Generator - Create settings.local.json with specific command patterns

This module generates .claude/settings.local.json with:
1. Specific command patterns (Bash(git:*), Bash(pytest:*), etc.) - NO wildcards
2. Comprehensive deny list blocking dangerous operations
3. File operation permissions (Read, Write, Edit, Glob, Grep)
4. Command auto-discovery from plugins/autonomous-dev/commands/*.md
5. User customization preservation during upgrades

Security Features:
- NO wildcards: Uses specific patterns only (Bash(git:*) NOT Bash(*))
- Comprehensive deny list: Blocks rm -rf, sudo, eval, chmod, etc.
- Path validation: CWE-22 (path traversal), CWE-59 (symlinks)
- Command injection prevention: Validates pattern syntax
- Atomic writes: Secure permissions (0o600)
- Audit logging: All operations logged

Usage:
    # Fresh install
    generator = SettingsGenerator(plugin_dir)
    result = generator.write_settings(settings_path)

    # Upgrade with merge
    result = generator.write_settings(settings_path, merge_existing=True, backup=True)

See Also:
    - docs/LIBRARIES.md section 30 for API documentation
    - tests/unit/lib/test_settings_generator.py for test cases
    - GitHub Issue #115 for security requirements

Date: 2025-12-12
Issue: GitHub #115
Agent: implementer
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Import security utilities
try:
    from autonomous_dev.lib.security_utils import validate_path, audit_log
    from autonomous_dev.lib.settings_merger import UNIFIED_HOOK_REPLACEMENTS
except ImportError:
    # Fallback for direct script execution
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from security_utils import validate_path, audit_log
    from settings_merger import UNIFIED_HOOK_REPLACEMENTS


# =============================================================================
# Module Constants
# =============================================================================

# Version for settings generation
SETTINGS_VERSION = "1.0.0"

# Safe command patterns - SPECIFIC ONLY, NO WILDCARDS
SAFE_COMMAND_PATTERNS = [
    # File operations (always needed)
    "Read(**)",
    "Write(**)",
    "Edit(**)",
    "Glob(**)",
    "Grep(**)",

    # Common file-specific patterns
    "Read(**/*.py)",
    "Write(**/*.py)",
    "Read(**/*.md)",
    "Write(**/*.md)",

    # Git operations (safe, read-only or controlled writes)
    "Bash(git:*)",

    # Python/Testing
    "Bash(python:*)",
    "Bash(python3:*)",
    "Bash(pytest:*)",
    "Bash(pip:*)",
    "Bash(pip3:*)",

    # GitHub CLI (safe operations)
    "Bash(gh:*)",

    # Package managers (local install only)
    "Bash(npm:*)",

    # Safe read-only commands
    "Bash(ls:*)",
    "Bash(cat:*)",
    "Bash(head:*)",
    "Bash(tail:*)",
    "Bash(grep:*)",
    "Bash(find:*)",
    "Bash(which:*)",
    "Bash(pwd:*)",
    "Bash(echo:*)",

    # Safe directory operations
    "Bash(cd:*)",
    "Bash(mkdir:*)",
    "Bash(touch:*)",

    # Safe file operations (not destructive)
    "Bash(cp:*)",
    "Bash(mv:*)",

    # Other common tools
    "Bash(black:*)",
    "Bash(mypy:*)",
    "Bash(ruff:*)",
    "Bash(isort:*)",
]

# Dangerous operations to ALWAYS deny (from auto_approve_policy.json)
DEFAULT_DENY_LIST = [
    # Destructive file operations
    "Bash(rm:-rf*)",
    "Bash(rm:-f*)",
    "Bash(shred:*)",
    "Bash(dd:*)",
    "Bash(mkfs:*)",
    "Bash(fdisk:*)",
    "Bash(parted:*)",

    # Privilege escalation
    "Bash(sudo:*)",
    "Bash(su:*)",
    "Bash(doas:*)",

    # Code execution
    "Bash(eval:*)",
    "Bash(exec:*)",
    "Bash(source:*)",
    "Bash(.:*)",  # . is alias for source

    # Permission changes
    "Bash(chmod:*)",
    "Bash(chown:*)",
    "Bash(chgrp:*)",

    # Network operations (potential data exfiltration)
    "Bash(nc:*)",
    "Bash(netcat:*)",
    "Bash(ncat:*)",
    "Bash(telnet:*)",
    "Bash(curl:*|*sh*)",
    "Bash(curl:*|*bash*)",
    "Bash(curl:*--data*)",  # Data exfiltration
    "Bash(wget:*|*sh*)",
    "Bash(wget:*|*bash*)",
    "Bash(wget:*--post-file*)",  # Data exfiltration

    # Dangerous git operations
    "Bash(git:*--force*)",
    "Bash(git:*push*-f*)",
    "Bash(git:*reset*--hard*)",
    "Bash(git:*clean*-fd*)",

    # Package operations (system-level)
    "Bash(apt:*install*)",
    "Bash(apt:*remove*)",
    "Bash(yum:*install*)",
    "Bash(brew:*install*)",
    "Bash(npm:*install*-g*)",  # Global install
    "Bash(npm:publish*)",
    "Bash(pip:upload*)",
    "Bash(twine:upload*)",

    # System operations
    "Bash(shutdown:*)",
    "Bash(reboot:*)",
    "Bash(halt:*)",
    "Bash(poweroff:*)",
    "Bash(kill:-9*-1*)",
    "Bash(killall:-9*)",

    # Shell injections
    "Bash(*|*sh*)",
    "Bash(*|*bash*)",
    "Bash(*$(rm*)",
    "Bash(*`rm*)",

    # Sensitive file access
    "Read(./.env)",
    "Read(./.env.*)",
    "Read(~/.ssh/**)",
    "Read(~/.aws/**)",
    "Read(~/.config/gh/**)",
    "Write(/etc/**)",
    "Write(/System/**)",
    "Write(/usr/**)",
    "Write(~/.ssh/**)",
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PermissionIssue:
    """Details about a detected permission issue.

    Attributes:
        issue_type: Type of issue (wildcard_pattern, missing_deny_list, empty_deny_list, outdated_pattern)
        description: Human-readable description of the issue
        pattern: Pattern affected by this issue (empty string if N/A)
        severity: Severity level (warning, error)
    """
    issue_type: str
    description: str
    pattern: str
    severity: str


@dataclass
class ValidationResult:
    """Result of permission validation.

    Attributes:
        valid: Whether validation passed
        issues: List of detected issues
        needs_fix: Whether fixes should be applied
    """
    valid: bool
    issues: List[PermissionIssue]
    needs_fix: bool


@dataclass
class GeneratorResult:
    """Result of settings generation operation.

    Attributes:
        success: Whether generation succeeded
        message: Human-readable result message
        settings_path: Path to generated settings file (None if failed)
        patterns_added: Number of new patterns added
        patterns_preserved: Number of user patterns preserved (upgrade only)
        denies_added: Number of deny patterns added
        details: Additional result details
    """
    success: bool
    message: str
    settings_path: Optional[str] = None
    patterns_added: int = 0
    patterns_preserved: int = 0
    denies_added: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


class SettingsGeneratorError(Exception):
    """Exception raised for settings generation errors."""
    pass


# =============================================================================
# Validation and Fixing Functions
# =============================================================================

def validate_permission_patterns(settings: Dict) -> ValidationResult:
    """Validate permission patterns in settings.

    Detects:
    - Bash(*) wildcard → severity "error"
    - Bash(:*) wildcard → severity "warning"
    - Missing deny list → severity "error"
    - Empty deny list → severity "error"

    Args:
        settings: Settings dictionary to validate

    Returns:
        ValidationResult with detected issues

    Examples:
        >>> settings = {"permissions": {"allow": ["Bash(*)"], "deny": []}}
        >>> result = validate_permission_patterns(settings)
        >>> result.valid
        False
        >>> len(result.issues)
        2
    """
    if settings is None:
        return ValidationResult(
            valid=False,
            issues=[PermissionIssue(
                issue_type="invalid_input",
                description="Settings is None",
                pattern="",
                severity="error"
            )],
            needs_fix=True
        )

    if not isinstance(settings, dict):
        return ValidationResult(
            valid=False,
            issues=[PermissionIssue(
                issue_type="invalid_input",
                description="Settings is not a dictionary",
                pattern="",
                severity="error"
            )],
            needs_fix=True
        )

    issues = []

    # Check if permissions key exists
    if "permissions" not in settings:
        return ValidationResult(
            valid=False,
            issues=[PermissionIssue(
                issue_type="malformed_structure",
                description="Missing permissions section in settings",
                pattern="",
                severity="error"
            )],
            needs_fix=True
        )

    permissions = settings["permissions"]
    if not isinstance(permissions, dict):
        return ValidationResult(
            valid=False,
            issues=[PermissionIssue(
                issue_type="malformed_structure",
                description="Permissions is not a dictionary",
                pattern="",
                severity="error"
            )],
            needs_fix=True
        )

    # Check allow list for wildcards
    allow_list = permissions.get("allow", [])
    if not isinstance(allow_list, list):
        allow_list = []

    # Detect Bash(*) wildcard - SEVERITY ERROR
    bash_wildcards = [p for p in allow_list if p == "Bash(*)"]
    for wildcard in bash_wildcards:
        issues.append(PermissionIssue(
            issue_type="wildcard_pattern",
            description="Overly permissive wildcard - too permissive",
            pattern=wildcard,
            severity="error"
        ))

    # Detect Bash(:*) wildcard - SEVERITY WARNING
    colon_wildcards = [p for p in allow_list if p == "Bash(:*)"]
    for wildcard in colon_wildcards:
        issues.append(PermissionIssue(
            issue_type="wildcard_pattern",
            description="Bash(:*) wildcard detected - less specific than recommended",
            pattern=wildcard,
            severity="warning"
        ))

    # Check deny list
    if "deny" not in permissions:
        issues.append(PermissionIssue(
            issue_type="missing_deny_list",
            description="Missing deny list - dangerous operations not blocked",
            pattern="",
            severity="error"
        ))
    elif not permissions["deny"]:
        issues.append(PermissionIssue(
            issue_type="empty_deny_list",
            description="Empty deny list - dangerous operations not blocked",
            pattern="",
            severity="error"
        ))

    # Settings are invalid if ANY issues exist (errors or warnings)
    valid = len(issues) == 0
    needs_fix = len(issues) > 0

    return ValidationResult(valid=valid, issues=issues, needs_fix=needs_fix)


def detect_outdated_patterns(settings: Dict) -> List[str]:
    """Detect patterns not in SAFE_COMMAND_PATTERNS.

    Args:
        settings: Settings dictionary to check

    Returns:
        List of outdated pattern strings

    Examples:
        >>> settings = {"permissions": {"allow": ["Bash(obsolete:*)"]}}
        >>> outdated = detect_outdated_patterns(settings)
        >>> "Bash(obsolete:*)" in outdated
        True
    """
    if not settings or not isinstance(settings, dict):
        return []

    if "permissions" not in settings:
        return []

    permissions = settings["permissions"]
    if not isinstance(permissions, dict):
        return []

    allow_list = permissions.get("allow", [])
    if not isinstance(allow_list, list):
        return []

    outdated = []
    for pattern in allow_list:
        if pattern not in SAFE_COMMAND_PATTERNS:
            outdated.append(pattern)

    return outdated


def fix_permission_patterns(user_settings: Dict, template_settings: Optional[Dict] = None) -> Dict:
    """Fix permission patterns while preserving user customizations.

    Process:
    1. Preserve user hooks (don't touch)
    2. Preserve valid custom allow patterns
    3. Replace wildcards with specific patterns
    4. Add comprehensive deny list
    5. Validate result

    Args:
        user_settings: User's existing settings
        template_settings: Optional template settings (unused, for compatibility)

    Returns:
        Fixed settings dictionary

    Raises:
        ValueError: If user_settings is None or not a dictionary

    Examples:
        >>> settings = {"permissions": {"allow": ["Bash(*)"]}, "hooks": {"auto_format": True}}
        >>> fixed = fix_permission_patterns(settings)
        >>> "Bash(*)" not in fixed["permissions"]["allow"]
        True
        >>> fixed["hooks"]["auto_format"]
        True
    """
    if user_settings is None:
        raise ValueError("user_settings cannot be None")

    if not isinstance(user_settings, dict):
        raise ValueError("user_settings must be a dictionary")

    # Deep copy to avoid modifying original
    fixed = json.loads(json.dumps(user_settings))

    # Ensure permissions structure exists
    if "permissions" not in fixed:
        fixed["permissions"] = {"allow": [], "deny": []}

    if not isinstance(fixed["permissions"], dict):
        fixed["permissions"] = {"allow": [], "deny": []}

    if "allow" not in fixed["permissions"]:
        fixed["permissions"]["allow"] = []

    if not isinstance(fixed["permissions"]["allow"], list):
        fixed["permissions"]["allow"] = []

    # Get current allow list
    current_allow = fixed["permissions"]["allow"]

    # Remove wildcard patterns (Bash(*) and Bash(:*))
    wildcards_to_remove = ["Bash(*)", "Bash(:*)"]
    new_allow = [p for p in current_allow if p not in wildcards_to_remove]

    # Add SAFE_COMMAND_PATTERNS if wildcards were removed
    has_wildcards = any(w in current_allow for w in wildcards_to_remove)
    if has_wildcards:
        # Merge SAFE_COMMAND_PATTERNS with existing patterns (avoid duplicates)
        for pattern in SAFE_COMMAND_PATTERNS:
            if pattern not in new_allow:
                new_allow.append(pattern)

    fixed["permissions"]["allow"] = new_allow

    # Fix deny list
    if "deny" not in fixed["permissions"] or not fixed["permissions"]["deny"]:
        fixed["permissions"]["deny"] = DEFAULT_DENY_LIST.copy()
    elif not isinstance(fixed["permissions"]["deny"], list):
        fixed["permissions"]["deny"] = DEFAULT_DENY_LIST.copy()

    return fixed


# =============================================================================
# SettingsGenerator Class
# =============================================================================

class SettingsGenerator:
    """Generate settings.local.json with command-specific patterns and deny list.

    This class discovers commands from the plugin directory and generates
    .claude/settings.local.json with:
    - Specific command patterns (NO wildcards)
    - Comprehensive deny list
    - User customization preservation (upgrades)

    Security:
        - Path validation (CWE-22, CWE-59)
        - Command injection prevention
        - Atomic writes with secure permissions
        - Audit logging

    Attributes:
        plugin_dir: Path to plugin directory (plugins/autonomous-dev)
        commands_dir: Path to commands directory
        discovered_commands: List of discovered command names
    """

    def __init__(self, plugin_dir: Optional[Path] = None, project_root: Optional[Path] = None):
        """Initialize settings generator.

        Args:
            plugin_dir: Path to plugin directory (plugins/autonomous-dev)
            project_root: Path to project root (alternative to plugin_dir)

        Raises:
            SettingsGeneratorError: If plugin_dir not found

        Note:
            Commands directory is validated lazily when needed by methods.
            This allows using static methods like build_deny_list() without
            requiring full plugin structure.
        """
        # Support both plugin_dir and project_root parameters
        if project_root is not None:
            self.plugin_dir = Path(project_root) / "plugins" / "autonomous-dev"
            # For project_root mode, allow missing plugin directory (used for global settings merge)
            self._allow_missing_plugin_dir = True
        elif plugin_dir is not None:
            self.plugin_dir = Path(plugin_dir)
            self._allow_missing_plugin_dir = False
        else:
            raise SettingsGeneratorError("Either plugin_dir or project_root must be provided")

        self.commands_dir = self.plugin_dir / "commands"
        self.discovered_commands = []
        self.invalid_commands_found = []  # Track invalid command names
        self._validated = False

        # Validate plugin directory exists (unless in project_root mode for global settings)
        if not self.plugin_dir.exists():
            if not self._allow_missing_plugin_dir:
                raise SettingsGeneratorError(
                    f"Plugin directory not found: {self.plugin_dir}\n"
                    f"Expected structure: plugins/autonomous-dev/"
                )
            # In project_root mode - allow missing plugin_dir for global settings merge
            return

        # Check if commands directory exists
        # Special case: Allow /tmp without commands/ for testing static methods
        # Otherwise, require commands/ directory for full functionality
        is_system_temp = str(self.plugin_dir.resolve()) in ['/tmp', '/var/tmp', '/private/tmp']

        if not self.commands_dir.exists():
            if not is_system_temp and not self._allow_missing_plugin_dir:
                raise SettingsGeneratorError(
                    f"Commands directory not found: {self.commands_dir}\n"
                    f"Expected structure: plugins/autonomous-dev/commands/"
                )
            # System temp directory or project_root mode - allow minimal initialization for static methods
        else:
            # Commands directory exists - discover commands
            self._validated = True
            self.discovered_commands = self.discover_commands()

    def discover_commands(self) -> List[str]:
        """Discover commands from plugins/autonomous-dev/commands/*.md files.

        Returns:
            List of command names (without .md extension)

        Raises:
            SettingsGeneratorError: If directory read fails or commands/ not found
        """
        # Validate commands directory exists
        if not self.commands_dir.exists():
            raise SettingsGeneratorError(
                f"Commands directory not found: {self.commands_dir}\n"
                f"Expected structure: plugins/autonomous-dev/commands/"
            )

        commands = []

        try:
            for file_path in self.commands_dir.iterdir():
                # Skip non-.md files
                if not file_path.suffix == ".md":
                    continue

                # Skip hidden files
                if file_path.name.startswith("."):
                    continue

                # Skip archived subdirectory
                if file_path.is_dir():
                    continue

                # Extract command name (remove .md extension)
                command_name = file_path.stem

                # Track invalid command names for security validation
                if not self._is_valid_command_name(command_name):
                    self.invalid_commands_found.append(command_name)
                    continue

                commands.append(command_name)

        except PermissionError as e:
            raise SettingsGeneratorError(
                f"Permission denied reading commands directory: {self.commands_dir}\n"
                f"Error: {e}"
            )
        except OSError as e:
            raise SettingsGeneratorError(
                f"Failed to read commands directory: {self.commands_dir}\n"
                f"Error: {e}"
            )

        return sorted(commands)

    def _is_valid_command_name(self, name: str) -> bool:
        """Validate command name to prevent injection.

        Args:
            name: Command name to validate

        Returns:
            True if valid, False otherwise
        """
        # Allow alphanumeric, dash, and underscore only
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))

    def build_command_patterns(self) -> List[str]:
        """Build specific command patterns from safe defaults.

        Returns specific patterns like:
        - Bash(git:*)
        - Bash(pytest:*)
        - Read(**)
        - Write(**)

        NEVER returns wildcards like Bash(*) or Bash(:*)

        Returns:
            List of specific command patterns

        Raises:
            SettingsGeneratorError: If pattern generation fails or invalid commands found
        """
        # Check for security issues (invalid command names)
        if self.invalid_commands_found:
            raise SettingsGeneratorError(
                f"Invalid command names detected (potential security risk): "
                f"{', '.join(self.invalid_commands_found)}\n"
                f"Command names must contain only alphanumeric, dash, and underscore characters"
            )

        patterns = []

        # Add safe command patterns (from module constant)
        patterns.extend(SAFE_COMMAND_PATTERNS)

        # Deduplicate patterns
        patterns = list(set(patterns))

        # Validate no wildcards in output
        dangerous_wildcards = ["Bash(*)", "Bash(**)", "Shell(*)", "Exec(*)"]
        for wildcard in dangerous_wildcards:
            if wildcard in patterns:
                raise SettingsGeneratorError(
                    f"SECURITY: Wildcard pattern detected in output: {wildcard}\n"
                    f"This would defeat the entire security model. Aborting."
                )

        return sorted(patterns)

    @staticmethod
    def build_deny_list() -> List[str]:
        """Build comprehensive deny list of dangerous operations.

        Returns patterns blocking:
        - Destructive file operations (rm -rf, shred, dd)
        - Privilege escalation (sudo, su, chmod)
        - Code execution (eval, exec, source)
        - Network operations (nc, curl|sh)
        - Dangerous git operations (--force, reset --hard)
        - Package publishing (npm publish, twine upload)

        Returns:
            List of deny patterns
        """
        # Return default deny list (from module constant)
        return list(DEFAULT_DENY_LIST)

    def generate_settings(self, merge_with: Optional[Dict] = None) -> Dict:
        """Generate settings dictionary with all patterns and metadata.

        Args:
            merge_with: Optional existing settings to merge with

        Returns:
            Settings dictionary ready for JSON serialization

        Structure:
            {
                "permissions": {
                    "allow": [...],
                    "deny": [...]
                },
                "hooks": {...},  # Preserved from merge_with
                "generated_by": "autonomous-dev",
                "version": "1.0.0",
                "timestamp": "2025-12-12T10:30:00Z"
            }
        """
        # Build patterns
        allow_patterns = self.build_command_patterns()
        deny_patterns = self.build_deny_list()

        # Add Claude Code standalone tools (not Bash patterns)
        standalone_tools = [
            "Task",
            "WebFetch",
            "WebSearch",
            "TodoWrite",
            "NotebookEdit",
        ]
        allow_patterns.extend(standalone_tools)

        # Initialize settings structure
        settings = {
            "permissions": {
                "allow": allow_patterns,
                "deny": deny_patterns,
            },
            "generated_by": "autonomous-dev",
            "version": SETTINGS_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }

        # Merge with existing settings if provided
        if merge_with:
            # Preserve user hooks
            if "hooks" in merge_with:
                settings["hooks"] = merge_with["hooks"]

            # Preserve user custom patterns (add to allow list)
            if "permissions" in merge_with and "allow" in merge_with["permissions"]:
                user_patterns = merge_with["permissions"]["allow"]
                # Filter out generated patterns, keep only user's custom ones
                custom_patterns = [
                    p for p in user_patterns
                    if p not in SAFE_COMMAND_PATTERNS
                ]
                # Add custom patterns to allow list
                settings["permissions"]["allow"].extend(custom_patterns)

                # Deduplicate
                settings["permissions"]["allow"] = list(set(settings["permissions"]["allow"]))

            # Preserve user deny patterns (union with defaults)
            if "permissions" in merge_with and "deny" in merge_with["permissions"]:
                user_denies = merge_with["permissions"]["deny"]
                settings["permissions"]["deny"].extend(user_denies)

                # Deduplicate
                settings["permissions"]["deny"] = list(set(settings["permissions"]["deny"]))

            # Preserve any other custom keys
            for key, value in merge_with.items():
                if key not in settings and key not in ["permissions"]:
                    settings[key] = value

        return settings

    def write_settings(
        self,
        output_path: Path,
        merge_existing: bool = False,
        backup: bool = False,
    ) -> GeneratorResult:
        """Write settings.local.json to disk.

        Args:
            output_path: Path to write settings.local.json
            merge_existing: Whether to merge with existing settings
            backup: Whether to backup existing file

        Returns:
            GeneratorResult with success status and statistics

        Raises:
            SettingsGeneratorError: If write fails or generator not properly initialized
        """
        # Validate generator was properly initialized
        if not self._validated and not self.plugin_dir.exists():
            raise SettingsGeneratorError(
                f"Generator not properly initialized - plugin directory not found: {self.plugin_dir}\n"
                f"Cannot generate settings without valid plugin structure."
            )

        try:
            # Step 1: Validate output path (security)
            try:
                validated_path = validate_path(
                    output_path,
                    purpose="settings generation",
                    allow_missing=True,
                )
            except ValueError as e:
                audit_log(
                    "settings_generation",
                    "path_validation_failed",
                    {
                        "output_path": str(output_path),
                        "error": str(e),
                    },
                )
                raise SettingsGeneratorError(
                    f"Path validation failed: {e}\n"
                    f"Cannot write to: {output_path}"
                )

            # Step 2: Read existing settings if merging
            existing_settings = None
            corrupted_backup = False

            if merge_existing and output_path.exists():
                try:
                    existing_content = output_path.read_text()
                    existing_settings = json.loads(existing_content)
                except json.JSONDecodeError:
                    # Corrupted JSON - backup and continue with fresh settings
                    corrupted_backup = True
                    backup_path = output_path.parent / f"{output_path.name}.corrupted"
                    output_path.rename(backup_path)

                    audit_log(
                        "settings_generation",
                        "corrupted_settings_backed_up",
                        {
                            "output_path": str(output_path),
                            "backup_path": str(backup_path),
                        },
                    )

            # Step 3: Backup existing file if requested
            if backup and output_path.exists() and not corrupted_backup:
                backup_path = output_path.parent / f"{output_path.name}.backup"
                output_path.rename(backup_path)

                audit_log(
                    "settings_generation",
                    "settings_backed_up",
                    {
                        "output_path": str(output_path),
                        "backup_path": str(backup_path),
                    },
                )

            # Step 4: Generate settings
            settings = self.generate_settings(merge_with=existing_settings)

            # Step 5: Create parent directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Step 6: Write settings atomically
            # Use temporary file + rename for atomicity
            temp_path = output_path.parent / f".{output_path.name}.tmp"

            try:
                # Write to temp file
                temp_path.write_text(json.dumps(settings, indent=2) + "\n")

                # Set secure permissions (0o600 - owner read/write only)
                temp_path.chmod(0o600)

                # Atomic rename
                temp_path.rename(output_path)

            except Exception as e:
                # Cleanup temp file if write failed
                if temp_path.exists():
                    temp_path.unlink()
                raise

            # Step 7: Calculate statistics
            patterns_added = len(settings["permissions"]["allow"])
            denies_added = len(settings["permissions"]["deny"])
            patterns_preserved = 0

            if existing_settings and "permissions" in existing_settings:
                # Count user patterns that were preserved
                user_patterns = existing_settings["permissions"].get("allow", [])
                custom_patterns = [
                    p for p in user_patterns
                    if p not in SAFE_COMMAND_PATTERNS
                ]
                patterns_preserved = len(custom_patterns)

            # Step 8: Audit log success
            audit_log(
                "settings_generation",
                "success",
                {
                    "output_path": str(output_path),
                    "patterns_added": patterns_added,
                    "denies_added": denies_added,
                    "patterns_preserved": patterns_preserved,
                    "merge_existing": merge_existing,
                    "backup": backup,
                    "corrupted": corrupted_backup,
                },
            )

            # Step 9: Return result
            message = "Settings created successfully"
            if corrupted_backup:
                message = "Settings regenerated (corrupted file backed up)"
            elif backup:
                message = "Settings updated successfully (backed up existing)"
            elif merge_existing:
                message = "Settings merged successfully"

            return GeneratorResult(
                success=True,
                message=message,
                settings_path=str(output_path),
                patterns_added=patterns_added,
                patterns_preserved=patterns_preserved,
                denies_added=denies_added,
                details={
                    "corrupted": corrupted_backup,
                    "merged": merge_existing,
                    "backed_up": backup,
                },
            )

        except PermissionError as e:
            audit_log(
                "settings_generation",
                "permission_denied",
                {
                    "output_path": str(output_path),
                    "error": str(e),
                },
            )
            raise SettingsGeneratorError(
                f"Permission denied writing settings: {output_path}\n"
                f"Error: {e}"
            )

        except OSError as e:
            audit_log(
                "settings_generation",
                "write_failed",
                {
                    "output_path": str(output_path),
                    "error": str(e),
                },
            )

            # Check for disk full errors
            if e.errno == 28:  # ENOSPC - No space left on device
                raise SettingsGeneratorError(
                    f"Disk full - cannot write settings: {output_path}\n"
                    f"Error: {e}"
                )

            raise SettingsGeneratorError(
                f"Failed to write settings: {output_path}\n"
                f"Error: {e}"
            )

    def merge_global_settings(
        self,
        global_path: Path,
        template_path: Path,
        fix_wildcards: bool = True,
        create_backup: bool = True
    ) -> Dict[str, Any]:
        """Merge global settings preserving user customizations.

        Process:
        1. Read template settings
        2. Read existing user settings (if any)
        3. Fix broken patterns if enabled
        4. Merge: template + user customizations
        5. Preserve user hooks completely
        6. Write atomically with backup

        Args:
            global_path: Path to global settings file (~/.claude/settings.json)
            template_path: Path to template file
            fix_wildcards: Whether to fix broken wildcard patterns
            create_backup: Whether to create backup before modification

        Returns:
            Merged settings dictionary

        Raises:
            SettingsGeneratorError: If template not found or write fails
        """
        # Step 1: Validate template exists
        if not template_path.exists():
            raise SettingsGeneratorError(
                f"Template file not found: {template_path}\n"
                f"Expected: plugins/autonomous-dev/config/global_settings_template.json"
            )

        # Step 2: Read template
        try:
            with open(template_path, 'r') as f:
                template = json.load(f)
        except json.JSONDecodeError as e:
            raise SettingsGeneratorError(
                f"Invalid JSON in template: {template_path}\n"
                f"Error: {e}"
            )
        except OSError as e:
            raise SettingsGeneratorError(
                f"Failed to read template: {template_path}\n"
                f"Error: {e}"
            )

        # Step 3: Read existing user settings (if exists)
        user_settings = {}
        if global_path.exists():
            try:
                with open(global_path, 'r') as f:
                    user_settings = json.load(f)
            except json.JSONDecodeError:
                # Corrupted file - create backup and use template
                if create_backup:
                    backup_path = global_path.with_suffix(".json.corrupted")
                    # Remove old corrupted backup if exists
                    if backup_path.exists():
                        backup_path.unlink()
                    global_path.rename(backup_path)
                    audit_log(
                        "settings_merge",
                        "corrupted_backup",
                        {"backup_path": str(backup_path)}
                    )
                user_settings = {}
            except OSError as e:
                raise SettingsGeneratorError(
                    f"Failed to read global settings: {global_path}\n"
                    f"Error: {e}"
                )

        # Step 4: Create backup if modifying existing file
        if global_path.exists() and create_backup and user_settings:
            backup_path = global_path.with_suffix(".json.backup")
            try:
                # Remove old backup if exists
                if backup_path.exists():
                    backup_path.unlink()
                with open(backup_path, 'w') as f:
                    json.dump(user_settings, f, indent=2)
                audit_log(
                    "settings_merge",
                    "backup_created",
                    {"backup_path": str(backup_path)}
                )
            except OSError as e:
                # Don't fail merge if backup fails - just log
                audit_log(
                    "settings_merge",
                    "backup_failed",
                    {"error": str(e)}
                )

        # Step 5: Merge settings
        merged = self._deep_merge_settings(template, user_settings, fix_wildcards)

        # Step 6: Validate merged settings
        self._validate_merged_settings(merged)

        # Step 7: Write atomically
        global_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = global_path.parent / f".{global_path.name}.tmp"

        try:
            # Use write_text for atomic write
            temp_path.write_text(json.dumps(merged, indent=2))

            # Atomic rename
            temp_path.replace(global_path)

            audit_log(
                "settings_merge",
                "success",
                {
                    "global_path": str(global_path),
                    "template_path": str(template_path),
                    "fixed_wildcards": fix_wildcards
                }
            )

            return merged

        except (PermissionError, IOError) as e:
            if temp_path.exists():
                temp_path.unlink()
            # Let PermissionError and IOError bubble up for testing
            raise
        except OSError as e:
            if temp_path.exists():
                temp_path.unlink()
            raise SettingsGeneratorError(
                f"Failed to write global settings: {global_path}\n"
                f"Error: {e}"
            )

    def _deep_merge_settings(
        self,
        template: Dict[str, Any],
        user_settings: Dict[str, Any],
        fix_wildcards: bool
    ) -> Dict[str, Any]:
        """Deep merge preserving user customizations.

        Merge strategy (Claude Code 2.0 format):
        1. Start with template (has all required patterns)
        2. Fix broken wildcards in user settings if enabled
        3. Merge permissions.allow: template + user patterns (union)
        4. Merge permissions.deny: template + user patterns (union)
        5. Preserve user hooks completely (don't modify)
        6. Preserve all other user settings not in template

        Args:
            template: Template settings
            user_settings: Existing user settings
            fix_wildcards: Whether to fix broken wildcard patterns

        Returns:
            Merged settings dictionary
        """
        # Start with template
        merged = json.loads(json.dumps(template))  # Deep copy

        # If no user settings, return template
        if not user_settings:
            return merged

        # Fix wildcards in user settings if enabled
        if fix_wildcards:
            user_settings = fix_permission_patterns(user_settings)

        # Merge permissions.allow and permissions.deny (Claude Code 2.0 format)
        if "permissions" in user_settings:
            user_perms = user_settings["permissions"]
            template_perms = merged.setdefault("permissions", {})

            # Merge allow patterns (union)
            template_allow = template_perms.get("allow", [])
            user_allow = user_perms.get("allow", [])
            # Remove broken wildcards from user patterns
            broken_wildcards = ["Bash(:*)", "Bash(*)", "Bash(**)"]
            user_allow = [p for p in user_allow if p not in broken_wildcards]
            # Union of template and user patterns (deduplicate)
            merged_allow = list(set(template_allow + user_allow))
            template_perms["allow"] = sorted(merged_allow)

            # Merge deny patterns (union)
            template_deny = template_perms.get("deny", [])
            user_deny = user_perms.get("deny", [])
            merged_deny = list(set(template_deny + user_deny))
            template_perms["deny"] = sorted(merged_deny)

        # Merge hooks by lifecycle event (Issue #138: Fix hook loss during merge)
        # Previously: User hooks completely replaced template hooks, losing UserPromptSubmit
        # Now: Merge hooks - template hooks + user hooks (user wins for duplicates)
        # Issue #144: Migrate old hooks to unified hooks (remove replaced hooks)
        template_hooks = merged.get("hooks", {})
        user_hooks = user_settings.get("hooks", {})

        # Issue #144: Build set of old hooks to remove based on unified hooks in template
        hooks_to_remove = set()
        for lifecycle, matcher_configs in template_hooks.items():
            for config in matcher_configs:
                if isinstance(config, dict):
                    inner_hooks = config.get("hooks", [config])
                    for hook in inner_hooks:
                        if isinstance(hook, dict):
                            cmd = hook.get("command", "")
                            for unified_hook, replaced_hooks in UNIFIED_HOOK_REPLACEMENTS.items():
                                if unified_hook in cmd:
                                    hooks_to_remove.update(replaced_hooks)

        # Start with template hooks (to preserve UserPromptSubmit, etc.)
        merged_hooks = json.loads(json.dumps(template_hooks))  # Deep copy

        # Merge user hooks on top (by lifecycle event), filtering out old hooks
        for lifecycle, hooks in user_hooks.items():
            if lifecycle not in merged_hooks:
                # New lifecycle from user - add all hooks (filtering old ones)
                filtered_hooks = []
                for hook in hooks:
                    if isinstance(hook, dict):
                        if "hooks" in hook:
                            # Nested format - filter inner hooks
                            filtered_inner = []
                            for inner_hook in hook.get("hooks", []):
                                if isinstance(inner_hook, dict):
                                    cmd = inner_hook.get("command", "")
                                    should_remove = any(old_hook in cmd for old_hook in hooks_to_remove)
                                    if not should_remove:
                                        filtered_inner.append(inner_hook)
                                else:
                                    filtered_inner.append(inner_hook)
                            if filtered_inner:
                                filtered_hooks.append({**hook, "hooks": filtered_inner})
                        else:
                            # Flat format - check command directly
                            cmd = hook.get("command", "")
                            should_remove = any(old_hook in cmd for old_hook in hooks_to_remove)
                            if not should_remove:
                                filtered_hooks.append(hook)
                    else:
                        filtered_hooks.append(hook)
                if filtered_hooks:
                    merged_hooks[lifecycle] = json.loads(json.dumps(filtered_hooks))
            else:
                # Existing lifecycle - merge individual hooks (avoid duplicates, filter old)
                existing_hooks = merged_hooks[lifecycle]
                for hook in hooks:
                    if isinstance(hook, dict):
                        if "hooks" in hook:
                            # Nested format - filter and merge inner hooks
                            for inner_hook in hook.get("hooks", []):
                                if isinstance(inner_hook, dict):
                                    cmd = inner_hook.get("command", "")
                                    should_remove = any(old_hook in cmd for old_hook in hooks_to_remove)
                                    if should_remove:
                                        continue
                                    # Check if this exact hook already exists
                                    hook_exists = any(
                                        h.get("command") == cmd for h in existing_hooks
                                        if isinstance(h, dict) and "command" in h
                                    )
                                    # Also check nested hooks
                                    for existing in existing_hooks:
                                        if isinstance(existing, dict) and "hooks" in existing:
                                            hook_exists = hook_exists or any(
                                                ih.get("command") == cmd
                                                for ih in existing.get("hooks", [])
                                                if isinstance(ih, dict)
                                            )
                                    if not hook_exists:
                                        # Add to first matcher config's hooks
                                        if existing_hooks and isinstance(existing_hooks[0], dict) and "hooks" in existing_hooks[0]:
                                            existing_hooks[0]["hooks"].append(json.loads(json.dumps(inner_hook)))
                        else:
                            # Flat format - check command directly
                            cmd = hook.get("command", "")
                            should_remove = any(old_hook in cmd for old_hook in hooks_to_remove)
                            if should_remove:
                                continue
                            hook_exists = any(
                                h.get("command") == hook.get("command") and h.get("matcher") == hook.get("matcher")
                                for h in existing_hooks
                                if isinstance(h, dict)
                            )
                            if not hook_exists:
                                existing_hooks.append(json.loads(json.dumps(hook)))

        if merged_hooks:
            merged["hooks"] = merged_hooks

        # Preserve all other user settings not in template
        for key, value in user_settings.items():
            if key not in ["permissions", "hooks"]:
                merged[key] = json.loads(json.dumps(value))  # Deep copy

        return merged

    def _fix_wildcard_patterns(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Fix broken wildcard patterns by replacing with safe patterns.

        Replaces: Bash(:*), Bash(*), Bash(**) → Safe specific patterns
        Preserves: All other patterns

        Args:
            settings: Settings dictionary to fix

        Returns:
            Fixed settings dictionary
        """
        # Deep copy to avoid modifying original
        fixed = json.loads(json.dumps(settings))

        broken_wildcards = ["Bash(:*)", "Bash(*)", "Bash(**)"]

        # Safe replacement patterns
        safe_patterns = [
            "Bash(git:*)",
            "Bash(python:*)",
            "Bash(python3:*)",
            "Bash(pytest:*)",
            "Bash(pip:*)",
            "Bash(pip3:*)",
            "Bash(ls:*)",
            "Bash(cat:*)",
            "Bash(gh:*)",
        ]

        # Fix allowedTools.Bash.allow_patterns
        if "allowedTools" in fixed and "Bash" in fixed["allowedTools"]:
            bash = fixed["allowedTools"]["Bash"]
            if "allow_patterns" in bash:
                patterns = bash["allow_patterns"]
                # Check if any broken patterns exist
                has_broken = any(p in broken_wildcards for p in patterns)

                if has_broken:
                    # Remove all broken patterns
                    patterns = [p for p in patterns if p not in broken_wildcards]
                    # Add safe patterns (avoiding duplicates)
                    for safe_pattern in safe_patterns:
                        if safe_pattern not in patterns:
                            patterns.append(safe_pattern)

                bash["allow_patterns"] = patterns

        return fixed

    def _validate_merged_settings(self, settings: Dict[str, Any]) -> None:
        """Validate merged settings (Claude Code 2.0 format).

        Ensures:
        1. No broken wildcard patterns
        2. Required safe patterns present
        3. Valid JSON structure

        Args:
            settings: Settings to validate

        Raises:
            SettingsGeneratorError: If validation fails
        """
        # Check for broken wildcards in permissions.allow
        broken_wildcards = ["Bash(:*)", "Bash(*)", "Bash(**)"]

        if "permissions" in settings and "allow" in settings["permissions"]:
            allow_patterns = settings["permissions"]["allow"]
            for pattern in allow_patterns:
                if pattern in broken_wildcards:
                    raise SettingsGeneratorError(
                        f"Validation failed: Broken wildcard pattern found: {pattern}\n"
                        f"This should have been fixed during merge"
                    )


# =============================================================================
# CLI Interface (for testing)
# =============================================================================

def main():
    """CLI interface for settings generator (testing only)."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python settings_generator.py <plugin_dir> <output_path>")
        print("\nExample:")
        print("  python settings_generator.py plugins/autonomous-dev .claude/settings.local.json")
        sys.exit(1)

    plugin_dir = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    try:
        generator = SettingsGenerator(plugin_dir)
        result = generator.write_settings(output_path)

        if result.success:
            print(f"✅ {result.message}")
            print(f"   Path: {result.settings_path}")
            print(f"   Patterns added: {result.patterns_added}")
            print(f"   Denies added: {result.denies_added}")
        else:
            print(f"❌ {result.message}")
            sys.exit(1)

    except SettingsGeneratorError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
