#!/usr/bin/env python3
"""
Validate Library Imports - Pre-commit Hook

Ensures all hooks and libs can be imported without errors.
Catches broken imports when libraries are deleted or renamed.

Usage:
    python3 validate_lib_imports.py

Exit Codes:
    0 - All imports successful
    1 - Some imports failed
"""

import ast
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Find project root by looking for .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def extract_local_imports(file_path: Path, lib_dir: Path) -> list[str]:
    """Extract local lib imports from a Python file.

    Returns:
        List of local library names that are imported
    """
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
    except SyntaxError:
        return []  # Syntax errors caught elsewhere

    local_imports = []
    lib_names = {f.stem for f in lib_dir.glob("*.py") if f.stem != "__init__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in lib_names:
                    local_imports.append(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                name = node.module.split(".")[0]
                if name in lib_names:
                    local_imports.append(name)

    return local_imports


def validate_lib_imports() -> tuple[bool, list[str]]:
    """Validate all local imports resolve to existing libs.

    Returns:
        Tuple of (success, list of errors)
    """
    project_root = get_project_root()
    plugin_dir = project_root / "plugins" / "autonomous-dev"
    hooks_dir = plugin_dir / "hooks"
    lib_dir = plugin_dir / "lib"

    if not lib_dir.exists():
        return True, []

    # Get all existing lib names
    existing_libs = {f.stem for f in lib_dir.glob("*.py") if f.stem != "__init__"}

    errors = []

    # Check hooks for broken imports
    for hook_file in hooks_dir.glob("*.py"):
        if hook_file.name.startswith("test_"):
            continue
        imports = extract_local_imports(hook_file, lib_dir)
        for imp in imports:
            if imp not in existing_libs:
                errors.append(f"{hook_file.name}: imports missing lib '{imp}'")

    # Check libs for broken cross-imports
    for lib_file in lib_dir.glob("*.py"):
        if lib_file.name.startswith("test_") or lib_file.name == "__init__.py":
            continue
        imports = extract_local_imports(lib_file, lib_dir)
        for imp in imports:
            if imp not in existing_libs:
                errors.append(f"{lib_file.name}: imports missing lib '{imp}'")

    return len(errors) == 0, errors


def main() -> int:
    """Main entry point."""
    success, errors = validate_lib_imports()

    if success:
        print("✅ All library imports valid")
        return 0
    else:
        print("❌ Broken library imports detected!")
        print("")
        print("Errors:")
        for error in sorted(errors):
            print(f"  - {error}")
        print("")
        print("Fix: Either restore the missing lib or update the import")
        return 1


if __name__ == "__main__":
    sys.exit(main())
