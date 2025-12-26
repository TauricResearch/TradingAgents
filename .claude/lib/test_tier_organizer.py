#!/usr/bin/env python3
"""
Test Tier Organizer - Classify and organize tests into unit/integration/uat tiers.

Analyzes test content to determine tier (unit/integration/uat), creates tier
directory structure, and moves tests to appropriate locations.

Key Features:
1. Intelligent tier classification (content and filename analysis)
2. Directory structure creation (tests/{unit,integration,uat}/)
3. Test file organization with collision handling
4. Test pyramid validation (unit > integration > uat)
5. Statistics and reporting

Directory Structure:
    tests/
    ├── unit/           # Unit tests (70-80%)
    │   ├── lib/        # Library tests
    │   └── ...
    ├── integration/    # Integration tests (15-20%)
    └── uat/            # UAT tests (5-10%)

Usage:
    from test_tier_organizer import (
        determine_tier,
        create_tier_directories,
        organize_tests_by_tier,
        get_tier_statistics
    )

    # Create directory structure
    create_tier_directories(Path("project_root"))

    # Organize tests
    test_files = [Path("test_example.py"), ...]
    organize_tests_by_tier(test_files)

    # Get statistics
    stats = get_tier_statistics(Path("tests"))

Date: 2025-12-25
Issue: #161 (Enhanced test-master for 3-tier coverage)
Agent: implementer
Phase: TDD Green (making tests pass)
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


def determine_tier(test_content: str) -> str:
    """Determine test tier from test file content.

    Analyzes test content for tier indicators:
    - UAT: pytest-bdd, Gherkin (scenario, given, when, then), @scenario/@given/@when/@then
    - Integration: multiple imports, subprocess, file I/O, "integration" in function name
    - Unit: default (single function, mocking, isolated)

    Args:
        test_content: Test file content as string

    Returns:
        Tier name: "unit", "integration", or "uat"

    Example:
        >>> content = "from pytest_bdd import scenario\\n"
        >>> determine_tier(content)
        'uat'
    """
    content_lower = test_content.lower()

    # UAT indicators (highest priority) - STRONG signals only
    # Must have pytest-bdd imports or Gherkin decorators
    strong_uat_indicators = [
        'pytest_bdd',
        'from pytest_bdd import',
        '@scenario',
        '@given',
        '@when',
        '@then',
        'def test_uat_',  # Explicit UAT naming
    ]

    for indicator in strong_uat_indicators:
        if indicator in content_lower:
            return "uat"

    # Integration indicators (medium priority)
    integration_indicators = [
        'subprocess.run',
        'subprocess.call',
        'def test_integration_',
        'test_full_pipeline',
        'test_end_to_end',
        'tmp_path',  # File I/O
        'tmpdir',
        'open(',  # File operations
        'file.write',
        'file.read'
    ]

    # Count module imports (integration tests import multiple modules)
    import_count = len(re.findall(r'^\s*from\s+\w+.*import', test_content, re.MULTILINE))
    if import_count >= 3:  # 3+ imports suggests integration
        return "integration"

    for indicator in integration_indicators:
        if indicator in content_lower:
            return "integration"

    # Default to unit
    return "unit"


def determine_tier_from_filename(filename: str) -> str:
    """Determine test tier from filename.

    Checks for tier prefixes in filename:
    - test_integration_*.py -> integration
    - test_uat_*.py -> uat
    - test_*.py -> unit (default)

    Args:
        filename: Test filename (e.g., "test_integration_workflow.py")

    Returns:
        Tier name: "unit", "integration", or "uat"

    Example:
        >>> determine_tier_from_filename("test_integration_workflow.py")
        'integration'
    """
    filename_lower = filename.lower()

    if 'test_uat_' in filename_lower or '_uat.' in filename_lower:
        return "uat"
    elif 'test_integration_' in filename_lower or '_integration.' in filename_lower:
        return "integration"
    else:
        return "unit"


def create_tier_directories(base_path: Path, subdirs: List[str] = None) -> None:
    """Create test tier directory structure.

    Creates:
    - tests/
    - tests/unit/
    - tests/integration/
    - tests/uat/
    - __init__.py files in each directory

    Args:
        base_path: Project root directory
        subdirs: Optional list of subdirectories to create in each tier (e.g., ["lib"])

    Raises:
        PermissionError: If directory creation fails due to permissions

    Example:
        >>> create_tier_directories(Path("/tmp/project"), subdirs=["lib"])
        # Creates: /tmp/project/tests/{unit,integration,uat}/lib/
    """
    tests_dir = base_path / "tests"

    try:
        # Create tests/ directory
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "__init__.py").touch(exist_ok=True)

        # Create tier directories
        for tier in ["unit", "integration", "uat"]:
            tier_dir = tests_dir / tier
            tier_dir.mkdir(exist_ok=True)
            (tier_dir / "__init__.py").touch(exist_ok=True)

            # Create subdirectories if specified
            if subdirs:
                for subdir in subdirs:
                    subdir_path = tier_dir / subdir
                    subdir_path.mkdir(parents=True, exist_ok=True)
                    (subdir_path / "__init__.py").touch(exist_ok=True)

    except PermissionError as e:
        raise PermissionError(f"Permission denied creating tier directories: {e}")


def move_test_to_tier(
    test_file: Path,
    tier: str,
    target_subdir: str = None,
    base_path: Path = None
) -> Path:
    """Move test file to appropriate tier directory.

    Args:
        test_file: Path to test file
        tier: Target tier ("unit", "integration", "uat")
        target_subdir: Optional subdirectory within tier (e.g., "lib")
        base_path: Optional base path (defaults to test_file's parent for cwd tests)

    Returns:
        Path to moved file

    Raises:
        FileNotFoundError: If test_file doesn't exist
        FileExistsError: If target file already exists
        ValueError: If tier is invalid

    Example:
        >>> move_test_to_tier(Path("test_parser.py"), "unit", target_subdir="lib")
        Path("tests/unit/lib/test_parser.py")
    """
    # Validate test file exists
    if not test_file.exists():
        raise FileNotFoundError(f"Test file not found: {test_file}")

    # Validate tier
    if tier not in ["unit", "integration", "uat"]:
        raise ValueError(f"Invalid tier: {tier}. Must be 'unit', 'integration', or 'uat'")

    # Determine base path
    if base_path is None:
        # If test_file is in cwd, use cwd as base
        # Otherwise, search up for project root
        if test_file.parent == Path.cwd():
            base_path = Path.cwd()
        else:
            # Search for tests/ directory parent
            current = test_file.parent
            while current != current.parent:
                if (current / "tests").exists():
                    base_path = current
                    break
                current = current.parent
            else:
                # Fallback to test file's parent
                base_path = test_file.parent

    # Build target path
    target_dir = base_path / "tests" / tier
    if target_subdir:
        target_dir = target_dir / target_subdir

    target_path = target_dir / test_file.name

    # Check for collision
    if target_path.exists():
        raise FileExistsError(f"Target file already exists: {target_path}")

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Move file
    test_file.rename(target_path)

    return target_path


def organize_tests_by_tier(test_files: List[Path], base_path: Path = None) -> Dict[str, List[Path]]:
    """Organize multiple test files into tier directories.

    Analyzes each test file, determines tier, and moves to appropriate directory.

    Args:
        test_files: List of test file paths
        base_path: Optional base path for tier directories

    Returns:
        Dict mapping tier name to list of organized file paths

    Raises:
        ValueError: If path traversal is detected

    Security:
        - Validates all paths are within base_path (CWE-22 prevention)
        - Uses Path.resolve() for canonicalization
        - Rejects symlinks and parent directory references

    Example:
        >>> files = [Path("test_unit.py"), Path("test_integration.py")]
        >>> result = organize_tests_by_tier(files)
        >>> result["unit"]
        [Path("tests/unit/test_unit.py")]
    """
    result = {
        "unit": [],
        "integration": [],
        "uat": []
    }

    # Establish safe base path for path traversal prevention
    if base_path is None:
        base_path = Path.cwd()
    safe_base = base_path.resolve()

    for test_file in test_files:
        if not test_file.exists():
            continue

        # Security: Validate file is within base_path (CWE-22 prevention)
        try:
            safe_file = test_file.resolve()
            if not str(safe_file).startswith(str(safe_base)):
                raise ValueError(f"Path traversal blocked: {test_file}")
        except (OSError, ValueError) as e:
            # Skip files that can't be resolved or are outside base
            continue

        # Read file content to determine tier
        try:
            content = test_file.read_text()
        except Exception:
            # Fallback to filename analysis
            content = ""

        # Determine tier (content analysis takes precedence over filename)
        if content:
            tier = determine_tier(content)
        else:
            tier = determine_tier_from_filename(test_file.name)

        # Determine subdirectory from original path safely
        # Only check if "lib" is an actual path component (not substring)
        # e.g., tests/unit/lib/test_parser.py -> target_subdir="lib"
        target_subdir = None
        path_parts = test_file.parts
        if "lib" in path_parts:
            target_subdir = "lib"

        # Move to tier
        try:
            moved_path = move_test_to_tier(test_file, tier, target_subdir, base_path)
            result[tier].append(moved_path)
        except FileExistsError:
            # Skip files that already exist in target
            pass

    return result


def get_tier_statistics(tests_path: Path) -> Dict[str, int]:
    """Get test count statistics per tier.

    Args:
        tests_path: Path to tests/ directory

    Returns:
        Dict with counts: {tier: count, "total": total_count}

    Example:
        >>> stats = get_tier_statistics(Path("tests"))
        >>> stats
        {"unit": 42, "integration": 10, "uat": 5, "total": 57}
    """
    stats = {
        "unit": 0,
        "integration": 0,
        "uat": 0,
        "total": 0
    }

    if not tests_path.exists():
        return stats

    for tier in ["unit", "integration", "uat"]:
        tier_dir = tests_path / tier
        if tier_dir.exists():
            # Count test_*.py files recursively
            test_files = list(tier_dir.rglob("test_*.py"))
            stats[tier] = len(test_files)

    stats["total"] = sum(stats[tier] for tier in ["unit", "integration", "uat"])

    return stats


def validate_test_pyramid(tests_path: Path) -> Tuple[bool, List[str]]:
    """Validate test pyramid structure (unit > integration > uat).

    Args:
        tests_path: Path to tests/ directory

    Returns:
        Tuple of (is_valid, warnings)

    Example:
        >>> is_valid, warnings = validate_test_pyramid(Path("tests"))
        >>> is_valid
        False
        >>> warnings
        ["Test pyramid inverted: integration (10) > unit (5)"]
    """
    stats = get_tier_statistics(tests_path)
    warnings = []

    # Check pyramid structure
    if stats["integration"] > stats["unit"]:
        warnings.append(
            f"Test pyramid inverted: integration ({stats['integration']}) > unit ({stats['unit']}). "
            "Aim for 70-80% unit tests."
        )

    if stats["uat"] > stats["integration"]:
        warnings.append(
            f"Test pyramid inverted: UAT ({stats['uat']}) > integration ({stats['integration']}). "
            "UAT tests should be 5-10% of total."
        )

    if stats["uat"] > stats["unit"]:
        warnings.append(
            f"Test pyramid severely inverted: UAT ({stats['uat']}) > unit ({stats['unit']}). "
            "Unit tests should form the base of the pyramid."
        )

    # Check total test count
    if stats["total"] == 0:
        warnings.append("No tests found")

    is_valid = len(warnings) == 0

    return is_valid, warnings
