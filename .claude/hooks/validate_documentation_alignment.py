#!/usr/bin/env python3
"""
Validates that PROJECT.md and CLAUDE.md are synchronized.

This hook prevents documentation drift by ensuring:
1. Agent counts match between PROJECT.md and reality
2. Command counts match between PROJECT.md and reality
3. Hook counts match between PROJECT.md and reality
4. No stale references to removed features (e.g., skills/)
5. Both documents have same version and recent update date

Relevant Skills:
- project-alignment-validation: Gap assessment methodology, conflict resolution patterns

Exit Codes:
- 0: All validations pass
- 1: Warnings (recommend fixing but allow)
- 2: Critical failures (block commit, must fix)
"""

import re
import sys
from pathlib import Path


def load_project_md():
    """Load and parse PROJECT.md"""
    project_path = Path(".claude/PROJECT.md")
    if not project_path.exists():
        return None

    content = project_path.read_text()

    # Extract agent count from "**Agents**: N total"
    agent_match = re.search(r"\*\*Agents\*\*:\s*(\d+)\s*total", content)
    agents = int(agent_match.group(1)) if agent_match else None

    # Extract command count from "**Commands**: N total"
    command_match = re.search(r"\*\*Commands\*\*:\s*(\d+)\s*total", content)
    commands = int(command_match.group(1)) if command_match else None

    # Extract hook count from "**Hooks**: N total"
    hook_match = re.search(r"\*\*Hooks\*\*:\s*(\d+)\s*total", content)
    hooks = int(hook_match.group(1)) if hook_match else None

    # Check for stale skills references
    has_stale_skills_ref = "plugins/autonomous-dev/skills/" in content

    # Extract version
    version_match = re.search(r"\*\*Version\*\*:\s*v([\d.]+)", content)
    version = version_match.group(1) if version_match else None

    # Extract last updated date
    last_updated_match = re.search(r"\*\*Last Updated\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    last_updated = last_updated_match.group(1) if last_updated_match else None

    return {
        "agents": agents,
        "commands": commands,
        "hooks": hooks,
        "stale_skills_ref": has_stale_skills_ref,
        "version": version,
        "last_updated": last_updated,
    }


def load_claude_md():
    """Load and parse CLAUDE.md"""
    claude_path = Path("CLAUDE.md")
    if not claude_path.exists():
        return None

    content = claude_path.read_text()

    # Check for stale skills references
    has_stale_skills_ref = "plugins/autonomous-dev/skills/" in content

    # Extract version
    version_match = re.search(r"\*\*Version\*\*:\s*v([\d.]+)", content)
    version = version_match.group(1) if version_match else None

    # Extract last updated date
    last_updated_match = re.search(r"\*\*Last Updated\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    last_updated = last_updated_match.group(1) if last_updated_match else None

    return {
        "stale_skills_ref": has_stale_skills_ref,
        "version": version,
        "last_updated": last_updated,
    }


def count_actual_agents():
    """Count actual agent files"""
    agents_dir = Path("plugins/autonomous-dev/agents")
    if not agents_dir.exists():
        return None
    return len(list(agents_dir.glob("*.md")))


def count_actual_commands():
    """Count actual command files"""
    commands_dir = Path("plugins/autonomous-dev/commands")
    if not commands_dir.exists():
        return None
    return len(list(commands_dir.glob("*.md")))


def count_actual_hooks():
    """Count actual hook files"""
    hooks_dir = Path("plugins/autonomous-dev/hooks")
    if not hooks_dir.exists():
        return None
    return len(list(hooks_dir.glob("*.py")))


def main():
    """Main validation function"""
    errors = []
    warnings = []

    # Load documentation
    project = load_project_md()
    claude = load_claude_md()

    if not project:
        print("⚠️  PROJECT.md not found at .claude/PROJECT.md", file=sys.stderr)
        warnings.append("PROJECT.md missing")

    if not claude:
        print("⚠️  CLAUDE.md not found", file=sys.stderr)
        warnings.append("CLAUDE.md missing")

    # Check agent counts
    actual_agents = count_actual_agents()
    if project and actual_agents is not None:
        if project["agents"] != actual_agents:
            errors.append(
                f"Agent count mismatch: PROJECT.md says {project['agents']}, "
                f"but found {actual_agents} agent files. "
                f"Update PROJECT.md line 182."
            )

    # Check command counts
    actual_commands = count_actual_commands()
    if project and actual_commands is not None:
        if project["commands"] != actual_commands:
            errors.append(
                f"Command count mismatch: PROJECT.md says {project['commands']}, "
                f"but found {actual_commands} command files. "
                f"Update PROJECT.md line 186."
            )

    # Check hook counts
    actual_hooks = count_actual_hooks()
    if project and actual_hooks is not None:
        if project["hooks"] != actual_hooks:
            errors.append(
                f"Hook count mismatch: PROJECT.md says {project['hooks']}, "
                f"but found {actual_hooks} hook files. "
                f"Update PROJECT.md line 187."
            )

    # Check for stale skills references
    if project and project["stale_skills_ref"]:
        errors.append(
            "PROJECT.md contains stale reference to 'plugins/autonomous-dev/skills/'. "
            "Skills were removed (Anthropic anti-pattern guidance v2.5+). "
            "Remove the reference."
        )

    if claude and claude["stale_skills_ref"]:
        errors.append(
            "CLAUDE.md contains stale reference to 'plugins/autonomous-dev/skills/'. "
            "Skills were removed. Remove the reference."
        )

    # Check version synchronization
    if project and claude and project["version"] != claude["version"]:
        warnings.append(
            f"Version mismatch: PROJECT.md has v{project['version']}, "
            f"CLAUDE.md has v{claude['version']}"
        )

    # Check date synchronization (should be recent)
    if project and claude:
        if project["last_updated"] != claude["last_updated"]:
            warnings.append(
                f"Update date mismatch: PROJECT.md dated {project['last_updated']}, "
                f"CLAUDE.md dated {claude['last_updated']}. "
                f"Consider synchronizing."
            )

    # Print results
    if errors:
        print("\n❌ CRITICAL DOCUMENTATION ALIGNMENT FAILURES:\n", file=sys.stderr)
        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}\n", file=sys.stderr)
        print(
            "Fix these issues and try again. "
            "Run: /align-project to auto-detect current state.",
            file=sys.stderr
        )
        return 2

    if warnings:
        print("⚠️  DOCUMENTATION ALIGNMENT WARNINGS:\n", file=sys.stderr)
        for i, warning in enumerate(warnings, 1):
            print(f"{i}. {warning}\n", file=sys.stderr)
        print("Warnings allow commit but recommend fixing.\n", file=sys.stderr)
        return 1

    # All checks pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"❌ Hook error: {e}", file=sys.stderr)
        sys.exit(2)
