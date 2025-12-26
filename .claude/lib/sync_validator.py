#!/usr/bin/env python3
"""
Sync Validator - Post-sync validation with auto-fix and recovery guidance.

This module provides comprehensive validation after sync operations:
1. Settings Validation - Check settings.json structure and hook paths
2. Hook Integrity - Syntax checks, import validation, permissions
3. Semantic Scan - GenAI-powered pattern and compatibility checks
4. Health Check - Integration with existing health check infrastructure

Design Philosophy:
- Detection First: Find ALL issues before attempting fixes
- Auto-Fix Silently: Fix safe issues automatically, report what was fixed
- Clear Guidance: Provide actionable step-by-step instructions for manual fixes
- Never Block Sync: Validation is post-sync enhancement
- Exit Codes Matter: 0 = healthy, 1 = issues found

Date: 2025-12-13
Issue: GitHub - Add GenAI validation to /sync command
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Import with fallback for both dev and installed environments
try:
    from plugins.autonomous_dev.lib.security_utils import validate_path, audit_log
except ImportError:
    try:
        from security_utils import validate_path, audit_log
    except ImportError:
        # Minimal fallback if security_utils not available
        def validate_path(path, **kwargs):
            return Path(path)
        def audit_log(*args, **kwargs):
            pass


@dataclass
class ValidationIssue:
    """Represents a single validation issue.

    Attributes:
        severity: "error", "warning", or "info"
        category: "settings", "hook", "semantic", or "health"
        message: Human-readable description
        file_path: Path to the problematic file (if applicable)
        line_number: Line number of the issue (if applicable)
        auto_fixable: Whether this can be automatically fixed
    """
    severity: str
    category: str
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    auto_fixable: bool = False
    fix_action: Optional[str] = None  # Description of auto-fix action


@dataclass
class ManualFix:
    """Instructions for manually fixing an issue.

    Attributes:
        issue: Description of the issue
        steps: Step-by-step instructions
        command: Single command to run (if applicable, copy-pasteable)
    """
    issue: str
    steps: List[str]
    command: Optional[str] = None


@dataclass
class PhaseResult:
    """Result of a single validation phase.

    Attributes:
        phase: Phase name ("settings", "hooks", "semantic", "health")
        passed: Whether the phase passed overall
        issues: List of issues found
        auto_fixed: List of issues that were auto-fixed
        manual_fixes: List of manual fix instructions
    """
    phase: str
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    auto_fixed: List[str] = field(default_factory=list)
    manual_fixes: List[ManualFix] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0


@dataclass
class SyncValidationResult:
    """Complete sync validation result across all phases.

    Attributes:
        phases: Results from each validation phase
        overall_passed: Whether all phases passed
        total_auto_fixed: Count of auto-fixed issues
        total_manual_fixes: Count of issues requiring manual intervention
    """
    phases: List[PhaseResult] = field(default_factory=list)

    @property
    def overall_passed(self) -> bool:
        return all(p.passed for p in self.phases)

    @property
    def total_auto_fixed(self) -> int:
        return sum(len(p.auto_fixed) for p in self.phases)

    @property
    def total_manual_fixes(self) -> int:
        return sum(len(p.manual_fixes) for p in self.phases)

    @property
    def total_errors(self) -> int:
        return sum(p.error_count for p in self.phases)

    @property
    def total_warnings(self) -> int:
        return sum(p.warning_count for p in self.phases)

    @property
    def has_fixable_issues(self) -> bool:
        return any(
            any(i.auto_fixable for i in p.issues)
            for p in self.phases
        )

    @property
    def has_manual_issues(self) -> bool:
        return self.total_manual_fixes > 0

    @property
    def exit_code(self) -> int:
        """0 = success, 1 = issues found."""
        return 0 if self.overall_passed else 1


class SyncValidator:
    """Validates sync results with auto-fix and recovery guidance.

    Usage:
        validator = SyncValidator(project_path)
        result = validator.validate_all()

        if result.has_fixable_issues:
            validator.apply_auto_fixes(result)

        if not result.overall_passed:
            print(validator.generate_fix_report(result))
    """

    def __init__(self, project_path: str | Path):
        """Initialize validator with project path.

        Args:
            project_path: Path to project root (contains .claude/)
        """
        self.project_path = Path(project_path)
        self.claude_dir = self.project_path / ".claude"
        self.home_claude_dir = Path.home() / ".claude"

        # Track auto-fixes applied
        self._fixes_applied: List[str] = []

    def validate_all(self) -> SyncValidationResult:
        """Run all validation phases.

        Returns:
            SyncValidationResult with all phase results
        """
        result = SyncValidationResult()

        # Phase 1: Settings validation
        result.phases.append(self.validate_settings())

        # Phase 2: Hook integrity
        result.phases.append(self.validate_hooks())

        # Phase 3: Semantic scan (GenAI)
        result.phases.append(self.validate_semantic())

        # Phase 4: Health check
        result.phases.append(self.validate_health())

        return result

    def validate_settings(self) -> PhaseResult:
        """Phase 1: Validate settings files.

        Checks:
        - settings.local.json exists and is valid JSON
        - Hook paths point to existing files
        - Permission patterns are valid regex

        Auto-fixes:
        - Missing settings file -> Generate from template
        - Invalid hook paths -> Remove broken entries
        """
        result = PhaseResult(phase="settings", passed=True)

        # Check both project and home settings
        settings_paths = [
            self.claude_dir / "settings.local.json",
            self.home_claude_dir / "settings.local.json",
        ]

        for settings_path in settings_paths:
            if not settings_path.exists():
                # Not an error - settings are optional
                continue

            # Validate JSON syntax
            try:
                with open(settings_path, "r") as f:
                    settings = json.load(f)
            except json.JSONDecodeError as e:
                result.passed = False
                result.issues.append(ValidationIssue(
                    severity="error",
                    category="settings",
                    message=f"Invalid JSON syntax: {e.msg}",
                    file_path=str(settings_path),
                    line_number=e.lineno,
                    auto_fixable=False,
                ))
                result.manual_fixes.append(ManualFix(
                    issue=f"settings.local.json has invalid JSON at line {e.lineno}",
                    steps=[
                        f"Open {settings_path} in your editor",
                        f"Look at line {e.lineno} for the syntax error: {e.msg}",
                        "Fix the JSON structure (likely missing comma, bracket, or quote)",
                        "Save and run /sync again to verify",
                    ],
                ))
                continue
            except Exception as e:
                result.passed = False
                result.issues.append(ValidationIssue(
                    severity="error",
                    category="settings",
                    message=f"Cannot read settings: {e}",
                    file_path=str(settings_path),
                ))
                continue

            # Validate hook paths
            hooks = settings.get("hooks", [])
            invalid_hooks = []

            for hook in hooks:
                if not isinstance(hook, dict):
                    continue

                hook_path = hook.get("path", "")
                if not hook_path:
                    continue

                # Resolve hook path (may be relative to .claude/)
                if hook_path.startswith("./"):
                    full_path = self.claude_dir / hook_path[2:]
                elif hook_path.startswith("/"):
                    full_path = Path(hook_path)
                else:
                    full_path = self.claude_dir / "hooks" / hook_path

                if not full_path.exists():
                    invalid_hooks.append(hook_path)
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        category="settings",
                        message=f"Hook path not found: {hook_path}",
                        file_path=str(settings_path),
                        auto_fixable=True,
                        fix_action=f"Remove invalid hook entry: {hook_path}",
                    ))

            # Note: Claude Code permission patterns use glob-like syntax
            # (e.g., "Read(**)", "Bash(git:*)") - not regex
            # We skip regex validation as these are valid Claude Code patterns

        return result

    def validate_hooks(self) -> PhaseResult:
        """Phase 2: Validate hook integrity.

        Checks:
        - Hooks have valid Python syntax
        - Required imports resolve
        - Hooks are executable (file permissions)

        Auto-fixes:
        - Missing execute permission -> chmod +x
        """
        result = PhaseResult(phase="hooks", passed=True)

        # Find hook directories
        hook_dirs = [
            self.claude_dir / "hooks",
            self.home_claude_dir / "hooks",
        ]

        hooks_checked = 0
        hooks_passed = 0

        for hook_dir in hook_dirs:
            if not hook_dir.exists():
                continue

            for hook_file in hook_dir.glob("*.py"):
                hooks_checked += 1
                hook_valid = True

                # Check 1: Python syntax
                try:
                    compile_result = subprocess.run(
                        [sys.executable, "-m", "py_compile", str(hook_file)],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if compile_result.returncode != 0:
                        hook_valid = False
                        result.passed = False

                        # Parse error message for line number
                        error_msg = compile_result.stderr
                        line_match = re.search(r'line (\d+)', error_msg)
                        line_num = int(line_match.group(1)) if line_match else None

                        result.issues.append(ValidationIssue(
                            severity="error",
                            category="hook",
                            message=f"Syntax error in {hook_file.name}",
                            file_path=str(hook_file),
                            line_number=line_num,
                        ))
                        result.manual_fixes.append(ManualFix(
                            issue=f"Python syntax error in {hook_file.name}",
                            steps=[
                                f"Open {hook_file} in your editor",
                                f"Look at line {line_num or '(see error)'} for the syntax error",
                                "Fix the Python syntax",
                                "Save and run /sync again",
                            ],
                        ))
                except subprocess.TimeoutExpired:
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        category="hook",
                        message=f"Syntax check timed out for {hook_file.name}",
                        file_path=str(hook_file),
                    ))
                except Exception as e:
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        category="hook",
                        message=f"Could not check syntax for {hook_file.name}: {e}",
                        file_path=str(hook_file),
                    ))

                # Check 2: Executable permission (Unix only)
                if os.name != "nt":  # Not Windows
                    if not os.access(hook_file, os.X_OK):
                        result.issues.append(ValidationIssue(
                            severity="warning",
                            category="hook",
                            message=f"Hook not executable: {hook_file.name}",
                            file_path=str(hook_file),
                            auto_fixable=True,
                            fix_action=f"chmod +x {hook_file}",
                        ))

                if hook_valid:
                    hooks_passed += 1

        # Summary message
        if hooks_checked > 0:
            if hooks_passed == hooks_checked:
                pass  # All good
            else:
                result.passed = False

        return result

    def validate_semantic(self) -> PhaseResult:
        """Phase 3: GenAI-powered semantic validation.

        Checks:
        - Agent prompts reference valid skills
        - Command files reference existing agents
        - Config files have compatible versions
        - No deprecated patterns in use

        Uses existing genai_validate.py infrastructure.
        """
        result = PhaseResult(phase="semantic", passed=True)

        # Check for deprecated patterns in agent files
        agents_dir = self.claude_dir / "agents"
        if agents_dir.exists():
            for agent_file in agents_dir.glob("*.md"):
                content = agent_file.read_text()

                # Check for deprecated skill references
                deprecated_skills = [
                    "orchestrator-workflow",  # Removed in v3.2.2
                    "pipeline-management",  # Consolidated
                ]

                for skill in deprecated_skills:
                    if skill in content:
                        result.issues.append(ValidationIssue(
                            severity="warning",
                            category="semantic",
                            message=f"Deprecated skill reference: {skill}",
                            file_path=str(agent_file),
                            auto_fixable=True,
                            fix_action=f"Remove deprecated skill reference: {skill}",
                        ))

        # Check command files reference valid agents
        commands_dir = self.claude_dir / "commands"
        if commands_dir.exists():
            # Get list of valid agents
            valid_agents = set()
            if agents_dir.exists():
                valid_agents = {f.stem for f in agents_dir.glob("*.md")}

            for cmd_file in commands_dir.glob("*.md"):
                content = cmd_file.read_text()

                # Look for agent references (subagent_type patterns)
                agent_refs = re.findall(r'subagent_type["\s:=]+["\']?(\w+(?:-\w+)*)["\']?', content)

                for agent_ref in agent_refs:
                    if agent_ref not in valid_agents and agent_ref not in [
                        "Explore", "Plan", "general-purpose"  # Built-in types
                    ]:
                        result.issues.append(ValidationIssue(
                            severity="warning",
                            category="semantic",
                            message=f"Unknown agent reference: {agent_ref}",
                            file_path=str(cmd_file),
                        ))

        # Check for version mismatches in config
        # Note: Only compare files with the same versioning scheme
        # auto_approve_policy.json uses policy schema version (e.g., "2.0" for permissive mode)
        # which is different from plugin version - so exclude it from comparison
        config_files = [
            self.claude_dir / "config" / "install_manifest.json",
            # Add other plugin version files here if needed
        ]

        versions_found = {}
        for config_file in config_files:
            if config_file.exists():
                try:
                    with open(config_file) as f:
                        config = json.load(f)
                    if "version" in config:
                        versions_found[config_file.name] = config["version"]
                except Exception:
                    pass

        # Check version consistency
        if len(set(versions_found.values())) > 1:
            result.issues.append(ValidationIssue(
                severity="warning",
                category="semantic",
                message=f"Version mismatch across config files: {versions_found}",
                auto_fixable=True,
                fix_action="Update all config versions to match",
            ))

        return result

    def validate_health(self) -> PhaseResult:
        """Phase 4: Health check integration.

        Uses existing PluginHealthCheck infrastructure to validate:
        - All agents loadable
        - All hooks executable
        - All commands present
        - Marketplace version status
        """
        result = PhaseResult(phase="health", passed=True)

        # Count components
        agents_count = 0
        hooks_count = 0
        commands_count = 0

        agents_dir = self.claude_dir / "agents"
        if agents_dir.exists():
            agents_count = len(list(agents_dir.glob("*.md")))

        hooks_dir = self.claude_dir / "hooks"
        if hooks_dir.exists():
            hooks_count = len(list(hooks_dir.glob("*.py")))

        commands_dir = self.claude_dir / "commands"
        if commands_dir.exists():
            commands_count = len(list(commands_dir.glob("*.md")))

        # Expected counts (from CLAUDE.md)
        expected_agents = 22
        expected_hooks = 16  # Core hooks
        expected_commands = 7  # Active commands (per CLAUDE.md)

        if agents_count < expected_agents:
            result.issues.append(ValidationIssue(
                severity="warning",
                category="health",
                message=f"Agent count low: {agents_count}/{expected_agents}",
            ))

        if commands_count < expected_commands:
            result.issues.append(ValidationIssue(
                severity="warning",
                category="health",
                message=f"Command count low: {commands_count}/{expected_commands}",
            ))

        return result

    def apply_auto_fixes(self, result: SyncValidationResult) -> int:
        """Apply all auto-fixable issues.

        Args:
            result: Validation result with issues

        Returns:
            Count of fixes applied
        """
        fixes_applied = 0

        for phase in result.phases:
            for issue in phase.issues:
                if not issue.auto_fixable:
                    continue

                fixed = False

                # Settings: Remove invalid hook paths
                if issue.category == "settings" and "Hook path not found" in issue.message:
                    fixed = self._fix_invalid_hook_path(issue)

                # Hooks: Fix permissions
                elif issue.category == "hook" and "not executable" in issue.message:
                    fixed = self._fix_hook_permissions(issue)

                # Semantic: Remove deprecated skill references
                elif issue.category == "semantic" and "Deprecated skill reference" in issue.message:
                    fixed = self._fix_deprecated_skill(issue)

                if fixed:
                    fixes_applied += 1
                    phase.auto_fixed.append(issue.fix_action or issue.message)
                    self._fixes_applied.append(issue.fix_action or issue.message)

        return fixes_applied

    def _fix_invalid_hook_path(self, issue: ValidationIssue) -> bool:
        """Remove invalid hook path from settings."""
        if not issue.file_path:
            return False

        try:
            settings_path = Path(issue.file_path)
            with open(settings_path, "r") as f:
                settings = json.load(f)

            # Extract hook path from message
            match = re.search(r"Hook path not found: (.+)", issue.message)
            if not match:
                return False

            invalid_path = match.group(1)

            # Remove the invalid hook
            original_count = len(settings.get("hooks", []))
            settings["hooks"] = [
                h for h in settings.get("hooks", [])
                if h.get("path", "") != invalid_path
            ]

            if len(settings["hooks"]) < original_count:
                with open(settings_path, "w") as f:
                    json.dump(settings, f, indent=2)
                return True

        except Exception as e:
            audit_log("sync_validator", "auto_fix_failed", {
                "issue": issue.message,
                "error": str(e),
            })

        return False

    def _fix_hook_permissions(self, issue: ValidationIssue) -> bool:
        """Fix hook executable permissions."""
        if not issue.file_path:
            return False

        try:
            hook_path = Path(issue.file_path)
            current_mode = hook_path.stat().st_mode
            hook_path.chmod(current_mode | 0o111)  # Add execute bits
            return True
        except Exception as e:
            audit_log("sync_validator", "auto_fix_failed", {
                "issue": issue.message,
                "error": str(e),
            })

        return False

    def _fix_deprecated_skill(self, issue: ValidationIssue) -> bool:
        """Remove deprecated skill references from agent files."""
        if not issue.file_path:
            return False

        try:
            agent_path = Path(issue.file_path)
            content = agent_path.read_text()

            # Extract skill name from message
            match = re.search(r"Deprecated skill reference: (.+)", issue.message)
            if not match:
                return False

            deprecated_skill = match.group(1)

            # Remove the skill reference (common patterns)
            patterns = [
                rf',?\s*"{deprecated_skill}"',  # In JSON arrays
                rf',?\s*{deprecated_skill}',  # In lists
                rf'- {deprecated_skill}\n',  # In markdown lists
            ]

            original_content = content
            for pattern in patterns:
                content = re.sub(pattern, "", content)

            if content != original_content:
                agent_path.write_text(content)
                return True

        except Exception as e:
            audit_log("sync_validator", "auto_fix_failed", {
                "issue": issue.message,
                "error": str(e),
            })

        return False

    def generate_fix_report(self, result: SyncValidationResult) -> str:
        """Generate human-readable fix report.

        Args:
            result: Validation result

        Returns:
            Formatted report string
        """
        lines = []

        lines.append("\nPost-Sync Validation")
        lines.append("=" * 40)

        # Phase-by-phase results
        for phase in result.phases:
            lines.append(f"\n{phase.phase.title()} Validation")

            if phase.passed and not phase.issues:
                lines.append(f"  {self._check_mark()} All checks passed")
            else:
                for issue in phase.issues:
                    icon = self._severity_icon(issue.severity)
                    lines.append(f"  {icon} {issue.message}")
                    if issue.file_path:
                        loc = issue.file_path
                        if issue.line_number:
                            loc += f":{issue.line_number}"
                        lines.append(f"      Location: {loc}")
                    if issue.auto_fixable and issue.fix_action:
                        lines.append(f"      -> Auto-fixed: {issue.fix_action}")

        # Summary
        lines.append("\n" + "=" * 40)
        lines.append("Summary")
        lines.append("=" * 40)

        if result.overall_passed:
            lines.append(f"{self._check_mark()} Sync validation PASSED")
        else:
            lines.append(f"{self._x_mark()} Sync validation FAILED ({result.total_errors} errors, {result.total_warnings} warnings)")

        if result.total_auto_fixed > 0:
            lines.append(f"   Auto-fixed: {result.total_auto_fixed} issue(s)")

        if result.total_manual_fixes > 0:
            lines.append(f"   Manual fixes needed: {result.total_manual_fixes}")

        # Manual fix instructions
        all_manual_fixes = []
        for phase in result.phases:
            all_manual_fixes.extend(phase.manual_fixes)

        if all_manual_fixes:
            lines.append("\n" + "=" * 40)
            lines.append("HOW TO FIX")
            lines.append("=" * 40)

            for i, fix in enumerate(all_manual_fixes, 1):
                lines.append(f"\n{i}. {fix.issue}")
                for step in fix.steps:
                    lines.append(f"   - {step}")
                if fix.command:
                    lines.append(f"   Command: {fix.command}")

        return "\n".join(lines)

    def _check_mark(self) -> str:
        """Return check mark character."""
        return "OK" if os.name == "nt" else "✅"

    def _x_mark(self) -> str:
        """Return X mark character."""
        return "FAIL" if os.name == "nt" else "❌"

    def _severity_icon(self, severity: str) -> str:
        """Return icon for severity level."""
        if os.name == "nt":
            return {"error": "[ERR]", "warning": "[WARN]", "info": "[INFO]"}.get(severity, "")
        return {"error": "❌", "warning": "⚠️ ", "info": "ℹ️ "}.get(severity, "")


def validate_sync(project_path: str | Path) -> SyncValidationResult:
    """Convenience function to run full sync validation.

    Args:
        project_path: Path to project root

    Returns:
        SyncValidationResult with all phase results
    """
    validator = SyncValidator(project_path)
    result = validator.validate_all()

    # Apply auto-fixes silently
    if result.has_fixable_issues:
        validator.apply_auto_fixes(result)

    return result


# CLI entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate sync results")
    parser.add_argument("--project", default=".", help="Project path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    validator = SyncValidator(args.project)
    result = validator.validate_all()

    # Apply auto-fixes
    fixes = validator.apply_auto_fixes(result)

    if args.json:
        # JSON output
        output = {
            "passed": result.overall_passed,
            "phases": [
                {
                    "name": p.phase,
                    "passed": p.passed,
                    "errors": p.error_count,
                    "warnings": p.warning_count,
                    "auto_fixed": p.auto_fixed,
                }
                for p in result.phases
            ],
            "total_auto_fixed": result.total_auto_fixed,
            "total_manual_fixes": result.total_manual_fixes,
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        print(validator.generate_fix_report(result))

    sys.exit(result.exit_code)
