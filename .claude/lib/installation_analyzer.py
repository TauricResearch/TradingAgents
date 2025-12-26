#!/usr/bin/env python3
"""
Installation Analyzer - Analyze installation type and recommend strategy

This module analyzes project state to determine installation type (fresh,
brownfield, upgrade) and recommends an appropriate installation strategy.

Key Features:
- Installation type detection (fresh/brownfield/upgrade)
- Conflict report generation
- Risk assessment (low/medium/high)
- Strategy recommendation with action items
- Comprehensive analysis reports

Usage:
    from installation_analyzer import InstallationAnalyzer, InstallationType

    # Analyze project
    analyzer = InstallationAnalyzer(project_dir)
    install_type = analyzer.detect_installation_type()
    strategy = analyzer.recommend_strategy()

Date: 2025-12-09
Issue: #106 (GenAI-first installation system)
Agent: implementer

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Import staging manager for conflict detection
try:
    from plugins.autonomous_dev.lib.staging_manager import StagingManager
    from plugins.autonomous_dev.lib.protected_file_detector import ProtectedFileDetector
    from plugins.autonomous_dev.lib.security_utils import audit_log
except ImportError:
    from staging_manager import StagingManager
    from protected_file_detector import ProtectedFileDetector
    from security_utils import audit_log


class InstallationType(Enum):
    """Installation type enumeration."""
    FRESH = "fresh"
    BROWNFIELD = "brownfield"
    UPGRADE = "upgrade"


class InstallationAnalyzer:
    """Analyze installation type and recommend strategy.

    This class analyzes project state to determine installation type and
    recommend an appropriate installation strategy.

    Attributes:
        project_dir: Path to project directory

    Examples:
        >>> analyzer = InstallationAnalyzer(project_dir)
        >>> install_type = analyzer.detect_installation_type()
        >>> print(f"Installation type: {install_type.value}")
    """

    def __init__(self, project_dir: Path | str):
        """Initialize installation analyzer.

        Args:
            project_dir: Path to project directory

        Raises:
            ValueError: If project directory doesn't exist
        """
        project_path = Path(project_dir) if isinstance(project_dir, str) else project_dir
        project_path = project_path.resolve()

        if not project_path.exists():
            raise ValueError(f"Project directory does not exist: {project_path}")

        self.project_dir = project_path

        # Audit log initialization
        audit_log("installation_analyzer", "initialized", {
            "project_dir": str(self.project_dir)
        })

    def detect_installation_type(self) -> InstallationType:
        """Detect installation type based on project state.

        Returns:
            InstallationType enum (FRESH, BROWNFIELD, or UPGRADE)

        Detection Logic:
        - FRESH: No .claude/ directory
        - BROWNFIELD: Has PROJECT.md or user artifacts, but no plugin files
        - UPGRADE: Has existing plugin files (commands, hooks, agents)

        Examples:
            >>> analyzer = InstallationAnalyzer(project_dir)
            >>> install_type = analyzer.detect_installation_type()
        """
        claude_dir = self.project_dir / ".claude"

        # FRESH: No .claude directory
        if not claude_dir.exists():
            return InstallationType.FRESH

        # Check for plugin files
        has_commands = (claude_dir / "commands").exists()
        has_hooks = (claude_dir / "hooks").exists()
        has_agents = (claude_dir / "agents").exists()

        # UPGRADE: Has plugin infrastructure
        if has_commands or has_hooks or has_agents:
            return InstallationType.UPGRADE

        # Check for user artifacts
        has_project_md = (claude_dir / "PROJECT.md").exists()
        has_env = (self.project_dir / ".env").exists()
        has_state = (claude_dir / "batch_state.json").exists()

        # BROWNFIELD: Has user artifacts but no plugin files
        if has_project_md or has_env or has_state:
            return InstallationType.BROWNFIELD

        # Default to FRESH if .claude exists but is empty
        return InstallationType.FRESH

    def generate_conflict_report(self, staging_dir: Path | str) -> Dict[str, Any]:
        """Generate conflict report between staging and project.

        Args:
            staging_dir: Path to staging directory

        Returns:
            Dict with conflict report:
            - total_conflicts: Number of conflicts
            - conflicts: List of conflict dicts
            - conflict_categories: Dict of category counts
            - total_staging_files: Number of files in staging

        Raises:
            ValueError: If staging directory doesn't exist

        Examples:
            >>> report = analyzer.generate_conflict_report(staging_dir)
            >>> print(f"Found {report['total_conflicts']} conflicts")
        """
        staging_path = Path(staging_dir) if isinstance(staging_dir, str) else staging_dir
        staging_path = staging_path.resolve()

        if not staging_path.exists():
            raise ValueError(f"Staging directory not found: {staging_path}")

        # Use StagingManager to detect conflicts
        manager = StagingManager(staging_path)
        conflicts = manager.detect_conflicts(self.project_dir)

        # Use ProtectedFileDetector to categorize conflicts
        detector = ProtectedFileDetector()

        # Categorize each conflict
        categorized_conflicts = []
        category_counts = {}

        for conflict in conflicts:
            file_path = conflict["file"]
            full_path = self.project_dir / file_path

            # Determine category
            category = "modified_plugin"
            if detector.matches_pattern(file_path):
                if file_path.endswith("PROJECT.md") or ".env" in file_path:
                    category = "config"
                elif "custom_" in file_path:
                    category = "custom_hook"

            categorized_conflicts.append({
                **conflict,
                "category": category
            })

            # Count categories
            category_counts[category] = category_counts.get(category, 0) + 1

        # Get total staging files
        staging_files = manager.list_files()

        return {
            "total_conflicts": len(categorized_conflicts),
            "conflicts": categorized_conflicts,
            "conflict_categories": category_counts,
            "total_staging_files": len(staging_files)
        }

    def recommend_strategy(self) -> Dict[str, Any]:
        """Recommend installation strategy based on project state.

        Returns:
            Dict with strategy recommendation:
            - approach: Strategy name (copy_all, skip_protected, backup_and_merge)
            - risk: Risk level (low, medium, high)
            - action_items: List of recommended actions
            - protected_files: List of protected files (if applicable)
            - conflicts: Conflict info (if applicable)
            - manual_review_recommended: True if high risk

        Examples:
            >>> strategy = analyzer.recommend_strategy()
            >>> print(f"Recommended approach: {strategy['approach']}")
        """
        install_type = self.detect_installation_type()

        # FRESH: Simple copy all
        if install_type == InstallationType.FRESH:
            return {
                "approach": "copy_all",
                "risk": "low",
                "action_items": [
                    "Copy all plugin files to .claude/",
                    "No user artifacts to protect"
                ]
            }

        # BROWNFIELD: Skip protected files
        if install_type == InstallationType.BROWNFIELD:
            detector = ProtectedFileDetector()
            protected = detector.detect_protected_files(self.project_dir)

            return {
                "approach": "skip_protected",
                "risk": "low",
                "action_items": [
                    "Copy plugin files to .claude/",
                    f"Skip {len(protected)} protected user files"
                ],
                "protected_files": [f["path"] for f in protected]
            }

        # UPGRADE: Backup and merge
        if install_type == InstallationType.UPGRADE:
            detector = ProtectedFileDetector()
            protected = detector.detect_protected_files(self.project_dir)

            # Assess risk based on number of modifications
            risk_level = "low"
            if len(protected) > 5:
                risk_level = "medium"
            if len(protected) > 15:
                risk_level = "high"

            strategy = {
                "approach": "backup_and_merge",
                "risk": risk_level,
                "action_items": [
                    "Create backups of conflicting files",
                    "Copy new plugin files",
                    f"Preserve {len(protected)} protected files"
                ],
                "conflicts": len(protected)
            }

            # Add manual review recommendation for high risk
            if risk_level == "high":
                strategy["manual_review_recommended"] = True
                strategy["action_items"].append("MANUAL REVIEW RECOMMENDED: Many user modifications detected")

            return strategy

        # Fallback (should not reach here)
        return {
            "approach": "manual",
            "risk": "high",
            "action_items": ["Manual installation recommended"],
            "manual_review_recommended": True
        }

    def assess_risk(self) -> Dict[str, Any]:
        """Assess installation risk.

        Returns:
            Dict with risk assessment:
            - level: Risk level (low, medium, high)
            - data_loss_risk: Boolean indicating data loss risk
            - factors: List of contributing factors
            - protected_files_count: Number of protected files
            - conflicts_count: Estimated conflicts

        Examples:
            >>> risk = analyzer.assess_risk()
            >>> print(f"Risk level: {risk['level']}")
        """
        install_type = self.detect_installation_type()

        # FRESH installation: Low risk
        if install_type == InstallationType.FRESH:
            return {
                "level": "low",
                "data_loss_risk": False,
                "factors": ["No existing files to overwrite"],
                "protected_files_count": 0,
                "conflicts_count": 0
            }

        # Detect protected files
        detector = ProtectedFileDetector()
        protected = detector.detect_protected_files(self.project_dir)

        # BROWNFIELD: Low to medium risk
        if install_type == InstallationType.BROWNFIELD:
            return {
                "level": "low" if len(protected) < 5 else "medium",
                "data_loss_risk": False,  # Protected files preserved
                "factors": [
                    f"{len(protected)} user artifacts will be protected",
                    "No plugin files to conflict with"
                ],
                "protected_files_count": len(protected),
                "conflicts_count": 0
            }

        # UPGRADE: Medium to high risk
        risk_level = "low"
        factors = []

        if len(protected) > 5:
            risk_level = "medium"
            factors.append("Multiple user modifications detected")

        if len(protected) > 15:
            risk_level = "high"
            factors.append("Extensive customizations present")

        return {
            "level": risk_level,
            "data_loss_risk": False,  # Backup strategy prevents data loss
            "factors": factors or ["Some user modifications present"],
            "protected_files_count": len(protected),
            "conflicts_count": len(protected)
        }

    def generate_analysis_report(self, staging_dir: Path | str) -> Dict[str, Any]:
        """Generate comprehensive analysis report.

        Args:
            staging_dir: Path to staging directory

        Returns:
            Dict with complete analysis:
            - timestamp: ISO 8601 timestamp
            - project_dir: Project directory path
            - staging_dir: Staging directory path
            - installation_type: Detected installation type
            - conflicts: Conflict report
            - strategy: Recommended strategy
            - risk: Risk assessment

        Examples:
            >>> report = analyzer.generate_analysis_report(staging_dir)
            >>> print(report["installation_type"])
        """
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "project_dir": str(self.project_dir),
            "staging_dir": str(staging_dir),
            "installation_type": self.detect_installation_type().value,
            "conflicts": self.generate_conflict_report(staging_dir),
            "strategy": self.recommend_strategy(),
            "risk": self.assess_risk()
        }
