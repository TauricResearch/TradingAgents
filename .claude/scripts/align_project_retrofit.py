#!/usr/bin/env python3
"""CLI script for /align-project-retrofit command.

This script orchestrates the brownfield retrofit process:
1. Analyze codebase structure and tech stack
2. Assess alignment with autonomous-dev standards
3. Generate migration plan
4. Execute migration (with backup/rollback)
5. Verify results and assess readiness

Usage:
    python align_project_retrofit.py [options]

Exit Codes:
    0: Success
    1: Error
    2: Verification failed (blockers present)

Related:
    - GitHub Issue #59: Brownfield retrofit command implementation
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.codebase_analyzer import CodebaseAnalyzer
from lib.alignment_assessor import AlignmentAssessor
from lib.migration_planner import MigrationPlanner
from lib.retrofit_executor import RetrofitExecutor, ExecutionMode
from lib.retrofit_verifier import RetrofitVerifier
from lib.security_utils import audit_log


def parse_args():
    """Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Retrofit brownfield projects for autonomous development",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full retrofit (step-by-step)
  python align_project_retrofit.py

  # Analyze only
  python align_project_retrofit.py --phase analyze

  # Plan only
  python align_project_retrofit.py --phase plan

  # Dry-run execution
  python align_project_retrofit.py --dry-run

  # Auto-execute all steps
  python align_project_retrofit.py --auto

  # JSON output
  python align_project_retrofit.py --json
        """
    )

    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Project root directory (default: current directory)"
    )

    parser.add_argument(
        "--phase",
        type=str,
        choices=["analyze", "assess", "plan", "execute", "verify", "all"],
        default="all",
        help="Which phase to run (default: all)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes"
    )

    parser.add_argument(
        "--auto",
        action="store_true",
        help="Execute all steps automatically (no confirmations)"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON for scripting"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (default: stdout)"
    )

    return parser.parse_args()


def run_analyze_phase(project_root: Path, verbose: bool = False) -> dict:
    """Run analysis phase.

    Args:
        project_root: Project root directory
        verbose: Enable verbose output

    Returns:
        Analysis results as dict
    """
    if verbose:
        print("PHASE 1: Analyzing codebase...")

    analyzer = CodebaseAnalyzer(project_root)
    analysis = analyzer.analyze()

    if verbose:
        print(f"  Tech Stack: {analysis.tech_stack.primary_language}")
        print(f"  Framework: {analysis.tech_stack.framework or 'None'}")
        print(f"  Files: {analysis.structure.total_files}")
        print(f"  Tests: {analysis.structure.test_files}")

    return {
        "phase": "analyze",
        "tech_stack": {
            "primary_language": analysis.tech_stack.primary_language,
            "framework": analysis.tech_stack.framework,
            "package_manager": analysis.tech_stack.package_manager,
            "test_framework": analysis.tech_stack.test_framework,
            "dependencies": list(analysis.tech_stack.dependencies)[:20]  # Top 20
        },
        "structure": {
            "total_files": analysis.structure.total_files,
            "source_files": analysis.structure.source_files,
            "test_files": analysis.structure.test_files,
            "config_files": analysis.structure.config_files,
            "doc_files": analysis.structure.doc_files,
            "has_src_dir": analysis.structure.has_src_dir,
            "has_tests_dir": analysis.structure.has_tests_dir,
            "has_docs_dir": analysis.structure.has_docs_dir
        },
        "analysis_object": analysis  # For next phase
    }


def run_assess_phase(project_root: Path, analysis_result: dict, verbose: bool = False) -> dict:
    """Run assessment phase.

    Args:
        project_root: Project root directory
        analysis_result: Results from analyze phase
        verbose: Enable verbose output

    Returns:
        Assessment results as dict
    """
    if verbose:
        print("PHASE 2: Assessing alignment...")

    assessor = AlignmentAssessor(project_root)
    assessment = assessor.assess(analysis_result["analysis_object"])

    if verbose:
        print(f"  12-Factor Score: {assessment.twelve_factor_score.compliance_percentage:.1f}%")
        print(f"  Alignment Gaps: {len(assessment.gaps)}")
        print(f"  PROJECT.md Confidence: {assessment.project_md.confidence:.2f}")

    return {
        "phase": "assess",
        "twelve_factor_score": assessment.twelve_factor_score.compliance_percentage,
        "gap_count": len(assessment.gaps),
        "priority_gaps": [
            {
                "category": gap.category,
                "severity": gap.severity.value,
                "description": gap.description,
                "impact": gap.impact_score,
                "effort": gap.effort_hours
            }
            for gap in assessment.priority_list[:5]  # Top 5
        ],
        "project_md_confidence": assessment.project_md.confidence,
        "assessment_object": assessment  # For next phase
    }


def run_plan_phase(project_root: Path, assessment_result: dict, verbose: bool = False) -> dict:
    """Run planning phase.

    Args:
        project_root: Project root directory
        assessment_result: Results from assess phase
        verbose: Enable verbose output

    Returns:
        Planning results as dict
    """
    if verbose:
        print("PHASE 3: Generating migration plan...")

    planner = MigrationPlanner(project_root)
    plan = planner.plan(assessment_result["assessment_object"])

    if verbose:
        print(f"  Migration Steps: {len(plan.steps)}")
        print(f"  Total Effort: {plan.total_effort_hours:.1f} hours")
        print(f"  Critical Path: {plan.critical_path_hours:.1f} hours")

    return {
        "phase": "plan",
        "step_count": len(plan.steps),
        "total_effort_hours": plan.total_effort_hours,
        "critical_path_hours": plan.critical_path_hours,
        "steps": [
            {
                "step_id": step.step_id,
                "title": step.title,
                "effort_size": step.effort_size.value,
                "effort_hours": step.effort_hours,
                "impact": step.impact_level.value
            }
            for step in plan.steps
        ],
        "plan_object": plan  # For next phase
    }


def run_execute_phase(
    project_root: Path,
    plan_result: dict,
    mode: ExecutionMode,
    verbose: bool = False
) -> dict:
    """Run execution phase.

    Args:
        project_root: Project root directory
        plan_result: Results from plan phase
        mode: Execution mode
        verbose: Enable verbose output

    Returns:
        Execution results as dict
    """
    if verbose:
        mode_str = "DRY RUN" if mode == ExecutionMode.DRY_RUN else "EXECUTING"
        print(f"PHASE 4: {mode_str} migration...")

    executor = RetrofitExecutor(project_root)
    execution = executor.execute(plan_result["plan_object"], mode)

    if verbose:
        print(f"  Completed: {len(execution.completed_steps)}")
        print(f"  Failed: {len(execution.failed_steps)}")
        if execution.backup:
            print(f"  Backup: {execution.backup.backup_path}")
        if execution.rollback_performed:
            print("  Rollback: PERFORMED")

    return {
        "phase": "execute",
        "mode": mode.value,
        "completed": len(execution.completed_steps),
        "failed": len(execution.failed_steps),
        "rollback": execution.rollback_performed,
        "backup_path": str(execution.backup.backup_path) if execution.backup else None,
        "execution_object": execution  # For next phase
    }


def run_verify_phase(project_root: Path, execution_result: dict, verbose: bool = False) -> dict:
    """Run verification phase.

    Args:
        project_root: Project root directory
        execution_result: Results from execute phase
        verbose: Enable verbose output

    Returns:
        Verification results as dict
    """
    if verbose:
        print("PHASE 5: Verifying results...")

    verifier = RetrofitVerifier(project_root)
    verification = verifier.verify(execution_result["execution_object"])

    if verbose:
        print(f"  Readiness Score: {verification.readiness_score:.1f}%")
        print(f"  Compliance Checks: {len([c for c in verification.compliance_checks if c.passed])}/{len(verification.compliance_checks)} passed")
        print(f"  Blockers: {len(verification.blockers)}")
        print(f"  Ready for /auto-implement: {'YES' if verification.ready_for_auto_implement else 'NO'}")

    return {
        "phase": "verify",
        "readiness_score": verification.readiness_score,
        "checks_passed": len([c for c in verification.compliance_checks if c.passed]),
        "checks_total": len(verification.compliance_checks),
        "blockers": verification.blockers,
        "ready_for_auto_implement": verification.ready_for_auto_implement,
        "verification_object": verification
    }


def main():
    """Main entry point."""
    args = parse_args()

    # Resolve project root
    project_root = Path(args.project_root).resolve()

    audit_log(
        "align_project_retrofit_start",
        project_root=str(project_root),
        phase=args.phase,
        dry_run=args.dry_run,
        auto=args.auto
    )

    try:
        results = {}

        # Determine execution mode
        if args.dry_run:
            exec_mode = ExecutionMode.DRY_RUN
        elif args.auto:
            exec_mode = ExecutionMode.AUTO
        else:
            exec_mode = ExecutionMode.STEP_BY_STEP

        # Run requested phases
        if args.phase in ["analyze", "all"]:
            results["analyze"] = run_analyze_phase(project_root, args.verbose)

        if args.phase in ["assess", "all"] and "analyze" in results:
            results["assess"] = run_assess_phase(project_root, results["analyze"], args.verbose)

        if args.phase in ["plan", "all"] and "assess" in results:
            results["plan"] = run_plan_phase(project_root, results["assess"], args.verbose)

        if args.phase in ["execute", "all"] and "plan" in results:
            results["execute"] = run_execute_phase(
                project_root,
                results["plan"],
                exec_mode,
                args.verbose
            )

        if args.phase in ["verify", "all"] and "execute" in results:
            results["verify"] = run_verify_phase(project_root, results["execute"], args.verbose)

        # Clean up non-serializable objects
        for phase_key in results:
            if "analysis_object" in results[phase_key]:
                del results[phase_key]["analysis_object"]
            if "assessment_object" in results[phase_key]:
                del results[phase_key]["assessment_object"]
            if "plan_object" in results[phase_key]:
                del results[phase_key]["plan_object"]
            if "execution_object" in results[phase_key]:
                del results[phase_key]["execution_object"]
            if "verification_object" in results[phase_key]:
                del results[phase_key]["verification_object"]

        # Output results
        if args.json:
            output = json.dumps(results, indent=2)
            if args.output:
                Path(args.output).write_text(output)
            else:
                print(output)
        else:
            # Human-readable output
            if not args.verbose:
                print("\n=== Retrofit Complete ===\n")
                if "verify" in results:
                    verify = results["verify"]
                    print(f"Readiness Score: {verify['readiness_score']:.1f}%")
                    print(f"Compliance: {verify['checks_passed']}/{verify['checks_total']} checks passed")
                    print(f"Blockers: {len(verify['blockers'])}")
                    print(f"Ready for /auto-implement: {'YES' if verify['ready_for_auto_implement'] else 'NO'}")

                    if verify['blockers']:
                        print("\nBlockers:")
                        for blocker in verify['blockers']:
                            print(f"  - {blocker}")

        audit_log(
            "align_project_retrofit_complete",
            project_root=str(project_root),
            success=True
        )

        # Exit code based on verification results
        if "verify" in results:
            if results["verify"]["blockers"]:
                return 2  # Blockers present
            return 0  # Success
        return 0

    except Exception as e:
        audit_log(
            "align_project_retrofit_failed",
            project_root=str(project_root),
            error=str(e),
            success=False
        )

        if args.json:
            error_output = {
                "error": str(e),
                "success": False
            }
            if args.output:
                Path(args.output).write_text(json.dumps(error_output, indent=2))
            else:
                print(json.dumps(error_output, indent=2))
        else:
            print(f"ERROR: {e}", file=sys.stderr)

        return 1


if __name__ == "__main__":
    sys.exit(main())
