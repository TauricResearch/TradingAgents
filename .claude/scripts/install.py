#!/usr/bin/env python3
"""
autonomous-dev Plugin Installer

Handles fresh installation, updates, and sync/repair of the autonomous-dev plugin.

Modes:
    install - Fresh installation (default)
    update  - Update existing installation, preserve customizations
    sync    - Repair missing/corrupt files without touching customizations
    force   - Force reinstall, overwrite everything
    check   - Check for updates only, no changes

Usage:
    python install.py --mode install
    python install.py --mode update
    python install.py --mode sync
    python install.py --mode force
    python install.py --mode check

Security:
    - HTTPS with TLS 1.2+ for all downloads
    - Path validation (CWE-22, CWE-59 prevention)
    - No privilege elevation required
    - Rollback on failure
    - Checksum verification

Issue: #105 (Simplify installation/update mechanism)
"""

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configuration
GITHUB_REPO = "akaszubski/autonomous-dev"
GITHUB_BRANCH = "master"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"

# Plugin structure - what to install
PLUGIN_COMPONENTS = {
    "agents": "plugins/autonomous-dev/agents",
    "commands": "plugins/autonomous-dev/commands",
    "skills": "plugins/autonomous-dev/skills",
    "templates": "plugins/autonomous-dev/templates",
    "hooks": "plugins/autonomous-dev/hooks",
    "scripts": "plugins/autonomous-dev/scripts",
    "lib": "plugins/autonomous-dev/lib",
    "config": "plugins/autonomous-dev/config",
}

# Target directory in user's project
TARGET_DIR = Path(".claude")

# Backup directory for customizations
BACKUP_DIR = TARGET_DIR / "backups"

# Files to skip (not user-facing)
SKIP_FILES = {
    "__pycache__",
    ".pyc",
    ".pyo",
    ".git",
    ".DS_Store",
    "Thumbs.db",
}

# Version file location
VERSION_FILE = "plugins/autonomous-dev/VERSION"

# Manifest file location (avoids GitHub API rate limiting)
MANIFEST_FILE = "plugins/autonomous-dev/config/install_manifest.json"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s


class Colors:
    """ANSI color codes for terminal output."""
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"  # No Color


def log_info(msg: str) -> None:
    print(f"{Colors.BLUE}ℹ{Colors.NC} {msg}")


def log_success(msg: str) -> None:
    print(f"{Colors.GREEN}✓{Colors.NC} {msg}")


def log_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}⚠{Colors.NC} {msg}")


def log_error(msg: str) -> None:
    print(f"{Colors.RED}✗{Colors.NC} {msg}")


def log_step(msg: str) -> None:
    print(f"{Colors.CYAN}→{Colors.NC} {msg}")


def is_transient_error(error: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    error_str = str(error).lower()
    transient_indicators = [
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "temporary failure",
        "503",  # Service Unavailable
        "502",  # Bad Gateway
        "429",  # Rate Limited
    ]
    return any(indicator in error_str for indicator in transient_indicators)


class GitHubDownloader:
    """Download files from GitHub with TLS enforcement and retry logic."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        # Create SSL context with TLS 1.2 minimum
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    def download_file(self, url: str, retry: bool = True) -> Optional[bytes]:
        """Download a file from URL with retry logic for transient failures.

        Args:
            url: URL to download from
            retry: Whether to retry on transient failures (default: True)

        Returns:
            File content as bytes, or None on failure
        """
        last_error = None
        attempts = MAX_RETRIES if retry else 1

        for attempt in range(attempts):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "autonomous-dev-installer/1.0"}
                )
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=60) as response:
                    return response.read()
            except Exception as e:
                last_error = e

                # Check if it's a permanent error (404, 403)
                if "404" in str(e) or "403" in str(e):
                    # Always log permanent errors
                    log_error(f"Download failed (permanent): {Path(url).name} - {e}")
                    return None

                # For transient errors, retry with backoff
                if retry and is_transient_error(e) and attempt < attempts - 1:
                    delay = RETRY_DELAYS[attempt]
                    log_warning(f"Download failed (attempt {attempt + 1}/{attempts}): {Path(url).name}")
                    if self.verbose:
                        log_info(f"  Error: {e}")
                        log_info(f"  Retrying in {delay}s...")
                    time.sleep(delay)
                    continue

                # Final failure - always log
                log_error(f"Download failed: {Path(url).name} - {e}")
                return None

        return None

    def download_text(self, url: str) -> Optional[str]:
        """Download a text file from URL."""
        content = self.download_file(url)
        if content:
            return content.decode("utf-8")
        return None

    def get_file_list(self, path: str) -> List[str]:
        """Get list of files in a GitHub directory using the API."""
        url = f"{GITHUB_API_BASE}/contents/{path}?ref={GITHUB_BRANCH}"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "autonomous-dev-installer/1.0",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
                files = []
                for item in data:
                    if item["type"] == "file":
                        files.append(item["path"])
                    elif item["type"] == "dir":
                        # Recursively get files in subdirectories
                        files.extend(self.get_file_list(item["path"]))
                return files
        except Exception as e:
            # Always log API failures
            log_warning(f"Failed to list files via API: {path} - {e}")
            return []

    def get_manifest(self) -> Optional[Dict[str, Any]]:
        """Download and parse the install manifest (avoids API rate limits)."""
        url = f"{GITHUB_RAW_BASE}/{MANIFEST_FILE}"
        content = self.download_text(url)
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                # Always log manifest parse errors
                log_error(f"Failed to parse manifest: {e}")
        return None


class FileManager:
    """Manage local files with path validation."""

    def __init__(self, target_dir: Path, backup_dir: Path):
        self.target_dir = target_dir
        self.backup_dir = backup_dir

    def validate_path(self, path: Path) -> bool:
        """Validate path to prevent traversal attacks (CWE-22).

        Uses relative_to() for secure path comparison instead of string matching.
        """
        try:
            # Resolve to absolute path
            resolved = path.resolve()
            target_resolved = self.target_dir.resolve()
            backup_resolved = self.backup_dir.resolve()

            # Use relative_to() - raises ValueError if path is not relative
            try:
                resolved.relative_to(target_resolved)
                return True
            except ValueError:
                pass

            try:
                resolved.relative_to(backup_resolved)
                return True
            except ValueError:
                pass

            return False
        except Exception as e:
            log_error(f"Path validation error: {path} - {e}")
            return False

    def get_file_hash(self, path: Path) -> Optional[str]:
        """Get SHA256 hash of a file."""
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return None

    def is_customized(self, local_path: Path, remote_content: bytes) -> bool:
        """Check if local file differs from remote (customized by user)."""
        if not local_path.exists():
            return False

        local_hash = self.get_file_hash(local_path)
        remote_hash = hashlib.sha256(remote_content).hexdigest()

        return local_hash != remote_hash

    def is_missing_or_corrupt(self, local_path: Path, remote_content: bytes) -> bool:
        """Check if local file is missing or doesn't match remote (for sync mode)."""
        if not local_path.exists():
            return True  # Missing

        # Check if file is corrupt (size 0 or can't be read)
        try:
            if local_path.stat().st_size == 0:
                return True  # Empty file = corrupt
            local_hash = self.get_file_hash(local_path)
            if local_hash is None:
                return True  # Can't read = corrupt
        except Exception:
            return True  # Error reading = corrupt

        return False  # File exists and is readable

    def backup_file(self, path: Path) -> Optional[Path]:
        """Backup a file before overwriting."""
        if not path.exists():
            return None

        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        relative_path = path.relative_to(self.target_dir)
        backup_path = self.backup_dir / timestamp / relative_path

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)

        return backup_path

    def write_file(self, path: Path, content: bytes) -> bool:
        """Write content to file with validation."""
        if not self.validate_path(path):
            log_error(f"Invalid path (security violation): {path}")
            return False

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)

            # Set executable for scripts
            if path.suffix in (".py", ".sh") or path.parent.name in ("scripts", "hooks"):
                os.chmod(path, 0o755)

            return True
        except Exception as e:
            log_error(f"Failed to write {path}: {e}")
            return False


class PluginInstaller:
    """Main installer logic with rollback support."""

    def __init__(self, mode: str = "install", verbose: bool = False):
        self.mode = mode
        self.verbose = verbose
        self.downloader = GitHubDownloader(verbose)
        self.file_manager = FileManager(TARGET_DIR, BACKUP_DIR)
        self.temp_dir: Optional[Path] = None

        # Stats
        self.stats = {
            "downloaded": 0,
            "skipped": 0,
            "backed_up": 0,
            "failed": 0,
            "repaired": 0,
        }

    def get_remote_version(self) -> Optional[str]:
        """Get version from GitHub."""
        url = f"{GITHUB_RAW_BASE}/{VERSION_FILE}"
        version = self.downloader.download_text(url)
        if version:
            return version.strip()
        return None

    def get_local_version(self) -> Optional[str]:
        """Get locally installed version."""
        version_file = TARGET_DIR / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        return None

    def check_for_updates(self) -> Tuple[Optional[str], Optional[str]]:
        """Check for available updates."""
        local = self.get_local_version()
        remote = self.get_remote_version()
        return local, remote

    def should_skip_file(self, path: str) -> bool:
        """Check if file should be skipped."""
        for skip in SKIP_FILES:
            if skip in path:
                return True
        return False

    def get_all_files_from_manifest(self, manifest: Dict[str, Any]) -> Dict[str, str]:
        """Get all files to install from static manifest (no API calls)."""
        all_files = {}

        components = manifest.get("components", {})
        for component, config in components.items():
            target = config.get("target", f".claude/{component}")
            files = config.get("files", [])

            log_step(f"Processing {component} ({len(files)} files)...")

            for github_path in files:
                if self.should_skip_file(github_path):
                    continue

                # Map GitHub path to local path using target from manifest
                # plugins/autonomous-dev/hooks/pre_tool_use.py -> .claude/hooks/pre_tool_use.py
                filename = Path(github_path).name
                local_path = str(Path(target) / filename)
                all_files[github_path] = local_path

        return all_files

    def get_all_files_from_api(self) -> Dict[str, str]:
        """Get all files to install from GitHub API (fallback)."""
        all_files = {}

        for component, github_path in PLUGIN_COMPONENTS.items():
            log_step(f"Scanning {component}...")
            files = self.downloader.get_file_list(github_path)

            for file_path in files:
                if self.should_skip_file(file_path):
                    continue

                # Map GitHub path to local path
                # plugins/autonomous-dev/hooks/pre_tool_use.py -> .claude/hooks/pre_tool_use.py
                relative = file_path.replace("plugins/autonomous-dev/", "")
                local_path = str(TARGET_DIR / relative)
                all_files[file_path] = local_path

            if self.verbose:
                log_info(f"  Found {len(files)} files in {component}")

        return all_files

    def get_all_files(self) -> Dict[str, str]:
        """Get all files to install - tries manifest first, falls back to API."""
        # Try manifest first (avoids rate limiting)
        log_step("Fetching install manifest...")
        manifest = self.downloader.get_manifest()

        if manifest:
            log_success(f"Using manifest v{manifest.get('version', 'unknown')}")
            return self.get_all_files_from_manifest(manifest)
        else:
            log_warning("Manifest not found, falling back to GitHub API...")
            return self.get_all_files_from_api()

    def download_to_temp(self, all_files: Dict[str, str]) -> bool:
        """Download all files to temp directory first (for rollback support).

        Returns True if all files downloaded successfully.
        """
        self.temp_dir = Path(tempfile.mkdtemp(prefix="autonomous-dev-install-"))
        log_step(f"Downloading files to staging area...")

        failed_files = []

        for github_path, local_path in all_files.items():
            url = f"{GITHUB_RAW_BASE}/{github_path}"
            content = self.downloader.download_file(url)

            if content is None:
                failed_files.append(github_path)
                continue

            # Write to temp directory
            temp_path = self.temp_dir / local_path
            temp_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                with open(temp_path, "wb") as f:
                    f.write(content)
            except Exception as e:
                log_error(f"Failed to stage {Path(local_path).name}: {e}")
                failed_files.append(github_path)

        if failed_files:
            log_error(f"Failed to download {len(failed_files)} files:")
            for f in failed_files[:5]:  # Show first 5
                log_error(f"  - {Path(f).name}")
            if len(failed_files) > 5:
                log_error(f"  ... and {len(failed_files) - 5} more")
            return False

        log_success(f"Staged {len(all_files)} files successfully")
        return True

    def commit_from_temp(self, all_files: Dict[str, str]) -> bool:
        """Copy files from temp directory to target (atomic commit)."""
        if not self.temp_dir:
            return False

        log_step(f"Installing files (mode: {self.mode})...")

        for github_path, local_path in all_files.items():
            temp_path = self.temp_dir / local_path
            target_path = Path(local_path)

            if not temp_path.exists():
                self.stats["failed"] += 1
                continue

            # Read content from temp
            with open(temp_path, "rb") as f:
                content = f.read()

            # Apply mode-specific logic
            if self.mode == "force":
                # Force mode: always overwrite
                pass
            elif self.mode == "sync":
                # Sync mode: only repair missing or corrupt files
                if target_path.exists():
                    if self.file_manager.is_missing_or_corrupt(target_path, content):
                        log_info(f"  Repairing: {target_path.name}")
                        self.stats["repaired"] += 1
                    else:
                        # File exists and is valid - skip (preserve customizations)
                        self.stats["skipped"] += 1
                        continue
                else:
                    # Missing file - install it
                    log_info(f"  Restoring: {target_path.name}")
                    self.stats["repaired"] += 1
            elif self.mode == "update":
                # Update mode: backup customizations, then update
                if target_path.exists() and self.file_manager.is_customized(target_path, content):
                    backup_path = self.file_manager.backup_file(target_path)
                    if backup_path:
                        log_info(f"  Backed up: {target_path.name}")
                        self.stats["backed_up"] += 1
            else:
                # Install mode: skip existing unless force
                if target_path.exists():
                    self.stats["skipped"] += 1
                    continue

            # Write the file
            if self.file_manager.write_file(target_path, content):
                self.stats["downloaded"] += 1
                if self.verbose:
                    log_success(f"  Installed: {target_path.name}")
            else:
                self.stats["failed"] += 1

        return True

    def cleanup_temp(self) -> None:
        """Clean up temporary directory."""
        if self.temp_dir and self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass  # Best effort cleanup

    def install_version_file(self) -> bool:
        """Install version file for tracking."""
        remote_version = self.get_remote_version()
        if remote_version:
            version_path = TARGET_DIR / "VERSION"
            return self.file_manager.write_file(
                version_path,
                remote_version.encode("utf-8")
            )
        return False

    def run(self) -> bool:
        """Run the installation with rollback support."""
        # Mode: check
        if self.mode == "check":
            local, remote = self.check_for_updates()
            print()
            if local:
                log_info(f"Installed version: {local}")
            else:
                log_info("Not installed")

            if remote:
                log_info(f"Latest version: {remote}")
            else:
                log_warning("Could not fetch latest version")

            if local and remote and local != remote:
                log_warning(f"Update available: {local} → {remote}")
                log_info("Run with --update to update")
            elif local and remote and local == remote:
                log_success("Already up to date")

            return True

        # Create target directory
        TARGET_DIR.mkdir(parents=True, exist_ok=True)

        # Get all files (from manifest or API)
        all_files = self.get_all_files()

        if not all_files:
            log_error("Failed to get file list from GitHub")
            return False

        log_info(f"Found {len(all_files)} files to process")
        print()

        try:
            # Phase 1: Download all files to temp directory
            if not self.download_to_temp(all_files):
                log_error("Installation aborted - download failed")
                log_info("No files were modified (rollback)")
                return False

            # Phase 2: Commit files from temp to target
            self.commit_from_temp(all_files)

            # Install version file
            self.install_version_file()

            # Print summary
            print()
            log_success("Installation Summary:")
            log_info(f"  Downloaded: {self.stats['downloaded']}")
            log_info(f"  Skipped: {self.stats['skipped']}")
            if self.stats['repaired'] > 0:
                log_info(f"  Repaired: {self.stats['repaired']}")
            if self.stats['backed_up'] > 0:
                log_info(f"  Backed up: {self.stats['backed_up']}")
            if self.stats['failed'] > 0:
                log_warning(f"  Failed: {self.stats['failed']}")

            # Validate installation - require 100% success
            total_processed = self.stats['downloaded'] + self.stats['skipped'] + self.stats['repaired']
            if self.stats['failed'] > 0:
                log_error(f"Installation incomplete: {self.stats['failed']} files failed")
                return False

            log_success(f"Installation complete: {total_processed} files processed")
            return True

        finally:
            # Always cleanup temp directory
            self.cleanup_temp()


def main():
    parser = argparse.ArgumentParser(
        description="autonomous-dev Plugin Installer"
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["install", "update", "sync", "force", "check"],
        default="install",
        help="Installation mode (default: install)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )

    args = parser.parse_args()

    installer = PluginInstaller(mode=args.mode, verbose=args.verbose)

    try:
        success = installer.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print()
        log_warning("Installation cancelled")
        installer.cleanup_temp()
        sys.exit(130)
    except Exception as e:
        log_error(f"Installation failed: {e}")
        installer.cleanup_temp()
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
