#!/usr/bin/env python3
"""
Codebase Analyzer - Phase 1: Tech stack detection and metrics calculation

This module provides comprehensive codebase analysis:
- Technology stack detection (Python, JavaScript, Go, Rust, Java, etc.)
- File organization analysis (src/, tests/, docs/)
- Code metrics (LOC, file counts, language distribution)
- Testing framework detection
- CI/CD configuration detection
- Documentation detection

Features:
- Multi-language project support
- Extensible tech stack detection
- Detailed metrics and reporting
- Empty project handling
- Security: Path validation and audit logging

Usage:
    from codebase_analyzer import CodebaseAnalyzer, TechStack

    analyzer = CodebaseAnalyzer(project_root="/path/to/project")
    report = analyzer.analyze()

    print(f"Primary language: {report.primary_language}")
    print(f"Tech stacks: {report.tech_stacks}")
    print(f"Total lines: {report.total_lines}")

Date: 2025-11-11
Feature: /align-project-retrofit command (Phase 1)
Agent: implementer


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Import with fallback for both dev (plugins/) and installed (.claude/lib/) environments
try:
    # Development environment
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from plugins.autonomous_dev.lib import security_utils
except ImportError:
    # Installed environment (.claude/lib/)
    import security_utils


class TechStack(Enum):
    """

    See error-handling-patterns skill for exception hierarchy and error handling best practices.

    Supported technology stacks."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    RUBY = "ruby"
    PHP = "php"
    CSHARP = "csharp"
    CPP = "cpp"
    UNKNOWN = "unknown"


# Tech stack detection patterns
TECH_STACK_INDICATORS = {
    TechStack.PYTHON: {
        "files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "setup.cfg", "tox.ini"],
        "extensions": [".py"],
        "dirs": ["__pycache__", ".venv", "venv"],
    },
    TechStack.JAVASCRIPT: {
        "files": ["package.json", "package-lock.json", "yarn.lock", ".npmrc"],
        "extensions": [".js", ".jsx", ".mjs"],
        "dirs": ["node_modules"],
    },
    TechStack.TYPESCRIPT: {
        "files": ["tsconfig.json"],
        "extensions": [".ts", ".tsx"],
        "dirs": ["node_modules"],
    },
    TechStack.GO: {
        "files": ["go.mod", "go.sum"],
        "extensions": [".go"],
        "dirs": ["vendor"],
    },
    TechStack.RUST: {
        "files": ["Cargo.toml", "Cargo.lock"],
        "extensions": [".rs"],
        "dirs": ["target"],
    },
    TechStack.JAVA: {
        "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "extensions": [".java"],
        "dirs": ["target", "build"],
    },
    TechStack.RUBY: {
        "files": ["Gemfile", "Gemfile.lock", ".ruby-version"],
        "extensions": [".rb"],
        "dirs": [],
    },
    TechStack.PHP: {
        "files": ["composer.json", "composer.lock"],
        "extensions": [".php"],
        "dirs": ["vendor"],
    },
}

# Testing framework detection
TESTING_FRAMEWORKS = {
    "pytest": ["pytest.ini", "pyproject.toml", "setup.cfg"],
    "unittest": ["test_*.py", "*_test.py"],
    "jest": ["jest.config.js", "jest.config.ts"],
    "mocha": ["mocha.opts", ".mocharc.js"],
    "go test": ["*_test.go"],
    "cargo test": ["Cargo.toml"],
    "junit": ["pom.xml", "build.gradle"],
    "rspec": ["spec/spec_helper.rb", ".rspec"],
    "phpunit": ["phpunit.xml", "phpunit.xml.dist"],
}

# CI/CD detection
CI_CD_INDICATORS = {
    "github_actions": [".github/workflows"],
    "gitlab_ci": [".gitlab-ci.yml"],
    "travis": [".travis.yml"],
    "circle_ci": [".circleci/config.yml"],
    "jenkins": ["Jenkinsfile"],
    "azure_pipelines": ["azure-pipelines.yml"],
}

# Standard directory patterns
STANDARD_DIRECTORIES = {
    "source": ["src", "lib", "app", "pkg"],
    "tests": ["tests", "test", "__tests__", "spec"],
    "docs": ["docs", "doc", "documentation"],
    "config": ["config", "conf", "cfg"],
    "scripts": ["scripts", "bin"],
    "build": ["build", "dist", "target", "out"],
}

# Files to skip
SKIP_PATTERNS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", ".tox", "dist", "build", "*.egg-info",
    ".DS_Store", "Thumbs.db",
}


@dataclass
class AnalysisReport:
    """Comprehensive codebase analysis report.

    Attributes:
        project_root: Path to analyzed project
        tech_stacks: Detected technology stacks
        primary_language: Primary programming language
        detected_files: Key files detected (config, manifest, etc.)
        testing_frameworks: Detected testing frameworks
        ci_cd_providers: Detected CI/CD providers
        has_ci_cd: Whether CI/CD is configured
        has_tests: Whether project has test files
        directory_structure: Directory organization analysis
        has_source_directory: Whether project has dedicated source directory
        has_test_directory: Whether project has dedicated test directory
        has_docs_directory: Whether project has documentation directory
        structure_type: Structure type (organized, flat, monorepo, etc.)
        file_distribution: File count distribution by directory
        total_files: Total number of files
        total_lines: Total lines of code
        lines_by_language: Lines of code by language (language names, not extensions)
        language_percentages: Language percentage distribution
        file_types: File type distribution
        estimated_test_coverage: Estimated test coverage percentage
        patterns_found: Patterns detected in codebase
        recommendations: Actionable recommendations
        warnings: Warnings about potential issues
        agent_analysis: Analysis from brownfield-analyzer agent
        architecture_style: Architecture style (monolithic, microservices, etc.)
        design_patterns: Detected design patterns
        quality_indicators: Code quality indicators
        metadata: Additional metadata
    """

    project_root: Optional[Path] = None
    tech_stacks: List[TechStack] = field(default_factory=list)
    primary_language: Optional[str] = None
    detected_files: List[str] = field(default_factory=list)
    testing_frameworks: List[str] = field(default_factory=list)
    ci_cd_providers: List[str] = field(default_factory=list)
    has_ci_cd: bool = False
    has_tests: bool = False
    directory_structure: List[str] = field(default_factory=list)
    has_source_directory: bool = False
    has_test_directory: bool = False
    has_docs_directory: bool = False
    structure_type: str = "unknown"
    file_distribution: Dict[str, int] = field(default_factory=dict)
    total_files: int = 0
    total_lines: int = 0
    lines_by_language: Dict[str, int] = field(default_factory=dict)
    language_percentages: Dict[str, float] = field(default_factory=dict)
    file_types: Dict[str, int] = field(default_factory=dict)
    estimated_test_coverage: float = 0.0
    patterns_found: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    agent_analysis: Optional[Dict[str, Any]] = None
    architecture_style: Optional[str] = None
    design_patterns: List[str] = field(default_factory=list)
    quality_indicators: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Auto-generate recommendations and warnings after initialization."""
        # Only generate if not already provided
        if not self.recommendations:
            self._auto_generate_recommendations()
        if not self.warnings:
            self._auto_generate_warnings()

    def _auto_generate_recommendations(self) -> None:
        """Generate actionable recommendations based on analysis data."""
        recommendations = []

        # CI/CD recommendations
        if not self.has_ci_cd:
            recommendations.append("Add CI/CD: Configure automated testing and deployment")

        # Documentation recommendations
        if not self.has_docs_directory:
            recommendations.append("Improve docs: Add documentation directory with README and guides")

        # Testing recommendations
        if not self.has_tests:
            recommendations.append("Add tests: Create test directory and add test coverage")
        elif self.estimated_test_coverage < 50:
            recommendations.append(f"Increase test coverage: Current estimate {self.estimated_test_coverage:.0f}%")

        # Structure recommendations
        if self.structure_type == "flat":
            recommendations.append("Organize structure: Consider organizing code into src/ and tests/ directories")

        self.recommendations = recommendations

    def _auto_generate_warnings(self) -> None:
        """Generate warnings for potential issues."""
        warnings = []

        # Test warnings
        if not self.has_tests:
            warnings.append("No test directory found - consider adding automated tests")

        # Structure warnings
        if self.structure_type == "flat":
            warnings.append("Flat structure detected - may be difficult to maintain as project grows")

        # CI/CD warnings
        if not self.has_ci_cd:
            warnings.append("No CI/CD configuration found - consider adding automated workflows")

        self.warnings = warnings

    def to_dict(self) -> Dict[str, Any]:
        """Serialize report to dictionary."""
        return {
            "project_root": str(self.project_root),
            "tech_stacks": [stack.value for stack in self.tech_stacks],
            "primary_language": self.primary_language,
            "detected_files": self.detected_files,
            "testing_frameworks": self.testing_frameworks,
            "ci_cd_providers": self.ci_cd_providers,
            "has_ci_cd": self.has_ci_cd,
            "has_tests": self.has_tests,
            "directory_structure": self.directory_structure,
            "has_source_directory": self.has_source_directory,
            "has_test_directory": self.has_test_directory,
            "has_docs_directory": self.has_docs_directory,
            "structure_type": self.structure_type,
            "file_distribution": self.file_distribution,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "lines_by_language": self.lines_by_language,
            "language_percentages": self.language_percentages,
            "file_types": self.file_types,
            "estimated_test_coverage": self.estimated_test_coverage,
            "patterns_found": self.patterns_found,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "agent_analysis": self.agent_analysis,
            "architecture_style": self.architecture_style,
            "design_patterns": self.design_patterns,
            "quality_indicators": self.quality_indicators,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize report to JSON string.

        Returns:
            JSON string representation of report
        """
        import json
        return json.dumps(self.to_dict(), indent=2)

    @property
    def summary(self) -> str:
        """Generate human-readable summary of analysis.

        Returns:
            Human-readable summary string
        """
        lines = [
            f"=== Codebase Analysis Report ===",
            f"Project: {self.project_root}",
            f"",
            f"Tech Stack:",
        ]

        if self.tech_stacks:
            for stack in self.tech_stacks:
                # Capitalize language name for display
                lang_name = stack.value.capitalize()
                lines.append(f"  - {lang_name}")
        else:
            lines.append("  - None detected")

        # Capitalize primary language for display
        primary_lang = self.primary_language.capitalize() if self.primary_language else 'Unknown'

        lines.extend([
            f"",
            f"Primary Language: {primary_lang}",
            f"",
            f"Metrics:",
            f"  - {self.total_files} files",
            f"  - {self.total_lines} lines",
            f"  - Estimated Test Coverage: {self.estimated_test_coverage:.1f}%",
            f"",
            f"Structure: {self.structure_type}",
            f"  - Source Directory: {'Yes' if self.has_source_directory else 'No'}",
            f"  - Test Directory: {'Yes' if self.has_test_directory else 'No'}",
            f"  - Docs Directory: {'Yes' if self.has_docs_directory else 'No'}",
        ])

        if self.recommendations:
            lines.append(f"")
            lines.append(f"Recommendations:")
            for rec in self.recommendations:
                lines.append(f"  - {rec}")

        if self.warnings:
            lines.append(f"")
            lines.append(f"Warnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)

    def generate_summary(self) -> str:
        """Generate human-readable summary of analysis (alias for summary property).

        Returns:
            Human-readable summary string
        """
        return self.summary


class CodebaseAnalyzer:
    """Analyze codebase for tech stack, structure, and metrics.

    This class performs comprehensive codebase analysis including:
    - Technology stack detection
    - File organization analysis
    - Code metrics calculation
    - Testing and CI/CD detection

    Attributes:
        project_root: Path to project root directory
    """

    def __init__(self, project_root: Path):
        """Initialize codebase analyzer.

        Args:
            project_root: Path to project root directory

        Raises:
            ValueError: If project_root is invalid or doesn't exist
        """
        self.project_root = Path(project_root).resolve()

        # Validate project root
        try:
            security_utils.validate_path(
                str(project_root),
                purpose="codebase analysis project root",
                allow_missing=False,
            )
        except ValueError as e:
            # Re-raise with clearer message for tests
            raise ValueError(f"Invalid project root: {project_root}") from e

        security_utils.audit_log(
            "codebase_analyzer_init",
            "success",
            {"project_root": str(self.project_root)},
        )

    def analyze(self) -> AnalysisReport:
        """Perform comprehensive codebase analysis.

        Returns:
            AnalysisReport with complete analysis results
        """
        report = AnalysisReport(project_root=self.project_root)

        # Detect tech stacks
        self._detect_tech_stacks(report)

        # Analyze directory structure
        self._analyze_directory_structure(report)

        # Calculate metrics
        self._calculate_metrics(report)

        # Detect testing frameworks
        self._detect_testing_frameworks(report)

        # Detect CI/CD
        self._detect_ci_cd(report)

        # Determine primary language
        self._determine_primary_language(report)

        # Determine structure type
        self._determine_structure_type(report)

        # Recommendations and warnings are auto-generated by __post_init__
        # No need to call explicitly here

        # Invoke agent for enhanced analysis (optional)
        try:
            self._invoke_agent(report)
        except Exception:
            # Agent invocation is optional - don't fail analysis
            pass

        security_utils.audit_log(
            "codebase_analysis_complete",
            "success",
            {
                "project_root": str(self.project_root),
                "tech_stacks": [stack.value for stack in report.tech_stacks],
                "total_files": report.total_files,
                "total_lines": report.total_lines,
            },
        )

        return report

    def _detect_tech_stacks(self, report: AnalysisReport) -> None:
        """Detect technology stacks in project.

        Args:
            report: AnalysisReport to update
        """
        detected_stacks: Set[TechStack] = set()

        for stack, indicators in TECH_STACK_INDICATORS.items():
            # Check for indicator files
            for file_name in indicators["files"]:
                if (self.project_root / file_name).exists():
                    detected_stacks.add(stack)
                    report.detected_files.append(file_name)

            # Check for file extensions (sample files)
            for ext in indicators["extensions"]:
                if list(self.project_root.rglob(f"*{ext}")):
                    detected_stacks.add(stack)

        report.tech_stacks = list(detected_stacks)

    def _analyze_directory_structure(self, report: AnalysisReport) -> None:
        """Analyze project directory structure.

        Args:
            report: AnalysisReport to update
        """
        directories = []

        for item in self.project_root.iterdir():
            if item.is_dir() and item.name not in SKIP_PATTERNS:
                directories.append(item.name)

        report.directory_structure = directories

        # Check for standard directories
        for dir_name in STANDARD_DIRECTORIES["source"]:
            if dir_name in directories:
                report.has_source_directory = True
                break

        for dir_name in STANDARD_DIRECTORIES["tests"]:
            if dir_name in directories:
                report.has_test_directory = True
                break

        for dir_name in STANDARD_DIRECTORIES["docs"]:
            if dir_name in directories:
                report.has_docs_directory = True
                break

    def _calculate_metrics(self, report: AnalysisReport) -> None:
        """Calculate code metrics.

        Args:
            report: AnalysisReport to update
        """
        file_counts: Dict[str, int] = defaultdict(int)
        line_counts_by_ext: Dict[str, int] = defaultdict(int)
        file_type_counts: Dict[str, int] = defaultdict(int)
        total_files = 0
        total_lines = 0
        source_files = 0
        test_files = 0

        # Extension to language mapping
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "c",
        }

        # Walk project directory
        for file_path in self._walk_project():
            # Check if file is binary first
            if self._is_binary_file(file_path):
                continue

            total_files += 1

            # Count by directory
            relative_path = file_path.relative_to(self.project_root)
            if len(relative_path.parts) > 1:
                top_dir = relative_path.parts[0]
                file_counts[top_dir] += 1

                # Track test files
                if "test" in top_dir.lower():
                    test_files += 1
                elif "test" not in str(relative_path).lower():
                    source_files += 1
            else:
                file_counts["root"] += 1
                if "test" in file_path.name.lower():
                    test_files += 1
                else:
                    source_files += 1

            # Count lines
            try:

                content = file_path.read_text(errors="ignore")
                lines = content.count("\n")

                # Only count non-empty files
                if lines > 0:
                    total_lines += lines

                    # Count by file extension (language)
                    ext = file_path.suffix.lower()
                    if ext:
                        file_type_counts[ext] += 1
                        line_counts_by_ext[ext] += lines

            except Exception:
                # Skip files that can't be read
                pass

        # Convert extension counts to language counts
        line_counts_by_language: Dict[str, int] = defaultdict(int)
        for ext, lines in line_counts_by_ext.items():
            lang = ext_to_lang.get(ext, ext.lstrip("."))
            line_counts_by_language[lang] += lines

        report.total_files = total_files
        report.total_lines = total_lines
        report.file_distribution = dict(file_counts)
        report.file_types = dict(file_type_counts)
        report.lines_by_language = dict(line_counts_by_language)
        report.has_tests = test_files > 0

        # Calculate test coverage estimate
        if source_files > 0:
            report.estimated_test_coverage = (test_files / source_files) * 100
            # Cap at 100%
            if report.estimated_test_coverage > 100:
                report.estimated_test_coverage = 100.0
        else:
            report.estimated_test_coverage = 0.0

        # Calculate language percentages
        if total_lines > 0:
            report.language_percentages = {
                lang: (lines / total_lines) * 100
                for lang, lines in line_counts_by_language.items()
            }

    def _detect_testing_frameworks(self, report: AnalysisReport) -> None:
        """Detect testing frameworks.

        Args:
            report: AnalysisReport to update
        """
        detected_frameworks = []

        for framework, patterns in TESTING_FRAMEWORKS.items():
            for pattern in patterns:
                # Check for config files
                if "/" not in pattern:
                    if (self.project_root / pattern).exists():
                        detected_frameworks.append(framework)
                        break
                    # Check for glob patterns
                    if "*" in pattern:
                        if list(self.project_root.rglob(pattern)):
                            detected_frameworks.append(framework)
                            break

        report.testing_frameworks = detected_frameworks

    def _detect_ci_cd(self, report: AnalysisReport) -> None:
        """Detect CI/CD configuration.

        Args:
            report: AnalysisReport to update
        """
        detected_providers = []

        for provider, paths in CI_CD_INDICATORS.items():
            for path in paths:
                if "/" in path:
                    # Directory path
                    if (self.project_root / path).exists():
                        detected_providers.append(provider)
                        break
                else:
                    # File path
                    if (self.project_root / path).exists():
                        detected_providers.append(provider)
                        break

        report.ci_cd_providers = detected_providers
        report.has_ci_cd = len(detected_providers) > 0

    def _determine_primary_language(self, report: AnalysisReport) -> None:
        """Determine primary programming language.

        Args:
            report: AnalysisReport to update
        """
        if not report.lines_by_language:
            report.primary_language = None
            return

        # Find language with most lines of code
        primary_ext = max(report.lines_by_language.items(), key=lambda x: x[1])[0]

        # Map extension to language name
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".cs": "csharp",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
        }

        report.primary_language = extension_map.get(primary_ext, primary_ext.lstrip("."))

    def _determine_structure_type(self, report: AnalysisReport) -> None:
        """Determine project structure type.

        Args:
            report: AnalysisReport to update
        """
        if report.has_source_directory and report.has_test_directory:
            report.structure_type = "organized"
        elif report.total_files == 0:
            report.structure_type = "empty"
        elif len(report.directory_structure) == 0 and report.total_files > 0:
            # Files exist but no subdirectories = flat structure
            report.structure_type = "flat"
        elif not report.has_source_directory and not report.has_test_directory:
            report.structure_type = "flat"
        else:
            report.structure_type = "mixed"


    def _invoke_agent(self, report: AnalysisReport) -> None:
        """Invoke brownfield-analyzer agent for enhanced analysis.

        Args:
            report: AnalysisReport to update
        """
        try:
            # Invoke agent (uses module-level function for testability)
            result = invoke_agent(
                agent_name="brownfield-analyzer",
                task="Analyze codebase structure and patterns",
                context={"project_root": str(self.project_root)},
            )

            if result.get("success"):
                analysis = result.get("analysis", {})
                report.agent_analysis = analysis

                # Extract agent insights
                if "patterns_found" in analysis:
                    report.patterns_found = analysis["patterns_found"]
                if "architecture_style" in analysis:
                    report.architecture_style = analysis["architecture_style"]
                if "design_patterns" in analysis:
                    report.design_patterns = analysis["design_patterns"]
                if "quality_indicators" in analysis:
                    report.quality_indicators = analysis["quality_indicators"]
                if "recommendations" in analysis:
                    # Merge with existing recommendations
                    report.recommendations.extend(analysis["recommendations"])

            else:
                # Agent failed - add warning
                error = result.get("error", "Unknown error")
                report.warnings.append(error)

        except Exception as e:
            # Agent invocation failed - log but don't fail analysis
            report.warnings.append(f"Agent invocation failed: {str(e)}")

            security_utils.audit_log(
                "codebase_analyzer_agent_failed",
                "warning",
                {
                    "project_root": str(self.project_root),
                    "error": str(e),
                },
            )

    def _is_binary_file(self, file_path: Path) -> bool:
        """Check if file is binary (non-text).

        Args:
            file_path: Path to file

        Returns:
            True if binary, False if text
        """
        # Binary file extensions
        binary_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
            ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz",
            ".exe", ".dll", ".so", ".dylib",
            ".pyc", ".pyo", ".class",
            ".woff", ".woff2", ".ttf", ".eot",
        }

        if file_path.suffix.lower() in binary_extensions:
            return True

        # Check first few bytes for binary content
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                # Check for null bytes (strong indicator of binary)
                if b"\x00" in chunk:
                    return True
        except Exception:
            # If we can't read it, assume binary
            return True

        return False

    def _walk_project(self) -> List[Path]:
        """Walk project directory, skipping ignored patterns.

        Returns:
            List of file paths
        """
        files = []

        for item in self.project_root.rglob("*"):
            # Skip if any path component matches skip patterns
            # Check against path parts, not full path string (to avoid false positives like "dist" in "distribution")
            skip_item = False
            for part in item.parts:
                # Skip hidden files and directories (starting with .)
                if part.startswith("."):
                    skip_item = True
                    break
                # Check exact match for directory names
                if part in SKIP_PATTERNS:
                    skip_item = True
                    break
                # Check glob patterns (e.g., "*.egg-info")
                for pattern in SKIP_PATTERNS:
                    if "*" in pattern:
                        import fnmatch
                        if fnmatch.fnmatch(part, pattern):
                            skip_item = True
                            break
                if skip_item:
                    break

            if skip_item:
                continue

            if item.is_file():
                files.append(item)

        return files


# Module-level agent invocation (for mocking in tests)
def invoke_agent(agent_name: str, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke agent for analysis (wrapper for testing).

    Args:
        agent_name: Name of agent to invoke
        task: Task description
        context: Context dictionary

    Returns:
        Agent result dictionary
    """
    from plugins.autonomous_dev.lib.agent_invoker import invoke_agent as _invoke_agent
    return _invoke_agent(agent_name=agent_name, task=task, context=context)


# Convenience function
def analyze_codebase(project_root: Path) -> AnalysisReport:
    """Analyze codebase and return report.

    Args:
        project_root: Path to project root

    Returns:
        AnalysisReport with analysis results
    """
    analyzer = CodebaseAnalyzer(project_root=project_root)
    return analyzer.analyze()
