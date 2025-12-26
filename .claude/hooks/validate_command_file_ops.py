#!/usr/bin/env python3
"""
Validate that slash commands with file operations use Python libraries.

This prevents the "sync doesn't work" bug where commands describe file operations
but rely on Claude interpretation instead of executing Python scripts.

Issue: GitHub #127 - /sync command doesn't execute Python dispatcher

File operations MUST use these libraries:
- sync_dispatcher.py - For sync operations
- copy_system.py - For file copying
- file_discovery.py - For file discovery

Run this as part of CI/CD or pre-commit to catch missing library usage.
"""

import sys
import re
from pathlib import Path


# Patterns that indicate DIRECT file operations (not agent-delegated)
# These patterns suggest the command directly manipulates files
FILE_OP_PATTERNS = [
    r'copies\s+\S+\s+to\s+\.claude',  # "Copies X to .claude/"
    r'syncs\s+\S+\s+to\s+\.claude',  # "Syncs X to .claude/"
    r'copy\s+from\s+\S+\s+to\s+\.claude',  # "Copy from X to .claude/"
    r'sync\s+from\s+\S+\s+to\s+\.claude',  # "Sync from X to .claude/"
    r'plugins/autonomous-dev/\S+[`\s]*→[`\s]*\.claude/',  # Direct path mapping (with optional backticks)
    r'/commands/[`\s]*→[`\s]*[`]?\.claude/commands/',  # Arrow mapping commands
    r'/hooks/[`\s]*→[`\s]*[`]?\.claude/hooks/',  # Arrow mapping hooks
    r'/agents/[`\s]*→[`\s]*[`]?\.claude/agents/',  # Arrow mapping agents
    r'Copies.*commands.*from',  # "Copies latest commands from"
]

# Patterns that indicate proper Python library EXECUTION (not just mentions)
# Must be in a bash block or explicit python execution
LIBRARY_EXECUTION_PATTERNS = [
    r'```bash\n[^`]*python[^`]*sync_dispatcher',  # Python execution in bash block
    r'```bash\n[^`]*python[^`]*copy_system',
    r'```bash\n[^`]*python[^`]*file_discovery',
    r'```bash\n[^`]*python[^`]*install_orchestrator',
    r'python\s+\S*sync_dispatcher\.py',  # Direct python execution
    r'python\s+\S*copy_system\.py',
    r'python\s+\S*file_discovery\.py',
    r'python\s+\S*install_orchestrator\.py',
    r'python3\s+\S*sync_dispatcher\.py',
    r'python3\s+\S*copy_system\.py',
]

# Fallback patterns - less strict, for commands that use agents
# which internally call the libraries
LIBRARY_MENTION_PATTERNS = [
    r'sync_dispatcher',
    r'copy_system',
    r'file_discovery',
    r'install_orchestrator',
]

# Commands that are exempt from this check
EXEMPT_COMMANDS = [
    'test.md',  # Testing, not file ops
    'status.md',  # Read-only
]


def has_file_operations(content: str) -> bool:
    """Check if content describes file operations."""
    content_lower = content.lower()

    for pattern in FILE_OP_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            return True

    return False


def uses_python_library_execution(impl_content: str) -> tuple[bool, str]:
    """Check if Implementation section EXECUTES Python libraries (not just mentions).

    Returns:
        (executes_library, warning_message)
    """
    # Check for explicit execution patterns
    for pattern in LIBRARY_EXECUTION_PATTERNS:
        if re.search(pattern, impl_content, re.IGNORECASE | re.DOTALL):
            return True, ""

    # Check if it at least mentions the libraries (warning case)
    for pattern in LIBRARY_MENTION_PATTERNS:
        if re.search(pattern, impl_content, re.IGNORECASE):
            return False, (
                "Command mentions Python library but doesn't execute it. "
                "Add explicit execution: python plugins/autonomous-dev/lib/sync_dispatcher.py"
            )

    # No library usage at all
    return False, (
        "Command performs file operations but doesn't use Python libraries. "
        "Use sync_dispatcher.py, copy_system.py, or file_discovery.py. See Issue #127."
    )


def get_implementation_section(content: str) -> str:
    """Extract the Implementation section from command content."""
    match = re.search(r'## Implementation\n(.+?)(?=\n## |\Z)', content, re.DOTALL)
    if match:
        return match.group(1)
    return ""


def validate_command_file_ops(filepath: Path) -> tuple[bool, str]:
    """
    Validate a command file EXECUTES Python libraries for file operations.

    Returns:
        (is_valid, error_message)
    """
    # Skip exempt commands
    if filepath.name in EXEMPT_COMMANDS:
        return True, ""

    with open(filepath) as f:
        content = f.read()

    # Check if command describes file operations
    if not has_file_operations(content):
        return True, ""  # No file operations, skip

    # Has file operations - check if it EXECUTES Python libraries
    impl_section = get_implementation_section(content)

    if not impl_section:
        # No implementation section - validate_commands.py handles this
        return True, ""

    # Check implementation section for Python library EXECUTION
    executes, error_msg = uses_python_library_execution(impl_section)

    if executes:
        return True, ""

    return False, error_msg


def main():
    """Validate all commands for proper file operation handling."""

    # Find commands directory relative to this script
    script_dir = Path(__file__).parent
    plugin_dir = script_dir.parent
    commands_dir = plugin_dir / "commands"

    if not commands_dir.exists():
        print(f"Commands directory not found: {commands_dir}")
        sys.exit(1)

    print("=" * 70)
    print("COMMAND FILE OPERATIONS VALIDATION")
    print("=" * 70)
    print()
    print("Checking that file operations use Python libraries...")
    print("(sync_dispatcher.py, copy_system.py, file_discovery.py)")
    print()

    command_files = sorted(commands_dir.glob("*.md"))

    if not command_files:
        print(f"No command files found in {commands_dir}")
        sys.exit(1)

    valid = []
    invalid = []
    skipped = []

    for filepath in command_files:
        # Skip archive directory
        if "archive" in str(filepath):
            continue

        is_valid, error = validate_command_file_ops(filepath)

        if is_valid:
            if has_file_operations(open(filepath).read()):
                valid.append(filepath.name)
                print(f"  {filepath.name} - uses Python library")
            else:
                skipped.append(filepath.name)
        else:
            invalid.append((filepath.name, error))
            print(f"  {filepath.name} - MISSING Python library")

    print()
    print("=" * 70)
    print(f"RESULTS: {len(valid)} valid, {len(invalid)} invalid, {len(skipped)} skipped (no file ops)")
    print("=" * 70)

    if invalid:
        print()
        print("FAILED COMMANDS:")
        print()
        for name, error in invalid:
            print(f"  {name}")
            print(f"     {error}")
            print()

        print("TO FIX:")
        print()
        print("  Commands with file operations MUST use Python libraries:")
        print()
        print("  1. For sync operations:")
        print("     python plugins/autonomous-dev/lib/sync_dispatcher.py --mode")
        print()
        print("  2. For file copying:")
        print("     Use copy_system.py or file_discovery.py")
        print()
        print("  3. For installation:")
        print("     Use install_orchestrator.py")
        print()
        print("  DO NOT rely on Claude interpretation for file operations!")
        print("  See Issue #127 for details.")
        print()

        sys.exit(1)

    print()
    print("ALL COMMANDS WITH FILE OPS USE PYTHON LIBRARIES!")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
