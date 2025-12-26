#!/usr/bin/env python3
"""
Install Orchestrator - Coordinates complete installation workflow

This module orchestrates the entire installation process, including:
- Fresh installations
- Upgrades with backup and rollback
- Marketplace directory detection
- Validation and reporting

Key Features:
- Comprehensive file discovery and copying
- Automatic backup before upgrades
- Rollback on failure
- Marketplace directory auto-detection
- Installation marker file tracking
- Validation and coverage reporting

Usage:
    from install_orchestrator import InstallOrchestrator

    # Fresh install
    orchestrator = InstallOrchestrator(plugin_dir, project_dir)
    result = orchestrator.fresh_install()

    # Upgrade install
    result = orchestrator.upgrade_install()

    # Rollback
    orchestrator.rollback(backup_dir)

    # Auto-detect marketplace
    orchestrator = InstallOrchestrator.auto_detect(project_dir)

Date: 2025-11-17
Issue: GitHub #80 (Bootstrap overhaul - Phase 4)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See error-handling-patterns skill for exception handling.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

# Import dependencies - handle both package import and direct script execution
try:
    # Try relative imports first (when used as package)
    from .file_discovery import FileDiscovery
    from .copy_system import CopySystem
    from .installation_validator import InstallationValidator, ValidationResult
    from .security_utils import validate_path, audit_log
except ImportError:
    # Fall back to same-directory imports (when run as script)
    import sys
    from pathlib import Path
    # Add lib directory to path for direct execution
    lib_dir = Path(__file__).parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))

    from file_discovery import FileDiscovery
    from copy_system import CopySystem
    from installation_validator import InstallationValidator
    from security_utils import validate_path, audit_log


class InstallError(Exception):
    """Raised when installation encounters a critical error."""
    pass


@dataclass
class InstallResult:
    """Result of installation operation.

    Attributes:
        status: "success" or "failure"
        files_copied: Number of files copied
        coverage: Coverage percentage (0-100)
        errors: List of error messages
        backup_dir: Optional backup directory path
        customizations_detected: Optional list of user customizations found
        files_added: Optional number of new files added during upgrade
        files_restored: Optional number of files restored during rollback
    """
    status: str
    files_copied: int
    coverage: float
    errors: List[str]
    backup_dir: Optional[Path] = None
    customizations_detected: Optional[int] = None
    customized_files: Optional[List[str]] = None
    files_added: Optional[int] = None
    files_restored: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        if result["backup_dir"]:
            result["backup_dir"] = str(result["backup_dir"])
        return result


class InstallOrchestrator:
    """Orchestrates plugin installation workflow.

    Coordinates file discovery, copying, validation, backup, and rollback.

    Attributes:
        plugin_dir: Path to plugin source directory
        project_dir: Path to project directory
        claude_dir: Path to .claude directory in project
        discovery: FileDiscovery instance
        copy_system: CopySystem instance

    Examples:
        >>> orchestrator = InstallOrchestrator(plugin_dir, project_dir)
        >>> result = orchestrator.fresh_install()
        >>> print(f"Installed {result.files_copied} files")
    """

    def __init__(self, plugin_dir: Path, project_dir: Path):
        """Initialize orchestrator with security validation.

        Args:
            plugin_dir: Plugin source directory
            project_dir: Project directory

        Raises:
            InstallError: If plugin directory doesn't exist
            ValueError: If path validation fails (path traversal, symlink)
        """
        # Validate paths (prevents CWE-22, CWE-59)
        self.plugin_dir = validate_path(
            Path(plugin_dir).resolve(),
            purpose="plugin directory",
            allow_missing=False
        )
        self.project_dir = validate_path(
            Path(project_dir).resolve(),
            purpose="project directory",
            allow_missing=False
        )
        self.claude_dir = self.project_dir / ".claude"

        # Audit log initialization
        audit_log("install_orchestrator", "initialized", {
            "plugin_dir": str(self.plugin_dir),
            "project_dir": str(self.project_dir)
        })

        self.discovery = FileDiscovery(self.plugin_dir)
        # CopySystem will be created per operation with specific source/dest
        self._copy_system_class = CopySystem

    @classmethod
    def from_marketplace(cls, marketplace_dir: Path, project_dir: Path) -> "InstallOrchestrator":
        """Create orchestrator from marketplace directory.

        Marketplace structure:
        ~/.claude/plugins/marketplaces/autonomous-dev/plugins/autonomous-dev/

        Args:
            marketplace_dir: Marketplace root directory
            project_dir: Project directory

        Returns:
            InstallOrchestrator instance

        Raises:
            InstallError: If marketplace directory structure is invalid
        """
        marketplace_dir = Path(marketplace_dir)
        plugin_dir = marketplace_dir / "plugins" / "autonomous-dev"

        if not plugin_dir.exists():
            raise InstallError(
                f"Invalid marketplace structure. Expected: {plugin_dir}"
            )

        return cls(plugin_dir, project_dir)

    @classmethod
    def auto_detect(cls, project_dir: Path) -> "InstallOrchestrator":
        """Auto-detect marketplace directory and create orchestrator.

        Checks common locations:
        - ~/.claude/plugins/marketplaces/autonomous-dev/
        - /usr/local/share/claude/plugins/marketplaces/autonomous-dev/

        Args:
            project_dir: Project directory

        Returns:
            InstallOrchestrator instance

        Raises:
            InstallError: If marketplace directory not found
        """
        home = Path.home()
        search_paths = [
            home / ".claude" / "plugins" / "marketplaces" / "autonomous-dev",
            Path("/usr/local/share/claude/plugins/marketplaces/autonomous-dev"),
        ]

        for marketplace_dir in search_paths:
            if marketplace_dir.exists():
                return cls.from_marketplace(marketplace_dir, project_dir)

        raise InstallError(
            "Could not auto-detect marketplace directory. "
            f"Searched: {', '.join(str(p) for p in search_paths)}"
        )

    def fresh_install(self, progress_callback: Optional[callable] = None, show_progress: bool = False) -> InstallResult:
        """Perform fresh installation.

        Workflow:
        1. Pre-install cleanup (remove .claude/lib/ duplicates)
        2. Discover all files in plugin directory
        3. Copy all files to .claude directory
        4. Set executable permissions on scripts
        5. Create installation marker file
        6. Validate coverage

        Args:
            progress_callback: Optional callback(current, total, message) for progress updates
            show_progress: Whether to print progress to stdout (default: False)

        Returns:
            InstallResult with status and metrics

        Raises:
            InstallError: If installation fails
        """
        from plugins.autonomous_dev.lib.orphan_file_cleaner import OrphanFileCleaner

        errors = []
        backup_dir = None

        # Create backup BEFORE try block if .claude exists (for rollback on failure)
        if self.claude_dir.exists():
            backup_dir = self._create_backup()

        try:
            # Step 1: Pre-install cleanup (remove duplicate libraries)
            cleaner = OrphanFileCleaner(project_root=self.project_dir)
            cleanup_result = cleaner.pre_install_cleanup()

            if not cleanup_result.success:
                # Log warning but continue installation
                errors.append(f"Pre-install cleanup warning: {cleanup_result.error_message}")

            # Step 2: Discover all files
            if progress_callback:
                progress_callback(0, 100, "Discovering plugin files...")

            files = self.discovery.discover_all_files()
            total_files = len(files)

            if total_files == 0:
                raise InstallError("No files discovered in plugin directory")

            if progress_callback:
                progress_callback(10, 100, f"Discovered {total_files} files")

            # Step 3: Ensure .claude directory exists
            self.claude_dir.mkdir(parents=True, exist_ok=True)

            # Step 4: Copy all files using CopySystem
            if progress_callback:
                progress_callback(20, 100, "Installing files...")

            copy_system = CopySystem(self.plugin_dir, self.claude_dir)

            # Create wrapper callback that adds progress display
            def combined_callback(current: int, total: int, message: str):
                if show_progress:
                    percentage = int((current / total) * 100) if total > 0 else 0
                    print(f"[{current}/{total}] {message} ({percentage}%)")
                if progress_callback:
                    progress_callback(current, total, message)

            copy_result = copy_system.copy_all(
                files=files,
                overwrite=True,
                preserve_timestamps=True,
                continue_on_error=False,  # Don't continue on error - we'll rollback
                progress_callback=combined_callback if (show_progress or progress_callback) else None
            )

            files_copied = copy_result["files_copied"]
            if copy_result["errors"] > 0:
                errors.extend(copy_result["error_list"])
                # If there were errors, raise to trigger rollback
                raise InstallError(f"Copy errors occurred: {copy_result['errors']} errors")

            # Step 5: Set executable permissions on scripts
            self._set_executable_permissions()

            # Step 6: Validate coverage
            validator = InstallationValidator(self.plugin_dir, self.claude_dir)
            validation = validator.validate()

            status = "success" if validation.status == "complete" else "failure"

            if validation.status != "complete":
                errors.append(f"Incomplete installation: {validation.coverage}% coverage")
                raise InstallError(f"Incomplete installation: {validation.coverage}% coverage")

            # Step 7: Create installation marker with coverage
            self._create_marker_file(files_copied, validation.coverage)

            return InstallResult(
                status=status,
                files_copied=files_copied,
                coverage=validation.coverage,
                errors=errors,
            )

        except Exception as e:
            # Rollback on failure if backup exists
            if backup_dir and backup_dir.exists():
                if show_progress:
                    print(f"Installation failed, rolling back...")
                try:
                    self.rollback(backup_dir)
                except Exception as rollback_error:
                    raise InstallError(
                        f"Installation failed and rollback failed: {e}, {rollback_error}"
                    )
            raise InstallError(f"Fresh installation failed: {e}")

    def upgrade(self, progress_callback: Optional[callable] = None, show_progress: bool = False) -> InstallResult:
        """Alias for upgrade_install() for backward compatibility."""
        return self.upgrade_install(progress_callback=progress_callback, show_progress=show_progress)

    def upgrade_install(self, progress_callback: Optional[callable] = None, show_progress: bool = False) -> InstallResult:
        """Perform upgrade installation with backup.

        Workflow:
        1. Pre-install cleanup (remove .claude/lib/ duplicates)
        2. Create backup of existing installation
        3. Discover files
        4. Copy files (preserving user customizations if possible)
        5. Set permissions
        6. Update marker file
        7. Validate
        8. On failure: rollback

        Returns:
            InstallResult with backup directory

        Raises:
            InstallError: If upgrade fails and rollback fails
        """
        from plugins.autonomous_dev.lib.orphan_file_cleaner import OrphanFileCleaner

        errors = []
        backup_dir = None

        try:
            # Step 1: Pre-install cleanup (remove duplicate libraries)
            cleaner = OrphanFileCleaner(project_root=self.project_dir)
            cleanup_result = cleaner.pre_install_cleanup()

            if not cleanup_result.success:
                # Log warning but continue installation
                errors.append(f"Pre-install cleanup warning: {cleanup_result.error_message}")

            # Step 2: Create backup
            backup_dir = self._create_backup()

            # Step 3: Discover files
            files = self.discovery.discover_all_files()
            total_files = len(files)

            # Step 4: Detect customizations and prepare file list
            files_to_copy = []
            customized_files = []
            new_files = []

            for source_file in files:
                rel_path = source_file.relative_to(self.plugin_dir)
                dest_file = self.claude_dir / rel_path

                # Track if this is a new file (doesn't exist in destination)
                if not dest_file.exists():
                    new_files.append(str(rel_path))

                # Check if file was customized by user
                if dest_file.exists():
                    # Compare file contents to detect customization
                    source_content = source_file.read_bytes()
                    dest_content = dest_file.read_bytes()
                    if source_content != dest_content:
                        customized_files.append(str(rel_path))

                # Only copy if not preserved or doesn't exist
                if not self._should_preserve(dest_file) or not dest_file.exists():
                    files_to_copy.append(source_file)

            # Use CopySystem for batch copy
            copy_system = CopySystem(self.plugin_dir, self.claude_dir)
            copy_result = copy_system.copy_all(
                files=files_to_copy,
                overwrite=True,
                preserve_timestamps=True,
                continue_on_error=True
            )

            files_copied = copy_result["files_copied"]
            if copy_result["errors"] > 0:
                errors.extend(copy_result["error_list"])

            # Step 5: Set permissions
            self._set_executable_permissions()

            # Step 6: Validate
            validator = InstallationValidator(self.plugin_dir, self.claude_dir)
            validation = validator.validate()

            if validation.status != "complete":
                # Rollback on incomplete installation
                errors.append(f"Validation failed: {validation.coverage}% coverage")
                self.rollback(backup_dir)
                return InstallResult(
                    status="failure",
                    files_copied=0,
                    coverage=0.0,
                    errors=errors,
                    backup_dir=backup_dir,
                )

            # Step 7: Update marker with coverage
            self._create_marker_file(files_copied, validation.coverage)

            return InstallResult(
                status="success",
                files_copied=files_copied,
                coverage=validation.coverage,
                errors=errors,
                backup_dir=backup_dir,
                customizations_detected=len(customized_files),
                customized_files=customized_files,
                files_added=len(new_files),
            )

        except Exception as e:
            if backup_dir:
                try:
                    self.rollback(backup_dir)
                except Exception as rollback_error:
                    raise InstallError(
                        f"Upgrade failed and rollback failed: {e}, {rollback_error}"
                    )
            raise InstallError(f"Upgrade installation failed: {e}")

    def rollback(self, backup_dir: Path) -> InstallResult:
        """Rollback installation from backup.

        Args:
            backup_dir: Path to backup directory

        Returns:
            InstallResult with success or failure status

        Raises:
            InstallError: If rollback fails critically
        """
        backup_dir = Path(backup_dir).resolve()

        if not backup_dir.exists():
            # Gracefully handle missing backup
            return InstallResult(
                status="failure",
                files_copied=0,
                coverage=0.0,
                errors=[f"Backup directory not found: {backup_dir}"],
                backup_dir=backup_dir,
                files_restored=0
            )

        try:
            # CRITICAL: If backup is inside .claude, move it outside first
            # Otherwise rmtree will delete the backup we're trying to restore from
            temp_backup = None
            if backup_dir.is_relative_to(self.claude_dir):
                temp_backup = self.project_dir / backup_dir.name
                shutil.move(str(backup_dir), str(temp_backup))
                backup_dir = temp_backup

            # Remove current installation
            if self.claude_dir.exists():
                shutil.rmtree(self.claude_dir)

            # Restore from backup
            shutil.copytree(backup_dir, self.claude_dir)

            # Count restored files (all files including nested)
            discovery = FileDiscovery(self.claude_dir)
            all_restored_files = discovery.discover_all_files()
            files_restored = len(all_restored_files)

            # Audit log for restoration
            audit_log("install_orchestrator", "rollback_complete", {
                "backup_dir": str(backup_dir),
                "files_restored": files_restored,
                "claude_dir": str(self.claude_dir)
            })

            # Clean up temporary backup if we moved it
            if temp_backup and temp_backup.exists():
                shutil.rmtree(temp_backup)

            return InstallResult(
                status="success",
                files_copied=0,
                coverage=100.0,
                errors=[],
                backup_dir=backup_dir,
                files_restored=files_restored
            )

        except Exception as e:
            return InstallResult(
                status="failure",
                files_copied=0,
                coverage=0.0,
                errors=[f"Rollback failed: {e}"],
                backup_dir=backup_dir,
                files_restored=0
            )

    def _create_backup(self) -> Path:
        """Create backup of existing installation.

        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = self.claude_dir / f".backup-{timestamp}"

        if self.claude_dir.exists():
            # Copy existing installation to backup
            shutil.copytree(
                self.claude_dir,
                backup_dir,
                ignore=shutil.ignore_patterns(".backup-*")
            )

        return backup_dir

    def _set_executable_permissions(self):
        """Set executable permissions on scripts and hooks."""
        executable_patterns = [
            "scripts/*.py",
            "hooks/*.py",
        ]

        for pattern in executable_patterns:
            for file_path in self.claude_dir.glob(pattern):
                if file_path.is_file():
                    # Security: Set explicit permissions (fixes CWE-732)
                    # Use 0o755 (rwxr-xr-x) instead of bitwise OR to prevent
                    # world-writable files
                    file_path.chmod(0o755)

    def _create_marker_file(self, files_installed: int, coverage: float = 100.0):
        """Create installation marker file.

        Args:
            files_installed: Number of files installed
            coverage: Installation coverage percentage
        """
        marker_file = self.claude_dir / ".autonomous-dev-installed"

        metadata = {
            "version": "3.8.0",  # Should match plugin version
            "timestamp": datetime.now().isoformat(),
            "files_installed": files_installed,
            "coverage": coverage,
            "plugin_dir": str(self.plugin_dir),
        }

        with open(marker_file, "w") as f:
            json.dump(metadata, f, indent=2)

    def _should_preserve(self, file_path: Path) -> bool:
        """Check if file should be preserved during upgrade.

        Preserves user customizations in:
        - .env files
        - settings.local.json
        - Custom hooks

        Args:
            file_path: File path to check

        Returns:
            True if file should be preserved
        """
        preserve_patterns = [
            ".env",
            "settings.local.json",
            "custom_hooks/",
        ]

        for pattern in preserve_patterns:
            if pattern in str(file_path):
                return True

        return False


def main():
    """CLI entry point for installation orchestrator."""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Install autonomous-dev plugin")
    parser.add_argument("--plugin-dir", type=Path, help="Plugin source directory")
    parser.add_argument("--project-dir", type=Path, help="Project directory")
    parser.add_argument("--source", type=Path, help="Source plugin directory (alias for --plugin-dir)")
    parser.add_argument("--dest", type=Path, help="Destination project directory (alias for --project-dir)")
    parser.add_argument("--fresh-install", action="store_true", help="Perform fresh installation")
    parser.add_argument("--upgrade", action="store_true", help="Perform upgrade installation")
    parser.add_argument("--mode", choices=["fresh", "upgrade"], help="Installation mode (legacy)")
    parser.add_argument("--show-progress", action="store_true", help="Show progress indicators")
    parser.add_argument("--auto-detect", action="store_true", help="Auto-detect marketplace directory")

    args = parser.parse_args()

    # Handle argument aliases
    plugin_dir = args.plugin_dir or args.source
    project_dir = args.project_dir or args.dest

    if not project_dir:
        print("❌ Error: --project-dir (or --dest) is required", file=sys.stderr)
        return 1

    try:
        # Create orchestrator
        if args.auto_detect:
            orchestrator = InstallOrchestrator.auto_detect(project_dir)
        elif plugin_dir:
            orchestrator = InstallOrchestrator(plugin_dir, project_dir)
        else:
            print("❌ Error: --plugin-dir (or --source) required unless --auto-detect is used", file=sys.stderr)
            return 1

        # Determine mode
        if args.fresh_install or args.mode == "fresh":
            result = orchestrator.fresh_install(show_progress=args.show_progress)
        elif args.upgrade or args.mode == "upgrade":
            result = orchestrator.upgrade_install(show_progress=args.show_progress)
        else:
            # Default to fresh install
            result = orchestrator.fresh_install(show_progress=args.show_progress)

        print(f"{'✅' if result.status == 'success' else '❌'} Installation {result.status}")
        print(f"📊 Files copied: {result.files_copied}")
        print(f"📈 Coverage: {result.coverage}%")

        if result.errors:
            print("\n⚠️ Errors:")
            for error in result.errors:
                print(f"  - {error}")

        return 0 if result.status == "success" else 1

    except InstallError as e:
        print(f"❌ Installation Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected Error: {e}", file=sys.stderr)
        return 1


# CLI interface for standalone usage
if __name__ == "__main__":
    import sys
    sys.exit(main())
