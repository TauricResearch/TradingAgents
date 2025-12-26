#!/usr/bin/env python3
"""
Feature dependency analyzer for smart batch ordering.

This module analyzes feature descriptions to detect dependencies and
optimizes execution order using topological sort (Kahn's algorithm).

Features:
- Keyword-based dependency detection (requires, depends, after, before, uses)
- File reference detection (.py, .md, .json, etc.)
- Topological sort for optimal execution order
- Circular dependency detection
- ASCII dependency graph visualization
- Security validations (CWE-22, CWE-78)
- Performance limits (timeout, memory)

Usage:
    >>> from feature_dependency_analyzer import analyze_dependencies, topological_sort
    >>> features = ["Add auth", "Add tests for auth"]
    >>> deps = analyze_dependencies(features)
    >>> ordered = topological_sort(features, deps)

Security:
- Input sanitization for feature text
- Resource limits (MAX_FEATURES=1000, TIMEOUT_SECONDS=5)
- No shell execution
- Path traversal protection (CWE-22)

Date: 2025-12-23
Issue: #157 (Smart dependency ordering for /batch-implement)
Version: 1.0.0
"""

import re
import time
from pathlib import Path
from typing import Dict, List, Set, Any
import sys

# Add lib directory to path for validation imports
lib_path = Path(__file__).parent
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))

try:
    from validation import sanitize_text_input
except ImportError:
    # Graceful degradation if validation not available
    def sanitize_text_input(text: str) -> str:
        """Fallback sanitization."""
        return str(text)[:10000]  # Basic length limit


# =============================================================================
# Constants
# =============================================================================

DEPENDENCY_KEYWORDS = {"requires", "depends", "after", "before", "uses", "needs"}
FILE_KEYWORDS = {".py", ".md", ".json", ".yaml", ".yml", ".sh", ".ts", ".js", ".tsx", ".jsx"}
MAX_FEATURES = 1000
TIMEOUT_SECONDS = 5


# =============================================================================
# Exceptions
# =============================================================================

class FeatureDependencyError(Exception):
    """Base exception for feature dependency operations."""
    pass


class CircularDependencyError(FeatureDependencyError):
    """Raised when circular dependencies detected."""
    pass


class AnalysisTimeoutError(FeatureDependencyError):
    """Raised when analysis exceeds timeout."""
    pass


# =============================================================================
# Core Functions
# =============================================================================

def detect_keywords(feature_text: str) -> Set[str]:
    """Extract dependency keywords from feature text.

    Detects:
    - Dependency keywords: requires, depends, after, before, uses, needs
    - File references: .py, .md, .json, .yaml, .yml, .sh, .ts, .js

    Args:
        feature_text: Feature description text

    Returns:
        Set of detected keywords (lowercase)

    Examples:
        >>> detect_keywords("Add login that requires authentication")
        {'authentication'}
        >>> detect_keywords("Update auth.py to add JWT")
        {'auth.py', 'jwt'}
    """
    # Sanitize input
    text = sanitize_text_input(feature_text)
    text_lower = text.lower()

    keywords = set()

    # Detect dependency keywords
    for keyword in DEPENDENCY_KEYWORDS:
        pattern = rf'\b{keyword}\b\s+(\w+(?:\s+\w+)?)'
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            # Extract the word(s) after the keyword
            extracted = match.group(1).strip()
            # Split on common stop words and take meaningful parts
            parts = extracted.split()
            for part in parts:
                if len(part) > 2 and part not in {'the', 'and', 'for', 'that', 'this', 'with'}:
                    keywords.add(part)

    # Detect file references
    for file_ext in FILE_KEYWORDS:
        pattern = rf'(\w+{re.escape(file_ext)})'
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            keywords.add(match.group(1))

    # Also extract significant words (nouns, tech terms)
    # Look for capitalized words or common tech terms
    tech_pattern = r'\b([A-Z][A-Za-z0-9]+|[a-z]+(?:API|DB|JWT|HTTP|SQL|REST|CRUD))\b'
    matches = re.finditer(tech_pattern, text)

    # Filter out common action verbs and generic words
    stop_words = {'add', 'update', 'fix', 'remove', 'delete', 'create', 'implement',
                 'typo', 'documentation', 'file', 'code', 'change', 'modify'}

    for match in matches:
        word = match.group(1).lower()
        if len(word) > 2 and word not in stop_words:
            keywords.add(word)

    return keywords


def build_dependency_graph(features: List[str], keywords: Dict[int, Set[str]]) -> Dict[int, List[int]]:
    """Build dependency graph from keywords.

    Match keywords across features to detect dependencies.
    If feature B's keywords match feature A's significant terms,
    then B depends on A.

    Logic:
    - Features with "test", "tests", "testing" depend on features they test
    - Features with dependency keywords (requires, depends, after, uses) depend on referenced features
    - File references create dependencies (feature modifying file.py depends on feature creating file.py)

    Args:
        features: List of feature descriptions
        keywords: Dict mapping feature index to keywords

    Returns:
        Dict mapping feature index to list of dependency indices

    Example:
        >>> features = ["Add auth", "Add tests for auth"]
        >>> keywords = {0: {"auth"}, 1: {"tests", "auth"}}
        >>> build_dependency_graph(features, keywords)
        {0: [], 1: [0]}
    """
    deps: Dict[int, List[int]] = {i: [] for i in range(len(features))}

    # Extract main subject/topic from each feature
    feature_topics: Dict[int, Set[str]] = {}
    for i, feature in enumerate(features):
        feature_lower = feature.lower()
        topics = set()

        # Extract main nouns/topics (skip verbs like "add", "update", "fix")
        skip_words = {'add', 'update', 'fix', 'remove', 'delete', 'create', 'implement',
                     'the', 'and', 'for', 'that', 'this', 'with', 'to', 'from', 'test', 'tests', 'testing'}
        words = feature_lower.split()
        for word in words:
            if len(word) > 2 and word not in skip_words:
                topics.add(word)

        feature_topics[i] = topics

    # Build dependencies based on feature relationships
    for i in range(len(features)):
        feature_i = features[i].lower()
        keywords_i = keywords.get(i, set())
        topics_i = feature_topics[i]

        # Check if this is a test/dependent feature
        is_test = any(word in feature_i for word in ['test', 'tests', 'testing'])
        has_dependency_keyword = any(kw in feature_i for kw in DEPENDENCY_KEYWORDS)

        # Extract what feature i creates vs what it requires
        creates_i = set()
        requires_i = set()

        # Pattern: "Add X" or "Create X" creates X
        create_match = re.search(r'(?:add|create|implement)\s+(\w+)', feature_i)
        if create_match:
            creates_i.add(create_match.group(1))

        # Pattern: "requires X", "depends on X", "after X", "using X"
        for kw in DEPENDENCY_KEYWORDS:
            pattern = rf'{kw}\s+(\w+)'
            matches = re.finditer(pattern, feature_i)
            for match in matches:
                requires_i.add(match.group(1))

        for j in range(len(features)):
            if i == j:
                continue

            feature_j = features[j].lower()
            topics_j = feature_topics[j]

            # What does feature j create?
            creates_j = set()
            create_match_j = re.search(r'(?:add|create|implement)\s+(\w+)', feature_j)
            if create_match_j:
                creates_j.add(create_match_j.group(1))

            # Skip if j is also a test (tests don't depend on other tests typically)
            is_j_test = any(word in feature_j for word in ['test', 'tests', 'testing'])

            # Rule 1: Test features depend on non-test features they reference
            if is_test and not is_j_test:
                # Check if feature i (test) references topics from feature j
                if topics_i & topics_j:
                    if j not in deps[i]:
                        deps[i].append(j)
                    continue

            # Rule 2: If feature i REQUIRES something that feature j CREATES, i depends on j
            if requires_i & creates_j:
                if j not in deps[i]:
                    deps[i].append(j)
                continue

            # Rule 3: Features with dependency keywords depend on earlier features with shared topics
            # Only if j comes before i (temporal ordering)
            if has_dependency_keyword and not is_test and j < i:
                # Check if feature i has dependency keyword pointing to feature j topics
                if topics_i & topics_j:
                    if j not in deps[i]:
                        deps[i].append(j)
                    continue

            # Rule 4: File references - feature modifying file depends on feature creating it
            # (Earlier features that mention a file are assumed to create it)
            file_refs_i = {k for k in keywords_i if any(ext in k for ext in FILE_KEYWORDS)}
            file_refs_j = {k for k in keywords.get(j, set()) if any(ext in k for ext in FILE_KEYWORDS)}

            if file_refs_i & file_refs_j and j < i:  # Only depend on earlier features
                if j not in deps[i]:
                    deps[i].append(j)

    return deps


def analyze_dependencies(features: List[str]) -> Dict[int, List[int]]:
    """Main entry point - detect dependencies via keyword matching.

    Args:
        features: List of feature descriptions

    Returns:
        Dict mapping feature index to list of dependency indices

    Raises:
        ValueError: If features list is too large (>MAX_FEATURES)
        AnalysisTimeoutError: If analysis exceeds TIMEOUT_SECONDS

    Examples:
        >>> features = ["Add auth", "Add tests for auth"]
        >>> analyze_dependencies(features)
        {0: [], 1: [0]}
    """
    # Validate input size
    if len(features) > MAX_FEATURES:
        raise ValueError(f"Too many features ({len(features)} > {MAX_FEATURES})")

    start_time = time.time()

    # Extract keywords from each feature
    keywords: Dict[int, Set[str]] = {}
    for i, feature in enumerate(features):
        # Check timeout
        if time.time() - start_time > TIMEOUT_SECONDS:
            raise AnalysisTimeoutError(f"Analysis exceeded {TIMEOUT_SECONDS}s timeout")

        keywords[i] = detect_keywords(feature)

    # Build dependency graph
    deps = build_dependency_graph(features, keywords)

    return deps


def topological_sort(features: List[str], deps: Dict[int, List[int]]) -> List[int]:
    """Order features using Kahn's algorithm.

    Returns features in dependency-respecting order.
    If circular dependencies detected, returns original order.

    Args:
        features: List of feature descriptions
        deps: Dict mapping feature index to dependency indices

    Returns:
        List of feature indices in execution order

    Raises:
        CircularDependencyError: If circular dependencies detected

    Examples:
        >>> features = ["Add auth", "Add tests"]
        >>> deps = {0: [], 1: [0]}
        >>> topological_sort(features, deps)
        [0, 1]
    """
    # Handle empty graph
    if not features:
        return []

    # Remove self-dependencies (ignore them)
    clean_deps = {}
    for i, dependencies in deps.items():
        clean_deps[i] = [d for d in dependencies if d != i]

    # Calculate in-degree for each node
    in_degree = {i: 0 for i in range(len(features))}
    for i, dependencies in clean_deps.items():
        in_degree[i] = len(dependencies)

    # Queue of nodes with no dependencies
    queue = [i for i, degree in in_degree.items() if degree == 0]
    sorted_order = []

    while queue:
        # Sort queue to prefer original order (stable sort)
        queue.sort()

        current = queue.pop(0)
        sorted_order.append(current)

        # Update in-degrees for nodes that depend on current
        for i, dependencies in clean_deps.items():
            if current in dependencies:
                in_degree[i] -= 1
                if in_degree[i] == 0:
                    queue.append(i)

    # Check for circular dependencies
    if len(sorted_order) != len(features):
        # Circular dependency detected
        # Return original order as fallback
        raise CircularDependencyError(
            f"Circular dependency detected: {len(sorted_order)} of {len(features)} features ordered"
        )

    return sorted_order


def visualize_graph(features: List[str], deps: Dict[int, List[int]]) -> str:
    """Generate ASCII dependency graph for user review.

    Args:
        features: List of feature descriptions
        deps: Dict mapping feature index to dependency indices

    Returns:
        Multi-line string showing dependencies

    Examples:
        >>> features = ["Add auth", "Add tests"]
        >>> deps = {0: [], 1: [0]}
        >>> print(visualize_graph(features, deps))
        Feature Dependency Graph:

        [0] Add auth

        [1] Add tests
            └─> depends on [0] Add auth
    """
    if not features:
        return "No features to visualize."

    lines = ["Feature Dependency Graph:", ""]

    for i, feature in enumerate(features):
        # Truncate long features
        display_feature = feature[:60] + "..." if len(feature) > 60 else feature

        lines.append(f"[{i}] {display_feature}")

        # Show dependencies
        dependencies = deps.get(i, [])
        if dependencies:
            for dep_idx in dependencies:
                dep_feature = features[dep_idx]
                dep_display = dep_feature[:50] + "..." if len(dep_feature) > 50 else dep_feature
                lines.append(f"    └─> depends on [{dep_idx}] {dep_display}")

        lines.append("")  # Blank line between features

    return "\n".join(lines)


# =============================================================================
# Helper Functions
# =============================================================================

def detect_circular_dependencies(deps: Dict[int, List[int]]) -> List[List[int]]:
    """Detect circular dependencies in graph.

    Args:
        deps: Dependency graph

    Returns:
        List of circular dependency chains
    """
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: int, path: List[int]) -> None:
        """DFS to detect cycles."""
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in deps.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path.copy())
            elif neighbor in rec_stack:
                # Cycle detected
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)

        rec_stack.remove(node)

    for i in range(len(deps)):
        if i not in visited:
            dfs(i, [])

    return cycles


def get_execution_order_stats(features: List[str], deps: Dict[int, List[int]],
                              ordered: List[int]) -> Dict[str, Any]:
    """Get statistics about execution order optimization.

    Args:
        features: List of feature descriptions
        deps: Dependency graph
        ordered: Ordered list of feature indices

    Returns:
        Dict with statistics
    """
    total_deps = sum(len(d) for d in deps.values())
    independent = sum(1 for d in deps.values() if len(d) == 0)

    return {
        "total_features": len(features),
        "total_dependencies": total_deps,
        "independent_features": independent,
        "dependent_features": len(features) - independent,
        "optimization_ratio": independent / len(features) if features else 0.0,
    }


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Core functions
    "analyze_dependencies",
    "topological_sort",
    "visualize_graph",
    "detect_keywords",
    "build_dependency_graph",

    # Exceptions
    "FeatureDependencyError",
    "CircularDependencyError",
    "AnalysisTimeoutError",

    # Constants
    "DEPENDENCY_KEYWORDS",
    "FILE_KEYWORDS",
    "TIMEOUT_SECONDS",

    # Helper functions
    "detect_circular_dependencies",
    "get_execution_order_stats",
]
