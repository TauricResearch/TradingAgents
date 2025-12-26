#!/usr/bin/env python3
"""
Tech Debt Detector - Proactive Code Quality Issue Detection

This module detects technical debt patterns that impact code quality and maintainability:
- Large files (1500+ LOC warning, 2500+ LOC critical)
- Circular imports (AST-based detection)
- Red test accumulation (failing tests)
- Config proliferation (scattered config files)
- Duplicate directories (naming inconsistencies)
- Dead code (unused imports/functions)
- Complexity issues (McCabe complexity with radon)

Integrated with reviewer checklist at CHECKPOINT 4.2 in /auto-implement workflow.

Security Features:
- Path traversal prevention (CWE-22)
- Symlink resolution for safe path handling (CWE-59)
- Conservative detection (minimize false positives)

Usage:
    from tech_debt_detector import TechDebtDetector, Severity

    # Detect tech debt in project
    detector = TechDebtDetector(project_root="/path/to/project")
    report = detector.analyze()

    # Check for blocking issues
    if report.blocked:
        print("CRITICAL issues found - commit blocked!")
        for issue in report.issues:
            if issue.severity == Severity.CRITICAL:
                print(f"  {issue.message}")

    # Get summary
    print(f"Found {len(report.issues)} issues")
    print(f"Counts: {report.counts}")

Date: 2025-12-25
Issue: GitHub #162 (Tech Debt Detection System)
Agent: implementer
Phase: TDD Green (making tests pass)

Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Set, Optional
from collections import defaultdict

# Try to import radon for complexity analysis (optional dependency)
try:
    from radon.complexity import cc_visit
    from radon.visitors import ComplexityVisitor
    RADON_AVAILABLE = True
except ImportError:
    RADON_AVAILABLE = False


# =============================================================================
# Severity Levels
# =============================================================================

class Severity(Enum):
    """Severity levels for tech debt issues.

    CRITICAL: Blocks workflow (exit code 1 in hooks)
    HIGH: Warning only (exit code 0, show message)
    MEDIUM: Informational (tracked but not blocking)
    LOW: Minor issues (low priority)
    """
    CRITICAL = 4  # Blocks commit
    HIGH = 3      # Warns but allows
    MEDIUM = 2    # Informational
    LOW = 1       # Minor


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TechDebtIssue:
    """Represents a single tech debt issue.

    Attributes:
        category: Type of issue (e.g., "large_file", "circular_import")
        severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)
        file_path: Path to affected file
        metric_value: Measured value (e.g., LOC count, complexity score)
        threshold: Threshold that was exceeded
        message: Human-readable description
        recommendation: Suggested fix

    Examples:
        >>> issue = TechDebtIssue(
        ...     category="large_file",
        ...     severity=Severity.HIGH,
        ...     file_path="/project/big.py",
        ...     metric_value=1800,
        ...     threshold=1500,
        ...     message="File exceeds size threshold",
        ...     recommendation="Split into smaller modules"
        ... )
    """
    category: str
    severity: Severity
    file_path: str
    metric_value: int
    threshold: int
    message: str
    recommendation: str


@dataclass
class TechDebtReport:
    """Aggregated report of all tech debt issues.

    Attributes:
        issues: List of all detected issues
        counts: Count of issues by severity level
        blocked: True if CRITICAL issues found (blocks commit)

    Examples:
        >>> report = TechDebtReport(
        ...     issues=[issue1, issue2],
        ...     counts={Severity.HIGH: 1, Severity.MEDIUM: 1},
        ...     blocked=False
        ... )
    """
    issues: List[TechDebtIssue]
    counts: Dict[Severity, int]
    blocked: bool


# =============================================================================
# Tech Debt Detector
# =============================================================================

class TechDebtDetector:
    """Main class for detecting technical debt patterns.

    Attributes:
        project_root: Root directory of project to analyze
        large_file_warn_threshold: LOC threshold for warning (default: 1000)
        large_file_block_threshold: LOC threshold for blocking (default: 1500)
        complexity_threshold: McCabe complexity threshold (default: 10)
        config_threshold: Config file count threshold (default: 20)
        red_test_threshold: Failing test threshold (default: 5)

    Examples:
        >>> detector = TechDebtDetector(project_root="/path/to/project")
        >>> report = detector.analyze()
        >>> if report.blocked:
        ...     print("Fix CRITICAL issues before committing!")
    """

    # Default directories to exclude from analysis
    DEFAULT_EXCLUDE_DIRS = {
        'venv', '.venv', 'env', '.env',  # Python virtual environments
        'node_modules',                   # Node.js dependencies
        '.git', '.svn', '.hg',           # Version control
        '__pycache__', '.pytest_cache',  # Python cache
        '.mypy_cache', '.ruff_cache',    # Linter caches
        'build', 'dist', 'egg-info',     # Build artifacts
        '.tox', '.nox',                  # Test runners
        'site-packages',                 # Installed packages
        '.idea', '.vscode',              # IDE configs
        'coverage', 'htmlcov',           # Coverage reports
        '.claude',                        # Install target (duplicate of plugins/)
    }

    def __init__(
        self,
        project_root: Path,
        large_file_warn_threshold: int = 1500,
        large_file_block_threshold: int = 2500,
        complexity_threshold: int = 10,
        config_threshold: int = 20,
        red_test_threshold: int = 5,
        exclude_dirs: Set[str] = None,
    ):
        """Initialize tech debt detector.

        Args:
            project_root: Root directory of project to analyze
            large_file_warn_threshold: LOC threshold for warning (default: 1500)
            large_file_block_threshold: LOC threshold for blocking (default: 2500)
            complexity_threshold: McCabe complexity threshold (default: 10)
            config_threshold: Config file count threshold (default: 20)
            red_test_threshold: Failing test threshold (default: 5)
            exclude_dirs: Directories to skip (default: venv, node_modules, .git, etc.)
        """
        # Security: Resolve path to prevent traversal
        self.project_root = Path(project_root).resolve()
        self.large_file_warn_threshold = large_file_warn_threshold
        self.large_file_block_threshold = large_file_block_threshold
        self.complexity_threshold = complexity_threshold
        self.config_threshold = config_threshold
        self.red_test_threshold = red_test_threshold
        self.exclude_dirs = exclude_dirs if exclude_dirs is not None else self.DEFAULT_EXCLUDE_DIRS

    def _should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped based on exclude_dirs.

        Args:
            path: Path to check

        Returns:
            True if path should be skipped
        """
        # Check if any parent directory is in exclude list
        for part in path.parts:
            if part in self.exclude_dirs:
                return True
        return False

    def analyze(self) -> TechDebtReport:
        """Run all tech debt detectors and aggregate results.

        Returns:
            TechDebtReport with all detected issues

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> report = detector.analyze()
            >>> print(f"Found {len(report.issues)} issues")
        """
        all_issues = []

        # Run all detectors
        all_issues.extend(self.detect_large_files())
        all_issues.extend(self.detect_circular_imports())
        all_issues.extend(self.detect_red_test_accumulation())
        all_issues.extend(self.detect_config_proliferation())
        all_issues.extend(self.detect_duplicate_directories())
        all_issues.extend(self.detect_dead_code())
        all_issues.extend(self.calculate_complexity())

        # Count by severity
        counts = defaultdict(int)
        for issue in all_issues:
            counts[issue.severity] += 1

        # Check if blocked (any CRITICAL issues)
        blocked = any(issue.severity == Severity.CRITICAL for issue in all_issues)

        return TechDebtReport(
            issues=all_issues,
            counts=dict(counts),
            blocked=blocked
        )

    def detect_large_files(self) -> List[TechDebtIssue]:
        """Detect files exceeding size thresholds.

        Thresholds:
            - 1500-2499 LOC: HIGH severity (warning)
            - 2500+ LOC: CRITICAL severity (blocks commit)

        Excludes:
            - Test files (test_*.py, *_test.py)
            - Non-Python files

        Returns:
            List of TechDebtIssue objects for large files

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.detect_large_files()
            >>> for issue in issues:
            ...     print(f"{issue.file_path}: {issue.metric_value} LOC")
        """
        issues = []

        # Find all Python files
        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories (venv, node_modules, etc.)
            if self._should_skip_path(py_file):
                continue
            # Skip test files
            if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                continue

            try:
                # Count lines
                with open(py_file, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for _ in f)

                # Check thresholds
                if line_count >= self.large_file_block_threshold:
                    issues.append(TechDebtIssue(
                        category="large_file",
                        severity=Severity.CRITICAL,
                        file_path=str(py_file),
                        metric_value=line_count,
                        threshold=self.large_file_block_threshold,
                        message=f"File has {line_count} lines (critical threshold: {self.large_file_block_threshold})",
                        recommendation="Split this file into smaller, focused modules (aim for <500 LOC per file)"
                    ))
                elif line_count >= self.large_file_warn_threshold:
                    issues.append(TechDebtIssue(
                        category="large_file",
                        severity=Severity.HIGH,
                        file_path=str(py_file),
                        metric_value=line_count,
                        threshold=self.large_file_warn_threshold,
                        message=f"File has {line_count} lines (warning threshold: {self.large_file_warn_threshold})",
                        recommendation="Consider splitting into smaller modules before it grows larger"
                    ))

            except (IOError, OSError):
                # Skip files we can't read (permission errors, etc.)
                continue

        return issues

    def detect_circular_imports(self) -> List[TechDebtIssue]:
        """Detect circular import dependencies using AST analysis.

        Returns:
            List of TechDebtIssue objects for circular imports (CRITICAL severity)

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.detect_circular_imports()
            >>> for issue in issues:
            ...     print(f"Circular import: {issue.file_path}")
        """
        issues = []

        # Build import graph
        import_graph: Dict[str, Set[str]] = defaultdict(set)

        # Parse all Python files
        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories
            if self._should_skip_path(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read(), filename=str(py_file))

                # Get module name relative to project root
                try:
                    rel_path = py_file.relative_to(self.project_root)
                    module_name = str(rel_path.with_suffix('')).replace('/', '.')
                except ValueError:
                    # File not under project_root
                    continue

                # Extract imports
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            import_graph[module_name].add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.level > 0:
                            # Handle relative imports (from .mod import x)
                            # Get package parts from module path
                            module_parts = module_name.rsplit('.', 1)
                            if len(module_parts) > 1:
                                parent_package = module_parts[0]
                                # Build relative module path
                                if node.module:
                                    relative_module = f"{parent_package}.{node.module}"
                                else:
                                    relative_module = parent_package
                                import_graph[module_name].add(relative_module)
                        elif node.module:
                            import_graph[module_name].add(node.module)

            except (IOError, OSError, SyntaxError):
                # Skip files we can't parse
                continue

        # Detect cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node: str, path: List[str]) -> Optional[List[str]]:
            """DFS to detect cycles."""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in import_graph.get(node, []):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, path[:])
                    if cycle:
                        return cycle
                elif neighbor in rec_stack and neighbor in path:
                    # Found cycle - neighbor is in current path
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]

            rec_stack.remove(node)
            return None

        # Check all nodes for cycles
        cycles_found = set()
        for node in import_graph:
            if node not in visited:
                cycle = has_cycle(node, [])
                if cycle:
                    # Normalize cycle (sort to avoid duplicates)
                    cycle_key = tuple(sorted(cycle))
                    if cycle_key not in cycles_found:
                        cycles_found.add(cycle_key)

                        # Create issue for first file in cycle
                        first_module = cycle[0]
                        # Find corresponding file
                        file_path = self.project_root / (first_module.replace('.', '/') + '.py')

                        issues.append(TechDebtIssue(
                            category="circular_import",
                            severity=Severity.CRITICAL,
                            file_path=str(file_path),
                            metric_value=len(cycle),
                            threshold=0,
                            message=f"Circular import detected: {' -> '.join(cycle)}",
                            recommendation="Refactor to break circular dependency (use dependency injection, move shared code to separate module, or use TYPE_CHECKING)"
                        ))

        return issues

    def detect_red_test_accumulation(self) -> List[TechDebtIssue]:
        """Detect accumulation of failing tests.

        Checks for pytest RED markers (@pytest.mark.RED) indicating unimplemented tests.

        Returns:
            List of TechDebtIssue objects for red test accumulation

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.detect_red_test_accumulation()
        """
        issues = []
        red_test_count = 0
        red_test_files = []

        # Find test files with RED markers
        for test_file in self.project_root.rglob("test_*.py"):
            # Skip excluded directories
            if self._should_skip_path(test_file):
                continue
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Count @pytest.mark.RED occurrences
                red_markers = content.count('@pytest.mark.RED')

                if red_markers > 0:
                    red_test_count += red_markers
                    red_test_files.append(str(test_file))

            except (IOError, OSError):
                continue

        # Check threshold
        if red_test_count > self.red_test_threshold:
            issues.append(TechDebtIssue(
                category="red_test_accumulation",
                severity=Severity.HIGH,
                file_path=", ".join(red_test_files[:3]),  # Show first 3
                metric_value=red_test_count,
                threshold=self.red_test_threshold,
                message=f"Found {red_test_count} RED test markers (threshold: {self.red_test_threshold})",
                recommendation="Complete implementation for pending tests or remove obsolete RED markers"
            ))

        return issues

    def detect_config_proliferation(self) -> List[TechDebtIssue]:
        """Detect proliferation of configuration files/classes.

        Looks for:
            - Multiple config.py files per directory
            - Many Config* classes in files

        Returns:
            List of TechDebtIssue objects for config proliferation

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.detect_config_proliferation()
        """
        issues = []

        # Method 1: Count config files per directory
        config_files_by_dir: Dict[str, List[Path]] = defaultdict(list)

        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories
            if self._should_skip_path(py_file):
                continue
            if 'config' in py_file.name.lower():
                parent = str(py_file.parent)
                config_files_by_dir[parent].append(py_file)

        # Check for proliferation of config files
        for directory, config_files in config_files_by_dir.items():
            if len(config_files) >= self.config_threshold:
                issues.append(TechDebtIssue(
                    category="config_proliferation",
                    severity=Severity.MEDIUM,
                    file_path=directory,
                    metric_value=len(config_files),
                    threshold=self.config_threshold,
                    message=f"Found {len(config_files)} config files in {directory}",
                    recommendation="Consolidate configuration into a single config module or use a config management library"
                ))

        # Method 2: Count Config* classes in individual files
        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories
            if self._should_skip_path(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content, filename=str(py_file))

                # Count Config* class definitions
                config_class_count = 0
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name.startswith('Config'):
                        config_class_count += 1

                # Report if excessive in single file
                if config_class_count >= self.config_threshold:
                    issues.append(TechDebtIssue(
                        category="config_proliferation",
                        severity=Severity.MEDIUM,
                        file_path=str(py_file),
                        metric_value=config_class_count,
                        threshold=self.config_threshold,
                        message=f"Found {config_class_count} Config classes in single file",
                        recommendation="Split configuration classes into separate modules or use a configuration management pattern"
                    ))

            except (IOError, OSError, SyntaxError):
                continue

        return issues

    def detect_duplicate_directories(self) -> List[TechDebtIssue]:
        """Detect directories with similar names or content (> 80% similarity).

        Checks for:
            - Singular/plural name patterns (lib/libs, util/utils)
            - Directories with > 80% file overlap

        Returns:
            List of TechDebtIssue objects for duplicate directories

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.detect_duplicate_directories()
        """
        issues = []

        # Get all directories (only direct children to avoid deep nesting noise)
        all_dirs = [d for d in self.project_root.iterdir() if d.is_dir() and not d.name.startswith('.')]

        # Method 1: Check for singular/plural patterns
        duplicate_patterns = [
            ('lib', 'libs'),
            ('util', 'utils'),
            ('helper', 'helpers'),
            ('config', 'configs'),
            ('test', 'tests'),
            ('script', 'scripts'),
        ]

        dir_names = {d.name: d for d in all_dirs}

        for singular, plural in duplicate_patterns:
            if singular in dir_names and plural in dir_names:
                issues.append(TechDebtIssue(
                    category="duplicate_directory",
                    severity=Severity.LOW,
                    file_path=f"{dir_names[singular]}, {dir_names[plural]}",
                    metric_value=2,
                    threshold=1,
                    message=f"Found duplicate directories: '{singular}' and '{plural}'",
                    recommendation=f"Consolidate into single directory (recommend: '{plural}')"
                ))

        # Method 2: Check for file similarity (80%+ overlap)
        def get_filenames(directory: Path) -> Set[str]:
            """Get set of filenames in directory."""
            try:
                return {f.name for f in directory.iterdir() if f.is_file()}
            except (IOError, OSError):
                return set()

        # Compare all directory pairs
        checked_pairs = set()
        for i, dir1 in enumerate(all_dirs):
            for dir2 in all_dirs[i+1:]:
                # Skip if already checked (order-independent)
                pair = tuple(sorted([dir1.name, dir2.name]))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Get filenames
                files1 = get_filenames(dir1)
                files2 = get_filenames(dir2)

                # Skip if either is empty
                if not files1 or not files2:
                    continue

                # Calculate similarity (Jaccard index)
                intersection = files1 & files2
                union = files1 | files2

                if len(union) > 0:
                    similarity = len(intersection) / len(union)

                    # Report if > 80% similar
                    if similarity > 0.8:
                        similarity_pct = int(similarity * 100)
                        issues.append(TechDebtIssue(
                            category="duplicate_directory",
                            severity=Severity.MEDIUM,
                            file_path=f"{dir1}, {dir2}",
                            metric_value=similarity_pct,
                            threshold=80,
                            message=f"Directories '{dir1.name}' and '{dir2.name}' have {similarity_pct}% file overlap (threshold: 80%)",
                            recommendation=f"Consolidate duplicate directories or clearly differentiate their purposes"
                        ))

        return issues

    def detect_dead_code(self) -> List[TechDebtIssue]:
        """Detect dead code (unused imports, unreferenced functions).

        Conservative detection to minimize false positives.

        Returns:
            List of TechDebtIssue objects for dead code

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.detect_dead_code()
        """
        issues = []

        # Detect unused imports and functions
        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories (venv, node_modules, etc.)
            if self._should_skip_path(py_file):
                continue
            # Skip test files (they may have intentional unused code)
            if py_file.name.startswith('test_') or py_file.name.endswith('_test.py'):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content, filename=str(py_file))

                # Get imported names
                imported_names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name
                            imported_names.add(name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name
                            imported_names.add(name)

                # Check if imports are used (simple heuristic: name appears in code)
                unused_imports = []
                for name in imported_names:
                    # Skip special imports
                    if name.startswith('_'):
                        continue

                    # Count occurrences (excluding import statement itself)
                    count = content.count(name)
                    # If name appears only once (the import itself), likely unused
                    if count == 1:
                        unused_imports.append(name)

                # Get function definitions
                function_names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Skip special functions
                        if not node.name.startswith('_'):
                            function_names.add(node.name)

                # Check if functions are called
                unused_functions = []
                for func_name in function_names:
                    # Count calls (function name + '(')
                    call_count = content.count(f"{func_name}(")
                    # If appears only once (the definition), likely unused
                    if call_count == 1:
                        unused_functions.append(func_name)

                # Report if unused imports found (threshold: 2+)
                if len(unused_imports) >= 2:
                    issues.append(TechDebtIssue(
                        category="dead_code",
                        severity=Severity.LOW,
                        file_path=str(py_file),
                        metric_value=len(unused_imports),
                        threshold=1,
                        message=f"Found {len(unused_imports)} potentially unused imports: {', '.join(unused_imports[:5])}",
                        recommendation="Remove unused imports to reduce clutter and confusion"
                    ))

                # Report if unused functions found (threshold: 2+)
                if len(unused_functions) >= 2:
                    issues.append(TechDebtIssue(
                        category="dead_code",
                        severity=Severity.LOW,
                        file_path=str(py_file),
                        metric_value=len(unused_functions),
                        threshold=1,
                        message=f"Found {len(unused_functions)} potentially unused functions: {', '.join(unused_functions[:5])}",
                        recommendation="Remove unused functions or make them private (prefix with _) if intended for future use"
                    ))

            except (IOError, OSError, SyntaxError):
                continue

        return issues

    def calculate_complexity(self) -> List[TechDebtIssue]:
        """Calculate McCabe complexity using radon library.

        Gracefully degrades if radon not installed.

        Severity levels:
            - 11-20: MEDIUM
            - 21-50: HIGH
            - 51+: CRITICAL

        Returns:
            List of TechDebtIssue objects for high complexity functions

        Examples:
            >>> detector = TechDebtDetector(project_root="/project")
            >>> issues = detector.calculate_complexity()
        """
        if not RADON_AVAILABLE:
            # Graceful degradation - radon not installed
            return []

        issues = []

        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories (venv, node_modules, etc.)
            if self._should_skip_path(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Calculate complexity
                complexity_results = cc_visit(content)

                for result in complexity_results:
                    if result.complexity > self.complexity_threshold:
                        # Determine severity based on complexity score
                        if result.complexity > 50:
                            severity = Severity.CRITICAL
                        elif result.complexity > 20:
                            severity = Severity.HIGH
                        else:
                            severity = Severity.MEDIUM

                        issues.append(TechDebtIssue(
                            category="complexity",
                            severity=severity,
                            file_path=f"{py_file}:{result.lineno}",
                            metric_value=result.complexity,
                            threshold=self.complexity_threshold,
                            message=f"Function '{result.name}' has complexity {result.complexity} (threshold: {self.complexity_threshold})",
                            recommendation="Refactor to reduce cyclomatic complexity (extract methods, simplify conditions, reduce nesting)"
                        ))

            except (IOError, OSError, SyntaxError):
                continue

        return issues


# =============================================================================
# Convenience Functions
# =============================================================================

def scan_project(project_root: Path) -> TechDebtReport:
    """Convenience function to scan project for tech debt.

    Args:
        project_root: Root directory of project to scan

    Returns:
        TechDebtReport with all detected issues

    Examples:
        >>> report = scan_project(Path("/project"))
        >>> if report.blocked:
        ...     print("Fix CRITICAL issues!")
    """
    detector = TechDebtDetector(project_root=project_root)
    return detector.analyze()
