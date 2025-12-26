"""Migration planning for brownfield retrofit.

This module generates step-by-step migration plans to align brownfield projects
with autonomous-dev standards. It analyzes alignment gaps, estimates effort,
detects dependencies, and optimizes execution order.

Classes:
    EffortSize: Effort size categories (XS/S/M/L/XL)
    ImpactLevel: Impact level categories (LOW/MEDIUM/HIGH)
    MigrationStep: Represents a single migration step
    MigrationPlan: Complete migration plan with steps and estimates
    MigrationPlanner: Main planning coordinator

Security:
    - CWE-22: Path validation via security_utils
    - CWE-117: Audit logging with sanitization
    - CWE-20: Input validation for all user inputs

Related:
    - GitHub Issue #59: Brownfield retrofit command implementation

Relevant Skills:
    - project-alignment-validation: Gap assessment methodology, prioritization patterns
    - error-handling-patterns: Exception hierarchy and error handling best practices
    - library-design-patterns: Standardized design patterns
    - state-management-patterns: Standardized design patterns
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List

from .security_utils import audit_log, validate_path
from .alignment_assessor import AlignmentGap, AssessmentResult, Severity


class EffortSize(Enum):
    """Effort size categories."""
    XS = "XS"  # 1 hour
    S = "S"    # 2 hours
    M = "M"    # 4 hours
    L = "L"    # 8 hours
    XL = "XL"  # 16 hours


class ImpactLevel(Enum):
    """Impact level categories."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class MigrationStep:
    """Represents a single migration step.

    Attributes:
        step_id: Unique step identifier (e.g., "STEP-001")
        title: Human-readable step title
        description: Detailed step description
        tasks: List of specific tasks to complete
        effort_size: T-shirt size estimate
        effort_hours: Estimated hours (derived from effort_size)
        impact_level: Impact on project (LOW/MEDIUM/HIGH)
        dependencies: List of step_ids that must complete first
        verification_criteria: List of criteria to verify completion
    """
    step_id: str
    title: str
    description: str
    tasks: List[str]
    effort_size: EffortSize
    effort_hours: float
    impact_level: ImpactLevel
    dependencies: List[str] = field(default_factory=list)
    verification_criteria: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all step data
        """
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "tasks": self.tasks,
            "effort_size": self.effort_size.value,
            "effort_hours": self.effort_hours,
            "impact_level": self.impact_level.value,
            "dependencies": self.dependencies,
            "verification_criteria": self.verification_criteria
        }


@dataclass
class MigrationPlan:
    """Complete migration plan with steps and estimates.

    Attributes:
        steps: List of migration steps in execution order
        total_effort_hours: Total estimated effort
        critical_path_hours: Critical path duration (accounting for parallelism)
    """
    steps: List[MigrationStep] = field(default_factory=list)
    total_effort_hours: float = 0.0
    critical_path_hours: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with all plan data
        """
        return {
            "steps": [step.to_dict() for step in self.steps],
            "total_effort_hours": self.total_effort_hours,
            "critical_path_hours": self.critical_path_hours,
            "step_count": len(self.steps)
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Convert to markdown format.

        Returns:
            Markdown-formatted migration plan
        """
        lines = [
            "# Migration Plan\n",
            f"**Total Steps**: {len(self.steps)}",
            f"**Total Effort**: {self.total_effort_hours:.1f} hours",
            f"**Critical Path**: {self.critical_path_hours:.1f} hours\n",
            "---\n"
        ]

        for i, step in enumerate(self.steps, 1):
            lines.append(f"## {i}. {step.title}\n")
            lines.append(f"**ID**: {step.step_id}")
            lines.append(f"**Effort**: {step.effort_size.value} ({step.effort_hours:.1f}h)")
            lines.append(f"**Impact**: {step.impact_level.value}\n")

            lines.append(f"**Description**: {step.description}\n")

            if step.dependencies:
                lines.append("**Dependencies**:")
                for dep in step.dependencies:
                    lines.append(f"- {dep}")
                lines.append("")

            lines.append("**Tasks**:")
            for task in step.tasks:
                lines.append(f"- {task}")
            lines.append("")

            if step.verification_criteria:
                lines.append("**Verification**:")
                for criterion in step.verification_criteria:
                    lines.append(f"- {criterion}")
                lines.append("")

            lines.append("---\n")

        return "\n".join(lines)


class MigrationPlanner:
    """Main migration planning coordinator.

    Analyzes alignment assessment results and generates optimized migration
    plans with effort estimates, dependency tracking, and execution ordering.
    """

    # Effort size to hours mapping
    EFFORT_HOURS = {
        EffortSize.XS: 1.0,
        EffortSize.S: 2.0,
        EffortSize.M: 4.0,
        EffortSize.L: 8.0,
        EffortSize.XL: 16.0
    }

    def __init__(self, project_root: Path):
        """Initialize migration planner.

        Args:
            project_root: Path to project root directory

        Raises:
            ValueError: If project_root invalid
        """
        # Security: Validate project root path (CWE-22)
        validated_root = validate_path(
            project_root,
            "project_root",
            allow_missing=False,
        )
        self.project_root = Path(validated_root)

        # Audit log initialization
        audit_log(
            "migration_planner_init",
            project_root=str(self.project_root),
            success=True
        )

    def plan(self, assessment: AssessmentResult) -> MigrationPlan:
        """Generate complete migration plan.

        Args:
            assessment: Alignment assessment results

        Returns:
            Migration plan with optimized execution order

        Raises:
            ValueError: If assessment invalid
        """
        if not assessment:
            raise ValueError("Assessment result required")

        audit_log(
            "migration_planning_start",
            project_root=str(self.project_root),
            gap_count=len(assessment.priority_list)
        )

        try:
            # Generate migration steps from prioritized gaps
            steps = self.generate_migration_steps(assessment.priority_list)

            # Detect dependencies between steps
            dependencies = self.detect_dependencies(steps)
            for step in steps:
                if step.step_id in dependencies:
                    step.dependencies = dependencies[step.step_id]

            # Optimize execution order
            optimized_steps = self.optimize_execution_order(steps)

            # Calculate totals
            total_effort = sum(step.effort_hours for step in optimized_steps)
            critical_path = self._calculate_critical_path(optimized_steps)

            plan = MigrationPlan(
                steps=optimized_steps,
                total_effort_hours=total_effort,
                critical_path_hours=critical_path
            )

            audit_log(
                "migration_planning_complete",
                project_root=str(self.project_root),
                step_count=len(optimized_steps),
                total_effort_hours=total_effort,
                critical_path_hours=critical_path,
                success=True
            )

            return plan

        except Exception as e:
            audit_log(
                "migration_planning_failed",
                project_root=str(self.project_root),
                error=str(e),
                success=False
            )
            raise

    def generate_migration_steps(self, gaps: List[AlignmentGap]) -> List[MigrationStep]:
        """Generate migration steps from alignment gaps.

        Args:
            gaps: List of prioritized alignment gaps

        Returns:
            List of migration steps
        """
        steps = []

        for i, gap in enumerate(gaps, 1):
            step_id = f"STEP-{i:03d}"

            # Estimate effort size
            effort_size = self.estimate_effort(gap)
            effort_hours = self.EFFORT_HOURS[effort_size]

            # Determine impact level
            impact_level = self._map_severity_to_impact(gap.severity)

            # Generate verification criteria
            verification_criteria = self._generate_verification_criteria(gap)

            step = MigrationStep(
                step_id=step_id,
                title=gap.description,
                description=f"**Current**: {gap.current_state}\n**Target**: {gap.desired_state}",
                tasks=gap.fix_steps,
                effort_size=effort_size,
                effort_hours=effort_hours,
                impact_level=impact_level,
                verification_criteria=verification_criteria
            )

            steps.append(step)

        return steps

    def estimate_effort(self, gap: AlignmentGap) -> EffortSize:
        """Estimate effort size for a gap.

        Args:
            gap: Alignment gap

        Returns:
            Effort size category
        """
        hours = gap.effort_hours

        if hours <= 1.5:
            return EffortSize.XS
        elif hours <= 3.0:
            return EffortSize.S
        elif hours <= 6.0:
            return EffortSize.M
        elif hours <= 12.0:
            return EffortSize.L
        else:
            return EffortSize.XL

    def analyze_impact(self, step: MigrationStep) -> str:
        """Analyze impact of a migration step.

        Args:
            step: Migration step

        Returns:
            Impact analysis description
        """
        impact_descriptions = {
            ImpactLevel.LOW: "Minimal impact - localized changes, low risk",
            ImpactLevel.MEDIUM: "Moderate impact - affects multiple areas, moderate risk",
            ImpactLevel.HIGH: "High impact - fundamental changes, high risk"
        }

        return impact_descriptions[step.impact_level]

    def detect_dependencies(self, steps: List[MigrationStep]) -> Dict[str, List[str]]:
        """Detect dependencies between migration steps.

        Args:
            steps: List of migration steps

        Returns:
            Dict mapping step_id to list of dependency step_ids
        """
        dependencies = {}

        # Build category index
        category_steps = {}
        for step in steps:
            # Extract category from description (simplified heuristic)
            category = self._extract_category(step)
            if category not in category_steps:
                category_steps[category] = []
            category_steps[category].append(step.step_id)

        # Define dependency rules
        dependency_rules = {
            "documentation": [],  # No dependencies
            "file-organization": [],  # No dependencies
            "testing": ["file-organization"],  # Tests depend on organization
            "automation": ["testing"],  # CI/CD depends on tests
            "twelve-factor": ["file-organization", "documentation"]  # Cleanup depends on basics
        }

        # Apply rules
        for step in steps:
            category = self._extract_category(step)
            step_deps = []

            if category in dependency_rules:
                for dep_category in dependency_rules[category]:
                    if dep_category in category_steps:
                        # Depend on all steps in that category
                        for dep_step_id in category_steps[dep_category]:
                            if dep_step_id != step.step_id:
                                step_deps.append(dep_step_id)

            if step_deps:
                dependencies[step.step_id] = step_deps

        return dependencies

    def optimize_execution_order(self, steps: List[MigrationStep]) -> List[MigrationStep]:
        """Optimize execution order using topological sort.

        Args:
            steps: List of migration steps

        Returns:
            Steps sorted by optimal execution order
        """
        # Build adjacency list
        graph = {step.step_id: step.dependencies for step in steps}
        step_map = {step.step_id: step for step in steps}

        # Topological sort (Kahn's algorithm)
        in_degree = {step_id: 0 for step_id in graph}
        for step_id, deps in graph.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[step_id] += 1

        # Queue of steps with no dependencies
        queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
        sorted_order = []

        while queue:
            # Sort queue by impact/effort for optimal ordering
            queue.sort(key=lambda sid: (
                -self._priority_score(step_map[sid]),  # Higher priority first
                step_map[sid].effort_hours  # Lower effort first (tie-breaker)
            ))

            current = queue.pop(0)
            sorted_order.append(current)

            # Update in-degrees
            for step_id, deps in graph.items():
                if current in deps:
                    in_degree[step_id] -= 1
                    if in_degree[step_id] == 0:
                        queue.append(step_id)

        # Return steps in sorted order
        return [step_map[step_id] for step_id in sorted_order]

    # Private helper methods

    def _map_severity_to_impact(self, severity: Severity) -> ImpactLevel:
        """Map gap severity to impact level.

        Args:
            severity: Gap severity

        Returns:
            Impact level
        """
        mapping = {
            Severity.CRITICAL: ImpactLevel.HIGH,
            Severity.HIGH: ImpactLevel.HIGH,
            Severity.MEDIUM: ImpactLevel.MEDIUM,
            Severity.LOW: ImpactLevel.LOW
        }
        return mapping[severity]

    def _generate_verification_criteria(self, gap: AlignmentGap) -> List[str]:
        """Generate verification criteria for a gap.

        Args:
            gap: Alignment gap

        Returns:
            List of verification criteria
        """
        criteria = []

        if gap.category == "documentation":
            criteria.append("PROJECT.md exists in .claude/ directory")
            criteria.append("All required sections present (GOALS, SCOPE, CONSTRAINTS)")
            criteria.append("Content matches project reality")

        elif gap.category == "file-organization":
            criteria.append("Files organized in standard directories")
            criteria.append("No source files in project root")
            criteria.append("Import paths updated and working")

        elif gap.category == "testing":
            criteria.append("Test framework installed and configured")
            criteria.append("Tests pass with pytest")
            criteria.append("Coverage > 80%")

        elif gap.category == "automation":
            criteria.append("CI/CD configuration exists")
            criteria.append("Automated tests run on commit")
            criteria.append("Status checks passing")

        else:
            criteria.append(f"Verify: {gap.desired_state}")
            criteria.append("Manual testing confirms functionality")

        return criteria

    def _extract_category(self, step: MigrationStep) -> str:
        """Extract category from step (heuristic).

        Args:
            step: Migration step

        Returns:
            Category name
        """
        title_lower = step.title.lower()

        if "project.md" in title_lower or "documentation" in title_lower:
            return "documentation"
        elif "file" in title_lower or "organization" in title_lower or "directory" in title_lower:
            return "file-organization"
        elif "test" in title_lower or "coverage" in title_lower:
            return "testing"
        elif "ci" in title_lower or "automation" in title_lower:
            return "automation"
        elif "12-factor" in title_lower or "twelve-factor" in title_lower:
            return "twelve-factor"
        else:
            return "other"

    def _priority_score(self, step: MigrationStep) -> float:
        """Calculate priority score for a step.

        Args:
            step: Migration step

        Returns:
            Priority score (higher = more important)
        """
        impact_score = {
            ImpactLevel.HIGH: 100,
            ImpactLevel.MEDIUM: 50,
            ImpactLevel.LOW: 25
        }

        # Impact/effort ratio
        effort = max(step.effort_hours, 0.1)
        return impact_score[step.impact_level] / effort

    def _calculate_critical_path(self, steps: List[MigrationStep]) -> float:
        """Calculate critical path duration.

        Uses dynamic programming to find longest path through dependency graph.

        Args:
            steps: List of migration steps in execution order

        Returns:
            Critical path duration in hours
        """
        # Build step map
        step_map = {step.step_id: step for step in steps}

        # Calculate longest path to each step
        longest_path = {}

        for step in steps:
            if not step.dependencies:
                # No dependencies - duration is just this step
                longest_path[step.step_id] = step.effort_hours
            else:
                # Duration is max of dependencies + this step
                max_dep_path = max(
                    longest_path.get(dep, 0)
                    for dep in step.dependencies
                    if dep in longest_path
                )
                longest_path[step.step_id] = max_dep_path + step.effort_hours

        # Critical path is maximum of all paths
        return max(longest_path.values()) if longest_path else 0.0
