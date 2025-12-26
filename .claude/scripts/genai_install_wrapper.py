#!/usr/bin/env python3
"""
GenAI Installation Wrapper - CLI wrapper for GenAI installation libraries

This module provides a CLI interface for setup-wizard Phase 0 GenAI integration,
wrapping the core installation libraries with JSON output for agent consumption.

Key Features:
- check-staging: Validate staging directory
- analyze: Detect installation type
- execute: Perform installation with protected file handling
- cleanup: Remove staging directory
- summary: Generate installation summary report

Usage:
    # Check staging
    python genai_install_wrapper.py check-staging /path/to/staging

    # Analyze installation type
    python genai_install_wrapper.py analyze /path/to/project

    # Execute installation
    python genai_install_wrapper.py execute /path/to/staging /path/to/project fresh

    # Cleanup staging
    python genai_install_wrapper.py cleanup /path/to/staging

    # Generate summary
    python genai_install_wrapper.py summary fresh /path/to/result.json /path/to/project

Date: 2025-12-09
Issue: #109 (GenAI-first installation CLI wrapper)
Agent: implementer
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

# Import installation libraries
try:
    from plugins.autonomous_dev.lib.staging_manager import StagingManager
    from plugins.autonomous_dev.lib.installation_analyzer import (
        InstallationAnalyzer,
        InstallationType,
    )
    from plugins.autonomous_dev.lib.protected_file_detector import (
        ProtectedFileDetector,
        ALWAYS_PROTECTED,
    )
    from plugins.autonomous_dev.lib.copy_system import CopySystem
    from plugins.autonomous_dev.lib.install_audit import InstallAudit
except ImportError:
    # Fallback for testing
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
    from staging_manager import StagingManager
    from installation_analyzer import InstallationAnalyzer
    from protected_file_detector import ProtectedFileDetector
    from copy_system import CopySystem
    from install_audit import InstallAudit


# Critical directories required in staging
CRITICAL_DIRS = [
    "plugins/autonomous-dev/commands",
    "plugins/autonomous-dev/agents",
    "plugins/autonomous-dev/hooks",
    "plugins/autonomous-dev/lib",
]


def check_staging(staging_path: str) -> Dict[str, Any]:
    """Check if staging directory exists and is valid.

    Args:
        staging_path: Path to staging directory

    Returns:
        Dict with:
        - status: "valid", "invalid", or "missing"
        - staging_path: Path to staging (if exists)
        - missing_dirs: List of missing critical directories (if invalid)
        - fallback_needed: True if should skip to Phase 1
        - message: Human-readable message (if missing)
    """
    staging = Path(staging_path)

    # Check if staging exists
    if not staging.exists():
        return {
            "status": "missing",
            "fallback_needed": True,
            "message": "Staging directory not found. Will skip to Phase 1 (manual setup).",
        }

    # Check for critical directories
    missing_dirs = []
    for dir_path in CRITICAL_DIRS:
        if not (staging / dir_path).is_dir():
            missing_dirs.append(dir_path)

    # If missing critical directories, staging is invalid
    if missing_dirs:
        return {
            "status": "invalid",
            "fallback_needed": True,
            "missing_dirs": missing_dirs,
            "message": f"Staging incomplete (missing {len(missing_dirs)} directories). Will skip to Phase 1.",
        }

    # Staging is valid
    return {
        "status": "valid",
        "staging_path": str(staging),
        "fallback_needed": False,
    }


def analyze_installation_type(project_path: str) -> Dict[str, Any]:
    """Analyze installation type for project.

    Args:
        project_path: Path to project directory

    Returns:
        Dict with:
        - type: "fresh", "brownfield", or "upgrade"
        - has_project_md: True if PROJECT.md exists
        - has_claude_dir: True if .claude/ exists
        - existing_files: List of existing plugin files
        - protected_files: List of protected files that shouldn't be overwritten
    """
    project_dir = Path(project_path)

    # Use InstallationAnalyzer
    analyzer = InstallationAnalyzer(project_dir)
    install_type = analyzer.detect_installation_type()

    # Check for PROJECT.md and .claude/
    has_project_md = (project_dir / ".claude" / "PROJECT.md").exists()
    has_claude_dir = (project_dir / ".claude").is_dir()

    # Find existing files
    existing_files = []
    if has_claude_dir:
        for file in (project_dir / ".claude").rglob("*"):
            if file.is_file():
                relative_path = file.relative_to(project_dir)
                existing_files.append(str(relative_path))

    # Check plugins directory
    plugins_dir = project_dir / "plugins" / "autonomous-dev"
    if plugins_dir.is_dir():
        for file in plugins_dir.rglob("*"):
            if file.is_file():
                relative_path = file.relative_to(project_dir)
                existing_files.append(str(relative_path))

    # Detect protected files
    detector = ProtectedFileDetector()
    protected = detector.detect_protected_files(project_dir)
    protected_files = [p["path"] for p in protected]

    return {
        "type": install_type.value,
        "has_project_md": has_project_md,
        "has_claude_dir": has_claude_dir,
        "existing_files": existing_files,
        "protected_files": protected_files,
    }


def execute_installation(
    staging_path: str, project_path: str, install_type: str, test_mode: bool = False
) -> Dict[str, Any]:
    """Execute installation from staging to project.

    Args:
        staging_path: Path to staging directory
        project_path: Path to project directory
        install_type: "fresh", "brownfield", or "upgrade"
        test_mode: If True, skip security validation (for testing)

    Returns:
        Dict with:
        - status: "success" or "error"
        - files_copied: Number of files copied
        - skipped_files: List of protected files that were skipped
        - backups_created: List of backup file paths (for upgrades)
        - error: Error message (if status is "error")
    """
    try:
        staging = Path(staging_path)
        project = Path(project_path)

        # Validate install_type
        valid_types = ["fresh", "brownfield", "upgrade"]
        if install_type not in valid_types:
            return {
                "status": "error",
                "error": f"Invalid install_type: {install_type}. Must be one of: {', '.join(valid_types)}",
            }

        # Validate staging exists
        if not staging.exists():
            return {
                "status": "error",
                "error": f"Staging directory does not exist: {staging}",
            }

        # Create project directory if it doesn't exist
        project.mkdir(parents=True, exist_ok=True)

        # Initialize audit log
        audit_file = project / ".claude" / "install_audit.jsonl"
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        audit = InstallAudit(audit_file)
        install_id = audit.start_installation(install_type)

        # Detect protected files in project
        detector = ProtectedFileDetector()
        protected = detector.detect_protected_files(project)
        protected_paths = [p["path"] for p in protected]

        # Also add ALWAYS_PROTECTED files to the list (even if they don't exist yet in project)
        # This prevents staging files from overwriting them if they exist
        from plugins.autonomous_dev.lib.protected_file_detector import ALWAYS_PROTECTED
        for always_protected in ALWAYS_PROTECTED:
            if always_protected not in protected_paths:
                protected_paths.append(always_protected)

        # Log protected files
        for protected_file in protected:
            audit.record_protected_file(
                install_id, protected_file["path"], protected_file["reason"]
            )

        # Build list of files to copy from staging
        files_to_copy = []
        for file_path in staging.rglob("*"):
            if file_path.is_file() and not file_path.is_symlink():
                files_to_copy.append(file_path.resolve())

        # Copy files with protection
        copier = CopySystem(staging, project)

        # Determine conflict strategy based on install type
        if install_type == "upgrade":
            conflict_strategy = "backup"
            backup_conflicts = True
        else:
            conflict_strategy = "skip"
            backup_conflicts = False

        result = copier.copy_all(
            files=files_to_copy,
            protected_files=protected_paths,
            conflict_strategy=conflict_strategy,
            backup_conflicts=backup_conflicts,
            backup_timestamp=True,
            continue_on_error=False,
        )

        # Log completion
        audit.log_success(
            install_id,
            files_copied=result["files_copied"],
            files_skipped=len(result.get("skipped_files", [])),
            backups_created=len(result.get("backed_up_files", [])),
        )

        # Return success with details
        return {
            "status": "success",
            "files_copied": result["files_copied"],
            "skipped_files": result.get("skipped_files", []),
            "backups_created": [str(b) for b in result.get("backed_up_files", [])],
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def cleanup_staging(staging_path: str) -> Dict[str, Any]:
    """Remove staging directory.

    Args:
        staging_path: Path to staging directory

    Returns:
        Dict with:
        - status: "success"
        - message: Human-readable message
    """
    staging = Path(staging_path)

    # Idempotent - return success if already removed
    if not staging.exists():
        return {
            "status": "success",
            "message": "Staging directory already removed (idempotent).",
        }

    # Remove staging directory
    try:
        manager = StagingManager(staging)
        manager.cleanup()
        return {
            "status": "success",
            "message": f"Staging directory removed: {staging}",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def generate_summary(
    install_type: str, install_result: Dict[str, Any], project_path: str
) -> Dict[str, Any]:
    """Generate installation summary report.

    Args:
        install_type: "fresh", "brownfield", or "upgrade"
        install_result: Result dict from execute_installation
        project_path: Path to project directory

    Returns:
        Dict with:
        - status: "success"
        - summary: Dict with installation details
        - next_steps: List of recommended next steps
    """
    # Parse install_result (may be from JSON file)
    if isinstance(install_result, str):
        result_file = Path(install_result)
        if result_file.exists():
            install_result = json.loads(result_file.read_text())

    # Build summary
    summary = {
        "install_type": install_type,
        "files_copied": install_result.get("files_copied", 0),
        "skipped_files": len(install_result.get("skipped_files", [])),
        "backups_created": len(install_result.get("backups_created", [])),
    }

    # Generate next steps based on install type
    next_steps = []

    if install_type == "fresh":
        next_steps.extend([
            "Run setup wizard to configure PROJECT.md and hooks",
            "Review generated PROJECT.md and customize for your project",
            "Configure environment variables in .env file",
            "Test installation with: /status",
        ])
    elif install_type == "brownfield":
        next_steps.extend([
            f"Review {len(install_result.get('skipped_files', []))} protected files that were preserved",
            "Your PROJECT.md was preserved - review for updates",
            "Test installation with: /status",
            "Run /align-project to check for any conflicts",
        ])
    elif install_type == "upgrade":
        if install_result.get("backups_created"):
            next_steps.extend([
                f"Review {len(install_result.get('backups_created', []))} backup files created",
                "Compare backups with new versions to see changes",
                "Remove backup files once you've reviewed changes",
            ])
        next_steps.extend([
            "Test updated plugin with: /status",
            "Run /health-check to validate plugin integrity",
            "Check release notes for breaking changes",
        ])

    return {
        "status": "success",
        "summary": summary,
        "next_steps": next_steps,
    }


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code: 0 for success, 1 for error
    """
    if len(sys.argv) < 2:
        print(json.dumps({
            "status": "error",
            "error": "Usage: genai_install_wrapper.py <command> [args...]",
            "commands": {
                "check-staging": "check-staging <staging_path>",
                "analyze": "analyze <project_path>",
                "execute": "execute <staging_path> <project_path> <install_type>",
                "cleanup": "cleanup <staging_path>",
                "summary": "summary <install_type> <result_file> <project_path>",
            }
        }))
        return 1

    command = sys.argv[1]

    try:
        if command == "check-staging":
            if len(sys.argv) < 3:
                print(json.dumps({"status": "error", "error": "Missing staging_path"}))
                return 1
            result = check_staging(sys.argv[2])
            print(json.dumps(result))
            return 0

        elif command == "analyze":
            if len(sys.argv) < 3:
                print(json.dumps({"status": "error", "error": "Missing project_path"}))
                return 1
            result = analyze_installation_type(sys.argv[2])
            print(json.dumps(result))
            return 0

        elif command == "execute":
            if len(sys.argv) < 5:
                print(json.dumps({
                    "status": "error",
                    "error": "Missing arguments: execute <staging_path> <project_path> <install_type>"
                }))
                return 1
            result = execute_installation(sys.argv[2], sys.argv[3], sys.argv[4])
            print(json.dumps(result))
            return 0 if result["status"] == "success" else 1

        elif command == "cleanup":
            if len(sys.argv) < 3:
                print(json.dumps({"status": "error", "error": "Missing staging_path"}))
                return 1
            result = cleanup_staging(sys.argv[2])
            print(json.dumps(result))
            return 0

        elif command == "summary":
            if len(sys.argv) < 5:
                print(json.dumps({
                    "status": "error",
                    "error": "Missing arguments: summary <install_type> <result_file> <project_path>"
                }))
                return 1
            result = generate_summary(sys.argv[2], sys.argv[3], sys.argv[4])
            print(json.dumps(result))
            return 0

        else:
            print(json.dumps({
                "status": "error",
                "error": f"Unknown command: {command}",
                "valid_commands": ["check-staging", "analyze", "execute", "cleanup", "summary"]
            }))
            return 1

    except Exception as e:
        print(json.dumps({
            "status": "error",
            "error": str(e),
            "command": command,
        }))
        return 1


if __name__ == "__main__":
    sys.exit(main())
