#!/usr/bin/env python3
"""
Validate that all slash commands have proper implementation instructions.

This prevents the "command does nothing" bug where commands are just documentation
without any actual bash/agent invocation instructions.

Run this as part of CI/CD or pre-commit to catch missing implementations.
"""

import sys
import re
from pathlib import Path


def validate_command(filepath: Path) -> tuple[bool, str]:
    """
    Validate a command file has proper ## Implementation section.

    Returns:
        (is_valid, error_message)
    """
    with open(filepath) as f:
        content = f.read()

    # Check for ## Implementation section header
    has_implementation_section = bool(re.search(r'^## Implementation', content, re.MULTILINE))

    if not has_implementation_section:
        # Check if implementation exists but not in proper section
        has_bash_block = bool(re.search(r'```bash\n(?!#\s*$).+', content, re.DOTALL))
        has_agent_invoke = bool(re.search(r'Invoke (the |orchestrator|test-master|doc-master|security-auditor|implementer|planner|reviewer|researcher)', content, re.IGNORECASE))
        has_script_exec = bool(re.search(r'python ["\']?\$\(dirname|python .+\.py', content))

        if has_bash_block or has_agent_invoke or has_script_exec:
            return False, "Implementation found but missing '## Implementation' section header (see templates/command-template.md)"

        return False, "Missing '## Implementation' section (command will only show docs, not execute)"

    # Has Implementation section - verify it contains actual execution instructions
    # Extract the Implementation section content
    impl_match = re.search(r'## Implementation\n(.+?)(?=\n## |\Z)', content, re.DOTALL)

    if not impl_match:
        return False, "## Implementation section is empty"

    impl_content = impl_match.group(1)

    # Check if Implementation section contains bash, agent invocation, or script
    has_bash = bool(re.search(r'```bash\n(?!#\s*$).+', impl_content, re.DOTALL))
    has_agent = bool(re.search(r'Invoke (the |orchestrator|test-master|doc-master|security-auditor|implementer|planner|reviewer|researcher)', impl_content, re.IGNORECASE))
    has_script = bool(re.search(r'python ["\']?\$\(dirname|python .+\.py', impl_content))

    if not (has_bash or has_agent or has_script):
        return False, "## Implementation section exists but contains no execution instructions (bash/agent/script)"

    return True, ""


def main():
    """Validate all commands in commands/"""

    # Find commands directory relative to this script
    # Script is at: plugins/autonomous-dev/hooks/validate_commands.py
    # Commands are at: plugins/autonomous-dev/commands/
    script_dir = Path(__file__).parent
    plugin_dir = script_dir.parent
    commands_dir = plugin_dir / "commands"

    if not commands_dir.exists():
        print(f"❌ Commands directory not found: {commands_dir}")
        sys.exit(1)

    print("=" * 70)
    print("SLASH COMMAND IMPLEMENTATION VALIDATION")
    print("=" * 70)
    print()

    command_files = sorted(commands_dir.glob("*.md"))

    if not command_files:
        print(f"❌ No command files found in {commands_dir}")
        sys.exit(1)

    valid = []
    invalid = []

    for filepath in command_files:
        is_valid, error = validate_command(filepath)

        if is_valid:
            valid.append(filepath.name)
            print(f"✅ {filepath.name}")
        else:
            invalid.append((filepath.name, error))
            print(f"❌ {filepath.name}: {error}")

    print()
    print("=" * 70)
    print(f"RESULTS: {len(valid)} valid, {len(invalid)} invalid")
    print("=" * 70)

    if invalid:
        print()
        print("FAILED COMMANDS:")
        print()
        for name, error in invalid:
            print(f"  ❌ {name}")
            print(f"     {error}")
            print()

        print("TO FIX:")
        print()
        print("  All commands MUST have a '## Implementation' section that shows")
        print("  how the command executes. Without this section, commands only")
        print("  display documentation without actually running (silent failure).")
        print()
        print("  This is Issue #13 - Commands without Implementation sections cause")
        print("  user confusion: 'The command doesn't do anything!'")
        print()
        print("  Add one of these patterns to your ## Implementation section:")
        print()
        print("  1. Direct bash commands:")
        print("     ## Implementation")
        print("     ```bash")
        print("     pytest tests/ --cov=src -v")
        print("     ```")
        print()
        print("  2. Script execution:")
        print("     ## Implementation")
        print("     ```bash")
        print('     python "$(dirname "$0")/../scripts/your_script.py"')
        print("     ```")
        print()
        print("  3. Agent invocation:")
        print("     ## Implementation")
        print("     Invoke the [agent-name] agent to [what it does].")
        print()
        print("  See templates/command-template.md for full guidance.")
        print()

        sys.exit(1)

    print()
    print("✅ ALL COMMANDS HAVE PROPER IMPLEMENTATIONS!")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
