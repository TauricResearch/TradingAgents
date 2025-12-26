"""
Settings merger for merging settings.local.json with template configuration.

This module provides functionality to merge template settings (e.g., PreToolUse hooks)
with user's existing settings.local.json while preserving user customizations.

Security Features:
- Path validation (CWE-22: Path Traversal)
- Symlink rejection (CWE-59: Improper Link Resolution)
- Atomic writes with secure permissions (0o600)
- Audit logging for all operations

Design Pattern:
- Deep merge: Nested dictionaries are merged recursively
- Hooks merge by lifecycle event (PreToolUse, PostToolUse, etc.)
- User customizations preserved (permissions, custom config)
- Duplicate hooks avoided

Usage:
    merger = SettingsMerger(project_root="/path/to/project")
    result = merger.merge_settings(
        template_path=Path("templates/settings.local.json"),
        user_path=Path(".claude/settings.local.json"),
        write_result=True
    )

See Also:
    - docs/LIBRARIES.md section 29 for API documentation
    - tests/unit/lib/test_settings_merger.py for test cases
"""

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Import security utilities
try:
    from autonomous_dev.lib.security_utils import validate_path, audit_log
except ImportError:
    # Fallback for direct script execution
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from security_utils import validate_path, audit_log


# Issue #144: Migration mapping from unified hooks to replaced hooks
# When a unified hook is added, remove the old hooks it replaces
UNIFIED_HOOK_REPLACEMENTS = {
    "unified_pre_tool.py": [
        "pre_tool_use.py",
        "enforce_implementation_workflow.py",
        "batch_permission_approver.py",
    ],
    "unified_prompt_validator.py": [
        "detect_feature_request.py",
    ],
    "unified_post_tool.py": [
        "post_tool_use_error_capture.py",
    ],
    "unified_session_tracker.py": [
        "session_tracker.py",
        "log_agent_completion.py",
        "auto_update_project_progress.py",
    ],
    "unified_git_automation.py": [
        "auto_git_workflow.py",
    ],
}


@dataclass
class MergeResult:
    """Result of settings merge operation.

    Attributes:
        success: Whether merge succeeded
        message: Human-readable result message
        settings_path: Path to merged settings file (None if merge failed)
        hooks_added: Number of hooks added from template
        hooks_preserved: Number of existing hooks preserved
        hooks_migrated: Number of old hooks removed during migration
        details: Additional result details (errors, warnings, etc.)
    """

    success: bool
    message: str
    settings_path: Optional[str] = None
    hooks_added: int = 0
    hooks_preserved: int = 0
    hooks_migrated: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


class SettingsMerger:
    """Merge settings.local.json with template configuration.

    This class handles merging template settings (e.g., PreToolUse hooks) with
    user's existing settings while preserving user customizations.

    Security:
        - Validates all paths against project root
        - Rejects symlinks and path traversal attempts
        - Atomic writes with secure permissions (0o600)
        - Audit logging for all operations

    Attributes:
        project_root: Project root directory for path validation
    """

    def __init__(self, project_root: str):
        """Initialize settings merger.

        Args:
            project_root: Project root directory for path validation
        """
        self.project_root = Path(project_root)

    def merge_settings(
        self, template_path: Path, user_path: Path, write_result: bool = True
    ) -> MergeResult:
        """Merge template settings with user settings.

        This method performs a deep merge of template settings with existing
        user settings, with special handling for hooks:

        1. Read template and user settings (if exists)
        2. Deep merge dictionaries (nested objects preserved)
        3. Merge hooks by lifecycle event (avoid duplicates)
        4. Atomic write to user path (if write_result=True)

        Args:
            template_path: Path to template settings.local.json
            user_path: Path to user settings.local.json
            write_result: Whether to write merged settings (False for dry-run)

        Returns:
            MergeResult with success status, counts, and details

        Security:
            - Validates both paths against project root
            - Rejects symlinks and path traversal attempts
            - Audit logs all operations
        """
        try:
            # Step 1: Validate paths (security)
            # Validate template path
            try:
                validate_path(
                    template_path,
                    purpose="template settings",
                    allow_missing=False,
                )
            except ValueError as e:
                audit_log(
                    "settings_merge",
                    "template_validation_failed",
                    {
                        "template_path": str(template_path),
                        "error": str(e),
                    },
                )
                return MergeResult(
                    success=False,
                    message=f"Template path validation failed: {e}",
                    details={"error": str(e)},
                )

            # Check if template exists
            if not template_path.exists():
                audit_log(
                    "settings_merge",
                    "template_not_found",
                    {
                        "template_path": str(template_path),
                    },
                )
                return MergeResult(
                    success=False,
                    message=f"Template settings not found: {template_path}",
                    details={"error": "Template file does not exist"},
                )

            # Validate user path (allow missing since we may create it)
            try:
                validate_path(
                    user_path,
                    purpose="user settings",
                    allow_missing=True,
                )
            except ValueError as e:
                audit_log(
                    "settings_merge",
                    "user_path_validation_failed",
                    {
                        "user_path": str(user_path),
                        "error": str(e),
                    },
                )
                return MergeResult(
                    success=False,
                    message=f"User path validation failed: {e}",
                    details={"error": str(e)},
                )

            # Step 2: Read template settings
            template_data = self._read_json(template_path)
            if template_data is None:
                audit_log(
                    "settings_merge",
                    "template_parse_failed",
                    {
                        "template_path": str(template_path),
                    },
                )
                return MergeResult(
                    success=False,
                    message=f"Failed to parse template JSON: {template_path}",
                    details={"error": "Invalid JSON in template file"},
                )

            # Step 3: Read existing user settings (if exists)
            user_data = {}
            if user_path.exists():
                user_data = self._read_json(user_path)
                if user_data is None:
                    audit_log(
                        "settings_merge",
                        "user_settings_parse_failed",
                        {
                            "user_path": str(user_path),
                        },
                    )
                    return MergeResult(
                        success=False,
                        message=f"Failed to parse user settings JSON: {user_path}",
                        details={"error": "Invalid JSON in user settings file"},
                    )

            # Step 4: Merge dictionaries
            merged_data = self._merge_dicts(user_data, template_data)

            # Step 5: Merge hooks (track counts, migrate old hooks to unified)
            merged_hooks, hooks_added, hooks_preserved, hooks_migrated = self._merge_hooks(
                user_data.get("hooks", {}), template_data.get("hooks", {})
            )
            merged_data["hooks"] = merged_hooks

            # Step 6: Write result (if not dry-run)
            if write_result:
                self._atomic_write(user_path, merged_data)

            # Step 7: Audit log success
            audit_log(
                "settings_merge",
                "merge_completed",
                {
                    "user_path": str(user_path),
                    "template_path": str(template_path),
                    "hooks_added": hooks_added,
                    "hooks_preserved": hooks_preserved,
                    "hooks_migrated": hooks_migrated,
                    "write_result": write_result,
                },
            )

            # Step 8: Return success
            message = "Settings merged successfully"
            if not user_path.exists() or not user_data:
                message = "Settings created from template"
            elif hooks_migrated > 0:
                message = f"Settings merged successfully (migrated {hooks_migrated} hooks to unified)"

            return MergeResult(
                success=True,
                message=message,
                settings_path=str(user_path),
                hooks_added=hooks_added,
                hooks_preserved=hooks_preserved,
                hooks_migrated=hooks_migrated,
                details={
                    "template_path": str(template_path),
                    "write_result": write_result,
                },
            )

        except Exception as e:
            # Catch-all for unexpected errors
            audit_log(
                "settings_merge",
                "unexpected_error",
                {
                    "template_path": str(template_path),
                    "user_path": str(user_path),
                    "error": str(e),
                },
            )
            return MergeResult(
                success=False,
                message=f"Settings merge failed: {e}",
                details={"error": str(e)},
            )

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read and parse JSON file.

        Args:
            path: Path to JSON file

        Returns:
            Parsed JSON as dictionary, or None if parse fails
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # Return None on parse error (caller handles)
            return None

    def _merge_dicts(self, base: Dict, updates: Dict) -> Dict:
        """Deep merge two dictionaries (updates override base).

        This performs a recursive deep merge where:
        - Nested dictionaries are merged recursively
        - Lists are replaced (not merged)
        - Scalar values from updates override base

        Args:
            base: Base dictionary (user settings)
            updates: Updates dictionary (template settings)

        Returns:
            Merged dictionary
        """
        merged = base.copy()

        for key, value in updates.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                # Special case: Don't deep merge "hooks" here (handled separately)
                if key == "hooks":
                    # Skip hooks - they're merged separately with duplicate detection
                    continue
                merged[key] = self._merge_dicts(merged[key], value)
            else:
                # Override with update value (lists, scalars, new keys)
                # But don't override "hooks" key here (handled separately)
                if key != "hooks":
                    merged[key] = value

        return merged

    def _merge_hooks(
        self, existing: Dict, new: Dict
    ) -> Tuple[Dict, int, int, int]:
        """Merge hooks by lifecycle event, avoiding duplicates.

        This merges hooks with special logic:
        - Merge by lifecycle event (PreToolUse, PostToolUse, etc.)
        - Avoid duplicate hooks (by exact dict comparison)
        - Preserve existing hooks (user customizations)
        - Issue #144: Migrate old hooks to unified hooks (remove replaced hooks)

        Args:
            existing: Existing hooks dictionary (user hooks)
            new: New hooks dictionary (template hooks)

        Returns:
            Tuple of (merged_hooks, hooks_added, hooks_preserved, hooks_migrated)
        """
        merged_hooks = {}
        hooks_added = 0
        hooks_preserved = 0
        hooks_migrated = 0

        # Issue #144: Build set of old hooks to remove (based on unified hooks in new)
        hooks_to_remove = set()
        for lifecycle, matcher_configs in new.items():
            for config in matcher_configs:
                if isinstance(config, dict):
                    # Handle nested structure: {"matcher": "*", "hooks": [...]}
                    inner_hooks = config.get("hooks", [config])  # Fallback to config itself if no nested hooks
                    for hook in inner_hooks:
                        if isinstance(hook, dict):
                            cmd = hook.get("command", "")
                            # Check if this is a unified hook
                            for unified_hook, replaced_hooks in UNIFIED_HOOK_REPLACEMENTS.items():
                                if unified_hook in cmd:
                                    # Mark old hooks for removal
                                    hooks_to_remove.update(replaced_hooks)

        # Start with existing hooks (preserve user customizations, migrate old hooks)
        for lifecycle, matcher_configs in existing.items():
            filtered_configs = []
            for config in matcher_configs:
                if isinstance(config, dict):
                    # Handle nested structure: {"matcher": "*", "hooks": [...]}
                    if "hooks" in config:
                        # Nested format - filter inner hooks
                        filtered_inner = []
                        for hook in config.get("hooks", []):
                            if isinstance(hook, dict):
                                cmd = hook.get("command", "")
                                should_remove = False
                                for old_hook in hooks_to_remove:
                                    if old_hook in cmd:
                                        should_remove = True
                                        hooks_migrated += 1
                                        break
                                if not should_remove:
                                    filtered_inner.append(hook)
                                    hooks_preserved += 1
                            else:
                                filtered_inner.append(hook)
                                hooks_preserved += 1
                        # Only add config if it still has hooks
                        if filtered_inner:
                            filtered_configs.append({**config, "hooks": filtered_inner})
                    else:
                        # Flat format - check command directly
                        cmd = config.get("command", "")
                        should_remove = False
                        for old_hook in hooks_to_remove:
                            if old_hook in cmd:
                                should_remove = True
                                hooks_migrated += 1
                                break
                        if not should_remove:
                            filtered_configs.append(config)
                            hooks_preserved += 1
                else:
                    filtered_configs.append(config)
                    hooks_preserved += 1
            merged_hooks[lifecycle] = filtered_configs

        # Add new hooks from template
        for lifecycle, hooks in new.items():
            if lifecycle not in merged_hooks:
                # New lifecycle event - add all hooks
                merged_hooks[lifecycle] = hooks.copy()
                hooks_added += len(hooks)
            else:
                # Existing lifecycle event - merge without duplicates
                existing_list = merged_hooks[lifecycle]
                for hook in hooks:
                    if hook not in existing_list:
                        existing_list.append(hook)
                        hooks_added += 1

        return merged_hooks, hooks_added, hooks_preserved, hooks_migrated

    def _atomic_write(self, path: Path, content: Dict) -> None:
        """Write JSON file atomically with secure permissions.

        This uses tempfile + rename for atomic writes:
        1. Create temp file in same directory
        2. Write JSON to temp file
        3. Set secure permissions (0o600)
        4. Atomic rename to target path

        Args:
            path: Target path for JSON file
            content: Dictionary to write as JSON

        Raises:
            OSError: If write fails
        """
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp file in same directory (for atomic rename)
        fd = None
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                dir=str(path.parent),
                prefix=".settings-",
                suffix=".json.tmp",
            )

            # Write JSON to temp file
            json_content = json.dumps(content, indent=2, sort_keys=True)
            os.write(fd, json_content.encode("utf-8"))
            os.close(fd)
            fd = None

            # Set secure permissions (user-only read/write)
            os.chmod(temp_path, 0o600)

            # Atomic rename
            os.rename(temp_path, path)

        except OSError as e:
            # Clean up temp file on error
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

            # Re-raise with context
            raise OSError(f"Failed to write settings atomically: {e}") from e


def log_audit(event: str, context: Dict[str, Any]) -> None:
    """Alias for audit_log (backward compatibility with test mocks).

    Args:
        event: Event description
        context: Event context
    """
    audit_log("settings_merge", event, context)
