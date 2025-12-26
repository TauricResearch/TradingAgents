#!/usr/bin/env python3
"""
Post-File-Move Hook - Auto-update documentation references

When files are moved, this hook:
1. Detects broken documentation references
2. Offers to auto-update all references
3. Updates markdown links and file paths

Usage:
    # Called automatically after file move by Claude Code
    python hooks/post_file_move.py <old_path> <new_path>

Example:
    python hooks/post_file_move.py debug-local.sh scripts/debug/debug-local.sh
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Tuple


def find_documentation_references(old_path: str, project_root: Path) -> List[Tuple[Path, int, str]]:
    """
    Find all documentation references to the old file path.

    Returns:
        List of (file_path, line_number, line_content) tuples
    """
    references = []

    # Search for file path in all markdown files
    try:
        result = subprocess.run(
            ["grep", "-rn", old_path, "--include=*.md", str(project_root)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                # Parse grep output: file:line:content
                parts = line.split(':', 2)
                if len(parts) == 3:
                    file_path = Path(parts[0])
                    line_num = int(parts[1])
                    content = parts[2]
                    references.append((file_path, line_num, content))

    except subprocess.CalledProcessError:
        pass  # No references found

    return references


def update_references(references: List[Tuple[Path, int, str]], old_path: str, new_path: str) -> int:
    """
    Update all references from old_path to new_path.

    Returns:
        Number of files updated
    """
    files_updated = set()

    for file_path, line_num, content in references:
        # Read file
        file_content = file_path.read_text()

        # Replace all occurrences of old_path with new_path
        updated_content = file_content.replace(old_path, new_path)

        if updated_content != file_content:
            # Write updated content
            file_path.write_text(updated_content)
            files_updated.add(file_path)
            print(f"  ✅ Updated: {file_path.relative_to(file_path.parents[len(file_path.parts)-1])}")

    return len(files_updated)


def get_project_root() -> Path:
    """Find project root directory."""
    current = Path.cwd()

    while current != current.parent:
        if (current / ".git").exists() or (current / "PROJECT.md").exists():
            return current
        current = current.parent

    return Path.cwd()


def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: post_file_move.py <old_path> <new_path>")
        return 1

    old_path = sys.argv[1]
    new_path = sys.argv[2]

    print(f"\n🔍 Checking for documentation references to: {old_path}")

    project_root = get_project_root()

    # Find all references
    references = find_documentation_references(old_path, project_root)

    if not references:
        print(f"✅ No documentation references found")
        return 0

    print(f"\n📝 Found {len(references)} reference(s) in documentation:")
    for file_path, line_num, content in references:
        relative_path = file_path.relative_to(project_root)
        print(f"  - {relative_path}:{line_num}")
        print(f"    {content.strip()[:80]}...")

    print()

    # Ask for confirmation
    response = input(f"Auto-update all references to: {new_path}? [Y/n] ")

    if response.lower() in ['', 'y', 'yes']:
        print("\n🔄 Updating references...")
        files_updated = update_references(references, old_path, new_path)

        print(f"\n✅ Updated {files_updated} file(s)")
        print("\nChanged files:")
        print("Run 'git status' to see changes")
        print("\nDon't forget to stage these changes:")
        print("  git add .")
        return 0
    else:
        print("\n⚠️ Skipped auto-update")
        print("\nManual update needed in:")
        unique_files = set(file_path for file_path, _, _ in references)
        for file_path in unique_files:
            relative_path = file_path.relative_to(project_root)
            print(f"  - {relative_path}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
