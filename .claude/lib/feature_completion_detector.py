#!/usr/bin/env python3
"""
Feature Completion Detector

Analyzes features against CLAUDE.md, PROJECT.md, and git history to detect
which features may already be complete. This helps avoid duplicate work
in batch processing.

Key Features:
1. Search CLAUDE.md for feature references
2. Search PROJECT.md for completed goals
3. Check git log for related commits
4. Pattern matching for issue numbers and feature descriptions
5. JSON output for command consumption

Usage:
    from feature_completion_detector import FeatureCompletionDetector

    # Create detector
    detector = FeatureCompletionDetector(project_root=Path("/path/to/project"))

    # Check if feature is complete
    result = detector.check_feature("Extract agent-output-formats skill (Issue #62)")

    # Result contains:
    # {
    #   "feature": "Extract agent-output-formats skill (Issue #62)",
    #   "likely_complete": True,
    #   "evidence": [
    #     "Found in CLAUDE.md: 'Issue #62 Phase 1.1 - agent-output-formats skill'",
    #     "Found in git log: commit 'feat: Extract agent-output-formats skill (Issue #62)'"
    #   ],
    #   "confidence": "high"  # high, medium, low
    # }

Author: implementer agent
Date: 2025-11-15
Issue: batch-implement feature fix
Phase: Implementation


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


# ==============================================================================
# Data Classes
# ==============================================================================


@dataclass
class CompletionCheck:
    """Result of checking if a feature is complete.

    Attributes:
        feature: Feature description
        likely_complete: True if feature appears to be complete
        evidence: List of evidence strings supporting the conclusion
        confidence: Confidence level (high, medium, low)
    """
    feature: str
    likely_complete: bool
    evidence: List[str] = field(default_factory=list)
    confidence: str = "low"  # high, medium, low

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "feature": self.feature,
            "likely_complete": self.likely_complete,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


# ==============================================================================
# Main Class
# ==============================================================================


class FeatureCompletionDetector:
    """Detector for identifying already-completed features.

    This class searches CLAUDE.md, PROJECT.md, and git history to determine
    if a feature has already been implemented.

    Attributes:
        project_root: Path to project root directory
    """

    def __init__(self, project_root: Path):
        """Initialize detector.

        Args:
            project_root: Path to project root directory

        Raises:
            ValueError: If project_root is invalid
        """
        self.project_root = Path(project_root)

        # Validate project root exists
        if not self.project_root.exists():
            raise ValueError(f"Project root not found: {self.project_root}")

        if not self.project_root.is_dir():
            raise ValueError(f"Project root is not a directory: {self.project_root}")

    def check_feature(self, feature: str) -> CompletionCheck:
        """Check if a feature is likely complete.

        Args:
            feature: Feature description to check

        Returns:
            CompletionCheck with evidence and confidence level
        """
        evidence = []
        confidence_score = 0

        # Extract issue number if present (e.g., "Issue #62")
        issue_match = re.search(r'Issue\s+#(\d+)', feature, re.IGNORECASE)
        issue_number = issue_match.group(1) if issue_match else None

        # Extract phase if present (e.g., "Phase 1.1", "Phase 2")
        phase_match = re.search(r'Phase\s+([\d.]+)', feature, re.IGNORECASE)
        phase = phase_match.group(1) if phase_match else None

        # 1. Check CLAUDE.md
        claude_md = self.project_root / "CLAUDE.md"
        if claude_md.exists():
            claude_content = claude_md.read_text(encoding="utf-8")

            # Search for issue number
            if issue_number and f"Issue #{issue_number}" in claude_content:
                evidence.append(f"Found 'Issue #{issue_number}' in CLAUDE.md")
                confidence_score += 2

            # Search for phase
            if phase and f"Phase {phase}" in claude_content:
                evidence.append(f"Found 'Phase {phase}' in CLAUDE.md")
                confidence_score += 1

            # Search for key phrases from feature
            keywords = self._extract_keywords(feature)
            for keyword in keywords:
                if keyword.lower() in claude_content.lower():
                    evidence.append(f"Found keyword '{keyword}' in CLAUDE.md")
                    confidence_score += 1

        # 2. Check PROJECT.md
        project_md = self.project_root / ".claude" / "PROJECT.md"
        if project_md.exists():
            project_content = project_md.read_text(encoding="utf-8")

            # Search for issue number
            if issue_number and f"Issue #{issue_number}" in project_content:
                evidence.append(f"Found 'Issue #{issue_number}' in PROJECT.md")
                confidence_score += 2

            # Search for completion markers
            if issue_number:
                completion_patterns = [
                    f"✅.*Issue #{issue_number}",
                    f"✓.*Issue #{issue_number}",
                    f"COMPLETED.*Issue #{issue_number}",
                ]
                for pattern in completion_patterns:
                    if re.search(pattern, project_content, re.IGNORECASE):
                        evidence.append(f"Found completion marker for Issue #{issue_number} in PROJECT.md")
                        confidence_score += 3
                        break

        # 3. Check git log
        git_evidence = self._check_git_log(feature, issue_number)
        if git_evidence:
            evidence.extend(git_evidence)
            confidence_score += len(git_evidence)

        # Determine if likely complete based on evidence
        likely_complete = confidence_score >= 3

        # Determine confidence level
        if confidence_score >= 5:
            confidence = "high"
        elif confidence_score >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        return CompletionCheck(
            feature=feature,
            likely_complete=likely_complete,
            evidence=evidence,
            confidence=confidence,
        )

    def check_all_features(self, features: List[str]) -> List[CompletionCheck]:
        """Check multiple features for completion.

        Args:
            features: List of feature descriptions

        Returns:
            List of CompletionCheck results
        """
        return [self.check_feature(feature) for feature in features]

    def _extract_keywords(self, feature: str) -> List[str]:
        """Extract key phrases from feature description.

        Args:
            feature: Feature description

        Returns:
            List of keywords to search for
        """
        keywords = []

        # Extract quoted strings
        quoted = re.findall(r'"([^"]+)"', feature)
        keywords.extend(quoted)

        # Extract skill names (e.g., "agent-output-formats skill")
        skill_match = re.search(r'([\w-]+)\s+skill', feature, re.IGNORECASE)
        if skill_match:
            keywords.append(skill_match.group(1))

        # Extract agent names (e.g., "test-master agent")
        agent_match = re.search(r'([\w-]+)\s+agent', feature, re.IGNORECASE)
        if agent_match:
            keywords.append(agent_match.group(1))

        # Extract library names (e.g., "security_utils.py")
        library_match = re.search(r'([\w_]+\.py)', feature)
        if library_match:
            keywords.append(library_match.group(1))

        return keywords

    def _check_git_log(self, feature: str, issue_number: Optional[str] = None) -> List[str]:
        """Check git log for related commits.

        Args:
            feature: Feature description
            issue_number: Issue number if present

        Returns:
            List of evidence strings from git log
        """
        evidence = []

        try:
            # Check if we're in a git repo
            git_dir = self.project_root / ".git"
            if not git_dir.exists():
                return evidence

            # Search git log for issue number
            if issue_number:
                result = subprocess.run(
                    ["git", "log", "--all", "--oneline", f"--grep=#{issue_number}"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    commits = result.stdout.strip().split('\n')
                    evidence.append(f"Found {len(commits)} commit(s) mentioning Issue #{issue_number}")

            # Search for keywords in recent commits (last 50)
            keywords = self._extract_keywords(feature)
            for keyword in keywords[:3]:  # Limit to top 3 keywords
                result = subprocess.run(
                    ["git", "log", "--all", "-50", "--oneline", f"--grep={keyword}"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    evidence.append(f"Found commits mentioning '{keyword}'")

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            # Git not available or timeout - skip git checks
            pass

        return evidence


# ==============================================================================
# CLI Entry Point
# ==============================================================================


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python feature_completion_detector.py <feature> [<feature2> ...]")
        print("\nExample:")
        print("  python feature_completion_detector.py 'Extract agent-output-formats skill (Issue #62)'")
        print("\nOutput: JSON with completion check results")
        sys.exit(1)

    features = sys.argv[1:]
    project_root = Path.cwd()

    # Initialize detector
    detector = FeatureCompletionDetector(project_root=project_root)

    try:
        # Check features
        results = detector.check_all_features(features)

        # Output JSON
        output = {
            "results": [r.to_dict() for r in results],
            "total_features": len(features),
            "likely_complete_count": sum(1 for r in results if r.likely_complete),
        }
        print(json.dumps(output, indent=2))

        sys.exit(0)

    except Exception as e:
        error_output = {
            "error": str(e),
            "type": type(e).__name__,
        }
        print(json.dumps(error_output, indent=2))
        sys.exit(1)
