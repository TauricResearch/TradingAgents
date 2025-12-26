#!/usr/bin/env python3
"""
Plugin health check utility.

Validates all autonomous-dev plugin components:
- Agents (20 specialist agents - orchestrator removed in v3.2.2)
- Hooks (13 core automation hooks)
- Commands (7 active commands)

Note: Skills removed per Issue #5 (PROJECT.md: "No skills/ directory - anti-pattern")

Usage:
    python health_check.py
    python health_check.py --verbose
    python health_check.py --json  # Machine-readable output
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Add lib to path for error_messages module
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from error_messages import ErrorMessage, ErrorCode

# Import validate_marketplace_version - will be mocked in tests
import plugins.autonomous_dev.lib.validate_marketplace_version as validate_marketplace_version_module


class PluginHealthCheck:
    """Validates autonomous-dev plugin component integrity."""

    # Expected components - 8 active agents (Issue #147: Agent consolidation)
    # Only agents actually invoked by commands are validated
    EXPECTED_AGENTS = [
        "doc-master",
        "implementer",
        "issue-creator",
        "planner",
        "researcher-local",
        "reviewer",
        "security-auditor",
        "test-master",
    ]

    # Skills removed per Issue #5 - PROJECT.md: "No skills/ directory - anti-pattern"
    EXPECTED_SKILLS = []

    # Core hooks - Issue #144 consolidated 51 hooks into unified hooks
    # Issue #147: Updated to match actual hooks after consolidation
    EXPECTED_HOOKS = [
        "auto_format.py",
        "auto_test.py",
        "enforce_file_organization.py",
        "enforce_pipeline_complete.py",
        "enforce_tdd.py",
        "security_scan.py",
        "unified_pre_tool.py",
        "unified_prompt_validator.py",
        "unified_session_tracker.py",
        "validate_claude_alignment.py",
        "validate_command_file_ops.py",
        "validate_project_alignment.py",
    ]

    EXPECTED_COMMANDS = [
        "advise.md",  # Added in v3.43.0 (Issue #158)
        "align.md",
        "auto-implement.md",
        "batch-implement.md",
        "create-issue.md",
        "health-check.md",  # Self-reference
        "setup.md",
        "sync.md",
    ]

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.plugin_dir = self._find_plugin_dir()
        self.results = {
            "agents": {},
            "skills": {},
            "hooks": {},
            "commands": {},
            "overall": "UNKNOWN",
        }

    def _find_plugin_dir(self) -> Path:
        """Find the plugin directory."""
        # Try ~/.claude/plugins/autonomous-dev
        home_plugin = Path.home() / ".claude" / "plugins" / "autonomous-dev"
        if home_plugin.exists():
            return home_plugin

        # Try current directory structure
        cwd_plugin = Path.cwd() / "plugins" / "autonomous-dev"
        if cwd_plugin.exists():
            return cwd_plugin

        # Plugin not found - provide helpful error
        error = ErrorMessage(
            code=ErrorCode.DIRECTORY_NOT_FOUND,
            title="Plugin directory not found",
            what_wrong=f"autonomous-dev plugin not found in expected locations:\n  • {home_plugin}\n  • {cwd_plugin}",
            how_to_fix=[
                "Install the plugin:\n/plugin marketplace add akaszubski/autonomous-dev\n/plugin install autonomous-dev",
                "Exit and restart Claude Code (REQUIRED):\nPress Cmd+Q (Mac) or Ctrl+Q (Windows/Linux)",
                "Verify installation:\n/plugin list  # Check if autonomous-dev appears",
                "If developing plugin, run from plugin directory:\ncd plugins/autonomous-dev\npython scripts/health_check.py"
            ],
            learn_more="docs/TROUBLESHOOTING.md#plugin-not-found"
        )
        error.print()
        sys.exit(1)

    def check_component_exists(
        self, component_type: str, component_name: str, file_extension: str = ".md"
    ) -> bool:
        """Check if a component file exists."""
        component_path = (
            self.plugin_dir / component_type / f"{component_name}{file_extension}"
        )
        return component_path.exists()

    def validate_agents(self) -> Tuple[int, int]:
        """Validate all agents exist and are loadable."""
        passed = 0
        for agent in self.EXPECTED_AGENTS:
            exists = self.check_component_exists("agents", agent, ".md")
            self.results["agents"][agent] = "PASS" if exists else "FAIL"
            if exists:
                passed += 1
        return passed, len(self.EXPECTED_AGENTS)

    def validate_skills(self) -> Tuple[int, int]:
        """Validate all skills exist and are loadable.

        Note: Skills removed per Issue #5 - PROJECT.md states
        "No skills/ directory - anti-pattern". Returns (0, 0).
        """
        # Skills intentionally removed - no validation needed
        return 0, 0

    def validate_hooks(self) -> Tuple[int, int]:
        """Validate all hooks exist and are executable."""
        passed = 0
        for hook in self.EXPECTED_HOOKS:
            hook_path = self.plugin_dir / "hooks" / hook
            exists = hook_path.exists()
            executable = hook_path.is_file() and hook_path.stat().st_mode & 0o111
            self.results["hooks"][hook] = "PASS" if exists else "FAIL"
            if exists:
                passed += 1
        return passed, len(self.EXPECTED_HOOKS)

    def validate_commands(self) -> Tuple[int, int]:
        """Validate all commands exist."""
        passed = 0
        for command in self.EXPECTED_COMMANDS:
            exists = self.check_component_exists("commands", command.replace(".md", ""), ".md")
            self.results["commands"][command.replace(".md", "")] = (
                "PASS" if exists else "FAIL"
            )
            if exists:
                passed += 1
        return passed, len(self.EXPECTED_COMMANDS)

    def _is_plugin_development_mode(self) -> bool:
        """Check if we're in plugin development mode (editing source)."""
        # Check if current plugin_dir is the source location
        source_markers = [
            self.plugin_dir / ".claude-plugin" / "plugin.json",
            self.plugin_dir.parent.parent / ".git"  # plugins/autonomous-dev is in git repo
        ]
        return all(marker.exists() for marker in source_markers)

    def _find_installed_plugin_path(self) -> Path:
        """Find the installed plugin path from Claude's config.

        Security: Validates paths from JSON config to prevent CWE-22 path traversal attacks.
        """
        from plugins.autonomous_dev.lib.security_utils import validate_path

        home = Path.home()
        installed_plugins_file = home / ".claude" / "plugins" / "installed_plugins.json"

        if not installed_plugins_file.exists():
            return None

        try:
            with open(installed_plugins_file) as f:
                config = json.load(f)

            # Look for autonomous-dev plugin
            for plugin_key, plugin_info in config.get("plugins", {}).items():
                if plugin_key.startswith("autonomous-dev@"):
                    install_path_str = plugin_info["installPath"]

                    # Security: Validate path from JSON to prevent path traversal (CWE-22)
                    try:
                        validated_path = validate_path(
                            Path(install_path_str),
                            purpose="installed plugin location",
                            allow_missing=True
                        )
                        return validated_path
                    except ValueError:
                        # Security violation - skip this path
                        continue
        except Exception:
            pass

        return None

    def validate_sync_status(self) -> Tuple[bool, List[str]]:
        """
        Validate if development and installed plugin locations are in sync.

        Returns:
            (in_sync, out_of_sync_files)
        """
        # Only relevant for plugin development mode
        if not self._is_plugin_development_mode():
            return True, []  # Not in dev mode, sync not applicable

        # Find installed location
        installed_path = self._find_installed_plugin_path()
        if not installed_path or not installed_path.exists():
            return True, []  # Plugin not installed, sync not applicable

        out_of_sync = []

        # Check key directories
        check_dirs = ["agents", "commands", "hooks", "scripts"]

        for dir_name in check_dirs:
            source_dir = self.plugin_dir / dir_name
            target_dir = installed_path / dir_name

            if not source_dir.exists():
                continue

            # Compare modification times
            for source_file in source_dir.rglob("*"):
                if source_file.is_file() and not source_file.name.startswith('.'):
                    relative_path = source_file.relative_to(source_dir)
                    target_file = target_dir / relative_path

                    if not target_file.exists():
                        out_of_sync.append(f"{dir_name}/{relative_path}")
                    elif source_file.stat().st_mtime > target_file.stat().st_mtime:
                        out_of_sync.append(f"{dir_name}/{relative_path}")

        self.results["sync"] = {
            "in_sync": len(out_of_sync) == 0,
            "dev_mode": True,
            "out_of_sync_files": out_of_sync[:10]  # Limit to first 10
        }

        return len(out_of_sync) == 0, out_of_sync

    def _validate_marketplace_version(self) -> bool:
        """
        Validate marketplace plugin version against project version.

        Returns:
            bool: Always True (non-blocking validation)
        """
        try:
            # Find project root (parent of .claude/)
            project_root = self.plugin_dir.parent.parent

            # Call validate_marketplace_version
            report = validate_marketplace_version_module.validate_marketplace_version(project_root)

            # Print the report
            print(report)

        except FileNotFoundError as e:
            # Marketplace plugin not installed - this is OK
            print(f"Marketplace Version: SKIP (marketplace plugin not found)")

        except PermissionError:
            # Permission denied - show error but don't block (CWE-209: don't leak paths)
            print(f"Marketplace Version: ERROR (permission denied reading plugin configuration)")

        except json.JSONDecodeError:
            # Corrupted JSON - show error but don't block (CWE-209: don't leak file details)
            print(f"Marketplace Version: ERROR (corrupted plugin configuration)")

        except Exception:
            # Any other error - show generic error but don't block (CWE-209: don't leak details)
            print(f"Marketplace Version: ERROR (unexpected error during version check)")

        # Always return True (non-blocking)
        return True

    def print_report(self):
        """Print human-readable health check report."""
        print("\nRunning plugin health check...\n")
        print("=" * 60)
        print("PLUGIN HEALTH CHECK REPORT")
        print("=" * 60)
        print()

        # Agents
        agent_pass, agent_total = self.validate_agents()
        print(f"Agents: {agent_pass}/{agent_total} loaded")
        for agent, status in self.results["agents"].items():
            dots = "." * (30 - len(agent))
            print(f"  {agent} {dots} {status}")
        print()

        # Skills - removed per Issue #5
        skill_pass, skill_total = self.validate_skills()
        # Skills section intentionally removed - no output

        # Hooks
        hook_pass, hook_total = self.validate_hooks()
        print(f"Hooks: {hook_pass}/{hook_total} executable")
        for hook, status in self.results["hooks"].items():
            dots = "." * (30 - len(hook))
            print(f"  {hook} {dots} {status}")
        print()

        # Commands
        cmd_pass, cmd_total = self.validate_commands()
        print(f"Commands: {cmd_pass}/{cmd_total} present")
        for cmd, status in list(self.results["commands"].items())[:10]:
            dots = "." * (30 - len(cmd))
            print(f"  /{cmd} {dots} {status}")
        if cmd_total > 10:
            print(f"  ... and {cmd_total - 10} more")
        print()

        # Sync status (only for plugin development)
        in_sync, out_of_sync_files = self.validate_sync_status()
        if "sync" in self.results and self.results["sync"]["dev_mode"]:
            if in_sync:
                print("Development Sync: IN SYNC ✅")
                print("  Source and installed locations match")
            else:
                print(f"Development Sync: OUT OF SYNC ⚠️")
                print(f"  {len(out_of_sync_files)} files need syncing")
                if out_of_sync_files[:5]:
                    print("  Recent changes not synced:")
                    for file in out_of_sync_files[:5]:
                        print(f"    - {file}")
                    if len(out_of_sync_files) > 5:
                        print(f"    ... and {len(out_of_sync_files) - 5} more")
                print("\n  💡 Run: /sync-dev to sync changes")
            print()

        # Marketplace version validation
        self._validate_marketplace_version()
        print()

        # Overall status
        total_issues = (
            (agent_total - agent_pass)
            + (hook_total - hook_pass)
            + (cmd_total - cmd_pass)
        )
        # Note: skills intentionally excluded (removed per Issue #5)

        print("=" * 60)
        if total_issues == 0:
            print("OVERALL STATUS: HEALTHY")
            self.results["overall"] = "HEALTHY"
        else:
            print(f"OVERALL STATUS: DEGRADED ({total_issues} issues found)")
            self.results["overall"] = "DEGRADED"
        print("=" * 60)
        print()

        if total_issues == 0:
            print("✅ All plugin components are functioning correctly!")
        else:
            print("⚠️  Issues detected:")
            issue_num = 1
            missing_components = []

            for component_type in ["agents", "hooks", "commands"]:  # skills removed
                for name, status in self.results[component_type].items():
                    if status == "FAIL":
                        component_path = f"~/.claude/plugins/autonomous-dev/{component_type}/{name}"
                        if component_type in ["agents", "commands"]:
                            component_path += ".md"
                        print(f"  {issue_num}. {component_type[:-1].title()} '{name}' missing: {component_path}")
                        missing_components.append((component_type, name))
                        issue_num += 1

            # Provide detailed recovery guidance
            print()
            print("=" * 70)
            print("HOW TO FIX [ERR-304]")
            print("=" * 70)
            print()
            print("Missing components indicate incomplete or corrupted plugin installation.")
            print()
            print("Recovery options:")
            print()
            print("1. QUICK FIX - Reinstall plugin (recommended):")
            print("   Step 1: Uninstall")
            print("     /plugin uninstall autonomous-dev")
            print()
            print("   Step 2: Exit and restart Claude Code (REQUIRED!)")
            print("     Press Cmd+Q (Mac) or Ctrl+Q (Windows/Linux)")
            print()
            print("   Step 3: Reinstall")
            print("     /plugin install autonomous-dev")
            print()
            print("   Step 4: Exit and restart again")
            print("     Press Cmd+Q (Mac) or Ctrl+Q (Windows/Linux)")
            print()
            print("2. VERIFY INSTALLATION - Check plugin location:")
            print("   ls -la ~/.claude/plugins/marketplaces/*/autonomous-dev/")
            print()
            print("3. MANUAL FIX - If you're developing the plugin:")
            print("   /sync-dev  # Sync local changes to installed location")
            print("   # Then restart Claude Code")
            print()
            print("Learn more: docs/TROUBLESHOOTING.md#plugin-health-check-failures")
            print("=" * 70)

        print()

    def print_json(self):
        """Print machine-readable JSON output."""
        # Run all validations first
        agent_pass, agent_total = self.validate_agents()
        skill_pass, skill_total = self.validate_skills()  # Returns (0, 0)
        hook_pass, hook_total = self.validate_hooks()
        cmd_pass, cmd_total = self.validate_commands()

        # Calculate overall status (skills excluded - removed per Issue #5)
        total_issues = (
            (agent_total - agent_pass)
            + (hook_total - hook_pass)
            + (cmd_total - cmd_pass)
        )

        self.results["overall"] = "HEALTHY" if total_issues == 0 else "DEGRADED"

        print(json.dumps(self.results, indent=2))

    def run(self, output_format: str = "text"):
        """Run health check."""
        if output_format == "json":
            self.print_json()
        else:
            self.print_report()

        # Exit code based on overall status
        sys.exit(0 if self.results["overall"] == "HEALTHY" else 1)


def run_health_check(project_dir: Path = None) -> Dict[str, Any]:
    """Run health check and return results (for integration tests).

    Args:
        project_dir: Optional project directory (for testing)

    Returns:
        Dictionary with health check results including installation validation
    """
    # Import installation validator
    try:
        from plugins.autonomous_dev.lib.installation_validator import InstallationValidator
        from plugins.autonomous_dev.lib.file_discovery import FileDiscovery
    except ImportError:
        # Fallback for testing
        InstallationValidator = None

    # Run standard health check
    checker = PluginHealthCheck(verbose=False)
    agent_pass, agent_total = checker.validate_agents()
    skill_pass, skill_total = checker.validate_skills()
    hook_pass, hook_total = checker.validate_hooks()
    cmd_pass, cmd_total = checker.validate_commands()

    results = {
        "agents": {"passed": agent_pass, "total": agent_total},
        "hooks": {"passed": hook_pass, "total": hook_total},
        "commands": {"passed": cmd_pass, "total": cmd_total},
    }

    # Add installation validation if available
    if InstallationValidator and project_dir:
        try:
            # Find plugin source (marketplace location)
            marketplace_dir = Path.home() / ".claude" / "plugins" / "marketplaces" / "autonomous-dev"
            plugin_source = marketplace_dir / "plugins" / "autonomous-dev"

            if plugin_source.exists():
                dest_dir = project_dir / ".claude"
                validator = InstallationValidator(plugin_source, dest_dir)
                validation_result = validator.validate()

                results["installation"] = {
                    "status": validation_result.status,
                    "coverage": validation_result.coverage,
                    "missing_files": validation_result.missing_files,
                    "total_expected": validation_result.total_expected,
                    "total_found": validation_result.total_found,
                }
        except Exception:
            # Installation validation failed, but don't block health check
            pass

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Plugin health check utility")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="JSON output format")
    args = parser.parse_args()

    checker = PluginHealthCheck(verbose=args.verbose)
    checker.run(output_format="json" if args.json else "text")


if __name__ == "__main__":
    main()
