#!/usr/bin/env python3
"""
File Organization Enforcer - Keeps project structure clean (GenAI-Enhanced)

This script enforces the standard project structure using intelligent GenAI
analysis instead of rigid pattern matching.

What it does:
- Analyzes file content and context to suggest optimal location
- Reads PROJECT.md for project-specific conventions
- Understands edge cases (setup.py is config, not source code)
- Explains reasoning for each suggestion
- Gracefully falls back to heuristics if GenAI unavailable

Benefits vs rules-based:
- Context-aware: Understands file purpose, not just extension
- Forgiving: Respects project conventions and common patterns
- Educational: Explains why each file belongs where it does
- Adaptable: Learns from PROJECT.md standards

Can run in two modes:
1. Validation mode (default): Reports violations with reasoning
2. Fix mode (--fix): Automatically fixes violations

Usage:
    # Check for violations (with GenAI analysis)
    python hooks/enforce_file_organization.py

    # Auto-fix violations
    python hooks/enforce_file_organization.py --fix

    # Disable GenAI (use heuristics only)
    GENAI_FILE_ORGANIZATION=false python hooks/enforce_file_organization.py

Exit codes:
- 0: Structure correct or successfully fixed
- 1: Violations found (validation mode)
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import List, Tuple, Dict, Optional
try:
    from genai_utils import GenAIAnalyzer, should_use_genai
    from genai_prompts import FILE_ORGANIZATION_PROMPT
except ImportError:
    # When run from different directory, try absolute import
    from hooks.genai_utils import GenAIAnalyzer, should_use_genai
    from hooks.genai_prompts import FILE_ORGANIZATION_PROMPT


def load_structure_template() -> Dict:
    """Load standard project structure template."""
    template_path = Path(__file__).parent.parent / "templates" / "project-structure.json"
    
    if not template_path.exists():
        return get_default_structure()
    
    return json.loads(template_path.read_text())


def get_default_structure() -> Dict:
    """Get default structure if template not found."""
    return {
        "structure": {
            "src/": {"required": True},
            "tests/": {"required": True},
            "docs/": {"required": True},
            "scripts/": {"required": False},
            ".claude/": {"required": True}
        }
    }


def get_project_root() -> Path:
    """Find project root directory."""
    current = Path.cwd()
    
    while current != current.parent:
        if (current / ".git").exists() or (current / "PROJECT.md").exists():
            return current
        current = current.parent
    
    return Path.cwd()


def check_required_directories(project_root: Path, structure: Dict) -> List[str]:
    """Check for missing required directories."""
    missing = []
    
    for dir_name, config in structure.get("structure", {}).items():
        if not dir_name.endswith("/"):
            continue
        
        if config.get("required", False):
            dir_path = project_root / dir_name.rstrip("/")
            if not dir_path.exists():
                missing.append(dir_name)
    
    return missing


def read_project_context(project_root: Path) -> str:
    """Read PROJECT.md and CLAUDE.md for project-specific organization standards."""
    import re
    context_parts = []

    # Read CLAUDE.md for root file policies
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text()

        # Extract root directory section
        root_match = re.search(
            r'##\s*(Root Directory|Root Files|File Organization)\s*\n(.*?)(?=\n##\s|\Z)',
            content,
            re.DOTALL | re.IGNORECASE
        )

        if root_match:
            context_parts.append("Project Standards (from CLAUDE.md):")
            context_parts.append(root_match.group(2).strip()[:400])

    # Read PROJECT.md for file organization section
    project_md = project_root / "PROJECT.md"
    if project_md.exists():
        content = project_md.read_text()

        org_match = re.search(
            r'##\s*(File Organization|Directory Structure|Project Structure)\s*\n(.*?)(?=\n##\s|\Z)',
            content,
            re.DOTALL | re.IGNORECASE
        )

        if org_match:
            context_parts.append("File Organization (from PROJECT.md):")
            context_parts.append(org_match.group(2).strip()[:400])

    if context_parts:
        return "\n\n".join(context_parts)

    return "Standard project structure (src/, tests/, docs/, scripts/)"


def analyze_file_with_genai(
    file_path: Path,
    project_root: Path,
    analyzer: Optional[GenAIAnalyzer] = None
) -> Tuple[str, str]:
    """
    Use GenAI to analyze file and suggest location.

    Returns:
        (suggested_location, reason) tuple
    """
    if not analyzer:
        return heuristic_file_location(file_path)

    # Read file content (first 20 lines)
    try:
        lines = file_path.read_text().split('\n')[:20]
        content_preview = '\n'.join(lines)
    except:
        content_preview = "(binary file or read error)"

    # Get project context
    project_context = read_project_context(project_root)

    # Analyze with GenAI
    response = analyzer.analyze(
        FILE_ORGANIZATION_PROMPT,
        filename=file_path.name,
        extension=file_path.suffix,
        content_preview=content_preview,
        project_context=project_context
    )

    if not response:
        # Fallback to heuristics
        return heuristic_file_location(file_path)

    # Parse response: "LOCATION | reason"
    parts = response.split('|', 1)
    if len(parts) != 2:
        return heuristic_file_location(file_path)

    location = parts[0].strip()
    reason = parts[1].strip()

    return (location, reason)


def heuristic_file_location(file_path: Path) -> Tuple[str, str]:
    """
    Fallback heuristic rules for file organization (used if GenAI unavailable).

    Returns:
        (suggested_location, reason) tuple
    """
    filename = file_path.name

    # Common root files (standard across most projects)
    COMMON_ROOT_FILES = {
        # Essential docs
        "README.md", "CHANGELOG.md", "LICENSE", "LICENSE.md",
        # Community docs
        "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md",
        # Project standards
        "CLAUDE.md", "PROJECT.md",
        # Build/config
        "setup.py", "conftest.py", "pyproject.toml", "package.json",
        "tsconfig.json", "Makefile", "Dockerfile", ".gitignore",
        ".dockerignore", "requirements.txt", "package-lock.json",
        "poetry.lock", "Cargo.toml", "go.mod"
    }

    # Allowed files in root
    if filename in COMMON_ROOT_FILES:
        return ("root", "allowed root file per project standards")

    # Test files
    if filename.startswith("test_") or filename.endswith("_test.py") or "_test." in filename:
        return ("tests/unit/", "test file (heuristic)")

    # Temporary/scratch files
    if filename in ["test.py", "debug.py"] or filename.startswith(("temp", "scratch")):
        return ("DELETE", "temporary or scratch file (heuristic)")

    # Documentation (not in allowed root list)
    if file_path.suffix == ".md":
        return ("docs/", "markdown documentation (heuristic)")

    # Scripts (shell scripts)
    if file_path.suffix in [".sh", ".bash"]:
        return ("scripts/", "shell script (heuristic)")

    # Source code files
    if file_path.suffix in [".py", ".js", ".ts", ".go", ".rs", ".java"]:
        return ("src/", "source code file (heuristic)")

    # Unknown - leave in root
    return ("root", "unknown file type - manual review needed")


def find_misplaced_files(project_root: Path, use_genai: bool = True, verbose: bool = False) -> List[Tuple[Path, str, str]]:
    """
    Find files in root that should be in subdirectories.

    Args:
        project_root: Project root directory
        use_genai: Whether to use GenAI analysis (default: True)
        verbose: Show debug output about GenAI status

    Returns:
        List of (file_path, suggested_location, reason) tuples
    """
    misplaced = []

    # Initialize GenAI analyzer if enabled
    analyzer = None
    genai_enabled = use_genai and should_use_genai("GENAI_FILE_ORGANIZATION")

    if verbose or os.environ.get("DEBUG_GENAI"):
        print("\n🔧 GenAI File Organization Status:", file=sys.stderr)
        print(f"   SDK Requested: {use_genai}", file=sys.stderr)
        print(f"   Feature Flag: {should_use_genai('GENAI_FILE_ORGANIZATION')}", file=sys.stderr)
        print(f"   Final Status: {'ENABLED' if genai_enabled else 'DISABLED (using heuristics)'}", file=sys.stderr)

    if genai_enabled:
        analyzer = GenAIAnalyzer(max_tokens=50)  # Short responses

        if verbose or os.environ.get("DEBUG_GENAI"):
            try:
                from anthropic import Anthropic
                print(f"   Anthropic SDK: AVAILABLE", file=sys.stderr)
            except ImportError:
                print(f"   Anthropic SDK: NOT INSTALLED (will use heuristics)", file=sys.stderr)
                analyzer = None

    # Scan root directory for files
    for file in project_root.iterdir():
        if not file.is_file():
            continue

        # Skip hidden files
        if file.name.startswith('.'):
            continue

        # Analyze file with GenAI or heuristics
        suggested_location, reason = analyze_file_with_genai(file, project_root, analyzer)

        # Skip if suggested location is root
        if suggested_location == "root":
            continue

        misplaced.append((file, suggested_location, reason))

    return misplaced


def create_directory_structure(project_root: Path, structure: Dict) -> None:
    """Create required directories if they don't exist."""
    for dir_name, config in structure.get("structure", {}).items():
        if not dir_name.endswith("/"):
            continue
        
        if config.get("required", False):
            dir_path = project_root / dir_name.rstrip("/")
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories if specified
            subdirs = config.get("subdirectories", {})
            for subdir_name in subdirs.keys():
                subdir_path = dir_path / subdir_name.rstrip("/")
                subdir_path.mkdir(parents=True, exist_ok=True)


def fix_file_organization(project_root: Path, misplaced: List[Tuple[Path, str, str]]) -> None:
    """Move misplaced files to correct locations."""
    for file_path, target_dir, reason in misplaced:
        if target_dir == "DELETE":
            print(f"  🗑️  Deleting: {file_path.name} ({reason})")
            file_path.unlink()
            continue

        target_path = project_root / target_dir / file_path.name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"  📁 Moving: {file_path.name} → {target_dir}")
        print(f"     Reason: {reason}")
        shutil.move(str(file_path), str(target_path))


def validate_structure(project_root: Path, fix: bool = False) -> Tuple[bool, str]:
    """
    Validate project structure against standard template.
    
    Args:
        project_root: Project root directory
        fix: If True, automatically fix violations
    
    Returns:
        (is_valid, message)
    """
    structure = load_structure_template()
    
    # Check required directories
    missing_dirs = check_required_directories(project_root, structure)
    
    # Check for misplaced files
    misplaced_files = find_misplaced_files(project_root)
    
    if not missing_dirs and not misplaced_files:
        return True, "✅ Project structure follows standard organization"
    
    # Report violations
    message = "❌ Project structure violations found:\n\n"
    
    if missing_dirs:
        message += "Missing required directories:\n"
        for dir_name in missing_dirs:
            message += f"  - {dir_name}\n"
        message += "\n"
    
    if misplaced_files:
        message += "Misplaced files:\n"
        for file_path, target, reason in misplaced_files:
            if target == "DELETE":
                message += f"  - {file_path.name} → DELETE ({reason})\n"
            else:
                message += f"  - {file_path.name} → {target} ({reason})\n"
        message += "\n"
    
    # Fix if requested
    if fix:
        message += "Fixing violations...\n\n"
        
        if missing_dirs:
            create_directory_structure(project_root, structure)
            message += "✅ Created missing directories\n"
        
        if misplaced_files:
            fix_file_organization(project_root, misplaced_files)
            message += f"✅ Moved {len(misplaced_files)} files to correct locations\n"
        
        message += "\n✅ Project structure now follows standard organization"
        return True, message
    else:
        message += "Run with --fix to automatically fix these issues:\n"
        message += "  python hooks/enforce_file_organization.py --fix"
        return False, message


def main() -> int:
    """Main entry point."""
    fix_mode = "--fix" in sys.argv
    
    print("🔍 Validating project structure...\n")
    
    project_root = get_project_root()
    is_valid, message = validate_structure(project_root, fix=fix_mode)
    
    print(message)
    print()
    
    if is_valid:
        print("✅ Structure validation PASSED")
        return 0
    else:
        print("❌ Structure validation FAILED")
        print("\nStandard structure:")
        print("  src/        - Source code")
        print("  tests/      - Tests (unit/, integration/, uat/)")
        print("  docs/       - Documentation")
        print("  scripts/    - Utility scripts")
        print("  .claude/    - Claude Code configuration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
